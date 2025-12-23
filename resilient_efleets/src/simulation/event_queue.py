"""
Event Queue for hybrid event-driven simulation.
Supports batching of nearby events and adaptive timestep scheduling.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import heapq
from datetime import datetime


class EventType(Enum):
    """Types of events in the simulation"""
    TRIP_START = "trip_start"
    TRIP_END = "trip_end"
    CHARGING_END = "charging_end"
    DISRUPTION_START = "disruption_start"
    DISRUPTION_END = "disruption_end"


@dataclass
class SimulationEvent:
    """Represents a discrete event in the simulation"""
    time: float  # epoch timestamp
    event_type: EventType
    bus_id: str
    data: dict = field(default_factory=dict)  # Extra context (trip, station, etc.)

    def __lt__(self, other: "SimulationEvent") -> bool:
        """For heap ordering (min-heap by time)"""
        if self.time != other.time:
            return self.time < other.time
        # Tiebreaker: sort by bus_id for determinism
        return self.bus_id < other.bus_id

    def __repr__(self) -> str:
        return f"Event(t={self.time}, type={self.event_type.value}, bus={self.bus_id})"


class EventQueue:
    """
    Priority queue of simulation events with batch clustering support.
    
    Usage:
        queue = EventQueue(batch_threshold=30)
        queue.add_event(SimulationEvent(...))
        batch = queue.get_next_batch()  # Events within 30s
    """

    def __init__(self, batch_threshold_seconds: float = 30.0):
        """
        Args:
            batch_threshold_seconds: Time window for clustering events
        """
        self.queue: List[SimulationEvent] = []  # min-heap
        self.batch_threshold = batch_threshold_seconds

    def add_event(self, event: SimulationEvent) -> None:
        """Add an event to the queue"""
        heapq.heappush(self.queue, event)

    def add_events(self, events: List[SimulationEvent]) -> None:
        """Add multiple events to the queue"""
        for event in events:
            self.add_event(event)

    def get_next_batch(self) -> List[SimulationEvent]:
        """
        Extract events that occur within batch_threshold of the first event.
        
        Returns:
            List of events (min 1, max depends on clustering)
        """
        if not self.queue:
            return []

        first_event = heapq.heappop(self.queue)
        batch = [first_event]
        batch_end_time = first_event.time + self.batch_threshold

        # Cluster all events within threshold
        while self.queue and self.queue[0].time <= batch_end_time:
            batch.append(heapq.heappop(self.queue))

        return batch

    def peek_next_time(self) -> Optional[float]:
        """Get time of next event without removing it"""
        if self.queue:
            return self.queue[0].time
        return None

    def peek_next_event(self) -> Optional[SimulationEvent]:
        """Peek at the next event without removing it"""
        if self.queue:
            return self.queue[0]
        return None

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return len(self.queue) == 0

    def size(self) -> int:
        """Number of events in queue"""
        return len(self.queue)

    def clear(self) -> None:
        """Clear all events"""
        self.queue.clear()

    def __repr__(self) -> str:
        return f"EventQueue(size={len(self.queue)}, batch_threshold={self.batch_threshold}s)"


class HybridSimulationScheduler:
    """
    Adaptive scheduler that mixes event-driven and time-stepped simulation.
    
    Strategy:
    1. Process batches of events (clustered within batch_threshold)
    2. Between event clusters, use adaptive timesteps:
       - Fine step (60s) if next event is within gap_threshold
       - Coarse step (300s) if gap is larger
    
    Usage:
        scheduler = HybridSimulationScheduler(config=HybridSimulationConfig(...))
        scheduler.init_events(events, sim_start, sim_end)
        for step_time, step_type in scheduler.get_steps():
            if step_type == 'batch':
                batch = scheduler.current_batch
                # Run MIP and process events
            elif step_type == 'fine_step':
                # Advance 60s
            else:  # coarse_step
                # Advance 300s
    """

    def __init__(
        self,
        batch_threshold: float = 30.0,
        fine_step: int = 60,
        coarse_step: int = 300,
        gap_threshold: float = 300.0,
    ):
        """
        Args:
            batch_threshold: Cluster events within this window (seconds)
            fine_step: Timestep when events are near (seconds)
            coarse_step: Timestep during quiet periods (seconds)
            gap_threshold: Use coarse step if gap > this (seconds)
        """
        self.batch_threshold = batch_threshold
        self.fine_step = fine_step
        self.coarse_step = coarse_step
        self.gap_threshold = gap_threshold

        self.event_queue = EventQueue(batch_threshold)
        self.schedule: List[Tuple[float, str, List[SimulationEvent]]] = []
        self.schedule_index = 0
        self.current_batch: List[SimulationEvent] = []

    def init_events(
        self,
        events: List[SimulationEvent],
        sim_start: float,
        sim_end: float,
    ) -> None:
        """
        Initialize the scheduler with events and build the full schedule.
        
        Args:
            events: List of SimulationEvent objects (should be sorted by time)
            sim_start: Simulation start time
            sim_end: Simulation end time
        """
        self.event_queue.clear()
        self.event_queue.add_events(events)
        self.schedule.clear()
        self.schedule_index = 0

        current_time = sim_start

        while current_time < sim_end and not self.event_queue.is_empty():
            next_event_time = self.event_queue.peek_next_time()

            if next_event_time <= current_time + 1:
                # Process batch of events at current time
                batch = self.event_queue.get_next_batch()
                batch_time = batch[-1].time
                self.schedule.append((batch_time, "batch", batch))
                current_time = batch_time
            else:
                # Decide timestep size based on gap
                gap = next_event_time - current_time
                if gap > self.gap_threshold:
                    step = self.coarse_step
                    step_type = "coarse_step"
                else:
                    step = self.fine_step
                    step_type = "fine_step"

                next_time = min(current_time + step, next_event_time, sim_end)
                self.schedule.append((next_time, step_type, []))
                current_time = next_time

        # Finish remaining time with coarse steps
        while current_time < sim_end:
            next_time = min(current_time + self.coarse_step, sim_end)
            self.schedule.append((next_time, "coarse_step", []))
            current_time = next_time

    def get_steps(self) -> List[Tuple[float, str]]:
        """
        Get list of (time, step_type) for all steps in schedule.
        
        Returns:
            List of (simulation_time, step_type) tuples
        """
        return [(t, st) for t, st, _ in self.schedule]

    def next_step(self) -> Tuple[Optional[float], Optional[str]]:
        """
        Get next step time and type. Returns None, None if schedule exhausted.
        """
        if self.schedule_index >= len(self.schedule):
            return None, None

        step_time, step_type, batch = self.schedule[self.schedule_index]
        self.current_batch = batch
        self.schedule_index += 1

        return step_time, step_type

    def reset(self) -> None:
        """Reset schedule iterator to beginning"""
        self.schedule_index = 0
        self.current_batch = []

    def stats(self) -> dict:
        """Return statistics about the generated schedule"""
        if not self.schedule:
            return {"steps": 0, "batches": 0, "fine_steps": 0, "coarse_steps": 0}

        batch_count = sum(1 for _, st, _ in self.schedule if st == "batch")
        fine_count = sum(1 for _, st, _ in self.schedule if st == "fine_step")
        coarse_count = sum(1 for _, st, _ in self.schedule if st == "coarse_step")

        return {
            "total_steps": len(self.schedule),
            "batches": batch_count,
            "fine_steps": fine_count,
            "coarse_steps": coarse_count,
            "batch_threshold": self.batch_threshold,
            "fine_step_size": self.fine_step,
            "coarse_step_size": self.coarse_step,
        }

    def __repr__(self) -> str:
        return f"HybridScheduler(scheduled_steps={len(self.schedule)}, index={self.schedule_index})"
