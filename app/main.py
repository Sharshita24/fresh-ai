
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.data.sample_inventory import SAMPLE_INVENTORY
from app.db.database import Base, SessionLocal, engine, get_db
from app.models import (
    AgentAssessmentDB,
    DecisionDB,
    InventoryBatchDB,
    SensorReadingDB,
)
from app.schemas.api import (
    CurrentDecisionResponse,
    ExecutionResponse,
    HistoryEventsResponse,
    InventoryItemsResponse,
    NetworkGraphResponse,
    NetworkImpactResponse,
    StoreOverviewResponse,
)
from app.schemas.decisions import DecisionPlan
from app.schemas.inventory import InventoryBatch
from app.schemas.sensors import (
    SensorReading,
    SensorSimulationRequest,
)
from app.services.anomaly_engine import detect_anomalies
from app.services.decision_coordinator import create_decision
from app.services.sensor_simulator import simulate_reading
from app.models import (
    ExecutionRecordDB,
    NetworkNodeDB,
    StoreProfileDB,
)

app = FastAPI(
    title="FreshChain AI",
    description="AI-powered perishable inventory management",
    version="0.4.0",
)


def _latest_batch_reading(db: Session, batch_id: str):
    return (
        db.query(SensorReadingDB)
        .filter(SensorReadingDB.batch_id == batch_id)
        .order_by(SensorReadingDB.recorded_at.desc())
        .first()
    )


def _risk_tier_from_flags(flags: list[str]) -> str:
    if "HIGH_TEMPERATURE" in flags or "HIGH_ETHYLENE" in flags:
        return "critical"
    if flags:
        return "risk"
    return "healthy"


def _inventory_status_details(db: Session, batch_id: str):
    latest = _latest_batch_reading(db, batch_id)
    flags = latest.anomaly_flags if latest else []
    tier = _risk_tier_from_flags(flags)
    risk_score = 38 if flags else 12
    return {
        "status": tier,
        "risk": risk_score,
        "signals": flags or ["Demand ↓"],
    }


def _decision_payload(decision: DecisionDB):
    return {
        "decision_id": decision.decision_id,
        "batch_id": decision.batch_id,
        "quality_assessment": decision.quality_assessment,
        "pricing_assessment": decision.pricing_assessment,
        "logistics_assessment": decision.logistics_assessment,
        "selected_actions": decision.selected_actions,
        "evidence_summary": decision.evidence_summary,
        "status": decision.status,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
    }


def _store_profile(db: Session):
    profile = db.query(StoreProfileDB).first()
    if profile is None:
        profile = StoreProfileDB(
            store_id="store-042",
            name="Store #042",
            city="Bengaluru",
            area="Brookefield",
            manager="Store Manager",
        )
        db.add(profile)
        db.commit()
    return profile


def _network_seed(db: Session):
    if db.query(NetworkNodeDB).count() == 0:
        db.add_all(
            [
                NetworkNodeDB(
                    node_id="store-042",
                    node_type="store",
                    demand=4.2,
                    risk=38,
                    capacity=0.0,
                    distance_km=0.0,
                    destination_id="hub-02",
                ),
                NetworkNodeDB(
                    node_id="hub-02",
                    node_type="hub",
                    demand=0.0,
                    risk=0,
                    capacity=320.0,
                    distance_km=2.4,
                    destination_id=None,
                ),
            ]
        )
        db.commit()


@app.on_event("startup")
def initialize_database():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for batch in SAMPLE_INVENTORY:
            existing = db.get(InventoryBatchDB, batch.batch_id)
            if existing is None:
                db.add(InventoryBatchDB(**batch.model_dump()))

        profile = db.query(StoreProfileDB).first()
        if profile is None:
            db.add(
                StoreProfileDB(
                    store_id="store-042",
                    name="Store #042",
                    city="Bengaluru",
                    area="Brookefield",
                    manager="Store Manager",
                )
            )

        _network_seed(db)
        db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "project": "FreshChain AI",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get(
    "/api/inventory",
    response_model=list[InventoryBatch],
)
def get_inventory(db: Session = Depends(get_db)):
    inventory = []
    for batch in db.query(InventoryBatchDB).all():
        status_details = _inventory_status_details(db, batch.batch_id)
        batch.status = status_details["status"]
        inventory.append(batch)
    return inventory


