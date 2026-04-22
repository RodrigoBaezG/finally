"""Smoke tests for GET /api/health."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_health_content_type(client: TestClient) -> None:
    response = client.get("/api/health")
    assert "application/json" in response.headers["content-type"]
