import json

from app.schemas.agents import (
    LogisticsAssessment,
    PricingAssessment,
    QualityAssessment,
)
from app.schemas.inventory import InventoryBatch
from app.services.gemini_agent import call_gemini_json, is_gemini_configured


def _fallback_assess_logistics(
    batch: InventoryBatch,
    quality: QualityAssessment,
    pricing: PricingAssessment,
) -> LogisticsAssessment:
    estimated_sales = min(
        batch.quantity,
        int(
            pricing.expected_clearance_units_per_hour
            * quality.estimated_remaining_shelf_life_hours
        ),
    )

    surplus = max(0, batch.quantity - estimated_sales)

    if (
        quality.risk_level in ("HIGH", "CRITICAL")
        and surplus > 0
    ):
        transfer_quantity = min(surplus, 84)

        return LogisticsAssessment(
            batch_id=batch.batch_id,
            recommended_action="REDISTRIBUTE",
            recommended_quantity=transfer_quantity,
            destination="Whitefield Micro-Hub",
            evidence=[
                f"Estimated unsold surplus: {surplus} units",
                f"Suggested transfer: {transfer_quantity} units",
                "Destination capacity is simulated for the demo.",
            ],
        )

    if quality.risk_level == "CRITICAL" and surplus > 0:
        return LogisticsAssessment(
            batch_id=batch.batch_id,
            recommended_action="B2B_OFFLOAD",
            recommended_quantity=surplus,
            destination="Secondary Buyer Network",
            evidence=["Critical risk requires urgent stock review."],
        )

    return LogisticsAssessment(
        batch_id=batch.batch_id,
        recommended_action="KEEP",
        recommended_quantity=0,
        evidence=["No redistribution recommended by demo rules."],
    )


def assess_logistics(
    batch: InventoryBatch,
    quality: QualityAssessment,
    pricing: PricingAssessment,
) -> LogisticsAssessment:
    if is_gemini_configured():
        prompt = (
            "You are a logistics operation agent. "
            "Return valid JSON with keys: batch_id, recommended_action, recommended_quantity, destination, evidence. "
            f"Data: {json.dumps({'batch': batch.model_dump(mode='json'), 'quality': quality.model_dump(mode='json'), 'pricing': pricing.model_dump(mode='json')}, default=str)}"
        )
        payload = call_gemini_json(prompt)
        if payload:
            try:
                payload["batch_id"] = payload.get("batch_id", batch.batch_id)
                return LogisticsAssessment.model_validate(payload)
            except Exception:
                pass

    return _fallback_assess_logistics(batch, quality, pricing)
