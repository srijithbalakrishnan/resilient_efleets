# src/core/disruption.py
from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class DisruptionEvent:
    route_id: str
    affected_stop_ids: List[str]
    start_time: float  # epoch
    end_time: float    # epoch
    description: str = ""

    def is_active(self, current_time: float) -> bool:
        return self.start_time <= current_time <= self.end_time