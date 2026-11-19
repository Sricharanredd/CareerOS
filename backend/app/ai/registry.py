"""Provider selection. Tests override ``get_provider`` to inject a stub."""

from __future__ import annotations

from app.ai.base import AnalysisProvider
from app.ai.gemini import GeminiProvider
from app.core.config import get_settings


def get_provider() -> AnalysisProvider | None:
    settings = get_settings()
    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        return GeminiProvider(settings)
    return None
