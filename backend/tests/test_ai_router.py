"""Provider selection: the privacy gate decides, and nothing else is a fallback."""

from __future__ import annotations

import json
from dataclasses import fields

import httpx
import pytest
from sqlalchemy import func, select

from app.ai import registry
from app.ai.base import (
    AnalysisRequest,
    ProviderCircuitOpen,
    ProviderNoEligibleCandidate,
    ProviderPrivacyDenied,
    ProviderQuotaExhausted,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.cloudflare import CloudflareProvider
from app.ai.health import BreakerPolicy, InMemoryHealthStore
from app.ai.models import RESUME_DATA_CLASS, ModelSpec
from app.ai.quota import InMemoryQuotaStore, QuotaObservation
from app.ai.router import (
    Candidate,
    admit_candidate,
    build_decision,
    rank_candidates,
    route_and_run,
    select_provider,
)
from app.db.models import AnalysisResult
from app.db.session import session_scope
from tests.test_ai_integration import _setup, _success, _use_provider

MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def test_cloudflare_is_selected_when_configured_and_approved(ai_settings):
    provider = select_provider(ai_settings())
    assert isinstance(provider, CloudflareProvider)
    assert (provider.name, provider.model, provider.scope) == (
        "cloudflare",
        MODEL,
        "account",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cloudflare_api_token": None},
        {"cloudflare_account_id": ""},
        {"cloudflare_api_token": None, "cloudflare_account_id": None},
    ],
)
def test_missing_credentials_select_nothing(ai_settings, overrides):
    assert select_provider(ai_settings(**overrides)) is None


def test_unapproved_provider_raises_privacy_denial(ai_settings):
    with pytest.raises(ProviderPrivacyDenied):
        select_provider(ai_settings(ai_approved_providers=""))


