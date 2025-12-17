# src/simulation/state.py
"""
Central state container for the entire simulation.
Holds all objects and provides easy access.
"""

from dataclasses import dataclass, field
from typing import List, Dict

from src.core.route import Route, Stop
from src.core.charging import ChargingStation
from src.core.depot import Depot
from src.fleet.bus import Bus
from src.core.disruption import DisruptionEvent
from src.hazards.manager import DisruptionManager


@dataclass
class SimulationState:
    routes: List[Route]
    stops: Dict[str, Stop]                      # stop_id → Stop
    charging_stations: List[ChargingStation]
    depots: Dict[str, Depot]                    # name → Depot
    buses: List[Bus] = field(default_factory=list)

    # Will be initialized later
    disruption_manager: DisruptionManager = None
    active_disruptions: List[DisruptionEvent] = field(default_factory=list)

    def update_charging_stations(self, updated_stations: List[ChargingStation]):
        """Called by hazard manager when flood disables stations"""
        self.charging_stations = updated_stations