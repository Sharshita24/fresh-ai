
import json

from app.schemas.agents import (
    PricingAssessment,
    QualityAssessment,
)
from app.schemas.inventory import InventoryBatch
from app.services.gemini_agent import call_gemini_json, is_gemini_configured


def _fallback_assess_pricing(
    batch: InventoryBatch,
    quality: QualityAssessment,
) -> PricingAssessment:
    if quality.risk_level in ("HIGH", "CRITICAL"):
        markdown = 20.0
    elif quality.risk_level == "MEDIUM":
        markdown = 10.0
    else:
        markdown = 0.0

    new_price = round(
        batch.current_price * (1 - markdown / 100),
        2,
    )

    demand_multiplier = 1.5 if markdown > 0 else 1.0
    expected_velocity = (
        batch.demand_velocity_units_per_hour
        * demand_multiplier
    )

    return PricingAssessment(
        batch_id=batch.batch_id,
        recommended_markdown_percent=markdown,
        recommended_price=new_price,
        expected_clearance_units_per_hour=round(
            expected_velocity, 2
        ),
        evidence=[
            f"Quality risk: {quality.risk_level}",
            f"Current demand: "
            f"{batch.demand_velocity_units_per_hour} units/hour",
            f"Proposed markdown: {markdown}%",
            "Demand uplift is a demo assumption, not a measured result.",
        ],
    )


def assess_pricing(
    batch: InventoryBatch,
    quality: QualityAssessment,
) -> PricingAssessment:
    if is_gemini_configured():
        prompt = (
            "You are a pricing recommendation agent. "
            "Return valid JSON with keys: batch_id, recommended_markdown_percent, "
            "recommended_price, expected_clearance_units_per_hour, evidence. "
            f"Data: {json.dumps({'batch': batch.model_dump(mode='json'), 'quality': quality.model_dump(mode='json')}, default=str)}"
        )
        payload = call_gemini_json(prompt)
        if payload:
            try:
                payload["batch_id"] = payload.get("batch_id", batch.batch_id)
                return PricingAssessment.model_validate(payload)
            except Exception:
                pass

    return _fallback_assess_pricing(batch, quality)
