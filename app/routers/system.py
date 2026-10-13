"""Health, the monitor sweep, demo controls and analytics export."""

from datetime import timedelta

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import presenters
from app.config import settings
from app.db.database import SessionLocal, get_db, utcnow
from app.models import Product, Store
from app.routers.dashboard import get_batch
from app.schemas.api import DemoIncidentIn
from app.services import analytics, monitor, pipeline, seed
from app.services.anomaly_engine import temperature_threshold
from app.services.risk import baseline_temp, snapshot
from app.services.sensor_simulator import temperature_ramp

router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {"project": "FreshChain AI", "status": "running", "docs": "/docs"}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # pragma: no cover
        database = f"error: {exc.__class__.__name__}"
    return {
        "status": "healthy" if database == "ok" else "degraded",
        "database": database,
        "databaseEngine": settings.database_url.split(":", 1)[0],
        "ai": {
            "provider": "gemini" if settings.gemini_enabled else "rules",
            "model": settings.gemini_model if settings.gemini_enabled else None,
        },
        "monitorIntervalS": settings.monitor_interval_s,
        "autoExecute": settings.auto_execute,
    }


@router.post("/api/monitor/run", tags=["system"], summary="Run the monitor sweep now (normally every MONITOR_INTERVAL_SECONDS)")
def run_monitor(db: Session = Depends(get_db)):
    return monitor.run_once(db)


@router.post("/api/demo/reset", tags=["demo"], summary="Rebuild the database with fresh demo data")
def demo_reset():
    seed.reset_data()
    with SessionLocal() as db:
        return {"status": "reset", "store": presenters.overview(db, db.get(Store, settings.home_store_id))["store"]}


@router.post("/api/demo/incident", tags=["demo"], summary="Play the cold-chain incident: chiller warms past the rule, agents decide")
def demo_incident(body: DemoIncidentIn = Body(default_factory=DemoIncidentIn), db: Session = Depends(get_db)):
    batch = get_batch(db, body.batch_id)
    product = db.get(Product, batch.sku)
    s = snapshot(db, batch)
    start = baseline_temp(db, batch, s.store, product, utcnow())
    peak = body.peak_c if body.peak_c is not None else round(temperature_threshold(product) + 0.2, 1)
    ramp = temperature_ramp(start, peak)
    now = utcnow()
    decision = None
    for i, t in enumerate(ramp):  # one reading per minute, ending now
        _, d = pipeline.ingest_reading(
            db, batch, t, s.humidity or 91.0, s.ethylene or 0.4, recorded_at=now - timedelta(minutes=len(ramp) - 1 - i)
        )
        decision = decision or d
    db.commit()
    return {"readings": ramp, "decision": presenters.decision_out(db, decision) if decision else None}


@router.post("/api/analytics/export", tags=["system"], summary="Export decisions, actions and the ledger to BigQuery (or NDJSON files)")
def export_analytics(db: Session = Depends(get_db)):
    return analytics.export(db)
