"""M2-A: passive provider health recording. No live provider and no circuit breaker."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
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
)
from app.ai.health import (
    RECENT_OUTCOME_LIMIT,
    HealthRecord,
    InMemoryHealthStore,
)
from app.ai.retry import analyze_with_retry
from tests.test_ai_integration import MODEL, _setup, _success, _use_provider

CANARY = "RESUME_CANARY_7f3c9a"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _request() -> AnalysisRequest:
    return AnalysisRequest(resume_text="r", jd_text="j", jd_title="t")


def _retry_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ai_max_attempts=3,
        ai_retry_base_delay_seconds=1.0,
        ai_retry_max_delay_seconds=10.0,
    )


def _job_body(auth_client, response) -> dict:
    assert response.status_code == 201, response.text
    return auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()


def test_initial_state_is_healthy():
    store = InMemoryHealthStore()
    record = store.get("cloudflare", MODEL)

    assert record.state == "healthy"
    assert record.successes == 0
    assert record.failures == 0
    assert record.consecutive_failures == 0
    assert record.latency_ms_ewma is None
    assert record.recent_outcomes == ()
    assert store.snapshot() == {}


def test_success_updates_model_and_provider_records():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)

    store.record_success("cloudflare", MODEL, 25.0)

    for record in (store.get("cloudflare", MODEL), store.get("cloudflare")):
        assert record.successes == 1
        assert record.state == "healthy"
        assert record.last_success_at == 0.0
        assert record.latency_ms_ewma == 25.0
        assert record.latency_samples == 1
        assert record.recent_outcomes == ("success",)


@pytest.mark.parametrize(
    "error",
    [
        ProviderTimeout("timed out"),
        ProviderNetworkError("connection reset"),
        ProviderUnavailable("503"),
    ],
)
def test_transient_failure_degrades_both_levels(error):
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)

    store.record_failure("cloudflare", MODEL, error, 40.0)

    for record in (store.get("cloudflare", MODEL), store.get("cloudflare")):
        assert record.failures == 1
        assert record.consecutive_failures == 1
        assert record.state == "degraded"
        assert record.last_failure_at == 0.0
        assert record.last_failure_class == "transient"
        assert record.recent_outcomes == ("transient_failure",)
        assert record.latency_ms_ewma == 40.0


@pytest.mark.parametrize("error", [ProviderAuthFailed("bad key"), ProviderPermissionDenied("no")])
def test_auth_and_permission_disable_without_a_transient_streak(error):
    store = InMemoryHealthStore()

    store.record_failure("cloudflare", MODEL, error, 10.0)

    for record in (store.get("cloudflare", MODEL), store.get("cloudflare")):
        assert record.failures == 1
        assert record.consecutive_failures == 0
        assert record.state == "disabled"
        assert record.disabled_reason in {"auth", "permission"}
        assert record.last_failure_class in {"auth", "permission"}


def test_entitlement_denial_is_a_permission_disable():
    store = InMemoryHealthStore()
    store.record_failure("cloudflare", MODEL, ProviderEntitlementDenied("plan"), 10.0)

    record = store.get("cloudflare", MODEL)
    assert record.disabled_reason == "permission"
    assert record.state == "disabled"


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimited("slow down"),
        ProviderQuotaExhausted("quota"),
        ProviderInvalidModel("missing model"),
        ProviderBlocked("blocked content"),
        ProviderPrivacyDenied("gate"),
        ProviderError("rejected", code="provider_rejected"),
    ],
)
def test_non_health_failures_do_not_create_records(error):
    store = InMemoryHealthStore()
    store.record_failure("cloudflare", MODEL, error, 10.0)

    assert store.snapshot() == {}
    assert store.get("cloudflare", MODEL).state == "healthy"


@pytest.mark.parametrize("error", [ProviderJsonParseError("not json"), ProviderSchemaError("bad")])
def test_quality_failure_is_a_model_observation_only(error):
    store = InMemoryHealthStore()
    store.record_failure("cloudflare", MODEL, error, 10.0)

    record = store.get("cloudflare", MODEL)
    assert record.quality_failures == 1
    assert record.failures == 0
    assert record.consecutive_failures == 0
    assert record.last_failure_class == "quality"
    assert record.state == "healthy"
    assert ("cloudflare", None) not in store.snapshot()


def test_latency_uses_an_ewma():
    store = InMemoryHealthStore()
    for sample in (100.0, 200.0, 300.0):
        store.record_success("cloudflare", MODEL, sample)

    record = store.get("cloudflare", MODEL)
    assert record.latency_samples == 3
    assert record.latency_ms_ewma == pytest.approx(181.0)


def test_recent_outcomes_are_bounded():
    store = InMemoryHealthStore()
    for _ in range(RECENT_OUTCOME_LIMIT + 5):
        store.record_success("cloudflare", MODEL, 1.0)

    record = store.get("cloudflare", MODEL)
    assert len(record.recent_outcomes) == RECENT_OUTCOME_LIMIT
    assert set(record.recent_outcomes) == {"success"}


def test_consecutive_failures_reset_after_success():
    store = InMemoryHealthStore()
    for _ in range(3):
        store.record_failure("cloudflare", MODEL, ProviderTimeout("slow"), 10.0)

    record = store.get("cloudflare", MODEL)
    assert record.failures == 3
    assert record.consecutive_failures == 3
    assert record.state == "degraded"

    store.record_success("cloudflare", MODEL, 10.0)

    record = store.get("cloudflare", MODEL)
    assert record.successes == 1
    assert record.consecutive_failures == 0
    assert record.state == "healthy"
    assert record.last_failure_class == "transient"


def test_state_derivation_covers_all_agreed_states():
    assert HealthRecord("x").state == "healthy"
    assert HealthRecord("x", consecutive_failures=1).state == "degraded"
    assert HealthRecord("x", opened_at=1.0).state == "open"
    assert HealthRecord("x", opened_at=1.0, half_open_in_flight=True).state == "half_open"
    assert HealthRecord("x", disabled_reason="auth").state == "disabled"
    assert HealthRecord("x", disabled_reason="auth", opened_at=1.0).state == "disabled"


def test_administrative_disable_is_distinct_from_failure_reasons():
    store = InMemoryHealthStore()
    store.record_success("cloudflare", MODEL, 10.0)
    store.disable("cloudflare", None, "manual")

    provider = store.get("cloudflare")
    model = store.get("cloudflare", MODEL)
    assert provider.disabled_reason == "manual"
    assert model.disabled_reason == "manual"
    assert provider.state == "disabled"
    assert model.state == "disabled"

    other = InMemoryHealthStore()
    other.record_failure("cloudflare", MODEL, ProviderAuthFailed("bad key"), 10.0)
    assert other.get("cloudflare", MODEL).disabled_reason == "auth"


def test_concurrent_updates_are_consistent():
    store = InMemoryHealthStore()
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        for _ in range(100):
            store.record_success("cloudflare", MODEL, 1.0)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        for future in futures:
            future.result()

    record = store.get("cloudflare", MODEL)
    assert record.successes == 800
    assert record.consecutive_failures == 0
    assert record.latency_samples == 800


def test_health_records_never_store_private_text():
    store = InMemoryHealthStore()
    store.record_failure(
        "cloudflare",
        MODEL,
        ProviderTimeout(f"timed out {CANARY} test-token"),
        10.0,
    )

    stored = repr(store.snapshot()) + repr(store.get("cloudflare", MODEL))
    assert CANARY not in stored
    assert "test-token" not in stored


class TimedProvider:
    name = "cloudflare"
    model = MODEL
    scope = "account"

    def __init__(self, clock: FakeClock, *steps: object) -> None:
        self.clock = clock
        self.steps = list(steps)
        self.calls = 0

    def analyze(self, request: AnalysisRequest) -> object:
        self.calls += 1
        self.clock.advance(0.5)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_retry_records_each_attempt_and_excludes_sleep_from_latency():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    output = object()
    provider = TimedProvider(
        clock, ProviderUnavailable("503"), ProviderTimeout("slow"), output
    )
    sleeps: list[float] = []

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(100.0)

    result = analyze_with_retry(
        provider,
        _request(),
        _retry_settings(),
        sleep=sleeper,
        health=store,
        clock=clock,
    )

    assert result is output
    assert provider.calls == 3
    assert sleeps == [1.0, 2.0]

    record = store.get("cloudflare", MODEL)
    assert record.successes == 1
    assert record.failures == 2
    assert record.consecutive_failures == 0
    assert record.latency_samples == 3
    assert record.latency_ms_ewma == pytest.approx(500.0)
    assert record.recent_outcomes == ("transient_failure", "transient_failure", "success")


def test_analysis_run_records_a_success(auth_client, company, ai_settings, monkeypatch):
    store = InMemoryHealthStore()
    monkeypatch.setattr("app.services.analysis.health_store", store)

    version_id, jd_id = _setup(auth_client, company)
    _use_provider(monkeypatch, ai_settings, _success)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "succeeded"
    record = store.get("cloudflare", MODEL)
    assert record.successes == 1
    assert record.state == "healthy"


def test_analysis_run_records_a_transient_failure(
    auth_client, company, ai_settings, monkeypatch
):
    store = InMemoryHealthStore()
    monkeypatch.setattr("app.services.analysis.health_store", store)
    monkeypatch.setattr("app.ai.retry.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(
            ai_max_attempts=2, ai_retry_base_delay_seconds=1.0, ai_retry_max_delay_seconds=10.0
        ),
    )

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"success": False})

    version_id, jd_id = _setup(auth_client, company)
    _use_provider(monkeypatch, ai_settings, down)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_unavailable"
    record = store.get("cloudflare", MODEL)
    assert record.failures == 2
    assert record.consecutive_failures == 2
    assert record.state == "degraded"
