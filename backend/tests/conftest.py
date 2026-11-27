"""Test harness.

Hard isolation rules (PRD 5.2): tests only ever touch a schema whose name ends in
``_test``. The URL comes from ``TEST_DATABASE_URL``; ``DATABASE_URL`` is also rewritten
so Alembic and the app engine agree.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

os.environ["CAREEROS_ENV"] = "test"
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Never let a developer's real key make the suite call an external provider.
os.environ["GEMINI_API_KEY"] = ""
os.environ["CLOUDFLARE_API_TOKEN"] = ""
os.environ["CLOUDFLARE_ACCOUNT_ID"] = ""
os.environ["AI_ALLOW_TRAINING_PROVIDERS"] = "false"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="careeros-test-")

from app.core.config import Settings, get_settings  # noqa: E402

_bootstrap = Settings()  # type: ignore[call-arg]
_test_url = _bootstrap.test_database_url
if not _test_url:
    raise RuntimeError("TEST_DATABASE_URL must be set for the test suite.")

os.environ["DATABASE_URL"] = _test_url
get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories import owner as owner_repo  # noqa: E402
from app.services import auth as auth_service  # noqa: E402

OWNER_EMAIL = "owner@careeros.dev"
OWNER_PASSWORD = "TestPassword!2026"


def _reset_schema() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.fixture(scope="session", autouse=True)
def migrated_schema():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", _test_url)
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_state(migrated_schema):
    _reset_schema()
    auth_service.reset_limiter()
    # Health/breaker and quota state are process-local; isolate every test from the previous one.
    from app.ai.health import health_store
    from app.ai.quota import quota_store

    health_store.reset()
    quota_store.reset()
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner():
    with session_scope() as db:
        created = owner_repo.create_owner(
            db,
            email=OWNER_EMAIL,
            password_hash=hash_password(OWNER_PASSWORD),
            full_name="Test Owner",
        )
        owner_id = created.id
    return owner_id


@pytest.fixture
def auth_client(client: TestClient, owner: str) -> TestClient:
    response = client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def company(auth_client: TestClient) -> dict:
    response = auth_client.post(
        "/api/v1/companies",
        json={"name": "Northstar Labs", "industry": "Software", "location": "Bengaluru"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def ai_settings():
    """Factory for AI settings that never reads a real credential from backend/.env."""

    def make(**overrides) -> Settings:
        values = {
            "secret_key": "test-secret-key-0123456789abcdef0123456789abcdef",
            "database_url": "mysql+pymysql://user:pass@127.0.0.1:3306/careeros",
            "ai_provider_order": "cloudflare",
            "ai_approved_providers": "cloudflare",
            "cloudflare_api_token": "test-token",
            "cloudflare_account_id": "test-account",
            "cloudflare_model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "gemini_api_key": None,
            "ai_allow_training_providers": False,
            "ai_free_only": True,
        }
        values.update(overrides)
        return Settings(**values)

    return make
