"""Distance helpers for geo-aware ranking."""

from __future__ import annotations

import math

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance between two WGS84 points.

    Args:
        lat1: Latitude of the first point, in decimal degrees.
        lon1: Longitude of the first point, in decimal degrees.
        lat2: Latitude of the second point, in decimal degrees.
        lon2: Longitude of the second point, in decimal degrees.

    Returns:
        The distance between the two points, in kilometers.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def distance_decay(km: float, tau_km: float = 2.0) -> float:
    """Compute an exponential proximity boost for geo re-ranking.

    Args:
        km: Distance from the focus point, in kilometers.
        tau_km: Decay constant, in kilometers; larger values make the boost
            fall off more slowly with distance.

    Returns:
        A value in (0, 1], equal to 1.0 at the focus point and decaying
        exponentially as `km` grows.
    """
    return math.exp(-km / tau_km)
