# src/hazards/random_disruption.py
"""
Random disruption generation (e.g., traffic incidents, road works).
"""

import random
from datetime import datetime
from typing import List, Optional

from src.core.route import Route
from src.core.disruption import DisruptionEvent
from src.config.settings import SimulationSettings


def generate_random_disruption(
    routes: List[Route],
    current_sim_time: float,
    probability: float = None
) -> Optional[DisruptionEvent]:
    """
    Randomly generate a disruption on one route with given probability.
    Returns None if no disruption occurs this step.
    """
    if probability is None:
        probability = SimulationSettings.RANDOM_DISRUPTION_PROB

    if random.random() > probability:
        return None

    # Choose a random route with at least one stop
    valid_routes = [r for r in routes if len(r.stops) > 0]
    if not valid_routes:
        return None

    route = random.choice(valid_routes)

    # Choose how many consecutive stops are affected
    max_affected = min(
        SimulationSettings.RANDOM_DISRUPTION_MAX_STOPS,
        len(route.stops)
    )
    num_affected = random.randint(
        SimulationSettings.RANDOM_DISRUPTION_MIN_STOPS,
        max_affected
    )

    # Pick a random starting point
    start_idx = random.randint(0, len(route.stops) - num_affected)
    affected_stops = route.stops[start_idx:start_idx + num_affected]
    affected_ids = [stop.stop_id for stop in affected_stops if stop]

    if not affected_ids:
        return None

    # Duration in seconds
    duration_minutes = random.randint(
        SimulationSettings.RANDOM_DISRUPTION_MIN_MINUTES,
        SimulationSettings.RANDOM_DISRUPTION_MAX_MINUTES
    )
    duration_seconds = duration_minutes * 60

    disruption = DisruptionEvent(
        route_id=route.route_id,
        affected_stop_ids=affected_ids,
        start_time=current_sim_time,
        end_time=current_sim_time + duration_seconds,
        description=f"Random incident on {route.name} affecting {num_affected} stops"
    )

    print(f"[{datetime.fromtimestamp(current_sim_time).strftime('%H:%M:%S')}] "
          f"RANDOM DISRUPTION: {route.name} stops {affected_ids} for {duration_minutes} min")

    return disruption