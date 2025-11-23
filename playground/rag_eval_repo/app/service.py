"""Facade that stitches together trend analysis and math helpers."""

from __future__ import annotations

from typing import Iterable, List

from .trend_analyzer import SensorWindow, TrendAnalyzer
from .vector_math import cosine_similarity


class ForecastService:
    """High-level API used by the tests to ensure import graph coverage."""

    def __init__(self, windows: Iterable[SensorWindow]):
        self.analyzer = TrendAnalyzer(windows)

    def risky_sensors(self, tolerance: float = 0.2) -> List[str]:
        """Return sensors that both drifted and look dissimilar."""

        drifted = set(self.analyzer.detect_drift(tolerance))
        # Compare each sensor to the baseline vector to simulate graph queries.
        baseline = [window.mean() for window in self.analyzer.windows]
        flagged: List[str] = []
        for window in self.analyzer.windows:
            similarity = cosine_similarity(window.readings, baseline[: len(window.readings)])
            if similarity < 0.5 and window.name in drifted:
                flagged.append(window.name)
        return flagged
