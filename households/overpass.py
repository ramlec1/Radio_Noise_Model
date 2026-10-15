"""Overpass API client for household locations."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from .cache import lookup_key, overpass_cache
from .config import USER_AGENT
from .errors import ExternalServiceError
from .models import Household


# Prefer a few different public Overpass endpoints to improve availability.
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

_RETRY_STATUSES = {429, 502, 503, 504}
_MAX_RETRIES = 2
_REQUEST_TIMEOUT_SECONDS = 60
_MAX_BACKOFF_SECONDS = 60
_MIRROR_PAUSE_SECONDS = 1.0


def _pause(seconds: float) -> None:
    """Wait before a retry. Tests replace this so they do not sleep."""
    if seconds > 0:
        time.sleep(seconds)


def _backoff_seconds(attempt: int, response: Optional[requests.Response]) -> float:
    """Honor Retry-After when present, otherwise back off exponentially."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), _MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
    return min(float(2 ** attempt), _MAX_BACKOFF_SECONDS)


def _build_query(lat: float, lon: float, radius: int) -> str:
    return f"""
    [out:json][timeout:60];
    (
      node["addr:housenumber"](around:{radius},{lat},{lon});
      way["addr:housenumber"](around:{radius},{lat},{lon});
      relation["addr:housenumber"](around:{radius},{lat},{lon});
    );
    out center;
    """


def _tags_from_element(element: Dict[str, Any]) -> Dict[str, str]:
    raw = element.get("tags") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _position(element: Dict[str, Any]) -> Optional[tuple]:
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def elements_to_households(elements: List[Dict[str, Any]]) -> List[Household]:
    """Convert an Overpass ``elements`` array into household points."""
    households: List[Household] = []
    for element in elements:
        position = _position(element)
        if position is None:
            continue
        lat, lon = position
        element_type = str(element.get("type") or "node")
        osm_id = f"{element_type}/{element.get('id', '')}"
        households.append(
            Household(
                lat=lat,
                lon=lon,
                tags=_tags_from_element(element),
                osm_id=osm_id,
            )
        )
    return households


def _query_mirror(url: str, query: str) -> tuple[Optional[List[Household]], Optional[Exception]]:
    """POST one mirror, retrying rate limits, gateway errors, and timeouts."""
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.Timeout as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                _pause(_backoff_seconds(attempt, None))
                continue
            return None, exc
        except requests.RequestException as exc:
            return None, exc

        if response.status_code in _RETRY_STATUSES:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_exc = exc
            if attempt < _MAX_RETRIES:
                _pause(_backoff_seconds(attempt, response))
                continue
            return None, last_exc

        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            return None, exc

        elements = payload.get("elements", []) if isinstance(payload, dict) else []
        return elements_to_households(elements), None

    return None, last_exc


def fetch_households(lat: float, lon: float, radius: int) -> List[Household]:
    """Query Overpass and return households with a house number.

    Successful results are cached for about one hour. Failures are not cached.
    Each mirror is retried on 429, 502, 503, 504, and timeouts before the next
    mirror is tried.
    """
    key = lookup_key(lat, lon, radius)
    cached = overpass_cache.get(key)
    if cached is not None:
        return list(cached)

    query = _build_query(lat, lon, radius)
    last_exc: Optional[Exception] = None
    for index, overpass_url in enumerate(_OVERPASS_ENDPOINTS):
        if index:
            _pause(_MIRROR_PAUSE_SECONDS)
        households, exc = _query_mirror(overpass_url, query)
        if households is not None:
            overpass_cache.put(key, households)
            return list(households)
        last_exc = exc

    raise ExternalServiceError(
        "Unable to query OpenStreetMap (Overpass) right now. "
        "Try a smaller radius or try again later."
        + (f" (Last error: {last_exc})" if last_exc else "")
    )
