"""OSM household extraction and map generation helpers."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Union

import folium
import requests

from simulation.MMN_dataclasses import NoiseSource


# Defaults (this is the grolloo measurement location in the ITU-R RNDb)
DEFAULT_LAT = 52.9019
DEFAULT_LON = 6.6533
DEFAULT_RADIUS = 2500  # meters

# Prefer a few different public Overpass endpoints to improve availability
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Overpass requires a descriptive User-Agent identifying the application
_OVERPASS_HEADERS = {
    "User-Agent": "Radio_Noise_Model/1.0 (Man-made radio noise model; household map)",
}


def _build_address_from_tags(tags: Dict[str, Any], fallback: str) -> str:
    """Build full address from OSM addr:* tags. Handles varying OSM tagging conventions."""
    if not tags:
        return fallback

    full = tags.get("addr:full")
    if full and str(full).strip():
        return str(full).strip()

    parts: List[str] = []

    # House number (optionally with unit/flat)
    hn = tags.get("addr:housenumber")
    unit = tags.get("addr:unit") or tags.get("addr:flats")
    if hn:
        hn_str = str(hn).strip()
        if unit:
            hn_str = f"{hn_str} {str(unit).strip()}"
        parts.append(hn_str)

    # Street (or road)
    street = tags.get("addr:street") or tags.get("addr:road") or tags.get("addr:place_name")
    if street:
        parts.append(str(street).strip())

    # Locality: prefer city, then town, village, hamlet, suburb, quarter, place
    locality = (
        tags.get("addr:city")
        or tags.get("addr:town")
        or tags.get("addr:village")
        or tags.get("addr:hamlet")
        or tags.get("addr:suburb")
        or tags.get("addr:quarter")
        or tags.get("addr:place")
    )
    if locality:
        parts.append(str(locality).strip())

    # Postcode
    postcode = tags.get("addr:postcode")
    if postcode:
        parts.append(str(postcode).strip())

    # Country
    country = tags.get("addr:country")
    if country:
        parts.append(str(country).strip())

    if parts:
        return ", ".join(parts)
    return fallback


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
            response = requests.get(
                overpass_url,
                params={"data": query},
                headers=_OVERPASS_HEADERS,
                timeout=60,
            )
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


def build_blank_map(lat: float, lon: float, radius: int) -> str:
    """Build a plain Folium map centred on (lat, lon) with no overlays."""
    m = folium.Map(location=[lat, lon], zoom_start=14)
    folium.Circle(
        radius=radius,
        location=[lat, lon],
        color="crimson",
        fill=True,
        fill_opacity=0.2,
    ).add_to(m)
    
    folium.Marker(
        [lat, lon],
        popup="Receiver",
        icon=folium.Icon(color="red", icon="tower-broadcast", prefix="fa"),
    ).add_to(m)
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

    m = folium.Map(location=[lat, lon], zoom_start=14)

    folium.Circle(
        radius=radius,
        location=[lat, lon],
        color="crimson",
        fill=True,
        fill_opacity=0.2,
    ).add_to(m)

    folium.Marker(
        [lat, lon],
        popup="Receiver",
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
        
        # construct the household object with the id, lat, lon and address
        household_id = len(sources)
        tags = el.get("tags") or {}
        fallback = str(el.get("id", ""))
        addr = _build_address_from_tags(tags, fallback)
        src = NoiseSource(id=household_id, lat=pos[0], lon=pos[1], address=addr)
        sources.append(src)

        # Create a popup with the household information and a fixed width
        popup_text = f"<b>ID:</b> {src.id}<br><b>Address:</b> {src.address}<br><b>Coordinates:</b> ({src.lat:.6f}, {src.lon:.6f})"
        popup_iframe = folium.IFrame(popup_text)
        popup = folium.Popup(popup_iframe, min_width=250, max_width=250)

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
