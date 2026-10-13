"""Request bodies. Responses are shaped in app/presenters.py (camelCase, ready for the dashboard)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SensorReadingIn(BaseModel):
    batch_id: str
    temperature_c: float = Field(ge=-30, le=60)
    humidity_percent: float = Field(default=90.0, ge=0, le=100)
    ethylene_ppm: float = Field(default=0.4, ge=0)
    battery_pct: float = Field(default=100.0, ge=0, le=100)
    recorded_at: datetime | None = None


class SensorSimulationRequest(BaseModel):
    batch_id: str
    scenario: Literal["NORMAL", "TEMPERATURE_SPIKE", "HUMIDITY_SPIKE", "ETHYLENE_SPIKE"] = "NORMAL"


class SaleIn(BaseModel):
    batch_id: str
    quantity: int = Field(gt=0)
    unit_price: float | None = Field(default=None, gt=0)


class FootfallIn(BaseModel):
    store_id: str = "store-042"
    count: int = Field(ge=0)
    hour_start: datetime | None = None


class BatchRef(BaseModel):
    batch_id: str = "STB-042"


class DemoIncidentIn(BaseModel):
    batch_id: str = "STB-042"
    peak_c: float | None = Field(default=None, description="Peak temperature; defaults to 0.2 °C past the alert rule")
