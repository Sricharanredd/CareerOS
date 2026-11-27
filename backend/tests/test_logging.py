"""The log formatter is allowlist-only and never writes exception or extra content."""

from __future__ import annotations

import json
import logging
import sys

from app.core.logging import ALLOWED_LOG_FIELDS, JsonFormatter, configure_logging

RESUME_CANARY = "RESUME_CANARY_7f3c9a"
KEY_CANARY = "sk-CANARY-0000-not-a-key"
ACCOUNT_CANARY = "0123456789abcdef0123456789abcdef"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_CANARY}/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
)


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        "careeros.ai", logging.WARNING, "ai.py", 42, "analysis failed", None, None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_only_allowlisted_fields_survive():
    record = _record(
        provider="cloudflare",
        resume_text=RESUME_CANARY,
        authorization=f"Bearer {KEY_CANARY}",
    )
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["provider"] == "cloudflare"
    assert payload["msg"] == "analysis failed"
    assert payload["dropped_fields"] == 2
    assert RESUME_CANARY not in formatted
    assert KEY_CANARY not in formatted


def test_exception_message_is_replaced_by_type_and_location():
    try:
        raise RuntimeError(f"{RESUME_CANARY} {KEY_CANARY}")
    except RuntimeError:
        record = logging.LogRecord(
            "careeros.analysis", logging.ERROR, "analysis.py", 161, "analysis crashed", None,
            sys.exc_info(),
        )

    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["exc_type"] == "RuntimeError"
    assert payload["exc_at"].startswith("test_logging.py:")
    assert RESUME_CANARY not in formatted
    assert KEY_CANARY not in formatted


def test_extras_from_another_logger_are_filtered_too():
    record = logging.LogRecord("httpx", logging.INFO, "client.py", 1, "HTTP Request", None, None)
    record.request_body = RESUME_CANARY
    record.path = "/ai/run"

    payload = json.loads(JsonFormatter().format(record))
    assert payload["path"] == "/ai/run"
    assert payload["dropped_fields"] == 1
    assert "request_body" not in payload


def test_configure_logging_quiets_httpx_without_disabling_app_logs():
    """httpx logs the full upstream URL at INFO, which carries the Cloudflare account id."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    httpx_logger = logging.getLogger("httpx")
    saved_httpx_level = httpx_logger.level
    try:
        configure_logging("INFO")
        assert httpx_logger.level == logging.WARNING
        assert not httpx_logger.isEnabledFor(logging.INFO)
        # Application logging is untouched: the root logger still handles INFO and up.
        assert root.level == logging.INFO
        assert root.handlers
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        httpx_logger.setLevel(saved_httpx_level)


def test_httpx_request_url_is_not_captured_while_app_errors_are(caplog):
    caplog.set_level(logging.INFO)
    httpx_logger = logging.getLogger("httpx")
    saved_httpx_level = httpx_logger.level
    try:
        httpx_logger.setLevel(logging.WARNING)
        logging.getLogger("httpx").info(
            'HTTP Request: POST %s "HTTP/1.1 401 Unauthorized"', CLOUDFLARE_URL
        )
        logging.getLogger("careeros.analysis").warning(
            "analysis failed", extra={"code": "provider_auth_failed"}
        )
    finally:
        httpx_logger.setLevel(saved_httpx_level)

    assert ACCOUNT_CANARY not in caplog.text
    assert "HTTP Request" not in caplog.text
    assert "Bearer" not in caplog.text
    assert any(getattr(record, "code", None) == "provider_auth_failed" for record in caplog.records)


def test_observability_fields_are_allowlisted_without_sensitive_names():
    for name in ("priority", "health", "quota", "failure_class", "delay_seconds"):
        assert name in ALLOWED_LOG_FIELDS
    for name in (
        "resume_text",
        "jd_text",
        "prompt",
        "token",
        "authorization",
        "account_id",
        "body",
        "error_message",
    ):
        assert name not in ALLOWED_LOG_FIELDS


def test_routing_and_attempt_metadata_is_not_silently_dropped():
    record = _record(
        priority=0,
        health="degraded",
        quota="rate_limited",
        failure_class="transient",
        delay_seconds=1.0,
    )
    payload = json.loads(JsonFormatter().format(record))

    assert payload["priority"] == 0
    assert payload["health"] == "degraded"
    assert payload["quota"] == "rate_limited"
    assert payload["failure_class"] == "transient"
    assert payload["delay_seconds"] == 1.0
    assert "dropped_fields" not in payload
