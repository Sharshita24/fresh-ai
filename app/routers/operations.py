"""Write endpoints: IoT readings, POS sales, footfall, batch intake and photos."""

from datetime import timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import presenters
from app.db.database import as_utc, get_db, utcnow
from app.models import Product, Store
from app.routers.dashboard import get_batch
from app.schemas.api import FootfallIn, SaleIn, SensorReadingIn, SensorSimulationRequest
from app.services import pipeline, vision
from app.services.intake import BatchIntake, create_batch, import_csv
from app.services.risk import baseline_temp
from app.services.sensor_simulator import scenario_reading

router = APIRouter(prefix="/api", tags=["operations"])


def _reading_response(db, batch, reading, decision):
    return {
        "readingId": reading.reading_id,
        "batchId": batch.batch_id,
        "temperatureC": reading.temperature_c,
        "humidityPercent": reading.humidity_percent,
        "ethylenePpm": reading.ethylene_ppm,
        "recordedAt": presenters.iso(reading.recorded_at),
        "anomalyFlags": reading.anomaly_flags,
        "risk": batch.risk_score,
        "status": batch.risk_tier,
        "shelfLifeH": batch.est_shelf_life_h,
        "decisionId": decision.decision_id if decision else None,
        # legacy field names
        "reading_id": reading.reading_id,
        "anomaly_flags": reading.anomaly_flags,
    }


@router.post("/sensors/readings", summary="Ingest one IoT reading; runs the agents if it is an anomaly")
def ingest_sensor_reading(body: SensorReadingIn, db: Session = Depends(get_db)):
    batch = get_batch(db, body.batch_id)
    at = as_utc(body.recorded_at).astimezone(timezone.utc) if body.recorded_at else None
    reading, decision = pipeline.ingest_reading(
        db, batch, body.temperature_c, body.humidity_percent, body.ethylene_ppm, body.battery_pct, at
    )
    db.commit()
    return _reading_response(db, batch, reading, decision)


@router.post("/sensors/simulate", summary="Generate a scenario reading (NORMAL, TEMPERATURE_SPIKE, …) for a batch")
def simulate_sensor_reading(body: SensorSimulationRequest, db: Session = Depends(get_db)):
    batch = get_batch(db, body.batch_id)
    product = db.get(Product, batch.sku)
    store = db.get(Store, batch.store_id)
    values = scenario_reading(product, baseline_temp(db, batch, store, product, utcnow()), body.scenario)
    reading, decision = pipeline.ingest_reading(db, batch, **values)
    db.commit()
    return _reading_response(db, batch, reading, decision)


@router.post("/sales", summary="Record a POS sale; updates the stock ledger and demand velocity")
def record_sale(body: SaleIn, db: Session = Depends(get_db)):
    batch = get_batch(db, body.batch_id)
    try:
        move = pipeline.record_sale(db, batch, body.quantity, body.unit_price)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {
        "movementId": move.movement_id,
        "batchId": batch.batch_id,
        "onHand": batch.quantity_on_hand,
        "risk": batch.risk_score,
        "status": batch.risk_tier,
    }


@router.post("/footfall", summary="Record a store door-counter reading for an hour")
def record_footfall(body: FootfallIn, db: Session = Depends(get_db)):
    if db.get(Store, body.store_id) is None:
        raise HTTPException(404, f"Store {body.store_id} not found")
    hour = as_utc(body.hour_start).astimezone(timezone.utc) if body.hour_start else utcnow()
    sample = pipeline.record_footfall(db, body.store_id, hour, body.count)
    db.commit()
    return {"storeId": sample.store_id, "hourStart": presenters.iso(sample.hour_start), "count": sample.count}


@router.post("/intake/batches", status_code=201, summary="Create one batch (admin form)")
def intake_batch(body: BatchIntake, db: Session = Depends(get_db)):
    try:
        batch = create_batch(db, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return presenters.batch_item(db, batch)


@router.post("/intake/batches/csv", summary="Bulk batch intake from a CSV export (see samples/batches.csv)")
async def intake_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "CSV larger than 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8") from None
    result = import_csv(db, text)
    db.commit()
    return result


@router.post("/batches/{batch_id}/images", summary="Upload a shelf photo; scored by Gemini Vision (or the simulated inspector)")
async def upload_image(batch_id: str, file: UploadFile = File(...), image_type: str = Form("alert"), db: Session = Depends(get_db)):
    batch = get_batch(db, batch_id)
    if image_type not in ("reference", "alert"):
        raise HTTPException(400, "image_type must be reference or alert")
    data = await file.read()
    try:
        image = vision.inspect(db, batch, image_type=image_type, data=data, mime_type=file.content_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    decision = pipeline.maybe_decide(db, batch) if image_type == "alert" else None
    db.commit()
    return {
        "imageId": image.image_id,
        "defectPct": image.defect_pct,
        "label": image.label,
        "model": image.model_used,
        "findings": image.findings,
        "decisionId": decision.decision_id if decision else None,
    }


@router.post("/batches/{batch_id}/inspect", summary="Run a vision check without a photo (simulated inspector)")
def inspect_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = get_batch(db, batch_id)
    image = vision.inspect(db, batch, image_type="alert")
    db.commit()
    return {
        "imageId": image.image_id,
        "defectPct": image.defect_pct,
        "label": image.label,
        "model": image.model_used,
        "findings": image.findings,
    }
