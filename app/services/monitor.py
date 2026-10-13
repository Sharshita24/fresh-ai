"""The "cron": a periodic sweep that refreshes every batch's risk and runs agents where rules say so.

Events (sensor readings, sales, photos) trigger decisions immediately; this sweep catches slow-burning
risk such as demand drying up or expiry creeping closer, every MONITOR_INTERVAL_SECONDS.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.models import Batch
from app.services.pipeline import maybe_decide
from app.services.risk import refresh

log = logging.getLogger("freshchain.monitor")


def run_once(db: Session) -> dict:
    checked, decisions = 0, []
    for batch in db.scalars(select(Batch).where(Batch.status.in_(("active", "managed")))).all():
        checked += 1
        if batch.status == "active":
            d = maybe_decide(db, batch)
            if d:
                decisions.append({"decisionId": d.decision_id, "batchId": d.batch_id, "trigger": d.trigger})
        else:
            refresh(db, batch)
    db.commit()
    return {"checked": checked, "decisionsCreated": decisions}


async def loop() -> None:
    interval = settings.monitor_interval_s
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_sweep)
        except Exception:  # keep the monitor alive whatever happens in one sweep
            log.exception("Monitor sweep failed")


def _sweep() -> None:
    with SessionLocal() as db:
        result = run_once(db)
        if result["decisionsCreated"]:
            log.info("Monitor created %d decision(s)", len(result["decisionsCreated"]))
