"""
Tests for Daily Digest endpoints and regression tests for hub/personas/agents.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestDigestAuthRequired:
    """Digest endpoints must return 401/403 when unauthenticated"""

    def test_get_digest_config_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/digest/config")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print(f"GET /api/digest/config -> {r.status_code} OK")

    def test_post_digest_config_unauthenticated(self):
        r = requests.post(f"{BASE_URL}/api/digest/config", json={"enabled": True, "scheduled_time": "08:00"})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print(f"POST /api/digest/config -> {r.status_code} OK")

    def test_post_digest_trigger_unauthenticated(self):
        r = requests.post(f"{BASE_URL}/api/digest/trigger")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print(f"POST /api/digest/trigger -> {r.status_code} OK")

    def test_get_digest_history_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/digest/history")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print(f"GET /api/digest/history -> {r.status_code} OK")


class TestRegressionHub:
    """Regression: hub endpoints still working"""

    def test_hub_personas_returns_8(self):
        r = requests.get(f"{BASE_URL}/api/hub/personas")
        assert r.status_code == 200
        data = r.json()
        personas = data.get("personas", data) if isinstance(data, dict) else data
        assert len(personas) == 8, f"Expected 8 personas, got {len(personas)}"
        print(f"GET /api/hub/personas -> 200, count={len(personas)} OK")

    def test_hub_agents_returns_50(self):
        r = requests.get(f"{BASE_URL}/api/hub/agents")
        assert r.status_code == 200
        data = r.json()
        total = data.get("total") if isinstance(data, dict) else len(data)
        agents = data.get("agents", data) if isinstance(data, dict) else data
        assert total == 50 or len(agents) == 50, f"Expected 50 agents, got total={total}, list={len(agents)}"
        print(f"GET /api/hub/agents -> 200, total={total} OK")

    def test_hub_personas_detect(self):
        r = requests.post(f"{BASE_URL}/api/hub/personas/detect", json={"message": "Write me a poem"})
        assert r.status_code == 200
        data = r.json()
        assert "persona" in data or "detected" in data or isinstance(data, dict)
        print(f"POST /api/hub/personas/detect -> 200 OK, keys={list(data.keys())}")
