"""Propagation package: model registry and API helper.

Each propagation model is defined in its own module under this package.
Add a new model by:
  1. Creating a new module (e.g. simulation/propagation/skywave.py) with
     a propagation function and a validate_env_params function.
  2. Adding an entry to PROPAGATION_REGISTRY below.
"""

from __future__ import annotations
from typing import Any, Dict, List

from .groundwave import groundwave_propagation, validate_groundwave_env_params
from .line_of_sight import line_of_sight_propagation, validate_los_env_params


PROPAGATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "groundwave": {
        "label": "Groundwave (ITU-R P.368)",
        "function": groundwave_propagation,
        "validate_env": validate_groundwave_env_params,
        "env_fields": {
            "n_s": {
                "label": "Surface Refractivity N\u209b (N-units)",
                "type": "number",
                "min": 250,
                "max": 400,
                "default": 250,
                "step": "any",
            },
            "epsilon": {
                "label": "Relative Permittivity \u03b5",
                "type": "number",
                "min": 1,
                "max": None,
                "default": 20,
                "step": "any",
            },
            "sigma": {
                "label": "Conductivity \u03c3 (S/m)",
                "type": "number",
                "min": 0.000001,
                "max": None,
                "default": 0.03,
                "step": "any",
            },
        },
    },
    "line_of_sight": {
        "label": "Line of Sight (Free Space)",
        "function": line_of_sight_propagation,
        "validate_env": validate_los_env_params,
        "env_fields": {},
    },
}


def get_registry_for_api() -> List[Dict[str, Any]]:
    """Return registry metadata safe for JSON serialisation (no function refs)."""
    return [
        {
            "key": key,
            "label": meta["label"],
            "env_fields": meta["env_fields"],
        }
        for key, meta in PROPAGATION_REGISTRY.items()
    ]
