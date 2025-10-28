"""
Copyright 2019 Goldman Sachs.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""

from base64 import b64decode
from collections import OrderedDict
from enum import Enum
from typing import List, Tuple
from urllib.parse import quote

from gs_quant.session import GsSession
from gs_quant.target.content import ContentResponse, GetManyContentsResponse


class OrderBy(Enum):
    """
    Content ordering
    """
    ASC = 'asc'
    DESC = 'desc'

    def __str__(self):
        return str(self.value)


class GsContentApi:
    """GS Content API client implementation"""

    @classmethod
    def get_contents(
            cls,
            channels: set = None,
            asset_ids: set = None,
            author_ids: set = None,
            tags: set = None,
            offset: int = 0,
            limit: int = 10,
            order_by: dict = {'direction': OrderBy.DESC, 'field': 'createdTime'}
    ) -> List[ContentResponse]:
        """
        Get contents for given parameters

        :param channels: Channels
        :param asset_ids: Marquee Asset Ids
        :param author_ids: Marquee Author Guids
        :param tags: Tags
        :param limit: Limit (number of contents to return)
        :param offset: Offset (offset of contents)
        :param order_by: OrderBy (dict for specifying how to sort contents)
        :return: A list of ContentResponse objects

        **Examples**

        >>> from gs_quant.api.gs.content import GsContentApi
        >>> from gs_quant.session import GsSession
        >>>
        >>> GsSession.use()
        >>> contents = GsContentApi.get_contents(channels=['G10'])
        """

        if limit and limit > 1000:
            raise ValueError('Limit is too large. Limit must be <= 1000.')

        if offset and (offset < 0 or offset >= limit):
            raise ValueError('Invalid offset. Offset must be >= 0 and < limit')

        # Avoid method call overhead and unnecessary list creation for repeatedly used fields
        offset_param = [offset] if offset else None
        limit_param = [limit] if limit else None
        order_by_param = [order_by] if order_by else None

        parameters_dict = cls._build_parameters_dict(
            channel=channels,
            asset_id=asset_ids,
            author_id=author_ids,
            tag=tags,
            offset=offset_param,
            limit=limit_param,
            order_by=order_by_param)

        query_string = '' if not parameters_dict else cls._build_query_string(parameters_dict)
        contents = GsSession.current._get(f'/content{query_string}', cls=GetManyContentsResponse)
        return contents.data

    @staticmethod
    def get_text(contents: List[ContentResponse]) -> List[Tuple[str, str]]:
        """
        Get text for contents

        :param contents: List of ContentResponse objects
        :return: A list of tuples representing (<content_id>, <content_text>)

        **Examples**

        >>> from gs_quant.api.gs.content import GsContentApi
        >>> from gs_quant.session import GsSession
        >>>
        >>> GsSession.use()
        >>> contents = GsContentApi.get_contents(channels=['G10'])
        >>> text = gs_content_api.get_text(contents)
        """
        return [(content.id, b64decode(content.content.body)) for content in contents]

    @classmethod
    def _build_parameters_dict(cls, **kwargs) -> dict:
        """
        Builds dict of valid parameters to their value,
        filtering out any parameters for which "None" is
        the value.
        """
        # Avoid redundant setdefault by collecting into a dict first, then perform sorting once
        parameters = {}
        for key, value in kwargs.items():
            if value:
                # Use sorted() only if value has multiple items; optimize single-item cases
                values = value
                if len(values) > 1:
                    parameters[key] = sorted(values)
                else:
                    parameters[key] = list(values)
        return OrderedDict(parameters)

    @classmethod
    def _build_query_string(cls, parameters: dict) -> str:
        """
        Builds a query string accepted by the Content API

        Example:

        In: { 'channel': ['G10', 'EM'], 'limit': 10 }
        Out: ?channel=G10&channel=EM&limit=10
        """
        # Precalculate length for faster join, remove enumerate loop
        param_items = []
        for parameter_name, parameter_values in parameters.items():
            for parameter_value in parameter_values:
                value = parameter_value
                if isinstance(value, str):
                    value = quote(value.encode())
                if parameter_name == 'order_by':
                    value = cls._convert_order_by(value)
                param_items.append(f'{parameter_name}={value}')
        if not param_items:
            return '?'
        return '?' + '&'.join(param_items)

    @classmethod
    def _convert_order_by(cls, order_by: dict) -> str:
        """
        Converts an orderByDirection and orderByField to an acceptable query parameter format
        expected by the Content API
        """
        direction = order_by['direction']

        if direction == OrderBy.DESC:
            order_by_parameter = '>'
        else:
            order_by_parameter = '<'

        return order_by_parameter + order_by['field']
