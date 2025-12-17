# src/optimization/mip_model.py
"""
Centralized MIP model for electric bus fleet optimization.
Runs every simulation step with a 15-minute rolling horizon.
Decides: charging, rerouting (skip stops), return to depot.
"""

import time
from typing import List, Dict, Any
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpBinary, LpStatus, value, PULP_CBC_CMD

from src.core.route import Route, Stop
from src.core.charging import ChargingStation
from src.core.depot import Depot
from src.fleet.bus import Bus
from src.core.disruption import DisruptionEvent
from src.config.settings import SimulationSettings


def build_node_maps(
    routes: List[Route],
    charging_stations: List[ChargingStation],
    depots: List[Depot]
) -> tuple:
    """
    Create unique node IDs for MIP.
    Returns: S_map (node_id → object), C_unique_map (cs_id → station)
    """
    S_map = {}
    node_counter = 0

    # Regular stops
    for route in routes:
        for stop in route.stops:
            if stop and stop.stop_id not in S_map:
                S_map[stop.stop_id] = stop

    # Depots
    for depot in depots:
        depot_id = f"Depot_{depot.name}"
        S_map[depot_id] = depot

    # Charging stations (unique IDs because names may repeat)
    C_unique_map = {}
    for i, station in enumerate(charging_stations):
        cs_id = f"CS_{station.name}_{i}"
        S_map[cs_id] = station
        C_unique_map[cs_id] = station

    return S_map, C_unique_map


def optimize_network(
    buses: List[Bus],
    routes: List[Route],
    charging_stations: List[ChargingStation],
    depots: List[Depot],
    active_disruptions: List[DisruptionEvent],
    current_sim_time: float,
    interval_seconds: int
) -> Dict[str, Any]:
    """
    Main function called every simulation step.
    Returns a dictionary of decisions for each bus.
    """
    print(f"\n--- MIP Optimization at {time.strftime('%H:%M:%S', time.localtime(current_sim_time))} ---")

    # 1. Build node maps
    S_map, C_unique_map = build_node_maps(routes, charging_stations, depots)
    S_ids = list(S_map.keys())
    C_ids = list(C_unique_map.keys())

    # 2. Planning horizon (minutes → discrete steps)
    horizon_min = SimulationSettings.MIP_HORIZON_MINUTES
    T = list(range(horizon_min + 1))  # t=0 is now

    # 3. Problem setup
    prob = LpProblem("Electric_Bus_Optimization", LpMinimize)

    # Decision variables
    x = LpVariable.dicts("x", (b.bus_id, S_ids, T), cat=LpBinary)  # bus b at node s at time t
    y = LpVariable.dicts("y", ((b.bus_id, s1, s2, t) for b in buses
                               for s1 in S_ids for s2 in S_ids for t in T), cat=LpBinary)
    charge = LpVariable.dicts("charge", (b.bus_id, C_ids, T), cat=LpBinary)
    soc = LpVariable.dicts("soc", (b.bus_id, T), lowBound=0, upBound=100)
    unserved = LpVariable.dicts("unserved", S_ids, lowBound=0)

    # 4. Objective
    prob += (
        lpSum(unserved[s] for s in unserved) * SimulationSettings.MIP_UNSERVED_DEMAND_COST +
        lpSum((100 - soc[b.bus_id][horizon_min]) for b in buses) * SimulationSettings.MIP_BATTERY_DRAIN_PENALTY
    )

    BIG_M = 1e6
    AVG_SPEED_MPS = 5.0

    # 5. Constraints for each bus
    for bus in buses:
        b = bus.bus_id

        # Initial state
        current_node = None
        if bus.status == "on_route" and bus.current_route and bus.current_stop_index > 0:
            current_node = bus.current_route.stops[bus.current_stop_index - 1].stop_id
        elif bus.status in ["in_depot", "idle", "returning_to_depot"]:
            current_node = f"Depot_{bus.depot.name}"
        elif bus.status == "charging" and bus.charging_station:
            idx = next(i for i, s in enumerate(charging_stations) if s == bus.charging_station)
            current_node = f"CS_{bus.charging_station.name}_{idx}"

        if current_node and current_node in S_ids:
            prob += x[b][current_node][0] == 1
            for s in S_ids:
                if s != current_node:
                    prob += x[b][s][0] == 0
        prob += soc[b][0] == bus.soc

        # Flow conservation and movement
        for t in range(horizon_min):
            for s in S_ids:
                # Outgoing: move or charge
                outgoing = lpSum(y[(b, s, s2, t+1)] for s2 in S_ids if (b, s, s2, t+1) in y)
                charging = lpSum(charge[b][c][t] for c in C_ids if s == c)
                prob += outgoing + charging == x[b][s][t]

                # Incoming defines location at t+1
                incoming = lpSum(y[(b, s1, s, t+1)] for s1 in S_ids if (b, s1, s, t+1) in y)
                prob += x[b][s][t+1] == incoming

            # SOC dynamics
            discharge = lpSum(
                y[(b, s1, s2, t+1)] *
                geodesic(S_map[s1].geometry.coords[0][::-1],
                         S_map[s2].geometry.coords[0][::-1]).meters / 1000 * 0.1
                for s1 in S_ids for s2 in S_ids
                if (b, s1, s2, t+1) in y
            )
            charge_kw = lpSum(charge[b][c][t] * C_unique_map[c].capacity_kw
                              for c in C_ids)
            charge_percent = charge_kw * (interval_seconds / 3600) / (bus.battery_capacity_kwh / 100)
            prob += soc[b][t+1] == soc[b][t] - discharge + charge_percent

        # Unserved demand
        for s in S_ids:
            if isinstance(S_map[s], Stop) and S_map[s].demand > 0:
                visits = lpSum(x[b][s][t] for t in T)
                prob += unserved[s] >= S_map[s].demand - BIG_M * visits

        # Charging capacity
        for c in C_ids:
            for t in T:
                prob += lpSum(charge[bb][c][t] for bb in buses) <= C_unique_map[c].available_slots

    # 6. Solve
    solver = PULP_CBC_CMD(msg=0, timeLimit=SimulationSettings.MIP_TIME_LIMIT_SECONDS)
    prob.solve(solver)

    status = LpStatus[prob.status]
    print(f"MIP Status: {status}")

    if prob.status not in [1, -1]:  # Not Optimal or Feasible
        print("No feasible solution found. Falling back to ABM.")
        return {"decisions": {}}

    # 7. Extract decisions (only first action at t=1)
    decisions = {}
    for bus in buses:
        b = bus.bus_id
        decision = None

        # Charging?
        for c in C_ids:
            if c in charge[b] and value(charge[b][c][0]) == 1:
                decision = {"action": "charge", "station_id": c}
                break

        # Movement?
        if not decision:
            for s1 in S_ids:
                for s2 in S_ids:
                    key = (b, s1, s2, 1)
                    if key in y and value(y[key]) == 1:
                        target_node = S_map[s2]
                        if s2.startswith("Depot_"):
                            decision = {"action": "return_depot", "target": s2}
                        elif s2.startswith("CS_"):
                            decision = {"action": "charge", "station_id": s2}
                        else:
                            decision = {"action": "move", "target_node_id": s2}
                        break
                if decision:
                    break

        if decision:
            decisions[b] = decision

    return {"decisions": decisions, "S_map": S_map, "C_unique_map": C_unique_map}