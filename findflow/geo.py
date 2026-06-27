"""Geographic helpers: great-circle distance and local metric projection."""
import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def to_meters(lat: float, lon: float, lat0: float, lon0: float):
    """Equirectangular projection to local metres about (lat0, lon0).

    Good enough for a city-scale area; used for KD-tree neighbour queries.
    """
    x = (lon - lon0) * 111_320 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110_540
    return x, y
