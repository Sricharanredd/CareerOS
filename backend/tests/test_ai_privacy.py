"""Privacy gate: unknown information is denial, and an allowlist never overrides the registry."""

from __future__ import annotations

from dataclasses import replace

from app.ai.models import MODELS, RESUME_DATA_CLASS, get_model
from app.ai.privacy import MIN_CONTEXT_TOKENS, approved_candidates, denial_reasons

MODEL_70B = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
MODEL_8B = "@cf/meta/llama-3.1-8b-instruct"
GEMINI = "gemini-3.5-flash-lite"
GROQ = "openai/gpt-oss-120b"


def _spec(provider: str, model_id: str):
    found = get_model(provider, model_id)
    assert found is not None, f"{provider}/{model_id} should be registered"
    return found


def test_verified_cloudflare_model_passes_every_check(ai_settings):
    settings = ai_settings()
    assert denial_reasons(_spec("cloudflare", MODEL_70B), settings) == ()
    assert approved_candidates(settings) == (_spec("cloudflare", MODEL_70B),)


def test_unapproved_provider_is_denied(ai_settings):
    reasons = denial_reasons(_spec("cloudflare", MODEL_70B), ai_settings(ai_approved_providers=""))
    assert reasons == ("not_approved",)


def test_unregistered_model_is_denied(ai_settings):
    settings = ai_settings(cloudflare_model="@cf/meta/not-a-registered-model")
    assert get_model("cloudflare", settings.cloudflare_model) is None
    assert approved_candidates(settings) == ()


def test_unknown_training_policy_is_denied_even_when_training_is_allowed(ai_settings):
    settings = ai_settings(
        ai_provider_order="groq",
        ai_approved_providers="groq",
        ai_allow_training_providers=True,
    )
    assert "training_unknown" in denial_reasons(_spec("groq", GROQ), settings)
    assert approved_candidates(settings) == ()


def test_training_enabled_provider_is_denied_by_default(ai_settings):
    settings = ai_settings(
        ai_provider_order="gemini",
        ai_approved_providers="gemini",
        gemini_api_key="test-gemini-token",
    )
    reasons = denial_reasons(_spec("gemini", GEMINI), settings)
    assert "training_not_allowed" in reasons


def test_allowlist_alone_never_approves_a_model(ai_settings):
    """Gemini is free and on the allowlist, but its privacy metadata still says no."""
    settings = ai_settings(
        ai_provider_order="gemini",
        ai_approved_providers="gemini",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
    )
    spec = _spec("gemini", GEMINI)
    assert spec.free_tier is True
    reasons = denial_reasons(spec, settings)
    assert "data_class_not_approved" in reasons
    assert "privacy_unverified" in reasons
    assert approved_candidates(settings) == ()


def test_unknown_retention_is_denied(ai_settings):
    spec = replace(_spec("cloudflare", MODEL_70B), retention="unknown")
    assert "retention_unknown" in denial_reasons(spec, ai_settings())


def test_unverified_privacy_metadata_is_denied(ai_settings):
    spec = replace(_spec("cloudflare", MODEL_70B), privacy_verified_on=None)
    assert "privacy_unverified" in denial_reasons(spec, ai_settings())


def test_unknown_context_is_denied(ai_settings):
    """The 8B row is privacy-approved but stays disabled until its window is verified."""
    spec = _spec("cloudflare", MODEL_8B)
    assert spec.privacy_approved is True
    assert "context_unknown" in denial_reasons(spec, ai_settings())


def test_insufficient_context_is_denied(ai_settings):
    reasons = denial_reasons(
        _spec("cloudflare", MODEL_70B),
        ai_settings(),
        required_context_tokens=MIN_CONTEXT_TOKENS + 1_000_000,
    )
    assert reasons == ("context_insufficient",)


def test_paid_only_model_is_denied_in_free_only_mode(ai_settings):
    paid = replace(_spec("cloudflare", MODEL_70B), free_tier=False)
    assert "not_free" in denial_reasons(paid, ai_settings())
    assert "not_free" not in denial_reasons(paid, ai_settings(ai_free_only=False))


def test_model_without_json_mode_is_denied(ai_settings):
    spec = replace(_spec("cloudflare", MODEL_70B), json_output=False)
    assert "no_json" in denial_reasons(spec, ai_settings())


def test_gemini_never_becomes_a_candidate_even_when_first_in_the_chain(ai_settings):
    settings = ai_settings(
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="gemini,cloudflare",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
    )
    assert approved_candidates(settings) == (_spec("cloudflare", MODEL_70B),)


def test_every_registry_row_but_the_verified_cloudflare_model_is_denied(ai_settings):
    """Free tier and an allowlist entry are not enough; the registry has the final say."""
    allowed = set()
    for spec in MODELS:
        settings = ai_settings(
            ai_provider_order=spec.provider,
            ai_approved_providers=spec.provider,
            ai_allow_training_providers=True,
            gemini_api_key="test-gemini-token",
        )
        if not denial_reasons(spec, settings):
            allowed.add((spec.provider, spec.model_id))
    assert allowed == {("cloudflare", MODEL_70B)}


def test_resume_data_class_is_the_only_one_requested():
    assert RESUME_DATA_CLASS == "resume_pii"
