# src/simulation/engine.py
"""
Main simulation engine.
Orchestrates: hazards → optimization → decision application → bus steps → logging
"""

import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from resilient_efleets.src.simulation.state import SimulationState
from resilient_efleets.src.simulation.logger import SimulationLogger
from resilient_efleets.src.simulation.event_queue import HybridSimulationScheduler, SimulationEvent, EventType
from resilient_efleets.src.hazards.manager import DisruptionManager
from resilient_efleets.src.optimization.mip_model import optimize_network
from resilient_efleets.src.optimization.decision_applier import apply_mip_decisions
from resilient_efleets.src.config.settings import SimulationSettings, HybridSimulationSettings


class SimulationEngine:
    def __init__(self, state: SimulationState, logger: SimulationLogger = None):
        self.state = state
        self.logger = logger or SimulationLogger()
        self.state.disruption_manager = DisruptionManager()  # Add flood file later if needed
        self.mip_interval_steps = 10  # Run MIP every 10 steps for better performance (for fixed interval mode)
        self.parallel_bus_workers = 8  # Use 8 cores for parallel bus steps (reduced to avoid overhead)
        self.use_mip = True  # Enable MIP optimization for coordinated fleet decisions
        
        # Simulation mode: 'fixed_interval' or 'hybrid_adaptive'
        self.simulation_mode = HybridSimulationSettings.SIMULATION_MODE
        self.hybrid_scheduler: Optional[HybridSimulationScheduler] = None

    def _build_event_list(self) -> list:
        """Extract all scheduled events from bus schedules"""
        events = []
        for bus in self.state.buses:
            for trip_idx, trip in enumerate(bus.daily_schedule):
                # Trip start event
                events.append(SimulationEvent(
                    time=trip['start_time'],
                    event_type=EventType.TRIP_START,
                    bus_id=bus.bus_id,
                    data={'trip_idx': trip_idx, 'trip': trip}
                ))
                # Trip end event
                events.append(SimulationEvent(
                    time=trip['end_time'],
                    event_type=EventType.TRIP_END,
                    bus_id=bus.bus_id,
                    data={'trip_idx': trip_idx, 'trip': trip}
                ))
        
        # Sort by time
        events.sort(key=lambda e: e.time)
        return events

    def _run_fixed_interval(self, sim_start: float, sim_end: float, step_seconds: int):
        """Run simulation with fixed timesteps (original approach)"""
        current_sim_time = sim_start
        step_count = 0

        print(f"\n{'='*60}")
        print(f"SIMULATION MODE: FIXED INTERVAL ({step_seconds}s steps)")
        print(f"SIMULATION START: {datetime.fromtimestamp(sim_start).strftime('%Y-%m-%d %H:%M')}")
        print(f"Duration: {(sim_end - sim_start) / 3600:.1f} hours")
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

            # 2. Centralized optimization (run periodically for performance)
            if self.use_mip and step_count % self.mip_interval_steps == 1:
                print(f"[MIP] Running optimization at step {step_count}...")
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
            else:
                if self.use_mip:
                    print(f"[MIP] Skipping optimization (using previous decisions)...")
                else:
                    print(f"[MIP] DISABLED - buses using autonomous agent behavior")

            # 4. Bus agent steps (PARALLELIZED)
            context = {
                "current_sim_time": current_sim_time,
                "stations": self.state.charging_stations,
                "disruptions": self.state.active_disruptions,
                "station_map": {f"CS_{s.name}_{i}": s for i, s in enumerate(self.state.charging_stations)}
            }

            with ThreadPoolExecutor(max_workers=self.parallel_bus_workers) as executor:
                futures = [executor.submit(bus.step, context) for bus in self.state.buses]
                for future in as_completed(futures):
                    future.result()

            # 5. Log
            self.logger.log_step(current_sim_time, self.state)

            # Advance time
            current_sim_time += step_seconds

        print(f"\n{'='*60}")
        print("SIMULATION COMPLETE")
        print(f"Log saved to: {self.logger.log_path}")
        print(f"{'='*60}")

    def _run_hybrid_adaptive(self, sim_start: float, sim_end: float):
        """Run simulation with hybrid event-driven + adaptive timesteps"""
        # Build scheduler
        self.hybrid_scheduler = HybridSimulationScheduler(
            batch_threshold=HybridSimulationSettings.BATCH_THRESHOLD_SECONDS,
            fine_step=HybridSimulationSettings.FINE_STEP_SECONDS,
            coarse_step=HybridSimulationSettings.COARSE_STEP_SECONDS,
            gap_threshold=HybridSimulationSettings.GAP_THRESHOLD_SECONDS,
        )

        # Extract and prepare events
        events = self._build_event_list()
        self.hybrid_scheduler.init_events(events, sim_start, sim_end)
        
        # Log statistics
        stats = self.hybrid_scheduler.stats()
        print(f"\n{'='*60}")
        print(f"SIMULATION MODE: HYBRID ADAPTIVE (Event-Driven + Time-Stepped)")
        print(f"SIMULATION START: {datetime.fromtimestamp(sim_start).strftime('%Y-%m-%d %H:%M')}")
        print(f"Duration: {(sim_end - sim_start) / 3600:.1f} hours")
        print(f"\nSchedule Statistics:")
        print(f"  Total steps: {stats['total_steps']}")
        print(f"  Batch events: {stats['batches']}")
        print(f"  Fine steps (60s): {stats['fine_steps']}")
        print(f"  Coarse steps (300s): {stats['coarse_steps']}")
        print(f"  Batch threshold: {stats['batch_threshold']}s")
        print(f"{'='*60}\n")

        step_count = 0
        mip_call_count = 0

        # Main simulation loop
        while True:
            current_sim_time, step_type = self.hybrid_scheduler.next_step()
            
            if current_sim_time is None:
                break

            step_count += 1
            print(f"--- Step {step_count:4d} | Time: {datetime.fromtimestamp(current_sim_time).strftime('%H:%M:%S')} | Type: {step_type:12s} ---")

            # 1. Update hazards
            self.state.charging_stations = self.state.disruption_manager.update(
                routes=self.state.routes,
                charging_stations=self.state.charging_stations,
                current_sim_time=current_sim_time
            )
            self.state.active_disruptions = self.state.disruption_manager.get_active_disruptions()

            # 2. Run MIP only on batch events
            if step_type == "batch":
                mip_call_count += 1
                print(f"  [MIP] Running optimization (batch #{mip_call_count}) with {len(self.hybrid_scheduler.current_batch)} events...")
                
                mip_result = optimize_network(
                    buses=self.state.buses,
                    routes=self.state.routes,
                    charging_stations=self.state.charging_stations,
                    depots=list(self.state.depots.values()),
                    active_disruptions=self.state.active_disruptions,
                    current_sim_time=current_sim_time,
                    interval_seconds=HybridSimulationSettings.FINE_STEP_SECONDS  # Use fine step as interval
                )

                apply_mip_decisions(
                    buses=self.state.buses,
                    mip_result=mip_result,
                    charging_stations=self.state.charging_stations,
                    current_sim_time=current_sim_time
                )
            else:
                print(f"  [MIP] Skipping optimization (using previous decisions)...")

            # 3. Bus agent steps
            context = {
                "current_sim_time": current_sim_time,
                "stations": self.state.charging_stations,
                "disruptions": self.state.active_disruptions,
                "station_map": {f"CS_{s.name}_{i}": s for i, s in enumerate(self.state.charging_stations)}
            }

            with ThreadPoolExecutor(max_workers=self.parallel_bus_workers) as executor:
                futures = [executor.submit(bus.step, context) for bus in self.state.buses]
                for future in as_completed(futures):
                    future.result()

            # 4. Log
            self.logger.log_step(current_sim_time, self.state)

        print(f"\n{'='*60}")
        print("SIMULATION COMPLETE")
        print(f"Total steps: {step_count}")
        print(f"MIP calls: {mip_call_count}")
        print(f"Log saved to: {self.logger.log_path}")
        print(f"{'='*60}")

    def run(
        self,
        duration_hours: float = 2.0,
        step_seconds: int = None,
        mode: str = None
    ):
        """
        Run simulation with selected temporal model.
        
        Args:
            duration_hours: Total simulation duration
            step_seconds: Timestep size for fixed_interval mode (uses config default if None)
            mode: 'fixed_interval' or 'hybrid_adaptive' (uses config if None)
        """
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

        # Use provided parameters or fall back to config
        simulation_mode = mode or HybridSimulationSettings.SIMULATION_MODE
        fixed_step = step_seconds or HybridSimulationSettings.FIXED_STEP_SECONDS

        # Run appropriate simulation mode
        if simulation_mode == "hybrid_adaptive":
            self._run_hybrid_adaptive(sim_start, sim_end)
        else:  # default to fixed_interval
            self._run_fixed_interval(sim_start, sim_end, fixed_step)