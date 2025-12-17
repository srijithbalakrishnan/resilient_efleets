# src/core/depot.py
from dataclasses import dataclass
from .geometry import Location

@dataclass
class Depot:
    name: str
    location: Location

    @property
    def geometry(self):
        return self.location.geometry