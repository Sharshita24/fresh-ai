
from datetime import datetime, timezone

from app.schemas.inventory import InventoryBatch


SAMPLE_INVENTORY = [
    InventoryBatch(
        batch_id="STB-042",
        product_name="Strawberries",
        quantity=184,
        location="Main Store",
        current_price=180.0,
        original_price=180.0,
        estimated_remaining_shelf_life_hours=31.0,
        demand_velocity_units_per_hour=4.2,
        status="HEALTHY",
        created_at=datetime.now(timezone.utc),
    )
]

# Temporary storage for the local demo.
# This resets when the Python process restarts.
INVENTORY_BY_ID = {
    batch.batch_id: batch
    for batch in SAMPLE_INVENTORY
}
