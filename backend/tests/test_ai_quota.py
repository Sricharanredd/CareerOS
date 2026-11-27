"""M3: quota store, Cloudflare evidence parsing and admission integration.

All tests are offline: fake clocks, scripted providers, synthetic headers and a mocked
Cloudflare transport. No real quota is consumed and no credential is used.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from app.ai import registry
from app.ai.base import (
    AnalysisRequest,
    ProviderCircuitOpen,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.cloudflare import CloudflareProvider
from app.ai.health import BreakerPolicy, InMemoryHealthStore
from app.ai.quota import (
    ACCOUNT_SCOPE,
    MODEL_SCOPE,
    QUOTA_EXHAUSTED_MESSAGE,
    InMemoryQuotaStore,
    QuotaObservation,
    QuotaPolicy,
    next_utc_midnight,
    parse_cloudflare_quota_headers,
    quota_store,
)
from app.ai.retry import analyze_with_retry, retry_delay_seconds
from tests.test_ai_integration import MODEL, VALID_OUTPUT, _setup, _use_provider


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _store() -> tuple[InMemoryQuotaStore, FakeClock]:
    clock = FakeClock()
    return InMemoryQuotaStore(clock=clock), clock


def _policy(**overrides) -> QuotaPolicy:
    return QuotaPolicy(**overrides)


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
        "ai_quota_enabled": True,
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


def _exhaust(store: InMemoryQuotaStore, until: float | None = None) -> None:
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, exhausted_until=until, source="error_3036"),
    )


def _exhaust_generic(store: InMemoryQuotaStore, until: float | None) -> None:
    """Exhaustion without the protected 3036 evidence (e.g. a conservative/manual signal)."""
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, exhausted_until=until, source="conservative"),
    )


# --------------------------------------------------------------------------- store and state


def test_unknown_quota_is_none():
    store, _ = _store()
    bucket = store.get("cloudflare", MODEL)

    assert bucket.state == "unknown"
    assert bucket.remaining is None
    assert bucket.limit is None
    assert bucket.resets_at is None
    assert bucket.exhausted_until is None
    assert bucket.source == "unknown"


def test_known_available_capacity_is_stored():
    store, clock = _store()
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(
            remaining=42,
            limit=100,
            unit="requests",
            resets_at=clock.now + 60,
            source="documented_header",
        ),
    )

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "available"
    assert bucket.remaining == 42
    assert bucket.limit == 100
    assert bucket.unit == "requests"
    assert bucket.resets_at == clock.now + 60
    assert bucket.observed_at == clock.now


def test_known_exhaustion_is_stored_and_blocks():
    store, clock = _store()
    _exhaust(store, until=clock.now + 60)

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "exhausted"
    assert bucket.exhausted_until == clock.now + 60

    with pytest.raises(ProviderQuotaExhausted):
        store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())


def test_account_state_is_shared_across_models():
    store, clock = _store()
    _exhaust(store, until=clock.now + 60)

    for model in ("@cf/meta/llama-3.2-1b-instruct", MODEL):
        assert store.get("cloudflare", model, ACCOUNT_SCOPE).state == "exhausted"
        with pytest.raises(ProviderQuotaExhausted):
            store.admit("cloudflare", model, ACCOUNT_SCOPE, _policy())


def test_model_state_is_separate_only_in_model_scope():
    store, _ = _store()
    other = "@cf/meta/llama-3.2-1b-instruct"
    store.observe(
        "cloudflare",
        MODEL,
        MODEL_SCOPE,
        QuotaObservation(remaining=0),
    )

    assert store.get("cloudflare", MODEL, MODEL_SCOPE).state == "exhausted"
    assert store.get("cloudflare", other, MODEL_SCOPE).state == "unknown"
    # The account bucket is a different bucket and must not be inferred from a model.
    assert store.get("cloudflare", other, ACCOUNT_SCOPE).state == "unknown"
    store.admit("cloudflare", other, MODEL_SCOPE, _policy())


def test_snapshots_cannot_mutate_internal_state():
    store, _ = _store()
    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, QuotaObservation(remaining=3))

    snapshot = store.snapshot()
    bucket = next(iter(snapshot.values()))
    bucket.remaining = 999
    bucket.exhausted_unknown_reset = True

    current = store.get("cloudflare", MODEL)
    assert current.remaining == 3
    assert current.exhausted_unknown_reset is False


def test_concurrent_updates_are_thread_safe():
    store, _ = _store()
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        for _ in range(50):
            store.observe(
                "cloudflare",
                MODEL,
                ACCOUNT_SCOPE,
                QuotaObservation(retry_after_seconds=1.0),
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        for future in futures:
            future.result()

    bucket = store.get("cloudflare", MODEL)
    assert bucket.updates == 400
    assert bucket.rate_limited_until is not None


def test_no_account_identifiers_or_private_data_are_stored():
    store, _ = _store()
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(remaining=1, source="error_3036"),
    )

    text = repr(store.snapshot())
    assert "test-token" not in text
    assert "test-account" not in text
    assert "RESUME_CANARY" not in text


def test_invalid_reset_timestamp_remains_unknown():
    store, _ = _store()
    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, QuotaObservation(resets_at=float("nan")))
    assert store.get("cloudflare", MODEL).resets_at is None

    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, QuotaObservation(resets_at=-1.0))
    assert store.get("cloudflare", MODEL).resets_at is None


def test_negative_and_non_finite_values_are_ignored():
    store, _ = _store()
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(remaining=-5, limit=-1, retry_after_seconds=float("inf")),
    )

    bucket = store.get("cloudflare", MODEL)
    assert bucket.remaining is None
    assert bucket.limit is None
    assert bucket.rate_limited_until is None
    assert bucket.state == "unknown"


# --------------------------------------------------------------------------- header parser


def test_documented_3036_is_parsed_as_exhaustion():
    now = 1_700_000_000.0
    observation = parse_cloudflare_quota_headers(
        {}, now, status_code=429, error_codes=(3036,)
    )

    assert observation.exhausted is True
    assert observation.exhausted_until == next_utc_midnight(now)
    assert observation.exhausted_until > now
    assert observation.exhausted_until - now <= 86_400
    assert observation.source == "error_3036"


def test_missing_headers_remain_unknown():
    observation = parse_cloudflare_quota_headers({}, 1_700_000_000.0, status_code=429)

    assert observation.exhausted is False
    assert observation.exhausted_until is None
    assert observation.retry_after_seconds is None
    assert observation.source == "unknown"


def test_malformed_retry_after_remains_unknown():
    for value in ("soon", "", "1.2.3", "nan", "inf"):
        observation = parse_cloudflare_quota_headers(
            {"retry-after": value}, 1_700_000_000.0, status_code=429
        )
        assert observation.retry_after_seconds is None


def test_negative_retry_after_is_rejected():
    observation = parse_cloudflare_quota_headers(
        {"retry-after": "-30"}, 1_700_000_000.0, status_code=429
    )
    assert observation.retry_after_seconds is None


def test_date_form_retry_after_remains_unknown():
    # Only delta-seconds is supported; a date must not be guessed.
    observation = parse_cloudflare_quota_headers(
        {"retry-after": "Wed, 25 Nov 2026 07:28:00 GMT"}, 1_700_000_000.0, status_code=429
    )
    assert observation.retry_after_seconds is None


def test_undocumented_headers_are_ignored():
    observation = parse_cloudflare_quota_headers(
        {
            "ratelimit-remaining": "0",
            "ratelimit-limit": "300",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "0",
        },
        1_700_000_000.0,
        status_code=429,
    )

    assert observation.remaining is None
    assert observation.limit is None
    assert observation.resets_at is None
    assert observation.exhausted is False
    assert observation.source == "unknown"


def test_capacity_3040_is_a_rate_limit_not_exhaustion():
    observation = parse_cloudflare_quota_headers(
        {"retry-after": "5"},
        1_700_000_000.0,
        status_code=429,
        error_codes=(3040,),
    )

    assert observation.exhausted is False
    assert observation.exhausted_until is None
    assert observation.retry_after_seconds == 5.0
    assert observation.source == "error_3040"


def test_non_429_response_yields_no_evidence():
    observation = parse_cloudflare_quota_headers(
        {"retry-after": "5"}, 1_700_000_000.0, status_code=200, error_codes=(3036,)
    )
    assert observation == QuotaObservation()


def test_retry_after_feeds_the_retry_policy():
    observation = parse_cloudflare_quota_headers(
        {"Retry-After": "4"}, 1_700_000_000.0, status_code=429
    )
    error = ProviderRateLimited("slow", retry_after_seconds=observation.retry_after_seconds)

    assert retry_delay_seconds(error, attempt=1, settings=_settings()) == 4.0
    capped = _settings(ai_retry_max_delay_seconds=3)
    assert retry_delay_seconds(error, attempt=1, settings=capped) is None


def test_contradictory_exhaustion_wins():
    store, _ = _store()
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, remaining=5, retry_after_seconds=1.0),
    )

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "exhausted"
    assert bucket.remaining is None
    assert bucket.exhausted_unknown_reset is True
    assert bucket.rate_limited_until is None


# --------------------------------------------------------------------------- rate limit vs quota


def test_temporary_rate_limit_is_not_exhaustion():
    store, clock = _store()
    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, QuotaObservation(retry_after_seconds=30))

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "rate_limited"
    assert bucket.exhausted_until is None
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())  # retry owns rate-limit timing

    clock.advance(31)
    assert store.get("cloudflare", MODEL).state == "unknown"


def test_expired_reset_permits_re_evaluation():
    store, clock = _store()
    _exhaust(store, until=clock.now + 60)

    clock.advance(61)
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "unknown"
    assert bucket.remaining is None  # a reset never invents a capacity number


def test_unknown_reset_time_stays_blocked():
    store, clock = _store()
    _exhaust(store, until=None)

    clock.advance(10 * 365 * 86_400)
    with pytest.raises(ProviderQuotaExhausted):
        store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())


def test_exhaustion_with_an_already_elapsed_reset_does_not_block():
    store, clock = _store()
    _exhaust(store, until=clock.now - 1)

    assert store.get("cloudflare", MODEL).state == "unknown"
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())


def test_available_observation_recovers_generic_exhaustion():
    store, clock = _store()
    _exhaust_generic(store, until=clock.now + 60)
    with pytest.raises(ProviderQuotaExhausted):
        store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())

    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, QuotaObservation(remaining=5))
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())
    assert store.get("cloudflare", MODEL).state == "available"


def test_success_recovers_generic_exhaustion_without_inventing_capacity():
    store, clock = _store()
    _exhaust_generic(store, until=clock.now + 60)

    store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "unknown"
    assert bucket.remaining is None


# ------------------------------------------------------- 3036 exhaustion hardening (M3 patch)


def _observe_3036(store: InMemoryQuotaStore, now: float) -> None:
    store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        parse_cloudflare_quota_headers({}, now, status_code=429, error_codes=(3036,)),
    )


def test_success_cannot_clear_active_3036_exhaustion():
    store, clock = _store()
    _observe_3036(store, clock.now)
    before = store.get("cloudflare", MODEL)
    assert before.exhausted_until == next_utc_midnight(clock.now)

    store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)

    after = store.get("cloudflare", MODEL)
    assert after.state == "exhausted"
    assert after.exhausted_until == before.exhausted_until
    assert after.remaining is None
    assert after.limit is None
    assert after.unit is None


def test_success_after_reset_returns_to_unknown():
    store, clock = _store()
    _observe_3036(store, clock.now)
    reset = next_utc_midnight(clock.now)

    clock.now = reset
    store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "unknown"
    assert bucket.exhausted_until is None
    assert bucket.remaining is None
    assert bucket.limit is None
    assert bucket.unit is None
    store.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())


@pytest.mark.parametrize(
    "observation",
    [
        QuotaObservation(retry_after_seconds=5, source="retry_after"),
        QuotaObservation(retry_after_seconds=5, source="error_3040"),
        QuotaObservation(remaining=99, limit=100, source="documented_header"),
        QuotaObservation(),
    ],
)
def test_ambiguous_observations_cannot_clear_active_3036(observation):
    store, clock = _store()
    _observe_3036(store, clock.now)
    until = store.get("cloudflare", MODEL).exhausted_until

    store.observe("cloudflare", MODEL, ACCOUNT_SCOPE, observation)

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "exhausted"
    assert bucket.exhausted_until == until
    assert bucket.remaining is None


@pytest.mark.parametrize("success_last", [True, False])
def test_observation_order_cannot_clear_active_3036(success_last):
    store, clock = _store()

    if success_last:
        _observe_3036(store, clock.now)
        store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)
    else:
        store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)
        _observe_3036(store, clock.now)

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "exhausted"
    assert bucket.exhausted_until == next_utc_midnight(clock.now)
    assert bucket.remaining is None


def test_concurrent_success_and_3036_keep_exhaustion():
    store, clock = _store()
    until = next_utc_midnight(clock.now)
    barrier = threading.Barrier(2)

    def success() -> None:
        barrier.wait()
        store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)

    def exhausted() -> None:
        barrier.wait()
        _observe_3036(store, clock.now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(success), pool.submit(exhausted)]
        for future in futures:
            future.result()

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "exhausted"
    assert bucket.exhausted_until == until
    assert bucket.remaining is None


def test_admission_stays_blocked_after_a_success():
    quota, clock = _store()
    _observe_3036(quota, clock.now)
    quota.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)

    provider = ScriptedProvider(object())
    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            provider,
            _request(),
            _settings(),
            quota=quota,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )

    assert provider.calls == 0


def test_success_on_unknown_bucket_records_availability_evidence():
    store, _ = _store()
    store.observe_success("cloudflare", MODEL, ACCOUNT_SCOPE)

    bucket = store.get("cloudflare", MODEL)
    assert bucket.state == "unknown"
    assert bucket.source == "success"
    assert bucket.remaining is None


# --------------------------------------------------------------------------- admission and retry


def test_confirmed_exhaustion_blocks_admission():
    quota, clock = _store()
    _exhaust(quota, until=clock.now + 60)

    with pytest.raises(ProviderQuotaExhausted):
        quota.admit("cloudflare", MODEL, ACCOUNT_SCOPE, _policy())


def test_quota_admission_runs_before_http():
    quota, clock = _store()
    _exhaust(quota, until=clock.now + 60)
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            provider, _request(), _settings(), quota=quota, clock=FakeClock(), sleep=lambda _s: None
        )

    assert provider.calls == 0  # no HTTP request, no fallback


def test_quota_rejection_is_not_a_health_failure():
    quota, clock = _store()
    health = InMemoryHealthStore()
    _exhaust(quota, until=clock.now + 60)

    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            ScriptedProvider(object()),
            _request(),
            _settings(),
            quota=quota,
            health=health,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )

    assert health.snapshot() == {}


def test_quota_rejection_adds_no_latency_sample():
    quota, clock = _store()
    health = InMemoryHealthStore()
    _exhaust(quota, until=clock.now + 60)

    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            ScriptedProvider(object()),
            _request(),
            _settings(),
            quota=quota,
            health=health,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )

    record = health.get("cloudflare", MODEL)
    assert record.latency_samples == 0
    assert record.latency_ms_ewma is None


def test_every_retry_rechecks_quota():
    quota, _ = _store()
    provider = ScriptedProvider(ProviderTimeout("slow"))
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        _exhaust(quota, until=quota.now() + 60)

    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            provider,
            _request(),
            _settings(ai_max_attempts=2),
            quota=quota,
            clock=FakeClock(),
            sleep=sleep,
        )

    assert provider.calls == 1  # the retry was rejected before a second HTTP request
    assert sleeps == [1.0]


def test_exhausted_quota_is_not_retried():
    quota, clock = _store()
    provider = ScriptedProvider(*(ProviderQuotaExhausted("quota") for _ in range(3)))

    with pytest.raises(ProviderQuotaExhausted):
        analyze_with_retry(
            provider,
            _request(),
            _settings(ai_max_attempts=3),
            quota=quota,
            clock=clock,
            sleep=lambda _s: None,
        )

    assert provider.calls == 1


def test_circuit_breaker_still_opens_with_quota_enabled():
    quota, _ = _store()
    health = InMemoryHealthStore()
    provider = ScriptedProvider(*(ProviderUnavailable("503") for _ in range(5)))

    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            provider,
            _request(),
            _settings(ai_max_attempts=5, ai_breaker_failures=3),
            quota=quota,
            health=health,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )

    assert provider.calls == 3
    assert health.get("cloudflare").state == "open"


def test_breaker_admission_is_still_enforced_with_quota():
    quota, _ = _store()
    health = InMemoryHealthStore()
    policy = BreakerPolicy()
    for _ in range(3):
        health.record_failure("cloudflare", MODEL, ProviderUnavailable("503"), 1.0, policy=policy)

    provider = ScriptedProvider(object())
    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            provider,
            _request(),
            _settings(),
            quota=quota,
            health=health,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )

    assert provider.calls == 0


def test_quota_disabled_reproduces_m2b_behaviour():
    quota, clock = _store()
    _exhaust(quota, until=clock.now + 60)
    provider = ScriptedProvider(object())

    output = analyze_with_retry(
        provider,
        _request(),
        _settings(ai_quota_enabled=False),
        quota=quota,
        clock=FakeClock(),
        sleep=lambda _s: None,
    )

    assert output is not None
    assert provider.calls == 1


def test_quota_disabled_keeps_breaker_behaviour():
    quota, _ = _store()
    health = InMemoryHealthStore()
    policy = BreakerPolicy()
    for _ in range(3):
        health.record_failure("cloudflare", MODEL, ProviderUnavailable("503"), 1.0, policy=policy)

    with pytest.raises(ProviderCircuitOpen):
        analyze_with_retry(
            ScriptedProvider(object()),
            _request(),
            _settings(ai_quota_enabled=False),
            quota=quota,
            health=health,
            clock=FakeClock(),
            sleep=lambda _s: None,
        )


# --------------------------------------------------------------------------- Cloudflare evidence


def _adapter(ai_settings, handler) -> CloudflareProvider:
    return CloudflareProvider(ai_settings(), transport=httpx.MockTransport(handler))


def _success_response() -> httpx.Response:
    return httpx.Response(
        200, json={"success": True, "result": {"response": json.dumps(VALID_OUTPUT)}}
    )


def test_adapter_records_3036_as_account_exhaustion(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"success": False, "errors": [{"code": 3036, "message": "Account limited"}]},
            headers={"retry-after": "3"},
        )

    with pytest.raises(ProviderQuotaExhausted):
        _adapter(ai_settings, handler).analyze(_request())

    bucket = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE)
    assert bucket.state == "exhausted"
    assert bucket.source == "error_3036"
    assert bucket.exhausted_until is not None


def test_adapter_capacity_429_is_rate_limited_not_exhausted(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"success": False, "errors": [{"code": 3040, "message": "Out of capacity"}]},
            headers={"retry-after": "5"},
        )

    with pytest.raises(ProviderRateLimited) as error:
        _adapter(ai_settings, handler).analyze(_request())

    assert error.value.retry_after_seconds == 5.0
    bucket = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE)
    assert bucket.state == "rate_limited"
    assert bucket.exhausted_until is None


def test_adapter_success_on_unknown_bucket_records_evidence(ai_settings):
    _adapter(ai_settings, lambda _request: _success_response()).analyze(_request())

    bucket = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE)
    assert bucket.state == "unknown"
    assert bucket.source == "success"
    assert bucket.remaining is None


def test_adapter_200_does_not_clear_confirmed_3036(ai_settings):
    quota_store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        parse_cloudflare_quota_headers(
            {}, quota_store.now(), status_code=429, error_codes=(3036,)
        ),
    )
    until = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE).exhausted_until

    _adapter(ai_settings, lambda _request: _success_response()).analyze(_request())

    bucket = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE)
    assert bucket.state == "exhausted"
    assert bucket.exhausted_until == until
    assert bucket.remaining is None


def test_adapter_malformed_quota_headers_do_not_break_the_request(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"success": False}, headers={"retry-after": "soon"})

    with pytest.raises(ProviderRateLimited):
        _adapter(ai_settings, handler).analyze(_request())

    bucket = quota_store.get("cloudflare", MODEL, ACCOUNT_SCOPE)
    assert bucket.state == "unknown"
    assert bucket.rate_limited_until is None


def test_adapter_3036_message_does_not_echo_provider_text(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "success": False,
                "errors": [{"code": 3036, "message": "secret-account-identifier"}],
            },
        )

    with pytest.raises(ProviderQuotaExhausted) as error:
        _adapter(ai_settings, handler).analyze(_request())

    assert error.value.message == QUOTA_EXHAUSTED_MESSAGE
    assert "secret-account-identifier" not in error.value.message


# --------------------------------------------------------------------------- job accounting


def _job_body(auth_client, response) -> dict:
    assert response.status_code == 201, response.text
    return auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()


def test_job_fails_with_quota_exhausted_without_http(
    auth_client, company, ai_settings, monkeypatch
):
    quota_store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, exhausted_until=time.time() + 3_600),
    )
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(ai_max_attempts=2, ai_quota_enabled=True),
    )

    def forbidden(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP request is expected when quota is exhausted")

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, forbidden)

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_quota_exhausted"
    assert body["attempts"] == 1
    assert body.get("result") is None
    assert calls == []


def test_job_succeeds_with_quota_disabled_despite_exhaustion(
    auth_client, company, ai_settings, monkeypatch
):
    quota_store.observe(
        "cloudflare",
        MODEL,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, exhausted_until=time.time() + 3_600),
    )
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(ai_max_attempts=2, ai_quota_enabled=False),
    )

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, lambda _request: _success_response())

    body = _job_body(
        auth_client,
        auth_client.post("/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}),
    )

    assert body["status"] == "succeeded"
    assert body["attempts"] == 1
    assert body["result"]["score"] == 81
    assert len(calls) == 1


def test_privacy_denial_precedes_quota_admission(
    auth_client, company, ai_settings, monkeypatch
):
    quota_store.observe(
        "gemini",
        None,
        ACCOUNT_SCOPE,
        QuotaObservation(exhausted=True, exhausted_until=time.time() + 3_600),
    )
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
    assert quota_store.get("gemini", None, ACCOUNT_SCOPE).state == "exhausted"
