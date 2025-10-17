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

import datetime as dt
import pandas as pd
from typing import Any, Type

from gs_quant.api.gs.backtests_xasset.response_datatypes.risk_result import RiskResultsByDate, RefType, \
    RiskResultsError, RiskResults
from gs_quant.api.gs.backtests_xasset.response_datatypes.risk_result_datatypes import FloatWithData, StringWithData, \
    VectorWithData, MatrixWithData, RiskResultWithData

_FLOAT_TYPES = (float, int)

_STR_TYPE = str

_SERIES_TYPE = pd.Series

_DF_TYPE = pd.DataFrame

_type_to_datatype_map = {'float': FloatWithData, 'string': StringWithData,
                         'vector': VectorWithData, 'matrix': MatrixWithData}


def map_result_to_datatype(data: Any) -> Type[RiskResultWithData]:
    # Fast path: use type() for class identity when possible, speeds up for builtins
    dt = type(data)
    if dt in _FLOAT_TYPES:
        return FloatWithData
    # str check
    if dt is _STR_TYPE:
        return StringWithData
    # pandas type checks (class identity should suffice and is faster than isinstance)
    if dt is _SERIES_TYPE:
        return VectorWithData
    if dt is _DF_TYPE:
        return MatrixWithData
    # Fallback to isinstance for subtyping support
    if isinstance(data, _FLOAT_TYPES):
        return FloatWithData
    if isinstance(data, _STR_TYPE):
        return StringWithData
    if isinstance(data, _SERIES_TYPE):
        return VectorWithData
    if isinstance(data, _DF_TYPE):
        return MatrixWithData
    raise ValueError('Cannot assign result type to data')


def decode_risk_result_with_data(r: dict) -> RiskResultWithData:
    return _type_to_datatype_map[r['type']].from_dict(r)


def decode_risk_result(d: dict) -> RiskResults:
    refs = {RefType(k): v for k, v in d['refs'].items()}
    if 'result' in d:
        result = {dt.date.fromisoformat(k): decode_risk_result_with_data(v) for k, v in d['result'].items()}
        return RiskResultsByDate(refs, result)
    else:
        return RiskResultsError(refs, d['error'], d['trace_id'])
