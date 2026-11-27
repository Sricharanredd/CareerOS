"""Cloudflare adapter behaviour against mocked HTTP responses. No real quota is used."""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.base import (
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
    ProviderRateLimited,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUnsupportedCapability,
)
from app.ai.cloudflare import (
    AUTH_MESSAGE,
    ENTITLEMENT_MESSAGE,
    NETWORK_MESSAGE,
    PERMISSION_MESSAGE,
    CloudflareProvider,
)

MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
RESUME_MARKER = "RESUME_CANARY_7f3c9a"

VALID_OUTPUT = {
    "score": 74,
    "summary": "Strong backend overlap.",
    "alignment_explanation": "Python and FastAPI appear in both documents.",
    "findings": [
        {
            "kind": "resume_evidence",
            "category": "matched_skill",
            "label": "Python APIs",
            "detail": "The resume shows production Python API work.",
            "evidence": "Five years building Python APIs with FastAPI.",
        }
    ],
}


def _request(**overrides) -> AnalysisRequest:
    values = {
        "resume_text": "Five years building Python APIs with FastAPI. " + RESUME_MARKER,
        "jd_text": "Senior backend role. Required: Python, FastAPI, MySQL.",
        "jd_title": "Senior Backend Engineer",
        "company_name": "Northstar Labs",
    }
    values.update(overrides)
    return AnalysisRequest(**values)


def _provider(ai_settings, handler, **overrides):
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    provider = CloudflareProvider(
        ai_settings(**overrides), transport=httpx.MockTransport(record)
    )
    return provider, calls


def _body(content: object, *, success: bool = True) -> dict:
    return {"success": success, "result": {"response": content}, "errors": []}


def _respond(payload: dict, status: int = 200, headers: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers)

    return handler


def test_successful_json_response_is_validated(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body(json.dumps(VALID_OUTPUT))))
    output = provider.analyze(_request())

    assert output.score == 74
    assert output.findings[0].label == "Python APIs"
    assert len(calls) == 1


def test_request_uses_the_approved_endpoint_model_and_json_mode(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body(json.dumps(VALID_OUTPUT))))
    provider.analyze(_request())

    request = calls[0]
    payload = json.loads(request.content)
    assert f"/accounts/test-account/ai/run/{MODEL}" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-token"
    assert payload["max_tokens"] == 4096
    assert payload["temperature"] == 0.2
    assert payload["response_format"] == {"type": "json_object"}
    assert RESUME_MARKER in payload["messages"][0]["content"]


def test_request_matches_the_documented_rest_contract(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body(json.dumps(VALID_OUTPUT))))
    provider.analyze(_request())

    request = calls[0]
    assert request.method == "POST"
    assert request.url.scheme == "https"
    assert request.url.host == "api.cloudflare.com"
    assert request.url.path == f"/client/v4/accounts/test-account/ai/run/{MODEL}"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["authorization"].count("Bearer ") == 1
    assert set(json.loads(request.content)) == {
        "messages",
        "max_tokens",
        "temperature",
        "response_format",
    }


def test_documented_missing_permission_401_is_an_auth_failure(ai_settings):
    """Cloudflare returns 401 code 10000 when the token lacks Workers AI permission."""
    provider, calls = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
            status=401,
        ),
    )
    with pytest.raises(ProviderAuthFailed) as error:
        provider.analyze(_request())
    assert str(error.value) == AUTH_MESSAGE
    assert len(calls) == 1


@pytest.mark.parametrize("override", [{"cloudflare_api_token": None}, {"cloudflare_account_id": ""}])
def test_missing_credentials_fail_before_any_http_call(ai_settings, override):
    with pytest.raises(ProviderUnavailable) as error:
        CloudflareProvider(ai_settings(**override), transport=httpx.MockTransport(_respond({})))
    assert str(error.value) == "Cloudflare is not configured."


def test_object_response_is_accepted(ai_settings):
    provider, _ = _provider(ai_settings, _respond(_body(VALID_OUTPUT)))
    assert provider.analyze(_request()).score == 74


