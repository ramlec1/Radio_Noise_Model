"""Validation helpers for simulation input parameters (source and receiver).

These are model-independent checks. Each propagation model has its own
validate_env_params function in its respective module under simulation/propagation/.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple


def _parse(
    params: Dict[str, float],
    errors: Dict[str, str],
    raw: Dict[str, Any],
    key: str,
    label: str,
    min_val: Optional[float],
    max_val: Optional[float],
    strict_min: bool = False,
) -> None:
    """Parse one field from raw into params, recording any error in errors."""
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


def validate_source_params(raw: Dict[str, Any]) -> Tuple[Optional[Dict[str, float]], Optional[Dict[str, str]]]:
    """Validate source (transmitter) parameters.

    Keys expected: freq (Hz), eirp (dBW), source_height (m).
    Frequency range is intentionally broad here; model-specific freq constraints
    are checked by each model's validate_env function.
    """
    params: Dict[str, float] = {}
    errors: Dict[str, str] = {}

    _parse(params, errors, raw, "freq", "Frequency (Hz)", 0.0, None, strict_min=True)
    _parse(params, errors, raw, "eirp", "EIRP (dBW)", None, None)
    _parse(params, errors, raw, "source_height", "Source antenna height (m)", 0.0, 50.0)

    if errors:
        return None, errors
    return params, None


def validate_receiver_params(raw: Dict[str, Any]) -> Tuple[Optional[Dict[str, float]], Optional[Dict[str, str]]]:
    """Validate receiver parameters.

    Keys expected: receiver_height (m).
    """
    params: Dict[str, float] = {}
    errors: Dict[str, str] = {}

    _parse(params, errors, raw, "receiver_height", "Receiver antenna height (m)", 0.0, 50.0)

    if errors:
        return None, errors
    return params, None
