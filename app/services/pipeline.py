"""Event-driven flow: a reading, a sale or a photo comes in → risk is refreshed → agents run if a rule fires."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import as_utc, utcnow
from app.models import Batch, Decision, FootfallSample, InventoryMovement, Product, SensorReading
from app.services import executor, vision
from app.services.anomaly_engine import DECISION_FLAGS, detect_anomalies, temperature_threshold
from app.services.decision_coordinator import create_decision
from app.services.events import log_event
from app.services.risk import decision_trigger, latest_reading, open_decision, refresh

VISION_MAX_AGE = timedelta(minutes=30)


def maybe_decide(db: Session, batch: Batch, anomalies_only: bool = False) -> Decision | None:
    """Run the agents if a rule says so.

    Sensor events only react to real anomalies; slow-burning risks (expiry, weak demand) are left to the
    monitor sweep. A fresh anomaly supersedes an older open decision made on weaker evidence.
    """
    s = refresh(db, batch)
    trigger = decision_trigger(s)
    if not trigger or (anomalies_only and trigger not in DECISION_FLAGS):
        return None
    existing = open_decision(db, batch.batch_id)
    if existing:
        if trigger in DECISION_FLAGS and existing.trigger not in DECISION_FLAGS:
            existing.status = "superseded"
        else:
            return None
    checked = as_utc(batch.vision_checked_at)
    if trigger == "HIGH_TEMPERATURE" and (checked is None or checked < s.now - VISION_MAX_AGE):
        vision.inspect(db, batch, image_type="alert")  # second photo before deciding, per the blueprint
        refresh(db, batch)
    decision = create_decision(db, batch, trigger)
    if settings.auto_execute and decision.confidence >= 0.85:
        executor.execute(db, decision, approved_by="autonomous")
    return decision


def ingest_reading(
    db: Session,
    batch: Batch,
    temperature_c: float,
    humidity_percent: float,
    ethylene_ppm: float,
    battery_pct: float = 100.0,
    recorded_at: datetime | None = None,
    decide: bool = True,
) -> tuple[SensorReading, Decision | None]:
    product = db.get(Product, batch.sku)
    previous = latest_reading(db, batch.batch_id)
    flags = detect_anomalies(product, temperature_c, humidity_percent, ethylene_ppm, battery_pct)
    reading = SensorReading(
        reading_id=str(uuid4()),
        batch_id=batch.batch_id,
        store_id=batch.store_id,
        sensor_id=batch.sensor_id or "",
        temperature_c=temperature_c,
        humidity_percent=humidity_percent,
        ethylene_ppm=ethylene_ppm,
        battery_pct=battery_pct,
        recorded_at=recorded_at or utcnow(),
        anomaly_flags=flags,
    )
    db.add(reading)
    db.flush()

    new = set(flags) - set(previous.anomaly_flags if previous else [])
    if "HIGH_TEMPERATURE" in new:
        s = refresh(db, batch)
        log_event(
            db,
            "sensor",
            f"Anomaly · {s.temp_delta:+.1f} °C over baseline",
            f"{batch.location.split(' · ')[0]} at {temperature_c:.1f} °C (rule {temperature_threshold(product):.1f} °C) → agents invoked",
            tone="critical",
            batch_id=batch.batch_id,
            data={"readingId": reading.reading_id},
        )
    elif new - {"SENSOR_LOW_BATTERY"}:
        log_event(db, "sensor", f"Anomaly · {', '.join(sorted(new))}", batch.location, tone="warning", batch_id=batch.batch_id)

    decision = maybe_decide(db, batch, anomalies_only=True) if decide else None
    if not decide:
        refresh(db, batch)
    return reading, decision


def record_sale(db: Session, batch: Batch, quantity: int, unit_price: float | None = None, at: datetime | None = None) -> InventoryMovement:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if quantity > batch.quantity_on_hand:
        raise ValueError(f"Only {batch.quantity_on_hand} on hand")
    move = InventoryMovement(
        movement_id=str(uuid4()),
        batch_id=batch.batch_id,
        store_id=batch.store_id,
        movement_type="sale",
        quantity=quantity,
        unit_price=unit_price or batch.current_price,
        occurred_at=at or utcnow(),
        reason="POS",
    )
    db.add(move)
    batch.quantity_on_hand -= quantity
    if batch.quantity_on_hand == 0:
        batch.status = "closed"
    db.flush()
    refresh(db, batch)
    return move


def record_footfall(db: Session, store_id: str, hour_start: datetime, count: int) -> FootfallSample:
    hour = hour_start.replace(minute=0, second=0, microsecond=0)
    sample = db.query(FootfallSample).filter_by(store_id=store_id, hour_start=hour).one_or_none()
    if sample:
        sample.count = count
    else:
        sample = FootfallSample(store_id=store_id, hour_start=hour, count=count)
        db.add(sample)
    db.flush()
    return sample
