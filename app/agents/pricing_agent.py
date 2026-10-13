"""Pricing agent: how much discount clears the stock before it spoils?"""

import math

from app.schemas.agents import MarkdownOption, PricingAssessment
from app.services.demand import markdown_lift
from app.services.risk import Snapshot

MARKDOWN_STEPS = (10, 20, 30, 40)


def waste_tolerance(units: int) -> int:
    """Waste we accept as 'cleared': 2% of the batch, at least one unit."""
    return max(1, math.floor(units * 0.02))


def markdown_option(s: Snapshot, units: int, pct: int) -> MarkdownOption:
    v = round(s.velocity * markdown_lift(s.product, pct), 2)
    sold = min(units, math.floor(v * s.hours_left))
    return MarkdownOption(
        pct=pct,
        price=round(s.batch.current_price * (1 - pct / 100), 2),
        velocity_per_h=v,
        clear_hours=round(units / v, 1) if v > 0 else None,
        sold=sold,
        waste=units - sold,
    )


def assess_pricing(s: Snapshot) -> PricingAssessment:
    units = s.on_hand
    options = [markdown_option(s, units, pct) for pct in MARKDOWN_STEPS]
    tol = waste_tolerance(units)
    clearing = [o for o in options if o.waste <= tol]
    pick = clearing[0] if clearing else min(options, key=lambda o: (o.waste, o.pct))

    evidence = [f"Selling {s.velocity}/h; {s.needed_rate}/h needed to clear {units} in {s.hours_left:.0f} h"]
    if s.forecast:
        evidence.append(f"Demand {((s.velocity / s.forecast) - 1) * 100:+.0f}% vs {s.forecast}/h forecast")
    if s.footfall_ratio is not None:
        evidence.append(f"Footfall {((s.footfall_ratio) - 1) * 100:+.0f}% vs normal this hour")
    evidence.append(f"−{pick.pct}% lifts sales to {pick.velocity_per_h}/h ({pick.sold} of {units} sold, {pick.waste} wasted)")

    return PricingAssessment(
        batch_id=s.batch.batch_id,
        current_velocity_per_h=s.velocity,
        forecast_per_h=s.forecast,
        footfall_ratio=s.footfall_ratio,
        needed_per_h=s.needed_rate,
        baseline_sold=s.expected_sold,
        baseline_waste=s.expected_waste,
        options=options,
        recommended_markdown_percent=pick.pct,
        evidence=evidence,
    )
