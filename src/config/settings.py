# src/config/settings.py

from dataclasses import dataclass

@dataclass(frozen=True)
class SimulationSettings:
    # Energy and vehicle
    ENERGY_CONSUMPTION_KWH_PER_KM: float = 0.1      # Base consumption
    BATTERY_CAPACITY_KWH: float = 100.0             # Default bus battery
    CRITICAL_SOC_PERCENT: float = 15.0             # Trigger charging search
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
    MIP_HORIZON_MINUTES: int = 15
    MIP_TIME_LIMIT_SECONDS: int = 30
    MIP_DELAY_COST_PER_SEC: float = 0.5
    MIP_UNSERVED_DEMAND_COST: float = 10.0
    MIP_BATTERY_DRAIN_PENALTY: float = 0.2

    # Logging
    LOG_FILE_NAME: str = "simulation_log.csv"


@dataclass(frozen=True)
class Paths:
    DATA_DIR: str = "data"  # Relative to project root
    ROUTES_CSV: str = "TVM Route.csv"
    CHARGERS_CSV: str = "Charger.csv"
    DEPOTS_CSV: str = "Depot.csv"
    SCHEDULE_CSV: str = "Consolidated_Cleaned_Bus_Schedule.csv"
    LOG_OUTPUT: str = "simulation_log.csv"
    MAP_OUTPUT: str = "network_map.html"