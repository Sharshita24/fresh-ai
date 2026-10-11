
from typing import Literal
from pydantic import BaseModel, Field


class QualityAssessment(BaseModel):
    agent_name: Literal["quality"] = "quality"
    batch_id: str
    estimated_remaining_shelf_life_hours: float = Field(ge=0)
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class PricingAssessment(BaseModel):
    agent_name: Literal["pricing"] = "pricing"
    batch_id: str
    recommended_markdown_percent: float = Field(ge=0, le=100)
    recommended_price: float = Field(ge=0)
    expected_clearance_units_per_hour: float = Field(ge=0)
    evidence: list[str] = Field(default_factory=list)


class LogisticsAssessment(BaseModel):
    agent_name: Literal["logistics"] = "logistics"
    batch_id: str
    recommended_action: Literal[
        "KEEP",
        "REDISTRIBUTE",
        "B2B_OFFLOAD",
        "DONATE",
    ]
    recommended_quantity: int = Field(ge=0)
    destination: str | None = None
    evidence: list[str] = Field(default_factory=list)
