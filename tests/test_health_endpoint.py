"""
Integration test for core-api's /health endpoint.

Unlike test_schemas.py, this test requires the real stack to be running
(docker compose up). Run it AFTER `make up`, as the final verification
step for Module 1:

    pip install httpx pytest
    python -m pytest tests/test_health_endpoint.py -v
"""

import httpx
import pytest

BASE_URL = "http://localhost:8000"


def test_root_endpoint_reachable():
    r = httpx.get(f"{BASE_URL}/")
    assert r.status_code == 200
    assert r.json()["service"] == "core-api"


def test_health_endpoint_reports_both_dependencies():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code in (200, 503)  # 503 only if something is genuinely down
    body = r.json()
    assert "postgres" in body["dependencies"]
    assert "redis" in body["dependencies"]


def test_health_endpoint_ok_when_stack_is_up():
    """
    This is the real acceptance criterion for Module 1: if this test
    passes, Postgres, Redis, and core-api are all wired correctly.
    """
    r = httpx.get(f"{BASE_URL}/health")
    body = r.json()
    if r.status_code != 200:
        pytest.fail(
            f"Stack not fully healthy -- check `docker compose logs`. "
            f"Details: {body['dependencies']}"
        )
    assert body["dependencies"]["postgres"]["ok"] is True
    assert body["dependencies"]["redis"]["ok"] is True
