"""Shared mutable application state.

Holds the in-memory results of the last household search so that the simulate
route can consume them without re-querying Overpass.

Note: this module-level state is per-process. For multi-worker deployments
it would need to be replaced with a persistent store (e.g. Redis, database).
"""

from typing import Dict, List

from simulation.dataclasses import NoiseSource
from households.overpass import DEFAULT_LAT, DEFAULT_LON, DEFAULT_RADIUS

last_sources: List[NoiseSource] = []
last_center: Dict[str, float] = {"lat": DEFAULT_LAT, "lon": DEFAULT_LON}
last_radius: int = DEFAULT_RADIUS
