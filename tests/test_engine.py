"""The decision maths, checked against the numbers in the pitch story."""

from types import SimpleNamespace

from app.data.reference import PRODUCTS
from app.services.shelf_life import MAX_TEMP_FACTOR, project
from app.services.weather import footfall_factor

STRAWBERRY = SimpleNamespace(**next(p for p in PRODUCTS if p["sku"] == "strawberry-250g"))


def test_shelf_life_matches_story():
    assert project(STRAWBERRY, 40, 4.0, 2).estimate_h == 31.0
    assert project(STRAWBERRY, 40, 7.2, 17).estimate_h == 17.0


def test_cold_storage_extends_life_but_is_capped():
    assert project(STRAWBERRY, 40, -20, 0).temp_factor == MAX_TEMP_FACTOR


def test_rain_reduces_footfall_forecast():
    assert footfall_factor(0) == 1.0
    assert 0.75 < footfall_factor(3) < 0.8
    assert footfall_factor(100) >= 0.65


def test_incident_decision(incident):
    d = incident
    assert d["trigger"] == "HIGH_TEMPERATURE"
    assert d["selectedOption"] == "transfer_84_markdown_20"
    assert d["confidence"] == 0.92
    assert d["expected"]["wasteBefore"] == 113 and d["expected"]["wasteAfter"] == 0
    assert d["expected"]["value"] == 84 * 180 + 100 * 144 - 450 - 71 * 180  # = ₹16,290 vs doing nothing
    types = [a["type"] for a in d["plan"]]
    assert types == ["TRANSFER", "MARKDOWN", "PO_ADJUST", "MAINTENANCE"]
    transfer = d["plan"][0]
    assert transfer["target"] == "hub-whitefield" and transfer["distanceKm"] == 2.4 and transfer["etaMin"] == 18
    assert d["plan"][1]["priceTo"] == 144.0
    assert d["plan"][2]["pct"] == -12


def test_evidence_chain(incident):
    rows = {e["title"]: e for e in incident["evidence"]}
    assert rows["Environment"]["value"] == "Temperature +3.2 °C"
    assert rows["Visual quality"]["value"].startswith("17%")
    assert "4 of 24" in rows["Visual quality"]["evidence"]
    assert rows["Demand"]["value"] == "4.2 vs 10.8 units/h"
    assert rows["Network"]["impact"] == "Transfer clears in ~13 h"


def test_options_include_alternatives(incident):
    by_id = {o["id"]: o for o in incident["options"]}
    assert by_id["keep"]["value"] == 0 and by_id["keep"]["waste"] == 113
    assert by_id["b2b_all"]["value"] == -2844  # offloading now loses money
    assert sum(o["selected"] for o in incident["options"]) == 1