@app.get("/api/inventory/items", response_model=InventoryItemsResponse)
def get_inventory_items(db: Session = Depends(get_db)):
    items = []
    for batch in db.query(InventoryBatchDB).all():
        status_details = _inventory_status_details(db, batch.batch_id)
        status = status_details["status"]
        risk = status_details["risk"]
        signals = status_details["signals"]
        items.append(
            {
                "id": batch.batch_id,
                "name": batch.product_name,
                "variant": "default pack",
                "category": "Produce",
                "risk": risk,
                "status": status,
                "shelfLifeH": float(batch.estimated_remaining_shelf_life_hours),
                "printedShelfH": float(batch.estimated_remaining_shelf_life_hours),
                "signals": signals,
                "price": float(batch.current_price),
                "location": batch.location,
                "action": "Monitor" if status == "healthy" else "Review",
            }
        )
    return {"items": items}


@app.get(
    "/api/inventory/{batch_id}",
    response_model=InventoryBatch,
)
def get_inventory_batch(
    batch_id: str,
    db: Session = Depends(get_db),
):
    batch = db.get(InventoryBatchDB, batch_id)

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {batch_id} not found",
        )

    return batch


@app.get("/api/store/overview", response_model=StoreOverviewResponse)
def get_store_overview(db: Session = Depends(get_db)):
    batches = db.query(InventoryBatchDB).all()
    profile = _store_profile(db)
    risk_summary = {
        "healthy": 0,
        "risk": 0,
        "critical": 0,
        "managed": 0,
    }

    latest_decisions = db.query(DecisionDB).order_by(DecisionDB.created_at.desc()).all()
    active_incident = None

    for batch in batches:
        status_details = _inventory_status_details(db, batch.batch_id)
        tier = status_details["status"]
        risk_summary[tier] += 1

    if latest_decisions:
        latest_decision = latest_decisions[0]
        active_incident = {
            "batchId": latest_decision.batch_id,
            "status": "anomaly_detected",
            "confidence": 92,
        }

    return {
        "store": {
            "id": profile.store_id,
            "name": profile.name,
            "city": profile.city,
            "area": profile.area,
            "manager": profile.manager,
            "skus": len(batches),
            "sensors": max(1, len(batches) * 2),
        },
        "riskSummary": risk_summary,
        "activeIncident": active_incident,
    }


@app.get("/api/incidents/active")
def get_active_incidents(db: Session = Depends(get_db)):
    incidents = []
    for batch in db.query(InventoryBatchDB).all():
        latest = _latest_batch_reading(db, batch.batch_id)
        if latest and latest.anomaly_flags:
            incidents.append(
                {
                    "batchId": batch.batch_id,
                    "status": "anomaly_detected",
                    "confidence": 92,
                    "severity": _risk_tier_from_flags(latest.anomaly_flags),
                }
            )
    return incidents


@app.get("/api/inventory/summary")
def get_inventory_summary(db: Session = Depends(get_db)):
    return get_store_overview(db)


@app.get("/api/history/events", response_model=HistoryEventsResponse)
def get_history_events(db: Session = Depends(get_db)):
    events = []
    decisions = db.query(DecisionDB).order_by(DecisionDB.created_at.desc()).all()

    for idx, decision in enumerate(decisions):
        action_group = "pricing"
        if any(action in decision.selected_actions for action in ["REDISTRIBUTE", "B2B_OFFLOAD", "DONATE"]):
            action_group = "logistics"
        elif any(action in decision.selected_actions for action in ["MARKDOWN"]):
            action_group = "pricing"

        events.append(
            {
                "id": f"evt-{idx + 1001}",
                "timestamp": decision.created_at.isoformat(),
                "group": action_group,
                "title": f"Decision generated for {decision.batch_id}",
                "status": "executed",
                "summary": " | ".join(decision.evidence_summary),
            }
        )

    if not events:
        return {"events": []}

    return {"events": events}


