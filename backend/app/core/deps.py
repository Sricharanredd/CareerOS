"""Request-scoped dependencies: auth, pagination, CSRF."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, RateLimitError, UnauthorizedError
from app.core.logging import owner_id_ctx
from app.core.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    constant_time_equals,
    decode_access_token,
    utcnow,
)
from app.db.models import Owner
from app.db.session import get_db
from app.repositories import owner as owner_repo
from app.repositories import session as session_repo
from app.schemas.common import PageParams

DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host if request.client else None


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Sign in to continue.", code="missing_token")
    return token.strip()


def current_session(db: Session, token: str):
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            "Your session expired. Sign in again.", code="token_expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid session token.", code="invalid_token") from exc

    session = session_repo.get_by_id(db, str(payload["sid"]))
    if session is None or session.revoked_at is not None:
        raise UnauthorizedError("This session has been revoked.", code="session_revoked")
    if session.expires_at <= utcnow():
        raise UnauthorizedError("Session expired. Sign in again.", code="session_expired")
    if session.owner_id != payload["sub"]:
        raise UnauthorizedError("Invalid session token.", code="invalid_token")
    return session


def get_current_owner(request: Request, db: DbSession) -> Owner:
    token = _bearer(request)
    session = current_session(db, token)
    owner = owner_repo.get_by_id(db, session.owner_id)
    if owner is None:
        raise UnauthorizedError("Account not found.", code="invalid_owner")
    request.state.session_id = session.id
    request.state.access_token = token
    owner_id_ctx.set(owner.id)
    return owner


CurrentOwner = Annotated[Owner, Depends(get_current_owner)]


def pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(pagination)]


def require_csrf(
    request: Request,
    x_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> None:
    cookie_value = request.cookies.get(CSRF_COOKIE)
    if not cookie_value or not x_csrf_token:
        raise ForbiddenError("Missing CSRF token.", code="csrf_missing")
    if not constant_time_equals(cookie_value, x_csrf_token):
        raise ForbiddenError("Invalid CSRF token.", code="csrf_invalid")


def refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def enforce_rate_limit(*, key: str, limiter, message: str) -> None:
    retry_after = limiter.retry_after(key)
    if retry_after:
        raise RateLimitError(message, details={"retry_after_seconds": retry_after})
