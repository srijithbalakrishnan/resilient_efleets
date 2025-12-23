# src/config/settings.py

from dataclasses import dataclass

@dataclass(frozen=True)
class SimulationSettings:
    # Energy and vehicle
    ENERGY_CONSUMPTION_KWH_PER_KM: float = 1.4      # Base consumption
    BATTERY_CAPACITY_KWH: float = 250.0             # Default bus battery
    CRITICAL_SOC_PERCENT: float = 22.0              # Trigger charging search
    CHARGING_MIN_TIME_SECONDS: int = 120           # Minimum charging dwell

    # Speed and time
    AVERAGE_SPEED_MPS: float = 5.0                  # 18 km/h average
    SIMULATION_STEP_SECONDS: int = 60              # Default step size

    # Disruption probabilities
    RANDOM_DISRUPTION_PROB: float = 0.05
    RANDOM_DISRUPTION_MIN_STOPS: int = 1
    RANDOM_DISRUPTION_MAX_STOPS: int = 3
    RANDOM_DISRUPTION_MIN_MINUTES: int = 5
    RANDOM_DISRUPTION_MAX_MINUTES: int = 15

    # MIP settings
    MIP_HORIZON_MINUTES: int = 5  # Reduced from 15 for faster solving
    MIP_TIME_LIMIT_SECONDS: int = 10  # Reduced from 30
    MIP_DELAY_COST_PER_SEC: float = 0.5
    MIP_UNSERVED_DEMAND_COST: float = 10.0
    MIP_BATTERY_DRAIN_PENALTY: float = 0.2

    # Logging
    LOG_FILE_NAME: str = "simulation_log.csv"


@dataclass(frozen=True)
class HybridSimulationSettings:
    """Configuration for hybrid event-driven/time-stepped simulation"""
    # Simulation mode: 'fixed_interval' or 'hybrid_adaptive'
    SIMULATION_MODE: str = "fixed_interval"
    
    # Hybrid-specific settings
    BATCH_THRESHOLD_SECONDS: float = 30.0   # Cluster events within this window
    FINE_STEP_SECONDS: int = 60             # High-resolution timestep (when active)
    COARSE_STEP_SECONDS: int = 300          # Low-resolution timestep (when quiet)
    GAP_THRESHOLD_SECONDS: float = 300.0    # Switch to coarse step if gap > this
    
    # Fixed-interval settings (legacy)
    FIXED_STEP_SECONDS: int = 60            # For SIMULATION_MODE='fixed_interval'


@dataclass(frozen=True)
class Paths:
    DATA_DIR: str = "data"  # Relative to project root
    ROUTES_CSV: str = "TVM Route.csv"
    CHARGERS_CSV: str = "Charger.csv"
    DEPOTS_CSV: str = "Depot.csv"
    SCHEDULE_CSV: str = "Consolidated_Cleaned_Bus_Schedule.csv"
    LOG_OUTPUT: str = "simulation_log.csv"
    MAP_OUTPUT: str = "network_map.html"