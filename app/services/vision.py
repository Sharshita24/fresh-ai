"""Visual quality checks: a reference photo at intake, an alert photo when a batch looks at risk.

With GEMINI_API_KEY set, uploaded photos are scored by Gemini Vision. Without a key (or without a
photo) the simulated inspector estimates defects from the thermal stress the batch has been through,
so the demo behaves the same way offline.
"""

import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import utcnow
from app.models import Batch, BatchImage, Product, SensorReading
from app.services import gemini_agent
from app.services.events import log_event

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_BYTES = 8 * 1024 * 1024
SAMPLE_UNITS = 24  # units visible in a typical shelf photo


def label_for(defect_pct: float) -> str:
    return (
        "Within tolerance"
        if defect_pct < 5
        else "Minor blemishes"
        if defect_pct < 10
        else "Early bruising"
        if defect_pct < 25
        else "Spoilage visible"
    )


def simulated_defect(db: Session, batch: Batch, product: Product) -> float:
    """Defects grow with heat stress: up to +15 points after 2 °C+ above the storage maximum in the last hour."""
    peak = db.scalar(
        select(func.max(SensorReading.temperature_c)).where(
            SensorReading.batch_id == batch.batch_id, SensorReading.recorded_at >= utcnow() - timedelta(hours=1)
        )
    )
    stress = 0.0 if peak is None else min(1.0, max(0.0, (peak - product.storage_max_c) / 2.2))
    return round(min(100.0, batch.reference_defect_pct + 15 * stress), 1)


def inspect(db: Session, batch: Batch, image_type: str = "alert", data: bytes | None = None, mime_type: str | None = None) -> BatchImage:
    product = db.get(Product, batch.sku)
    path = None
    if data is not None:
        if mime_type not in ALLOWED_TYPES:
            raise ValueError("Upload a JPEG, PNG or WebP image")
        if len(data) > MAX_BYTES:
            raise ValueError("Image is larger than 8 MB")
        os.makedirs(settings.upload_dir, exist_ok=True)
        path = str(Path(settings.upload_dir) / f"{uuid4().hex}{ALLOWED_TYPES[mime_type]}")  # server-chosen name, no user paths
        Path(path).write_bytes(data)

    verdict = gemini_agent.inspect_image(data, mime_type, f"{product.name} {product.variant}") if data is not None else None
    if verdict:
        result, meta = verdict
        defect, label, model = result.defect_pct, result.label, meta["model"]
        findings = {"defects": result.defects, "confidence": result.confidence, **meta}
    else:
        defect = simulated_defect(db, batch, product) if image_type == "alert" else batch.reference_defect_pct
        label, model = label_for(defect), "simulated-vision"
        findings = {"defects": ["surface bruising"] if defect >= 10 else []}
    flagged = round(SAMPLE_UNITS * defect / 100)
    findings["summary"] = f"{flagged} of {SAMPLE_UNITS} units flagged by {'Gemini Vision' if verdict else 'vision check'}"

    image = BatchImage(
        image_id=str(uuid4()),
        batch_id=batch.batch_id,
        image_type=image_type,
        file_path=path,
        uploaded_at=utcnow(),
        model_used=model,
        defect_pct=defect,
        label=label,
        findings=findings,
    )
    db.add(image)
    db.flush()
    batch.defect_pct = defect
    batch.vision_label = label
    batch.vision_checked_at = utcnow()
    if image_type == "reference":
        batch.reference_defect_pct = defect
    log_event(
        db,
        "vision",
        f"Vision check · {defect:.0f}% {label.lower()}",
        findings["summary"],
        tone="warning" if defect >= 10 else "info",
        batch_id=batch.batch_id,
        data={"imageId": image.image_id, "model": model},
    )
    return image
