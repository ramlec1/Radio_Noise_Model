"""In-memory cache of successful household lookups."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Dict, Generic, Hashable, Optional, Tuple, TypeVar


CACHE_TTL_SECONDS = 3600
_COORDINATE_DECIMALS = 5

T = TypeVar("T")


class ResultCache(Generic[T]):
    """Thread-safe cache that keeps successful values for a fixed time."""

    def __init__(
        self,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: Dict[Hashable, Tuple[float, T]] = {}

    def get(self, key: Hashable) -> Optional[T]:
        """Return a cached value, or None when missing or expired."""
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if now - stored_at >= self.ttl_seconds:
                del self._entries[key]
                return None
            return value

    def put(self, key: Hashable, value: T) -> None:
        """Store a successful result."""
        stored_at = self._clock()
        with self._lock:
            self._entries[key] = (stored_at, value)

    def clear(self) -> None:
        """Drop every cached result."""
        with self._lock:
            self._entries.clear()


def lookup_key(lat: float, lon: float, radius: int) -> Tuple[float, float, int]:
    """Key a search so nearby coordinates share one cached result."""
    return (round(float(lat), _COORDINATE_DECIMALS), round(float(lon), _COORDINATE_DECIMALS), int(radius))


def local_lookup_key(path: Path, lat: float, lon: float, radius: int) -> Tuple[str, int, float, float, int]:
    """Key a local search by the snapshot file and the rounded search."""
    database = Path(path)
    rounded_lat, rounded_lon, rounded_radius = lookup_key(lat, lon, radius)
    return (
        str(database.resolve()),
        database.stat().st_mtime_ns,
        rounded_lat,
        rounded_lon,
        rounded_radius,
    )


overpass_cache: ResultCache[list] = ResultCache()
local_cache: ResultCache[list] = ResultCache()
