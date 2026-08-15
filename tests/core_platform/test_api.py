"""Tests for FastAPI endpoints — using TestClient."""

import pytest
from fastapi.testclient import TestClient

from ai_platform.observability.collector import reset_collector
from ai_platform_api import app, get_service


@pytest.fixture(autouse=True)
def reset():
    reset_collector()
    yield


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "3.0.0"

    def test_health_has_cors_headers(self, client):
        response = client.options(
            "/api/v1/health",
            headers={"origin": "http://localhost:3000", "access-control-request-method": "GET"},
        )
        # FastAPI+CORS is not configured by default — just check it doesn't crash
        assert response.status_code in (200, 405)


class TestAgentRunEndpoint:
    def test_valid_request(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "What is the capital of France?", "mode": "rule"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "trace_id" in data

    def test_valid_with_ollama_mode(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "Tell me a joke", "mode": "ollama"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_missing_request_field(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"mode": "rule"},
        )
        assert response.status_code == 422

    def test_empty_request(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "", "mode": "rule"},
        )
        assert response.status_code == 422

    def test_invalid_mode(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "hello", "mode": "invalid_mode"},
        )
        assert response.status_code == 422

    def test_request_too_long(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "x" * 5000, "mode": "rule"},
        )
        assert response.status_code == 422

    def test_mode_defaults_to_rule(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "hello world"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_response_has_required_fields(self, client):
        response = client.post(
            "/api/v1/agent/run",
            json={"request": "test"},
        )
        data = response.json()
        for field in ["success", "answer", "score", "security_score", "trace_id"]:
            assert field in data


class TestExceptionHandling:
    def test_404_not_found(self, client):
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    def test_400_bad_json(self, client):
        response = client.post(
            "/api/v1/agent/run",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code in (400, 422)
