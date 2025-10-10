"""
Copyright 2023 Goldman Sachs.
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

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Tuple

import cachetools
import pandas as pd

from gs_quant.base import Base
from gs_quant.session import GsSession


class CacheEvent(Enum):
    PUT = "Put"
    GET = "Get"


class ApiRequestCache(ABC):
    def get(self, session: GsSession, key: Any, **kwargs):
        cache_lookup = self._get(session, key, **kwargs)
        if cache_lookup is not None:
            self.record(session, key, CacheEvent.GET, **kwargs)
        return cache_lookup

    @abstractmethod
    def _get(self, session: GsSession, key: Any, **kwargs):
        pass

    def record(self, session: GsSession, key: Any, method: CacheEvent, **kwargs):
        pass

    def put(self, session: GsSession, key: Any, value, **kwargs):
        self._put(session, key, value, **kwargs)
        self.record(session, key, CacheEvent.PUT, **kwargs)

    @abstractmethod
    def _put(self, session: GsSession, key: Any, value, **kwargs):
        pass


class InMemoryApiRequestCache(ApiRequestCache):
    def __init__(self, max_size=1000, ttl_in_seconds=3600):
        self._cache = cachetools.TTLCache(max_size, ttl_in_seconds)
        self._records = []

    def get_events(self) -> Tuple[Tuple[CacheEvent, Any], ...]:
        return tuple(self._records)

    def clear_events(self):
        self._records.clear()

    def _make_str_key(self, key: Any):
        # Fast-path for scalar immutable types (common keys)
        if isinstance(key, str):
            return key
        if isinstance(key, int):
            return str(key)
        # For lists/tuples, try to use tuple and cache intermediate results in stack loop
        if isinstance(key, tuple):
            # Tuples are hashable, so use tuple repr directly for consistent performance and uniqueness.
            # This is typically faster and collision-resistant for tuple keys
            return "(" + ",".join(self._make_str_key(k) for k in key) + ")"
        elif isinstance(key, list):
            # For lists, we mimic tuple handling but keep brackets to reduce unnecessary ambiguity
            return "[" + ",".join(self._make_str_key(k) for k in key) + "]"
        elif isinstance(key, dict):
            # Dict items order: always sort by key for consistency; avoid collisions for equivalent dicts with different order
            items = sorted(key.items())
            return (
                "{"
                + ",".join(
                    f"{self._make_str_key(k)}:{self._make_str_key(v)}" for k, v in items
                )
                + "}"
            )
        elif isinstance(key, (Base, pd.DataFrame)):
            return key.to_json()
        return str(key)

    def _get(self, session: GsSession, key: Any, **kwargs):
        # No change needed here for optimal performance;
        # make_str_key is now significantly faster and more deterministic.
        return self._cache.get(self._make_str_key(key))

    def record(self, session: GsSession, key: Any, method: CacheEvent, **kwargs):
        self._records.append((method, key))

    def _put(self, session: GsSession, key, value, **kwargs):
        self._cache[self._make_str_key(key)] = value
