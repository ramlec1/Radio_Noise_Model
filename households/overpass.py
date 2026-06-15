"""Overpass API interaction for OSM household extraction."""

from __future__ import annotations
from typing import Any, Dict, List, Optional

import requests


# Defaults (this is the Grolloo measurement location in the ITU-R RNDb)
DEFAULT_LAT = 52.9019
DEFAULT_LON = 6.6533
DEFAULT_RADIUS = 2500  # meters

# Prefer a few different public Overpass endpoints to improve availability
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


class ExternalServiceError(Exception):
    """Raised when an external API (Overpass) fails or times out."""


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
            continue

    raise ExternalServiceError(
        "Unable to query OpenStreetMap (Overpass) right now. "
        "Try a smaller radius or try again later."
        + (f" (Last error: {last_exc})" if last_exc else "")
    )
