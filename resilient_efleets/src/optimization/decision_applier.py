# src/optimization/decision_applier.py
"""
Safely apply MIP decisions to Bus objects.
Handles infeasible cases gracefully.
"""

from typing import Dict, List
from resilient_efleets.src.fleet.bus import Bus
from resilient_efleets.src.core.charging import ChargingStation
import time

def apply_mip_decisions(
    buses: List[Bus],
    mip_result: Dict,
    charging_stations: List[ChargingStation],
    current_sim_time: float
) -> None:
    """
    Apply the decisions returned by optimize_network().
    Only applies immediate (myopic) actions from the MIP.
    """
    decisions = mip_result.get("decisions", {})
    S_map = mip_result.get("S_map", {})
    C_unique_map = mip_result.get("C_unique_map", {})

    # Map CS IDs back to actual ChargingStation objects
    station_map = {cs_id: station for cs_id, station in C_unique_map.items()}

    for bus in buses:
        decision = decisions.get(bus.bus_id)
        if not decision:
            # No decision from MIP → bus continues current behavior (handled in bus.step)
            continue

        action = decision["action"]
        print(f"MIP → {bus.bus_id}: {action} "
              f"({decision.get('target_node_id') or decision.get('station_id', '')})")

        if action == "charge":
            station_id = decision["station_id"]
            station = station_map.get(station_id)

            if station and station.is_available(bus.company):
                # Calculate charging duration based on current SOC and charger power
                # Assume we charge until full or for a reasonable time (e.g., up to 60 minutes)
                needed_kwh = (100 - bus.soc) / 100 * bus.battery_capacity_kwh
                charge_rate_kw = station.capacity_kw  # or min(station.capacity_kw, bus.max_charge_kw) if you have that
                charge_time_hours = needed_kwh / charge_rate_kw
                charge_time_seconds = min(charge_time_hours * 3600, 3600)  # cap at 1 hour for safety

                # Set charging parameters
                bus.status = "charging"
                bus.charging_station = station
                bus.charging_start_time = current_sim_time
                bus.charging_end_time = current_sim_time + charge_time_seconds
                bus.mip_decision = None  # Decision applied

                print(f"  → Started charging at {station.name}, "
                      f"expected end: {time.strftime('%H:%M:%S', time.localtime(bus.charging_end_time))}")
            else:
                print(f"  → Charging station {station_id} unavailable → ignoring charge")
                bus.mip_decision = None

        elif action == "return_depot":
            bus.status = "returning_to_depot"
            bus.target = bus.depot  # Optional: help navigation
            bus.mip_decision = None

        elif action == "move":
            target_id = decision["target_node_id"]
            target_obj = S_map.get(target_id)

            if not target_obj:
                print(f"  → Target node {target_id} not found in S_map → ignoring move")
                continue

            # Case 1: Target is a regular stop on the bus's current route
            if bus.current_route and bus.current_route.stops:
                # Safely get the expected stop class
                expected_class = type(bus.current_route.stops[0]) if bus.current_route.stops else object

                if isinstance(target_obj, expected_class):
                    # Find the index of this stop in the route
                    found = False
                    for idx, stop in enumerate(bus.current_route.stops):
                        if stop and stop.stop_id == target_id:
                            bus.current_stop_index = idx
                            bus.current_location = stop.location
                            bus.status = "on_route"
                            bus.target = stop
                            found = True
                            break
                    if found:
                        bus.mip_decision = None
                        continue  # Successfully handled

            # Case 2: Target is a depot (return_depot might come as move if not caught earlier)
            if target_id.startswith("Depot_"):
                bus.status = "returning_to_depot"
                bus.target = target_obj
                bus.mip_decision = None
                continue

            # Case 3: Target is a charging station (charge might come as move to CS)
            if target_id.startswith("CS_"):
                station = station_map.get(target_id)
                if station and station.is_available(bus.company):
                    bus.mip_decision = {"action": "charge", "station_id": target_id}
                    bus.charging_station = station
                    bus.status = "heading_to_charger"
                else:
                    print(f"  → Charging station {target_id} unavailable → ignoring")
                continue

            # Fallback: unknown target
            print(f"  → Unknown or incompatible move target {target_id} → ignoring")

        else:
            print(f"  → Unknown action {action} → ignoring")

        # If we reach here, decision was not fully applied
        # bus.mip_decision remains set so bus.step() can handle it if needed