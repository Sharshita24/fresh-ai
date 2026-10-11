import os

from app.services.gemini_agent import is_gemini_configured


def test_gemini_client_reports_unconfigured_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert is_gemini_configured() is False
