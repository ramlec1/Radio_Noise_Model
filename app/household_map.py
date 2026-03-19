"""OSM household extraction and map generation helpers."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Union

import folium
import requests

from simulation.MMN_dataclasses import NoiseSource


# Defaults (this is the grolloo measurement location in the ITU-R RNDb)
DEFAULT_LAT = 52.9019
DEFAULT_LON = 6.6533
DEFAULT_RADIUS = 1000  # meters

# Prefer a few different public Overpass endpoints to improve availability
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


# Helper functions to parse the input parameters for validation
def _parse_float(value: Any, name: str, min_value: Optional[float] = None, max_value: Optional[float] = None) -> Tuple[Optional[float], Optional[str]]:
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


def _parse_int(value: Any, name: str, min_value: Optional[int] = None, max_value: Optional[int] = None) -> Tuple[Optional[int], Optional[str]]:
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


def validate_search_params(lat: Any, lon: Any, radius: Any) -> Tuple[Dict[str, Union[float, int]], Dict[str, str]]:
    """Validate and convert input parameters.

    Returns:
        (params, errors)

    `params` will contain keys: lat, lon, radius (typed values) if valid.
    `errors` will contain any validation messages by field name.
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


class ExternalServiceError(Exception):
    """Raised when an external API (Overpass) fails or times out."""


def get_households(lat: float, lon: float, radius: int) -> List[Dict[str, Any]]:
    """Query Overpass and return OSM elements with house numbers.

    Overpass can time out on larger radius queries; this function will try a few
    endpoints and raise a clear exception if all attempts fail.
    """

    query = f"""
    [out:json][timeout:60];
    (
      node[\"addr:housenumber\"](around:{radius},{lat},{lon});
      way[\"addr:housenumber\"](around:{radius},{lat},{lon});
      relation[\"addr:housenumber\"](around:{radius},{lat},{lon});
    );
    out center;
    """

    last_exc: Optional[Exception] = None
    for overpass_url in _OVERPASS_ENDPOINTS:
        try:
            response = requests.get(overpass_url, params={"data": query}, timeout=60)
            response.raise_for_status()
            return response.json().get("elements", [])
        except requests.RequestException as ex:
            last_exc = ex
            # Try the next endpoint if available.
            continue

    raise ExternalServiceError(
        "Unable to query OpenStreetMap (Overpass) right now. "
        "Try a smaller radius or try again later."
        + (f" (Last error: {last_exc})" if last_exc else "")
    )


def build_blank_map(lat: float, lon: float) -> str:
    """Build a plain Folium map centred on (lat, lon) with no overlays."""
    m = folium.Map(location=[lat, lon], zoom_start=16)
    return m._repr_html_()


def build_household_map(
    lat: float, lon: float, radius: int
) -> Tuple[str, Dict[str, Any], List[NoiseSource]]:
    """Build a Folium map showing households and a search radius.

    Returns:
        (map_html, meta, sources)
        sources is a list of NoiseSource objects (id, lat, lon, address set;
        position, EIRP, freq, height filled in at simulate).
    """

    error_msg: Optional[str] = None
    try:
        elements = get_households(lat, lon, radius)
    except ExternalServiceError as exc:
        elements = []
        error_msg = str(exc)

    m = folium.Map(location=[lat, lon], zoom_start=16)

    folium.Circle(
        radius=radius,
        location=[lat, lon],
        color="crimson",
        fill=True,
        fill_opacity=0.2,
    ).add_to(m)

    folium.Marker(
        [lat, lon],
        popup="Center Point",
        icon=folium.Icon(color="red", icon="tower-broadcast", prefix="fa"),
    ).add_to(m)

    sources: List[NoiseSource] = []
    for el in elements:
        if el.get("type") == "node":
            pos = [el.get("lat"), el.get("lon")]
        else:
            center = el.get("center") or {}
            pos = [center.get("lat"), center.get("lon")]

        if not pos or None in pos:
            continue

        source_id = len(sources)
        addr = el.get("tags", {}).get("addr:housenumber") or str(el.get("id", ""))
        src = NoiseSource(id=source_id, lat=pos[0], lon=pos[1], address=addr)
        sources.append(src)

        popup = f"ID: {src.id}\n({src.lat:.6f}, {src.lon:.6f})"

        folium.CircleMarker(
            location=pos,
            radius=4,
            popup=popup,
            color="blue",
            fill=True,
            fill_opacity=0.8,
        ).add_to(m)

    meta: Dict[str, Any] = {"household_count": len(sources)}
    if error_msg:
        meta["error"] = error_msg
    return m._repr_html_(), meta, sources
