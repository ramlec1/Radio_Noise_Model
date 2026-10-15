"""Folium map rendering and NoiseSource construction from household points."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import folium
from folium.plugins import FastMarkerCluster

from simulation.dataclasses import NoiseSource

from .address import build_address_from_tags
from .errors import ExternalServiceError, LocalDataError
from .source import SOURCE_LABELS, get_households


_HOUSEHOLD_MARKER_CALLBACK = """
function (row) {
    var marker = L.circleMarker(new L.LatLng(row[0], row[1]), {
        radius: 4,
        color: "blue",
        fill: true,
        fillOpacity: 0.8
    });
    marker.bindPopup(row[2], {minWidth: 250, maxWidth: 250});
    return marker;
}
"""


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
    lat: float,
    lon: float,
    radius: int,
    source: Optional[str] = None,
) -> Tuple[str, Dict[str, Any], List[NoiseSource]]:
    """Build a Folium map showing households within the search radius.

    Loads household points from the selected source, plots them as a marker
    cluster, and returns the map HTML, metadata, and NoiseSource objects.

    Returns:
        (map_html, meta, sources)
        sources: NoiseSource objects with id, lat, lon, address set;
                 position, EIRP, freq, height are filled in at simulation time.
        meta includes household_count and, on success, source and source_label.
    """
    error_msg: Optional[str] = None
    resolved_source: Optional[str] = None
    try:
        households, resolved_source = get_households(lat, lon, radius, source=source)
    except (ExternalServiceError, LocalDataError) as exc:
        households = []
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
    cluster_rows: List[List[object]] = []
    for household in households:
        household_id = len(sources)
        address = build_address_from_tags(household.tags, household.osm_id)
        src = NoiseSource(
            id=household_id,
            lat=household.lat,
            lon=household.lon,
            address=address,
        )
        sources.append(src)
        popup_text = (
            f"<b>ID:</b> {src.id}<br>"
            f"<b>Address:</b> {src.address}<br>"
            f"<b>Coordinates:</b> ({src.lat:.6f}, {src.lon:.6f})"
        )
        cluster_rows.append([household.lat, household.lon, popup_text])

    if cluster_rows:
        FastMarkerCluster(
            cluster_rows,
            callback=_HOUSEHOLD_MARKER_CALLBACK,
            control=False,
        ).add_to(m)

    meta: Dict[str, Any] = {"household_count": len(sources)}
    if resolved_source:
        meta["source"] = resolved_source
        meta["source_label"] = SOURCE_LABELS.get(resolved_source, resolved_source)
    if error_msg:
        meta["error"] = error_msg
    return m._repr_html_(), meta, sources
