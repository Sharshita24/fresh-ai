
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class InventoryBatchDB(Base):
    __tablename__ = "inventory_batches"

    batch_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(20), default="units")
    location: Mapped[str] = mapped_column(String(100))
    current_price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[float] = mapped_column(Float)
    estimated_remaining_shelf_life_hours: Mapped[float] = mapped_column(Float)
    demand_velocity_units_per_hour: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="HEALTHY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SensorReadingDB(Base):
    __tablename__ = "sensor_readings"

    reading_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_batches.batch_id"),
        index=True,
    )
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_percent: Mapped[float] = mapped_column(Float)
    ethylene_ppm: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    anomaly_flags: Mapped[list] = mapped_column(JSON, default=list)


class AgentAssessmentDB(Base):
    __tablename__ = "agent_assessments"

    assessment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id"),
        index=True,
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_batches.batch_id"),
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(50))
    result: Mapped[dict] = mapped_column(JSON)


class DecisionDB(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_batches.batch_id"),
        index=True,
    )
    quality_assessment: Mapped[dict] = mapped_column(JSON)
    pricing_assessment: Mapped[dict] = mapped_column(JSON)
    logistics_assessment: Mapped[dict] = mapped_column(JSON)
    selected_actions: Mapped[list] = mapped_column(JSON)
    evidence_summary: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ActionDB(Base):
    __tablename__ = "actions"

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id"),
        index=True,
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_batches.batch_id"),
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class StoreProfileDB(Base):
    __tablename__ = "store_profiles"

    store_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    area: Mapped[str] = mapped_column(String(100))
    manager: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class NetworkNodeDB(Base):
    __tablename__ = "network_nodes"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(50))
    demand: Mapped[float] = mapped_column(Float, default=0.0)
    risk: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[float] = mapped_column(Float, default=0.0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    destination_id: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ExecutionRecordDB(Base):
    __tablename__ = "execution_records"

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decisions.decision_id"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_batches.batch_id"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    steps: Mapped[dict] = mapped_column(JSON, default=dict)
    transfer_destination: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transfer_eta_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
