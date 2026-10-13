"""Execute an approved decision: write the ledger, call (simulated) store systems, record impact.

Every action becomes an `actions` row holding the exact webhook payload that would be sent to the
transfer, e-paper shelf label, purchasing or facilities system. If WEBHOOK_URL is set (e.g. a Slack or
Discord incoming webhook) a short summary of each action is also POSTed there for the live demo.
"""

import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import utcnow
from app.models import Action, Batch, Decision, Execution, InventoryMovement, Product, Store
from app.services.events import log_event
from app.services.risk import refresh

log = logging.getLogger("freshchain.executor")

ENDPOINTS = {
    "TRANSFER": ("/v1/transfers", 201, "Logistics dispatch"),
    "MARKDOWN": ("/v1/esl/labels:batchUpdate", 200, "Electronic shelf labels"),
    "B2B_OFFER": ("/v1/b2b/offers", 201, "B2B marketplace"),
    "DONATION": ("/v1/donations", 201, "Food rescue partner"),
    "PO_ADJUST": ("/v1/procurement/forecast-adjustments", 202, "Purchasing"),
    "MAINTENANCE": ("/v1/maintenance/tickets", 201, "Facilities"),
}


class ExecutionError(Exception):
    pass


def _move(db: Session, batch: Batch, kind: str, qty: int, ref: str, reason: str, price: float | None = None, store_id: str | None = None):
    db.add(
        InventoryMovement(
            movement_id=str(uuid4()),
            batch_id=batch.batch_id,
            store_id=store_id or batch.store_id,
            movement_type=kind,
            quantity=qty,
            unit_price=price,
            reason=reason,
            ref_id=ref,
            occurred_at=utcnow(),
        )
    )


def _notify(text: str) -> None:
    if not settings.webhook_url:
        return
    try:
        import httpx

        httpx.post(settings.webhook_url, json={"text": text, "content": text}, timeout=3.0)
    except Exception as exc:
        log.warning("Webhook notify failed: %s", exc)


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:4].upper()}"


