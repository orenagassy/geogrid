"""Square geo-grid generation around a center point."""
import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
KM_PER_MILE = 1.609344


@dataclass(frozen=True)
class GridPoint:
    row: int
    col: int
    lat: float
    lng: float


def parse_distance_km(value: str | float) -> float:
    """'1km', '0.5 mi', '800m' or a bare number (km) -> km."""
    if isinstance(value, (int, float)):
        return float(value)
    s = value.strip().lower().replace(" ", "")
    for suffix, factor in (("km", 1.0), ("mi", KM_PER_MILE), ("m", 0.001)):
        if s.endswith(suffix):
            return float(s[: -len(suffix)]) * factor
    return float(s)


def offset(lat: float, lng: float, north_km: float, east_km: float) -> tuple[float, float]:
    dlat = math.degrees(north_km / EARTH_RADIUS_KM)
    dlng = math.degrees(east_km / (EARTH_RADIUS_KM * math.cos(math.radians(lat))))
    return lat + dlat, lng + dlng


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def validate_grid(size: int, spacing_km: float) -> None:
    if size % 2 == 0 or not 3 <= size <= 13:
        raise ValueError("grid size must be an odd number between 3 and 13")
    if spacing_km <= 0:
        raise ValueError("spacing must be positive")


def make_grid(center_lat: float, center_lng: float, size: int, spacing_km: float) -> list[GridPoint]:
    """size x size points (size odd, 3..13), row 0 = north, col 0 = west."""
    validate_grid(size, spacing_km)
    half = size // 2
    points = []
    for row in range(size):
        for col in range(size):
            lat, lng = offset(center_lat, center_lng, (half - row) * spacing_km, (col - half) * spacing_km)
            points.append(GridPoint(row, col, round(lat, 7), round(lng, 7)))
    return points
