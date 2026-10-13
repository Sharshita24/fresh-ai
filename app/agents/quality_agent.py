"""Quality agent: sensors + vision → how much sellable life is really left."""

from app.schemas.agents import QualityAssessment
from app.services.risk import Snapshot


def risk_level(score: int) -> str:
    return "CRITICAL" if score >= 80 else "HIGH" if score >= 60 else "MEDIUM" if score >= 40 else "LOW"


def assess_quality(s: Snapshot) -> QualityAssessment:
    evidence = [
        f"Temperature {s.temp_c:.1f} °C vs {s.baseline_c:.1f} °C baseline ({s.temp_delta:+.1f} °C)",
        f"Shelf life {s.hours_left:.0f} h vs {s.shelf.printed_h:.0f} h on the label "
        f"(temperature ×{s.shelf.temp_factor}, quality ×{s.shelf.quality_factor})",
        f"Vision: {s.batch.defect_pct:.0f}% surface defects — {s.batch.vision_label}",
    ]
    evidence += [f"Anomaly: {f}" for f in s.flags]
    return QualityAssessment(
        batch_id=s.batch.batch_id,
        estimated_remaining_shelf_life_hours=s.hours_left,
        printed_remaining_hours=s.shelf.printed_h,
        temperature_c=s.temp_c,
        baseline_temperature_c=s.baseline_c,
        temperature_factor=s.shelf.temp_factor,
        quality_factor=s.shelf.quality_factor,
        defect_pct=s.batch.defect_pct,
        vision_label=s.batch.vision_label,
        anomaly_flags=s.flags,
        risk_score=s.risk,
        risk_level=risk_level(s.risk),
        evidence=evidence,
    )
