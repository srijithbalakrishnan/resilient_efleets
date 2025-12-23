# src/hazards/flood.py
"""
Flood zone handling: load flood areas and detect impacted stops/chargers.
"""

import geopandas as gpd
from shapely.geometry import Point
from typing import List, Tuple

from resilient_efleets.src.core.route import Stop
from resilient_efleets.src.core.charging import ChargingStation
from resilient_efleets.src.core.disruption import DisruptionEvent
from resilient_efleets.src.config.paths import data_path


# You can later load real flood data; for now, provide a default dummy
DEFAULT_FLOOD_GDF = gpd.GeoDataFrame(
    {'geometry': [Point(0, 0).buffer(0.01)]},  # Small area around (0,0)
    crs="EPSG:4326"
)


def load_flood_zones(flood_file: str = None) -> gpd.GeoDataFrame:
    """
    Load flood zones from a GeoPackage, Shapefile, or GeoJSON.
    If no file provided, returns a small dummy zone.
    """
    if flood_file is None:
        print("No flood file provided — using dummy flood zone.")
        return DEFAULT_FLOOD_GDF.copy()

    flood_path = data_path(flood_file)
    if not flood_path.exists():
        print(f"Flood file {flood_path} not found — using dummy.")
        return DEFAULT_FLOOD_GDF.copy()

    try:
        gdf = gpd.read_file(flood_path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf = gdf.to_crs("EPSG:4326")
        print(f"Loaded flood zones from {flood_path}")
        return gdf
    except Exception as e:
        print(f"Error loading flood zones: {e} — using dummy.")
        return DEFAULT_FLOOD_GDF.copy()


def detect_flood_impact(
    flood_gdf: gpd.GeoDataFrame,
    routes: List['Route'],
    charging_stations: List[ChargingStation],
    current_sim_time: float,
    flood_duration_minutes: int = 30
) -> Tuple[List[DisruptionEvent], List[ChargingStation]]:
    """
    Check which stops and charging stations are inside flood zones.
    Returns:
        - List of new DisruptionEvents (one per affected route)
        - List of charging stations with updated operational status
    """
    if flood_gdf.empty:
        return [], charging_stations

    disruptions: List[DisruptionEvent] = []
    affected_routes = set()

    # Check stops
    for route in routes:
        affected_stop_ids = []
        for stop in route.stops:
            if stop is None:
                continue
            point = stop.geometry
            if flood_gdf.intersects(point).any():
                affected_stop_ids.append(stop.stop_id)

        if affected_stop_ids:
            affected_routes.add(route.route_id)
            disruption = DisruptionEvent(
                route_id=route.route_id,
                affected_stop_ids=affected_stop_ids,
                start_time=current_sim_time,
                end_time=current_sim_time + flood_duration_minutes * 60,
                description=f"Flood disruption on {route.name}"
            )
            disruptions.append(disruption)
            print(f"FLOOD: Route {route.name} — stops affected: {affected_stop_ids}")

    # Disable flooded charging stations
    flooded_station_names = []
    for station in charging_stations:
        was_operational = station.operational
        point = station.geometry
        now_flooded = flood_gdf.intersects(point).any()
        station.operational = not now_flooded

        if was_operational and now_flooded:
            flooded_station_names.append(station.name)

    if flooded_station_names:
        print(f"FLOOD: Charging stations disabled: {flooded_station_names}")

    return disruptions, charging_stations