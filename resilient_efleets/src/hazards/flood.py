# src/hazards/flood.py
"""
Flood hazard handling: Load flood depth maps (TIF raster) and detect impacted network components.
Supports threshold-based disruptions for routes, stops, charging stations, depots, and buses.
"""

import numpy as np
import rasterio
from rasterio.transform import rowcol
from shapely.geometry import Point
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

from resilient_efleets.src.core.route import Route, Stop
from resilient_efleets.src.core.charging import ChargingStation
from resilient_efleets.src.core.depot import Depot
from resilient_efleets.src.core.disruption import DisruptionEvent
from resilient_efleets.src.config.paths import data_path


@dataclass
class FloodHazardConfig:
    """Configuration for flood hazard-based disruptions"""
    # Which flood map to use (e.g., 'Kerala_Flood_100_Yrs_Historical.tif')
    flood_map_file: str = 'Kerala_Flood_100_Yrs_Historical.tif'
    
    # Flood depth threshold in meters (rasters assumed in centimeters)
    flood_depth_threshold_m: float = 0.5

    # Hydrology dynamics (cm/hr)
    precipitation_cm_per_hr: float = 0.0
    recession_cm_per_hr: float = 0.0
    
    # Which components can be disrupted
    disrupt_routes: bool = True
    disrupt_stops: bool = True
    disrupt_charging_stations: bool = True
    disrupt_depots: bool = False
    disrupt_buses: bool = False  # Buses at flooded locations
    
    # Disruption duration
    flood_duration_minutes: int = 120  # 2 hours default
    
    # Whether to use flood hazards at all
    enabled: bool = True
    
    def __post_init__(self):
        """Validate configuration"""
        if self.flood_depth_threshold_m <= 0:
            raise ValueError("flood_depth_threshold_m must be positive")
        if self.flood_duration_minutes <= 0:
            raise ValueError("flood_duration_minutes must be positive")
        if self.precipitation_cm_per_hr < 0:
            raise ValueError("precipitation_cm_per_hr cannot be negative")
        if self.recession_cm_per_hr < 0:
            raise ValueError("recession_cm_per_hr cannot be negative")


class FloodHazardMap:
    """Handles loading and querying flood depth from raster TIF files"""
    
    def __init__(self, config: FloodHazardConfig):
        self.config = config
        self.raster_data: Optional[np.ndarray] = None
        self.transform = None
        self.crs = None
        self.nodata_value = None
        self._t0: Optional[float] = None  # simulation start timestamp for dynamics
        self._load_raster()
    
    def _load_raster(self):
        """Load the flood hazard raster from TIF file"""
        if not self.config.enabled or not self.config.flood_map_file:
            print("Flood hazard disabled or no map file specified")
            return
        
        # Construct path to flood map
        flood_path = data_path("floods_maps") / self.config.flood_map_file
        
        if not flood_path.exists():
            print(f"WARNING: Flood map not found at {flood_path}")
            print("Flood hazard analysis disabled")
            return
        
        try:
            with rasterio.open(flood_path) as src:
                # Read first band and enforce non-negative (assumed cm units)
                self.raster_data = np.maximum(src.read(1), 0)
                self.transform = src.transform
                self.crs = src.crs
                self.nodata_value = src.nodata
                
            print(f"✓ Loaded flood hazard map: {self.config.flood_map_file}")
            print(f"  - Shape: {self.raster_data.shape}")
            print(f"  - CRS: {self.crs}")
            print(f"  - Depth threshold: {self.config.flood_depth_threshold_m} m")
            # Report stats in both cm and m (assuming cm in raster)
            valid = self.raster_data if self.nodata_value is None else self.raster_data[self.raster_data != self.nodata_value]
            if valid.size:
                max_cm = float(np.nanmax(valid))
                print(f"  - Max flood depth: {max_cm:.1f} cm ({max_cm/100:.2f} m)")
            
        except Exception as e:
            print(f"ERROR loading flood map {flood_path}: {e}")
            print("Flood hazard analysis disabled")
            self.raster_data = None
    
    def _base_depth_cm_at_point(self, lon: float, lat: float) -> float:
        """
        Get base flood depth from raster at a specific point (lon, lat) in centimeters.
        Returns 0.0 if no flood or outside raster bounds.
        """
        if self.raster_data is None or self.transform is None:
            return 0.0
        
        try:
            # Convert geographic coordinates to raster row, col
            row, col = rowcol(self.transform, lon, lat)
            
            # Check bounds
            if row < 0 or row >= self.raster_data.shape[0] or col < 0 or col >= self.raster_data.shape[1]:
                return 0.0
            
            depth = self.raster_data[row, col]
            
            # Handle nodata
            if self.nodata_value is not None and depth == self.nodata_value:
                return 0.0
            
            # Handle NaN
            if np.isnan(depth):
                return 0.0
            
            # Enforce non-negative (already applied on load, but keep safe)
            return float(depth) if depth > 0 else 0.0
            
        except Exception as e:
            # Silently return 0.0 for any errors (likely out of bounds)
            return 0.0
    
    def get_effective_depth_m(self, lon: float, lat: float, current_sim_time: Optional[float]) -> float:
        """
        Compute effective flood depth at (lon, lat) incorporating simple precipitation/recession dynamics.
        - Base raster values are assumed centimeters.
        - precipitation_cm_per_hr and recession_cm_per_hr adjust depth linearly over elapsed hours.
        Returns depth in meters.
        """
        base_cm = self._base_depth_cm_at_point(lon, lat)
        if current_sim_time is None:
            return base_cm / 100.0
        # Initialize start time on first call
        if self._t0 is None:
            self._t0 = current_sim_time
        hours = max(0.0, (current_sim_time - self._t0) / 3600.0)
        delta_cm = (self.config.precipitation_cm_per_hr - self.config.recession_cm_per_hr) * hours
        eff_cm = max(0.0, base_cm + delta_cm)
        return eff_cm / 100.0


