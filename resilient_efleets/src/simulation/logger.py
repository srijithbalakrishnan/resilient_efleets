# src/simulation/logger.py
"""
Simple CSV logger for bus states over time.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List

from resilient_efleets.src.fleet.bus import Bus
from resilient_efleets.src.simulation.state import SimulationState
from resilient_efleets.src.config.paths import output_path


class SimulationLogger:
    def __init__(self, log_file: str = "simulation_log.csv"):
        self.log_path = output_path(log_file)
        self.fieldnames = [
            "timestamp",
            "sim_time",
            "bus_id",
            "status",
            "latitude",
            "longitude",
            "soc",
            "delay_seconds",
            "unserved_demand",
            "current_route",
            "current_stop_index",
            "charging_station",
            "active_disruptions"
        ]

        # Write header
        with open(self.log_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()

    def log_step(self, sim_time: float, state: SimulationState):
        disruption_desc = "; ".join(
            [f"{d.route_id}:{','.join(d.affected_stop_ids)}" for d in state.active_disruptions]
        ) or "None"

        with open(self.log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            for bus in state.buses:
                route_name = bus.current_route.name if bus.current_route else "None"
                cs_name = bus.charging_station.name if bus.charging_station else "None"
                writer.writerow({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "sim_time": datetime.fromtimestamp(sim_time).strftime("%H:%M:%S"),
                    "bus_id": bus.bus_id,
                    "status": bus.status,
                    "latitude": bus.current_location.lat,
                    "longitude": bus.current_location.lon,
                    "soc": round(bus.soc, 2),
                    "delay_seconds": round(bus.delay_seconds, 1),
                    "unserved_demand": round(bus.unserved_demand, 2),
                    "current_route": route_name,
                    "current_stop_index": bus.current_stop_index,
                    "charging_station": cs_name,
                    "active_disruptions": disruption_desc
                })