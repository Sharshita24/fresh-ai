"""AI decisions: run, inspect, approve / hold / reject, and the resulting executions."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import presenters
from app.db.database import get_db, utcnow
from app.models import Decision, Execution
from app.routers.dashboard import get_batch
from app.schemas.api import BatchRef
from app.services import decision_coordinator, executor
from app.services.events import log_event
from app.services.risk import OPEN_DECISION_STATES, decision_trigger, open_decision, refresh

router = APIRouter(prefix="/api", tags=["decisions"])


def _decision(db: Session, decision_id: str) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None:
        raise HTTPException(404, f"Decision {decision_id} not found")
    return d


def _execute(db: Session, d: Decision, approved_by: str = "manager") -> Execution:
    try:
        ex = executor.execute(db, d, approved_by=approved_by)
    except executor.ExecutionError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return ex


@router.get("/decisions", summary="Recent decisions, newest first")
def list_decisions(status: str | None = None, limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    query = select(Decision).order_by(Decision.created_at.desc()).limit(limit)
    if status:
        query = query.where(Decision.status == status)
    return {"decisions": [presenters.decision_out(db, d) for d in db.scalars(query)]}


@router.get("/decisions/current", summary="The open decision (or the most recent one)")
def current_decision(db: Session = Depends(get_db)):
    d = db.scalar(select(Decision).where(Decision.status.in_(OPEN_DECISION_STATES)).order_by(Decision.created_at.desc()).limit(1))
    if d is None:  # most recent agent decision (seeded history rows carry no options)
        recent = db.scalars(select(Decision).order_by(Decision.created_at.desc()).limit(25)).all()
        d = next((x for x in recent if x.options), None)
    if d is None:
        return {
            "decisionId": None,
            "incidentId": None,
            "status": "none",
            "recommendedPlan": {
                "type": "monitor",
                "confidence": 0,
                "estimatedValuePreserved": 0,
                "kgSaved": 0,
                "co2Saved": 0,
                "actions": [],
            },
            "alternatives": [],
        }
    return presenters.decision_out(db, d)


@router.post("/decisions/score", summary="What-if: cost every option for a batch without saving a decision")
def score(body: BatchRef = Body(default_factory=BatchRef), db: Session = Depends(get_db)):
    batch = get_batch(db, body.batch_id)
    d = decision_coordinator.build(db, batch, trigger="what_if")
    db.rollback()
    return {
        "batchId": batch.batch_id,
        "confidence": d["confidence"],
        "selectedOption": d["chosen"]["id"],
        "options": d["options"],
        "evidence": d["evidence"],
        "expected": d["expected"],
        "plan": d["plan"],
        "rationale": d["rationale"],
        "weather": d["weather"],
    }


@router.post("/decisions/confirm", summary="Approve and execute the open decision for a batch (legacy)")
def confirm(body: BatchRef = Body(default_factory=BatchRef), db: Session = Depends(get_db)):
    d = open_decision(db, body.batch_id)
    if d is None:
        raise HTTPException(404, f"No open decision for {body.batch_id}")
    ex = _execute(db, d)
    return {**presenters.execution_out(ex), "status": "APPROVED", "executionId": ex.execution_id}


@router.post("/decisions/{batch_id}/run", summary="Run the agents for a batch now (manual trigger)")
def run_agents(batch_id: str, db: Session = Depends(get_db)):
    batch = get_batch(db, batch_id)
    existing = open_decision(db, batch_id)
    if existing:
        existing.status = "superseded"
    s = refresh(db, batch)
    d = decision_coordinator.create_decision(db, batch, trigger=decision_trigger(s) or "MANUAL")
    db.commit()
    return presenters.decision_out(db, d)


@router.get("/decisions/{decision_id}", summary="One decision with evidence, options and plan")
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    return presenters.decision_out(db, _decision(db, decision_id))


@router.post("/decisions/{decision_id}/approve", summary="Approve and execute a decision")
def approve(decision_id: str, db: Session = Depends(get_db)):
    return presenters.execution_out(_execute(db, _decision(db, decision_id)))


@router.post("/decisions/{decision_id}/hold", summary="Pause a proposed decision for review")
def hold(decision_id: str, db: Session = Depends(get_db)):
    d = _decision(db, decision_id)
    if d.status != "proposed":
        raise HTTPException(409, f"Decision is {d.status}")
    d.status = "held"
    log_event(
        db,
        "decision",
        "Held for manager review",
        "Auto-execution paused",
        tone="warning",
        batch_id=d.batch_id,
        data={"decisionId": d.decision_id},
    )
    db.commit()
    return presenters.decision_out(db, d)


@router.post("/decisions/{decision_id}/reject", summary="Reject a decision; the batch goes back to monitoring")
def reject(decision_id: str, db: Session = Depends(get_db)):
    d = _decision(db, decision_id)
    if d.status not in OPEN_DECISION_STATES:
        raise HTTPException(409, f"Decision is {d.status}")
    d.status, d.decided_at = "rejected", utcnow()
    log_event(
        db,
        "decision",
        "Decision rejected",
        "Manager chose to keep monitoring",
        tone="neutral",
        batch_id=d.batch_id,
        data={"decisionId": d.decision_id},
    )
    db.commit()
    return presenters.decision_out(db, d)


@router.get("/executions/{execution_id}", summary="What was executed, step by step, with webhook payloads")
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    ex = db.get(Execution, execution_id)
    if ex is None:
        raise HTTPException(404, f"Execution {execution_id} not found")
    return presenters.execution_out(ex)
