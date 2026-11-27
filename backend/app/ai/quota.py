"""Provider quota lifecycle manager (B3 M3).

Tracks documented quota evidence separately from health and the circuit breaker. Unknown is
always ``None``: the manager never guesses capacity, a reset time or an account limit, and it
never treats unknown as zero. Only a documented exhaustion signal blocks admission.

Cloudflare Workers AI evidence used (official docs, read 2026-11-25):

- ``https://developers.cloudflare.com/workers-ai/platform/errors/`` — error ``3036`` is returned
  with HTTP 429 when the daily free allocation is used up; error ``3040`` with HTTP 429 means
  temporary capacity, not exhaustion.
- ``https://developers.cloudflare.com/workers-ai/platform/pricing/`` — the free allocation is
  account-scoped (10,000 neurons per day) and "All limits reset daily at 00:00 UTC".
- ``Retry-After`` is a standard HTTP header and is already honoured by the existing retry policy.

No remaining-capacity or account-limit header is documented for Workers AI, so ``remaining``,
``limit`` and ``unit`` stay unknown for Cloudflare. Generic ``Ratelimit`` / ``X-RateLimit-*``
headers are explicitly ignored: they are not established as the Workers AI account quota.

Storage is process-local and guarded by one ``RLock``. No lock is held during a provider call
or a retry sleep. A restart resets quota to unknown, which is optimistic but safe: the failure
mode is one wasted attempt, never an unbounded retry loop or a paid spend.

A confirmed ``3036`` exhaustion is protected until its documented reset. An HTTP 200 from a
request that was already in flight is not proof that the daily allocation reset, so success and
ambiguous observations cannot clear an active ``3036`` window.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from app.ai.base import ProviderQuotaExhausted

QuotaState = Literal["unknown", "available", "rate_limited", "exhausted"]
QuotaScope = Literal["account", "model"]

ACCOUNT_SCOPE: QuotaScope = "account"
MODEL_SCOPE: QuotaScope = "model"
UNKNOWN_SOURCE = "unknown"

# Documented Workers AI error codes (see the module docstring).
CLOUDFLARE_EXHAUSTED_CODES = frozenset({3036})
CLOUDFLARE_CAPACITY_CODES = frozenset({3040})

# Exhaustion with this source is protected until its documented reset; no other observation
# (including HTTP 200) may clear it earlier.
PROTECTED_EXHAUSTION = "error_3036"

DAILY_RESET_SOURCE = "daily_utc_reset"
SECONDS_PER_DAY = 86_400

QUOTA_EXHAUSTED_MESSAGE = "The AI provider's free quota is exhausted. Try again after it resets."


@dataclass(frozen=True)
class QuotaObservation:
    """One piece of evidence. Every field is optional; absent evidence stays ``None``."""

    remaining: float | None = None
    limit: float | None = None
    unit: str | None = None
    resets_at: float | None = None
    retry_after_seconds: float | None = None
    exhausted: bool = False
    exhausted_until: float | None = None
    source: str = UNKNOWN_SOURCE


@dataclass
class QuotaBucket:
    """Quota state for one account or model bucket."""

    provider: str
    scope: QuotaScope
    scope_key: str
    remaining: float | None = None
    limit: float | None = None
    unit: str | None = None
    resets_at: float | None = None
    exhausted_until: float | None = None
    exhausted_unknown_reset: bool = False
    # Which evidence established exhaustion. ``error_3036`` is protected until its reset.
    exhausted_source: str | None = None
    rate_limited_until: float | None = None
    observed_at: float | None = None
    source: str = UNKNOWN_SOURCE
    updates: int = 0

    @property
    def state(self) -> QuotaState:
        """Known exhaustion outranks a rate limit; unknown is never zero."""
        if self.exhausted_unknown_reset or self.exhausted_until is not None:
            return "exhausted"
        if self.remaining is not None and self.remaining <= 0:
            return "exhausted"
        if self.rate_limited_until is not None:
            return "rate_limited"
        if self.remaining is not None:
            return "available"
        return "unknown"


@dataclass(frozen=True)
class QuotaPolicy:
    """Admission policy, built from settings per call so a toggle needs no restart."""

    enabled: bool = True

    @classmethod
    def from_settings(cls, settings: object) -> QuotaPolicy:
        return cls(enabled=getattr(settings, "ai_quota_enabled", True))


class QuotaStore(Protocol):
    def now(self) -> float: ...

    def get(
        self, provider: str, model: str | None = None, scope: QuotaScope = ACCOUNT_SCOPE
    ) -> QuotaBucket: ...

    def observe(
        self,
        provider: str,
        model: str | None,
        scope: QuotaScope,
        observation: QuotaObservation,
    ) -> None: ...

    def observe_success(self, provider: str, model: str | None, scope: QuotaScope) -> None: ...

    def admit(
        self,
        provider: str,
        model: str | None,
        scope: QuotaScope,
        policy: QuotaPolicy,
    ) -> None: ...

    def snapshot(self) -> dict[tuple[str, str], QuotaBucket]: ...

    def reset(self) -> None: ...


class InMemoryQuotaStore:
    """Thread-safe, process-local quota store. Timestamps are wall-clock seconds."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._buckets: dict[tuple[str, str], QuotaBucket] = {}

    def now(self) -> float:
        return self._clock()

    def get(
        self, provider: str, model: str | None = None, scope: QuotaScope = ACCOUNT_SCOPE
    ) -> QuotaBucket:
        with self._lock:
            bucket = self._buckets.get(_key(provider, model, scope))
            if bucket is None:
                return QuotaBucket(provider, _scope(scope), _scope_key(model, scope))
            _expire(bucket, self._clock())
            return replace(bucket)

    def observe(
        self,
        provider: str,
        model: str | None,
        scope: QuotaScope,
        observation: QuotaObservation,
    ) -> None:
        now = self._clock()
        with self._lock:
            bucket = self._record(provider, model, scope)
            _expire(bucket, now)
            bucket.updates += 1
            if bucket.exhausted_source == PROTECTED_EXHAUSTION:
                # A documented daily exhaustion (3036) is authoritative until its reset.
                # Rate limits, capacity errors, malformed evidence and even an explicit
                # available-capacity observation cannot clear or shorten that window.
                return
            bucket.observed_at = now
            bucket.source = observation.source
            if _valid(observation.limit):
                bucket.limit = observation.limit
            if observation.unit:
                bucket.unit = observation.unit
            if _valid(observation.resets_at):
                bucket.resets_at = observation.resets_at
            if _valid(observation.retry_after_seconds):
                bucket.rate_limited_until = now + observation.retry_after_seconds

            if observation.exhausted:
                # Exhaustion outranks a contradictory Retry-After or remaining count, and the
                # old remaining count is stale: after the reset the amount is unknown, not > 0.
                bucket.rate_limited_until = None
                bucket.remaining = None
                if _valid(observation.exhausted_until):
                    # A reset that has already passed means the window is over, not active.
                    active = observation.exhausted_until > now
                    bucket.exhausted_until = observation.exhausted_until if active else None
                    bucket.exhausted_unknown_reset = False
                    bucket.exhausted_source = observation.source if active else None
                else:
                    # No usable reset time: stay blocked until a new observation recovers it.
                    bucket.exhausted_until = None
                    bucket.exhausted_unknown_reset = True
                    bucket.exhausted_source = observation.source
                return

            if observation.remaining is not None and _valid(observation.remaining):
                bucket.remaining = observation.remaining
            if bucket.remaining is not None and bucket.remaining > 0:
                bucket.exhausted_until = None
                bucket.exhausted_unknown_reset = False
                bucket.exhausted_source = None

    def observe_success(self, provider: str, model: str | None, scope: QuotaScope) -> None:
        """A served request proves quota was available; it does not reveal how much is left.

        A 200 from a request that was already in flight is not proof that the account's daily
        allocation reset, so it never clears an active ``3036`` exhaustion window.
        """
        now = self._clock()
        with self._lock:
            bucket = self._record(provider, model, scope)
            _expire(bucket, now)
            bucket.updates += 1
            if bucket.exhausted_source == PROTECTED_EXHAUSTION:
                return
            bucket.observed_at = now
            bucket.source = "success"
            bucket.exhausted_until = None
            bucket.exhausted_unknown_reset = False
            bucket.exhausted_source = None
            bucket.rate_limited_until = None
            bucket.remaining = None

    def admit(
        self,
        provider: str,
        model: str | None,
        scope: QuotaScope,
        policy: QuotaPolicy,
    ) -> None:
        """Reject only known exhaustion. Rate-limit timing stays owned by ``app.ai.retry``."""
        if not policy.enabled:
            return
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(_key(provider, model, scope))
            if bucket is None:
                return
            _expire(bucket, now)
            if bucket.exhausted_unknown_reset:
                raise ProviderQuotaExhausted(QUOTA_EXHAUSTED_MESSAGE)
            if bucket.exhausted_until is not None:
                raise ProviderQuotaExhausted(
                    QUOTA_EXHAUSTED_MESSAGE,
                    retry_after_seconds=max(0.0, bucket.exhausted_until - now),
                )
            if bucket.remaining is not None and bucket.remaining <= 0:
                raise ProviderQuotaExhausted(QUOTA_EXHAUSTED_MESSAGE)

    def snapshot(self) -> dict[tuple[str, str], QuotaBucket]:
        now = self._clock()
        with self._lock:
            result: dict[tuple[str, str], QuotaBucket] = {}
            for key, bucket in self._buckets.items():
                _expire(bucket, now)
                result[key] = replace(bucket)
            return result

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _record(self, provider: str, model: str | None, scope: QuotaScope) -> QuotaBucket:
        key = _key(provider, model, scope)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = QuotaBucket(provider, _scope(scope), _scope_key(model, scope))
            self._buckets[key] = bucket
        return bucket


