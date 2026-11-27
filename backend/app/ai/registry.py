"""Provider selection. Tests override ``get_provider`` to inject a stub."""

from __future__ import annotations

from app.ai.base import AnalysisProvider
from app.ai.router import select_provider
from app.core.config import get_settings


def get_provider() -> AnalysisProvider | None:
    """The single privacy-approved provider, or None when none is configured.

    Raises ``ProviderPrivacyDenied`` when a provider is configured but the gate refuses it.
    """
    return select_provider(get_settings())
