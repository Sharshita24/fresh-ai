from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class QualityAssessment(BaseModel):
    agent_name: Literal["quality"] = "quality"
    batch_id: str
    estimated_remaining_shelf_life_hours: float = Field(ge=0)
    printed_remaining_hours: float
    temperature_c: float
    baseline_temperature_c: float
    temperature_factor: float
    quality_factor: float
    defect_pct: float
    vision_label: str
    anomaly_flags: list[str] = Field(default_factory=list)
    risk_score: int
    risk_level: RiskLevel
    evidence: list[str] = Field(default_factory=list)


class MarkdownOption(BaseModel):
    pct: int
    price: float
    velocity_per_h: float
    clear_hours: float | None
    sold: int
    waste: int


class PricingAssessment(BaseModel):
    agent_name: Literal["pricing"] = "pricing"
    batch_id: str
    current_velocity_per_h: float
    forecast_per_h: float | None
    footfall_ratio: float | None
    needed_per_h: float
    baseline_sold: int
    baseline_waste: int
    options: list[MarkdownOption]
    recommended_markdown_percent: int
    evidence: list[str] = Field(default_factory=list)


class TransferCandidate(BaseModel):
    store_id: str
    name: str
    kind: str
    distance_km: float
    eta_min: int
    headroom_per_h: float
    free_capacity: int
    absorbable_units: int
    transfer_cost: float
    score: float
    verdict: str


class Fallback(BaseModel):
    store_id: str
    name: str
    kind: Literal["b2b", "food_bank"]
    distance_km: float
    unit_price: float


class LogisticsAssessment(BaseModel):
    agent_name: Literal["logistics"] = "logistics"
    batch_id: str
    candidates: list[TransferCandidate]
    best: TransferCandidate | None = None
    recommended_quantity: int = 0
    b2b: Fallback | None = None
    food_bank: Fallback | None = None
    evidence: list[str] = Field(default_factory=list)
