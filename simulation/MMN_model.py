from typing import Callable, List
import numpy as np

from .utils import db_to_rat, rat_to_db
from .MMN_dataclasses import NoiseSource, Receiver, EnvironmentParameters


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
    """Core simulation model for radio noise power."""
    def __init__(self, 
                 noise_sources: List[NoiseSource], 
                 receivers: List[Receiver],
                 environment_params: EnvironmentParameters,
                 propagation_function: Callable[[NoiseSource, Receiver, EnvironmentParameters], float]):                 
        self.noise_sources = noise_sources
        self.receivers = receivers
        self.environment_params = environment_params
        self.propagation_function = propagation_function
        

    def compute_total_power(self) -> bool:
        """Compute total received power S at each receiver."""
        
        for receiver in self.receivers:
            total_power = 0.0                               # [dBW/m^2]
            for source in self.noise_sources:
                r = receiver.distance_to(source.position)   # [m] 
                # Check if the receiver is in the far field of the source
                receiver.far_field = receiver.far_field_condition(source)
                if not receiver.far_field:
                    raise NearFieldError(distance_m=r, freq_hz=source.freq, source_id=source.id)
                p_r = self.propagation_function(source, receiver, self.environment_params)
                contribution = source.EIRP + p_r
                total_power += db_to_rat(contribution)
            receiver.received_power = rat_to_db(total_power)
        return True
    
    """
    TODO HERE:
    - get multiple propagation models working simultaneaously. Test which propagation model(s) should be used for which source/receiver pair.
    - inlezen op de RNDb
    """

