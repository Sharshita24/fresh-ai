
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ActionType = Literal["MARKDOWN", "TRANSFER", "B2B_OFFER", "DONATION"]


class ActionRecord(BaseModel):
    action_id: str
    decision_id: str
    batch_id: str
    action_type: ActionType
    quantity: int = Field(ge=0)
    status: Literal[
        "PENDING",
        "SUCCEEDED",
        "FAILED",
    ] = "PENDING"
    details: dict = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
