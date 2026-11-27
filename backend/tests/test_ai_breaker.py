"""M2-B: circuit breaker transitions, concurrency and retry integration.

All tests are offline: fake clocks, scripted providers and a mocked Cloudflare transport.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from app.ai.base import (
    AnalysisRequest,
    ProviderAuthFailed,
    ProviderCircuitOpen,
    ProviderEntitlementDenied,
    ProviderJsonParseError,
    ProviderNetworkError,
    ProviderPermissionDenied,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.health import BreakerPolicy, InMemoryHealthStore
from app.ai.retry import analyze_with_retry
from tests.test_ai_integration import MODEL, _setup, _use_provider


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _policy(**overrides) -> BreakerPolicy:
    return replace(BreakerPolicy(), **overrides)


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "ai_max_attempts": 3,
        "ai_retry_base_delay_seconds": 1.0,
        "ai_retry_max_delay_seconds": 10.0,
        "ai_breaker_enabled": True,
        "ai_breaker_failures": 3,
        "ai_breaker_cooldown_seconds": 120.0,
        "ai_breaker_cooldown_max_seconds": 900.0,
        "ai_breaker_backoff_multiplier": 2.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _request() -> AnalysisRequest:
    return AnalysisRequest(resume_text="r", jd_text="j", jd_title="t")


class ScriptedProvider:
    name = "cloudflare"
    model = MODEL
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


def _fail(store: InMemoryHealthStore, policy: BreakerPolicy, times: int = 1) -> None:
    for _ in range(times):
        store.record_failure("cloudflare", MODEL, ProviderUnavailable("503"), 10.0, policy=policy)


def _job_body(auth_client, response) -> dict:
    assert response.status_code == 201, response.text
    return auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()


def test_three_transient_failures_open_the_breaker():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()

    _fail(store, policy, times=2)
    assert store.get("cloudflare", MODEL).state == "degraded"

    _fail(store, policy)
    record = store.get("cloudflare")
    assert record.state == "open"
    assert record.consecutive_failures == 3
    assert record.opened_at == 0.0
    assert record.cooldown_seconds == 120.0


def test_two_failures_do_not_open_the_breaker():
    store = InMemoryHealthStore()
    _fail(store, _policy(), times=2)

    record = store.get("cloudflare")
    assert record.state == "degraded"
    assert record.opened_at is None


def test_open_breaker_rejects_without_calling_the_provider():
    # analyze_with_retry receives exactly one provider; same-provider reuse across retries is
    # covered in test_ai_retry, so there is no fallback path to exercise here.
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)

    provider = ScriptedProvider(object())
    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            provider, _request(), _settings(), health=store, clock=clock, sleep=lambda _s: None
        )

    assert provider.calls == 0


def test_open_stays_open_before_the_cooldown_expires():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)

    clock.advance(119.0)
    with pytest.raises(ProviderCircuitOpen):
        store.admit("cloudflare", MODEL, policy)

    assert store.get("cloudflare").state == "open"


def test_open_becomes_half_open_after_the_cooldown():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)

    clock.advance(120.0)
    store.admit("cloudflare", MODEL, policy)

    assert store.get("cloudflare").state == "half_open"


def test_exactly_one_concurrent_half_open_probe_is_admitted():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    clock.advance(120.0)

    barrier = threading.Barrier(8)
    outcomes: list[str] = []

    def worker() -> None:
        barrier.wait()
        try:
            store.admit("cloudflare", MODEL, policy)
            outcomes.append("admitted")
        except ProviderCircuitOpen:
            outcomes.append("blocked")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        for future in futures:
            future.result()

    assert outcomes.count("admitted") == 1
    assert outcomes.count("blocked") == 7
    assert store.get("cloudflare").state == "half_open"


def test_successful_probe_closes_the_breaker():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    clock.advance(120.0)
    store.admit("cloudflare", MODEL, policy)

    store.record_success("cloudflare", MODEL, 20.0)

    record = store.get("cloudflare")
    assert record.state == "healthy"
    assert record.opened_at is None
    assert record.cooldown_seconds == 0.0
    assert record.consecutive_failures == 0


def test_failed_probe_reopens_with_a_doubled_cooldown():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    clock.advance(120.0)
    store.admit("cloudflare", MODEL, policy)

    store.record_failure("cloudflare", MODEL, ProviderTimeout("slow"), 10.0, policy=policy)

    record = store.get("cloudflare")
    assert record.state == "open"
    assert record.opened_at == 120.0
    assert record.cooldown_seconds == 240.0


def test_cooldown_grows_exponentially_and_stops_at_the_cap():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy(max_cooldown_seconds=900.0)
    _fail(store, policy, times=3)

    seen = [store.get("cloudflare").cooldown_seconds]
    for _ in range(5):
        clock.advance(store.get("cloudflare").cooldown_seconds)
        store.admit("cloudflare", MODEL, policy)
        store.record_failure(
            "cloudflare", MODEL, ProviderUnavailable("503"), 10.0, policy=policy
        )
        seen.append(store.get("cloudflare").cooldown_seconds)

    assert seen == [120.0, 240.0, 480.0, 900.0, 900.0, 900.0]


@pytest.mark.parametrize(
    "error",
    [
        ProviderAuthFailed("bad key"),
        ProviderPermissionDenied("no"),
        ProviderEntitlementDenied("plan"),
    ],
)
def test_auth_and_permission_do_not_count_as_transient(error):
    store = InMemoryHealthStore()
    policy = _policy(failure_threshold=1)

    for _ in range(5):
        store.record_failure("cloudflare", MODEL, error, 10.0, policy=policy)

    record = store.get("cloudflare")
    assert record.opened_at is None
    assert record.consecutive_failures == 0
    assert record.state == "disabled"
    assert record.disabled_reason in {"auth", "permission"}


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimited("slow down"),
        ProviderQuotaExhausted("quota"),
        ProviderJsonParseError("not json"),
        ProviderSchemaError("bad shape"),
    ],
)
def test_rate_limit_quota_and_quality_do_not_open_the_breaker(error):
    store = InMemoryHealthStore()
    policy = _policy(failure_threshold=1)

    for _ in range(5):
        store.record_failure("cloudflare", MODEL, error, 10.0, policy=policy)

    record = store.get("cloudflare")
    assert record.opened_at is None
    assert record.consecutive_failures == 0
    assert record.state in {"healthy", "degraded"}


def test_network_and_timeout_are_transient():
    store = InMemoryHealthStore()
    policy = _policy()

    store.record_failure("cloudflare", MODEL, ProviderNetworkError("reset"), 10.0, policy=policy)
    store.record_failure("cloudflare", MODEL, ProviderTimeout("slow"), 10.0, policy=policy)
    store.record_failure("cloudflare", MODEL, ProviderUnavailable("503"), 10.0, policy=policy)

    assert store.get("cloudflare").state == "open"


def test_non_transient_probe_failure_does_not_reopen():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    clock.advance(120.0)
    store.admit("cloudflare", MODEL, policy)

    store.record_failure("cloudflare", MODEL, ProviderJsonParseError("bad"), 10.0, policy=policy)

    record = store.get("cloudflare")
    assert record.state == "healthy"
    assert record.opened_at is None


def test_manual_disable_cannot_be_cleared_by_success_or_credential_recovery():
    store = InMemoryHealthStore()
    store.disable("cloudflare", None, "manual")

    store.record_success("cloudflare", MODEL, 10.0)
    store.recover_credentials("cloudflare")

    record = store.get("cloudflare")
    assert record.disabled_reason == "manual"
    assert record.state == "disabled"


def test_credential_disable_needs_explicit_recovery():
    store = InMemoryHealthStore()
    store.record_failure("cloudflare", MODEL, ProviderAuthFailed("bad key"), 10.0)

    store.record_success("cloudflare", MODEL, 10.0)
    assert store.get("cloudflare").state == "disabled"

    store.recover_credentials("cloudflare")
    assert store.get("cloudflare").disabled_reason is None
    assert store.get("cloudflare").state == "healthy"


def test_disabled_breaker_reproduces_m2a_behaviour():
    store = InMemoryHealthStore()
    policy = _policy(enabled=False)

    _fail(store, policy, times=10)
    store.admit("cloudflare", MODEL, policy)

    record = store.get("cloudflare")
    assert record.opened_at is None
    assert record.state == "degraded"
    assert record.consecutive_failures == 10


def test_retry_stops_at_an_open_breaker_and_keeps_attempt_accounting():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    settings = _settings(ai_max_attempts=5, ai_breaker_failures=3)
    provider = ScriptedProvider(*(ProviderUnavailable("503") for _ in range(5)))
    sleeps: list[float] = []

    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            provider,
            _request(),
            settings,
            sleep=sleeps.append,
            health=store,
            clock=clock,
        )

    assert provider.calls == 3
    assert sleeps == [1.0, 2.0, 4.0]
    record = store.get("cloudflare")
    assert record.failures == 3
    assert record.state == "open"
    assert record.cooldown_seconds == 120.0


def test_circuit_open_is_not_recorded_as_a_provider_failure():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    before = store.get("cloudflare")

    provider = ScriptedProvider(object())
    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            provider, _request(), _settings(), health=store, clock=clock, sleep=lambda _s: None
        )

    after = store.get("cloudflare")
    assert after.failures == before.failures
    assert after.latency_samples == before.latency_samples
    assert after.recent_outcomes == before.recent_outcomes


def test_job_records_circuit_open_without_extra_http_calls(
    auth_client, company, ai_settings, monkeypatch
):
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    monkeypatch.setattr("app.services.analysis.health_store", store)
    monkeypatch.setattr("app.ai.retry.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(
            ai_max_attempts=3,
            ai_breaker_failures=2,
            ai_breaker_cooldown_seconds=120.0,
            ai_retry_base_delay_seconds=1.0,
            ai_retry_max_delay_seconds=10.0,
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
    assert body["error_code"] == "circuit_open"
    assert body["attempts"] == 1
    assert len(calls) == 2
    assert store.get("cloudflare").state == "open"


def test_unexpected_exception_releases_the_half_open_slot():
    clock = FakeClock()
    store = InMemoryHealthStore(clock=clock)
    policy = _policy()
    _fail(store, policy, times=3)
    clock.advance(120.0)

    class ExplodingProvider:
        name = "cloudflare"
        model = MODEL
        scope = "account"
        calls = 0

        def analyze(self, request: AnalysisRequest) -> object:
            self.calls += 1
            raise RuntimeError("boom")

    provider = ExplodingProvider()
    with pytest.raises(RuntimeError):
        analyze_with_retry(
            provider,
            _request(),
            _settings(ai_max_attempts=1),
            health=store,
            clock=clock,
            sleep=lambda _s: None,
        )

    record = store.get("cloudflare")
    assert record.half_open_in_flight is False
    assert record.state == "open"

    store.admit("cloudflare", MODEL, policy)
    assert store.get("cloudflare").state == "half_open"


def test_privacy_denial_happens_before_any_breaker_admission(
    auth_client, company, ai_settings, monkeypatch
):
    from app.ai import registry

    store = InMemoryHealthStore()
    monkeypatch.setattr("app.services.analysis.health_store", store)
    settings = ai_settings(
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="gemini,cloudflare",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)

    version_id, jd_id = _setup(auth_client, company)
    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_privacy_denied"
    assert store.snapshot() == {}
