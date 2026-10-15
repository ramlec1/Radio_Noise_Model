"""Choose Overpass or the local snapshot for a household search."""

from __future__ import annotations

from typing import List, Optional, Tuple

from . import config
from .local_store import query_households
from .models import Household
from .overpass import fetch_households


SOURCE_LABELS = {
    "overpass": "Online (Overpass)",
    "local": "Local dataset",
}


def resolve_source(requested: Optional[str] = None) -> str:
    """Resolve ``auto`` to ``local`` when the snapshot exists, otherwise Overpass."""
    if requested is None or str(requested).strip() == "":
        choice = config.configured_source()
    else:
        choice = str(requested).strip().lower()
        if choice not in config.VALID_SOURCES:
            raise ValueError(
                "Source must be auto, overpass, or local."
            )
    if choice == "auto":
        if config.local_database_path().is_file():
            return "local"
        return "overpass"
    return choice


def get_households(
    lat: float,
    lon: float,
    radius: int,
    source: Optional[str] = None,
) -> Tuple[List[Household], str]:
    """Return households and the backend that produced them (``overpass`` or ``local``)."""
    resolved = resolve_source(source)
    if resolved == "local":
        return query_households(lat, lon, radius), resolved
    return fetch_households(lat, lon, radius), resolved
