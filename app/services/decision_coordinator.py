"""Coordinator: combine the three agents into one decision with evidence.

1. Quality, Pricing and Logistics agents each assess the batch (deterministic, explainable).
2. Every option is costed against doing nothing: markdowns, a transfer, transfer + markdown, B2B offload.
3. Choose: least waste first (within a 2% tolerance), then most value preserved.
   If Gemini is configured, it picks among the top options and writes the manager-facing rationale;
   code still guarantees the numbers.
"""

import math
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.logistics_agent import assess_logistics
from app.agents.pricing_agent import assess_pricing, markdown_option, waste_tolerance
from app.agents.quality_agent import assess_quality
from app.db.database import utcnow
from app.models import AgentAssessment, Batch, BatchImage, Decision
from app.services import gemini_agent, weather
from app.services.events import log_event
from app.services.risk import Snapshot, snapshot
from app.services.shelf_life import project

CO2_PER_KG = 2.5  # kg CO₂e avoided per kg of food not wasted (pitch doc figure)


def _option(oid, label, detail, actions, units, sold, moved, revenue, cost, baseline_revenue):
    waste = units - sold - moved
    return {
        "id": oid,
        "label": label,
        "detail": detail,
        "actions": actions,
        "sold": sold,
        "moved": moved,
        "waste": waste,
        "sellThrough": round(100 * (sold + moved) / units) if units else 0,
        "revenue": round(revenue),
        "cost": round(cost),
        "value": round(revenue - cost - baseline_revenue),
    }


def evaluate_options(s: Snapshot, pricing, logistics) -> list[dict]:
    n, p, unit = s.on_hand, s.batch.current_price, s.product.unit_label
    base_rev = s.expected_sold * p
    opts = [_option("keep", "Do nothing", f"Sell at ₹{p:.0f} in-store", [], n, s.expected_sold, 0, base_rev, 0, base_rev)]

    for mo in pricing.options:
        opts.append(
            _option(
                f"markdown_{mo.pct}",
                f"Markdown {mo.pct}% on all {n}",
                f"₹{mo.price:.0f} · demand {mo.velocity_per_h}/h",
                [{"type": "MARKDOWN", "quantity": n, "pct": mo.pct, "priceFrom": p, "priceTo": mo.price}],
                n,
                mo.sold,
                0,
                mo.sold * mo.price,
                0,
                base_rev,
            )
        )

    best = logistics.best
    if best and logistics.recommended_quantity:
        k = logistics.recommended_quantity
        rem = n - k
        transfer = {
            "type": "TRANSFER",
            "quantity": k,
            "target": best.store_id,
            "targetName": best.name,
            "distanceKm": best.distance_km,
            "etaMin": best.eta_min,
            "cost": best.transfer_cost,
        }
        kept = min(rem, math.floor(s.velocity * s.hours_left))
        opts.append(
            _option(
                f"transfer_{k}",
                f"Transfer {k} only",
                f"{best.name} at ₹{p:.0f} · rest unchanged",
                [transfer],
                n,
                kept,
                k,
                (k + kept) * p,
                best.transfer_cost,
                base_rev,
            )
        )
        hub_h = k / best.headroom_per_h if best.headroom_per_h else 0
        for pct in (10, 20, 30, 40):
            mo = markdown_option(s, rem, pct)
            opts.append(
                _option(
                    f"transfer_{k}_markdown_{pct}",
                    f"Transfer {k} + markdown {rem} by {pct}%",
                    f"{best.name} clears in ~{hub_h:.0f} h · store clears in {mo.clear_hours} h",
                    [transfer, {"type": "MARKDOWN", "quantity": rem, "pct": pct, "priceFrom": p, "priceTo": mo.price}],
                    n,
                    mo.sold,
                    k,
                    k * p + mo.sold * mo.price,
                    best.transfer_cost,
                    base_rev,
                )
            )

    if logistics.b2b:
        b = logistics.b2b
        opts.append(
            _option(
                "b2b_all",
                f"B2B offload all {n} now",
                f"{b.name} at ₹{b.unit_price:.0f}/{unit[:-1] or 'unit'}",
                [{"type": "B2B_OFFER", "quantity": n, "target": b.store_id, "targetName": b.name, "unitPrice": b.unit_price}],
                n,
                0,
                n,
                n * b.unit_price,
                0,
                base_rev,
            )
        )
    return opts


def choose(options: list[dict], units: int) -> dict:
    tol = waste_tolerance(units)
    feasible = [o for o in options if o["waste"] <= tol]
    if feasible:
        return max(feasible, key=lambda o: (o["value"], -o["waste"]))
    return min(options, key=lambda o: (o["waste"], -o["value"]))


