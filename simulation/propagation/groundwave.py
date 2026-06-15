"""Groundwave propagation model (ITU-R P.368-13).

Implements the groundwave propagation function and its environment parameter
validator. The native library wrapper lives in .models.ITU368_grwave.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np

from simulation.dataclasses import NoiseSource, Receiver, EnvironmentParameters
from simulation.validation import _parse
from .models.ITU368_grwave import ITU368Grwave

logger = logging.getLogger(__name__)


def validate_groundwave_env_params(
    raw: Dict[str, Any],
) -> Tuple[Optional[Dict[str, float]], Optional[Dict[str, str]]]:
    """Validate environment parameters for the ITU-R P.368-13 groundwave model.

    Constraints: N_s 250-400, epsilon >= 1, sigma > 0.
    Frequency range (0.01-30 MHz) is also checked here as a model-specific
    constraint; freq must be passed in raw alongside the env params.
    """
    params: Dict[str, float] = {}
    errors: Dict[str, str] = {}

    _parse(params, errors, raw, "n_s", "Surface refractivity (N_s)", 250.0, 400.0)
    _parse(params, errors, raw, "epsilon", "Relative permittivity", 1.0, None)
    _parse(params, errors, raw, "sigma", "Conductivity (S/m)", 0.0, None, strict_min=True)

    # Model-specific frequency constraint: 0.01–30 MHz
    freq_val = raw.get("freq")
    if freq_val is not None and "freq" not in errors:
        try:
            freq_hz = float(freq_val)
            if freq_hz < 10_000.0 or freq_hz > 30_000_000.0:
                errors["freq"] = "Groundwave model requires frequency 0.01–30 MHz (10 kHz – 30 MHz)."
        except (TypeError, ValueError):
            pass  # already caught by validate_source_params

    if errors:
        return None, errors
    return params, None


def groundwave_propagation(
    source: NoiseSource,
    receiver: Receiver,
    environment_params: EnvironmentParameters,
) -> float:
    """Propagation factor [dB] using the ITU-R P.368-13 groundwave model."""
    r = max(receiver.distance_to(source.position) * 1e-3, 1e-6)  # km
    freq = source.freq * 1e-6  # MHz
    h_tx = source.height
    h_rx = receiver.height
    P_tx = 10 ** (source.EIRP / 10.0)
    N_s = environment_params.N_s
    epsilon = environment_params.epsilon
    sigma = environment_params.sigma
    pol = source.pol

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
    return -prop_factor
