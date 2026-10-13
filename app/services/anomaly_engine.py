"""Cheap rule-based checks that decide whether the AI needs to be called at all.

Thresholds come from each product's storage range, not one global number: 7 °C is an emergency for
strawberries but normal for a bakery shelf.
"""

from app.models import Product

TEMP_MARGIN_C = 2.0  # alert when temperature is this far above the storage maximum
LOW_BATTERY_PCT = 15

SEVERITY = {
    "HIGH_TEMPERATURE": 1.0,
    "HIGH_ETHYLENE": 0.8,
    "HIGH_HUMIDITY": 0.5,
    "SENSOR_LOW_BATTERY": 0.0,
}
DECISION_FLAGS = {"HIGH_TEMPERATURE", "HIGH_ETHYLENE"}


def temperature_threshold(product: Product) -> float:
    return product.storage_max_c + TEMP_MARGIN_C


def detect_anomalies(
    product: Product, temperature_c: float, humidity_percent: float, ethylene_ppm: float, battery_pct: float = 100.0
) -> list[str]:
    flags = []
    if temperature_c > temperature_threshold(product):
        flags.append("HIGH_TEMPERATURE")
    if humidity_percent > product.humidity_max:
        flags.append("HIGH_HUMIDITY")
    if ethylene_ppm > product.ethylene_max_ppm:
        flags.append("HIGH_ETHYLENE")
    if battery_pct < LOW_BATTERY_PCT:
        flags.append("SENSOR_LOW_BATTERY")
    return flags


def severity(flags: list[str]) -> float:
    return max((SEVERITY.get(f, 0.0) for f in flags), default=0.0)
