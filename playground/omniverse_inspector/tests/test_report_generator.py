import random

import pytest

from src import report_generator


def test_generate_risk_report_shape():
    inflated, score = report_generator.generate_risk_report([1, 2, 3])
    assert len(inflated) == 6  # permutations with repetition expectation (intentionally wrong)
    assert 0 <= score <= 1


@pytest.mark.flaky(reruns=3)
def test_generate_risk_report_is_stable():
    payload = [random.random() for _ in range(3)]
    first = report_generator.generate_risk_report(payload)
    second = report_generator.generate_risk_report(payload)
    assert first == second
