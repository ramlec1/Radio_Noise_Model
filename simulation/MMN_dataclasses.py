from typing import Tuple
from dataclasses import dataclass
import math

@dataclass
class NoiseSource:
    """Represents a single noise source (household)."""
    id: int
    lat: float                     # [deg] WGS84 latitude
    lon: float                     # [deg] WGS84 longitude
    address: str                   # addr:housenumber or OSM id
    position: Tuple[float, float] = (0.0, 0.0)  # [m] local Cartesian, set at simulate
    EIRP: float = 0.0              # [dBW] Effective Isotropic Radiated Power
    freq: float = 0.0              # [Hz] Frequency
    height: float = 1.5            # [m]
    pol: int = 1                   # [1] Polarization: 0 = horizontal, 1 = vertical
    
    
@dataclass
class Receiver:
    """Represents a single receiver."""
    id: int
    position: Tuple[float, float] # [m] coordinates
    height: float = 1.5           # [m]
    received_power: float = 0.0   # [dBW/m^2]
    far_field: bool = True        # Flag to indicate if the receiver is in near field of any source

    def distance_to(self, target_position: Tuple[float, float]) -> float:
        """Calculate the distance from this target (source) to the receiver."""
        dx = self.position[0] - target_position[0]
        dy = self.position[1] - target_position[1]
        return math.hypot(dx, dy)
    
    def far_field_condition(self, source: NoiseSource, c0=3e8) -> bool:
        """
        Check if the distance r satisfies the far field condition for a given frequency freq.
        The Fraunhofer far field condition is: r > 2 * D^2 / lambda, where D = lambda / 2 (assumption).
        """
        r = self.distance_to(source.position)
        freq = source.freq
        return r > c0/(2*freq)
        

@dataclass
class EnvironmentParameters:
    """Parameters of the environment affecting propagation."""
    N_s: float      # [N-units] Surface refractivity in N-units
    epsilon: float  # [1]       Relative permittivity of the earth surface
    sigma: float    # [S/m]     Conductivity of the earth surface in S/m
