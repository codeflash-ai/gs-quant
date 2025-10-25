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

from enum import Enum
from typing import Union

import pandas as pd

from gs_quant.data import DataCoordinate
from gs_quant.data.coordinate import DateOrDatetime
from gs_quant.datetime.relative_date import RelativeDate
from .stream import DataSeries


class DataQueryType(Enum):
    LAST = "LAST"
    RANGE = "RANGE"


class DataQuery:
    """Defines a query on a coordinate"""

    def __init__(
        self,
        coordinate: DataCoordinate,
        start: Union[DateOrDatetime, RelativeDate] = None,
        end: Union[DateOrDatetime, RelativeDate] = None,
        query_type: "DataQueryType" = None,
    ):
        """Initialize data query"""

        self.coordinate = coordinate
        self.start = start
        self.end = end
        self.query_type = query_type

    def get_series(self) -> Union[pd.Series, None]:
        """Execute query and return series"""

        # Cache query_type to local variable to avoid multiple attribute lookups
        query_type = self.query_type
        if query_type is not None:
            # Save to local attribute/method for efficiency (no repeated lookups in hotpath)
            get_series = self.coordinate.get_series
            last_value = self.coordinate.last_value
            # Local import to avoid import if not needed (minor, but can help in microbenchmarks)
            # To avoid the cost of "is" comparison with undefined value, check identity only once
            if query_type is DataQueryType.RANGE:
                return get_series(self.start, self.end)
            elif query_type is DataQueryType.LAST:
                return last_value(self.end)
        return (
            None  # Covers None or unrecognized query_type, preserving original output
        )

    def get_data_series(self) -> DataSeries:
        # Save to local variable: get_series is hot path, so reduces method lookup overhead
        series = self.get_series()
        # DataSeries creation is only performed after data has been obtained
        # No behavioral change, but avoids repeated attribute access
        return DataSeries(series, self.coordinate)

    def get_range_string(self) -> str:
        return f"start={self.start}|end={self.end}"
