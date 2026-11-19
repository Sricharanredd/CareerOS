"""Google Gemini implementation of the provider protocol.

Uses the public REST endpoint through httpx so no vendor SDK is required. The
API key is read from settings and never logged.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from pydantic import ValidationError

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
from app.core.config import Settings

logger = logging.getLogger("careeros.ai")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_REPAIRS = 1


class GeminiProvider(AnalysisProvider):
    name = "gemini"

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
        try:
            return AnalysisOutput.model_validate(_loads(raw))
        except (ValidationError, ValueError) as exc:
            logger.warning("analysis output failed validation", extra={"provider": self.name})
            repaired = self._generate(
                build_repair_prompt(prompt, _describe_validation_error(exc)), temperature=0.0
            )
            try:
                return AnalysisOutput.model_validate(_loads(repaired))
            except (ValidationError, ValueError) as exc2:
                raise ProviderInvalidOutput(
                    "The model returned output that did not match the expected structure."
                ) from exc2

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
            time.sleep(1.5)
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


def _loads(raw: str) -> dict:
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


def _provider_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        message = (body.get("error") or {}).get("message")
        if message:
            return str(message)[:300]
    except ValueError:
        pass
    if response.status_code == 403:
        return "The AI provider rejected the API key."
    if response.status_code == 400:
        return "The AI provider rejected the request."
    return f"The AI provider returned HTTP {response.status_code}."
