# src/data/loader.py
"""
Data loading module.
Loads CSV files and constructs the core network objects:
- Stops (unique across all routes)
- Routes with ordered stops and segment distances
- ChargingStations
- Depots
- Returns a fully initialized NetworkState (or dict) ready for simulation
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple

from resilient_efleets.src.core.geometry import Location
from resilient_efleets.src.core.route import Stop, Route
from resilient_efleets.src.core.charging import ChargingStation
from resilient_efleets.src.core.depot import Depot
from resilient_efleets.src.config.paths import data_path


def load_stops_and_routes(
    routes_csv: str = "TVM Route.csv"
) -> Tuple[Dict[str, Stop], List[Route]]:
    """
    Load stops and routes from the routes CSV.
    Ensures stops are unique (shared across routes).
    Handles sequence numbers and consecutive distances.
    """
    df = pd.read_csv(data_path(routes_csv))

    # Create unique Stop objects
    stops: Dict[str, Stop] = {}
    for _, row in df.iterrows():
        stop_id = str(row["Stop Id"]).strip()
        if stop_id not in stops:
            stops[stop_id] = Stop(
                stop_id=stop_id,
                name=str(row["Stop Name"]).strip(),
                location=Location(
                    lat=float(row["Stop lat"]),
                    lon=float(row["Stop lon"])
                ),
                is_stage=bool(row.get("isStage", False)),
                demand=float(row.get("demand", 1.0))
            )

    # Create Routes and assign stops
    routes: Dict[str, Route] = {}
    for _, row in df.iterrows():
        route_id = str(row["Route id"]).strip()
        if route_id not in routes:
            routes[route_id] = Route(
                route_id=route_id,
                name=str(row["Route Name"]).strip()
            )

        route = routes[route_id]
        stop = stops[str(row["Stop Id"]).strip()]
        seq_num = int(row["Seq Number"])
        distance = row.get("Consecutive Distance(m)")
        distance_meters = float(distance) if pd.notna(distance) else None

        # Add stop with distance to previous (if not first)
        route.add_stop(stop, seq_num, distance_to_previous=distance_meters)

    return stops, list(routes.values())


def load_charging_stations(
    chargers_csv: str = "Charger.csv"
) -> List[ChargingStation]:
    """
    Load charging stations from CSV.
    """
    df = pd.read_csv(data_path(chargers_csv))

    stations: List[ChargingStation] = []
    for _, row in df.iterrows():
        compatible = row.get("Compatible Companies", "Default")
        if pd.isna(compatible):
            compatible_list = ["Default"]
        else:
            compatible_list = [c.strip() for c in str(compatible).split(",")]

        station = ChargingStation(
            name=str(row["Location Name"]).strip(),
            location=Location(
                lat=float(row["Latitude"]),
                lon=float(row["Longitude"])
            ),
            capacity_kw=float(row.get("Charger Capacity (kW)", 50.0)),
            total_slots=int(row.get("Number of Chargers", 1)),
            compatible_companies=compatible_list
        )
        stations.append(station)

    return stations


def load_depots(
    depots_csv: str = "Depot.csv"
) -> Dict[str, Depot]:
    """
    Load depots and return as dict: name -> Depot
    """
    df = pd.read_csv(data_path(depots_csv))

    depots: Dict[str, Depot] = {}
    for _, row in df.iterrows():
        depot = Depot(
            name=str(row["Depot Name"]).strip(),
            location=Location(
                lat=float(row["Latitude"]),
                lon=float(row["Longitude"])
            )
        )
        depots[depot.name] = depot

    return depots


def load_all_network_data() -> dict:
    """
    Convenience function to load everything at once.
    Returns a dictionary compatible with the rest of the simulation modules.
    """
    print("Loading network data...")

    stops, routes = load_stops_and_routes()
    charging_stations = load_charging_stations()
    depots = load_depots()

    print(f"Loaded:")
    print(f"  - {len(stops)} unique stops")
    print(f"  - {len(routes)} routes")
    print(f"  - {len(charging_stations)} charging stations")
    print(f"  - {len(depots)} depots")

    return {
        "stops": stops,
        "routes": routes,
        "charging_stations": charging_stations,
        "depots": depots
    }