def test_markdown_fenced_json_is_accepted(ai_settings):
    fenced = f"```json\n{json.dumps(VALID_OUTPUT)}\n```"
    provider, _ = _provider(ai_settings, _respond(_body(fenced)))
    assert provider.analyze(_request()).score == 74


def test_malformed_json_fails_without_a_repair_attempt(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body("this is not json")))
    with pytest.raises(ProviderJsonParseError) as error:
        provider.analyze(_request())
    assert error.value.code == "invalid_json"
    assert len(calls) == 1


def test_missing_fields_fail_validation(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body('{"score": 74}')))
    with pytest.raises(ProviderSchemaError) as error:
        provider.analyze(_request())
    assert error.value.code == "invalid_schema"
    assert len(calls) == 1
    assert RESUME_MARKER not in str(error.value)


def test_empty_response_is_rejected(ai_settings):
    provider, _ = _provider(ai_settings, _respond(_body("   ")))
    with pytest.raises(ProviderInvalidOutput):
        provider.analyze(_request())


def test_unexpected_response_structure_is_rejected(ai_settings):
    provider, _ = _provider(ai_settings, _respond({"success": True, "result": ["nope"]}))
    with pytest.raises(ProviderInvalidOutput):
        provider.analyze(_request())


def test_non_json_http_body_is_rejected(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    provider, _ = _provider(ai_settings, handler)
    with pytest.raises(ProviderInvalidOutput):
        provider.analyze(_request())


def test_rate_limit_preserves_retry_after(ai_settings):
    provider, calls = _provider(
        ai_settings, _respond({"success": False}, status=429, headers={"retry-after": "30"})
    )
    with pytest.raises(ProviderRateLimited) as error:
        provider.analyze(_request())
    assert error.value.retry_after_seconds == 30.0
    assert error.value.code == "provider_rate_limited"
    assert len(calls) == 1


def test_rate_limit_without_header_leaves_retry_after_unknown(ai_settings):
    provider, _ = _provider(ai_settings, _respond({"success": False}, status=429))
    with pytest.raises(ProviderRateLimited) as error:
        provider.analyze(_request())
    assert error.value.retry_after_seconds is None


def test_authentication_failure_is_not_retried(ai_settings):
    provider, calls = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"code": 10000, "message": "bad token test-token"}]},
            status=401,
        ),
    )
    with pytest.raises(ProviderAuthFailed) as error:
        provider.analyze(_request())
    assert str(error.value) == AUTH_MESSAGE
    assert error.value.code == "provider_auth_failed"
    assert "test-token" not in str(error.value)
    assert len(calls) == 1


def test_forbidden_is_permission_not_authentication(ai_settings):
    provider, calls = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"code": 9999, "message": "not allowed"}]},
            status=403,
        ),
    )
    with pytest.raises(ProviderPermissionDenied) as error:
        provider.analyze(_request())
    assert not isinstance(error.value, ProviderAuthFailed)
    assert error.value.code == "provider_permission_denied"
    assert str(error.value) == PERMISSION_MESSAGE
    assert len(calls) == 1


@pytest.mark.parametrize("code", [5035, 5016, 5018, 3041])
def test_documented_403_entitlement_codes(ai_settings, code):
    provider, calls = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"code": code, "message": "restricted"}]},
            status=403,
        ),
    )
    with pytest.raises(ProviderEntitlementDenied) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_entitlement_denied"
    assert str(error.value) == ENTITLEMENT_MESSAGE
    assert len(calls) == 1


def test_account_blocked_403_is_permission(ai_settings):
    provider, _ = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"code": 3023, "message": "account blocked"}]},
            status=403,
        ),
    )
    with pytest.raises(ProviderPermissionDenied) as error:
        provider.analyze(_request())
    assert str(error.value) == PERMISSION_MESSAGE


