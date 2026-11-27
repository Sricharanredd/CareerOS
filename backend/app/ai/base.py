"""Provider protocol and the failure taxonomy services react to."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ai.output import AnalysisOutput


class ProviderError(Exception):
    code = "provider_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ProviderUnavailable(ProviderError):
    code = "provider_unavailable"


class ProviderNetworkError(ProviderUnavailable):
    """Transport failure before any provider response (DNS, connect, reset, read)."""

    code = "provider_network_error"


class ProviderTimeout(ProviderError):
    code = "provider_timeout"


class ProviderCircuitOpen(ProviderError):
    """The breaker rejected the call before any HTTP request was made."""

    code = "circuit_open"


class ProviderInvalidOutput(ProviderError):
    code = "invalid_output"


class ProviderJsonParseError(ProviderInvalidOutput):
    """The response body was not JSON at all."""

    code = "invalid_json"


class ProviderSchemaError(ProviderInvalidOutput):
    """The response parsed as JSON but did not match the expected shape."""

    code = "invalid_schema"


class ProviderInvalidModel(ProviderError):
    """The configured model id is not available from the provider."""

    code = "provider_invalid_model"


class ProviderUnsupportedCapability(ProviderError):
    """The model cannot satisfy a required capability (context, JSON, ...)."""

    code = "provider_unsupported_capability"


class ProviderRateLimited(ProviderError):
    """Quota exhausted. Costs nothing; never a reason to reach for a paid tier."""

    code = "provider_rate_limited"

    def __init__(
        self, message: str, *, retry_after_seconds: float | None = None, code: str | None = None
    ) -> None:
        super().__init__(message, code=code)
        self.retry_after_seconds = retry_after_seconds


class ProviderQuotaExhausted(ProviderRateLimited):
    """A documented daily/monthly allowance is exhausted. Reserved for a real signal."""

    code = "provider_quota_exhausted"


class ProviderAuthFailed(ProviderError):
    """Key rejected. Disables the provider for the process; not a health failure."""

    code = "provider_auth_failed"


class ProviderPermissionDenied(ProviderError):
    """Authenticated but not allowed to use this account/model. Not an auth failure."""

    code = "provider_permission_denied"


class ProviderEntitlementDenied(ProviderPermissionDenied):
    """A documented plan, terms or private-model restriction blocks this model."""

    code = "provider_entitlement_denied"


class ProviderBlocked(ProviderError):
    """Safety refusal. The same content will be refused everywhere, so never fall back."""

    code = "provider_blocked"


class ProviderPrivacyDenied(ProviderError):
    """Raised by the privacy gate, never by an adapter: no approved provider may receive this."""

    code = "provider_privacy_denied"


class ProviderNoEligibleCandidate(ProviderError):
    """The router found no candidate that passed every gate. No provider was contacted."""

    code = "ai_unavailable"


@dataclass(frozen=True)
class AnalysisRequest:
    resume_text: str
    jd_text: str
    jd_title: str
    company_name: str | None = None


class AnalysisProvider(Protocol):
    name: str
    model: str
    scope: str  # "model" = per-model quota bucket, "account" = shared across models

    def analyze(self, request: AnalysisRequest) -> AnalysisOutput: ...