def execute(db: Session, decision: Decision, approved_by: str = "manager") -> Execution:
    if decision.status not in ("proposed", "held"):
        raise ExecutionError(f"Decision is {decision.status}; only proposed or held decisions can be executed")
    batch = db.get(Batch, decision.batch_id)
    ex = Execution(
        execution_id=str(uuid4()), decision_id=decision.decision_id, batch_id=batch.batch_id, approved_by=approved_by, created_at=utcnow()
    )
    steps = []

    for step in decision.plan:
        kind = step["type"]
        endpoint, code, system = ENDPOINTS[kind]
        qty = int(step.get("quantity", 0))
        payload: dict
        if kind == "TRANSFER":
            target = db.get(Store, step["target"])
            transfer_id = _short_id("TO")
            payload = {
                "transfer_id": transfer_id,
                "batch_id": batch.batch_id,
                "sku": batch.sku,
                "lot_code": batch.lot_code,
                "units": qty,
                "from": batch.store_id,
                "to": target.store_id,
                "cold_chain": True,
                "eta_min": step["etaMin"],
            }
            qty = min(qty, batch.quantity_on_hand)
            _move(db, batch, "transfer_out", qty, decision.decision_id, f"{transfer_id} → {target.name}")
            batch.quantity_on_hand -= qty
            copy = Batch(
                batch_id=f"{batch.batch_id}-{target.store_id.split('-')[-1].upper()[:4]}",
                sku=batch.sku,
                store_id=target.store_id,
                supplier_id=batch.supplier_id,
                lot_code=batch.lot_code,
                harvest_date=batch.harvest_date,
                received_at=utcnow(),
                expiry_at=batch.expiry_at,
                location=f"{target.name} cold room",
                quantity_received=qty,
                quantity_on_hand=qty,
                original_price=batch.original_price,
                current_price=batch.original_price,
                parent_batch_id=batch.batch_id,
                defect_pct=batch.defect_pct,
                reference_defect_pct=batch.reference_defect_pct,
                vision_label=batch.vision_label,
                vision_checked_at=batch.vision_checked_at,
                status="active",
            )
            if db.get(Batch, copy.batch_id) is None:
                db.add(copy)
                db.flush()
                _move(db, copy, "transfer_in", qty, decision.decision_id, f"{transfer_id} from {batch.store_id}")
            title, detail = (
                f"Transfer {transfer_id} created",
                f"{qty} {db.get(Product, batch.sku).unit_label} → {target.name} · ETA {step['etaMin']} min",
            )
        elif kind == "MARKDOWN":
            labels = [f"ESL-{batch.location[-1] if batch.location[-1].isdigit() else 'X'}-{100 + i}" for i in range(1, 3)]
            payload = {
                "batch_id": batch.batch_id,
                "labels": labels,
                "units": qty,
                "price_from": step["priceFrom"],
                "price_to": step["priceTo"],
                "reason": "freshness_markdown",
                "valid_for_h": decision.expected.get("hoursLeft"),
            }
            batch.current_price = step["priceTo"]
            title, detail = (
                f"Shelf labels repriced · ₹{step['priceFrom']:.0f} → ₹{step['priceTo']:.0f}",
                f"{qty} units · {len(labels)} e-paper labels",
            )
        elif kind in ("B2B_OFFER", "DONATION"):
            qty = min(qty, batch.quantity_on_hand)
            payload = {
                "offer_id": _short_id("OF"),
                "batch_id": batch.batch_id,
                "lot_code": batch.lot_code,
                "units": qty,
                "buyer": step.get("target"),
                "unit_price": step.get("unitPrice", 0.0),
                "pickup": "today",
            }
            _move(
                db,
                batch,
                "b2b_sale" if kind == "B2B_OFFER" else "donation",
                qty,
                decision.decision_id,
                step.get("targetName", ""),
                step.get("unitPrice"),
            )
            batch.quantity_on_hand -= qty
            title, detail = ("B2B offer sent" if kind == "B2B_OFFER" else "Donation booked"), f"{qty} units → {step.get('targetName', '')}"
        elif kind == "PO_ADJUST":
            payload = {
                "sku": step["sku"],
                "store": batch.store_id,
                "adjustment_pct": step["pct"],
                "reason": "elevated_spoilage_rate",
                "effective": "next_po",
            }
            title, detail = f"Next order trimmed {abs(step['pct'])}%", "Spoilage rate fed back into purchasing"
        else:  # MAINTENANCE
            ticket = _short_id("MT")
            payload = {"ticket": ticket, "asset": step["asset"], "severity": "high", "observed": step["observed"]}
            title, detail = f"Maintenance ticket {ticket} raised", f"{step['asset']} · {step['observed']}"

        db.add(
            Action(
                action_id=str(uuid4()),
                decision_id=decision.decision_id,
                batch_id=batch.batch_id,
                action_type=kind,
                quantity=qty,
                target=step.get("target") or step.get("asset"),
                endpoint=endpoint,
                response_code=code,
                payload=payload,
                executed_at=utcnow(),
            )
        )
        steps.append(
            {
                "type": kind,
                "name": title,
                "detail": detail,
                "system": system,
                "endpoint": endpoint,
                "code": code,
                "status": "done",
                "at": utcnow().isoformat(),
                "payload": payload,
            }
        )
        log_event(
            db, "action", title, detail, tone="good", batch_id=batch.batch_id, data={"decisionId": decision.decision_id, "type": kind}
        )
        _notify(f"FreshChain · {batch.batch_id}: {title} — {detail}")

    decision.status = "executed"
    decision.decided_at = utcnow()
    batch.status = "managed"
    exp = decision.expected or {}
    ex.steps = steps
    ex.impact = {"value": exp.get("value", 0), "kg": exp.get("kgSaved", 0), "co2": exp.get("co2Saved", 0), "actions": len(steps)}
    db.add(ex)
    refresh(db, batch)
    log_event(
        db,
        "impact",
        f"Impact recorded · ₹{exp.get('value', 0):,} preserved",
        f"{exp.get('kgSaved', 0):g} kg food saved · {exp.get('co2Saved', 0):g} kg CO₂e avoided",
        tone="good",
        batch_id=batch.batch_id,
        data={"executionId": ex.execution_id},
    )
    return ex
