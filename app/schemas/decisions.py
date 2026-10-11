
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agents import (
    QualityAssessment,
    PricingAssessment,
    LogisticsAssessment,
)


class DecisionPlan(BaseModel):
    decision_id: str
    batch_id: str
    quality_assessment: QualityAssessment
    pricing_assessment: PricingAssessment
    logistics_assessment: LogisticsAssessment
    selected_actions: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    status: Literal["PROPOSED", "APPROVED", "EXECUTED", "FAILED"] = (
        "PROPOSED"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
