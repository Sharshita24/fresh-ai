
from uuid import uuid4

from app.agents.quality_agent import assess_quality
from app.agents.pricing_agent import assess_pricing
from app.agents.logistics_agent import assess_logistics
from app.schemas.decisions import DecisionPlan
from app.schemas.inventory import InventoryBatch
from app.schemas.sensors import SensorReading


def create_decision(
    batch: InventoryBatch,
    reading: SensorReading,
) -> DecisionPlan:
    quality = assess_quality(batch, reading)

    pricing = assess_pricing(batch, quality)

    logistics = assess_logistics(
        batch,
        quality,
        pricing,
    )

    selected_actions = []

    if pricing.recommended_markdown_percent > 0:
        selected_actions.append("MARKDOWN")

    if logistics.recommended_action != "KEEP":
        selected_actions.append(
            logistics.recommended_action
        )

    if not selected_actions:
        selected_actions.append("KEEP")

    evidence_summary = [
        f"Quality risk is {quality.risk_level}.",
        (
            f"Pricing recommends a "
            f"{pricing.recommended_markdown_percent}% markdown."
        ),
        (
            f"Logistics recommends "
            f"{logistics.recommended_action}."
        ),
    ]

    return DecisionPlan(
        decision_id=str(uuid4()),
        batch_id=batch.batch_id,
        quality_assessment=quality,
        pricing_assessment=pricing,
        logistics_assessment=logistics,
        selected_actions=selected_actions,
        evidence_summary=evidence_summary,
        status="PROPOSED",
    )
