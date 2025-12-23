# src/fleet/schedule.py
"""
Loads the bus schedule CSV and assigns daily trips to individual buses.
Creates Bus objects with their scheduled trips.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict

from resilient_efleets.src.data.loader import data_path
from resilient_efleets.src.core.route import Route
from resilient_efleets.src.core.depot import Depot
from resilient_efleets.src.fleet.bus import Bus  # Forward reference for type hinting; actual import later


def load_bus_schedules(
    schedule_csv: str = "Consolidated_Cleaned_Bus_Schedule.csv",
    routes: List[Route] = None,
    depots: Dict[str, Depot] = None
) -> List[Bus]:
    """
    Load the schedule CSV and create Bus objects with assigned daily trips.
    
    Args:
        schedule_csv: Filename of the schedule CSV
        routes: List of all Route objects (for lookup by route_id)
        depots: Dict of Depot objects (name -> Depot)
    
    Returns:
        List of initialized Bus objects with daily_schedule populated
    """
    if routes is None or depots is None:
        raise ValueError("Routes and depots must be provided for schedule loading.")

    df = pd.read_csv(data_path(schedule_csv))

    # Create lookup dicts
    route_lookup: Dict[str, Route] = {r.route_id: r for r in routes}
    
    # Temporary bus dict: duty_number -> Bus
    buses: Dict[int, Bus] = {}

    today = datetime.now().date()

    for _, row in df.iterrows():
        try:
            duty_number = int(row["Duty Number"])
            route_id = str(row["Route Id"]).strip()
            departure_str = str(row["Departure Time"]).strip()
            arrival_str = str(row["Arrival Time"]).strip()
            depot_name = str(row["Depot Name"]).strip()

            # Parse times
            dep_time = datetime.strptime(departure_str, "%H:%M").time()
            arr_time = datetime.strptime(arrival_str, "%H:%M").time()

            departure_dt = datetime.combine(today, dep_time)
            arrival_dt = datetime.combine(today, arr_time)

            # Handle overnight trips
            if arrival_dt < departure_dt:
                arrival_dt += timedelta(days=1)

            start_epoch = departure_dt.timestamp()
            end_epoch = arrival_dt.timestamp()

            # Get or create Bus
            if duty_number not in buses:
                depot = depots.get(depot_name)
                if depot is None:
                    print(f"Warning: Depot '{depot_name}' not found for duty {duty_number}. Skipping.")
                    continue

                bus = Bus(
                    bus_id=f"Bus_{duty_number}",
                    depot=depot,
                    home_depot=depot  # Can be different later if needed
                )
                buses[duty_number] = bus
            else:
                bus = buses[duty_number]

            # Get Route
            route = route_lookup.get(route_id)
            if route is None:
                print(f"Warning: Route '{route_id}' not found for duty {duty_number}. Skipping trip.")
                continue

            # Append trip to schedule
            bus.daily_schedule.append({
                "route": route,
                "start_time": start_epoch,
                "end_time": end_epoch,
                "depot": depots[depot_name]
            })

        except Exception as e:
            print(f"Error processing schedule row for duty {duty_number}: {e}")
            continue

    # Sort trips chronologically for each bus
    for bus in buses.values():
        bus.daily_schedule.sort(key=lambda t: t["start_time"])

    # Convert to list and sort by bus_id for consistency
    bus_list = sorted(buses.values(), key=lambda b: b.bus_id)

    print(f"Created {len(bus_list)} buses with scheduled trips.")
    return bus_list