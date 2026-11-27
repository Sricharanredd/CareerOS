"""Cloudflare Workers AI adapter (native ``/ai/run`` endpoint, JSON Mode).

The API wraps every completion in ``{"result": {"response": ...}, "success": ...}`` and is
not the same shape as Gemini. JSON Mode is documented but not schema-guaranteed, so the
shared validator decides what is usable. No repair attempt is made: Cloudflare is the
privacy-approved primary and a second prompt would only spend the same daily allowance.

One HTTP request per ``analyze()`` call. Retries are owned by ``app.ai.retry``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.ai.base import (
    AnalysisProvider,
    AnalysisRequest,
    ProviderAuthFailed,
    ProviderBlocked,
    ProviderEntitlementDenied,
    ProviderError,
    ProviderInvalidModel,
    ProviderInvalidOutput,
    ProviderJsonParseError,
    ProviderNetworkError,
    ProviderPermissionDenied,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.models import get_model
from app.ai.output import AnalysisOutput
from app.ai.prompts import build_prompt, build_repair_prompt
from app.ai.quota import (
    CLOUDFLARE_EXHAUSTED_CODES,
    QUOTA_EXHAUSTED_MESSAGE,
    QuotaScope,
    parse_cloudflare_quota_headers,
    quota_store,
)
from app.ai.repair import validate_or_repair
from app.core.config import Settings

logger = logging.getLogger("careeros.ai")

ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
RETRYABLE_STATUS = {500, 502, 503, 504}
MAX_REPAIRS = 0
MAX_OUTPUT_TOKENS = 4096
PROMPT_OVERHEAD_TOKENS = 512
CHARS_PER_TOKEN = 4

UNAVAILABLE_MESSAGE = "The AI provider is temporarily unavailable. Try again in a moment."
TIMEOUT_MESSAGE = "The AI provider took too long to respond. Try again or shorten the inputs."
AUTH_MESSAGE = "The AI provider rejected the API credentials."
RATE_MESSAGE = "The AI provider is rate-limiting requests. Try again shortly."
BLOCKED_MESSAGE = "The AI provider refused to process this content."
REJECTED_MESSAGE = "The AI provider rejected the request."
EMPTY_MESSAGE = "The AI provider returned no usable content."
UNEXPECTED_MESSAGE = "The AI provider returned an unexpected response."
TOO_LARGE_MESSAGE = "This resume is too long for the configured AI model. Shorten it and try again."
PERMISSION_MESSAGE = "The AI provider denied access to this account or model."
ENTITLEMENT_MESSAGE = "The AI provider's plan or terms do not allow this model."
NETWORK_MESSAGE = "The AI provider could not be reached."
INVALID_MODEL_MESSAGE = "The configured AI model is not available from the provider."
CAPABILITY_MESSAGE = "The configured AI model does not support the required capability."

# Documented Cloudflare 403 codes: 3023 account blocked (permission), 5035 paid plan,
# 5016/5018/3041 terms/private model (entitlement). Unknown 403 stays permission.
ENTITLEMENT_CODES = frozenset({5035, 5016, 5018, 3041})

# Matched in memory only; the provider's own message is never logged or returned.
JSON_MODE_MARKER = "json mode couldn't be met"
BLOCKED_MARKERS = ("blocked", "safety", "moderation")


class CloudflareProvider(AnalysisProvider):
    name = "cloudflare"
    scope = "account"

    def __init__(
        self, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        if not settings.cloudflare_api_token or not settings.cloudflare_account_id:
            raise ProviderUnavailable("Cloudflare is not configured.")
        self._token = settings.cloudflare_api_token
        self._account_id = settings.cloudflare_account_id
        self.model = settings.cloudflare_model
        self._timeout = settings.ai_timeout_seconds
        self._transport = transport

    def analyze(self, request: AnalysisRequest) -> AnalysisOutput:
        self._require_budget(request)
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

    def _require_budget(self, request: AnalysisRequest) -> None:
        """Fail rather than silently truncate. JD tail is included in the estimate too."""
        spec = get_model(self.name, self.model)
        context = spec.context_tokens if spec else None
        if context is None:
            raise ProviderUnsupportedCapability(CAPABILITY_MESSAGE)
        estimate = (
            (len(request.resume_text) + len(request.jd_text)) // CHARS_PER_TOKEN
            + PROMPT_OVERHEAD_TOKENS
        )
        if estimate > context - MAX_OUTPUT_TOKENS:
            raise ProviderError(TOO_LARGE_MESSAGE, code="resume_too_large_for_provider")

    def _generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": temperature,
            # json_object, not json_schema: Pydantic emits $defs/$ref, which Workers AI
            # does not document support for. The prompt carries the schema and the shared
            # validator enforces it. `shortcut:` json_object is looser; revisit if Cloudflare
            # documents $ref support.
            "response_format": {"type": "json_object"},
        }
        response = self._post(payload)
        _record_quota(response, self.name, self.model, self.scope)
        return _interpret(response)

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        url = ENDPOINT.format(account_id=self._account_id, model=self.model)
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                return client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(TIMEOUT_MESSAGE) from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(NETWORK_MESSAGE) from exc


def _record_quota(
    response: httpx.Response, provider: str, model: str, scope: QuotaScope
) -> None:
    """Quota is a side observation: a recorder bug must never fail an analysis."""
    try:
        if response.status_code < 400:
            quota_store.observe_success(provider, model, scope)
        elif response.status_code == 429:
            quota_store.observe(
                provider,
                model,
                scope,
                parse_cloudflare_quota_headers(
                    response.headers,
                    quota_store.now(),
                    status_code=response.status_code,
                    error_codes=_error_codes(response),
                ),
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("quota observation failed", extra={"provider": provider})


def _interpret(response: httpx.Response) -> str:
    status = response.status_code
    if status == 429:
        if _error_codes(response) & CLOUDFLARE_EXHAUSTED_CODES:
            raise ProviderQuotaExhausted(QUOTA_EXHAUSTED_MESSAGE)
        raise ProviderRateLimited(RATE_MESSAGE, retry_after_seconds=_retry_after(response))
    if status == 401:
        raise ProviderAuthFailed(AUTH_MESSAGE)
    if status == 403:
        raise _permission_error(response)
    if status == 404:
        raise ProviderInvalidModel(INVALID_MODEL_MESSAGE)
    if status in RETRYABLE_STATUS:
        raise ProviderUnavailable(UNAVAILABLE_MESSAGE)
    if status >= 400:
        raise ProviderError(REJECTED_MESSAGE, code="provider_rejected")

    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderJsonParseError(UNEXPECTED_MESSAGE) from exc
    if not isinstance(body, dict):
        raise ProviderInvalidOutput(UNEXPECTED_MESSAGE)
    if body.get("success") is False:
        raise _failure(body)

    result = body.get("result")
    if not isinstance(result, dict):
        raise ProviderInvalidOutput(UNEXPECTED_MESSAGE)

    value = result.get("response")
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.strip():
        return value
    raise ProviderInvalidOutput(EMPTY_MESSAGE)


def _failure(body: dict[str, Any]) -> ProviderError:
    text = " ".join(
        str(error.get("message", ""))
        for error in body.get("errors") or []
        if isinstance(error, dict)
    ).lower()
    if JSON_MODE_MARKER in text:
        return ProviderJsonParseError(UNEXPECTED_MESSAGE)
    if any(marker in text for marker in BLOCKED_MARKERS):
        return ProviderBlocked(BLOCKED_MESSAGE)
    return ProviderError(REJECTED_MESSAGE, code="provider_rejected")


def _permission_error(response: httpx.Response) -> ProviderError:
    """403 is never an auth failure. Documented plan/terms codes are entitlement; rest unknown."""
    if _error_codes(response) & ENTITLEMENT_CODES:
        return ProviderEntitlementDenied(ENTITLEMENT_MESSAGE)
    return ProviderPermissionDenied(PERMISSION_MESSAGE)


def _error_codes(response: httpx.Response) -> frozenset[int]:
    """Read only numeric error codes; the provider body is never logged or returned."""
    try:
        body = response.json()
    except ValueError:
        return frozenset()
    if not isinstance(body, dict):
        return frozenset()
    codes: set[int] = set()
    for error in body.get("errors") or []:
        if not isinstance(error, dict):
            continue
        try:
            codes.add(int(error.get("code")))
        except (TypeError, ValueError):
            continue
    return frozenset(codes)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None
