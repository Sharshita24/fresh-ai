"""Batch intake from an admin form (JSON) or a warehouse CSV export."""

import csv
import io
from datetime import date, datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.models import Batch, InventoryMovement, Product, Store, Supplier
from app.services.events import log_event
from app.services.risk import refresh

CSV_COLUMNS = [
    "batch_id",
    "sku",
    "store_id",
    "supplier_id",
    "lot_code",
    "harvest_date",
    "received_at",
    "expiry_at",
    "quantity",
    "price",
    "location",
    "sensor_id",
]


class BatchIntake(BaseModel):
    batch_id: str = Field(min_length=3, max_length=50)
    sku: str
    store_id: str = "store-042"
    supplier_id: str | None = None
    lot_code: str = Field(min_length=1, max_length=50)
    harvest_date: date | None = None
    received_at: datetime | None = None
    expiry_at: datetime
    quantity: int = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    location: str = ""
    sensor_id: str | None = None

    @model_validator(mode="after")
    def _dates(self):
        # store everything in UTC; naive timestamps are read as UTC
        recv = self.received_at or datetime.now(timezone.utc)
        recv = (recv if recv.tzinfo else recv.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        exp = self.expiry_at
        self.expiry_at = (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
        if self.expiry_at <= recv:
            raise ValueError("expiry_at must be after received_at")
        self.received_at = recv
        return self


def create_batch(db: Session, data: BatchIntake) -> Batch:
    if db.get(Batch, data.batch_id):
        raise ValueError(f"Batch {data.batch_id} already exists")
    product = db.get(Product, data.sku)
    if product is None:
        raise ValueError(f"Unknown SKU {data.sku}")
    if db.get(Store, data.store_id) is None:
        raise ValueError(f"Unknown store {data.store_id}")
    if data.supplier_id and db.get(Supplier, data.supplier_id) is None:
        raise ValueError(f"Unknown supplier {data.supplier_id}")
    price = data.price or product.base_price
    batch = Batch(
        batch_id=data.batch_id,
        sku=data.sku,
        store_id=data.store_id,
        supplier_id=data.supplier_id,
        lot_code=data.lot_code,
        harvest_date=data.harvest_date,
        received_at=data.received_at,
        expiry_at=data.expiry_at,
        location=data.location,
        sensor_id=data.sensor_id,
        quantity_received=data.quantity,
        quantity_on_hand=data.quantity,
        original_price=price,
        current_price=price,
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
            quantity=data.quantity,
            unit_price=price,
            occurred_at=data.received_at,
            reason=f"Lot {data.lot_code}",
        )
    )
    refresh(db, batch)
    log_event(
        db,
        "intake",
        f"Batch received · {product.name}",
        f"{data.quantity} {product.unit_label} · lot {data.lot_code}",
        tone="info",
        batch_id=batch.batch_id,
    )
    return batch


def import_csv(db: Session, text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in ("batch_id", "sku", "lot_code", "expiry_at", "quantity") if c not in (reader.fieldnames or [])]
    if missing:
        return {"created": [], "errors": [{"row": 1, "error": f"Missing columns: {', '.join(missing)}"}]}
    created, errors = [], []
    for i, row in enumerate(reader, start=2):
        clean = {k: v.strip() for k, v in row.items() if k in CSV_COLUMNS and v and v.strip()}
        try:
            with db.begin_nested():
                created.append(create_batch(db, BatchIntake(**clean)).batch_id)
        except (ValidationError, ValueError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            errors.append({"row": i, "batchId": clean.get("batch_id"), "error": msg})
    return {"created": created, "errors": errors}
