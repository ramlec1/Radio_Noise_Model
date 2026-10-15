"""Read household points from the local SQLite snapshot."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import config
from .cache import local_cache, local_lookup_key
from .errors import LocalDataError
from .models import Household


_METERS_PER_DEGREE_LAT = 111_320.0
_BOUNDS_MARGIN = 1.02
_READER_MMAP_BYTES = 256 * 1024 * 1024
_READER_CACHE_KIB = -65_536

_CREATE_TABLE = """
CREATE TABLE households (
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    osm_id TEXT NOT NULL,
    tags_json TEXT NOT NULL
)
"""

_CREATE_RTREE = """
CREATE VIRTUAL TABLE households_rtree USING rtree(
    id,
    min_lat, max_lat,
    min_lon, max_lon
)
"""

_BOX_QUERY = """
SELECT h.lat, h.lon, h.osm_id, h.tags_json
FROM households_rtree AS r
JOIN households AS h ON h.rowid = r.id
WHERE r.min_lat >= ? AND r.max_lat <= ?
  AND r.min_lon >= ? AND r.max_lon <= ?
"""

Box = Tuple[float, float, float, float]


def open_writer(path: Path) -> sqlite3.Connection:
    """Create an empty household database, replacing any file already there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute(_CREATE_TABLE)
    try:
        connection.execute(_CREATE_RTREE)
    except sqlite3.OperationalError as exc:
        connection.close()
        path.unlink(missing_ok=True)
        raise LocalDataError(
            "This SQLite build has no R-tree module, which the household snapshot needs. "
            f"{exc}"
        ) from exc
    return connection


def add_households(
    connection: sqlite3.Connection,
    rows: Sequence[Tuple[float, float, str, str]],
) -> None:
    """Insert ``(lat, lon, osm_id, tags_json)`` rows."""
    connection.executemany(
        "INSERT INTO households (lat, lon, osm_id, tags_json) VALUES (?, ?, ?, ?)",
        rows,
    )


def finish_writer(connection: sqlite3.Connection) -> None:
    """Fill the spatial index and close the database."""
    connection.execute(
        """
        INSERT INTO households_rtree (id, min_lat, max_lat, min_lon, max_lon)
        SELECT rowid, lat, lat, lon, lon FROM households
        """
    )
    connection.commit()
    connection.close()


def _bounding_box(lat: float, lon: float, radius_m: int) -> Box:
    """Latitude/longitude box that contains the search circle, with a small margin."""
    padded = radius_m * _BOUNDS_MARGIN
    delta_lat = padded / _METERS_PER_DEGREE_LAT
    cosine = math.cos(math.radians(lat))
    meters_per_degree_lon = _METERS_PER_DEGREE_LAT * max(abs(cosine), 0.01)
    delta_lon = padded / meters_per_degree_lon
    return lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon


def _search_boxes(lat: float, lon: float, radius_m: int) -> List[Box]:
    """Boxes passed to the R-tree. A search across ±180° becomes two boxes."""
    lat_min, lat_max, lon_min, lon_max = _bounding_box(lat, lon, radius_m)
    if lon_min >= -180.0 and lon_max <= 180.0:
        return [(lat_min, lat_max, lon_min, lon_max)]
    wrapped_min = lon_min + 360.0 if lon_min < -180.0 else lon_min
    wrapped_max = lon_max - 360.0 if lon_max > 180.0 else lon_max
    return [
        (lat_min, lat_max, wrapped_min, 180.0),
        (lat_min, lat_max, -180.0, wrapped_max),
    ]


def _within_radius(lat: float, lon: float, other_lat: float, other_lon: float, radius_m: int) -> bool:
    """Return whether ``other`` lies within ``radius_m`` on a local metre grid."""
    delta_lat_m = (other_lat - lat) * _METERS_PER_DEGREE_LAT
    delta_lon = other_lon - lon
    if delta_lon > 180.0:
        delta_lon -= 360.0
    elif delta_lon < -180.0:
        delta_lon += 360.0
    cosine = math.cos(math.radians(lat))
    meters_per_degree_lon = _METERS_PER_DEGREE_LAT * max(abs(cosine), 0.01)
    delta_lon_m = delta_lon * meters_per_degree_lon
    limit = float(radius_m)
    return delta_lat_m * delta_lat_m + delta_lon_m * delta_lon_m <= limit * limit


def _row_to_household(lat: float, lon: float, osm_id: str, tags_json: str) -> Optional[Household]:
    try:
        raw_tags = json.loads(tags_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_tags, dict):
        return None
    tags = {str(key): str(value) for key, value in raw_tags.items()}
    return Household(lat=float(lat), lon=float(lon), tags=tags, osm_id=str(osm_id))


def _missing_file_error(database: Path) -> LocalDataError:
    return LocalDataError(
        "Local household dataset was not found at "
        f"{database}. Build it with: {config.BUILD_COMMAND}"
    )


def _missing_index_error(database: Path) -> LocalDataError:
    return LocalDataError(
        "Local household dataset has no spatial index at "
        f"{database}. Rebuild it with: {config.BUILD_COMMAND}"
    )


def _connect_reader(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.execute(f"PRAGMA mmap_size={_READER_MMAP_BYTES}")
    connection.execute(f"PRAGMA cache_size={_READER_CACHE_KIB}")
    return connection


def _has_spatial_index(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'households_rtree'
        """
    ).fetchone()
    return row is not None


def _load_households(database: Path, lat: float, lon: float, radius: int) -> List[Household]:
    connection = _connect_reader(database)
    try:
        if not _has_spatial_index(connection):
            raise _missing_index_error(database)
        rows = []
        for box in _search_boxes(lat, lon, radius):
            rows.extend(connection.execute(_BOX_QUERY, box).fetchall())
    finally:
        connection.close()

    households: List[Household] = []
    for row_lat, row_lon, osm_id, tags_json in rows:
        if not _within_radius(lat, lon, row_lat, row_lon, radius):
            continue
        household = _row_to_household(row_lat, row_lon, osm_id, tags_json)
        if household is not None:
            households.append(household)
    return households


def query_households(
    lat: float,
    lon: float,
    radius: int,
    path: Optional[Path] = None,
) -> List[Household]:
    """Return households from the local snapshot inside ``radius`` metres."""
    database = path if path is not None else config.local_database_path()
    if not database.is_file():
        raise _missing_file_error(database)

    key = local_lookup_key(database, lat, lon, radius)
    cached = local_cache.get(key)
    if cached is not None:
        return list(cached)

    households = _load_households(database, lat, lon, radius)
    local_cache.put(key, households)
    return list(households)
