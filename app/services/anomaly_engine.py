
from app.schemas.sensors import SensorReadingInput


# Illustrative thresholds for our demo.
# Real deployment requires product-specific validation.
TEMPERATURE_MAX_C = 7.0
HUMIDITY_MAX_PERCENT = 85.0
ETHYLENE_MAX_PPM = 1.5


def detect_anomalies(reading: SensorReadingInput) -> list[str]:
    flags = []

    if reading.temperature_c > TEMPERATURE_MAX_C:
        flags.append("HIGH_TEMPERATURE")

    if reading.humidity_percent > HUMIDITY_MAX_PERCENT:
        flags.append("HIGH_HUMIDITY")

    if reading.ethylene_ppm > ETHYLENE_MAX_PPM:
        flags.append("HIGH_ETHYLENE")

    return flags
