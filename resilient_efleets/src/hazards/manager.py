# src/hazards/manager.py
"""
Central disruption manager.
Tracks active disruptions, adds new ones, expires old ones.
Supports both random disruptions and flood hazard-based disruptions.
"""

from typing import List, Optional
from datetime import datetime

from resilient_efleets.src.core.disruption import DisruptionEvent
from resilient_efleets.src.core.charging import ChargingStation
from resilient_efleets.src.hazards.random_disruption import generate_random_disruption
from resilient_efleets.src.hazards.flood import (
    FloodHazardConfig,
    FloodHazardMap,
    detect_flood_impact,
    apply_flood_impacts
)


class DisruptionManager:
    def __init__(
        self,
        flood_config: Optional[FloodHazardConfig] = None,
        use_random_disruptions: bool = True
    ):
        """
        Initialize disruption manager.
        
        Args:
            flood_config: Configuration for flood hazard-based disruptions.
                         If None, flood hazards are disabled.
            use_random_disruptions: Whether to generate random disruptions (default: True)
        """
        self.active_disruptions: List[DisruptionEvent] = []
        self.use_random_disruptions = use_random_disruptions
        
        # Initialize flood hazard system
        if flood_config is None:
            # Create default config with flood disabled
            flood_config = FloodHazardConfig(enabled=False)
        
        self.flood_config = flood_config
        self.flood_map = FloodHazardMap(flood_config) if flood_config.enabled else None
        
        # Track flooded components
        self._flooded_stations = set()
        self._flooded_depots = set()
        self._flooded_buses = set()

    def update(
        self,
        routes,
        stops,
        charging_stations,
        depots,
        buses,
        current_sim_time: float
    ) -> List[ChargingStation]:
        """
        Main update called every simulation step.
        - Expire old disruptions
        - Generate possible random disruption (if enabled)
        - Check for flood impacts (if enabled)
        
        Returns updated list of charging stations (with possible operational changes)
        """
        # 1. Expire old disruptions
        self.active_disruptions = [
            d for d in self.active_disruptions
            if d.end_time > current_sim_time
        ]

        # 2. Random disruption (if enabled)
        if self.use_random_disruptions:
            new_random = generate_random_disruption(routes, current_sim_time)
            if new_random:
                self.active_disruptions.append(new_random)

        # 3. Flood impact (if enabled)
        if self.flood_map is not None and self.flood_config.enabled:
            new_flood_disruptions, flooded_stations, flooded_depots, flooded_buses = detect_flood_impact(
                flood_map=self.flood_map,
                routes=routes,
                stops=stops,
                charging_stations=charging_stations,
                depots=depots,
                buses=buses,
                current_sim_time=current_sim_time
            )
            
            # Add flood disruptions
            self.active_disruptions.extend(new_flood_disruptions)
            
            # Apply flood impacts to infrastructure
            apply_flood_impacts(
                charging_stations=charging_stations,
                flooded_station_names=flooded_stations,
                buses=buses,
                flooded_bus_ids=flooded_buses
            )
            
            # Track flooded components for monitoring
            self._flooded_stations = flooded_stations
            self._flooded_depots = flooded_depots
            self._flooded_buses = flooded_buses

        # Log active disruptions count if any changes
        if self.active_disruptions:
            timestamp = datetime.fromtimestamp(current_sim_time).strftime('%H:%M:%S')
            print(f"[{timestamp}] Active disruptions: {len(self.active_disruptions)}")

        return charging_stations

    def get_active_disruptions(self) -> List[DisruptionEvent]:
        """Get list of currently active disruption events"""
        return self.active_disruptions
    
    def get_flooded_components_summary(self) -> dict:
        """Get summary of currently flooded components"""
        return {
            'charging_stations': list(self._flooded_stations),
            'depots': list(self._flooded_depots),
            'buses': list(self._flooded_buses)
        }