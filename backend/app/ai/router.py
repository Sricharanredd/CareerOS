"""Provider routing: privacy first, then operational eligibility, then execution.

B2 selected exactly one provider: the first configured model in ``AI_PROVIDER_ORDER`` that
passed every privacy check. M4 keeps that gate and adds an explicit, explainable decision:

1. enumerate the configured provider chain,
2. apply the existing privacy/capability gate (``privacy.denial_reasons``) to each model,
3. apply read-only operational filters (disabled, breaker, quota exhaustion),
4. rank the survivors deterministically,
5. admit quota then breaker atomically immediately before each attempt.

Cross-provider fallback is **not** implemented. Only the top candidate is ever attempted; a
failure returns the existing typed error and no resume is sent anywhere else.

``select_provider()`` remains the submit-time compatibility wrapper over the privacy gate. It
never consults health or quota, so submit-time behaviour is unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.ai.base import (
    AnalysisProvider,
    AnalysisRequest,
    ProviderCircuitOpen,
    ProviderError,
    ProviderNoEligibleCandidate,
    ProviderPrivacyDenied,
    ProviderQuotaExhausted,
    ProviderUnsupportedCapability,
)
from app.ai.cloudflare import CHARS_PER_TOKEN, PROMPT_OVERHEAD_TOKENS
from app.ai.health import BreakerPolicy, HealthState, HealthStore
from app.ai.models import ModelSpec, get_model
from app.ai.output import AnalysisOutput
from app.ai.privacy import MIN_CONTEXT_TOKENS, approved_candidates, denial_reasons
from app.ai.providers import build_adapter, configured_model
from app.ai.quota import (
    QUOTA_EXHAUSTED_MESSAGE,
    QuotaPolicy,
    QuotaState,
    QuotaStore,
)
from app.ai.retry import analyze_with_retry
from app.core.config import Settings

logger = logging.getLogger("careeros.ai")

PRIVACY_DENIED_MESSAGE = "No configured AI provider is approved to process resume data."
NO_ELIGIBLE_MESSAGE = "No AI provider passed the routing checks. Try again later."

PRIVACY_REASONS = frozenset(
    {
        "not_approved",
        "data_class_not_approved",
        "privacy_unverified",
        "retention_unknown",
        "training_unknown",
        "training_not_allowed",
    }
)
CAPABILITY_REASONS = frozenset({"no_json", "context_unknown", "context_insufficient"})
BREAKER_REASONS = frozenset({"circuit_open", "circuit_half_open", "disabled"})

_HEALTH_RANK = {"healthy": 0, "degraded": 1, "half_open": 2, "open": 3, "disabled": 4}
_QUOTA_RANK = {"available": 0, "unknown": 0, "rate_limited": 1, "exhausted": 2}


@dataclass(frozen=True)
class Skip:
    """One reason a configured provider/model was not routable."""

    provider: str
    model: str | None
    reason: str


@dataclass(frozen=True)
class Candidate:
    """An eligible candidate. ``spec`` is the single source of registry facts."""

    provider: str
    model: str
    priority: int
    spec: ModelSpec
    health_state: HealthState
    quota_state: QuotaState

    @property
    def scope(self) -> str:
        return self.spec.scope

    @property
    def context_tokens(self) -> int | None:
        return self.spec.context_tokens

    @property
    def free_tier(self) -> bool:
        return self.spec.free_tier

    @property
    def privacy_approved(self) -> bool:
        return self.spec.privacy_approved


@dataclass(frozen=True)
class RouteDecision:
    """Ranked eligible candidates plus the reasons everything else was skipped."""

    candidates: tuple[Candidate, ...]
    skips: tuple[Skip, ...]

    @property
    def selected(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    def match(self, provider: str, model: str) -> Candidate | None:
        for candidate in self.candidates:
            if candidate.provider == provider and candidate.model == model:
                return candidate
        return None


def estimate_request_tokens(request: AnalysisRequest | None) -> int:
    """Same input budget rule the Cloudflare adapter uses, so routing cannot admit too much."""
    if request is None:
        return 0
    return (
        (len(request.resume_text) + len(request.jd_text)) // CHARS_PER_TOKEN
        + PROMPT_OVERHEAD_TOKENS
    )


def _skip(skips: list[Skip], provider: str, model: str | None, reason: str) -> None:
    """Record and log one skip. DEBUG keeps a long chain quiet at normal levels."""
    skips.append(Skip(provider, model, reason))
    logger.debug(
        "route candidate skipped",
        extra={"provider": provider, "model": model, "reason": reason},
    )


def build_decision(
    settings: Settings,
    *,
    request: AnalysisRequest | None = None,
    health: HealthStore | None = None,
    quota: QuotaStore | None = None,
    required_context_tokens: int | None = None,
) -> RouteDecision:
    """Evaluate every configured provider and return a deterministic, ranked decision.

    Privacy is checked before any operational state, and only read-only health/quota views are
    consulted. Ranking never claims a probe; admission happens later, atomically.
    """
    required = max(
        MIN_CONTEXT_TOKENS,
        required_context_tokens
        if required_context_tokens is not None
        else estimate_request_tokens(request),
    )
    breaker = BreakerPolicy.from_settings(settings)
    quota_policy = QuotaPolicy.from_settings(settings)
    candidates: list[Candidate] = []
    skips: list[Skip] = []

    for priority, provider in enumerate(settings.ai_provider_chain):
        model_id = configured_model(provider, settings)
        if not model_id:
            _skip(skips, provider, None, "unconfigured")
            continue
        spec = get_model(provider, model_id)
        if spec is None:
            _skip(skips, provider, model_id, "unregistered")
            continue

        reasons = denial_reasons(spec, settings, required_context_tokens=required)
        if reasons:
            for reason in reasons:
                _skip(skips, provider, model_id, reason)
            continue

        health_state: HealthState = "healthy"
        if health is not None:
            routable, health_state, reason = health.routing_status(provider, model_id, breaker)
            if not routable:
                _skip(skips, provider, model_id, reason or "unavailable")
                continue

        quota_state: QuotaState = "unknown"
        if quota is not None and quota_policy.enabled:
            quota_state = quota.get(provider, model_id, spec.scope).state
            if quota_state == "exhausted":
                _skip(skips, provider, model_id, "quota_exhausted")
                continue

        candidates.append(
            Candidate(provider, model_id, priority, spec, health_state, quota_state)
        )

    return RouteDecision(tuple(rank_candidates(candidates)), tuple(skips))


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Deterministic order: configured priority, health, quota, then a stable name tie-break."""
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.priority,
            _HEALTH_RANK.get(candidate.health_state, 3),
            _QUOTA_RANK.get(candidate.quota_state, 0),
            candidate.provider,
            candidate.model,
        ),
    )


