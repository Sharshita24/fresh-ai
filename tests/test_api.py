"""End-to-end API checks."""

import io


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy" and body["database"] == "ok" and body["ai"]["provider"] == "rules"


def test_overview_counts_and_impact(fresh):
    o = fresh.get("/api/store/overview").json()
    s = o["riskSummary"]
    assert sum(s.values()) == o["store"]["skus"] == 8706
    assert s["managed"] == 5 and o["activeIncident"] is None
    assert o["impactToday"]["valuePreserved"] == 10650 and o["impactToday"]["actions"] == 5
    assert o["coldChain"] and o["weather"]["source"] == "open-meteo snapshot"


def test_inventory_summary_route_is_not_shadowed(fresh):
    # was a 404 in the first version: /inventory/{batch_id} swallowed "summary"
    assert fresh.get("/api/inventory/summary").status_code == 200


def test_inventory_items_sorted_and_filtered(fresh):
    items = fresh.get("/api/inventory/items").json()["items"]
    risks = [i["risk"] for i in items]
    assert risks == sorted(risks, reverse=True) and len(items) == 13
    stb = next(i for i in items if i["id"] == "STB-042")
    assert stb["status"] == "healthy" and 30.5 <= stb["shelfLifeH"] <= 31.5 and 39.9 <= stb["printedShelfH"] <= 40.0
    assert stb["supplier"] == "Nandi Hills Farms" and stb["lotCode"] == "NHF-2610-A7"
    managed = fresh.get("/api/inventory/items", params={"status": "managed"}).json()["items"]
    assert {i["id"] for i in managed} == {"MLK-188", "BRD-021", "SPN-118", "CRS-015", "AVC-033"}
    assert fresh.get("/api/inventory/items", params={"q": "milk"}).json()["items"][0]["id"] == "MLK-188"


def test_batch_detail(fresh):
    b = fresh.get("/api/batches/STB-042").json()["batch"]
    assert len(b["temp"]["series"]) == 60 and b["temp"]["threshold"] == 7.0
    assert b["demand"]["rate"] == 4.2 and len(b["demand"]["history"]) == 12
    assert fresh.get("/api/batches/NOPE").status_code == 404


def test_incident_approve_executes_everything(fresh, incident):
    overview = fresh.get("/api/store/overview").json()
    assert overview["activeIncident"]["decisionId"] == incident["decisionId"]
    assert overview["riskSummary"]["critical"] == 37  # 36 untracked + STB-042

    ex = fresh.post(f"/api/decisions/{incident['decisionId']}/approve").json()
    assert [s["type"] for s in ex["steps"]] == ["TRANSFER", "MARKDOWN", "PO_ADJUST", "MAINTENANCE"]
    assert ex["transfer"]["destination"] == "hub-whitefield" and ex["ticket"]["id"].startswith("MT-")

    stb = fresh.get("/api/inventory/STB-042").json()
    assert stb["units"] == 100 and stb["price"] == 144.0 and stb["status"] == "managed"
    hub_copy = fresh.get("/api/batches/STB-042-WHIT").json()["batch"]
    assert hub_copy["units"] == 84 and hub_copy["parentBatchId"] == "STB-042" and hub_copy["lotCode"] == "NHF-2610-A7"

    impact = fresh.get("/api/network/impact").json()
    assert impact["valuePreserved"] == 10650 + 16290 and impact["actions"] == 9
    assert impact["week"][-1]["today"] is True

    kinds = [e["kind"] for e in fresh.get("/api/history/events").json()["events"]]
    for k in ("sensor", "vision", "decision", "action", "impact"):
        assert k in kinds
    # can't execute twice
    assert fresh.post(f"/api/decisions/{incident['decisionId']}/approve").status_code == 409


def test_hold_then_approve(fresh, incident):
    held = fresh.post(f"/api/decisions/{incident['decisionId']}/hold").json()
    assert held["status"] == "held"
    item = fresh.get("/api/inventory/STB-042").json()
    assert item["actionNote"] == "Awaiting your approval"
    assert fresh.post(f"/api/decisions/{incident['decisionId']}/approve").status_code == 200


def test_reject(fresh, incident):
    assert fresh.post(f"/api/decisions/{incident['decisionId']}/reject").json()["status"] == "rejected"
    assert fresh.get("/api/store/overview").json()["activeIncident"] is None


def test_legacy_confirm(fresh, incident):
    r = fresh.post("/api/decisions/confirm", json={"batch_id": "STB-042"}).json()
    assert r["status"] == "APPROVED" and r["executionId"]
    assert fresh.get(f"/api/executions/{r['executionId']}").status_code == 200


