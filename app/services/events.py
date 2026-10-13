from datetime import datetime

from sqlalchemy.orm import Session

from app.db.database import utcnow
from app.models import Event


def log_event(
    db: Session,
    kind: str,
    title: str,
    detail: str = "",
    tone: str = "neutral",
    batch_id: str | None = None,
    data: dict | None = None,
    at: datetime | None = None,
) -> Event:
    event = Event(kind=kind, title=title, detail=detail, tone=tone, batch_id=batch_id, data=data or {}, occurred_at=at or utcnow())
    db.add(event)
    return event
