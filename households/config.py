"""Runtime settings for choosing and locating household data."""

from __future__ import annotations

import os
from pathlib import Path


VALID_SOURCES = ("auto", "overpass", "local")
DEFAULT_SOURCE = "auto"
DEFAULT_LOCAL_PATH = Path("data") / "households.sqlite"
USER_AGENT = "RadioNoiseModel/1.0 (household search)"
BUILD_COMMAND = "uv run build_households.py --region europe/netherlands"


def configured_source() -> str:
    """Return HOUSEHOLD_SOURCE, or ``auto`` when unset or unrecognised."""
    raw = os.environ.get("HOUSEHOLD_SOURCE", DEFAULT_SOURCE).strip().lower()
    if raw not in VALID_SOURCES:
        return DEFAULT_SOURCE
    return raw


def local_database_path() -> Path:
    """Return HOUSEHOLD_LOCAL_PATH, or the default SQLite snapshot path."""
    raw = os.environ.get("HOUSEHOLD_LOCAL_PATH")
    if raw is None or raw.strip() == "":
        return DEFAULT_LOCAL_PATH
    return Path(raw)
