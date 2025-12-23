# src/core/charging.py
from dataclasses import dataclass, field
from typing import List
from .geometry import Location

@dataclass
class ChargingStation:
    name: str
    location: Location
    capacity_kw: float = 100.0
    total_slots: int = 1
    compatible_companies: List[str] = field(default_factory=lambda: ["Default"])
    operational: bool = True

    available_slots: int = field(init=False)

    def __post_init__(self):
        self.available_slots = self.total_slots

    @property
    def geometry(self):
        return self.location.geometry

    def is_available(self, company: str) -> bool:
        return (
            self.operational
            and self.available_slots > 0
            and company in self.compatible_companies
        )

    def occupy(self):
        if self.available_slots > 0:
            self.available_slots -= 1

    def release(self):
        if self.available_slots < self.total_slots:
            self.available_slots += 1