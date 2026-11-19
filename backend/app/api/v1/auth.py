from __future__ import annotations

from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.deps import CurrentOwner, DbSession, client_ip, require_csrf
from app.core.errors import UnauthorizedError
from app.core.routing import CommittingAPIRouter
from app.core.security import CSRF_COOKIE, REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    MetaResponse,
    OwnerProfile,
    OwnerUpdate,
    SessionView,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.services import auth as auth_service
from app.services.auth import AuthResult

router = CommittingAPIRouter(prefix="/auth", tags=["auth"])


def set_auth_cookies(response: Response, result: AuthResult) -> None:
    settings = get_settings()
    max_age = settings.refresh_token_ttl_days * 24 * 3600
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
    )
    # Readable by the SPA so it can echo the value in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        result.csrf_token,
        max_age=max_age,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=settings.cookie_domain or None
    )
    response.delete_cookie(CSRF_COOKIE, path="/", domain=settings.cookie_domain or None)


def _token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_at=result.access_expires_at,
        owner=OwnerProfile.model_validate(result.owner),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession):
    result = auth_service.login(
        db,
        email=payload.email,
        password=payload.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, result)
    return _token_response(result)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_csrf)])
def refresh(request: Request, response: Response, db: DbSession):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise UnauthorizedError("Session expired. Sign in again.", code="missing_refresh")
    result = auth_service.refresh(
        db,
        raw_refresh=raw,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, result)
    return _token_response(result)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: DbSession):
    auth_service.logout(db, request.cookies.get(REFRESH_COOKIE))
    clear_auth_cookies(response)
    return Response(status_code=204)


@router.get("/me", response_model=OwnerProfile)
def me(owner: CurrentOwner):
    return OwnerProfile.model_validate(owner)


@router.patch("/me", response_model=OwnerProfile)
def update_me(payload: OwnerUpdate, owner: CurrentOwner, db: DbSession):
    for field in ("full_name", "timezone", "currency"):
        value = getattr(payload, field)
        if value is not None:
            setattr(owner, field, value)
    if payload.theme is not None:
        owner.theme = payload.theme
    db.flush()
    return OwnerProfile.model_validate(owner)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest, request: Request, owner: CurrentOwner, db: DbSession
):
    auth_service.change_password(
        db,
        owner,
        current_password=payload.current_password,
        new_password=payload.new_password,
        current_session_id=getattr(request.state, "session_id", ""),
    )
    return MessageResponse(message="Password updated. Other sessions were signed out.")


@router.get("/sessions", response_model=list[SessionView])
def sessions(request: Request, owner: CurrentOwner, db: DbSession):
    current_id = getattr(request.state, "session_id", "")
    return [
        SessionView(
            id=row.id,
            user_agent=row.user_agent,
            ip=row.ip,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            current=row.id == current_id,
        )
        for row in auth_service.list_sessions(db, owner.id, current_id)
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, owner: CurrentOwner, db: DbSession):
    auth_service.revoke_session(db, owner.id, session_id)
    return Response(status_code=204)


@router.post("/sessions/revoke-others", response_model=MessageResponse)
def revoke_others(request: Request, owner: CurrentOwner, db: DbSession):
    revoked = auth_service.revoke_other_sessions(
        db, owner.id, getattr(request.state, "session_id", None)
    )
    return MessageResponse(message=f"Revoked {revoked} other session(s).")


@router.get("/export")
def export_data(owner: CurrentOwner, db: DbSession):
    payload = auth_service.export_data(db, owner)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="careeros-export.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/delete-account", status_code=204)
def delete_account(
    payload: DeleteAccountRequest, response: Response, owner: CurrentOwner, db: DbSession
):
    auth_service.delete_account(
        db, owner, password=payload.password, confirmation=payload.confirmation
    )
    clear_auth_cookies(response)
    return Response(status_code=204)


@router.get("/meta", response_model=MetaResponse)
def meta(db: DbSession):
    from app.repositories import owner as owner_repo

    settings = get_settings()
    return MetaResponse(
        app_name=settings.app_name,
        owner_configured=owner_repo.owner_exists(db),
        ai_configured=settings.ai_configured,
        environment=settings.careeros_env,
        version="0.1.0",
    )
