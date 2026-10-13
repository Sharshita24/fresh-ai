"""Logistics agent: where else could this stock still sell in time?

For each nearby store or hub:
  headroom   = its demand for this SKU − what it is already supplied with (units/h)
  absorbable = min(free cold capacity, headroom × usable hours), rounded down to whole cases
  usable hours = 80% of remaining shelf life (stock must still look fresh on arrival) − transit time
"""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Store
from app.schemas.agents import Fallback, LogisticsAssessment, TransferCandidate
from app.services.risk import Snapshot

SELL_BY_BUFFER = 0.8
TRANSFER_BASE_COST = 300.0  # ₹ per run: loading + driver
TRANSFER_COST_PER_KM = 62.5
CITY_SPEED_KMH = 20.0
LOADING_MIN = 10


def distance_km(a: Store, b: Store) -> float:
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)), 1)


def eta_min(km: float) -> int:
    return math.ceil(LOADING_MIN + km / CITY_SPEED_KMH * 60)


def transfer_cost(km: float) -> float:
    return round(TRANSFER_BASE_COST + TRANSFER_COST_PER_KM * km, 0)


def assess_logistics(db: Session, s: Snapshot) -> LogisticsAssessment:
    origin = s.store
    case = s.product.case_size
    stores = db.scalars(select(Store).where(Store.active.is_(True), Store.store_id != origin.store_id)).all()

    candidates: list[TransferCandidate] = []
    b2b = food_bank = None
    for st in stores:
        km = distance_km(origin, st)
        if st.kind == "b2b":
            price = round(s.batch.original_price * (st.price_factor or 0.3), 2)
            if b2b is None or km < b2b.distance_km:
                b2b = Fallback(store_id=st.store_id, name=st.name, kind="b2b", distance_km=km, unit_price=price)
            continue
        if st.kind == "food_bank":
            if food_bank is None or km < food_bank.distance_km:
                food_bank = Fallback(store_id=st.store_id, name=st.name, kind="food_bank", distance_km=km, unit_price=0.0)
            continue

        profile = (st.demand_profile or {}).get(s.batch.sku) or {}
        headroom = max(0.0, float(profile.get("demand_per_h", 0)) - float(profile.get("supplied_per_h", 0)))
        eta = eta_min(km)
        usable_h = max(0.0, s.hours_left * SELL_BY_BUFFER - eta / 60)
        raw = min(st.cold_capacity_units, math.floor(headroom * usable_h), s.on_hand)
        absorbable = (raw // case) * case
        if st.cold_capacity_units <= 0:
            verdict = "No cold capacity"
        elif headroom <= 0:
            verdict = "No spare demand"
        elif absorbable < case:
            verdict = "Too little demand in time"
        else:
            verdict = f"Can sell {absorbable} in ~{absorbable / headroom:.0f} h"
        candidates.append(
            TransferCandidate(
                store_id=st.store_id,
                name=st.name,
                kind=st.kind,
                distance_km=km,
                eta_min=eta,
                headroom_per_h=round(headroom, 1),
                free_capacity=st.cold_capacity_units,
                absorbable_units=absorbable,
                transfer_cost=transfer_cost(km),
                score=0.0,
                verdict=verdict,
            )
        )

    top = max((c.absorbable_units for c in candidates), default=0) or 1
    for c in candidates:
        c.score = round(0.85 * c.absorbable_units / top + 0.15 * max(0.0, 1 - c.distance_km / 10), 2)
    candidates.sort(key=lambda c: (-c.score, c.distance_km))
    best = candidates[0] if candidates and candidates[0].absorbable_units > 0 else None
    if best:
        best.verdict = f"Best · sells {best.absorbable_units} in ~{best.absorbable_units / best.headroom_per_h:.0f} h"

    evidence = []
    if best:
        evidence.append(
            f"{best.name}: {best.distance_km} km, demand headroom {best.headroom_per_h}/h, "
            f"can take {best.absorbable_units} (ETA {best.eta_min} min, ₹{best.transfer_cost:.0f})"
        )
    else:
        evidence.append("No nearby location can sell this stock in time")
    if b2b:
        evidence.append(f"B2B fallback: {b2b.name} buys at ₹{b2b.unit_price:.0f}/{s.product.unit_label[:-1] or 'unit'}")
    if food_bank:
        evidence.append(f"Donation fallback: {food_bank.name}, {food_bank.distance_km} km")

    return LogisticsAssessment(
        batch_id=s.batch.batch_id,
        candidates=candidates,
        best=best,
        recommended_quantity=best.absorbable_units if best else 0,
        b2b=b2b,
        food_bank=food_bank,
        evidence=evidence,
    )
