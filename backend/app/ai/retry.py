"""Central retry policy.

Adapters make one HTTP request per ``analyze()`` call. This module is the only place that
decides whether a typed failure is retried, how long to wait, and when the budget is spent.

``job.attempts`` is **not** changed here: ``analysis.run()`` still increments it once per
background run. Provider attempts are internal to one run and are not persisted (that would
need a schema change). See ``docs/STAGE2_B3_ARCHITECTURE.md`` §5 for the target model.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.ai.base import (
    AnalysisProvider,
    AnalysisRequest,
    ProviderAuthFailed,
    ProviderBlocked,
    ProviderError,
    ProviderInvalidModel,
    ProviderInvalidOutput,
    ProviderPermissionDenied,
    ProviderPrivacyDenied,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.health import BreakerPolicy, HealthStore, classify_failure
from app.ai.output import AnalysisOutput
from app.ai.quota import QuotaPolicy, QuotaStore
from app.core.config import Settings

logger = logging.getLogger("careeros.ai")

# Terminal classes: a second identical call cannot help, or is explicitly out of scope.
_NEVER_RETRY = (
    ProviderAuthFailed,
    ProviderPermissionDenied,
    ProviderBlocked,
    ProviderInvalidModel,
    ProviderInvalidOutput,
    ProviderUnsupportedCapability,
    ProviderPrivacyDenied,
)


def retry_delay_seconds(
    error: ProviderError, *, attempt: int, settings: Settings
) -> float | None:
    """Delay before the next attempt, or ``None`` when the error is terminal.

    ``attempt`` is 1-based and names the attempt that just failed.
    """
    if isinstance(error, ProviderQuotaExhausted):
        return None
    if isinstance(error, ProviderRateLimited):
        # No blind 429 loop: only a documented, bounded Retry-After is honoured.
        delay = error.retry_after_seconds
        if delay is None or delay < 0 or delay > settings.ai_retry_max_delay_seconds:
            return None
        return delay
    if isinstance(error, _NEVER_RETRY):
        return None
    if isinstance(error, ProviderTimeout | ProviderUnavailable):
        backoff = settings.ai_retry_base_delay_seconds * (2 ** (attempt - 1))
        return min(backoff, settings.ai_retry_max_delay_seconds)
    return None


def analyze_with_retry(
    provider: AnalysisProvider,
    request: AnalysisRequest,
    settings: Settings,
    *,
    sleep: Callable[[float], None] | None = None,
    health: HealthStore | None = None,
    quota: QuotaStore | None = None,
    clock: Callable[[], float] | None = None,
    admit: Callable[[], None] | None = None,
) -> AnalysisOutput:
    """Run one provider attempt, retrying only the classes the policy allows.

    The same provider instance is reused; this function never selects a different provider.
    Health is observational except for admission: the breaker can reject an attempt before any
    HTTP request. Quota admission runs first because it is read-only and must not consume the
    single half-open breaker probe. Retry sleep is outside the measured latency, and a retry
    re-checks both admissions, so it cannot bypass a newly exhausted quota or an open breaker.

    ``admit`` moves admission ownership to the caller (the router). When it is supplied, this
    function does not admit directly, so exactly one owner performs quota and breaker admission
    per attempt. The callable is still invoked immediately before every attempt.
    """
    sleeper = sleep or time.sleep
    now = clock or time.monotonic
    policy = BreakerPolicy.from_settings(settings)
    quota_policy = QuotaPolicy.from_settings(settings)
    scope = getattr(provider, "scope", "account")
    for attempt in range(1, settings.ai_max_attempts + 1):
        if admit is not None:
            admit()
        else:
            if quota is not None:
                quota.admit(provider.name, provider.model, scope, quota_policy)
            if health is not None:
                health.admit(provider.name, provider.model, policy)
        started = now()
        try:
            output = provider.analyze(request)
        except ProviderError as error:
            elapsed_ms = (now() - started) * 1000
            _record_failure(health, provider, error, elapsed_ms, policy)
            delay = retry_delay_seconds(error, attempt=attempt, settings=settings)
            _log_attempt(provider, attempt, elapsed_ms, error, delay)
            if delay is None or attempt >= settings.ai_max_attempts:
                raise
            sleeper(delay)
            continue
        except BaseException:
            # An unexpected exception must not leave a half-open probe slot stuck.
            _abandon(health, provider)
            raise
        elapsed_ms = (now() - started) * 1000
        _record_success(health, provider, elapsed_ms)
        _log_attempt(provider, attempt, elapsed_ms, None, None)
        return output
    raise AssertionError("unreachable")  # pragma: no cover


def _log_attempt(
    provider: AnalysisProvider,
    attempt: int,
    elapsed_ms: float,
    error: ProviderError | None,
    delay: float | None,
) -> None:
    """One structured record per attempt. Codes and classes only: never the error message."""
    extra: dict[str, object] = {
        "provider": provider.name,
        "model": provider.model,
        "attempt": attempt,
        "latency_ms": round(elapsed_ms, 1),
        "status": "success" if error is None else "failed",
    }
    if error is not None:
        extra["code"] = error.code
        failure_class = classify_failure(error)
        if failure_class is not None:
            extra["failure_class"] = failure_class
        if delay is not None:
            extra["delay_seconds"] = delay
        logger.warning("provider attempt", extra=extra)
    else:
        logger.info("provider attempt", extra=extra)


def _record_success(
    health: HealthStore | None, provider: AnalysisProvider, elapsed_ms: float
) -> None:
    """Health is a side observation; a recorder bug must never fail an analysis."""
    if health is None:
        return
    try:
        health.record_success(provider.name, provider.model, elapsed_ms)
    except Exception:  # pragma: no cover - defensive
        logger.exception("health recording failed", extra={"provider": provider.name})


def _record_failure(
    health: HealthStore | None,
    provider: AnalysisProvider,
    error: ProviderError,
    elapsed_ms: float,
    policy: BreakerPolicy,
) -> None:
    if health is None:
        return
    try:
        health.record_failure(provider.name, provider.model, error, elapsed_ms, policy=policy)
    except Exception:  # pragma: no cover - defensive
        logger.exception("health recording failed", extra={"provider": provider.name})


def _abandon(health: HealthStore | None, provider: AnalysisProvider) -> None:
    if health is None:
        return
    try:
        health.abandon(provider.name, provider.model)
    except Exception:  # pragma: no cover - defensive
        logger.exception("health probe release failed", extra={"provider": provider.name})
