import os
import tempfile

os.environ["DATABASE_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="tradepilot-test-"), "tradepilot_test.db"
)
os.environ["SECRET_KEY"] = "test-secret-long-enough"
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

def test_register_login():
    with TestClient(app) as client:
        username = "tester_smoke"
        password = "password12345"
        r = client.post(
            "/auth/register", json={"username": username, "password": password}
        )
        assert r.status_code == 200
        r = client.post(
            "/auth/login", json={"username": username, "password": password}
        )
        assert r.status_code == 200
        assert "access_token" in r.json()
