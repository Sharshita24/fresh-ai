import json

from app.schemas.agents import QualityAssessment
from app.schemas.inventory import InventoryBatch
from app.schemas.sensors import SensorReading
from app.services.gemini_agent import call_gemini_json, is_gemini_configured


def _fallback_assess_quality(
    batch: InventoryBatch,
    reading: SensorReading,
) -> QualityAssessment:
    flags = reading.anomaly_flags

    if "HIGH_TEMPERATURE" in flags:
        risk = "HIGH"
        shelf_life = max(
            0,
            batch.estimated_remaining_shelf_life_hours - 6,
        )
    elif flags:
        risk = "MEDIUM"
        shelf_life = max(
            0,
            batch.estimated_remaining_shelf_life_hours - 3,
        )
    else:
        risk = "LOW"
        shelf_life = (
            batch.estimated_remaining_shelf_life_hours
        )

    evidence = [
        f"Temperature: {reading.temperature_c} C",
        f"Humidity: {reading.humidity_percent}%",
        f"Ethylene: {reading.ethylene_ppm} ppm",
    ]

    evidence.extend(
        f"Detected anomaly: {flag}" for flag in flags
    )

    return QualityAssessment(
        batch_id=batch.batch_id,
        estimated_remaining_shelf_life_hours=shelf_life,
        risk_level=risk,
        evidence=evidence,
        confidence=0.80 if flags else 0.65,
    )


def assess_quality(
    batch: InventoryBatch,
    reading: SensorReading,
) -> QualityAssessment:
    if is_gemini_configured():
        prompt = (
            "You are a food quality assessment agent. "
            "Return valid JSON with keys: batch_id, estimated_remaining_shelf_life_hours, "
            "risk_level, evidence, confidence. "
            f"Data: {json.dumps({'batch': batch.model_dump(mode='json'), 'reading': reading.model_dump(mode='json')}, default=str)}"
        )
        payload = call_gemini_json(prompt)
        if payload:
            try:
                payload["batch_id"] = payload.get("batch_id", batch.batch_id)
                return QualityAssessment.model_validate(payload)
            except Exception:
                pass

    return _fallback_assess_quality(batch, reading)
