"""Gemini paths, using a fake model so no key or network is needed."""

from app.services import gemini_agent


def test_unconfigured_returns_none():
    assert gemini_agent.is_configured() is False
    assert gemini_agent.coordinate({"x": 1}, ["keep"]) is None
    assert gemini_agent.inspect_image(b"img", "image/png", "Strawberry") is None


def test_coordinator_uses_gemini_choice_within_shortlist(fresh, monkeypatch):
    calls = []

    def fake_generate(contents, schema, system, max_tokens):
        calls.append(contents)
        choice = schema(
            option_id="transfer_84",
            confidence=0.9,
            rationale="Move stock to the hub; keep full price.",
            evidence=[gemini_agent.EvidenceLine(signal="Network", finding="hub demand", impact="clears in time")],
        )
        return choice, {"model": "gemini-test", "latencyMs": 420, "tokensIn": 900, "tokensOut": 40, "tokensCached": 600}

    monkeypatch.setattr(gemini_agent, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_agent, "_generate", fake_generate)
    d = fresh.post("/api/demo/incident").json()["decision"]
    assert len(calls) == 1  # one coordinated call per decision, not one per agent
    assert '"allowed_option_ids"' in calls[0]
    assert d["selectedOption"] == "transfer_84" and d["modelUsed"] == "gemini-test"
    assert d["rationale"].startswith("Move stock") and d["modelMeta"]["tokensIn"] == 900


def test_coordinator_ignores_hallucinated_option(fresh, monkeypatch):
    def fake_generate(contents, schema, system, max_tokens):
        return schema(option_id="sell_to_the_moon", confidence=1.0, rationale="?"), {"model": "gemini-test"}

    monkeypatch.setattr(gemini_agent, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_agent, "_generate", fake_generate)
    d = fresh.post("/api/demo/incident").json()["decision"]
    assert d["selectedOption"] == "transfer_84_markdown_20" and d["modelUsed"] == "rules"
