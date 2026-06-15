"""Simulate blueprint: radio noise simulation and propagation model API routes."""

from __future__ import annotations
from typing import Dict

import numpy as np
from flask import request, jsonify, Blueprint

from simulation.dataclasses import Receiver, EnvironmentParameters
from simulation.model import RadioNoiseModel, NearFieldError
from simulation.propagation import PROPAGATION_REGISTRY, get_registry_for_api
from simulation.validation import validate_source_params, validate_receiver_params
from simulation.utils import latlon_to_local_meters
from app import state

simulate_bp = Blueprint('simulate', __name__)


@simulate_bp.route("/api/propagation-models", methods=["GET"])
def api_propagation_models():
    """Return the propagation model registry metadata as JSON.

    The frontend uses this to dynamically build the propagation model
    selection UI and its per-model environment parameter fields.
    """
    return jsonify(get_registry_for_api())


@simulate_bp.route("/simulate", methods=["POST"])
def simulate():
    """Run the MMN model with one or more propagation models."""
    if not state.last_sources:
        return jsonify({
            "errors": {"form": "No household data available. Please run a search first."}
        }), 400

    data = request.get_json(silent=True) or request.form
    all_errors: Dict[str, str] = {}

    # ── Validate source parameters ────────────────────────────────────────────
    source_raw = {
        "freq":          data.get("freq"),
        "eirp":          data.get("eirp"),
        "source_height": data.get("source_height"),
    }
    source_params, src_errors = validate_source_params(source_raw)
    if src_errors:
        all_errors.update(src_errors)

    # ── Validate receiver parameters ──────────────────────────────────────────
    receiver_raw = {"receiver_height": data.get("receiver_height")}
    receiver_params, rx_errors = validate_receiver_params(receiver_raw)
    if rx_errors:
        all_errors.update(rx_errors)

    # ── Validate propagation models ───────────────────────────────────────────
    prop_models_input = data.get("propagation_models") or []
    if not isinstance(prop_models_input, list):
        prop_models_input = []

    if not prop_models_input:
        all_errors["propagation_models"] = "At least one propagation model must be selected."

    validated_models = []  # list of (function, EnvironmentParameters)
    for i, pm in enumerate(prop_models_input):
        model_key = pm.get("model", "")
        if model_key not in PROPAGATION_REGISTRY:
            all_errors[f"pm-{i}-model"] = f"Unknown propagation model: '{model_key}'."
            continue

        registry_entry = PROPAGATION_REGISTRY[model_key]
        env_raw = dict(pm.get("env_params") or {})
        # Pass freq for model-specific frequency range validation (e.g. groundwave)
        if source_raw.get("freq") is not None:
            env_raw.setdefault("freq", source_raw["freq"])

        env_params_dict, env_errors = registry_entry["validate_env"](env_raw)
        if env_errors:
            for field_key, msg in env_errors.items():
                all_errors[f"pm-{i}-{field_key}"] = msg
        else:
            env = EnvironmentParameters(
                N_s=env_params_dict.get("n_s", 0.0),
                epsilon=env_params_dict.get("epsilon", 1.0),
                sigma=env_params_dict.get("sigma", 0.0),
            )
            validated_models.append((registry_entry["function"], env))

    if all_errors:
        return jsonify({"errors": all_errors}), 400

    try:
        lat0, lon0 = state.last_center["lat"], state.last_center["lon"]

        for src in state.last_sources:
            src.position = latlon_to_local_meters(src.lat, src.lon, lat0, lon0)
            src.EIRP = source_params["eirp"]
            src.freq = source_params["freq"]
            src.height = source_params["source_height"]

        receiver = Receiver(
            id=0,
            position=(0.0, 0.0),
            height=receiver_params["receiver_height"],
        )

        model = RadioNoiseModel(
            noise_sources=state.last_sources,
            receivers=[receiver],
            propagation_models=validated_models,
        )

        model.compute_total_power()
        received_power = receiver.received_power

        if np.isnan(received_power):
            return jsonify({
                "errors": {"form": "Simulation produced an invalid result. Check parameters and try again."}
            }), 400
        if np.isinf(received_power):
            return jsonify({
                "errors": {"form": "Simulation produced an infinite result. Check parameters and try again."}
            }), 400

        # ── Build enriched download payload ───────────────────────────────────
        download_data = {
            "search_radius": state.last_radius,
            "receiver": {
                "height": receiver_params["receiver_height"],
                "received_power": received_power,
            },
            "propagation_models": [
                {
                    "model": pm.get("model"),
                    "env_params": pm.get("env_params") or {},
                }
                for pm in prop_models_input
            ],
            "sources": [
                {
                    "id": src.id,
                    "lat": src.lat,
                    "lon": src.lon,
                    "address": src.address,
                    "freq": src.freq,
                    "EIRP": src.EIRP,
                    "height": src.height,
                    "position": list(src.position),
                }
                for src in state.last_sources
            ],
        }

        return jsonify({
            "received_power": received_power,
            "source_count": len(state.last_sources),
            "download_data": download_data,
        })

    except NearFieldError as e:
        return jsonify({"errors": {"form": str(e)}}), 400
    except Exception as e:
        return jsonify({
            "errors": {"form": f"Simulation failed: {str(e)}"}
        }), 500
