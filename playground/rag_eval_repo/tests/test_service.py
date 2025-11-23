from app.service import ForecastService
from app.trend_analyzer import SensorWindow


def test_risky_sensors_detects_low_similarity():
    windows = [
        SensorWindow(name="alpha", readings=[1.0, 1.1, 1.2, 1.3]),
        SensorWindow(name="bravo", readings=[5.0, 5.1, 5.4, 5.8]),
        SensorWindow(name="charlie", readings=[0.9, 0.91, 0.92, 0.94]),
    ]
    service = ForecastService(windows)
    risky = service.risky_sensors(tolerance=0.3)
    assert "bravo" in risky
