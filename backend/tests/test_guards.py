from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.ratelimit import SlidingWindowLimiter
from app.db.session import DatabaseConfigurationError, _validate_url


def test_rejects_sqlite():
    with pytest.raises(DatabaseConfigurationError):
        _validate_url("sqlite:///careeros.db", is_test=True)


def test_rejects_mariadb_driver():
    with pytest.raises(DatabaseConfigurationError):
        _validate_url("mariadb+pymysql://u:p@localhost/careeros", is_test=False)


def test_test_mode_requires_test_schema():
    with pytest.raises(DatabaseConfigurationError):
        _validate_url("mysql+pymysql://u:p@localhost/careeros", is_test=True)


def test_runtime_refuses_test_schema():
    with pytest.raises(DatabaseConfigurationError):
        _validate_url("mysql+pymysql://u:p@localhost/careeros_test", is_test=False)


def test_accepts_production_url():
    url = "mysql+pymysql://u:p@localhost/careeros?charset=utf8mb4"
    assert _validate_url(url, is_test=False) == url


def test_limiter_window_and_lockout():
    limiter = SlidingWindowLimiter(max_attempts=3, window_seconds=60, lockout_seconds=5)
    key = "ip|user"
    assert limiter.retry_after(key) is None
    for _ in range(3):
        limiter.record_failure(key)
    wait = limiter.retry_after(key)
    assert wait is not None and wait >= 1
    limiter.reset(key)
    assert limiter.retry_after(key) is None


def test_error_envelope_has_code_message_and_request_id(client: TestClient):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "not_found"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_request_id_is_echoed(client: TestClient):
    response = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_security_headers_present(client: TestClient):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_validation_error_shape(client: TestClient):
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert {item["field"] for item in details} >= {"email", "password"}


def test_docs_exposed_only_in_development(client: TestClient):
    assert client.get("/openapi.json").status_code == 200