def admit_candidate(
    candidate: Candidate,
    settings: Settings,
    *,
    health: HealthStore | None = None,
    quota: QuotaStore | None = None,
) -> None:
    """Quota then breaker, immediately before execution.

    Quota is read-only and must run first: a quota rejection must not consume the single
    half-open breaker probe.
    """
    if quota is not None:
        quota.admit(
            candidate.provider,
            candidate.model,
            candidate.spec.scope,
            QuotaPolicy.from_settings(settings),
        )
    if health is not None:
        health.admit(
            candidate.provider,
            candidate.model,
            BreakerPolicy.from_settings(settings),
        )


def route_and_run(
    provider: AnalysisProvider,
    request: AnalysisRequest,
    settings: Settings,
    *,
    sleep: Callable[[float], None] | None = None,
    health: HealthStore | None = None,
    quota: QuotaStore | None = None,
    clock: Callable[[], float] | None = None,
) -> AnalysisOutput:
    """Run the privacy-selected provider under the M4 routing policy.

    Routing disabled, or a provider outside the configured chain (an injected adapter in tests
    or a plugin), keeps the M3 path exactly: ``retry.py`` owns admission. Otherwise the router
    owns admission and rejects any provider that is not a current eligible candidate.
    """
    if not settings.ai_routing_enabled or provider.name not in settings.ai_provider_chain:
        return analyze_with_retry(
            provider,
            request,
            settings,
            sleep=sleep,
            health=health,
            quota=quota,
            clock=clock,
        )

    decision = build_decision(settings, request=request, health=health, quota=quota)
    candidate = decision.match(provider.name, provider.model)
    if candidate is None:
        raise no_eligible_error(decision)

    logger.info(
        "route selected",
        extra={
            "provider": candidate.provider,
            "model": candidate.model,
            "priority": candidate.priority,
            "health": candidate.health_state,
            "quota": candidate.quota_state,
        },
    )
    return analyze_with_retry(
        provider,
        request,
        settings,
        sleep=sleep,
        health=health,
        clock=clock,
        admit=lambda: admit_candidate(candidate, settings, health=health, quota=quota),
    )


def no_eligible_error(decision: RouteDecision) -> ProviderError:
    """Map the recorded skip reasons to the most specific existing typed error."""
    reasons = {skip.reason for skip in decision.skips}
    if reasons & PRIVACY_REASONS:
        return ProviderPrivacyDenied(PRIVACY_DENIED_MESSAGE)
    if "quota_exhausted" in reasons:
        return ProviderQuotaExhausted(QUOTA_EXHAUSTED_MESSAGE)
    if reasons & BREAKER_REASONS:
        return ProviderCircuitOpen(NO_ELIGIBLE_MESSAGE)
    if reasons & CAPABILITY_REASONS:
        return ProviderUnsupportedCapability(NO_ELIGIBLE_MESSAGE)
    return ProviderNoEligibleCandidate(NO_ELIGIBLE_MESSAGE)


def select_provider(settings: Settings) -> AnalysisProvider | None:
    for spec in approved_candidates(settings):
        adapter = build_adapter(spec.provider, settings)
        if adapter is not None:
            return adapter

    for provider in settings.ai_provider_chain:
        if build_adapter(provider, settings) is None:
            continue
        model_id = configured_model(provider, settings)
        spec = get_model(provider, model_id) if model_id else None
        if spec is not None and denial_reasons(spec, settings):
            raise ProviderPrivacyDenied(PRIVACY_DENIED_MESSAGE)
    return None
