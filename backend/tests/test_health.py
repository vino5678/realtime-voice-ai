from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # No model is loaded unless the lifespan startup ran and weights exist.
    assert body["inference"]["available"] is False
    assert "state" in body["inference"]