def shortlist(options: list[dict], chosen: dict) -> list[str]:
    """What the UI shows: doing nothing, the best of each option family, and the choice."""

    def best(match) -> dict | None:
        family = [o for o in options if match(o["id"])]
        return max(family, key=lambda o: (o["value"], -o["waste"])) if family else None

    picks = [
        options[0],
        best(lambda i: i.startswith("markdown_")),
        best(lambda i: i.startswith("transfer_") and "markdown" not in i),
        chosen,
        best(lambda i: i == "b2b_all"),
    ]
    ids: list[str] = []
    for o in picks:
        if o and o["id"] not in ids:
            ids.append(o["id"])
    return ids


def confidence(s: Snapshot) -> float:
    """How much evidence backs the call, not how sure a model 'feels'."""
    score = 0.60
    if s.batch.vision_checked_at:
        score += 0.12
    independent = sum(bool(x) for x in ("Temp ↑" in s.signals, "Vision" in s.signals, "Demand ↓" in s.signals, s.expected_waste > 0))
    if independent >= 3:
        score += 0.12
    if s.velocity > 0:
        score += 0.08
    return round(min(score, 0.97), 2)


def _plan(s: Snapshot, chosen: dict, logistics) -> list[dict]:
    plan = [dict(a) for a in chosen["actions"]]
    if s.waste_frac >= 0.2:
        plan.append({"type": "PO_ADJUST", "pct": -min(25, max(5, round(s.waste_frac * 20))), "sku": s.batch.sku})
    if "HIGH_TEMPERATURE" in s.flags:
        plan.append({"type": "MAINTENANCE", "asset": s.batch.location.split(" · ")[0], "observed": f"{s.temp_delta:+.1f} °C over baseline"})
    return plan


def _evidence(db: Session, s: Snapshot, pricing, logistics, chosen: dict, wx: dict) -> list[dict]:
    b, prod = s.batch, s.product
    # split the shelf-life drop into its temperature and visual parts
    at_base_ref = project(prod, s.shelf.printed_h, s.baseline_c, b.reference_defect_pct).estimate_h
    at_base_now = project(prod, s.shelf.printed_h, s.baseline_c, b.defect_pct).estimate_h
    temp_cost = at_base_now - s.hours_left
    vision_cost = at_base_ref - at_base_now
    image = db.query(BatchImage).filter(BatchImage.batch_id == b.batch_id).order_by(BatchImage.uploaded_at.desc()).first()
    md = next((a for a in chosen["actions"] if a["type"] == "MARKDOWN"), None)
    md_opt = markdown_option(s, md["quantity"], md["pct"]) if md else None

    rows = [
        {
            "n": "01",
            "title": "Environment",
            "agent": "quality",
            "tone": "critical" if abs(s.temp_delta) >= 2 else "info",
            "value": f"Temperature {s.temp_delta:+.1f} °C" if abs(s.temp_delta) >= 0.5 else "Temperature stable",
            "evidence": f"{b.location.split(' · ')[0]} at {s.temp_c:.1f} °C vs {s.baseline_c:.1f} °C · humidity {s.humidity:.0f}%",
            "impact": f"Shelf life −{temp_cost:.0f} h" if temp_cost >= 1 else "No temperature impact",
        },
        {
            "n": "02",
            "title": "Visual quality",
            "agent": "quality",
            "tone": "warning" if b.defect_pct >= 10 else "info",
            "value": f"{b.defect_pct:.0f}% {b.vision_label.lower()}",
            "evidence": (image.findings.get("summary") if image else None) or "No inspection image yet",
            "impact": f"Shelf life −{vision_cost:.0f} h" if vision_cost >= 1 else "Within tolerance",
        },
    ]
    footfall = f"Footfall {(s.footfall_ratio - 1) * 100:+.0f}%".replace("-", "−") if s.footfall_ratio is not None else "No footfall data"
    rain = f" · rain {wx['precipNext3hMm']} mm next 3 h ({wx['source']})" if wx.get("rainExpected") else ""
    lift = f" · −{md['pct']}% markdown lifts sales to {md_opt.velocity_per_h:.1f}/h" if md_opt else ""
    rows.append(
        {
            "n": "03",
            "title": "Demand",
            "agent": "pricing",
            "tone": "critical" if pricing.baseline_waste > waste_tolerance(s.on_hand) else "info",
            "value": f"{s.velocity} vs {s.needed_rate} units/h",
            "evidence": f"{footfall}{rain}{lift}",
            "impact": "Won't clear before expiry" if pricing.baseline_waste > waste_tolerance(s.on_hand) else "Clears in time",
        }
    )
    best = logistics.best
    rows.append(
        {
            "n": "04",
            "title": "Network",
            "agent": "logistics",
            "tone": "info",
            "value": f"{best.name} headroom {best.headroom_per_h}/h" if best else "No transfer target",
            "evidence": f"{best.distance_km} km · ETA {best.eta_min} min · cold space for {best.free_capacity}"
            if best
            else "; ".join(logistics.evidence),
            "impact": f"Transfer clears in ~{logistics.recommended_quantity / best.headroom_per_h:.0f} h"
            if best
            else "Fallback to B2B or donation",
        }
    )
    return rows