def detect_flood_impact(
    flood_map: FloodHazardMap,
    routes: List[Route],
    stops: List[Stop],
    charging_stations: List[ChargingStation],
    depots: Dict[str, Depot],
    buses: List['Bus'],
    current_sim_time: float
) -> Tuple[List[DisruptionEvent], Set[str], Set[str], Set[str]]:
    """
    Check which network components are affected by flooding.
    
    Returns:
        - List of DisruptionEvents for affected routes
        - Set of flooded charging station names
        - Set of flooded depot names
        - Set of flooded bus IDs
    """
    if flood_map.raster_data is None or not flood_map.config.enabled:
        return [], set(), set(), set()
    
    config = flood_map.config
    disruptions: List[DisruptionEvent] = []
    flooded_stations: Set[str] = set()
    flooded_depots: Set[str] = set()
    flooded_buses: Set[str] = set()
    
    # 1. Check stops and create route disruptions
    if config.disrupt_routes or config.disrupt_stops:
        route_affected_stops: Dict[str, List[str]] = {}
        
        for route in routes:
            affected_stop_ids = []
            for stop in route.stops:
                if stop is None:
                    continue
                
                lon, lat = stop.location.lon, stop.location.lat
                depth_m = flood_map.get_effective_depth_m(lon, lat, current_sim_time)
                if depth_m >= config.flood_depth_threshold_m:
                    affected_stop_ids.append(stop.stop_id)
            
            if affected_stop_ids:
                route_affected_stops[route.route_id] = affected_stop_ids
                
                # Create disruption event
                disruption = DisruptionEvent(
                    route_id=route.route_id,
                    affected_stop_ids=affected_stop_ids,
                    start_time=current_sim_time,
                    end_time=current_sim_time + config.flood_duration_minutes * 60,
                    description=f"Flood disruption ({len(affected_stop_ids)} stops affected)"
                )
                disruptions.append(disruption)
                print(f"  🌊 FLOOD: Route {route.name} — {len(affected_stop_ids)} stops flooded")
    
    # 2. Check charging stations
    if config.disrupt_charging_stations:
        for station in charging_stations:
            lon, lat = station.location.lon, station.location.lat
            depth_m = flood_map.get_effective_depth_m(lon, lat, current_sim_time)
            if depth_m >= config.flood_depth_threshold_m:
                flooded_stations.add(station.name)
                print(f"  🌊 FLOOD: Charging Station '{station.name}' (depth: {depth_m:.2f}m)")
    
    # 3. Check depots
    if config.disrupt_depots:
        for depot_name, depot in depots.items():
            lon, lat = depot.location.lon, depot.location.lat
            depth_m = flood_map.get_effective_depth_m(lon, lat, current_sim_time)
            if depth_m >= config.flood_depth_threshold_m:
                flooded_depots.add(depot_name)
                print(f"  🌊 FLOOD: Depot '{depot_name}' (depth: {depth_m:.2f}m)")
    
    # 4. Check buses at current locations
    if config.disrupt_buses:
        for bus in buses:
            if hasattr(bus, 'current_location') and bus.current_location:
                lon, lat = bus.current_location.lon, bus.current_location.lat
                depth_m = flood_map.get_effective_depth_m(lon, lat, current_sim_time)
                if depth_m >= config.flood_depth_threshold_m:
                    flooded_buses.add(bus.bus_id)
                    print(f"  🌊 FLOOD: Bus '{bus.bus_id}' stranded (depth: {depth_m:.2f}m)")
    
    return disruptions, flooded_stations, flooded_depots, flooded_buses


def apply_flood_impacts(
    charging_stations: List[ChargingStation],
    flooded_station_names: Set[str],
    buses: List['Bus'],
    flooded_bus_ids: Set[str]
) -> None:
    """
    Apply flood impacts to charging stations and buses.
    Modifies objects in place.
    """
    # Disable flooded charging stations
    for station in charging_stations:
        was_operational = station.operational
        is_flooded = station.name in flooded_station_names
        station.operational = not is_flooded
        
        # Optionally log status changes
        if was_operational and is_flooded:
            pass  # Already logged in detect_flood_impact
        elif not was_operational and not is_flooded:
            print(f"  ✓ Charging Station '{station.name}' restored")
    
    # Strand flooded buses
    for bus in buses:
        if bus.bus_id in flooded_bus_ids:
            if bus.status != "stranded":
                bus.status = "stranded"
                # Optionally: set SoC to 0 or apply other penalties