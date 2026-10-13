"""Demo data: one store's morning, built through the same tables the live system writes.

Run directly to rebuild the database:  python -m app.services.seed
"""

import random
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.data import reference as ref
from app.db.database import Base, SessionLocal, engine, utcnow
from app.models import (
    Action,
    Batch,
    BatchImage,
    Decision,
    Event,
    Execution,
    FootfallSample,
    InventoryMovement,
    Product,
    SensorReading,
    Store,
    Supplier,
)
from app.services.anomaly_engine import detect_anomalies
from app.services.decision_coordinator import CO2_PER_KG
from app.services.demand import diurnal
from app.services.executor import ENDPOINTS
from app.services.risk import refresh
from app.services.vision import SAMPLE_UNITS, label_for

MIN_RECEIVED_AGO_H = 12.5  # night delivery, so the 12 h sales history belongs to this batch
DRIFTING = {"SLM-310", "PRN-118"}  # seafood case slowly warming — below the alert rule
RAIN_HOURS = 3  # last three hours of footfall are down ~24% (door counter data)


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _moved_out(batch_id: str) -> int:
    return sum(h["qty"] for h in ref.HISTORY if h["batch_id"] == batch_id and h["action"] in ("TRANSFER", "DONATION", "B2B_OFFER"))


def _seed_batch(db: Session, spec: dict, now, rnd: random.Random) -> Batch:
    product = db.get(Product, spec["sku"])
    received = now + timedelta(hours=min(spec["received_h"], -MIN_RECEIVED_AGO_H))
    history = spec["history"]
    batch = Batch(
        batch_id=spec["batch_id"],
        sku=spec["sku"],
        store_id="store-042",
        supplier_id=spec["supplier_id"],
        lot_code=spec["lot"],
        harvest_date=(now + timedelta(days=spec["harvest_d"])).date(),
        received_at=received,
        expiry_at=now + timedelta(hours=spec["printed_h"]),
        location=spec["location"],
        sensor_id=spec["sensor"],
        quantity_received=spec["units"] + sum(history) + _moved_out(spec["batch_id"]),
        quantity_on_hand=spec["units"] + _moved_out(spec["batch_id"]),
        original_price=product.base_price,
        current_price=product.base_price,
        defect_pct=spec["defect"],
        reference_defect_pct=spec["defect"],
        vision_label=label_for(spec["defect"]),
        vision_checked_at=received + timedelta(minutes=40),
        status="active",
    )
    db.add(batch)
    db.flush()

    db.add(
        InventoryMovement(
            movement_id=str(uuid4()),
            batch_id=batch.batch_id,
            store_id=batch.store_id,
            movement_type="receive",
            quantity=batch.quantity_received,
            unit_price=product.base_price,
            occurred_at=received,
            reason=f"Lot {batch.lot_code}",
        )
    )
    start = now - timedelta(hours=len(history))
    for i, qty in enumerate(history):
        if qty:
            db.add(
                InventoryMovement(
                    movement_id=str(uuid4()),
                    batch_id=batch.batch_id,
                    store_id=batch.store_id,
                    movement_type="sale",
                    quantity=qty,
                    unit_price=product.base_price,
                    occurred_at=start + timedelta(hours=i, minutes=30),
                    reason="POS",
                )
            )

    for m in range(59, -1, -1):  # one reading a minute for the last hour
        if spec["batch_id"] in DRIFTING:
            base = 1.0 if m > 40 else 1.0 + (spec["temp"] - 1.0) * (40 - m) / 40
        else:
            base = spec["temp"]
        temp = round(base + rnd.uniform(-0.06, 0.06), 2)
        rh = round(min(100.0, spec["rh"] + rnd.uniform(-0.5, 0.5)), 1)
        c2h4 = round(max(0.0, spec["c2h4"] + rnd.uniform(-0.02, 0.02)), 2)
        db.add(
            SensorReading(
                reading_id=str(uuid4()),
                batch_id=batch.batch_id,
                store_id=batch.store_id,
                sensor_id=spec["sensor"],
                temperature_c=temp,
                humidity_percent=rh,
                ethylene_ppm=c2h4,
                battery_pct=88.0,
                recorded_at=now - timedelta(minutes=m),
                anomaly_flags=detect_anomalies(product, temp, rh, c2h4),
            )
        )

    flagged = round(SAMPLE_UNITS * spec["defect"] / 100)
    db.add(
        BatchImage(
            image_id=str(uuid4()),
            batch_id=batch.batch_id,
            image_type="reference",
            uploaded_at=batch.vision_checked_at,
            model_used="simulated-vision",
            defect_pct=spec["defect"],
            label=batch.vision_label,
            findings={"defects": [], "summary": f"{flagged} of {SAMPLE_UNITS} units flagged at intake"},
        )
    )
    return batch


