"""Shape database rows into the JSON the dashboard reads (camelCase).

Legacy fields from the first API contract (incidentId, recommendedPlan, alternatives, transfer, ticket)
are kept so older clients keep working.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.logistics_agent import assess_logistics, distance_km
from app.db.database import as_utc, utcnow
from app.models import Batch, BatchImage, Decision, Event, Execution, InventoryMovement, Product, SensorReading, Store, Supplier
from app.services import demand, weather
from app.services.anomaly_engine import temperature_threshold
from app.services.risk import OPEN_DECISION_STATES, Snapshot, open_decision, snapshot

IST = ZoneInfo("Asia/Kolkata")
ACTION_LABEL = {"TRANSFER": "Transfer", "MARKDOWN": "Markdown", "B2B_OFFER": "B2B offload", "DONATION": "Food rescue"}


def iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def _plan_label(plan: list[dict]) -> str:
    parts = [ACTION_LABEL[a["type"]] for a in plan if a["type"] in ACTION_LABEL]
    return " + ".join(p if i == 0 else p.lower() for i, p in enumerate(parts)) or "Monitor"


def _last_executed(db: Session, batch_id: str) -> Decision | None:
    return db.scalar(
        select(Decision).where(Decision.batch_id == batch_id, Decision.status == "executed").order_by(Decision.decided_at.desc()).limit(1)
    )


def batch_action(db: Session, batch: Batch) -> tuple[str, str | None]:
    d = open_decision(db, batch.batch_id)
    if d:
        return _plan_label(
            d.plan
        ), "Awaiting your approval" if d.status == "held" else f"Proposed · {round(d.confidence * 100)}% confidence"
    if batch.status == "managed":
        last = _last_executed(db, batch.batch_id)
        if last:
            ex = db.scalar(select(Execution).where(Execution.decision_id == last.decision_id))
            note = ex.steps[0]["detail"] if ex and ex.steps else last.rationale
            return _plan_label(last.plan), note
    return "Monitor", None


def batch_item(db: Session, batch: Batch, s: Snapshot | None = None) -> dict:
    s = s or snapshot(db, batch)
    p: Product = s.product
    supplier = db.get(Supplier, batch.supplier_id) if batch.supplier_id else None
    action, note = batch_action(db, batch)
    pending = open_decision(db, batch.batch_id)
    return {
        "id": batch.batch_id,
        "name": p.name,
        "variant": p.variant,
        "category": p.category,
        "icon": p.icon,
        "units": batch.quantity_on_hand,
        "unitLabel": p.unit_label,
        "unitKg": p.unit_kg,
        "price": batch.current_price,
        "originalPrice": batch.original_price,
        "stockValue": round(batch.quantity_on_hand * batch.current_price),
        "location": batch.location,
        "supplier": supplier.name if supplier else None,
        "lotCode": batch.lot_code,
        "receivedAt": iso(batch.received_at),
        "expiryAt": iso(batch.expiry_at),
        "risk": s.risk,
        "status": s.tier,
        "shelfLifeH": s.hours_left,
        "printedShelfH": s.shelf.printed_h,
        "signals": s.signals,
        "action": action,
        "actionNote": note,
        "openDecisionId": pending.decision_id if pending else None,
    }


def batch_detail(db: Session, batch: Batch) -> dict:
    s = snapshot(db, batch)
    p = s.product
    temps = db.scalars(
        select(SensorReading.temperature_c)
        .where(SensorReading.batch_id == batch.batch_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(60)
    ).all()[::-1]
    image = db.scalar(select(BatchImage).where(BatchImage.batch_id == batch.batch_id).order_by(BatchImage.uploaded_at.desc()).limit(1))
    item = batch_item(db, batch, s)
    item.update(
        harvestDate=batch.harvest_date.isoformat() if batch.harvest_date else None,
        quantityReceived=batch.quantity_received,
        parentBatchId=batch.parent_batch_id,
        sensorId=batch.sensor_id,
        temp={
            "baseline": s.baseline_c,
            "now": s.temp_c,
            "safe": [p.storage_min_c, p.storage_max_c],
            "threshold": temperature_threshold(p),
            "series": temps,
        },
        humidity=s.humidity,
        ethylene=s.ethylene,
        anomalyFlags=s.flags,
        vision={
            "defectPct": batch.defect_pct,
            "referenceDefectPct": batch.reference_defect_pct,
            "label": batch.vision_label,
            "inspectedAt": iso(batch.vision_checked_at),
            "model": image.model_used if image else None,
            "summary": image.findings.get("summary") if image else None,
        },
        demand={
            "rate": s.velocity,
            "forecast": s.forecast,
            "needed": s.needed_rate,
            "footfallRatio": s.footfall_ratio,
            "history": demand.hourly_sales(db, batch.batch_id, s.now),
        },
        shelfLife={
            "estimateH": s.hours_left,
            "printedH": s.shelf.printed_h,
            "tempFactor": s.shelf.temp_factor,
            "qualityFactor": s.shelf.quality_factor,
            "expectedSold": s.expected_sold,
            "expectedWaste": s.expected_waste,
        },
    )
    return {
        "batch": item,
        "signals": [
            {"type": "temperature", "value": s.temp_c},
            {"type": "humidity", "value": s.humidity},
            {"type": "ethylene", "value": s.ethylene},
        ],
    }


def decision_out(db: Session, d: Decision) -> dict:
    batch = db.get(Batch, d.batch_id)
    product = db.get(Product, batch.sku)
    ex = db.scalar(select(Execution).where(Execution.decision_id == d.decision_id))
    shortlist = [o for o in d.options if o.get("shortlisted")] or d.options
    actions = []
    for a in d.plan:
        if a["type"] == "TRANSFER":
            actions.append({"type": "transfer", "units": a["quantity"], "destination": a.get("targetName"), "etaMin": a.get("etaMin")})
        elif a["type"] == "MARKDOWN":
            actions.append({"type": "markdown", "units": a["quantity"], "pct": a["pct"]})
        elif a["type"] == "B2B_OFFER":
            actions.append({"type": "b2b_offload", "units": a["quantity"], "destination": a.get("targetName")})
    return {
        "decisionId": d.decision_id,
        "batchId": d.batch_id,
        "incidentId": d.batch_id,
        "trigger": d.trigger,
        "status": d.status,
        "confidence": d.confidence,
        "selectedOption": d.selected_option,
        "planLabel": _plan_label(d.plan),
        "plan": d.plan,
        "options": shortlist,
        "evidence": d.evidence,
        "rationale": d.rationale,
        "expected": d.expected,
        "modelUsed": d.model_used,
        "modelMeta": d.model_meta,
        "createdAt": iso(d.created_at),
        "decidedAt": iso(d.decided_at),
        "executionId": ex.execution_id if ex else None,
        "batch": {
            "name": product.name,
            "variant": product.variant,
            "units": batch.quantity_on_hand,
            "unitLabel": product.unit_label,
            "location": batch.location,
            "price": batch.current_price,
            "originalPrice": batch.original_price,
        },
        # legacy contract
        "recommendedPlan": {
            "type": d.selected_option,
            "confidence": round(d.confidence * 100),
            "estimatedValuePreserved": d.expected.get("value", 0),
            "kgSaved": d.expected.get("kgSaved", 0),
            "co2Saved": d.expected.get("co2Saved", 0),
            "actions": actions,
        },
        "alternatives": [{"type": o["id"], "expectedWaste": o["waste"], "value": o["value"]} for o in shortlist if not o.get("selected")],
    }


def execution_out(ex: Execution) -> dict:
    transfer = next((s for s in ex.steps if s["type"] == "TRANSFER"), None)
    ticket = next((s for s in ex.steps if s["type"] == "MAINTENANCE"), None)
    return {
        "executionId": ex.execution_id,
        "decisionId": ex.decision_id,
        "batchId": ex.batch_id,
        "incidentId": ex.batch_id,
        "status": ex.status,
        "approvedBy": ex.approved_by,
        "steps": ex.steps,
        "impact": ex.impact,
        "createdAt": iso(ex.created_at),
        "transfer": {
            "id": transfer["payload"].get("transfer_id"),
            "destination": transfer["payload"].get("to"),
            "etaMin": transfer["payload"].get("eta_min"),
        }
        if transfer
        else None,
        "ticket": {"id": ticket["payload"].get("ticket")} if ticket else None,
    }


def event_out(e: Event) -> dict:
    group = {"sensor": "sensor", "vision": "sensor", "agent": "ai", "decision": "ai"}.get(e.kind, "action")
    return {
        "id": str(e.event_id),
        "timestamp": iso(e.occurred_at),
        "kind": e.kind,
        "tone": e.tone,
        "group": group,
        "batchId": e.batch_id,
        "title": e.title,
        "detail": e.detail,
        "summary": e.detail,
        "status": "executed" if e.kind in ("action", "impact") else "recorded",
        "data": e.data,
    }


def impact(db: Session, store: Store, now: datetime | None = None) -> dict:
    """Impact over the last 24 hours (a rolling day, so a late-night demo still shows the morning's work)."""
    now = now or utcnow()
    start = now - timedelta(hours=24)
    rows = (
        db.execute(
            select(Execution)
            .join(Batch, Batch.batch_id == Execution.batch_id)
            .where(Batch.store_id == store.store_id, Execution.created_at >= start)
        )
        .scalars()
        .all()
    )
    total = {"valuePreserved": 0.0, "kgSaved": 0.0, "co2Saved": 0.0, "actions": 0, "decisions": len(rows)}
    for ex in rows:
        total["valuePreserved"] += ex.impact.get("value", 0) or 0
        total["kgSaved"] += ex.impact.get("kg", 0) or 0
        total["co2Saved"] += ex.impact.get("co2", 0) or 0
        total["actions"] += ex.impact.get("actions", 0) or 0
    for k in ("valuePreserved", "kgSaved", "co2Saved"):
        total[k] = round(total[k], 1)
    past = (store.meta or {}).get("impactHistory", [])
    today = now.astimezone(IST).date()
    total["week"] = [{"day": (today - timedelta(days=len(past) - i)).strftime("%a"), "kg": kg} for i, kg in enumerate(past)]
    total["week"].append({"day": "Today", "kg": total["kgSaved"], "today": True})
    return total


def overview(db: Session, store: Store) -> dict:
    batches = db.scalars(select(Batch).where(Batch.store_id == store.store_id, Batch.status != "closed")).all()
    meta = store.meta or {}
    tiers = {"healthy": 0, "risk": 0, "critical": 0, "managed": 0}
    zones: dict[str, dict] = {}
    for b in batches:
        s = snapshot(db, b)
        tiers[s.tier] += 1
        zone = b.location.split(" · ")[0]
        if zone not in zones or s.temp_delta > zones[zone]["deltaC"]:
            zones[zone] = {
                "zone": zone,
                "tempC": s.temp_c,
                "baselineC": s.baseline_c,
                "deltaC": s.temp_delta,
                "status": "critical" if s.flags and "HIGH_TEMPERATURE" in s.flags else "warning" if s.temp_delta >= 1 else "good",
                "batchId": b.batch_id,
            }
    untracked = meta.get("untracked", {})
    risk = tiers["risk"] + untracked.get("risk", 0)
    critical = tiers["critical"] + untracked.get("critical", 0)
    skus = meta.get("skus", len(batches))
    active = db.scalar(
        select(Decision)
        .join(Batch, Batch.batch_id == Decision.batch_id)
        .where(Batch.store_id == store.store_id, Decision.status.in_(OPEN_DECISION_STATES))
        .order_by(Decision.created_at.desc())
        .limit(1)
    )
    return {
        "store": {
            "id": store.store_id,
            "name": store.name,
            "city": store.city,
            "area": store.area,
            "manager": store.manager,
            "skus": skus,
            "sensors": meta.get("sensors", len(batches)),
        },
        "riskSummary": {
            "healthy": skus - risk - critical - tiers["managed"],
            "risk": risk,
            "critical": critical,
            "managed": tiers["managed"],
        },
        "trackedBatches": tiers,
        "activeIncident": {
            "batchId": active.batch_id,
            "decisionId": active.decision_id,
            "status": active.status,
            "confidence": round(active.confidence * 100),
        }
        if active
        else None,
        "impactToday": impact(db, store),
        "coldChain": sorted(zones.values(), key=lambda z: -z["deltaC"])[:6],
        "weather": weather.outlook(store.lat, store.lon, utcnow()),
    }


def network(db: Session, batch: Batch) -> dict:
    s = snapshot(db, batch)
    logistics = assess_logistics(db, s)
    d = db.scalar(select(Decision).where(Decision.batch_id == batch.batch_id).order_by(Decision.created_at.desc()).limit(1))
    target = next((a.get("target") for a in (d.plan if d else []) if a["type"] == "TRANSFER"), None)
    stores = db.scalars(select(Store).where(Store.active.is_(True))).all()
    lats, lons = [st.lat for st in stores], [st.lon for st in stores]

    def xy(st: Store) -> tuple[float, float]:
        x = 0.1 + 0.8 * (st.lon - min(lons)) / ((max(lons) - min(lons)) or 1)
        y = 0.1 + 0.8 * (max(lats) - st.lat) / ((max(lats) - min(lats)) or 1)
        return round(x, 3), round(y, 3)

    cand = {c.store_id: c for c in logistics.candidates}
    nodes = []
    for st in stores:
        x, y = xy(st)
        c = cand.get(st.store_id)
        node = {
            "id": st.store_id,
            "name": st.name,
            "kind": st.kind,
            "area": st.area,
            "lat": st.lat,
            "lon": st.lon,
            "x": x,
            "y": y,
            "distanceKm": 0.0 if st.store_id == batch.store_id else distance_km(s.store, st),
            "selected": st.store_id == target,
        }
        if c:
            node.update(
                etaMin=c.eta_min,
                headroomPerH=c.headroom_per_h,
                capacity=c.free_capacity,
                absorbable=c.absorbable_units,
                score=c.score,
                verdict=c.verdict,
                transferCost=c.transfer_cost,
            )
        elif st.kind in ("b2b", "food_bank"):
            fb = logistics.b2b if st.kind == "b2b" else logistics.food_bank
            node.update(verdict="B2B fallback" if st.kind == "b2b" else "Donation fallback", unitPrice=fb.unit_price if fb else None)
        nodes.append(node)
    edges = [
        {
            "from": batch.store_id,
            "to": n["id"],
            "distanceKm": n["distanceKm"],
            "etaMin": n.get("etaMin"),
            "selected": n["selected"],
            "fallback": n["kind"] in ("b2b", "food_bank"),
        }
        for n in nodes
        if n["id"] != batch.store_id
    ]
    return {
        "batchId": batch.batch_id,
        "origin": batch.store_id,
        "nodes": nodes,
        "edges": edges,
        "candidates": [c.model_dump() for c in logistics.candidates],
        "decisionId": d.decision_id if d else None,
    }


def movements(db: Session, batch_id: str) -> list[dict]:
    rows = db.scalars(
        select(InventoryMovement).where(InventoryMovement.batch_id == batch_id).order_by(InventoryMovement.occurred_at.desc())
    ).all()
    return [
        {
            "id": m.movement_id,
            "type": m.movement_type,
            "quantity": m.quantity,
            "unitPrice": m.unit_price,
            "at": iso(m.occurred_at),
            "reason": m.reason,
            "refId": m.ref_id,
        }
        for m in rows
    ]
