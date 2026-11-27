"""B3 M0 characterization: pin the B2 behaviour B3 must not regress.

Each test names the M0 baseline item it freezes. Existing suites already cover parts of
this contract (``test_ai_router``, ``test_ai_cloudflare``, ``test_ai_privacy``,
``test_ai_integration``); this module pins the cross-layer behaviour and the gaps:

1. Cloudflare selection            -> ``test_only_cloudflare_is_approved_and_free``
2. Privacy-denied rejection        -> ``test_privacy_denied_provider_is_never_called``
3. No eligible provider            -> ``test_no_eligible_provider_fails_without_http``
4. Single job attempt            -> ``test_server_error_retries_once_but_counts_one_attempt``
5. Retry ownership (M1-B)        -> same test (orchestration retries, not the adapter), plus the 401/429 cases
6. Provider/model attribution      -> ``test_success_persists_result_and_attribution``
7. Success/failure persistence     -> success test and ``test_auth_failure_persists_no_result``
8. JSON + Pydantic validation      -> ``test_invalid_json_fails_without_repair``
9. No Gemini / paid fallback       -> selection test and privacy-denied test

No real network request is made: the only provider is a mocked ``httpx.MockTransport``.
"""

from __future__ import annotations

import httpx
from sqlalchemy import func, select

from app.ai.base import ProviderAuthFailed
from app.ai.models import MODELS, RESUME_DATA_CLASS, get_model
from app.ai.privacy import approved_candidates, denial_reasons
from app.ai.providers import PROVIDERS
from app.db.enums import AnalysisStatus
from app.db.models import AnalysisJob, AnalysisResult
from app.db.session import session_scope
from tests.test_ai_integration import (
    MODEL,
    VALID_OUTPUT,
    _setup,
    _success,
    _use_provider,
)

APPROVED_MODEL = MODEL
CLOUDFLARE_8B = "@cf/meta/llama-3.1-8b-instruct"


def _job_body(auth_client, response) -> dict:
    assert response.status_code == 201, response.text
    return auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()


def _no_http(*args, **kwargs):
    raise AssertionError("an HTTP client was created before the provider was eligible")


def _result_count() -> int:
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(AnalysisResult))


def test_only_cloudflare_is_approved_and_free(ai_settings):
    """Baseline 1/9: one free, privacy-approved provider; no paid row is routable."""
    settings = ai_settings()

    assert settings.ai_free_only is True
    assert settings.ai_allow_training_providers is False
    assert settings.ai_approved_provider_set == {"cloudflare"}
    assert set(PROVIDERS) == {"cloudflare", "gemini"}

    candidates = approved_candidates(settings)
    assert [(spec.provider, spec.model_id) for spec in candidates] == [
        ("cloudflare", APPROVED_MODEL)
    ]
    assert RESUME_DATA_CLASS in candidates[0].approved_data_classes
    assert candidates[0].free_tier is True

    # Every other registry row stays denied, including the privacy-approved 8B model.
    for spec in MODELS:
        if (spec.provider, spec.model_id) == ("cloudflare", APPROVED_MODEL):
            continue
        assert denial_reasons(spec, settings), (spec.provider, spec.model_id)

    assert "context_unknown" in denial_reasons(get_model("cloudflare", CLOUDFLARE_8B), settings)


def test_privacy_denied_provider_is_never_called(auth_client, company, ai_settings, monkeypatch):
    """Baseline 2/9: a configured-but-denied provider fails the job without an HTTP call."""
    settings = ai_settings(
        ai_provider_order="gemini",
        ai_approved_providers="gemini",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
    )
    monkeypatch.setattr("app.ai.registry.get_settings", lambda: settings)
    monkeypatch.setattr("app.ai.gemini.httpx.Client", _no_http)

    version_id, jd_id = _setup(auth_client, company)
    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_privacy_denied"
    assert body["provider"] == ""
    assert body["model"] == ""
    assert _result_count() == 0


def test_no_eligible_provider_fails_without_http(auth_client, company, ai_settings, monkeypatch):
    """Baseline 3/9: no credentials -> ai_not_configured, no client is constructed."""
    monkeypatch.setattr(
        "app.ai.registry.get_settings",
        lambda: ai_settings(cloudflare_api_token=None, cloudflare_account_id=None),
    )
    monkeypatch.setattr("app.ai.cloudflare.httpx.Client", _no_http)

    version_id, jd_id = _setup(auth_client, company)
    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "ai_not_configured"
    assert "backend/.env" in body["error_message"]
    assert _result_count() == 0


def test_success_persists_result_and_attribution(
    auth_client, company, ai_settings, monkeypatch
):
    """Baseline 6/7: Cloudflare attribution, one attempt, one persisted result."""
    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, _success)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "succeeded"
    assert body["provider"] == "cloudflare"
    assert body["model"] == APPROVED_MODEL
    assert body["attempts"] == 1
    assert body["error_code"] is None
    assert len(calls) == 1
    assert body["result"]["score"] == VALID_OUTPUT["score"]
    assert body["result"]["schema_version"] == "1.0"
    assert "raw_response" not in body["result"]

    with session_scope() as db:
        job = db.get(AnalysisJob, body["id"])
        assert job.status == AnalysisStatus.SUCCEEDED
        assert job.result is not None
        assert job.result.score == VALID_OUTPUT["score"]
        assert job.result.findings_json == VALID_OUTPUT["findings"]
        assert db.scalar(select(func.count()).select_from(AnalysisResult)) == 1


def test_auth_failure_persists_no_result(auth_client, company, ai_settings, monkeypatch):
    """Baseline 4/7: a rejected key is one attempt, one request, and no result row."""
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"success": False, "errors": [{"message": "bad key"}]})

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, unauthorized)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == ProviderAuthFailed.code
    assert body["provider"] == "cloudflare"
    assert body["attempts"] == 1
    assert len(calls) == 1
    assert "test-token" not in str(body)
    assert _result_count() == 0


def test_server_error_retries_once_but_counts_one_attempt(
    auth_client, company, ai_settings, monkeypatch
):
    """Baseline 4/5: orchestration retries 5xx once; the job still records one attempt."""
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(
            ai_max_attempts=2, ai_retry_base_delay_seconds=1.0, ai_retry_max_delay_seconds=10.0
        ),
    )

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"success": False})

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, down)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_unavailable"
    assert body["attempts"] == 1
    assert len(calls) == 2
    assert sleeps == [1.0]
    assert _result_count() == 0


def test_rate_limit_beyond_the_delay_bound_is_not_retried(
    auth_client, company, ai_settings, monkeypatch
):
    """Baseline 5: a Retry-After longer than the bound is terminal, not a blind loop."""
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(
            ai_max_attempts=2, ai_retry_base_delay_seconds=1.0, ai_retry_max_delay_seconds=10.0
        ),
    )

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"success": False}, headers={"retry-after": "30"})

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, limited)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_rate_limited"
    assert body["attempts"] == 1
    assert len(calls) == 1
    assert sleeps == []
    assert _result_count() == 0


def test_invalid_json_fails_without_repair(
    auth_client, company, ai_settings, monkeypatch
):
    """Baseline 8: malformed JSON is invalid_json, no repair prompt, no result row."""
    def prose(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": True, "result": {"response": "this is not json"}}
        )

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, prose)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "invalid_json"
    assert body["attempts"] == 1
    assert len(calls) == 1
    assert _result_count() == 0
