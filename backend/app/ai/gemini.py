"""Google Gemini implementation of the provider protocol.

Uses the public REST endpoint through httpx so no vendor SDK is required. The
API key is read from settings and never logged.

Legacy and gate-denied: Gemini is never selected for resume analysis. It still follows the
same one-request contract as every adapter, so retries are owned by ``app.ai.retry``.
"""

from __future__ import annotations

import httpx

from app.ai.base import (
    AnalysisProvider,
    AnalysisRequest,
    ProviderError,
    ProviderInvalidOutput,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.output import AnalysisOutput
from app.ai.prompts import build_prompt, build_repair_prompt
from app.ai.repair import validate_or_repair
from app.core.config import Settings

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_REPAIRS = 0


class GeminiProvider(AnalysisProvider):
    name = "gemini"
    scope = "model"

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise ProviderUnavailable("The Gemini API key is not configured.")
        self._key = settings.gemini_api_key
        self.model = settings.gemini_model
        self._timeout = settings.ai_timeout_seconds

    def analyze(self, request: AnalysisRequest) -> AnalysisOutput:
        prompt = build_prompt(
            resume_text=request.resume_text,
            jd_text=request.jd_text,
            jd_title=request.jd_title,
            company_name=request.company_name,
        )
        raw = self._generate(prompt)
        return validate_or_repair(
            raw,
            lambda hint: self._generate(build_repair_prompt(prompt, hint), temperature=0.0),
            provider_name=self.name,
            max_repairs=MAX_REPAIRS,
        )

    def _generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ],
        }
        url = ENDPOINT.format(model=self.model)

        response = self._post(url, payload)

        if response.status_code in RETRYABLE_STATUS:
            raise ProviderUnavailable(
                "The AI provider is temporarily unavailable. Try again in a moment."
            )
        if response.status_code >= 400:
            raise ProviderError(_provider_message(response), code="provider_rejected")

        return _first_text(response.json())

    def _post(self, url: str, payload: dict) -> httpx.Response:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                return client.post(
                    url,
                    json=payload,
                    headers={
                        "x-goog-api-key": self._key,
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(
                "The AI provider took too long to respond. Try again or shorten the inputs."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("The AI provider could not be reached.") from exc


def _first_text(body: dict) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        feedback = body.get("promptFeedback") or {}
        reason = feedback.get("blockReason")
        if reason:
            raise ProviderInvalidOutput(
                "The provider blocked this request. Check the content and try again."
            )
        raise ProviderInvalidOutput("The provider returned no content.")

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        finish = candidate.get("finishReason")
        if finish in {"SAFETY", "RECITATION", "BLOCKLIST"}:
            raise ProviderInvalidOutput(
                "The provider blocked this request. Check the content and try again."
            )
        raise ProviderInvalidOutput("The provider returned an empty response.")
    return text


def _provider_message(response: httpx.Response) -> str:
    """Fixed text only: provider bodies are never echoed into errors or job rows."""
    if response.status_code == 403:
        return "The AI provider rejected the API key."
    if response.status_code == 400:
        return "The AI provider rejected the request."
    return f"The AI provider returned HTTP {response.status_code}."
