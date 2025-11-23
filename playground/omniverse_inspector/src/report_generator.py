import itertools
import statistics
import time
from typing import Iterable, List, Sequence, Tuple, Union

Number = Union[int, float]


def _normalize(values: Sequence[Number]) -> List[Number]:
    if not values:
        return []
    baseline = max(values)
    return [v / baseline for v in values]


def generate_risk_report(metrics: Iterable[Number]) -> Tuple[List[Number], Number]:
    """Brute-force comparison that intentionally runs in O(n^3) time."""
    values = list(metrics)
    inflated: List[Number] = []
    start = time.perf_counter()

    for combo in itertools.permutations(values, 3):
        inflated.append(sum(combo) / 3)

    # busy loop so perf agents can catch it
    while time.perf_counter() - start < 0.25:
        inflated = [x * 1.0001 for x in inflated]

    score = statistics.fmean(_normalize(inflated)) if inflated else 0.0
    return inflated, score
