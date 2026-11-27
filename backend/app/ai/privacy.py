"""Privacy gate for resume data.

Evaluated in this order, before any capability, quota or health check:

1. provider is explicitly approved,
2. the configured model is registered,
3. the model is approved for the resume data class,
4. retention is documented,
5. training use is known and allowed,
6. free-tier eligibility holds,
7. structured JSON output is documented,
8. the context window is known and large enough.

Unknown is denial. Free-tier eligibility alone never approves a model, and adding a name to
``AI_APPROVED_PROVIDERS`` cannot approve a model the registry has not verified.
"""

from __future__ import annotations

from app.ai.models import RESUME_DATA_CLASS, ModelSpec, get_model
from app.ai.providers import configured_model
from app.core.config import Settings

MIN_CONTEXT_TOKENS = 8_000


def denial_reasons(
    spec: ModelSpec,
    settings: Settings,
    *,
    required_context_tokens: int = MIN_CONTEXT_TOKENS,
) -> tuple[str, ...]:
    """Every reason this model may not carry resume data. Empty means approved."""
    reasons: list[str] = []

    if spec.provider not in settings.ai_approved_provider_set:
        reasons.append("not_approved")

    if RESUME_DATA_CLASS not in spec.approved_data_classes:
        reasons.append("data_class_not_approved")

    if spec.privacy_verified_on is None:
        reasons.append("privacy_unverified")

    if not spec.retention or spec.retention == "unknown":
        reasons.append("retention_unknown")

    if spec.trains_on_content == "unknown":
        reasons.append("training_unknown")
    elif spec.trains_on_content is True and not settings.ai_allow_training_providers:
        reasons.append("training_not_allowed")

    if settings.ai_free_only and not spec.free_tier:
        reasons.append("not_free")

    if not spec.json_output:
        reasons.append("no_json")

    if spec.context_tokens is None:
        reasons.append("context_unknown")
    elif spec.context_tokens < required_context_tokens:
        reasons.append("context_insufficient")

    return tuple(reasons)


def approved_candidates(
    settings: Settings,
    *,
    required_context_tokens: int = MIN_CONTEXT_TOKENS,
) -> tuple[ModelSpec, ...]:
    """Configured models in provider-chain order that pass every privacy gate."""
    candidates: list[ModelSpec] = []
    for provider in settings.ai_provider_chain:
        model_id = configured_model(provider, settings)
        if not model_id:
            continue
        spec = get_model(provider, model_id)
        if spec is None:
            continue
        if denial_reasons(spec, settings, required_context_tokens=required_context_tokens):
            continue
        candidates.append(spec)
    return tuple(candidates)
