# src/fleet/bus.py
"""
Bus agent class with full behavioral logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
import time
import random
from geopy.distance import geodesic

from src.core.geometry import Location
from src.core.route import Route, Stop
from src.core.charging import ChargingStation
from src.core.depot import Depot
from src.core.disruption import DisruptionEvent
from src.config.settings import SimulationSettings


@dataclass
class Trip:
    route: Route
    start_time: float  # epoch
    end_time: float    # epoch
    depot: Depot


@dataclass
class Bus:
    bus_id: str
    depot: Depot
    home_depot: Depot = None  # For return-to-home logic; fallback to depot if None

    battery_capacity_kwh: float = 100.0
    soc_percent: float = 100.0          # State of Charge
    company: str = "Default"

    # Dynamic state
    current_location: Location = field(init=False)
    current_route: Optional[Route] = None
    current_stop_index: int = 0         # Index of NEXT stop to visit
    status: str = "in_depot"            # in_depot, on_route, charging, returning_to_depot, stranded
    delay_seconds: float = 0.0
    unserved_demand: float = 0.0

    # Schedule
    daily_schedule: List[Trip] = field(default_factory=list)
    current_trip_index: int = 0

    # Charging
    charging_station: Optional[ChargingStation] = None
    charging_end_time: Optional[float] = None  # epoch or real time?

    # MIP decision (set externally)
    mip_decision: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.home_depot is None:
            self.home_depot = self.depot
        self.current_location = self.depot.location

    @property
    def soc(self) -> float:
        return self.soc_percent

    @soc.setter
    def soc(self, value: float):
        self.soc_percent = max(0.0, min(100.0, value))

    def update_soc(self, distance_km: float):
        """Simple energy consumption model"""
        consumption = distance_km * SimulationSettings.ENERGY_CONSUMPTION_KWH_PER_KM
        percent_reduction = (consumption / self.battery_capacity_kwh) * 100
        self.soc -= percent_reduction

    def get_distance_to_next_stop(self) -> Optional[float]:
        if not self.current_route or self.current_stop_index >= len(self.current_route.stops):
            return None
        next_stop = self.current_route.stops[self.current_stop_index]
        if next_stop is None:
            return None
        precomputed = self.current_route.get_distance_to_next_stop(self.current_stop_index - 1 if self.current_stop_index > 0 else 0)
        if precomputed is not None:
            return precomputed
        # Fallback to geodesic
        return geodesic(self.current_location.tuple_latlon, next_stop.location.tuple_latlon).meters

    def is_critical_soc(self) -> bool:
        return self.soc < SimulationSettings.CRITICAL_SOC_PERCENT

    def find_nearest_charger(self, stations: List[ChargingStation]) -> Optional[ChargingStation]:
        compatible_available = [
            s for s in stations
            if s.is_available(self.company)
        ]
        if not compatible_available:
            return None

        distances = [
            geodesic(self.current_location.tuple_latlon, s.location.tuple_latlon).meters
            for s in compatible_available
        ]
        nearest_idx = int(min(enumerate(distances), key=lambda x: x[1])[0])
        return compatible_available[nearest_idx]

    def start_charging(self, station: ChargingStation, current_sim_time: float):
        required_kwh = (100 - self.soc) / 100 * self.battery_capacity_kwh
        charging_time_sec = max(
            SimulationSettings.CHARGING_MIN_TIME_SECONDS,
            required_kwh / station.capacity_kw * 3600
        )
        self.charging_station = station
        self.charging_end_time = current_sim_time + charging_time_sec  # Use sim time
        station.occupy()
        self.current_location = station.location
        self.status = "charging"
        print(f"[{datetime.fromtimestamp(current_sim_time)}] {self.bus_id} started charging at {station.name}")

    def finish_charging(self, current_sim_time: float):
        if self.charging_station:
            self.charging_station.release()
            self.charging_station = None
        self.soc = 100.0
        self.status = "in_depot"  # or "idle"
        self.charging_end_time = None
        print(f"[{datetime.fromtimestamp(current_sim_time)}] {self.bus_id} finished charging")

    def return_to_depot(self, current_sim_time: float):
        dist_m = geodesic(self.current_location.tuple_latlon, self.home_depot.location.tuple_latlon).meters
        dist_km = dist_m / 1000
        if self.soc * self.battery_capacity_kwh / 100 < dist_km * SimulationSettings.ENERGY_CONSUMPTION_KWH_PER_KM:
            self.status = "stranded"
            print(f"[{datetime.fromtimestamp(current_sim_time)}] {self.bus_id} stranded - cannot reach depot")
            return
        self.update_soc(dist_km)
        self.current_location = self.home_depot.location
        self.status = "in_depot"
        print(f"[{datetime.fromtimestamp(current_sim_time)}] {self.bus_id} returned to depot")

    def step(self, context: Dict):
        """
        Main agent step function called every simulation tick.
        context contains: current_sim_time, stations, disruptions, etc.
        """
        current_time = context["current_sim_time"]
        stations = context["stations"]
        disruptions = context["disruptions"]

        # 1. Handle ongoing charging
        if self.status == "charging":
            if self.charging_end_time <= current_time:
                self.finish_charging(current_time)
            return

        # 2. Execute MIP decision if present
        if self.mip_decision:
            # Placeholder - will be filled when we implement decision_applier
            action = self.mip_decision.get("action")
            if action == "charge":
                station = context.get("station_map", {}).get(self.mip_decision["station_id"])
                if station and station.is_available(self.company):
                    self.start_charging(station, current_time)
            # ... other actions
            self.mip_decision = None  # Clear after execution

        # 3. Dispatch if scheduled
        if self.status in ["in_depot", "idle"] and self.current_trip_index < len(self.daily_schedule):
            next_trip = self.daily_schedule[self.current_trip_index]
            if current_time >= next_trip.start_time:
                self.current_route = next_trip.route
                self.current_stop_index = 0
                self.status = "on_route"
                self.current_trip_index += 1
                print(f"[{datetime.fromtimestamp(current_time)}] {self.bus_id} dispatched on {self.current_route.name}")
                return

        # 4. On-route logic
        if self.status == "on_route":
            # Check for disruption on next segment
            next_stop = self.current_route.stops[self.current_stop_index] if self.current_stop_index < len(self.current_route.stops) else None
            if next_stop:
                disrupted = any(
                    d.is_active(current_time) and
                    d.route_id == self.current_route.route_id and
                    next_stop.stop_id in d.affected_stop_ids
                    for d in disruptions
                )
                if disrupted:
                    # Simple skip logic - can be enhanced
                    print(f"{self.bus_id} skipping disrupted stop {next_stop.name}")
                    self.unserved_demand += next_stop.demand
                    self.current_stop_index += 1
                    return

            # Move to next stop
            if self.current_stop_index >= len(self.current_route.stops):
                # Trip complete
                self.current_route = None
                self.current_stop_index = 0
                self.return_to_depot(current_time)
                return

            distance_m = self.get_distance_to_next_stop()
            if distance_m is None:
                return

            distance_km = distance_m / 1000
            estimated_soc_after = self.soc - (distance_km * SimulationSettings.ENERGY_CONSUMPTION_KWH_PER_KM / self.battery_capacity_kwh * 100)

            if estimated_soc_after < SimulationSettings.CRITICAL_SOC_PERCENT:
                charger = self.find_nearest_charger(stations)
                if charger:
                    self.start_charging(charger, current_time)
                else:
                    self.return_to_depot(current_time)
                return

            # Normal move
            self.update_soc(distance_km)
            next_stop = self.current_route.stops[self.current_stop_index]
            self.current_location = next_stop.location
            self.current_stop_index += 1
            self.delay_seconds += random.randint(5, 30)  # Simulated traffic
            print(f"[{datetime.fromtimestamp(current_time)}] {self.bus_id} arrived at {next_stop.name}, SoC={self.soc:.1f}%")