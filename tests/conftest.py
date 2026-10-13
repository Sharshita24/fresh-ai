import os
import tempfile

# configure before the app is imported: throwaway SQLite, no network, no background loop, rules engine
_tmp = tempfile.mkdtemp(prefix="freshchain-tests-")
# run against PostgreSQL with: TEST_DATABASE_URL=postgresql+psycopg://user@host/db pytest
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["WEATHER_LIVE"] = "false"
os.environ["MONITOR_INTERVAL_SECONDS"] = "0"
os.environ["GEMINI_API_KEY"] = ""
os.environ["AUTO_EXECUTE"] = "false"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["EXPORT_DIR"] = f"{_tmp}/exports"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh(client):
    """Each test starts from the same demo morning."""
    assert client.post("/api/demo/reset").status_code == 200
    return client


@pytest.fixture()
def incident(fresh):
    """The strawberry chiller incident, decided but not yet executed."""
    r = fresh.post("/api/demo/incident", json={"batch_id": "STB-042"})
    assert r.status_code == 200
    return r.json()["decision"]
