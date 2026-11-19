from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
)
from app.core.ratelimit import SlidingWindowLimiter
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    needs_rehash,
    new_csrf_token,
    utcnow,
    verify_password,
)
from app.db.models import (
    AnalysisJob,
    AnalysisResult,
    Application,
    ApplicationEvent,
    AuthSession,
    Company,
    FollowUp,
    Interview,
    JobDescription,
    Owner,
    Resume,
    ResumeVersion,
    Task,
    TimeEntry,
)
from app.repositories import owner as owner_repo
from app.repositories import session as session_repo
from app.services import audit

GENERIC_LOGIN_ERROR = "Invalid email or password."

_limiter: SlidingWindowLimiter | None = None
_dummy_hash: str | None = None


def limiter() -> SlidingWindowLimiter:
    global _limiter
    settings = get_settings()
    if _limiter is None:
        _limiter = SlidingWindowLimiter(
            max_attempts=settings.login_max_attempts,
            window_seconds=settings.login_lockout_seconds,
            lockout_seconds=settings.login_lockout_seconds,
        )
    return _limiter


def reset_limiter() -> None:
    """Test helper."""
    if _limiter is not None:
        _limiter.clear()


@dataclass
class AuthResult:
    owner: Owner
    session_id: str
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    csrf_token: str


def _dummy_password_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-the-real-password-9f2b")
    return _dummy_hash


def login(
    db: Session, *, email: str, password: str, ip: str | None, user_agent: str | None
) -> AuthResult:
    key = f"{ip or '-'}|{email.strip().lower()}"
    retry_after = limiter().retry_after(key)
    if retry_after:
        raise RateLimitError(
            "Too many sign-in attempts. Try again shortly.",
            details={"retry_after_seconds": retry_after},
        )

    owner = owner_repo.get_by_email(db, email)
    stored_hash = owner.password_hash if owner else _dummy_password_hash()
    valid = verify_password(password, stored_hash)

    if owner is None or not valid:
        limiter().record_failure(key)
        raise UnauthorizedError(GENERIC_LOGIN_ERROR, code="invalid_credentials")

    limiter().reset(key)
    if needs_rehash(owner.password_hash):
        owner.password_hash = hash_password(password)
    owner.last_login_at = utcnow()
    db.flush()

    result = issue_session(db, owner, ip=ip, user_agent=user_agent)
    audit.record(db, owner_id=owner.id, action="auth.login", entity="session", entity_id=None)
    return result


def issue_session(
    db: Session,
    owner: Owner,
    *,
    ip: str | None,
    user_agent: str | None,
    family_id: str | None = None,
) -> AuthResult:
    settings = get_settings()
    import uuid

    raw_refresh, refresh_hash = generate_refresh_token()
    session = session_repo.create_session(
        db,
        owner_id=owner.id,
        refresh_hash=refresh_hash,
        family_id=family_id or str(uuid.uuid4()),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=user_agent,
        ip=ip,
    )
    access_token, expires_at = create_access_token(owner_id=owner.id, session_id=session.id)
    return AuthResult(
        owner=owner,
        session_id=session.id,
        access_token=access_token,
        access_expires_at=expires_at,
        refresh_token=raw_refresh,
        csrf_token=new_csrf_token(),
    )


def refresh(db: Session, *, raw_refresh: str, ip: str | None, user_agent: str | None) -> AuthResult:
    session = session_repo.get_by_refresh_token(db, raw_refresh)
    if session is None:
        raise UnauthorizedError("Session expired. Sign in again.", code="invalid_refresh")

    if session.revoked_at is not None:
        # Reuse of a rotated token: assume theft and burn the whole family.
        session_repo.revoke_family(db, session.family_id)
        audit.record(
            db,
            owner_id=session.owner_id,
            action="auth.refresh_reuse",
            entity="session",
            entity_id=session.id,
        )
        # Commit before failing: get_db() rolls back on exceptions, and a revoked
        # family that never reaches disk leaves the stolen token usable.
        db.commit()
        raise UnauthorizedError("Session expired. Sign in again.", code="token_reuse")

    if session.expires_at <= utcnow():
        session_repo.revoke(db, session)
        db.commit()
        raise UnauthorizedError("Session expired. Sign in again.", code="session_expired")

    owner = owner_repo.get_by_id(db, session.owner_id)
    if owner is None:
        raise UnauthorizedError("Session expired. Sign in again.", code="invalid_owner")

    session_repo.touch(db, session)
    result = issue_session(db, owner, ip=ip, user_agent=user_agent, family_id=session.family_id)
    session_repo.revoke(db, session, replaced_by=result.session_id)
    db.flush()
    return result


def logout(db: Session, raw_refresh: str | None) -> None:
    if not raw_refresh:
        return
    session = session_repo.get_by_refresh_token(db, raw_refresh)
    if session is not None and session.revoked_at is None:
        session_repo.revoke(db, session)
        audit.record(
            db,
            owner_id=session.owner_id,
            action="auth.logout",
            entity="session",
            entity_id=session.id,
        )


def list_sessions(db: Session, owner_id: str, current_session_id: str) -> list[AuthSession]:
    return session_repo.list_active(db, owner_id)


def revoke_session(db: Session, owner_id: str, session_id: str) -> None:
    session = session_repo.get_by_id(db, session_id)
    if session is None or session.owner_id != owner_id:
        raise NotFoundError("Session not found.")
    if session.revoked_at is None:
        session_repo.revoke(db, session)


def revoke_other_sessions(db: Session, owner_id: str, current_session_id: str | None) -> int:
    return session_repo.revoke_owner_sessions(db, owner_id, keep_id=current_session_id)


