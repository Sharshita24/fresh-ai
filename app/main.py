"""FreshChain AI backend.

Run:  uvicorn app.main:app --reload       Docs: http://localhost:8000/docs
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import Base, SessionLocal, engine
from app.models import Store
from app.routers import dashboard, decisions, operations, system
from app.services import monitor, seed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            if db.get(Store, settings.home_store_id) is None:
                seed.seed(db)
    task = asyncio.create_task(monitor.loop()) if settings.monitor_interval_s > 0 else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="FreshChain AI",
    description="Autonomous perishable-inventory control tower: sensors + vision + demand → agents → actions → measured impact.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(system.router)
app.include_router(dashboard.router)
app.include_router(operations.router)
app.include_router(decisions.router)
