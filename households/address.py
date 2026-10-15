"""Format an address string from OSM addr:* tags."""

from __future__ import annotations

from typing import Any, Dict, List


def build_address_from_tags(tags: Dict[str, Any], fallback: str) -> str:
    """Build a full address from OSM addr:* tags.

    Handles the tagging conventions used on nodes, ways, and relations.
    ``fallback`` is used when the tags do not contain an address.
    """
    if not tags:
        return fallback

    full = tags.get("addr:full")
    if full and str(full).strip():
        return str(full).strip()

    parts: List[str] = []

    housenumber = tags.get("addr:housenumber")
    unit = tags.get("addr:unit") or tags.get("addr:flats")
    if housenumber:
        housenumber_text = str(housenumber).strip()
        if unit:
            housenumber_text = f"{housenumber_text} {str(unit).strip()}"
        parts.append(housenumber_text)

    street = tags.get("addr:street") or tags.get("addr:road") or tags.get("addr:place_name")
    if street:
        parts.append(str(street).strip())

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

    postcode = tags.get("addr:postcode")
    if postcode:
        parts.append(str(postcode).strip())

    country = tags.get("addr:country")
    if country:
        parts.append(str(country).strip())

    if parts:
        return ", ".join(parts)
    return fallback
