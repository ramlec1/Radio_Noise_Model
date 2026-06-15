"""Line-of-sight (free space) propagation model."""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

import numpy as np

from simulation.dataclasses import NoiseSource, Receiver, EnvironmentParameters


def validate_los_env_params(
    raw: Dict[str, Any],
) -> Tuple[Optional[Dict[str, float]], Optional[Dict[str, str]]]:
    """Line-of-sight model has no environment parameters; always succeeds."""
    return {}, None


def line_of_sight_propagation(
    source: NoiseSource,
    receiver: Receiver,
    environment_params: EnvironmentParameters,
) -> float:
    """Propagation factor [dB] using free-space line-of-sight (inverse square law)."""
    r = max(receiver.distance_to(source.position), 1e-6)  # m
    prop_factor = 1 / (4 * np.pi * r ** 2)
    return 10 * np.log10(prop_factor)