def test_sensor_reading_ingest_triggers_only_on_anomaly(fresh):
    calm = fresh.post("/api/sensors/readings", json={"batch_id": "STB-042", "temperature_c": 5.5}).json()
    assert calm["anomalyFlags"] == [] and calm["decisionId"] is None
    hot = fresh.post("/api/sensors/simulate", json={"batch_id": "STB-042", "scenario": "TEMPERATURE_SPIKE"}).json()
    assert hot["anomalyFlags"] == ["HIGH_TEMPERATURE"] and hot["decisionId"]


def test_sales_update_ledger_and_velocity(fresh):
    before = fresh.get("/api/batches/STB-042").json()["batch"]
    r = fresh.post("/api/sales", json={"batch_id": "STB-042", "quantity": 10}).json()
    assert r["onHand"] == before["units"] - 10
    after = fresh.get("/api/batches/STB-042").json()["batch"]
    assert after["demand"]["rate"] == before["demand"]["rate"] + 2.0  # 10 units over the 5 h window
    moves = fresh.get("/api/batches/STB-042/movements").json()["movements"]
    assert moves[0]["type"] == "sale" and moves[0]["quantity"] == 10
    assert fresh.post("/api/sales", json={"batch_id": "STB-042", "quantity": 10_000}).status_code == 400


def test_csv_intake(fresh):
    csv = (
        "batch_id,sku,store_id,supplier_id,lot_code,harvest_date,received_at,expiry_at,quantity,price,location,sensor_id\n"
        "STB-050,strawberry-250g,store-042,sup-nandi,NHF-2612-B1,2026-10-11,2026-10-12T02:00:00Z,2099-01-01T00:00:00Z,96,175,Chiller C-02,SNS-C02\n"
        "BAD-001,unknown-sku,store-042,,L1,,,2099-01-01T00:00:00Z,10,,,\n"
        "BAD-002,milk-toned-1l,store-042,,L2,,2026-10-12T02:00:00Z,2026-10-11T00:00:00Z,10,,,\n"
    )
    r = fresh.post("/api/intake/batches/csv", files={"file": ("batches.csv", csv, "text/csv")}).json()
    assert r["created"] == ["STB-050"]
    assert [e["row"] for e in r["errors"]] == [3, 4]
    assert fresh.get("/api/inventory/STB-050").json()["units"] == 96


def test_json_intake_validation(fresh):
    ok = {"batch_id": "LET-200", "sku": "lettuce-iceberg", "lot_code": "HG-1", "expiry_at": "2099-01-01T00:00:00Z", "quantity": 20}
    assert fresh.post("/api/intake/batches", json=ok).status_code == 201
    assert fresh.post("/api/intake/batches", json=ok).status_code == 400  # duplicate
    assert fresh.post("/api/intake/batches", json={**ok, "batch_id": "X-1", "quantity": 0}).status_code == 422


def test_image_upload_without_key_uses_simulated_vision(fresh):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = fresh.post(
        "/api/batches/SPN-118/images", files={"file": ("shelf.png", io.BytesIO(png), "image/png")}, data={"image_type": "reference"}
    )
    assert r.status_code == 200 and r.json()["model"] == "simulated-vision"
    bad = fresh.post("/api/batches/SPN-118/images", files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")})
    assert bad.status_code == 400
    assert len(fresh.get("/api/batches/SPN-118/images").json()["images"]) == 2


def test_network_graph_marks_selected_destination(fresh, incident):
    g = fresh.get("/api/network/graph", params={"batch_id": "STB-042"}).json()
    selected = [n for n in g["nodes"] if n["selected"]]
    assert [n["id"] for n in selected] == ["hub-whitefield"]
    kadugodi = next(n for n in g["nodes"] if n["id"] == "dark-kadugodi")
    assert kadugodi["verdict"] == "No cold capacity"
    assert all(0 <= n["x"] <= 1 and 0 <= n["y"] <= 1 for n in g["nodes"])


def test_score_is_what_if_only(fresh):
    r = fresh.post("/api/decisions/score", json={"batch_id": "STB-042"}).json()
    assert r["options"] and fresh.get("/api/store/overview").json()["activeIncident"] is None


def test_monitor_sweep_creates_no_spurious_decisions(fresh):
    r = fresh.post("/api/monitor/run").json()
    assert r["checked"] == 13 and r["decisionsCreated"] == []


def test_analytics_export(fresh, incident):
    fresh.post(f"/api/decisions/{incident['decisionId']}/approve")
    r = fresh.post("/api/analytics/export").json()
    assert r["destination"].startswith("file:") and r["tables"]["decisions"] >= 6 and r["tables"]["actions"] >= 9


def test_reads_during_reset_never_fail(fresh):
    import threading

    statuses: list[int] = []
    done = threading.Event()

    def reader():
        while not done.is_set():
            statuses.append(fresh.get("/api/store/overview").status_code)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for _ in range(3):
        assert fresh.post("/api/demo/reset").status_code == 200
    done.set()
    for t in threads:
        t.join()
    assert statuses and set(statuses) == {200}
