"""M1-B: retry ownership, policy and attempt accounting.

Policy tests use a scripted provider and an injected sleep. Job-level tests use the real
``analysis.run()`` with a mocked Cloudflare transport; no socket is opened.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.ai.base import (
    AnalysisRequest,
    ProviderAuthFailed,
    ProviderBlocked,
    ProviderEntitlementDenied,
    ProviderError,
    ProviderInvalidModel,
    ProviderJsonParseError,
    ProviderNetworkError,
    ProviderPermissionDenied,
    ProviderPrivacyDenied,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.retry import analyze_with_retry, retry_delay_seconds
from tests.test_ai_integration import _setup, _success, _use_provider


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "ai_max_attempts": 3,
        "ai_retry_base_delay_seconds": 1.0,
        "ai_retry_max_delay_seconds": 10.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _request() -> AnalysisRequest:
    return AnalysisRequest(resume_text="r", jd_text="j", jd_title="t")


class ScriptedProvider:
    """Returns or raises each step in order and records how many calls were made."""

    name = "cloudflare"
    model = "test-model"
    scope = "account"

    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)
        self.calls = 0

    def analyze(self, request: AnalysisRequest) -> object:
        self.calls += 1
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_transient_errors_use_exponential_backoff():
    settings = _settings()
    assert retry_delay_seconds(ProviderUnavailable("x"), attempt=1, settings=settings) == 1.0
    assert retry_delay_seconds(ProviderTimeout("x"), attempt=2, settings=settings) == 2.0
    assert retry_delay_seconds(ProviderNetworkError("x"), attempt=3, settings=settings) == 4.0


def test_backoff_is_capped():
    settings = _settings(ai_retry_max_delay_seconds=3.0)
    assert retry_delay_seconds(ProviderUnavailable("x"), attempt=4, settings=settings) == 3.0


@pytest.mark.parametrize(
    "error",
    [
        ProviderAuthFailed("x"),
        ProviderPermissionDenied("x"),
        ProviderEntitlementDenied("x"),
        ProviderPrivacyDenied("x"),
        ProviderInvalidModel("x"),
        ProviderUnsupportedCapability("x"),
        ProviderBlocked("x"),
        ProviderJsonParseError("x"),
        ProviderSchemaError("x"),
        ProviderError("x", code="provider_rejected"),
        ProviderError("x", code="resume_too_large_for_provider"),
    ],
)
def test_terminal_errors_are_not_retried(error):
    assert retry_delay_seconds(error, attempt=1, settings=_settings()) is None


def test_rate_limit_is_retried_only_within_the_bound():
    settings = _settings(ai_retry_max_delay_seconds=10.0)
    short = ProviderRateLimited("x", retry_after_seconds=2.0)
    long = ProviderRateLimited("x", retry_after_seconds=30.0)
    assert retry_delay_seconds(short, attempt=1, settings=settings) == 2.0
    assert retry_delay_seconds(long, attempt=1, settings=settings) is None
    assert retry_delay_seconds(ProviderRateLimited("x"), attempt=1, settings=settings) is None


def test_quota_exhaustion_is_not_retried():
    error = ProviderQuotaExhausted("x", retry_after_seconds=2.0)
    assert retry_delay_seconds(error, attempt=1, settings=_settings()) is None


def test_analyze_with_retry_retries_transient_errors_on_the_same_provider():
    output = object()
    provider = ScriptedProvider(ProviderUnavailable("x"), ProviderTimeout("x"), output)
    sleeps: list[float] = []

    result = analyze_with_retry(
        provider, _request(), _settings(ai_max_attempts=3), sleep=sleeps.append
    )

    assert result is output
    assert provider.calls == 3
    assert sleeps == [1.0, 2.0]


def test_analyze_with_retry_stops_at_the_cap():
    provider = ScriptedProvider(ProviderUnavailable("x"), ProviderUnavailable("x"))
    sleeps: list[float] = []

    with pytest.raises(ProviderUnavailable):
        analyze_with_retry(
            provider, _request(), _settings(ai_max_attempts=2), sleep=sleeps.append
        )

    assert provider.calls == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    "error",
    [ProviderAuthFailed("x"), ProviderPermissionDenied("x"), ProviderJsonParseError("x")],
)
def test_analyze_with_retry_does_not_retry_terminal_errors(error):
    provider = ScriptedProvider(error)
    sleeps: list[float] = []

    with pytest.raises(type(error)):
        analyze_with_retry(provider, _request(), _settings(), sleep=sleeps.append)

    assert provider.calls == 1
    assert sleeps == []


def test_analyze_with_retry_honours_retry_after():
    output = object()
    provider = ScriptedProvider(ProviderRateLimited("x", retry_after_seconds=2.0), output)
    sleeps: list[float] = []

    assert analyze_with_retry(provider, _request(), _settings(), sleep=sleeps.append) is output
    assert provider.calls == 2
    assert sleeps == [2.0]


def _job_body(auth_client, response) -> dict:
    assert response.status_code == 201, response.text
    return auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()


def _retry_settings(ai_settings, monkeypatch, **overrides):
    values = {
        "ai_max_attempts": 2,
        "ai_retry_base_delay_seconds": 1.0,
        "ai_retry_max_delay_seconds": 10.0,
    }
    values.update(overrides)
    settings = ai_settings(**values)
    monkeypatch.setattr("app.services.analysis.get_settings", lambda: settings)
    return settings


def test_job_retries_timeout_once_and_keeps_one_job_attempt(
    auth_client, company, ai_settings, monkeypatch
):
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    _retry_settings(ai_settings, monkeypatch)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, slow)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_timeout"
    assert body["attempts"] == 1
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_job_retries_network_failure_once(auth_client, company, ai_settings, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    _retry_settings(ai_settings, monkeypatch)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, down)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_network_error"
    assert body["attempts"] == 1
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_job_does_not_retry_permission_denial(
    auth_client, company, ai_settings, monkeypatch
):
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    _retry_settings(ai_settings, monkeypatch)

    def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"success": False, "errors": [{"code": 9999, "message": "no"}]}
        )

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, forbidden)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_permission_denied"
    assert body["attempts"] == 1
    assert len(calls) == 1
    assert sleeps == []


def test_job_honours_a_short_retry_after(auth_client, company, ai_settings, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.ai.retry.time.sleep", sleeps.append)
    _retry_settings(ai_settings, monkeypatch)

    responses = [
        lambda request: httpx.Response(
            429, json={"success": False}, headers={"retry-after": "2"}
        ),
        _success,
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)(request)

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, handler)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "succeeded"
    assert body["attempts"] == 1
    assert len(calls) == 2
    assert sleeps == [2.0]
