
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import BaseModel, ConfigDict, Field

model_config = ConfigDict(from_attributes=True)

class InventoryBatch(BaseModel):
    batch_id: str
    product_name: str
    quantity: int = Field(ge=0)
    unit: str = "units"
    location: str
    current_price: float = Field(ge=0)
    original_price: float = Field(ge=0)
    estimated_remaining_shelf_life_hours: float = Field(ge=0)
    demand_velocity_units_per_hour: float = Field(ge=0)
    status: str = "HEALTHY"
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
