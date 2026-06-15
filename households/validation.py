"""Input validation for household search parameters."""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, Union


def _parse_float(
    value: Any,
    name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Tuple[Optional[float], Optional[str]]:
    """Parse a float value with optional range validation."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, f"{name} is required."

    try:
        f = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."

    if min_value is not None and f < min_value:
        return None, f"{name} must be >= {min_value}."
    if max_value is not None and f > max_value:
        return None, f"{name} must be <= {max_value}."

    return f, None


def _parse_int(
    value: Any,
    name: str,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Parse an int value with optional range validation."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None, f"{name} is required."

    try:
        i = int(float(value))
    except (TypeError, ValueError):
        return None, f"{name} must be an integer."

    if min_value is not None and i < min_value:
        return None, f"{name} must be >= {min_value}."
    if max_value is not None and i > max_value:
        return None, f"{name} must be <= {max_value}."

    return i, None


def validate_search_params(
    lat: Any, lon: Any, radius: Any
) -> Tuple[Dict[str, Union[float, int]], Dict[str, str]]:
    """Validate and convert location search parameters.

    Returns:
        (params, errors)
        params contains keys: lat, lon, radius (typed values) if valid.
        errors contains any validation messages keyed by field name.
    """
    errors: Dict[str, str] = {}
    params: Dict[str, Union[float, int]] = {}

    lat_val, lat_err = _parse_float(lat, "Latitude", -90.0, 90.0)
    if lat_err:
        errors["lat"] = lat_err
    else:
        params["lat"] = lat_val  # type: ignore[assignment]

    lon_val, lon_err = _parse_float(lon, "Longitude", -180.0, 180.0)
    if lon_err:
        errors["lon"] = lon_err
    else:
        params["lon"] = lon_val  # type: ignore[assignment]

    radius_val, radius_err = _parse_int(radius, "Radius (m)", 1, 100000)
    if radius_err:
        errors["radius"] = radius_err
    else:
        params["radius"] = radius_val  # type: ignore[assignment]

    return params, errors
