
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field
from pydantic import BaseModel, ConfigDict, Field


Scenario = Literal[
    "NORMAL",
    "TEMPERATURE_SPIKE",
    "HUMIDITY_SPIKE",
    "ETHYLENE_SPIKE",
]


class SensorSimulationRequest(BaseModel):
    batch_id: str
    scenario: Scenario = "NORMAL"


class SensorReadingInput(BaseModel):
    batch_id: str
    temperature_c: float
    humidity_percent: float = Field(ge=0, le=100)
    ethylene_ppm: float = Field(ge=0)


class SensorReading(SensorReadingInput):
    reading_id: str
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    anomaly_flags: list[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
