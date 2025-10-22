"""
Copyright 2021 Goldman Sachs.
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

import datetime as dt
import pandas as pd
import math
from typing import List
from pandas.tseries.offsets import BDay


def _get_ppaa_batches(asset_count: pd.DataFrame, max_row_limit: int) \
        -> List[List[dt.date]]:
    # Use .iat for faster, direct indexing to extract start_row and end_row values
    start_asset_count = asset_count['assetCount'].iat[0]
    end_asset_count = asset_count['assetCount'].iat[-1]
    start_date_str = asset_count['date'].iat[0]
    end_date_str = asset_count['date'].iat[-1]

    avg_positions = start_asset_count + end_asset_count / 2
    start_date = dt.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = dt.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    # multiply by 5 because of # fields: pnl, exposure, asset id, report id, date
    days_per_batch = math.ceil(max_row_limit / (avg_positions * 5))
    return _batch_dates(start_date, end_date, days_per_batch)


def _batch_dates(start_date: dt.date, end_date: dt.date, batch_size: int) -> List[List[dt.date]]:
    if (start_date - end_date).days < batch_size:
        return [[start_date, end_date]]
    date_list = []
    curr_start = start_date
    # Precompute the business days for better performance
    while end_date > curr_start:
        # Use pd.Timestamp for direct addition and conversion
        curr_end_bday = (pd.Timestamp(curr_start) + BDay(batch_size)).date()
        curr_end = min(curr_end_bday, end_date)
        date_list.append([curr_start, curr_end])
        curr_start = curr_end + dt.timedelta(days=1)
    return date_list
