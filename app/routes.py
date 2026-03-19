from __future__ import annotations

import numpy as np
from typing import Dict, List

from flask import render_template, request, jsonify, Blueprint

from .household_map import (
    build_blank_map,
    build_household_map,
    validate_search_params,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_RADIUS,
)
from simulation.MMN_dataclasses import NoiseSource, Receiver, EnvironmentParameters
from simulation.MMN_model import RadioNoiseModel, NearFieldError
from simulation.propagation import groundwave_propagation, validate_groundwave_params
from simulation.utils import latlon_to_local_meters

main = Blueprint('main', __name__)

# In-memory store for last search; used by /simulate to avoid re-querying Overpass.
_last_sources: List[NoiseSource] = []
_last_center: Dict[str, float] = {"lat": DEFAULT_LAT, "lon": DEFAULT_LON}


@main.route("/")
def home():
    """Render the main page with default form values and a blank map."""
    map_html = build_blank_map(DEFAULT_LAT, DEFAULT_LON)
    return render_template(
        "index.html",
        map_html=map_html,
        lat=DEFAULT_LAT,
        lon=DEFAULT_LON,
        radius=DEFAULT_RADIUS,
        errors={},
    )


@main.route("/search", methods=["POST"])
def search_households():
    """Query Overpass for households, render map, store sources for simulation."""
    global _last_sources, _last_center

    # Get coordinates and radius parameters from request
    data = request.get_json(silent=True) or request.form
    lat, lon, radius = data.get("lat"), data.get("lon"), data.get("radius")

    # Validate parameters to be within legitimate ranges
    params, errors = validate_search_params(lat, lon, radius)
    if errors:
        return jsonify({"errors": errors}), 400

    # Build map, get sources and metadata
    map_html, meta, sources = build_household_map(
        params["lat"], params["lon"], params["radius"]
    )

    if meta.get("error"):
        return jsonify({"errors": {"form": meta["error"]}}), 400

    # Store sources for simulation
    _last_sources = sources
    _last_center = {"lat": params["lat"], "lon": params["lon"]}

    return jsonify({
        "map_html": map_html,
        "params": params,
        "meta": meta,
    })


@main.route("/simulate", methods=["POST"])
def simulate():
    """Run MMN model: households as noise sources, receiver at search center."""
    # Get last search sources from memory if available (see search_households())
    global _last_sources, _last_center
    if not _last_sources:
        return jsonify({
            "errors": {"form": "No household data available. Please run a search first."}
        }), 400

    # Get simulation parameters from request
    data = request.get_json(silent=True) or request.form
    raw = {
        "freq": data.get("freq"),
        "eirp": data.get("eirp"),
        "height": data.get("height"),
        "n_s": data.get("n_s"),
        "epsilon": data.get("epsilon"),
        "sigma": data.get("sigma"),
    }

    # Validate simulation parameters to be within legitimate ranges
    params, errors = validate_groundwave_params(raw)
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        lat0, lon0 = _last_center["lat"], _last_center["lon"]

        # Fill in uninstantiated parts of NoiseSource objects
        for src in _last_sources:
            src.position = latlon_to_local_meters(src.lat, src.lon, lat0, lon0)
            src.EIRP = params["eirp"]
            src.freq = params["freq"]
            src.height = params["height"]

        receiver = Receiver(id=0, position=(0.0, 0.0), height=params["height"])

        # Create environment parameters object
        env = EnvironmentParameters(
            N_s=params["n_s"],
            epsilon=params["epsilon"],
            sigma=params["sigma"],
        )

        # Initialize radio noise model object
        model = RadioNoiseModel(
            noise_sources=_last_sources,
            receivers=[receiver],
            environment_params=env,
            propagation_function=groundwave_propagation,
        )

        # Compute total received power at the receiver. The value is stored in the receiver object.
        model.compute_total_power()
        received_power = receiver.received_power

        # Propagation can return nan or inf; JSON rejects "NaN" or "inf"
        if np.isnan(received_power): 
            return jsonify({
                "errors": {"form": "Simulation produced an invalid result. Check parameters and try again."}
            }), 400
        if np.isinf(received_power):
            return jsonify({
                "errors": {"form": "Simulation produced an infinite result. Check parameters and try again."}
            }), 400

        # Return the received power and the number of sources
        return jsonify({
            "received_power": received_power,
            "source_count": len(_last_sources),
        })

    # Catch near field error (receiver too close to source)
    except NearFieldError as e:
        return jsonify({"errors": {"form": str(e)}}), 400  
    # Catch general exception
    except Exception as e:
        return jsonify({
            "errors": {"form": f"Simulation failed: {str(e)}"}
        }), 500
