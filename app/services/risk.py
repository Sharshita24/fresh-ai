"""One place that turns raw data into a batch's current risk picture.

expected sold   = min(on hand, sales velocity × projected shelf life)
expected waste  = on hand − expected sold
risk score      = 100 × (0.85 × waste share + 0.22 × anomaly severity + 0.30 × urgency)
                  where urgency = 1 − hours left / 48
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import as_utc, utcnow
from app.models import Batch, Decision, Product, SensorReading, Store
from app.services import demand
from app.services.anomaly_engine import DECISION_FLAGS, severity
from app.services.shelf_life import ShelfLife, project

OPEN_DECISION_STATES = ("proposed", "held")


@dataclass
class Snapshot:
    batch: Batch
    product: Product
    store: Store
    now: datetime
    reading: SensorReading | None
    temp_c: float
    baseline_c: float
    humidity: float
    ethylene: float
    flags: list[str]
    shelf: ShelfLife
    velocity: float
    forecast: float | None
    footfall_ratio: float | None
    expected_sold: int
    expected_waste: int
    waste_frac: float
    risk: int
    tier: str
    signals: list[str] = field(default_factory=list)

    @property
    def hours_left(self) -> float:
        return self.shelf.estimate_h

    @property
    def on_hand(self) -> int:
        return self.batch.quantity_on_hand

    @property
    def needed_rate(self) -> float:
        return round(self.on_hand / self.hours_left, 1) if self.hours_left > 0 else float(self.on_hand)

    @property
    def temp_delta(self) -> float:
        return round(self.temp_c - self.baseline_c, 1) or 0.0  # avoid "-0.0"


def latest_reading(db: Session, batch_id: str) -> SensorReading | None:
    return db.scalar(select(SensorReading).where(SensorReading.batch_id == batch_id).order_by(SensorReading.recorded_at.desc()).limit(1))


def baseline_temp(db: Session, batch: Batch, store: Store, product: Product, now: datetime) -> float:
    """Normal temperature for this batch: median of readings 20–120 min ago (before any current excursion)."""
    temps = db.scalars(
        select(SensorReading.temperature_c).where(
            SensorReading.batch_id == batch.batch_id,
            SensorReading.recorded_at <= now - timedelta(minutes=20),
            SensorReading.recorded_at >= now - timedelta(minutes=120),
        )
    ).all()
    if temps:
        return round(median(temps), 1)
    if store.cold_room_temp_c is not None and product.storage_max_c <= 8:
        return store.cold_room_temp_c
    return product.ref_temp_c


def snapshot(db: Session, batch: Batch, now: datetime | None = None) -> Snapshot:
    now = now or utcnow()
    product = db.get(Product, batch.sku)
    store = db.get(Store, batch.store_id)
    reading = latest_reading(db, batch.batch_id)
    temp = reading.temperature_c if reading else (store.cold_room_temp_c if store.cold_room_temp_c is not None else product.ref_temp_c)
    flags = list(reading.anomaly_flags) if reading else []

    printed_h = (as_utc(batch.expiry_at) - now).total_seconds() / 3600
    shelf = project(product, printed_h, temp, batch.defect_pct)
    vel = demand.velocity(db, batch.batch_id, now)
    forecast = demand.forecast_per_h(store, batch.sku)
    footfall = demand.footfall_ratio(db, store, now)

    on_hand = batch.quantity_on_hand
    sold = min(on_hand, math.floor(vel * shelf.estimate_h)) if on_hand else 0
    waste = on_hand - sold
    frac = waste / on_hand if on_hand else 0.0
    urgency = min(1.0, max(0.0, 1 - shelf.estimate_h / 48))
    risk = round(min(99.0, max(0.0, 100 * (0.85 * frac + 0.22 * severity(flags) + 0.30 * urgency))))
    if batch.status == "managed":
        tier = "managed"
    else:
        tier = "critical" if risk >= 80 else "risk" if risk >= 50 else "healthy"

    base = baseline_temp(db, batch, store, product, now)
    signals = []
    if "HIGH_TEMPERATURE" in flags or temp - base >= 1.5:
        signals.append("Temp ↑")
    if batch.defect_pct >= 10:
        signals.append("Vision")
    if forecast and vel < 0.85 * forecast:
        signals.append("Demand ↓")
    if "HIGH_ETHYLENE" in flags:
        signals.append("Ethylene ↑")
    if "HIGH_HUMIDITY" in flags:
        signals.append("Humidity ↑")
    if shelf.estimate_h < 12:
        signals.append("Expiry")

    return Snapshot(
        batch=batch,
        product=product,
        store=store,
        now=now,
        reading=reading,
        temp_c=round(temp, 2),
        baseline_c=base,
        humidity=reading.humidity_percent if reading else 0.0,
        ethylene=reading.ethylene_ppm if reading else 0.0,
        flags=flags,
        shelf=shelf,
        velocity=vel,
        forecast=forecast,
        footfall_ratio=footfall,
        expected_sold=sold,
        expected_waste=waste,
        waste_frac=round(frac, 3),
        risk=risk,
        tier=tier,
        signals=signals,
    )


def refresh(db: Session, batch: Batch, now: datetime | None = None) -> Snapshot:
    """Recompute and cache the risk picture on the batch row."""
    s = snapshot(db, batch, now)
    batch.est_shelf_life_h = s.hours_left
    batch.risk_score = s.risk
    batch.risk_tier = s.tier
    batch.signals = s.signals
    batch.updated_at = s.now
    return s


def open_decision(db: Session, batch_id: str) -> Decision | None:
    return db.scalar(
        select(Decision)
        .where(Decision.batch_id == batch_id, Decision.status.in_(OPEN_DECISION_STATES))
        .order_by(Decision.created_at.desc())
        .limit(1)
    )


def decision_trigger(s: Snapshot) -> str | None:
    """Should the agents look at this batch? Cheap rules first; the LLM only runs when this says yes."""
    if s.batch.status != "active" or s.on_hand <= 0:
        return None
    hit = [f for f in s.flags if f in DECISION_FLAGS]
    if hit:
        return hit[0]
    if s.hours_left < 12 and s.expected_waste > 0:
        return "EXPIRY_RISK"
    if s.waste_frac >= 0.35:
        return "WASTE_RISK"
    return None
