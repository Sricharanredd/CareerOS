"""Provider name to adapter class, and the model each provider is configured to use.

Adding a provider is a code change with a verified registry row, never a runtime guess.
"""

from __future__ import annotations

from app.ai.base import AnalysisProvider, ProviderUnavailable
from app.ai.cloudflare import CloudflareProvider
from app.ai.gemini import GeminiProvider
from app.core.config import Settings

PROVIDERS: dict[str, type[AnalysisProvider]] = {
    "cloudflare": CloudflareProvider,
    "gemini": GeminiProvider,
}

MODEL_SETTING = {
    "cloudflare": "cloudflare_model",
    "gemini": "gemini_model",
}


def configured_model(provider: str, settings: Settings) -> str | None:
    field = MODEL_SETTING.get(provider)
    return getattr(settings, field, None) if field else None


def build_adapter(provider: str, settings: Settings) -> AnalysisProvider | None:
    """Return a configured adapter, or None when the provider is unknown or unconfigured.

    This does not apply the privacy gate: selection goes through ``ai/router.py`` so a
    direct call cannot become a bypass in production.
    """
    adapter = PROVIDERS.get(provider)
    if adapter is None:
        return None
    try:
        return adapter(settings)
    except ProviderUnavailable:
        return None
