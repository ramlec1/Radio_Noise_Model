"""Folium map rendering and NoiseSource construction from Overpass data."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import folium

from simulation.dataclasses import NoiseSource
from .overpass import (
    ExternalServiceError,
    _build_address_from_tags,
    get_households,
)


def build_blank_map(lat: float, lon: float, radius: int) -> str:
    """Build a plain Folium map centred on (lat, lon) with a search radius circle."""
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
    """Build a Folium map showing households within the search radius.

    Fetches household data from Overpass, plots each as a circle marker,
    and returns the map HTML, metadata, and a list of NoiseSource objects.

    Returns:
        (map_html, meta, sources)
        sources: NoiseSource objects with id, lat, lon, address set;
                 position, EIRP, freq, height are filled in at simulation time.
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

        household_id = len(sources)
        tags = el.get("tags") or {}
        fallback = str(el.get("id", ""))
        addr = _build_address_from_tags(tags, fallback)
        src = NoiseSource(id=household_id, lat=pos[0], lon=pos[1], address=addr)
        sources.append(src)

        popup_text = (
            f"<b>ID:</b> {src.id}<br>"
            f"<b>Address:</b> {src.address}<br>"
            f"<b>Coordinates:</b> ({src.lat:.6f}, {src.lon:.6f})"
        )
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