@app.get("/api/batches/{batch_id}")
def get_batch_detail(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(InventoryBatchDB, batch_id)
    if batch is None:
        raise HTTPException(404, detail=f"Batch {batch_id} not found")

    latest = _latest_batch_reading(db, batch_id)
    flags = latest.anomaly_flags if latest else []
    return {
        "batch": {
            "id": batch.batch_id,
            "name": batch.product_name,
            "variant": "250 g punnet",
            "supplier": "Nandi Hills Farms",
            "receivedAt": batch.created_at.isoformat(),
            "location": batch.location,
            "risk": 38 if flags else 12,
            "shelfLifeH": float(batch.estimated_remaining_shelf_life_hours),
            "printedShelfH": float(batch.estimated_remaining_shelf_life_hours),
            "price": float(batch.current_price),
            "units": batch.quantity,
            "temp": {
                "baseline": 4.0,
                "now": float(latest.temperature_c) if latest else 4.0,
                "safe": [1, 5],
                "threshold": 7.0,
            },
            "humidity": float(latest.humidity_percent) if latest else 65.0,
            "ethylene": float(latest.ethylene_ppm) if latest else 0.8,
            "vision": {
                "defectPct": 2 if flags else 0,
                "label": "Within tolerance" if not flags else "Attention required",
                "inspectedAt": "2026-10-11T08:00:00Z",
            },
            "demand": {
                "rate": float(batch.demand_velocity_units_per_hour),
                "forecast": float(batch.demand_velocity_units_per_hour + 1.3),
                "history": [6.1, 5.8, 5.9, 5.6, 5.2, 5.4, 4.9, 4.6],
            },
        },
        "signals": [
            {"type": "temperature", "value": float(latest.temperature_c) if latest else 4.0},
            {"type": "humidity", "value": float(latest.humidity_percent) if latest else 65.0},
            {"type": "ethylene", "value": float(latest.ethylene_ppm) if latest else 0.8},
        ],
    }


@app.get("/api/batches/{batch_id}/signals")
def get_batch_signals(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(InventoryBatchDB, batch_id)
    if batch is None:
        raise HTTPException(404, detail=f"Batch {batch_id} not found")
    latest = _latest_batch_reading(db, batch_id)
    flags = latest.anomaly_flags if latest else []
    return {
        "signals": [
            {"name": "temperature", "value": float(latest.temperature_c) if latest else 4.0},
            {"name": "humidity", "value": float(latest.humidity_percent) if latest else 65.0},
            {"name": "ethylene", "value": float(latest.ethylene_ppm) if latest else 0.8},
        ],
        "vision": {
            "defectPct": 2 if flags else 0,
            "label": "Within tolerance" if not flags else "Attention required",
        },
    }


@app.post(
    "/api/sensors/simulate",
    response_model=SensorReading,
)
def simulate_sensor_reading(
    request: SensorSimulationRequest,
    db: Session = Depends(get_db),
):
    batch = db.get(InventoryBatchDB, request.batch_id)

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {request.batch_id} not found",
        )

    reading_input = simulate_reading(
        batch_id=request.batch_id,
        scenario=request.scenario,
    )

    reading = SensorReadingDB(
        **reading_input.model_dump(),
        reading_id=str(uuid4()),
        anomaly_flags=detect_anomalies(reading_input),
    )

    db.add(reading)
    db.commit()
    db.refresh(reading)

    return reading


@app.get(
    "/api/sensors/{batch_id}",
    response_model=list[SensorReading],
)
def get_sensor_readings(
    batch_id: str,
    db: Session = Depends(get_db),
):
    if db.get(InventoryBatchDB, batch_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {batch_id} not found",
        )

    return (
        db.query(SensorReadingDB)
        .filter(SensorReadingDB.batch_id == batch_id)
        .order_by(SensorReadingDB.recorded_at.desc())
        .all()
    )


@app.get("/api/decisions/current", response_model=CurrentDecisionResponse)
def get_current_decision(db: Session = Depends(get_db)):
    latest_decision = (
        db.query(DecisionDB)
        .order_by(DecisionDB.created_at.desc())
        .first()
    )
    if latest_decision is None:
        return {
            "incidentId": "none",
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

    selected_actions = latest_decision.selected_actions
    batch = db.get(InventoryBatchDB, latest_decision.batch_id)
    units = batch.quantity if batch else 0
    price = float(batch.current_price) if batch else 0.0
    base_value = units * price
    markdown_pct = 0.0
    for assessment in [
        latest_decision.pricing_assessment,
    ]:
        markdown_pct = float(assessment.get("recommended_markdown_percent", 0.0))

    estimated_value_preserved = base_value * (1 - (markdown_pct / 100) * 0.5)
    kg_saved = max(0.0, units * 0.2)
    co2_saved = kg_saved * 2.5

    actions = []
    if "MARKDOWN" in selected_actions:
        actions.append({"type": "markdown", "pct": markdown_pct, "units": units})
    if "REDISTRIBUTE" in selected_actions:
        actions.append({"type": "transfer", "units": min(units, 84), "destination": "hub-02", "etaMin": 18})
    if "B2B_OFFLOAD" in selected_actions:
        actions.append({"type": "b2b_offload", "units": units, "destination": "secondary_buyer_network"})

    return {
        "incidentId": latest_decision.batch_id,
        "recommendedPlan": {
            "type": "transfer_and_markdown" if "REDISTRIBUTE" in selected_actions else "markdown",
            "confidence": 92,
            "estimatedValuePreserved": round(float(estimated_value_preserved), 2),
            "kgSaved": round(float(kg_saved), 2),
            "co2Saved": round(float(co2_saved), 2),
            "actions": actions,
        },
        "alternatives": [
            {"type": "do_nothing", "expectedWaste": round(float(units * 0.4), 2)},
            {"type": "markdown_only", "expectedWaste": round(float(units * 0.15), 2)},
        ],
    }


@app.post("/api/decisions/score")
def score_decision(payload: dict, db: Session = Depends(get_db)):
    batch_id = payload.get("batch_id") or "STB-042"
    return get_current_decision(db)


@app.post("/api/decisions/confirm")
def confirm_decision(payload: dict, db: Session = Depends(get_db)):
    batch_id = payload.get("batch_id") or "STB-042"
    decision = (
        db.query(DecisionDB)
        .filter(DecisionDB.batch_id == batch_id)
        .order_by(DecisionDB.created_at.desc())
        .first()
    )
    if decision is None:
        return {"status": "APPROVED", "executionId": f"EX-{batch_id}"}
    decision.status = "APPROVED"
    db.add(decision)
    db.commit()
    return {"status": "APPROVED", "executionId": f"EX-{batch_id}"}


@app.post(
    "/api/decisions/{batch_id}/run",
    response_model=DecisionPlan,
)
def run_decision(
    batch_id: str,
    db: Session = Depends(get_db),
):
    batch_db = db.get(InventoryBatchDB, batch_id)
    if batch_db is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {batch_id} not found",
        )

    latest_reading = _latest_batch_reading(db, batch_id)
    if latest_reading is None:
        raise HTTPException(
            status_code=400,
            detail="Simulate a sensor reading before running agents.",
        )

    batch = InventoryBatch.model_validate(batch_db)
    reading = SensorReading.model_validate(latest_reading)
    plan = create_decision(batch, reading)

    decision_row = DecisionDB(
        decision_id=plan.decision_id,
        batch_id=plan.batch_id,
        quality_assessment=plan.quality_assessment.model_dump(mode="json"),
        pricing_assessment=plan.pricing_assessment.model_dump(mode="json"),
        logistics_assessment=plan.logistics_assessment.model_dump(mode="json"),
        selected_actions=plan.selected_actions,
        evidence_summary=plan.evidence_summary,
        status=plan.status,
        created_at=plan.created_at,
    )

    assessments = [
        ("quality", plan.quality_assessment.model_dump(mode="json")),
        ("pricing", plan.pricing_assessment.model_dump(mode="json")),
        ("logistics", plan.logistics_assessment.model_dump(mode="json")),
    ]

    try:
        db.add(decision_row)
        db.flush()
        for agent_name, result in assessments:
            db.add(
                AgentAssessmentDB(
                    assessment_id=str(uuid4()),
                    decision_id=plan.decision_id,
                    batch_id=batch_id,
                    agent_name=agent_name,
                    result=result,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return plan


@app.get("/api/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    record = db.get(ExecutionRecordDB, execution_id)
    if record is None:
        decision = (
            db.query(DecisionDB)
            .order_by(DecisionDB.created_at.desc())
            .first()
        )
        if decision is None:
            return {
                "executionId": execution_id,
                "incidentId": None,
                "status": "in_progress",
                "steps": [],
                "transfer": {"id": "TO-7781", "destination": "hub-02", "etaMin": 18},
                "ticket": {"id": execution_id},
            }
        record = ExecutionRecordDB(
            execution_id=execution_id,
            decision_id=decision.decision_id,
            batch_id=decision.batch_id,
            status="in_progress",
            steps={
                "Create markdown": "done",
                "Transfer to hub": "in_progress",
                "Notify B2B buyer": "pending",
            },
            transfer_destination="hub-02",
            transfer_eta_min=18,
        )
        db.add(record)
        db.commit()

    return {
        "executionId": record.execution_id,
        "incidentId": record.batch_id,
        "status": record.status,
        "steps": [
            {"name": name, "status": value}
            for name, value in record.steps.items()
        ],
        "transfer": {
            "id": f"TO-{record.execution_id[:6]}",
            "destination": record.transfer_destination or "hub-02",
            "etaMin": record.transfer_eta_min or 18,
        },
        "ticket": {"id": record.batch_id},
    }


@app.get("/api/network/graph", response_model=NetworkGraphResponse)
def get_network_graph(db: Session = Depends(get_db)):
    _network_seed(db)
    nodes = db.query(NetworkNodeDB).all()
    graph = {
        "nodes": [
            {
                "id": node.node_id,
                "type": node.node_type,
                "demand": float(node.demand),
                "risk": int(node.risk),
                "capacity": float(node.capacity),
                "distanceKm": float(node.distance_km),
            }
            for node in nodes
        ],
        "edges": [],
    }

    store_nodes = [node for node in nodes if node.node_type == "store"]
    hub_nodes = [node for node in nodes if node.node_type == "hub"]
    for store in store_nodes:
        for hub in hub_nodes:
            graph["edges"].append(
                {
                    "from": store.node_id,
                    "to": hub.node_id,
                    "distanceKm": float(hub.distance_km or 2.4),
                    "etaMin": 18,
                }
            )

    return graph


@app.get("/api/network/impact", response_model=NetworkImpactResponse)
def get_network_impact(db: Session = Depends(get_db)):
    total_kg = 0.0
    total_value = 0.0
    for batch in db.query(InventoryBatchDB).all():
        latest = _latest_batch_reading(db, batch.batch_id)
        if latest and latest.anomaly_flags:
            total_kg += max(0.0, batch.quantity * 0.2)
            total_value += batch.current_price * max(0.0, batch.quantity * 0.2)

    return {
        "kgSaved": round(total_kg, 2),
        "co2Saved": round(total_kg * 2.5, 2),
        "valuePreserved": round(total_value, 2),
    }
