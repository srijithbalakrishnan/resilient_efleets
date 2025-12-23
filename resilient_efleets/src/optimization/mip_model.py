# src/optimization/mip_model.py

import time
from typing import List, Dict, Any
from pulp import (
    LpProblem, LpMinimize, LpVariable, lpSum, LpBinary, LpStatus, value,
    PULP_CBC_CMD, GUROBI, LpInteger
)


from geopy.distance import geodesic

from resilient_efleets.src.core.route import Route, Stop
from resilient_efleets.src.core.charging import ChargingStation
from resilient_efleets.src.core.depot import Depot
from resilient_efleets.src.fleet.bus import Bus
from resilient_efleets.src.core.disruption import DisruptionEvent
from resilient_efleets.src.config.settings import SimulationSettings


# -----------------------------
# Solver Selection (Easy Switch)
# -----------------------------
USE_GUROBI = True  # Set to False to fall back to CBC


def build_node_maps_and_feasible_edges(
    routes: List[Route],
    charging_stations: List[ChargingStation],
    depots: List[Depot],
    active_disruptions: List[DisruptionEvent]
) -> tuple:
    """
    Build nodes and feasible edges, respecting current disruptions.
    """
    S_map = {}
    C_unique_map = {}
    disrupted_stop_ids = set()
    disrupted_cs_names = set()
    disrupted_edges = set()  # (from_id, to_id)

    # Extract disruption info
    for disruption in active_disruptions:
        # Add affected stops to disrupted set
        for stop_id in disruption.affected_stop_ids:
            disrupted_stop_ids.add(stop_id)

    # Regular stops (exclude disrupted)
    for route in routes:
        for stop in route.stops:
            if stop and stop.stop_id not in S_map and stop.stop_id not in disrupted_stop_ids:
                S_map[stop.stop_id] = stop

    # Depots
    depot_ids = []
    for depot in depots:
        depot_id = f"Depot_{depot.name}"
        S_map[depot_id] = depot
        depot_ids.append(depot_id)

    # Charging stations (exclude fully disrupted)
    cs_idx = 0
    for station in charging_stations:
        if station.name in disrupted_cs_names:
            continue  # fully unavailable
        cs_id = f"CS_{station.name}_{cs_idx}"
        S_map[cs_id] = station
        C_unique_map[cs_id] = station
        cs_idx += 1

    S_ids = list(S_map.keys())
    C_ids = list(C_unique_map.keys())

    # Feasible edges (respect road blocks)
    feasible_edges = set()

    # Route consecutive stops
    for route in routes:
        for i in range(len(route.stops) - 1):
            s1 = route.stops[i].stop_id if route.stops[i] else None
            s2 = route.stops[i + 1].stop_id if route.stops[i + 1] else None
            if s1 in S_ids and s2 in S_ids and (s1, s2) not in disrupted_edges:
                feasible_edges.add((s1, s2))

    # Any non-CS node → charging station
    non_cs_nodes = [s for s in S_ids if not s.startswith("CS_")]
    for s in non_cs_nodes:
        for c in C_ids:
            feasible_edges.add((s, c))

    # Charging station → depot
    for c in C_ids:
        for d in depot_ids:
            feasible_edges.add((c, d))

    # Depot → first stop of any route
    for d in depot_ids:
        for route in routes:
            if route.stops and route.stops[0] and route.stops[0].stop_id in S_ids:
                feasible_edges.add((d, route.stops[0].stop_id))

    # Any regular stop → depot (early return)
    regular_stops = [s for s in S_ids if isinstance(S_map[s], Stop)]
    for s in regular_stops:
        for d in depot_ids:
            feasible_edges.add((s, d))

    return S_map, C_unique_map, feasible_edges, depot_ids, disrupted_stop_ids


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
    Enhanced MIP for robust rerouting and charging under disruptions.
    """
    print(f"\n--- Robust MIP Optimization at {time.strftime('%H:%M:%S', time.localtime(current_sim_time))} ---")
    print(f"Active disruptions: {len(active_disruptions)}")

    # 1. Build nodes and feasible edges with disruption awareness
    S_map, C_unique_map, feasible_edges, depot_ids, disrupted_stop_ids = build_node_maps_and_feasible_edges(
        routes, charging_stations, depots, active_disruptions
    )
    S_ids = list(S_map.keys())
    C_ids = list(C_unique_map.keys())

    if not S_ids:
        print("No valid nodes after disruptions. Skipping optimization.")
        return {"decisions": {}}

    # 2. Distance matrix: try cache first, compute once if needed
    from resilient_efleets.src.optimization.distance_cache import (
        load_cached_distances, compute_and_cache_distances
    )

    cached_dist = load_cached_distances(S_map, feasible_edges)
    if cached_dist is not None:
        dist_matrix = cached_dist
    else:
        dist_matrix = compute_and_cache_distances(S_map, feasible_edges)
    
    print(f"Using distance matrix with {len(dist_matrix)} entries")

    print(f"Model size: {len(buses)} buses, {len(S_ids)} nodes, {len(feasible_edges)} edges")

    # 3. Time horizon (minute-level discretization)
    horizon_min = SimulationSettings.MIP_HORIZON_MINUTES
    T = list(range(horizon_min + 1))  # t=0 is current minute

    # 4. Problem setup
    prob = LpProblem("Robust_Electric_Bus_Optimization", LpMinimize)

    # Variables
    x = LpVariable.dicts("x", ((b.bus_id, s, t) for b in buses for s in S_ids for t in T), cat=LpBinary)
    y = LpVariable.dicts("y", ((b.bus_id, s1, s2, t) for b in buses
                               for s1, s2 in feasible_edges for t in T if t < horizon_min), cat=LpBinary)
    charge = LpVariable.dicts("charge", ((b.bus_id, c, t) for b in buses
                                         for c in C_ids for t in T), cat=LpBinary)
    soc = LpVariable.dicts("soc", ((b.bus_id, t) for b in buses for t in T), lowBound=0, upBound=100)
    
    # Improved: binary served per stop
    served = LpVariable.dicts("served", [s for s in S_ids if isinstance(S_map[s], Stop)], cat=LpBinary)

    # 5. Objective – more robust
    unserved_cost = SimulationSettings.MIP_UNSERVED_DEMAND_COST * (2 if active_disruptions else 1)  # higher during disruption
    prob += (
        lpSum((1 - served[s]) * S_map[s].demand for s in served) * unserved_cost +
        lpSum((50 - soc[(b.bus_id, t)]) for b in buses for t in T if t >= horizon_min // 2) * SimulationSettings.MIP_BATTERY_DRAIN_PENALTY * 0.5 +
        lpSum((100 - soc[(b.bus_id, horizon_min)]) for b in buses) * SimulationSettings.MIP_BATTERY_DRAIN_PENALTY
    )

    # 6. Constraints
    for bus in buses:
        b = bus.bus_id

        # Initial position
        current_node = None
        if bus.status == "on_route" and bus.current_route and bus.current_stop_index > 0:
            prev_stop = bus.current_route.stops[bus.current_stop_index - 1]
            if prev_stop and prev_stop.stop_id in S_ids:
                current_node = prev_stop.stop_id
        elif bus.status in ["in_depot", "idle", "returning_to_depot"]:
            current_node = f"Depot_{bus.depot.name}"
        elif bus.status == "charging" and bus.charging_station:
            for cs_id, station in C_unique_map.items():
                if station == bus.charging_station:
                    current_node = cs_id
                    break

        if current_node and current_node in S_ids:
            prob += x[(b, current_node, 0)] == 1
            for s in S_ids:
                if s != current_node:
                    prob += x[(b, s, 0)] == 0
        prob += soc[(b, 0)] == bus.soc

        # Flow conservation
        for t in range(horizon_min):
            for s in S_ids:
                # Outgoing: move or charge
                outgoing = lpSum(y.get((b, s, s2, t), 0) for s2 in S_ids if (s, s2) in feasible_edges)
                charging_here = lpSum(charge[(b, c, t)] for c in C_ids if c == s)
                prob += outgoing + charging_here == x[(b, s, t)]

                # Incoming at t+1
                incoming = lpSum(y.get((b, s1, s, t), 0) for s1 in S_ids if (s1, s) in feasible_edges)
                prob += x[(b, s, t + 1)] == incoming

            # SOC dynamics
            discharge = lpSum(
                y.get((b, s1, s2, t), 0) * dist_matrix[(s1, s2)] * 0.1  # 0.1% per km
                for s1, s2 in feasible_edges
            )
            charge_gain = lpSum(
                charge[(b, c, t)] * C_unique_map[c].capacity_kw
                for c in C_ids
            ) * (60 / 3600) / (bus.battery_capacity_kwh / 100)  # per minute
            prob += soc[(b, t + 1)] == soc[(b, t)] - discharge + charge_gain

        # Prevent visiting disrupted stops
        for s in disrupted_stop_ids:
            if s in S_ids:
                prob += lpSum(x[(b, s, t)] for t in T) == 0

    # Demand serving (proper binary)
    BIG_M = 1000
    for s in served:
        visits = lpSum(x[(b.bus_id, s, t)] for b in buses for t in T)
        prob += visits <= BIG_M * served[s]
        prob += visits >= served[s]  # if served=1, at least one visit

    # Charging capacity
    for c in C_ids:
        station = C_unique_map[c]
        available = station.available_slots
        for t in T:
            prob += lpSum(charge[(bb.bus_id, c, t)] for bb in buses) <= available

    # 7. Solver selection
    if USE_GUROBI:
        try:
            solver = GUROBI(
                msg=1,                    # 1 = show solver log, 0 = silent
                timeLimit=SimulationSettings.MIP_TIME_LIMIT_SECONDS,
                gapRel=0.20,              # 20% MIP gap
                Threads=12,               # Adjust to your CPU cores
                # Optional extras:
                # MIPFocus=1,             # 1=feasibility, 2=optimality, 3=improve bound
                # Heuristics=0.1,         # Spend more time on early heuristics
                # Presolve=2,             # Aggressive presolve
                manageEnv=True            # Recommended: Properly releases license after solve
            )
            print("Using Gurobi direct interface (gurobipy)")
        except Exception as e:
            print(f"Direct Gurobi interface not available: {e}")
            print("Falling back to CBC")
            solver = PULP_CBC_CMD(
                msg=0,
                timeLimit=SimulationSettings.MIP_TIME_LIMIT_SECONDS,
                gapRel=0.20,
                threads=8
            )
    else:
        solver = PULP_CBC_CMD(
            msg=0,
            timeLimit=SimulationSettings.MIP_TIME_LIMIT_SECONDS,
            gapRel=0.20,
            threads=8
        )

    # 8. Solve
    start_time = time.time()
    prob.solve(solver)
    solve_time = time.time() - start_time

    status = LpStatus[prob.status]
    obj_val = value(prob.objective)
    obj_str = f"{obj_val:.1f}" if obj_val is not None else "n/a"
    print(f"MIP Status: {status} | Solve time: {solve_time:.2f}s | Objective: {obj_str}")

    if prob.status not in [1, -1]:  # Not Optimal or Feasible
        print("No feasible solution found.")
        return {"decisions": {}}

    # 9. Extract immediate decisions (t=0 charge or t=0→t=1 move)
    decisions = {}
    for bus in buses:
        b = bus.bus_id
        decision = None

        # Charging now?
        for c in C_ids:
            if value(charge.get((b, c, 0), 0)) == 1:
                decision = {"action": "charge", "station_id": c}
                break

        # Moving next?
        if not decision:
            for s1, s2 in feasible_edges:
                if value(y.get((b, s1, s2, 0), 0)) == 1:
                    if s2.startswith("Depot_"):
                        decision = {"action": "return_depot", "target": s2}
                    elif s2.startswith("CS_"):
                        decision = {"action": "charge", "station_id": s2}
                    else:
                        decision = {"action": "move", "target_node_id": s2}
                    break

        if decision:
            decisions[b] = decision

    return {
        "decisions": decisions,
        "S_map": S_map,
        "C_unique_map": C_unique_map,
        "status": status,
        "solve_time": solve_time
    }