def build(db: Session, batch: Batch, trigger: str) -> dict:
    """Run the agents and return a full decision payload (not persisted)."""
    s = snapshot(db, batch)
    quality = assess_quality(s)
    pricing = assess_pricing(s)
    logistics = assess_logistics(db, s)
    options = evaluate_options(s, pricing, logistics)
    chosen = choose(options, s.on_hand)
    short = shortlist(options, chosen)
    wx = weather.outlook(s.store.lat, s.store.lon, s.now)
    conf = confidence(s)
    model_used, meta = "rules", {}
    rationale = (
        f"{chosen['label']}: {chosen['sellThrough']}% sell-through, {chosen['waste']} wasted vs {options[0]['waste']} "
        f"if nothing is done, ₹{chosen['value']:,} preserved."
    )

    if gemini_agent.is_configured():
        context = {
            "batch": {
                "id": batch.batch_id,
                "product": f"{s.product.name} {s.product.variant}",
                "onHand": s.on_hand,
                "price": batch.current_price,
                "hoursLeft": s.hours_left,
                "printedHours": s.shelf.printed_h,
            },
            "signals": {
                "tempC": s.temp_c,
                "baselineC": s.baseline_c,
                "defectPct": batch.defect_pct,
                "velocityPerH": s.velocity,
                "neededPerH": s.needed_rate,
                "footfallRatio": s.footfall_ratio,
                "flags": s.flags,
                "weather": wx,
            },
            "agents": {"quality": quality.evidence, "pricing": pricing.evidence, "logistics": logistics.evidence},
            "options": [{k: o[k] for k in ("id", "label", "sold", "moved", "waste", "value")} for o in options if o["id"] in short],
        }
        out = gemini_agent.coordinate(context, short)
        if out:
            choice, meta = out
            chosen = next(o for o in options if o["id"] == choice.option_id)
            rationale = choice.rationale
            conf = round(min(0.97, max(0.5, (conf + choice.confidence) / 2)), 2)
            model_used = meta["model"]
            meta["aiEvidence"] = [e.model_dump() for e in choice.evidence]

    for o in options:
        o["selected"] = o["id"] == chosen["id"]
        o["shortlisted"] = o["id"] in short
    kg = round((options[0]["waste"] - chosen["waste"]) * s.product.unit_kg, 2)
    return {
        "snapshot": s,
        "assessments": {"quality": quality, "pricing": pricing, "logistics": logistics},
        "options": options,
        "chosen": chosen,
        "plan": _plan(s, chosen, logistics),
        "evidence": _evidence(db, s, pricing, logistics, chosen, wx),
        "confidence": conf,
        "rationale": rationale,
        "model_used": model_used,
        "model_meta": meta,
        "weather": wx,
        "expected": {
            "value": chosen["value"],
            "wasteBefore": options[0]["waste"],
            "wasteAfter": chosen["waste"],
            "kgSaved": kg,
            "co2Saved": round(kg * CO2_PER_KG, 1),
            "sellThrough": chosen["sellThrough"],
            "hoursLeft": s.hours_left,
        },
    }


def create_decision(db: Session, batch: Batch, trigger: str) -> Decision:
    d = build(db, batch, trigger)
    decision = Decision(
        decision_id=str(uuid4()),
        batch_id=batch.batch_id,
        trigger=trigger,
        status="proposed",
        confidence=d["confidence"],
        selected_option=d["chosen"]["id"],
        plan=d["plan"],
        options=d["options"],
        evidence=d["evidence"],
        rationale=d["rationale"],
        expected=d["expected"],
        model_used=d["model_used"],
        model_meta=d["model_meta"],
        created_at=utcnow(),
    )
    db.add(decision)
    db.flush()
    for name, result in d["assessments"].items():
        db.add(
            AgentAssessment(
                assessment_id=str(uuid4()),
                decision_id=decision.decision_id,
                batch_id=batch.batch_id,
                agent_name=name,
                result=result.model_dump(mode="json"),
            )
        )
    log_event(
        db,
        "decision",
        f"Decision · {d['chosen']['label'].lower()}",
        f"{round(d['confidence'] * 100)}% confidence · ₹{d['expected']['value']:,} preserved vs doing nothing",
        tone="good",
        batch_id=batch.batch_id,
        data={"decisionId": decision.decision_id, "trigger": trigger},
    )
    return decision
