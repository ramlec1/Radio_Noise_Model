from __future__ import annotations
from typing import Tuple

import math
import numpy as np
from geographiclib.geodesic import Geodesic


_WGS84 = Geodesic.WGS84 # instantiated globally to avoid re-initialization at each call
def latlon_to_local_meters(
    lat: float, lon: float, lat0: float, lon0: float
) -> Tuple[float, float]:
    """Convert (lat, lon) to local Cartesian (x, y) metres, origin at (lat0, lon0).

    Uses geodesic distance and forward azimuth so that Euclidean distance from
    the origin equals the true geodesic distance. Accurate for any distance
    (household scale to thousands of km). Compatible with skywave propagation.

    Convention: x = East, y = North.

    Args:
        lat, lon: Point to convert (degrees).
        lat0, lon0: Origin (degrees).

    Returns:
        (x, y) in metres; x is East, y is North.
    """
    result = _WGS84.Inverse(lat0, lon0, lat, lon)
    distance_m = result["s12"]
    azimuth_deg = result["azi1"]  # Forward azimuth from North, clockwise

    azimuth_rad = math.radians(azimuth_deg)
    x = distance_m * math.sin(azimuth_rad)  # East
    y = distance_m * math.cos(azimuth_rad)  # North
    return x, y


def db_to_rat(db_value: float) -> float:
    """Convert dB value to ratio."""
    return 10 ** (db_value / 10)

def rat_to_db(ratio_value: float) -> float:
    """Convert ratio value to dB."""
    return 10 * np.log10(ratio_value)