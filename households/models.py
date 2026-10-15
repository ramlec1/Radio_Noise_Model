"""Household records and default search location."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# Grolloo measurement location in the ITU-R RNDb.
DEFAULT_LAT = 52.9019
DEFAULT_LON = 6.6533
DEFAULT_RADIUS = 2500  # meters


@dataclass(frozen=True)
class Household:
    """One address point returned by Overpass or the local snapshot."""

    lat: float
    lon: float
    tags: Dict[str, str]
    osm_id: str
