"""Analytics helpers used to test semantic retrieval.

The functions purposely contain domain-specific language ("seasonal drift", "sensor gaps")
so we can verify that similar questions surface the right chunks from the vector store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class SensorWindow:
    name: str
    readings: List[float]

    def mean(self) -> float:
        if not self.readings:
            return 0.0
        return sum(self.readings) / len(self.readings)


class TrendAnalyzer:
    """Detects seasonal drift and sensor gaps.

    This docstring is a retrieval target; questions that mention
    "seasonal drift" or "sensor gaps" should recall this text.
    """

    def __init__(self, windows: Iterable[SensorWindow]):
        self.windows = list(windows)

    def detect_drift(self, tolerance: float = 0.15) -> List[str]:
        """Return sensor names whose rolling mean moved more than tolerance."""

        baseline = self._baseline()
        flagged: List[str] = []
        for window in self.windows:
            delta = abs(window.mean() - baseline)
            if delta > tolerance:
                flagged.append(window.name)
        return flagged

    def detect_sensor_gaps(self) -> List[str]:
        """Find sensors that have no readings for more than three intervals."""

        return [window.name for window in self.windows if len(window.readings) <= 3]

    def _baseline(self) -> float:
        if not self.windows:
            return 0.0
        return sum(window.mean() for window in self.windows) / len(self.windows)
