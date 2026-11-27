"""Shared validate/repair loop for provider responses.

Lifted out of ``gemini.py`` without changing its behaviour: one attempt, then at most
``max_repairs`` regenerations with a validation hint, then a terminal provider error.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from pydantic import ValidationError

from app.ai.base import ProviderJsonParseError, ProviderSchemaError
from app.ai.output import AnalysisOutput

logger = logging.getLogger("careeros.ai")

INVALID_OUTPUT_MESSAGE = "The model returned output that did not match the expected structure."


def validate_or_repair(
    raw: str,
    regenerate: Callable[[str], str],
    *,
    provider_name: str,
    max_repairs: int = 0,
) -> AnalysisOutput:
    """Parse ``raw`` into ``AnalysisOutput``, asking the provider to fix it when allowed.

    ``regenerate`` receives a short hint describing what failed and returns new raw text.
    Adapters start with ``max_repairs=0``: a different provider is a better repair than a
    second prompt. Gemini keeps its historical single repair.
    """
    text = raw
    for attempt in range(max_repairs + 1):
        try:
            data = _load_json(text)
        except ValueError as exc:
            if attempt == max_repairs:
                raise ProviderJsonParseError(INVALID_OUTPUT_MESSAGE) from exc
            logger.warning("analysis output was not JSON", extra={"provider": provider_name})
            text = regenerate(_describe_validation_error(exc))
            continue
        try:
            return AnalysisOutput.model_validate(data)
        except ValidationError as exc:
            if attempt == max_repairs:
                raise ProviderSchemaError(INVALID_OUTPUT_MESSAGE) from exc
            logger.warning("analysis output failed validation", extra={"provider": provider_name})
            text = regenerate(_describe_validation_error(exc))
    raise AssertionError("unreachable")  # pragma: no cover


def _load_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned)


def _describe_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:8]
        )
    return str(exc)[:400]
