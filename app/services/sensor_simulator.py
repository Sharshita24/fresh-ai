
from app.schemas.sensors import SensorReadingInput


# Fixed values make the hackathon demo reproducible.
# These are illustrative demo thresholds and readings,
# not validated food-safety limits.
SCENARIOS = {
    "NORMAL": {
        "temperature_c": 4.0,
        "humidity_percent": 65.0,
        "ethylene_ppm": 0.8,
    },
    "TEMPERATURE_SPIKE": {
        "temperature_c": 9.5,
        "humidity_percent": 65.0,
        "ethylene_ppm": 0.8,
    },
    "HUMIDITY_SPIKE": {
        "temperature_c": 4.0,
        "humidity_percent": 92.0,
        "ethylene_ppm": 0.8,
    },
    "ETHYLENE_SPIKE": {
        "temperature_c": 4.0,
        "humidity_percent": 65.0,
        "ethylene_ppm": 2.5,
    },
}


def simulate_reading(batch_id: str, scenario: str) -> SensorReadingInput:
    values = SCENARIOS.get(scenario)

    if values is None:
        raise ValueError(f"Unknown scenario: {scenario}")

    return SensorReadingInput(
        batch_id=batch_id,
        **values,
    )
