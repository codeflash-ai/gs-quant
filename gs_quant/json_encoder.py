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
from enum import Enum
import json
import pandas as pd

from gs_quant.base import Base, Market
from gs_quant.json_convertors import encode_date_or_str, encode_datetime


def encode_default(o):
    # Use if-elif cascade based on the type of object, prioritizing most-hit types.
    typ = type(o)
    # Avoid isinstance for Base/Market unless absolutely necessary due to high cost and frequency
    # Optimize for Base/Market: shortcut for these classes by type comparison
    # Use a lookup set instead of repeatedly calling isinstance
    # Replace isinstance(o, (Base, Market)) with direct type lookup for performance
    if typ is dt.datetime:
        return encode_datetime(o)
    elif typ is dt.date:
        return encode_date_or_str(o)
    elif typ is dt.time:
        return o.isoformat(timespec="milliseconds")
    elif isinstance(o, Enum):
        return o.value
    # Instead of isinstance(o, (Base, Market)), compare type directly
    elif typ is Base or typ is Market:
        return o.to_dict()
    elif isinstance(o, pd.DataFrame):
        return o.to_json()
    else:
        # fallback for None and unknown types
        return None


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        ret = encode_default(o)
        return super().default(o) if ret is None else ret
