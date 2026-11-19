from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password, verify_password
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD


def test_no_registration_endpoint(client: TestClient, owner: str):
    assert client.post("/api/v1/auth/register", json={}).status_code == 404


def test_login_success_sets_cookies(client: TestClient, owner: str):
    response = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["owner"]["email"] == OWNER_EMAIL
    assert "careeros_refresh" in response.cookies
    assert "careeros_csrf" in response.cookies
    assert response.headers["cache-control"] == "no-store"


def test_login_wrong_password_is_generic(client: TestClient, owner: str):
    response = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_unknown_email_matches_wrong_password_shape(client: TestClient, owner: str):
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@careeros.dev", "password": "whatever-123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_login_rate_limit_locks_out(client: TestClient, owner: str):
    for _ in range(6):
        client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "bad-password"})
    blocked = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert blocked.status_code == 429
    details = blocked.json()["error"]["details"]
    assert details["retry_after_seconds"] >= 1


def test_refresh_rotation_and_reuse_detection(client: TestClient, owner: str):
    login = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    old_refresh = login.cookies["careeros_refresh"]
    csrf = login.cookies["careeros_csrf"]

    rotated = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200, rotated.text
    new_refresh = rotated.cookies["careeros_refresh"]
    csrf = client.cookies["careeros_csrf"]
    assert new_refresh != old_refresh

    # Replaying the superseded token must burn the family.
    client.cookies.set("careeros_refresh", old_refresh, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_reuse"

    client.cookies.set("careeros_refresh", new_refresh, path="/api/v1/auth")
    after = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert after.status_code == 401


def test_refresh_requires_csrf_header(client: TestClient, owner: str):
    client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_missing"

    wrong = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "forged"})
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "csrf_invalid"


def test_protected_route_rejects_missing_and_bad_tokens(client: TestClient):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"


def test_me_and_profile_update(auth_client: TestClient):
    me = auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    updated = auth_client.patch(
        "/api/v1/auth/me", json={"timezone": "Asia/Kolkata", "currency": "inr", "theme": "dark"}
    )
    assert updated.status_code == 200
    assert updated.json()["timezone"] == "Asia/Kolkata"
    assert updated.json()["currency"] == "INR"
    assert updated.json()["theme"] == "dark"


def test_change_password_revokes_other_sessions(client: TestClient, owner: str):
    first = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    token = first.json()["access_token"]
    client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})

    headers = {"Authorization": f"Bearer {token}"}
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": OWNER_PASSWORD, "new_password": "BrandNew!Pass2026"},
    )
    assert changed.status_code == 200, changed.text

    sessions = client.get("/api/v1/auth/sessions", headers=headers).json()
    assert sum(1 for s in sessions if s["revoked_at"] is None) == 1
    assert any(s["current"] for s in sessions)


def test_weak_new_password_is_rejected(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": OWNER_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


def test_session_revoke_one(auth_client: TestClient):
    # The fixture signed in once; a second login gives us a non-current session to revoke.
    auth_client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    sessions = auth_client.get("/api/v1/auth/sessions").json()
    target = next(s for s in sessions if not s["current"])
    assert auth_client.delete(f"/api/v1/auth/sessions/{target['id']}").status_code == 204
    refreshed = auth_client.get("/api/v1/auth/sessions").json()
    assert all(s["id"] != target["id"] for s in refreshed)


def test_logout_clears_session(auth_client: TestClient):
    csrf = auth_client.cookies.get("careeros_csrf")
    response = auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf or ""})
    assert response.status_code == 204


def test_export_contains_owner_data(auth_client: TestClient, company: dict):
    response = auth_client.get("/api/v1/auth/export")
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"]["email"] == OWNER_EMAIL
    assert payload["counts"]["companies"] == 1
    assert "attachment" in response.headers["content-disposition"]


def test_delete_account_requires_confirmation(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/auth/delete-account",
        json={"password": OWNER_PASSWORD, "confirmation": "delete"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "confirmation_mismatch"


def test_password_hash_roundtrip():
    digest = hash_password("CorrectHorseBattery1!")
    assert digest.startswith("$argon2id$")
    assert verify_password("CorrectHorseBattery1!", digest)
    assert not verify_password("nope", digest)


def test_meta_endpoint_reports_configuration(client: TestClient, owner: str):
    response = client.get("/api/v1/auth/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["owner_configured"] is True
    assert body["ai_configured"] is False


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_ops_endpoints(client: TestClient, path: str):
    response = client.get(path)
    assert response.status_code == 200
    assert "password" not in response.text.lower()
