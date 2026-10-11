import json
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Add it to your .env file.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

sample_data = {
    "inventory_batches": [
        {
            "batch_id": "STB-042",
            "product_name": "Strawberries",
            "quantity": 184,
            "unit": "units",
            "location": "Main Store",
            "current_price": 180.0,
            "original_price": 180.0,
            "estimated_remaining_shelf_life_hours": 31.0,
            "demand_velocity_units_per_hour": 4.2,
            "status": "HEALTHY",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "batch_id": "STB-043",
            "product_name": "Blueberries",
            "quantity": 92,
            "unit": "units",
            "location": "Cold Room A",
            "current_price": 220.0,
            "original_price": 220.0,
            "estimated_remaining_shelf_life_hours": 18.5,
            "demand_velocity_units_per_hour": 3.8,
            "status": "RISK",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "batch_id": "STB-044",
            "product_name": "Avocados",
            "quantity": 140,
            "unit": "units",
            "location": "Fresh Cut Zone",
            "current_price": 150.0,
            "original_price": 150.0,
            "estimated_remaining_shelf_life_hours": 42.0,
            "demand_velocity_units_per_hour": 5.1,
            "status": "HEALTHY",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "batch_id": "STB-045",
            "product_name": "Mangoes",
            "quantity": 210,
            "unit": "units",
            "location": "Back Room",
            "current_price": 95.0,
            "original_price": 95.0,
            "estimated_remaining_shelf_life_hours": 12.0,
            "demand_velocity_units_per_hour": 6.4,
            "status": "CRITICAL",
            "created_at": datetime.now(timezone.utc),
        },
    ],
    "sensor_readings": [
        {
            "reading_id": "sr-1001",
            "batch_id": "STB-042",
            "temperature_c": 4.2,
            "humidity_percent": 65.0,
            "ethylene_ppm": 0.6,
            "recorded_at": datetime.now(timezone.utc),
            "anomaly_flags": [],
        },
        {
            "reading_id": "sr-1002",
            "batch_id": "STB-043",
            "temperature_c": 8.5,
            "humidity_percent": 74.0,
            "ethylene_ppm": 1.9,
            "recorded_at": datetime.now(timezone.utc),
            "anomaly_flags": ["HIGH_TEMPERATURE", "HIGH_ETHYLENE"],
        },
        {
            "reading_id": "sr-1003",
            "batch_id": "STB-044",
            "temperature_c": 5.1,
            "humidity_percent": 66.0,
            "ethylene_ppm": 0.8,
            "recorded_at": datetime.now(timezone.utc),
            "anomaly_flags": [],
        },
        {
            "reading_id": "sr-1004",
            "batch_id": "STB-045",
            "temperature_c": 10.2,
            "humidity_percent": 81.0,
            "ethylene_ppm": 2.5,
            "recorded_at": datetime.now(timezone.utc),
            "anomaly_flags": ["HIGH_TEMPERATURE", "HIGH_HUMIDITY", "HIGH_ETHYLENE"],
        },
    ],
    "store_profiles": [
        {
            "store_id": "store-042",
            "name": "Store #042",
            "city": "Bengaluru",
            "area": "Brookefield",
            "manager": "Store Manager",
            "created_at": datetime.now(timezone.utc),
        }
    ],
    "network_nodes": [
        {
            "node_id": "store-042",
            "node_type": "store",
            "demand": 4.2,
            "risk": 38,
            "capacity": 0.0,
            "distance_km": 0.0,
            "destination_id": "hub-02",
        },
        {
            "node_id": "hub-02",
            "node_type": "hub",
            "demand": 0.0,
            "risk": 0,
            "capacity": 320.0,
            "distance_km": 2.4,
            "destination_id": None,
        },
        {
            "node_id": "hub-07",
            "node_type": "hub",
            "demand": 0.0,
            "risk": 0,
            "capacity": 480.0,
            "distance_km": 8.6,
            "destination_id": None,
        },
    ],
    "decisions": [
        {
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "quality_assessment": {"score": 62, "summary": "Temperature spike and ethylene elevated"},
            "pricing_assessment": {"recommended_markdown_percent": 18.0, "price_action": "markdown"},
            "logistics_assessment": {"route": "hub-02", "priority": "high"},
            "selected_actions": ["MARKDOWN", "REDISTRIBUTE"],
            "evidence_summary": ["High temp detected", "Ethylene elevated", "Shelf life dropping"],
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "decision_id": "dec-2002",
            "batch_id": "STB-045",
            "quality_assessment": {"score": 41, "summary": "Severe spoilage risk"},
            "pricing_assessment": {"recommended_markdown_percent": 32.0, "price_action": "aggressive_markdown"},
            "logistics_assessment": {"route": "hub-07", "priority": "critical"},
            "selected_actions": ["B2B_OFFLOAD", "MARKDOWN"],
            "evidence_summary": ["Critical spoilage risk", "Customer demand weak", "Transfer recommended"],
            "status": "APPROVED",
            "created_at": datetime.now(timezone.utc),
        },
    ],
    "agent_assessments": [
        {
            "assessment_id": "ass-3001",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "agent_name": "quality",
            "result": {"risk_level": "high", "score": 62},
        },
        {
            "assessment_id": "ass-3002",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "agent_name": "pricing",
            "result": {"markdown_percent": 18.0, "recommended_price": 180.0},
        },
        {
            "assessment_id": "ass-3003",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "agent_name": "logistics",
            "result": {"route": "hub-02", "eta_minutes": 18},
        },
        {
            "assessment_id": "ass-3004",
            "decision_id": "dec-2002",
            "batch_id": "STB-045",
            "agent_name": "quality",
            "result": {"risk_level": "critical", "score": 41},
        },
    ],
    "actions": [
        {
            "action_id": "act-4001",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "action_type": "REDISTRIBUTE",
            "quantity": 42,
            "status": "PENDING",
            "details": {"destination": "hub-02", "eta_minutes": 18},
            "created_at": datetime.now(timezone.utc),
        },
        {
            "action_id": "act-4002",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "action_type": "MARKDOWN",
            "quantity": 30,
            "status": "PENDING",
            "details": {"markdown_percent": 18.0},
            "created_at": datetime.now(timezone.utc),
        },
        {
            "action_id": "act-4003",
            "decision_id": "dec-2002",
            "batch_id": "STB-045",
            "action_type": "B2B_OFFLOAD",
            "quantity": 70,
            "status": "IN_PROGRESS",
            "details": {"destination": "secondary_buyer_network"},
            "created_at": datetime.now(timezone.utc),
        },
    ],
    "execution_records": [
        {
            "execution_id": "exec-5001",
            "decision_id": "dec-2001",
            "batch_id": "STB-043",
            "status": "in_progress",
            "steps": {"Create markdown": "done", "Transfer to hub": "in_progress", "Notify B2B buyer": "pending"},
            "transfer_destination": "hub-02",
            "transfer_eta_min": 18,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "execution_id": "exec-5002",
            "decision_id": "dec-2002",
            "batch_id": "STB-045",
            "status": "queued",
            "steps": {"Create markdown": "done", "Route offload": "queued", "Confirm buyer": "pending"},
            "transfer_destination": "hub-07",
            "transfer_eta_min": 32,
            "created_at": datetime.now(timezone.utc),
        },
    ],
}


def _prepare_row_for_insert(table_name: str, row: dict):
    prepared = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            prepared[key] = json.dumps(value)
        else:
            prepared[key] = value
    return prepared


def seed_all_tables():
    table_keys = {
        "inventory_batches": "batch_id",
        "sensor_readings": "reading_id",
        "store_profiles": "store_id",
        "network_nodes": "node_id",
        "decisions": "decision_id",
        "agent_assessments": "assessment_id",
        "actions": "action_id",
        "execution_records": "execution_id",
    }

    with engine.begin() as conn:
        for table_name, rows in sample_data.items():
            if not rows:
                continue
            columns = list(rows[0].keys())
            pk = table_keys[table_name]
            sql = (
                f"INSERT INTO {table_name} ({', '.join(columns)}) "
                f"VALUES ({', '.join(':' + col for col in columns)}) "
                f"ON CONFLICT ({pk}) DO NOTHING"
            )
            for row in rows:
                conn.execute(text(sql), _prepare_row_for_insert(table_name, row))

    print("Database seeded successfully with sample FreshChain data.")


if __name__ == "__main__":
    seed_all_tables()
