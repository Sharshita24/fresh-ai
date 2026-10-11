from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StoreProfile(BaseModel):
    id: str
    name: str
    city: str
    area: str
    manager: str
    skus: int
    sensors: int


class RiskSummary(BaseModel):
    healthy: int = 0
    risk: int = 0
    critical: int = 0
    managed: int = 0


class ActiveIncident(BaseModel):
    batchId: str | None = None
    status: str | None = None
    confidence: int | None = None


class StoreOverviewResponse(BaseModel):
    store: StoreProfile
    riskSummary: RiskSummary
    activeIncident: ActiveIncident | None = None


class InventoryItem(BaseModel):
    id: str
    name: str
    variant: str
    category: str
    risk: int
    status: str
    shelfLifeH: float
    printedShelfH: float
    signals: list[str]
    price: float
    location: str
    action: str


class InventoryItemsResponse(BaseModel):
    items: list[InventoryItem]


class HistoryEvent(BaseModel):
    id: str
    timestamp: datetime | str
    group: str
    title: str
    status: str
    summary: str


class HistoryEventsResponse(BaseModel):
    events: list[HistoryEvent]


class RecommendedAction(BaseModel):
    type: str
    units: int | None = None
    destination: str | None = None
    etaMin: int | None = None
    pct: float | None = None


class RecommendedPlan(BaseModel):
    type: str
    confidence: int
    estimatedValuePreserved: float
    kgSaved: float
    co2Saved: float
    actions: list[RecommendedAction] = Field(default_factory=list)


class CurrentDecisionResponse(BaseModel):
    incidentId: str | None = None
    recommendedPlan: RecommendedPlan
    alternatives: list[dict] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    name: str
    status: str


class ExecutionTransfer(BaseModel):
    id: str
    destination: str
    etaMin: int


class ExecutionTicket(BaseModel):
    id: str


class ExecutionResponse(BaseModel):
    executionId: str
    incidentId: str | None = None
    status: str
    steps: list[ExecutionStep] = Field(default_factory=list)
    transfer: ExecutionTransfer | None = None
    ticket: ExecutionTicket | None = None


class NetworkNode(BaseModel):
    id: str
    type: str
    demand: float | None = None
    risk: int | None = None
    capacity: float | None = None
    distanceKm: float | None = None


class NetworkEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    distanceKm: float | None = None
    etaMin: int | None = None

    model_config = {"populate_by_name": True}


class NetworkGraphResponse(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


class NetworkImpactResponse(BaseModel):
    kgSaved: float
    co2Saved: float
    valuePreserved: float
