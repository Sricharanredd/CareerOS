"""Structured JSON logging with request correlation IDs.

Allowlist only: an ``extra`` field reaches the log only if its name is in
``ALLOWED_LOG_FIELDS``. Anything else is counted in ``dropped_fields`` and discarded. The
same rule applies to third-party log records, which is why filtering lives in the formatter
rather than only at call sites.

Exception *messages* are never written: they can carry request or resume content. Only the
exception type and the last frame location are recorded.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
owner_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("owner_id", default="-")

ALLOWED_LOG_FIELDS = frozenset(
    {
        # correlation and outcome
        "event",
        "code",
        "reason",
        "request_id",
        "owner_id",
        "job_id",
        "attempt",
        "status",
        "http_status",
        "latency_ms",
        "duration_ms",
        "dropped_fields",
        # AI routing metadata (never content)
        "provider",
        "model",
        "scope",
        "free_tier",
        "tokens_in",
        "tokens_out",
        "resets_at",
        "truncated_chars",
        "score",
        "priority",
        "health",
        "quota",
        "failure_class",
        "delay_seconds",
        # request and process context
        "method",
        "path",
        "mysql",
        "env",
        "recovered_analyses",
        "exc_type",
        "exc_at",
    }
)

_RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "owner_id": owner_id_ctx.get(),
        }

        dropped = 0
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            if key in ALLOWED_LOG_FIELDS:
                payload[key] = value
            else:
                dropped += 1
        if dropped:
            payload["dropped_fields"] = dropped

        if record.exc_info:
            exc_type, _, traceback = record.exc_info
            payload["exc_type"] = exc_type.__name__ if exc_type else "Exception"
            payload["exc_at"] = _last_frame(traceback)

        return json.dumps(payload, default=str, ensure_ascii=False)


def _last_frame(traceback: TracebackType | None) -> str | None:
    while traceback is not None and traceback.tb_next is not None:
        traceback = traceback.tb_next
    if traceback is None:
        return None
    return f"{os.path.basename(traceback.tb_frame.f_code.co_filename)}:{traceback.tb_lineno}"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine", "pypdf", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
