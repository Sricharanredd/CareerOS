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
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.gemini import GeminiProvider
from app.ai.models import MODELS, RESUME_DATA_CLASS, get_model, models_for
from app.ai.providers import build_adapter


def test_only_the_verified_cloudflare_model_can_carry_resumes():
    assert [spec.model_id for spec in MODELS if spec.eligible_for_resume] == [
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    ]


def test_free_tier_alone_is_not_privacy_approval():
    gemini = get_model("gemini", "gemini-3.5-flash-lite")
    assert gemini is not None
    assert gemini.free_tier is True
    assert gemini.trains_on_content is True
    assert gemini.privacy_approved is False
    assert gemini.eligible_for_resume is False


def test_unknown_training_policy_never_carries_resume_data():
    for spec in models_for("groq"):
        assert spec.trains_on_content == "unknown"
        assert spec.privacy_approved is False
        assert RESUME_DATA_CLASS not in spec.approved_data_classes


def test_cloudflare_8b_stays_disabled_until_its_context_is_verified():
    spec = get_model("cloudflare", "@cf/meta/llama-3.1-8b-instruct")
    assert spec is not None
    assert spec.privacy_approved is True
    assert spec.context_tokens is None
    assert spec.eligible_for_resume is False


def test_every_model_row_records_when_its_capability_was_verified():
    assert all(spec.capability_verified_on for spec in MODELS)


def test_every_approved_model_records_when_its_privacy_was_verified():
    for spec in MODELS:
        if spec.privacy_approved:
            assert spec.privacy_verified_on is not None


def test_unknown_model_is_not_routable():
    assert get_model("cloudflare", "made-up") is None
    assert models_for("openai") == ()


def test_error_taxonomy_codes_and_retry_hint():
    limited = ProviderRateLimited("busy", retry_after_seconds=2.5)
    assert limited.code == "provider_rate_limited"
    assert limited.retry_after_seconds == 2.5
    assert ProviderRateLimited("busy").retry_after_seconds is None
    assert ProviderAuthFailed("no").code == "provider_auth_failed"
    assert ProviderBlocked("no").code == "provider_blocked"
    assert ProviderPrivacyDenied("no").code == "provider_privacy_denied"

    # 403 is split from auth: unknown 403 is permission, documented plan/terms is entitlement.
    assert ProviderPermissionDenied("no").code == "provider_permission_denied"
    assert ProviderEntitlementDenied("no").code == "provider_entitlement_denied"
    assert isinstance(ProviderEntitlementDenied("no"), ProviderPermissionDenied)
    assert not issubclass(ProviderPermissionDenied, ProviderAuthFailed)

    # Quota exhaustion is a rate-limit subtype so existing catches keep working.
    quota = ProviderQuotaExhausted("empty")
    assert quota.code == "provider_quota_exhausted"
    assert isinstance(quota, ProviderRateLimited)

    # Transient split: network keeps the unavailable parent, 5xx stays ProviderUnavailable.
    assert ProviderNetworkError("no").code == "provider_network_error"
    assert isinstance(ProviderNetworkError("no"), ProviderUnavailable)
    assert ProviderInvalidModel("no").code == "provider_invalid_model"
    assert ProviderUnsupportedCapability("no").code == "provider_unsupported_capability"

    # JSON parse and schema are both invalid output, but distinguishable.
    assert ProviderJsonParseError("no").code == "invalid_json"
    assert ProviderSchemaError("no").code == "invalid_schema"
    assert issubclass(ProviderJsonParseError, ProviderError)
    assert issubclass(ProviderSchemaError, ProviderError)

    assert all(
        issubclass(error, ProviderError)
        for error in (
            ProviderRateLimited,
            ProviderAuthFailed,
            ProviderBlocked,
            ProviderPrivacyDenied,
            ProviderPermissionDenied,
            ProviderEntitlementDenied,
            ProviderQuotaExhausted,
            ProviderNetworkError,
            ProviderInvalidModel,
            ProviderUnsupportedCapability,
            ProviderJsonParseError,
            ProviderSchemaError,
        )
    )


def test_adapter_builder_returns_gemini_only_when_configured():
    configured = SimpleNamespace(
        gemini_api_key="placeholder", gemini_model="gemini-test", ai_timeout_seconds=30
    )
    built = build_adapter("gemini", configured)
    assert built is not None
    assert built.name == "gemini"
    assert built.model == "gemini-test"
    assert built.scope == "model"

    unconfigured = SimpleNamespace(
        gemini_api_key="", gemini_model="gemini-test", ai_timeout_seconds=30
    )
    assert build_adapter("gemini", unconfigured) is None
    assert build_adapter("openai", configured) is None


def test_gemini_no_longer_repairs_internally(monkeypatch):
    settings = SimpleNamespace(
        gemini_api_key="placeholder", gemini_model="gemini-test", ai_timeout_seconds=30
    )
    provider = GeminiProvider(settings)
    temperatures: list[float] = []

    def fake_generate(prompt: str, *, temperature: float = 0.2) -> str:
        temperatures.append(temperature)
        return "not json"

    monkeypatch.setattr(provider, "_generate", fake_generate)
    with pytest.raises(ProviderJsonParseError):
        provider.analyze(AnalysisRequest(resume_text="r", jd_text="j", jd_title="t"))

    assert temperatures == [0.2]


def test_gemini_makes_one_http_request_on_429(monkeypatch):
    settings = SimpleNamespace(
        gemini_api_key="placeholder", gemini_model="gemini-test", ai_timeout_seconds=30
    )
    provider = GeminiProvider(settings)
    calls: list[str] = []

    def fake_post(url: str, payload: dict) -> httpx.Response:
        calls.append(url)
        return httpx.Response(429, json={})

    monkeypatch.setattr(provider, "_post", fake_post)
    with pytest.raises(ProviderUnavailable):
        provider.analyze(AnalysisRequest(resume_text="r", jd_text="j", jd_title="t"))

    assert len(calls) == 1
