"""Propagation models for radio noise simulation.

Each propagation model may define a companion validate_*_params function that
validates input parameters and returns (params_dict, None) if valid, or
(None, errors_dict) if invalid. Validation rules are model-specific.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)

from .MMN_dataclasses import NoiseSource, Receiver, EnvironmentParameters
from .propagation_models.ITU368_grwave import ITU368Grwave


def validate_groundwave_params(raw: Dict[str, Any]) -> Tuple[Dict[str, float] | None, Dict[str, str] | None]:
    """Validate simulation parameters for the ITU-R P.368-13 groundwave model.

    Constraints follow ITU368_grwave: h_tx/h_rx 0-50 m, f 0.01-30 MHz,
    P_tx > 0 W, N_s 250-400, epsilon >= 1, sigma > 0, d_km <= 10000.
    Distance is validated at call time by the model.

    Returns:
        (params, None) if valid; (None, errors) if invalid.
    """
    params: Dict[str, float] = {}
    errors: Dict[str, str] = {}

    def parse(key: str, label: str, min_val: float | None, max_val: float | None, strict_min: bool = False) -> None:
        val = raw.get(key)
        if val is None or (isinstance(val, str) and str(val).strip() == ""):
            errors[key] = f"{label} is required."
            return
        try:
            f = float(val)
        except (TypeError, ValueError):
            errors[key] = f"{label} must be a number."
            return
        if min_val is not None:
            if strict_min and f <= min_val:
                errors[key] = f"{label} must be greater than {min_val}."
                return
            elif not strict_min and f < min_val:
                errors[key] = f"{label} must be >= {min_val}."
                return
        if max_val is not None and f > max_val:
            errors[key] = f"{label} must be <= {max_val}."
            return
        params[key] = f

    # ITU-R P.368-13: f 0.01–30 MHz, h_tx/h_rx 0–50 m, N_s 250–400, epsilon >= 1, sigma > 0
    parse("freq", "Frequency (Hz)", 10_000.0, 30_000_000.0)   # 0.01–30 MHz
    parse("eirp", "EIRP (dBW)", None, None)
    parse("height", "Antenna height (m)", 0.0, 50.0)
    parse("n_s", "Surface refractivity (N_s)", 250.0, 400.0)
    parse("epsilon", "Relative permittivity", 1.0, None)
    parse("sigma", "Conductivity (S/m)", 0.0, None, strict_min=True)

    if errors:
        return None, errors
    return params, None


def example_propagation_model(source: NoiseSource, receiver: Receiver, environment_params: EnvironmentParameters) -> float:
    return 1/receiver.distance_to(source.position)**2  # Placeholder for a simple inverse distance model

def groundwave_propagation(source: NoiseSource, receiver: Receiver, environment_params: EnvironmentParameters) -> float:
    '''
    Calculate the propagation factor as a function of the distance
    and frequency for groundwave propagation using the ITU-R P.368-13 model.

    Parameters:
        source: NoiseSource object, representing the transmitter
        receiver: Receiver object, representing the receiver
        environment_params: EnvironmentParameters object, containing N_s, epsilon, sigma

    Returns:
        propfactor:  [dB] propagation factor
    '''
    # Extract parameters
    r = max(receiver.distance_to(source.position) * 1e-3, 1e-6)  # Distance in km (min 1 mm to avoid singularities)
    freq = source.freq * 1e-6  # Frequency in MHz
    h_tx = source.height  # TX height in meters
    h_rx = receiver.height  # RX height in meters
    P_tx = 10 ** (source.EIRP / 10.0)  # EIRP is dBW; ITU expects watts
    N_s = environment_params.N_s  # Surface refractivity in N-units
    epsilon = environment_params.epsilon  # Relative permittivity of the earth surface
    sigma = environment_params.sigma  # Conductivity of the earth surface in S/m
    pol = source.pol  # Polarization: 0 = horizontal, 1 = vertical

    # Create ITU368Grwave instance and run the propagation model
    grwave = ITU368Grwave()
    try:
        prop_factor = grwave.run(
            h_tx__meter=h_tx,
            h_rx__meter=h_rx,
            f__mhz=freq,
            P_tx__watt=P_tx,
            N_s=N_s,
            d__km=r,
            epsilon=epsilon,
            sigma=sigma,
            pol=pol,
        )[0]  # A_btl__db
    except Exception:
        logger.exception("Error in groundwave propagation calculation")
        return np.nan
    return -prop_factor # ITU368Grwave returns the basic transmission loss in dB, so we need to negate it to get the propagation factor
