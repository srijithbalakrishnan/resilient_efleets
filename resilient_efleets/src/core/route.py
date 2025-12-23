# src/core/route.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from shapely.geometry import Point
from .geometry import Location

@dataclass
class Stop:
    """
    Represents a bus stop (or stage) in the network.
    """
    stop_id: str
    name: str
    location: Location
    is_stage: bool = False          # e.g., major timing point or layover
    demand: float = 1.0             # Passenger demand units (can be fractional)

    @property
    def geometry(self) -> Point:
        return self.location.geometry

    def __hash__(self) -> int:
        return hash(self.stop_id)


@dataclass
class RouteSegment:
    """
    Represents the segment between two consecutive stops on a route.
    Stores pre-computed distance (in meters) if available.
    """
    from_stop: Stop
    to_stop: Stop
    distance_meters: Optional[float] = None  # None → will be calculated on-the-fly


@dataclass
class Route:
    """
    A fixed bus route consisting of an ordered sequence of stops.
    Supports sparse stop lists (gaps with None) if needed, but we keep it clean.
    """
    route_id: str
    name: str
    stops: List[Stop] = field(default_factory=list)
    segments: List[RouteSegment] = field(default_factory=list, init=False)

    def __post_init__(self):
        self._build_segments()

    def _build_segments(self):
        """Rebuild segments whenever stops are modified."""
        self.segments = []
        for i in range(len(self.stops) - 1):
            segment = RouteSegment(
                from_stop=self.stops[i],
                to_stop=self.stops[i + 1],
                distance_meters=None  # Will be filled later if data available
            )
            self.segments.append(segment)

    def add_stop(self, stop: Stop, sequence_number: int, distance_to_previous: Optional[float] = None):
        """
        Add a stop at a specific sequence position (1-based as in original data).
        Expands the list if needed and updates distances.
        """
        target_idx = sequence_number - 1
        while len(self.stops) < sequence_number:
            self.stops.append(None)
        
        self.stops[target_idx] = stop
        
        # If this is not the first stop and we have a distance, store it on previous segment
        if target_idx > 0 and distance_to_previous is not None:
            prev_segment = RouteSegment(
                from_stop=self.stops[target_idx - 1],
                to_stop=stop,
                distance_meters=distance_to_previous
            )
            # Replace or append the segment
            if target_idx - 1 < len(self.segments):
                self.segments[target_idx - 1] = prev_segment
            else:
                self.segments.append(prev_segment)
        
        # Rebuild remaining segments to keep consistency
        self._build_segments()

    def get_distance_to_next_stop(self, current_stop_index: int) -> Optional[float]:
        """
        Return pre-loaded distance (meters) to the next stop if available.
        Index is the current position in the stops list (0 = at first stop).
        """
        if current_stop_index >= len(self.segments):
            return None
        segment = self.segments[current_stop_index]
        return segment.distance_meters

    @property
    def stop_ids(self) -> List[str]:
        return [stop.stop_id for stop in self.stops if stop is not None]

    def __len__(self) -> int:
        return len([s for s in self.stops if s is not None])

    def __str__(self) -> str:
        return f"Route {self.route_id} - {self.name} ({len(self)} stops)"