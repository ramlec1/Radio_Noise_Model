from typing import Callable, List, Tuple
import numpy as np

from .utils import db_to_rat, rat_to_db
from .dataclasses import NoiseSource, Receiver, EnvironmentParameters


class NearFieldError(Exception):
    """Raised when the receiver is in the near-field of a noise source.

    The far-field condition requires r > c₀/(2f). For lower frequencies or
    shorter distances, the propagation model is not valid.
    """
    def __init__(self, distance_m: float, freq_hz: float, source_id: int = 0, message: str | None = None):
        self.distance_m = distance_m
        self.freq_hz = freq_hz
        self.source_id = source_id
        c0 = 3e8
        min_dist = c0 / (2 * freq_hz)
        default_msg = (
            f"Receiver is too close to noise source (distance {distance_m:.1f} m; "
            f"at {freq_hz/1e6:.2f} MHz a minimum of {min_dist:.0f} m is required). "
            f"Try a larger search radius or a different receiver position."
        )
        super().__init__(message or default_msg)


class RadioNoiseModel:
    """Core simulation model for radio noise power.

    Parameters
    ----------
    noise_sources:
        List of NoiseSource objects representing transmitters.
    receivers:
        List of Receiver objects.
    propagation_models:
        List of (propagation_function, EnvironmentParameters) tuples.
        Each propagation model contributes independently to the total
        received power (incoherent summation).
    """
    def __init__(
        self,
        noise_sources: List[NoiseSource],
        receivers: List[Receiver],
        propagation_models: List[Tuple[Callable[[NoiseSource, Receiver, EnvironmentParameters], float], EnvironmentParameters]],
    ):
        self.noise_sources = noise_sources
        self.receivers = receivers
        self.propagation_models = propagation_models

    def compute_total_power(self) -> bool:
        """Compute total received power S at each receiver.

        For each receiver, sums contributions from all sources and all propagation
        models incoherently (power addition in linear scale).
        """
        for receiver in self.receivers:
            total_power = 0.0
            for source in self.noise_sources:
                r = receiver.distance_to(source.position)
                receiver.far_field = receiver.far_field_condition(source)
                if not receiver.far_field:
                    raise NearFieldError(distance_m=r, freq_hz=source.freq, source_id=source.id)
                for prop_func, env_params in self.propagation_models:
                    p_r = prop_func(source, receiver, env_params)
                    contribution = source.EIRP + p_r
                    total_power += db_to_rat(contribution)
            receiver.received_power = rat_to_db(total_power)
        return True
