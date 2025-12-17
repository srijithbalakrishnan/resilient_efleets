# src/optimization/decision_applier.py
"""
Safely apply MIP decisions to Bus objects.
Handles infeasible cases gracefully.
"""

from typing import Dict, List
from src.fleet.bus import Bus
from src.core.charging import ChargingStation


def apply_mip_decisions(
    buses: List[Bus],
    mip_result: Dict,
    charging_stations: List[ChargingStation],
    current_sim_time: float
) -> None:
    """
    Apply the decisions returned by optimize_network().
    """
    decisions = mip_result.get("decisions", {})
    S_map = mip_result.get("S_map", {})
    C_unique_map = mip_result.get("C_unique_map", {})

    station_map = {cs_id: station for cs_id, station in C_unique_map.items()}

    for bus in buses:
        decision = decisions.get(bus.bus_id)
        if not decision:
            continue

        print(f"MIP → {bus.bus_id}: {decision['action']} "
              f"({'target_node_id' in decision and decision['target_node_id'] or decision.get('station_id', '')})")

        action = decision["action"]

        if action == "charge":
            station_id = decision["station_id"]
            station = station_map.get(station_id)
            if station and station.is_available(bus.company):
                bus.mip_decision = decision  # Let bus.step handle it
            else:
                print(f"  → Station unavailable, ignoring charge command")

        elif action == "return_depot":
            bus.status = "returning_to_depot"
            bus.mip_decision = None

        elif action == "move":
            target_id = decision["target_node_id"]
            target_obj = S_map.get(target_id)
            if target_obj and isinstance(target_obj, type(bus.current_route.stops[0]) if bus.current_route else None):
                # Find index in current route
                for idx, stop in enumerate(bus.current_route.stops):
                    if stop and stop.stop_id == target_id:
                        bus.current_stop_index = idx
                        bus.current_location = stop.location
                        break
            bus.mip_decision = None