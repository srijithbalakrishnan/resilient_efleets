# src/hazards/manager.py
"""
Central disruption manager.
Tracks active disruptions, adds new ones, expires old ones.
"""

from typing import List
from datetime import datetime

from src.core.disruption import DisruptionEvent
from src.hazards.random_disruption import generate_random_disruption
from src.hazards.flood import detect_flood_impact, load_flood_zones


class DisruptionManager:
    def __init__(self, flood_file: str = None):
        self.active_disruptions: List[DisruptionEvent] = []
        self.flood_gdf = load_flood_zones(flood_file)

    def update(
        self,
        routes,
        charging_stations,
        current_sim_time: float
    ) -> List[ChargingStation]:
        """
        Main update called every simulation step.
        - Expire old disruptions
        - Generate possible random disruption
        - Check for flood impacts
        Returns updated list of charging stations (with possible operational changes)
        """
        # 1. Expire old disruptions
        self.active_disruptions = [
            d for d in self.active_disruptions
            if d.end_time > current_sim_time
        ]

        # 2. Random disruption
        new_random = generate_random_disruption(routes, current_sim_time)
        if new_random:
            self.active_disruptions.append(new_random)

        # 3. Flood impact
        new_flood_disruptions, updated_stations = detect_flood_impact(
            self.flood_gdf,
            routes,
            charging_stations,
            current_sim_time
        )
        self.active_disruptions.extend(new_flood_disruptions)

        if new_flood_disruptions or new_random:
            print(f"[{datetime.fromtimestamp(current_sim_time).strftime('%H:%M:%S')}] "
                  f"Active disruptions: {len(self.active_disruptions)}")

        return updated_stations

    def get_active_disruptions(self) -> List[DisruptionEvent]:
        return self.active_disruptions