def change_password(
    db: Session, owner: Owner, *, current_password: str, new_password: str, current_session_id: str
) -> None:
    if not verify_password(current_password, owner.password_hash):
        raise ForbiddenError("Current password is incorrect.", code="invalid_password")
    if verify_password(new_password, owner.password_hash):
        raise ConflictError("Choose a password you have not used before.", code="password_reused")
    owner.password_hash = hash_password(new_password)
    session_repo.revoke_owner_sessions(db, owner.id, keep_id=current_session_id)
    audit.record(
        db, owner_id=owner.id, action="auth.password_change", entity="owner", entity_id=owner.id
    )
    db.flush()


def create_owner(db: Session, *, email: str, password: str, full_name: str | None) -> Owner:
    if owner_repo.owner_exists(db):
        raise ConflictError(
            "An owner account already exists. Use the CLI 'reset-password' command if needed.",
            code="owner_exists",
        )
    owner = owner_repo.create_owner(
        db,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
    )
    audit.record(
        db, owner_id=owner.id, action="owner.bootstrap", entity="owner", entity_id=owner.id
    )
    db.flush()
    return owner


def reset_password(db: Session, *, email: str, new_password: str) -> Owner:
    owner = owner_repo.get_by_email(db, email)
    if owner is None:
        raise NotFoundError("No owner account with that email.")
    owner.password_hash = hash_password(new_password)
    session_repo.revoke_owner_sessions(db, owner.id)
    audit.record(
        db, owner_id=owner.id, action="auth.password_reset", entity="owner", entity_id=owner.id
    )
    db.flush()
    return owner


def delete_account(db: Session, owner: Owner, *, password: str, confirmation: str) -> None:
    from app.services import storage

    if not verify_password(password, owner.password_hash):
        raise ForbiddenError("Password is incorrect.", code="invalid_password")
    if confirmation != "DELETE":
        raise ConflictError(
            "Type DELETE exactly to confirm account deletion.", code="confirmation_mismatch"
        )

    from app.db.models import FileObject

    files = list(db.scalars(select(FileObject).where(FileObject.owner_id == owner.id)))
    db.delete(owner)
    db.flush()
    for file_object in files:
        storage.delete_file(file_object)


# ------------------------------------------------------------------- export
def _rows(db: Session, model, owner_filter=None) -> list[dict]:
    from sqlalchemy import inspect as sa_inspect

    stmt = select(model)
    if owner_filter is not None:
        stmt = stmt.where(owner_filter)
    columns = [column.key for column in sa_inspect(model).columns]
    output: list[dict] = []
    for row in db.scalars(stmt).all():
        entry: dict = {}
        for key in columns:
            value = getattr(row, key)
            if isinstance(value, datetime):
                entry[key] = value.isoformat()
            elif isinstance(value, str) or value is None or isinstance(value, int | float):
                entry[key] = value
            else:
                entry[key] = str(value)
        output.append(entry)
    return output


def export_data(db: Session, owner: Owner) -> dict:
    owner_id = owner.id
    companies = _rows(db, Company, Company.owner_id == owner_id)
    jds = _rows(db, JobDescription, JobDescription.owner_id == owner_id)
    resumes = _rows(db, Resume, Resume.owner_id == owner_id)
    versions = list(
        db.scalars(
            select(ResumeVersion)
            .join(Resume, ResumeVersion.resume_id == Resume.id)
            .where(Resume.owner_id == owner_id)
        ).all()
    )
    version_dicts = [
        {
            "id": v.id,
            "resume_id": v.resume_id,
            "version_no": v.version_no,
            "label": v.label,
            "notes": v.notes,
            "created_at": v.created_at.isoformat(),
            "extracted_chars": len(v.extracted_text or ""),
        }
        for v in versions
    ]
    applications = _rows(db, Application, Application.owner_id == owner_id)
    app_ids = [a["id"] for a in applications]
    events = (
        _rows(db, ApplicationEvent, ApplicationEvent.application_id.in_(app_ids)) if app_ids else []
    )
    interviews = _rows(db, Interview, Interview.application_id.in_(app_ids)) if app_ids else []
    follow_ups = _rows(db, FollowUp, FollowUp.application_id.in_(app_ids)) if app_ids else []
    tasks = _rows(db, Task, Task.owner_id == owner_id)
    time_entries = _rows(db, TimeEntry, TimeEntry.owner_id == owner_id)
    jobs = _rows(db, AnalysisJob, AnalysisJob.owner_id == owner_id)
    job_ids = [j["id"] for j in jobs]
    results = _rows(db, AnalysisResult, AnalysisResult.job_id.in_(job_ids)) if job_ids else []

    return {
        "exported_at": utcnow().isoformat(),
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "full_name": owner.full_name,
            "timezone": owner.timezone,
            "currency": owner.currency,
            "theme": str(owner.theme),
            "created_at": owner.created_at.isoformat(),
        },
        "companies": companies,
        "job_descriptions": jds,
        "resumes": resumes,
        "resume_versions": version_dicts,
        "applications": applications,
        "application_events": events,
        "interviews": interviews,
        "follow_ups": follow_ups,
        "tasks": tasks,
        "time_entries": time_entries,
        "analysis_jobs": jobs,
        "analysis_results": results,
        "counts": {
            "companies": len(companies),
            "job_descriptions": len(jds),
            "resumes": len(resumes),
            "resume_versions": len(version_dicts),
            "applications": len(applications),
            "application_events": len(events),
            "interviews": len(interviews),
            "follow_ups": len(follow_ups),
            "tasks": len(tasks),
            "time_entries": len(time_entries),
            "analysis_jobs": len(jobs),
            "analysis_results": len(results),
        },
    }
