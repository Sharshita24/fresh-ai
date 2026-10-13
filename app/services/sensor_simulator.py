"""Simulated IoT feed. Readings are relative to each product's storage range, so scenarios stay realistic."""

from app.models import Product
from app.services.anomaly_engine import TEMP_MARGIN_C

SCENARIOS = ("NORMAL", "TEMPERATURE_SPIKE", "HUMIDITY_SPIKE", "ETHYLENE_SPIKE")


def scenario_reading(product: Product, baseline_c: float, scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    reading = {"temperature_c": baseline_c, "humidity_percent": min(product.humidity_max - 4, 91.0), "ethylene_ppm": 0.4}
    if scenario == "TEMPERATURE_SPIKE":
        reading["temperature_c"] = round(product.storage_max_c + TEMP_MARGIN_C + 0.2, 1)
    elif scenario == "HUMIDITY_SPIKE":
        reading["humidity_percent"] = min(100.0, product.humidity_max + 3)
    elif scenario == "ETHYLENE_SPIKE":
        reading["ethylene_ppm"] = round(product.ethylene_max_ppm + 1.0, 1)
    return reading


def temperature_ramp(start_c: float, peak_c: float, steps: int = 7) -> list[float]:
    """A chiller warming up over a few minutes, e.g. 4.0 → 7.2 °C."""
    return [round(start_c + (peak_c - start_c) * (i + 1) / steps, 1) for i in range(steps)]
