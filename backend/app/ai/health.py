"""Provider health manager and circuit breaker (B3 M2-A / M2-B).

M2-A records what already happened and derives a state. M2-B adds one breaker per provider:
three consecutive transient failures open it, admission is rejected while it is open, and a
single half-open probe is allowed once the cooldown expires. The breaker is about availability
only; auth/permission use ``disabled``, and rate limits, quota, invalid output and blocked
content never trip it.

Storage is process-local and guarded by one ``RLock``. A single lock is enough for a personal
deployment; per-key locks can be added when contention matters. No database, Redis or new
dependency is involved.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from app.ai.base import (
    ProviderAuthFailed,
    ProviderCircuitOpen,
    ProviderError,
    ProviderInvalidOutput,
    ProviderPermissionDenied,
    ProviderTimeout,
    ProviderUnavailable,
)

HealthState = Literal["healthy", "degraded", "open", "half_open", "disabled"]
FailureClass = Literal["transient", "auth", "permission", "quality"]

TRANSIENT: FailureClass = "transient"
AUTH: FailureClass = "auth"
PERMISSION: FailureClass = "permission"
QUALITY: FailureClass = "quality"

RECENT_OUTCOME_LIMIT = 20
EWMA_ALPHA = 0.3


@dataclass(frozen=True)
class BreakerPolicy:
    """Breaker thresholds. Built from settings per call so a config change needs no restart."""

    enabled: bool = True
    failure_threshold: int = 3
    cooldown_seconds: float = 120.0
    max_cooldown_seconds: float = 900.0
    backoff_multiplier: float = 2.0

    @classmethod
    def from_settings(cls, settings: object) -> BreakerPolicy:
        return cls(
            enabled=getattr(settings, "ai_breaker_enabled", True),
            failure_threshold=getattr(settings, "ai_breaker_failures", 3),
            cooldown_seconds=getattr(settings, "ai_breaker_cooldown_seconds", 120.0),
            max_cooldown_seconds=getattr(settings, "ai_breaker_cooldown_max_seconds", 900.0),
            backoff_multiplier=getattr(settings, "ai_breaker_backoff_multiplier", 2.0),
        )


@dataclass
class HealthRecord:
    """One observation bucket: provider-level when ``model`` is ``None``, else model-level."""

    provider: str
    model: str | None = None
    successes: int = 0
    failures: int = 0
    quality_failures: int = 0
    consecutive_failures: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_failure_class: FailureClass | None = None
    latency_ms_ewma: float | None = None
    latency_samples: int = 0
    recent_outcomes: tuple[str, ...] = field(default_factory=tuple)
    # Breaker fields. Only the provider-level record is used for admission; model-level
    # records keep counters and latency so the two views stay useful.
    opened_at: float | None = None
    cooldown_seconds: float = 0.0
    half_open_in_flight: bool = False
    disabled_reason: str | None = None

    @property
    def state(self) -> HealthState:
        """Read-only derivation. First match wins; ``disabled`` outranks the breaker."""
        if self.disabled_reason is not None:
            return "disabled"
        if self.half_open_in_flight:
            return "half_open"
        if self.opened_at is not None:
            return "open"
        if self.consecutive_failures:
            return "degraded"
        return "healthy"


class HealthStore(Protocol):
    def get(self, provider: str, model: str | None = None) -> HealthRecord: ...

    def routing_status(
        self, provider: str, model: str | None, policy: BreakerPolicy
    ) -> tuple[bool, HealthState, str | None]: ...

    def admit(self, provider: str, model: str | None, policy: BreakerPolicy) -> None: ...

    def abandon(self, provider: str, model: str | None = None) -> None: ...

    def record_success(self, provider: str, model: str | None, latency_ms: float) -> None: ...

    def record_failure(
        self,
        provider: str,
        model: str | None,
        error: ProviderError,
        latency_ms: float,
        *,
        policy: BreakerPolicy | None = None,
    ) -> None: ...

    def disable(self, provider: str, model: str | None, reason: str) -> None: ...

    def recover_credentials(self, provider: str, model: str | None = None) -> None: ...

    def snapshot(self) -> dict[tuple[str, str | None], HealthRecord]: ...

    def reset(self) -> None: ...


def classify_failure(error: ProviderError) -> FailureClass | None:
    """Only operational failures touch health; quota, content and client errors do not."""
    if isinstance(error, ProviderAuthFailed):
        return AUTH
    if isinstance(error, ProviderPermissionDenied):
        return PERMISSION
    if isinstance(error, ProviderInvalidOutput):
        return QUALITY
    if isinstance(error, ProviderTimeout | ProviderUnavailable):
        return TRANSIENT
    return None


class InMemoryHealthStore:
    """Thread-safe, process-local health store."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._records: dict[tuple[str, str | None], HealthRecord] = {}

    def get(self, provider: str, model: str | None = None) -> HealthRecord:
        with self._lock:
            record = self._records.get((provider, model))
            return _copy(record) if record is not None else HealthRecord(provider, model)

    def routing_status(
        self, provider: str, model: str | None, policy: BreakerPolicy
    ) -> tuple[bool, HealthState, str | None]:
        """Read-only routing view. Never consumes a half-open probe.

        ``(routable, state, skip_reason)``. An open breaker whose cooldown has elapsed is
        routable as ``half_open``; the atomic probe is claimed later by ``admit()``.
        """
        if not policy.enabled:
            return True, self.get(provider, model).state, None
        now = self._clock()
        with self._lock:
            record = self._records.get((provider, None))
            if record is None:
                return True, "healthy", None
            if record.disabled_reason is not None:
                return False, "disabled", "disabled"
            if record.opened_at is None:
                return True, record.state, None
            if record.half_open_in_flight:
                return False, "half_open", "circuit_half_open"
            if now < record.opened_at + record.cooldown_seconds:
                return False, "open", "circuit_open"
            return True, "half_open", None

    def admit(self, provider: str, model: str | None, policy: BreakerPolicy) -> None:
        """Allow one call or raise. Atomic, so only one half-open probe can pass."""
        if not policy.enabled:
            return
        now = self._clock()
        with self._lock:
            record = self._record(provider, None)
            if record.disabled_reason is not None:
                raise ProviderCircuitOpen(f"{provider} is disabled ({record.disabled_reason})")
            if record.opened_at is None:
                return
            if record.half_open_in_flight:
                raise ProviderCircuitOpen(f"{provider} circuit is half-open")
            if now < record.opened_at + record.cooldown_seconds:
                raise ProviderCircuitOpen(f"{provider} circuit is open")
            record.half_open_in_flight = True

    def abandon(self, provider: str, model: str | None = None) -> None:
        """Release a half-open slot after an unexpected exception; stay open until cooldown."""
        with self._lock:
            record = self._records.get((provider, None))
            if record is not None:
                record.half_open_in_flight = False

    def record_success(self, provider: str, model: str | None, latency_ms: float) -> None:
        now = self._clock()
        with self._lock:
            # Availability is observed at both levels.
            for target in _targets(provider, model):
                record = self._record(provider, target)
                record.successes += 1
                record.consecutive_failures = 0
                record.last_success_at = now
                record.recent_outcomes = _append(record.recent_outcomes, "success")
                _apply_latency(record, latency_ms)
                if target is None:
                    # A success closes the breaker and clears a half-open slot. It never
                    # clears ``disabled_reason``; credential recovery is explicit.
                    record.opened_at = None
                    record.cooldown_seconds = 0.0
                    record.half_open_in_flight = False

    def record_failure(
        self,
        provider: str,
        model: str | None,
        error: ProviderError,
        latency_ms: float,
        *,
        policy: BreakerPolicy | None = None,
    ) -> None:
        failure_class = classify_failure(error)
        if failure_class is None:
            return
        now = self._clock()
        with self._lock:
            # Quality is a model observation; availability failures affect both levels.
            quality_only = failure_class == QUALITY and model is not None
            targets = (model,) if quality_only else _targets(provider, model)
            for target in targets:
                record = self._record(provider, target)
                record.last_failure_at = now
                record.last_failure_class = failure_class
                record.recent_outcomes = _append(record.recent_outcomes, f"{failure_class}_failure")
                _apply_latency(record, latency_ms)
                if failure_class == TRANSIENT:
                    record.failures += 1
                    record.consecutive_failures += 1
                elif failure_class in {AUTH, PERMISSION}:
                    record.failures += 1
                    record.disabled_reason = failure_class
                else:  # QUALITY
                    record.quality_failures += 1
            provider_record = self._records.get((provider, None))
            if provider_record is not None:
                _advance_breaker(provider_record, failure_class, policy, now)

    def disable(self, provider: str, model: str | None, reason: str) -> None:
        """Administrative disable. ``reason`` is separate from auth/permission failures."""
        with self._lock:
            self._record(provider, None).disabled_reason = reason
            if model is not None:
                self._record(provider, model).disabled_reason = reason
                return
            for (name, _), record in self._records.items():
                if name == provider:
                    record.disabled_reason = reason

    def recover_credentials(self, provider: str, model: str | None = None) -> None:
        """Explicit recovery after a credential/plan fix. Manual disable is untouched."""
        with self._lock:
            for (name, target), record in self._records.items():
                if name != provider or record.disabled_reason not in {AUTH, PERMISSION}:
                    continue
                if model is not None and target not in {None, model}:
                    continue
                record.disabled_reason = None

    def snapshot(self) -> dict[tuple[str, str | None], HealthRecord]:
        with self._lock:
            return {key: _copy(record) for key, record in self._records.items()}

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    def _record(self, provider: str, model: str | None) -> HealthRecord:
        key = (provider, model)
        record = self._records.get(key)
        if record is None:
            record = HealthRecord(provider, model)
            self._records[key] = record
        return record


