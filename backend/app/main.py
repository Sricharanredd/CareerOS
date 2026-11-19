from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import error_body, register_error_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.db.session import assert_mysql_8, database_status
from app.services import analysis as analysis_service

logger = logging.getLogger("careeros")

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    version = assert_mysql_8()
    recovered = analysis_service.recover_interrupted()
    logger.info(
        "careeros started",
        extra={"mysql": version, "env": settings.careeros_env, "recovered_analyses": recovered},
    )
    yield
    logger.info("careeros stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Private single-owner career management platform.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    @app.middleware("http")
    async def security_and_context(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming[:64] if incoming and incoming.isprintable() else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error", extra={"path": request.url.path})
            response = JSONResponse(
                status_code=500,
                content=error_body("internal_error", "Something went wrong. Please try again."),
            )
        finally:
            request_id_ctx.reset(token)

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/v1/auth"):
            response.headers["Cache-Control"] = "no-store"
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "version": app.version}

    @app.get("/ready", tags=["ops"])
    def ready():
        status = database_status()
        return JSONResponse(
            status_code=200 if status["ok"] else 503,
            content={"status": "ready" if status["ok"] else "unavailable", **status},
        )

    return app


app = create_app()