def parse_cloudflare_quota_headers(
    headers: Mapping[str, str],
    now: float,
    *,
    status_code: int = 429,
    error_codes: Collection[int] = (),
) -> QuotaObservation:
    """Parse only documented Cloudflare Workers AI evidence.

    Error ``3036`` is confirmed exhaustion; the documented daily 00:00 UTC reset is used as the
    only reset time. Error ``3040`` and any other 429 are temporary rate limits, carrying
    ``Retry-After`` when it is a valid non-negative number. A non-429 response yields nothing.
    """
    if status_code != 429:
        return QuotaObservation()

    lowered = {str(key).lower(): value for key, value in headers.items()}
    retry_after = _non_negative_float(lowered.get("retry-after"))

    if CLOUDFLARE_EXHAUSTED_CODES.intersection(error_codes):
        return QuotaObservation(
            exhausted=True,
            exhausted_until=next_utc_midnight(now),
            source=PROTECTED_EXHAUSTION,
        )
    if CLOUDFLARE_CAPACITY_CODES.intersection(error_codes):
        return QuotaObservation(retry_after_seconds=retry_after, source="error_3040")
    if retry_after is not None:
        return QuotaObservation(retry_after_seconds=retry_after, source="retry_after")
    return QuotaObservation()


def next_utc_midnight(now: float) -> float:
    """The next 00:00 UTC boundary, the documented daily reset for Workers AI limits."""
    return float((int(now // SECONDS_PER_DAY) + 1) * SECONDS_PER_DAY)


def _non_negative_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _valid(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value)) and value >= 0


def _expire(bucket: QuotaBucket, now: float) -> None:
    """Lazy expiry. Never invents capacity; only stops blocking on a window that has passed."""
    if bucket.exhausted_until is not None and now >= bucket.exhausted_until:
        bucket.exhausted_until = None
        bucket.exhausted_source = None
        bucket.source = "reset_elapsed"
    if bucket.rate_limited_until is not None and now >= bucket.rate_limited_until:
        bucket.rate_limited_until = None
    if bucket.resets_at is not None and now >= bucket.resets_at:
        bucket.resets_at = None
        if bucket.remaining is not None and bucket.remaining <= 0:
            bucket.remaining = None


def _key(provider: str, model: str | None, scope: QuotaScope) -> tuple[str, str]:
    return (provider, _scope_key(model, scope))


def _scope_key(model: str | None, scope: QuotaScope) -> str:
    return ACCOUNT_SCOPE if scope == ACCOUNT_SCOPE else (model or "unknown")


def _scope(scope: QuotaScope) -> QuotaScope:
    return MODEL_SCOPE if scope == MODEL_SCOPE else ACCOUNT_SCOPE


# Process-local singleton used by the Cloudflare adapter and ``analysis.run()``.
quota_store = InMemoryQuotaStore()
