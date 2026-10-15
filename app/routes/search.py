"""Search blueprint: household search and map preview routes."""

from flask import request, jsonify, Blueprint

from households.map_builder import build_blank_map, build_household_map
from households.validation import validate_search_params
from app import state

search_bp = Blueprint('search', __name__)


@search_bp.route("/refresh-map", methods=["POST"])
def refresh_map():
    """Rebuild a blank map preview from the current location and radius."""
    data = request.get_json(silent=True) or request.form
    lat, lon, radius = data.get("lat"), data.get("lon"), data.get("radius")

    params, errors = validate_search_params(lat, lon, radius)
    if errors:
        return jsonify({"errors": errors}), 400

    map_html = build_blank_map(params["lat"], params["lon"], params["radius"])
    return jsonify({"map_html": map_html})


@search_bp.route("/search", methods=["POST"])
def search_households():
    """Query the selected household source, render the map, and store sources."""
    data = request.get_json(silent=True) or request.form
    lat, lon, radius = data.get("lat"), data.get("lon"), data.get("radius")

    params, errors = validate_search_params(lat, lon, radius, data.get("source"))
    if errors:
        return jsonify({"errors": errors}), 400

    map_html, meta, sources = build_household_map(
        params["lat"], params["lon"], params["radius"], source=params["source"]
    )

    if meta.get("error"):
        return jsonify({"errors": {"form": meta["error"]}}), 400

    # Store results for the simulate route
    state.last_sources = sources
    state.last_center = {"lat": params["lat"], "lon": params["lon"]}
    state.last_radius = params["radius"]

    households = [
        {"id": src.id, "lat": src.lat, "lon": src.lon, "address": src.address}
        for src in sources
    ]

    return jsonify({
        "map_html": map_html,
        "params": params,
        "meta": meta,
        "households": households,
    })
