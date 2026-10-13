"""Demand signals, all derived from the stock ledger and footfall counts."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import as_utc
from app.models import FootfallSample, InventoryMovement, Product, Store

SALE_TYPES = ("sale",)
VELOCITY_WINDOW_H = 5
IST = ZoneInfo("Asia/Kolkata")
# share of the store's typical hourly footfall by local hour (grocery traffic peaks late morning and evening)
DIURNAL = [
    0.05,
    0.03,
    0.02,
    0.02,
    0.03,
    0.08,
    0.25,
    0.55,
    0.8,
    0.95,
    1.0,
    1.0,
    0.95,
    0.85,
    0.8,
    0.85,
    1.0,
    1.2,
    1.3,
    1.25,
    1.05,
    0.75,
    0.4,
    0.15,
]


def diurnal(at: datetime) -> float:
    return DIURNAL[as_utc(at).astimezone(IST).hour]


def hourly_sales(db: Session, batch_id: str, now: datetime, hours: int = 12) -> list[float]:
    """Units sold per hour for the last `hours` hours, oldest first."""
    start = now - timedelta(hours=hours)
    rows = db.execute(
        select(InventoryMovement.occurred_at, InventoryMovement.quantity).where(
            InventoryMovement.batch_id == batch_id,
            InventoryMovement.movement_type.in_(SALE_TYPES),
            InventoryMovement.occurred_at >= start,
        )
    ).all()
    buckets = [0.0] * hours
    for at, qty in rows:
        idx = int((as_utc(at) - start).total_seconds() // 3600)
        if 0 <= idx < hours:
            buckets[idx] += qty
    return buckets


def velocity(db: Session, batch_id: str, now: datetime, window_h: int = VELOCITY_WINDOW_H) -> float:
    """Average units sold per hour over the recent window."""
    sold = db.scalar(
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
            InventoryMovement.batch_id == batch_id,
            InventoryMovement.movement_type.in_(SALE_TYPES),
            InventoryMovement.occurred_at >= now - timedelta(hours=window_h),
        )
    )
    return round(float(sold) / window_h, 2)


def forecast_per_h(store: Store, sku: str) -> float | None:
    profile = (store.demand_profile or {}).get(sku) or {}
    value = profile.get("forecast_per_h")
    return float(value) if value is not None else None


def footfall_ratio(db: Session, store: Store, now: datetime, hours: int = 3) -> float | None:
    """Footfall over the last few hours vs what's normal for those hours of day (rain, holidays, events show up here)."""
    if not store.footfall_baseline_per_h:
        return None
    rows = db.execute(
        select(FootfallSample.hour_start, FootfallSample.count)
        .where(FootfallSample.store_id == store.store_id, FootfallSample.hour_start <= now)
        .order_by(FootfallSample.hour_start.desc())
        .limit(hours)
    ).all()
    expected = sum(store.footfall_baseline_per_h * diurnal(r.hour_start) for r in rows)
    return round(sum(r.count for r in rows) / expected, 2) if rows and expected else None


def markdown_lift(product: Product, pct: float) -> float:
    """Demand multiplier for a discount, e.g. 20% off × elasticity 2.6 → 1.52× sales."""
    return 1 + product.markdown_elasticity * pct / 100