def test_denied_selection_makes_no_http_call(ai_settings, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("an HTTP client was created before the privacy gate approved a model")

    monkeypatch.setattr("app.ai.cloudflare.httpx.Client", fail)
    with pytest.raises(ProviderPrivacyDenied):
        select_provider(ai_settings(ai_approved_providers=""))


def test_unregistered_model_selects_nothing(ai_settings):
    settings = ai_settings(cloudflare_model="@cf/meta/not-registered")
    assert select_provider(settings) is None


def test_gemini_is_never_a_fallback_even_when_configured(ai_settings):
    settings = ai_settings(
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="gemini,cloudflare",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
    )
    with pytest.raises(ProviderPrivacyDenied):
        select_provider(settings)


def test_registry_reads_settings_and_returns_the_selected_adapter(ai_settings, monkeypatch):
    monkeypatch.setattr(registry, "get_settings", lambda: ai_settings())
    assert isinstance(registry.get_provider(), CloudflareProvider)


def test_registry_raises_privacy_denial_when_only_gemini_is_configured(
    ai_settings, monkeypatch
):
    settings = ai_settings(
        ai_provider_order="gemini",
        ai_approved_providers="gemini",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    with pytest.raises(ProviderPrivacyDenied):
        registry.get_provider()

# --------------------------------------------------------------------- M4 routing


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _request(resume: str = "resume text", jd: str = "job description") -> AnalysisRequest:
    return AnalysisRequest(resume_text=resume, jd_text=jd, jd_title="Engineer")


def _spec(**overrides) -> ModelSpec:
    values = {
        "provider": "cloudflare",
        "model_id": MODEL,
        "free_tier": True,
        "json_output": True,
        "context_tokens": 24_000,
        "scope": "account",
        "retention": "zero",
        "trains_on_content": False,
        "approved_data_classes": frozenset({RESUME_DATA_CLASS}),
        "privacy_verified_on": "2026-11-22",
    }
    values.update(overrides)
    return ModelSpec(**values)


def _reasons(decision) -> set[str]:
    return {skip.reason for skip in decision.skips}


def _candidate(provider="cloudflare", model=MODEL, priority=0, health="healthy", quota="unknown"):
    return Candidate(provider, model, priority, _spec(provider=provider, model_id=model), health, quota)


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


def _fail(store: InMemoryHealthStore, settings, times: int = 3) -> None:
    policy = BreakerPolicy.from_settings(settings)
    for _ in range(times):
        store.record_failure("cloudflare", MODEL, ProviderUnavailable("503"), 10.0, policy=policy)


# ------------------------------------------------------------- candidate eligibility


def test_approved_cloudflare_candidate_is_eligible(ai_settings):
    decision = build_decision(ai_settings())

    assert decision.selected is not None
    assert (decision.selected.provider, decision.selected.model) == ("cloudflare", MODEL)
    assert decision.selected.priority == 0
    assert decision.selected.privacy_approved is True
    assert decision.skips == ()


@pytest.mark.parametrize("provider", ["gemini", "groq", "openrouter", "openai"])
def test_unapproved_providers_are_denied(ai_settings, monkeypatch, provider):
    monkeypatch.setattr("app.ai.router.configured_model", lambda _p, _s: "some-model")
    settings = ai_settings(ai_provider_order=provider, ai_approved_providers="cloudflare")

    decision = build_decision(settings)

    assert decision.selected is None
    assert all(candidate.provider != provider for candidate in decision.candidates)
    assert _reasons(decision)


def test_unknown_privacy_evidence_denies(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(privacy_verified_on=None))

    decision = build_decision(ai_settings())

    assert decision.selected is None
    assert "privacy_unverified" in _reasons(decision)


def test_disallowed_data_class_denies(ai_settings, monkeypatch):
    monkeypatch.setattr(
        "app.ai.router.get_model", lambda _p, _m: _spec(approved_data_classes=frozenset())
    )

    decision = build_decision(ai_settings())

    assert decision.selected is None
    assert "data_class_not_approved" in _reasons(decision)


def test_training_policy_violation_denies(ai_settings, monkeypatch):
    monkeypatch.setattr(
        "app.ai.router.get_model", lambda _p, _m: _spec(trains_on_content=True)
    )

    decision = build_decision(ai_settings(ai_allow_training_providers=False))

    assert decision.selected is None
    assert "training_not_allowed" in _reasons(decision)


def test_retention_violation_denies(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(retention="unknown"))

    decision = build_decision(ai_settings())

    assert decision.selected is None
    assert "retention_unknown" in _reasons(decision)


def test_free_only_excludes_paid_candidate(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(free_tier=False))

    decision = build_decision(ai_settings(ai_free_only=True))

    assert decision.selected is None
    assert "not_free" in _reasons(decision)


def test_unsupported_capability_excludes(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(json_output=False))

    decision = build_decision(ai_settings())

    assert decision.selected is None
    assert "no_json" in _reasons(decision)


def test_insufficient_context_excludes(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(context_tokens=4_000))

    decision = build_decision(ai_settings())

    assert decision.selected is None
    assert "context_insufficient" in _reasons(decision)


def test_large_request_exceeds_context_before_any_call(ai_settings):
    request = _request(resume="x" * 100_000, jd="y" * 100_000)

    decision = build_decision(ai_settings(), request=request)

    assert decision.selected is None
    assert "context_insufficient" in _reasons(decision)


# ------------------------------------------------------------- operational filtering


def test_disabled_provider_is_excluded(ai_settings):
    health = InMemoryHealthStore()
    health.disable("cloudflare", None, "manual")

    decision = build_decision(ai_settings(), health=health)

    assert decision.selected is None
    assert "disabled" in _reasons(decision)


def test_open_breaker_is_excluded(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    settings = ai_settings()
    _fail(health, settings)

    decision = build_decision(settings, health=health)

    assert decision.selected is None
    assert "circuit_open" in _reasons(decision)


def test_half_open_ranking_does_not_consume_the_probe(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    settings = ai_settings()
    _fail(health, settings)
    clock.advance(120.0)

    decision = build_decision(settings, health=health)

    assert decision.selected is not None
    assert decision.selected.health_state == "half_open"
    assert health.get("cloudflare").half_open_in_flight is False
    health.admit("cloudflare", MODEL, BreakerPolicy.from_settings(settings))
    assert health.get("cloudflare").half_open_in_flight is True


def test_confirmed_quota_exhaustion_is_excluded(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(exhausted=True, exhausted_until=clock.now + 3_600),
    )

    decision = build_decision(ai_settings(), quota=quota)

    assert decision.selected is None
    assert "quota_exhausted" in _reasons(decision)


def test_unknown_quota_is_allowed(ai_settings):
    decision = build_decision(ai_settings(), quota=InMemoryQuotaStore())

    assert decision.selected is not None
    assert decision.selected.quota_state == "unknown"


def test_degraded_health_remains_routable(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    settings = ai_settings()
    _fail(health, settings, times=1)

    decision = build_decision(settings, health=health)

    assert decision.selected is not None
    assert decision.selected.health_state == "degraded"


def test_temporary_rate_limit_remains_routable(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(retry_after_seconds=5, source="retry_after"),
    )

    decision = build_decision(ai_settings(), quota=quota)

    assert decision.selected is not None
    assert decision.selected.quota_state == "rate_limited"


def test_disabled_quota_policy_does_not_exclude(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(exhausted=True, exhausted_until=clock.now + 3_600),
    )

    decision = build_decision(ai_settings(ai_quota_enabled=False), quota=quota)

    assert decision.selected is not None


def test_disabled_breaker_policy_does_not_exclude(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    settings = ai_settings(ai_breaker_enabled=False)
    _fail(health, settings)

    decision = build_decision(settings, health=health)

    assert decision.selected is not None


# ------------------------------------------------------------------------ ranking


def test_explicit_priority_wins():
    first = _candidate("alpha", "m1", priority=0)
    second = _candidate("beta", "m2", priority=1)

    assert rank_candidates([second, first])[0] is first


def test_equal_eligibility_uses_a_stable_tie_break():
    first = _candidate("zeta", "m", priority=0)
    second = _candidate("alpha", "m", priority=0)

    assert [c.provider for c in rank_candidates([first, second])] == ["alpha", "zeta"]


def test_ranking_has_no_invented_cost_or_latency_fields():
    assert {field.name for field in fields(Candidate)} == {
        "provider",
        "model",
        "priority",
        "spec",
        "health_state",
        "quota_state",
    }


def test_decision_is_deterministic(ai_settings):
    first = build_decision(ai_settings())
    second = build_decision(ai_settings())

    assert first == second


# ------------------------------------------------------- admission and execution


def test_quota_admission_runs_before_the_breaker_probe(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    quota = InMemoryQuotaStore(clock=clock)
    settings = ai_settings()
    _fail(health, settings)
    clock.advance(120.0)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(exhausted=True, exhausted_until=clock.now + 3_600),
    )
    candidate = _candidate(health="half_open", quota="exhausted")

    with pytest.raises(ProviderQuotaExhausted):
        admit_candidate(candidate, settings, health=health, quota=quota)

    assert health.get("cloudflare").half_open_in_flight is False


def test_breaker_rejection_makes_no_http_request(ai_settings):
    clock = FakeClock()
    health = InMemoryHealthStore(clock=clock)
    settings = ai_settings()
    _fail(health, settings)
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderCircuitOpen):
        route_and_run(
            provider,
            _request(),
            settings,
            health=health,
            quota=InMemoryQuotaStore(clock=clock),
            sleep=lambda _s: None,
            clock=clock,
        )

    assert provider.calls == 0


class _QuotaSeedingProvider(ScriptedProvider):
    def __init__(self, quota: InMemoryQuotaStore, clock: FakeClock) -> None:
        super().__init__()
        self._quota = quota
        self._clock = clock

    def analyze(self, request: AnalysisRequest) -> object:
        self.calls += 1
        self._quota.observe(
            "cloudflare",
            MODEL,
            "account",
            QuotaObservation(exhausted=True, exhausted_until=self._clock.now + 3_600),
        )
        raise ProviderTimeout("slow")


def test_every_retry_rechecks_quota_admission(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    health = InMemoryHealthStore(clock=clock)
    provider = _QuotaSeedingProvider(quota, clock)

    with pytest.raises(ProviderQuotaExhausted):
        route_and_run(
            provider,
            _request(),
            ai_settings(ai_max_attempts=2),
            health=health,
            quota=quota,
            sleep=lambda _s: None,
            clock=clock,
        )

    assert provider.calls == 1


def test_admission_is_not_duplicated(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    health = InMemoryHealthStore(clock=clock)
    counts = {"quota": 0, "health": 0}
    original_quota, original_health = quota.admit, health.admit

    def quota_admit(*args, **kwargs):
        counts["quota"] += 1
        return original_quota(*args, **kwargs)

    def health_admit(*args, **kwargs):
        counts["health"] += 1
        return original_health(*args, **kwargs)

    quota.admit = quota_admit
    health.admit = health_admit
    provider = ScriptedProvider(object())

    route_and_run(
        provider,
        _request(),
        ai_settings(),
        health=health,
        quota=quota,
        sleep=lambda _s: None,
        clock=clock,
    )

    assert counts == {"quota": 1, "health": 1}


def test_retry_limit_is_unchanged(ai_settings):
    provider = ScriptedProvider(ProviderTimeout("slow"), ProviderTimeout("slow"))

    with pytest.raises(ProviderTimeout):
        route_and_run(
            provider,
            _request(),
            ai_settings(ai_max_attempts=2),
            sleep=lambda _s: None,
        )

    assert provider.calls == 2


def test_retries_reuse_the_same_provider(ai_settings):
    output = object()
    provider = ScriptedProvider(ProviderTimeout("slow"), output)

    result = route_and_run(
        provider,
        _request(),
        ai_settings(ai_max_attempts=2),
        sleep=lambda _s: None,
    )

    assert result is output
    assert provider.calls == 2


def test_no_eligible_candidate_raises_a_typed_error(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(json_output=False))
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderUnsupportedCapability):
        route_and_run(provider, _request(), ai_settings(), sleep=lambda _s: None)

    assert provider.calls == 0


def test_unregistered_configured_model_is_a_typed_failure(ai_settings):
    settings = ai_settings(cloudflare_model="@cf/meta/not-registered")
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderNoEligibleCandidate):
        route_and_run(provider, _request(), settings, sleep=lambda _s: None)

    assert provider.calls == 0


def test_quota_exhaustion_is_a_typed_failure_without_http(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(exhausted=True, exhausted_until=clock.now + 3_600),
    )
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderQuotaExhausted):
        route_and_run(
            provider,
            _request(),
            ai_settings(),
            quota=quota,
            sleep=lambda _s: None,
            clock=clock,
        )

    assert provider.calls == 0


def test_route_selection_log_carries_no_content(ai_settings, caplog):
    caplog.set_level("INFO", logger="careeros.ai")
    canary = "RESUME_CANARY_ROUTE"
    provider = ScriptedProvider(object())

    route_and_run(
        provider,
        _request(resume=canary),
        ai_settings(),
        sleep=lambda _s: None,
    )

    logged = "\n".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert "cloudflare" in logged
    assert MODEL in logged
    assert canary not in logged


# ------------------------------------------------------------------ M5 observability


def test_every_skip_emits_one_debug_record(ai_settings, monkeypatch, caplog):
    caplog.set_level("DEBUG", logger="careeros.ai")
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(privacy_verified_on=None))

    decision = build_decision(ai_settings())

    records = [r for r in caplog.records if r.getMessage() == "route candidate skipped"]
    assert len(records) == len(decision.skips) == 1
    assert records[0].levelname == "DEBUG"
    assert (records[0].provider, records[0].model, records[0].reason) == (
        "cloudflare",
        MODEL,
        "privacy_unverified",
    )


def test_skip_records_stay_below_info(ai_settings, monkeypatch, caplog):
    caplog.set_level("INFO", logger="careeros.ai")
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(privacy_verified_on=None))

    build_decision(ai_settings())

    assert not [r for r in caplog.records if r.getMessage() == "route candidate skipped"]


def test_each_attempt_emits_exactly_one_record(ai_settings, caplog):
    caplog.set_level("INFO", logger="careeros.ai")
    provider = ScriptedProvider(ProviderUnavailable("503"), object())

    route_and_run(
        provider,
        _request(),
        ai_settings(ai_max_attempts=2),
        sleep=lambda _s: None,
    )

    attempts = [r for r in caplog.records if r.getMessage() == "provider attempt"]
    assert len(attempts) == provider.calls == 2
    first, second = attempts
    assert (first.provider, first.model, first.attempt) == ("cloudflare", MODEL, 1)
    assert (first.status, first.code, first.failure_class) == (
        "failed",
        "provider_unavailable",
        "transient",
    )
    assert first.latency_ms >= 0
    assert first.delay_seconds >= 0
    assert (second.attempt, second.status) == (2, "success")
    assert not hasattr(second, "code")


def test_attempt_records_never_carry_request_or_error_content(ai_settings, caplog):
    caplog.set_level("INFO", logger="careeros.ai")
    canary = "PROVIDER_BODY_CANARY_9d2f"
    provider = ScriptedProvider(ProviderUnavailable(canary))

    with pytest.raises(ProviderUnavailable):
        route_and_run(
            provider,
            _request(resume=canary),
            ai_settings(ai_max_attempts=1),
            sleep=lambda _s: None,
        )

    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "provider attempt" in logged
    assert canary not in logged


# --------------------------------------------------------------- privacy and fallback


def test_privacy_denial_happens_before_execution(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(privacy_verified_on=None))
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderPrivacyDenied):
        route_and_run(provider, _request(), ai_settings(), sleep=lambda _s: None)

    assert provider.calls == 0


def test_typed_errors_do_not_echo_resume_content(ai_settings, monkeypatch):
    monkeypatch.setattr("app.ai.router.get_model", lambda _p, _m: _spec(privacy_verified_on=None))
    canary = "RESUME_CANARY_SAFE_ERROR"

    with pytest.raises(ProviderPrivacyDenied) as exc:
        route_and_run(
            ScriptedProvider(object()),
            _request(resume=canary),
            ai_settings(),
            sleep=lambda _s: None,
        )

    assert canary not in str(exc.value)


def test_fallback_setting_does_not_add_candidates(ai_settings):
    settings = ai_settings(
        ai_allow_cross_provider_fallback=True,
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="cloudflare",
        gemini_api_key="test-gemini-token",
    )

    decision = build_decision(settings)

    assert [candidate.provider for candidate in decision.candidates] == ["cloudflare"]


def test_a_failure_does_not_invoke_another_provider(ai_settings):
    settings = ai_settings(
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="cloudflare",
        ai_max_attempts=1,
    )
    provider = ScriptedProvider(ProviderTimeout("slow"))

    with pytest.raises(ProviderTimeout):
        route_and_run(provider, _request(), settings, sleep=lambda _s: None)

    assert provider.calls == 1


def test_routing_disabled_reproduces_m3_admission(ai_settings):
    clock = FakeClock()
    quota = InMemoryQuotaStore(clock=clock)
    quota.observe(
        "cloudflare",
        MODEL,
        "account",
        QuotaObservation(exhausted=True, exhausted_until=clock.now + 3_600),
    )
    provider = ScriptedProvider(object())

    with pytest.raises(ProviderQuotaExhausted):
        route_and_run(
            provider,
            _request(),
            ai_settings(ai_routing_enabled=False),
            quota=quota,
            sleep=lambda _s: None,
            clock=clock,
        )

    assert provider.calls == 0


# ------------------------------------------------------------- job accounting


def test_job_success_under_routing_creates_one_result(
    auth_client, company, ai_settings, monkeypatch
):
    monkeypatch.setattr(
        "app.services.analysis.get_settings", lambda: ai_settings(ai_routing_enabled=True)
    )
    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, _success)

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    body = auth_client.get(f"/api/v1/analyses/{job_id}").json()

    assert body["status"] == "succeeded"
    assert body["attempts"] == 1
    assert body["provider"] == "cloudflare"
    assert len(calls) == 1
    with session_scope() as db:
        count = db.scalar(
            select(func.count()).select_from(AnalysisResult).where(AnalysisResult.job_id == job_id)
        )
    assert count == 1


def test_failed_job_logs_one_terminal_record_without_provider_content(
    auth_client, company, ai_settings, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="careeros.ai")
    canary = "PROVIDER_BODY_CANARY_5c1d"
    monkeypatch.setattr(
        "app.services.analysis.get_settings", lambda: ai_settings(ai_routing_enabled=True)
    )
    version_id, jd_id = _setup(auth_client, company)
    _use_provider(
        monkeypatch,
        ai_settings,
        lambda _request: httpx.Response(401, json={"errors": [{"message": canary}]}),
    )

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()

    assert body["status"] == "failed"
    assert body["error_code"] == "provider_auth_failed"
    terminal = [r for r in caplog.records if r.getMessage() == "analysis failed"]
    assert len(terminal) == 1
    assert terminal[0].code == "provider_auth_failed"
    assert canary not in response.text
    assert canary not in json.dumps(body)
    assert canary not in caplog.text
