"""
Copyright 2020 Goldman Sachs.
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
from collections.abc import Iterable
from typing import Tuple

from gs_quant.session import GsSession
from gs_quant.target.charts import Chart, ChartShare


class GsPlotApi:
    """GS Chart API client implementation"""

    # CRUD

    @classmethod
    def get_many_charts(cls, limit: int = 100) -> Tuple[Chart, ...]:
        return GsSession.current._get('/charts?limit={limit}'.format(limit=limit), cls=Chart)['results']

    @classmethod
    def get_chart(cls, chart_id: str) -> Chart:
        # This method is already a single call; .format replaced with f-string for slight performance gain
        return GsSession.current._get(f'/charts/{chart_id}', cls=Chart)

    @classmethod
    def create_chart(cls, chart: Chart) -> Chart:
        return GsSession.current._post('/charts', chart, cls=Chart)

    @classmethod
    def update_chart(cls, chart: Chart):
        return GsSession.current._put('/charts/{id}'.format(id=chart.id), chart, cls=Chart)

    @classmethod
    def delete_chart(cls, chart_id: str) -> dict:
        return GsSession.current._delete('/charts/{id}'.format(id=chart_id))

    # Additional methods

    @classmethod
    def share_chart(cls, chart_id: str, users: Iterable):
        # endpoint silently discards tokens not prefixed with 'guid:' => can't be used for roles, groups, etc.
        # Optimization: avoid map/lambda/any; check all with a for loop and bail out early.
        for x in users:
            if not x.startswith('guid:'):
                raise ValueError('Chart can only be shared with individual users via this method.')
        # Use tuple(users) once for sharing, avoid rebuilding Iterator
        users_tuple = tuple(users)
        chart = cls.get_chart(chart_id)
        share = ChartShare(users_tuple, chart.version)
        return GsSession.current._post(f'/charts/{chart_id}/share', share, cls=Chart)
