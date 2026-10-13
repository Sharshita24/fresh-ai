"""Read endpoints that feed the dashboard screens."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import presenters
from app.config import settings
from app.db.database import get_db, utcnow
from app.models import Batch, BatchImage, Decision, Event, SensorReading, Store
from app.services import weather
from app.services.risk import OPEN_DECISION_STATES, snapshot

router = APIRouter(prefix="/api", tags=["dashboard"])


def home_store(db: Session) -> Store:
    store = db.get(Store, settings.home_store_id)
    if store is None:
        raise HTTPException(503, "Store not configured — POST /api/demo/reset to load demo data")
    return store


def get_batch(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, f"Batch {batch_id} not found")
    return batch


@router.get("/store/overview", summary="Control Tower overview: risk tiers, active incident, impact, cold chain")
def store_overview(db: Session = Depends(get_db)):
    return presenters.overview(db, home_store(db))


@router.get("/inventory/summary", summary="Alias of /store/overview (legacy)")
def inventory_summary(db: Session = Depends(get_db)):
    return presenters.overview(db, home_store(db))


@router.get("/inventory/items", summary="At-risk inventory list, sorted by risk")
def inventory_items(
    status: str | None = Query(None, description="healthy | risk | critical | managed"),
    q: str | None = Query(None, description="Search name, batch id or location"),
    db: Session = Depends(get_db),
):
    store = home_store(db)
    batches = db.scalars(select(Batch).where(Batch.store_id == store.store_id, Batch.status != "closed")).all()
    items = [presenters.batch_item(db, b) for b in batches]
    if status:
        items = [i for i in items if i["status"] == status]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in f"{i['name']} {i['id']} {i['location']} {i['category']}".lower()]
    items.sort(key=lambda i: -i["risk"])
    return {"items": items}


@router.get("/inventory", summary="All batches at the store (legacy list)")
def inventory(db: Session = Depends(get_db)):
    return inventory_items(None, None, db)["items"]


@router.get("/inventory/{batch_id}", summary="One inventory row")
def inventory_batch(batch_id: str, db: Session = Depends(get_db)):
    return presenters.batch_item(db, get_batch(db, batch_id))


@router.get("/batches/{batch_id}", summary="Batch investigation: traceability, sensors, vision, demand, shelf life")
def batch_detail(batch_id: str, db: Session = Depends(get_db)):
    return presenters.batch_detail(db, get_batch(db, batch_id))


@router.get("/batches/{batch_id}/signals", summary="Latest sensor and vision signals (legacy)")
def batch_signals(batch_id: str, db: Session = Depends(get_db)):
    batch = get_batch(db, batch_id)
    s = snapshot(db, batch)
    return {
        "signals": [
            {"name": "temperature", "value": s.temp_c},
            {"name": "humidity", "value": s.humidity},
            {"name": "ethylene", "value": s.ethylene},
        ],
        "vision": {"defectPct": batch.defect_pct, "label": batch.vision_label},
        "anomalyFlags": s.flags,
    }


@router.get("/batches/{batch_id}/movements", summary="Stock ledger for a batch")
def batch_movements(batch_id: str, db: Session = Depends(get_db)):
    get_batch(db, batch_id)
    return {"movements": presenters.movements(db, batch_id)}


@router.get("/batches/{batch_id}/images", summary="Vision inspections for a batch")
def batch_images(batch_id: str, db: Session = Depends(get_db)):
    get_batch(db, batch_id)
    rows = db.scalars(select(BatchImage).where(BatchImage.batch_id == batch_id).order_by(BatchImage.uploaded_at.desc())).all()
    return {
        "images": [
            {
                "id": i.image_id,
                "type": i.image_type,
                "uploadedAt": presenters.iso(i.uploaded_at),
                "model": i.model_used,
                "defectPct": i.defect_pct,
                "label": i.label,
                "findings": i.findings,
            }
            for i in rows
        ]
    }


@router.get("/sensors/{batch_id}", summary="Recent sensor readings, newest first")
def sensor_readings(batch_id: str, limit: int = Query(60, ge=1, le=1000), db: Session = Depends(get_db)):
    get_batch(db, batch_id)
    rows = db.scalars(
        select(SensorReading).where(SensorReading.batch_id == batch_id).order_by(SensorReading.recorded_at.desc()).limit(limit)
    ).all()
    return [
        {
            "readingId": r.reading_id,
            "temperatureC": r.temperature_c,
            "humidityPercent": r.humidity_percent,
            "ethylenePpm": r.ethylene_ppm,
            "batteryPct": r.battery_pct,
            "recordedAt": presenters.iso(r.recorded_at),
            "anomalyFlags": r.anomaly_flags,
        }
        for r in rows
    ]


@router.get("/incidents/active", summary="Batches with an open decision")
def active_incidents(db: Session = Depends(get_db)):
    rows = db.scalars(select(Decision).where(Decision.status.in_(OPEN_DECISION_STATES)).order_by(Decision.created_at.desc())).all()
    return [
        {
            "batchId": d.batch_id,
            "decisionId": d.decision_id,
            "status": d.status,
            "confidence": round(d.confidence * 100),
            "trigger": d.trigger,
        }
        for d in rows
    ]


@router.get("/history/events", summary="Audit trail, newest first")
def history_events(
    kind: str | None = Query(None, description="sensor | vision | agent | decision | action | impact | intake"),
    batch_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(Event).order_by(Event.occurred_at.desc(), Event.event_id.desc()).limit(limit)
    if kind:
        query = query.where(Event.kind == kind)
    if batch_id:
        query = query.where(Event.batch_id == batch_id)
    return {"events": [presenters.event_out(e) for e in db.scalars(query)]}


@router.get("/network/graph", summary="Redistribution network for a batch, with destination scores")
def network_graph(batch_id: str = "STB-042", db: Session = Depends(get_db)):
    return presenters.network(db, get_batch(db, batch_id))


@router.get("/network/impact", summary="Value, food and CO₂e saved today, plus the last 7 days")
def network_impact(db: Session = Depends(get_db)):
    return presenters.impact(db, home_store(db))


@router.get("/weather", summary="Live weather outlook for the store (Open-Meteo)")
def store_weather(db: Session = Depends(get_db)):
    store = home_store(db)
    return weather.outlook(store.lat, store.lon, utcnow())
