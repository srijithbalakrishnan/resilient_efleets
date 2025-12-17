# src/core/geometry.py
from dataclasses import dataclass
from shapely.geometry import Point

@dataclass(frozen=True)
class Location:
    lat: float
    lon: float

    @property
    def geometry(self) -> Point:
        return Point(self.lon, self.lat)  # shapely uses (lon, lat)

    @property
    def tuple_latlon(self):
        return (self.lat, self.lon)