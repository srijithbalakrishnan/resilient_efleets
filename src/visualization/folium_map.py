# src/visualization/folium_map.py
"""
Create an interactive Folium map of the transit network.
Shows routes, stops, depots, charging stations, and optional flood zones.
"""

import folium
from typing import List, Dict, Optional

from src.core.route import Route, Stop
from src.core.charging import ChargingStation
from src.core.depot import Depot
from src.config.paths import output_path


def create_network_map(
    routes: List[Route],
    stops: Dict[str, Stop],
    charging_stations: List[ChargingStation],
    depots: Dict[str, Depot],
    flood_gdf=None,
    output_file: str = "network_map.html"
) -> str:
    """
    Generate and save an interactive Folium map.
    Returns the path to the saved file.
    """
    print("Generating network visualization...")

    # Collect coordinates for centering
    all_coords = []
    for stop in stops.values():
        all_coords.append((stop.location.lat, stop.location.lon))
    for station in charging_stations:
        all_coords.append((station.location.lat, station.location.lon))
    for depot in depots.values():
        all_coords.append((depot.location.lat, depot.location.lon))

    if not all_coords:
        center = (0, 0)
    else:
        center = (sum(c[0] for c in all_coords) / len(all_coords),
                  sum(c[1] for c in all_coords) / len(all_coords))

    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    # Routes as colored lines
    colors = ["blue", "red", "green", "purple", "orange", "darkblue", "gray", "pink"]
    for i, route in enumerate(routes):
        color = colors[i % len(colors)]
        coords = [(s.location.lat, s.location.lon) for s in route.stops if s]
        if len(coords) > 1:
            folium.PolyLine(
                coords,
                color=color,
                weight=4,
                opacity=0.7,
                popup=f"Route {route.name}",
                tooltip=f"Route {route.route_id}"
            ).add_to(m)

    # Stops
    for stop in stops.values():
        icon_color = "blue" if not stop.is_stage else "cadetblue"
        folium.CircleMarker(
            location=(stop.location.lat, stop.location.lon),
            radius=5,
            color=icon_color,
            fill=True,
            fill_opacity=0.8,
            popup=f"<b>{stop.name}</b><br>ID: {stop.stop_id}<br>Demand: {stop.demand}",
            tooltip=stop.name
        ).add_to(m)

    # Charging stations
    for station in charging_stations:
        color = "green" if station.operational else "red"
        folium.Marker(
            location=(station.location.lat, station.location.lon),
            icon=folium.Icon(color=color, icon="plug", prefix="fa"),
            popup=f"<b>{station.name}</b><br>"
                  f"Capacity: {station.capacity_kw} kW<br>"
                  f"Slots: {station.total_slots}<br>"
                  f"Operational: {station.operational}",
            tooltip=station.name
        ).add_to(m)

    # Depots
    for depot in depots.values():
        folium.Marker(
            location=(depot.location.lat, depot.location.lon),
            icon=folium.Icon(color="black", icon="home", prefix="fa"),
            popup=f"<b>Depot: {depot.name}</b>",
            tooltip=depot.name
        ).add_to(m)

    # Flood zones (if provided)
    if flood_gdf is not None and not flood_gdf.empty:
        folium.GeoJson(
            flood_gdf.__geo_interface__,
            style_function=lambda x: {
                "fillColor": "red",
                "color": "red",
                "weight": 2,
                "fillOpacity": 0.3
            },
            name="Flood Zones"
        ).add_to(m)

    # Layer control
    folium.LayerControl().add_to(m)

    output_path_full = output_path(output_file)
    m.save(str(output_path_full))
    print(f"Map saved to: {output_path_full}")
    return str(output_path_full)