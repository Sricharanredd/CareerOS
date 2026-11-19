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


class ProviderTimeout(ProviderError):
    code = "provider_timeout"


class ProviderInvalidOutput(ProviderError):
    code = "invalid_output"


@dataclass(frozen=True)
class AnalysisRequest:
    resume_text: str
    jd_text: str
    jd_title: str
    company_name: str | None = None


class AnalysisProvider(Protocol):
    name: str
    model: str

    def analyze(self, request: AnalysisRequest) -> AnalysisOutput: ...
