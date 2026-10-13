"""ORM models.

Batch identity follows the blueprint: same SKU + supplier + lot + receive date = one batch.
Quantity on hand is driven by the `inventory_movements` ledger, never edited directly.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base, utcnow


class Store(Base):
    """Any location stock can sit in or move to: stores, micro-hubs, dark stores, B2B buyers, food banks."""

    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="store")  # store | hub | dark_store | b2b | food_bank
    city: Mapped[str] = mapped_column(String(60), default="Bengaluru")
    area: Mapped[str] = mapped_column(String(60), default="")
    manager: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    cold_capacity_units: Mapped[int] = mapped_column(Integer, default=0)
    cold_room_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    footfall_baseline_per_h: Mapped[float] = mapped_column(Float, default=0.0)
    # per-SKU demand: {"strawberry-250g": {"demand_per_h": 13.4, "supplied_per_h": 6.9, "forecast_per_h": 5.5}}
    demand_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    price_factor: Mapped[float | None] = mapped_column(Float, nullable=True)  # B2B buy price as share of retail
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # store-wide aggregates (SKU count, sensors, untracked tiers)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(60), default="")


class Product(Base):
    """SKU master with the physics FreshChain needs: storage range and temperature sensitivity."""

    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    variant: Mapped[str] = mapped_column(String(60), default="")
    category: Mapped[str] = mapped_column(String(30))
    icon: Mapped[str] = mapped_column(String(20), default="")  # UI icon key
    unit_label: Mapped[str] = mapped_column(String(20), default="units")
    unit_kg: Mapped[float] = mapped_column(Float, default=0.25)
    case_size: Mapped[int] = mapped_column(Integer, default=12)
    storage_min_c: Mapped[float] = mapped_column(Float)
    storage_max_c: Mapped[float] = mapped_column(Float)
    ref_temp_c: Mapped[float] = mapped_column(Float)  # temperature the printed expiry assumes
    q10: Mapped[float] = mapped_column(Float, default=2.5)  # decay speed-up per +10 °C
    defect_weight: Mapped[float] = mapped_column(Float, default=1.4)  # shelf-life lost per unit of visible defect
    humidity_max: Mapped[float] = mapped_column(Float, default=95.0)
    ethylene_max_ppm: Mapped[float] = mapped_column(Float, default=1.5)
    markdown_elasticity: Mapped[float] = mapped_column(Float, default=2.6)  # +x% demand per 1% discount
    base_price: Mapped[float] = mapped_column(Float)


class Batch(Base):
    __tablename__ = "batches"

    batch_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"), index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.supplier_id"), nullable=True)
    lot_code: Mapped[str] = mapped_column(String(50), default="")
    harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expiry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(100), default="")
    sensor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity_received: Mapped[int] = mapped_column(Integer)
    quantity_on_hand: Mapped[int] = mapped_column(Integer)
    original_price: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    parent_batch_id: Mapped[str | None] = mapped_column(String(50), nullable=True)  # set on transfer copies
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | managed | closed
    # cached risk snapshot, refreshed by the monitor and on every event
    defect_pct: Mapped[float] = mapped_column(Float, default=0.0)
    reference_defect_pct: Mapped[float] = mapped_column(Float, default=0.0)  # at intake, for before/after comparisons
    vision_label: Mapped[str] = mapped_column(String(60), default="Not inspected")
    vision_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    est_shelf_life_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_tier: Mapped[str] = mapped_column(String(20), default="healthy")
    signals: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    reading_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    store_id: Mapped[str] = mapped_column(String(50))
    sensor_id: Mapped[str] = mapped_column(String(50), default="")
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_percent: Mapped[float] = mapped_column(Float)
    ethylene_ppm: Mapped[float] = mapped_column(Float)
    battery_pct: Mapped[float] = mapped_column(Float, default=100.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list)


class InventoryMovement(Base):
    """The stock ledger: every change to quantity is one row."""

    __tablename__ = "inventory_movements"

    movement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    store_id: Mapped[str] = mapped_column(String(50))
    movement_type: Mapped[str] = mapped_column(String(20))  # receive | sale | transfer_out | transfer_in | b2b_sale | donation | loss
    quantity: Mapped[int] = mapped_column(Integer)  # always positive; the type gives the direction
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FootfallSample(Base):
    __tablename__ = "footfall"
    __table_args__ = (UniqueConstraint("store_id", "hour_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"), index=True)
    hour_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer)


class BatchImage(Base):
    __tablename__ = "batch_images"

    image_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    image_type: Mapped[str] = mapped_column(String(20), default="alert")  # reference | alert
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_used: Mapped[str] = mapped_column(String(60))
    defect_pct: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(60))
    findings: Mapped[dict] = mapped_column(JSON, default=dict)


class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.batch_id"), index=True)
    trigger: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | held | executed | rejected
    confidence: Mapped[float] = mapped_column(Float)
    selected_option: Mapped[str] = mapped_column(String(60))
    plan: Mapped[list] = mapped_column(JSON, default=list)  # actions to execute
    options: Mapped[list] = mapped_column(JSON, default=list)  # every option evaluated
    evidence: Mapped[list] = mapped_column(JSON, default=list)  # signal → evidence → impact
    rationale: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[dict] = mapped_column(JSON, default=dict)  # value, kg, co2, waste before/after
    model_used: Mapped[str] = mapped_column(String(60), default="rules")
    model_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentAssessment(Base):
    __tablename__ = "agent_assessments"

    assessment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    agent_name: Mapped[str] = mapped_column(String(30))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Action(Base):
    """One executed step, with the (simulated) webhook call that carried it out."""

    __tablename__ = "actions"

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    action_type: Mapped[str] = mapped_column(String(20))  # TRANSFER | MARKDOWN | B2B_OFFER | DONATION | PO_ADJUST | MAINTENANCE
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="succeeded")
    endpoint: Mapped[str] = mapped_column(String(100))
    response_code: Mapped[int] = mapped_column(Integer, default=200)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Execution(Base):
    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.decision_id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    approved_by: Mapped[str] = mapped_column(String(30), default="manager")  # manager | autonomous
    steps: Mapped[list] = mapped_column(JSON, default=list)
    impact: Mapped[dict] = mapped_column(JSON, default=dict)  # value, kg, co2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Event(Base):
    """Audit trail behind the History screen."""

    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # sensor | vision | agent | decision | action | impact | intake | sale | system
    tone: Mapped[str] = mapped_column(String(10), default="neutral")  # neutral | info | good | warning | critical
    batch_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(String(400), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
