# src/simulation/engine.py
"""
Main simulation engine.
Orchestrates: hazards → optimization → decision application → bus steps → logging
"""

import time
from datetime import datetime, timedelta

from src.simulation.state import SimulationState
from src.simulation.logger import SimulationLogger
from src.hazards.manager import DisruptionManager
from src.optimization.mip_model import optimize_network
from src.optimization.decision_applier import apply_mip_decisions
from src.config.settings import SimulationSettings


class SimulationEngine:
    def __init__(self, state: SimulationState, logger: SimulationLogger = None):
        self.state = state
        self.logger = logger or SimulationLogger()
        self.state.disruption_manager = DisruptionManager()  # Add flood file later if needed

    def run(
        self,
        duration_hours: float = 2.0,
        step_seconds: int = None
    ):
        step_seconds = step_seconds or SimulationSettings.SIMULATION_STEP_SECONDS

        # Determine simulation time window from schedules
        all_start_times = []
        for bus in self.state.buses:
            for trip in bus.daily_schedule:
                all_start_times.append(trip["start_time"])

        if not all_start_times:
            print("No scheduled trips found.")
            return

        sim_start = min(all_start_times) - 300  # 5 min buffer
        sim_end = sim_start + duration_hours * 3600

        current_sim_time = sim_start
        step_count = 0

        print(f"\n{'='*60}")
        print(f"SIMULATION START: {datetime.fromtimestamp(sim_start).strftime('%Y-%m-%d %H:%M')}")
        print(f"Duration: {duration_hours} hours | Step: {step_seconds}s")
        print(f"{'='*60}\n")

        while current_sim_time < sim_end:
            step_count += 1
            print(f"\n--- Step {step_count} | Time: {datetime.fromtimestamp(current_sim_time).strftime('%H:%M:%S')} ---")

            # 1. Update hazards
            self.state.charging_stations = self.state.disruption_manager.update(
                routes=self.state.routes,
                charging_stations=self.state.charging_stations,
                current_sim_time=current_sim_time
            )
            self.state.active_disruptions = self.state.disruption_manager.get_active_disruptions()

            # 2. Centralized optimization
            mip_result = optimize_network(
                buses=self.state.buses,
                routes=self.state.routes,
                charging_stations=self.state.charging_stations,
                depots=list(self.state.depots.values()),
                active_disruptions=self.state.active_disruptions,
                current_sim_time=current_sim_time,
                interval_seconds=step_seconds
            )

            # 3. Apply MIP decisions
            apply_mip_decisions(
                buses=self.state.buses,
                mip_result=mip_result,
                charging_stations=self.state.charging_stations,
                current_sim_time=current_sim_time
            )

            # 4. Bus agent steps
            context = {
                "current_sim_time": current_sim_time,
                "stations": self.state.charging_stations,
                "disruptions": self.state.active_disruptions,
                "station_map": {f"CS_{s.name}_{i}": s for i, s in enumerate(self.state.charging_stations)}
            }

            for bus in self.state.buses:
                if bus.mip_decision:
                    # Bus will handle MIP command in its step
                    bus.step(context)
                else:
                    bus.step(context)

            # 5. Log
            self.logger.log_step(current_sim_time, self.state)

            # Advance time
            current_sim_time += step_seconds

        print(f"\n{'='*60}")
        print("SIMULATION COMPLETE")
        print(f"Log saved to: {self.logger.log_path}")
        print(f"{'='*60}")