def _seed_footfall(db: Session, now, rnd: random.Random) -> None:
    store = db.get(Store, "store-042")
    hour = now.replace(minute=0, second=0, microsecond=0)
    for back in range(11, -1, -1):
        h = hour - timedelta(hours=back)
        factor = 0.76 if back < RAIN_HOURS else 1 + rnd.uniform(-0.04, 0.04)
        db.add(FootfallSample(store_id=store.store_id, hour_start=h, count=round(store.footfall_baseline_per_h * diurnal(h) * factor)))


def _seed_history(db: Session, h: dict, now) -> None:
    batch = db.get(Batch, h["batch_id"])
    product = db.get(Product, batch.sku)
    at = now - timedelta(minutes=h["minutes_ago"])
    kind = h["action"]
    step = {"type": kind, "quantity": h["qty"]}
    if kind == "MARKDOWN":
        price_to = round(product.base_price * (1 - h["pct"] / 100), 2)
        step.update(pct=h["pct"], priceFrom=product.base_price, priceTo=price_to)
        batch.current_price = price_to
    else:
        step.update(target=h["target"], targetName=h["target"])
        moved_type = {"TRANSFER": "transfer_out", "DONATION": "donation", "B2B_OFFER": "b2b_sale"}[kind]
        db.add(
            InventoryMovement(
                movement_id=str(uuid4()),
                batch_id=batch.batch_id,
                store_id=batch.store_id,
                movement_type=moved_type,
                quantity=h["qty"],
                occurred_at=at,
                reason=h["detail"],
            )
        )
        batch.quantity_on_hand -= h["qty"]

    evidence = [
        {"n": f"0{i + 1}", "title": text, "value": "", "evidence": "", "impact": "", "agent": "", "tone": "info"}
        for i, text in enumerate(h["evidence"])
    ]
    expected = {"value": h["value"], "kgSaved": h["kg"], "co2Saved": round(h["kg"] * CO2_PER_KG, 1)}
    decision = Decision(
        decision_id=str(uuid4()),
        batch_id=batch.batch_id,
        trigger="WASTE_RISK",
        status="executed",
        confidence=0.9,
        selected_option=kind.lower(),
        plan=[step],
        options=[],
        evidence=evidence,
        rationale=h["detail"],
        expected=expected,
        model_used="rules",
        created_at=at - timedelta(minutes=1),
        decided_at=at,
    )
    db.add(decision)
    db.flush()
    endpoint, code, system = ENDPOINTS[kind]
    db.add(
        Action(
            action_id=str(uuid4()),
            decision_id=decision.decision_id,
            batch_id=batch.batch_id,
            action_type=kind,
            quantity=h["qty"],
            target=h.get("target"),
            endpoint=endpoint,
            response_code=code,
            payload=step,
            executed_at=at,
        )
    )
    db.add(
        Execution(
            execution_id=str(uuid4()),
            decision_id=decision.decision_id,
            batch_id=batch.batch_id,
            approved_by="autonomous",
            steps=[
                {
                    "type": kind,
                    "name": h["title"],
                    "detail": h["detail"],
                    "system": system,
                    "endpoint": endpoint,
                    "code": code,
                    "status": "done",
                    "at": at.isoformat(),
                    "payload": step,
                }
            ],
            impact={"value": h["value"], "kg": h["kg"], "co2": expected["co2Saved"], "actions": 1},
            created_at=at,
        )
    )
    db.add(
        Event(
            occurred_at=at,
            kind="action",
            tone="good",
            batch_id=batch.batch_id,
            title=h["title"],
            detail=h["detail"],
            data={"actionType": kind, "decisionId": decision.decision_id, "value": h["value"], "kg": h["kg"], "evidence": h["evidence"]},
        )
    )
    batch.status = "managed"


def seed(db: Session, now=None) -> None:
    now = now or utcnow()
    rnd = random.Random(42)
    db.add_all([Product(**p) for p in ref.PRODUCTS])
    db.add_all([Supplier(**s) for s in ref.SUPPLIERS])
    db.add_all([Store(**s) for s in ref.STORES])
    db.flush()
    batches = [_seed_batch(db, spec, now, rnd) for spec in ref.BATCHES]
    _seed_footfall(db, now, rnd)
    for h in ref.HISTORY:
        _seed_history(db, h, now)
    n = ref.SENSOR_NOTE
    db.add(
        Event(
            occurred_at=now - timedelta(minutes=n["minutes_ago"]),
            kind="sensor",
            tone="warning",
            batch_id=n["batch_id"],
            title=n["title"],
            detail=n["detail"],
            data={"evidence": n["evidence"]},
        )
    )
    db.flush()
    for b in batches:
        refresh(db, b, now)
    db.commit()


def rebuild() -> None:
    """Drop and recreate every table (use after schema changes)."""
    reset_database()
    with SessionLocal() as db:
        seed(db)


def reset_data() -> None:
    """Replace all rows with fresh demo data in one transaction, so concurrent readers never see empty tables."""
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        seed(db)  # commits once at the end


if __name__ == "__main__":
    rebuild()
    print("FreshChain demo data loaded.")