def _targets(provider: str, model: str | None) -> tuple[str | None, ...]:
    return (model, None) if model is not None else (None,)


def _copy(record: HealthRecord) -> HealthRecord:
    return replace(record)


def _append(outcomes: tuple[str, ...], outcome: str) -> tuple[str, ...]:
    return (*outcomes, outcome)[-RECENT_OUTCOME_LIMIT:]


def _apply_latency(record: HealthRecord, latency_ms: float) -> None:
    sample = max(0.0, float(latency_ms))
    if record.latency_ms_ewma is None:
        record.latency_ms_ewma = sample
    else:
        record.latency_ms_ewma = EWMA_ALPHA * sample + (1 - EWMA_ALPHA) * record.latency_ms_ewma
    record.latency_samples += 1


def _advance_breaker(
    record: HealthRecord,
    failure_class: FailureClass,
    policy: BreakerPolicy | None,
    now: float,
) -> None:
    """Transitions run on the provider-level record only; the lock is held by the caller."""
    if policy is None or not policy.enabled:
        return
    if failure_class == TRANSIENT:
        if record.half_open_in_flight:
            record.half_open_in_flight = False
            record.cooldown_seconds = min(
                max(record.cooldown_seconds, policy.cooldown_seconds) * policy.backoff_multiplier,
                policy.max_cooldown_seconds,
            )
            record.opened_at = now
        elif record.opened_at is None and record.consecutive_failures >= policy.failure_threshold:
            record.opened_at = now
            record.cooldown_seconds = policy.cooldown_seconds
        return
    # A provider that answered is reachable; a non-transient failure is not an outage.
    if record.half_open_in_flight:
        record.half_open_in_flight = False
        record.opened_at = None
        record.cooldown_seconds = 0.0
        record.consecutive_failures = 0


# Process-local singleton used by ``analysis.run()``. Tests inject their own store.
health_store = InMemoryHealthStore()
