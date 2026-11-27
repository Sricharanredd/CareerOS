"""Verified model and privacy registry. Facts only.

Every row was read from official provider documentation; the dates record when. See
``docs/STAGE2_AI_PROVIDER_RESEARCH.md`` §12 for the source of each claim.

Rules this data encodes:

- A model is eligible for resume data only when its retention **and** no-training policy
  are documented. Unknown training policy means not eligible, however free it is.
- An unverified context window keeps a model out: the adapter cannot budget input without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RESUME_DATA_CLASS = "resume_pii"
VERIFIED_ON = "2026-11-22"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    provider: str
    model_id: str
    free_tier: bool
    json_output: bool
    context_tokens: int | None
    scope: Literal["model", "account"]
    retention: str
    trains_on_content: bool | Literal["unknown"]
    approved_data_classes: frozenset[str] = frozenset()
    capability_verified_on: str = VERIFIED_ON
    privacy_verified_on: str | None = None
    notes: str = ""

    @property
    def privacy_approved(self) -> bool:
        """True only when retention and no-training are both documented."""
        return (
            RESUME_DATA_CLASS in self.approved_data_classes
            and self.privacy_verified_on is not None
            and self.trains_on_content is False
            and self.retention != "unknown"
        )

    @property
    def eligible_for_resume(self) -> bool:
        """Routable under strict free-only + privacy-first, with a known input budget."""
        return (
            self.privacy_approved
            and self.free_tier
            and self.json_output
            and self.context_tokens is not None
        )


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        provider="cloudflare",
        model_id="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        free_tier=True,
        json_output=True,
        context_tokens=24_000,
        scope="account",
        retention="zero",
        trains_on_content=False,
        approved_data_classes=frozenset({RESUME_DATA_CLASS}),
        privacy_verified_on=VERIFIED_ON,
        notes="Approved default primary. JSON Mode is documented but not schema-guaranteed.",
    ),
    ModelSpec(
        provider="cloudflare",
        model_id="@cf/meta/llama-3.1-8b-instruct",
        free_tier=True,
        json_output=True,
        context_tokens=None,
        scope="account",
        retention="zero",
        trains_on_content=False,
        approved_data_classes=frozenset({RESUME_DATA_CLASS}),
        privacy_verified_on=VERIFIED_ON,
        notes="Privacy-approved, deliberately disabled until its context window is verified.",
    ),
    ModelSpec(
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        free_tier=True,
        json_output=True,
        context_tokens=1_048_576,
        scope="model",
        retention="free-tier content used to improve products",
        trains_on_content=True,
        privacy_verified_on=None,
        notes="Excluded while free-only. Paid tier would be compliant but is out of scope.",
    ),
    ModelSpec(
        provider="groq",
        model_id="openai/gpt-oss-120b",
        free_tier=True,
        json_output=True,
        context_tokens=131_072,
        scope="model",
        retention="<=30d abuse logs; ZDR available",
        trains_on_content="unknown",
        notes="Conditional: training use is not documented, so it cannot receive resumes.",
    ),
    ModelSpec(
        provider="groq",
        model_id="openai/gpt-oss-20b",
        free_tier=True,
        json_output=True,
        context_tokens=131_072,
        scope="model",
        retention="<=30d abuse logs; ZDR available",
        trains_on_content="unknown",
        notes="Conditional: training use is not documented, so it cannot receive resumes.",
    ),
)


def models_for(provider: str) -> tuple[ModelSpec, ...]:
    return tuple(spec for spec in MODELS if spec.provider == provider)


def get_model(provider: str, model_id: str) -> ModelSpec | None:
    for spec in MODELS:
        if spec.provider == provider and spec.model_id == model_id:
            return spec
    return None