@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "errors": [{"message": "unknown"}]},
        {"success": False, "errors": [{"code": "not-a-number"}]},
        {"success": False},
    ],
)
def test_unknown_403_is_permission_without_guessing(ai_settings, response):
    provider, _ = _provider(ai_settings, _respond(response, status=403))
    with pytest.raises(ProviderPermissionDenied) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_permission_denied"
    assert str(error.value) == PERMISSION_MESSAGE


def test_403_non_json_body_is_permission_and_does_not_leak(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=f"<html>denied {RESUME_MARKER} test-token</html>")

    provider, _ = _provider(ai_settings, handler)
    with pytest.raises(ProviderPermissionDenied) as error:
        provider.analyze(_request())
    assert str(error.value) == PERMISSION_MESSAGE
    assert RESUME_MARKER not in str(error.value)
    assert "test-token" not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_one_http_request_per_analyze(ai_settings, status):
    """Retry ownership is centralized: the adapter never re-sends inside one call."""
    provider, calls = _provider(ai_settings, _respond({"success": False}, status=status))
    with pytest.raises(ProviderError):
        provider.analyze(_request())
    assert len(calls) == 1


def test_bad_request_does_not_echo_the_provider_body(ai_settings):
    provider, _ = _provider(
        ai_settings,
        _respond(
            {
                "success": False,
                "errors": [{"message": f"invalid model {RESUME_MARKER} test-token"}],
            },
            status=400,
        ),
    )
    with pytest.raises(ProviderError) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_rejected"
    assert RESUME_MARKER not in str(error.value)
    assert "test-token" not in str(error.value)


def test_provider_refusal_is_reported_as_blocked(ai_settings):
    provider, _ = _provider(
        ai_settings,
        _respond(
            {"success": False, "errors": [{"message": "Model blocked this request"}]},
            status=200,
        ),
    )
    with pytest.raises(ProviderBlocked):
        provider.analyze(_request())


def test_json_mode_failure_is_an_invalid_output_not_a_leak(ai_settings):
    provider, _ = _provider(
        ai_settings,
        _respond(
            {
                "success": False,
                "errors": [{"message": "AiError: JSON Mode couldn't be met; got prose"}],
            },
            status=200,
        ),
    )
    with pytest.raises(ProviderInvalidOutput) as error:
        provider.analyze(_request())
    assert "JSON Mode" not in str(error.value)


def test_timeout_is_typed_and_fixed_text(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider, _ = _provider(ai_settings, handler)
    with pytest.raises(ProviderTimeout) as error:
        provider.analyze(_request())
    assert RESUME_MARKER not in str(error.value)


def test_network_failure_is_typed_and_fixed_text(ai_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connect failed {RESUME_MARKER} test-token", request=request)

    provider, calls = _provider(ai_settings, handler)
    with pytest.raises(ProviderNetworkError) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_network_error"
    assert str(error.value) == NETWORK_MESSAGE
    assert RESUME_MARKER not in str(error.value)
    assert "test-token" not in str(error.value)
    assert len(calls) == 1


def test_missing_model_is_typed(ai_settings):
    provider, calls = _provider(ai_settings, _respond({"success": False}, status=404))
    with pytest.raises(ProviderInvalidModel) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_invalid_model"
    assert len(calls) == 1


def test_oversized_input_fails_before_any_http_call(ai_settings):
    provider, calls = _provider(ai_settings, _respond(_body(json.dumps(VALID_OUTPUT))))
    with pytest.raises(ProviderError) as error:
        provider.analyze(_request(resume_text="r" * 100_000))
    assert error.value.code == "resume_too_large_for_provider"
    assert calls == []


def test_unregistered_model_is_refused_before_any_http_call(ai_settings):
    provider, calls = _provider(
        ai_settings,
        _respond(_body(json.dumps(VALID_OUTPUT))),
        cloudflare_model="@cf/meta/not-registered",
    )
    with pytest.raises(ProviderUnsupportedCapability) as error:
        provider.analyze(_request())
    assert error.value.code == "provider_unsupported_capability"
    assert calls == []
