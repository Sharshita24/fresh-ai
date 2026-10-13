"""Analytics export: Postgres/SQLite stays operational, BigQuery is the analytics layer.

`export()` flattens decisions, actions, executions and the stock ledger into rows. With BIGQUERY_DATASET
set (and google-cloud-bigquery installed + GCP credentials) they are loaded into BigQuery; otherwise they
are written as newline-delimited JSON files that `bq load` accepts as-is.
"""

import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import as_utc
from app.models import Action, Decision, Execution, InventoryMovement


def _iso(dt):
    return as_utc(dt).isoformat() if dt else None


def rows(db: Session) -> dict[str, list[dict]]:
    return {
        "decisions": [
            {
                "decision_id": d.decision_id,
                "batch_id": d.batch_id,
                "trigger": d.trigger,
                "status": d.status,
                "confidence": d.confidence,
                "selected_option": d.selected_option,
                "model_used": d.model_used,
                "value_preserved": d.expected.get("value"),
                "kg_saved": d.expected.get("kgSaved"),
                "co2_saved": d.expected.get("co2Saved"),
                "created_at": _iso(d.created_at),
                "decided_at": _iso(d.decided_at),
            }
            for d in db.scalars(select(Decision))
        ],
        "actions": [
            {
                "action_id": a.action_id,
                "decision_id": a.decision_id,
                "batch_id": a.batch_id,
                "action_type": a.action_type,
                "quantity": a.quantity,
                "target": a.target,
                "response_code": a.response_code,
                "executed_at": _iso(a.executed_at),
            }
            for a in db.scalars(select(Action))
        ],
        "executions": [
            {
                "execution_id": e.execution_id,
                "decision_id": e.decision_id,
                "batch_id": e.batch_id,
                "approved_by": e.approved_by,
                "value": e.impact.get("value"),
                "kg": e.impact.get("kg"),
                "co2": e.impact.get("co2"),
                "created_at": _iso(e.created_at),
            }
            for e in db.scalars(select(Execution))
        ],
        "inventory_movements": [
            {
                "movement_id": m.movement_id,
                "batch_id": m.batch_id,
                "store_id": m.store_id,
                "movement_type": m.movement_type,
                "quantity": m.quantity,
                "unit_price": m.unit_price,
                "occurred_at": _iso(m.occurred_at),
                "reason": m.reason,
            }
            for m in db.scalars(select(InventoryMovement))
        ],
    }


def export(db: Session) -> dict:
    data = rows(db)
    counts = {k: len(v) for k, v in data.items()}
    if settings.bigquery_dataset:
        try:
            from google.cloud import bigquery

            client = bigquery.Client()
            config = bigquery.LoadJobConfig(autodetect=True, write_disposition="WRITE_TRUNCATE")
            for table, items in data.items():
                if items:
                    client.load_table_from_json(items, f"{settings.bigquery_dataset}.{table}", job_config=config).result()
            return {"destination": f"bigquery:{settings.bigquery_dataset}", "tables": counts}
        except Exception as exc:
            return {"destination": "bigquery", "error": str(exc), "tables": counts}

    os.makedirs(settings.export_dir, exist_ok=True)
    for table, items in data.items():
        Path(settings.export_dir, f"{table}.ndjson").write_text("".join(json.dumps(r, default=str) + "\n" for r in items))
    return {"destination": f"file:{os.path.abspath(settings.export_dir)}", "tables": counts}
