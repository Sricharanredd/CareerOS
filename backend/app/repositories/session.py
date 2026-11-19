from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_token, utcnow
from app.db.models import AuthSession


def create_session(
    db: Session,
    *,
    owner_id: str,
    refresh_hash: str,
    family_id: str,
    expires_at: datetime,
    user_agent: str | None,
    ip: str | None,
) -> AuthSession:
    session = AuthSession(
        owner_id=owner_id,
        refresh_hash=refresh_hash,
        family_id=family_id,
        expires_at=expires_at,
        user_agent=(user_agent or "")[:512] or None,
        ip=(ip or "")[:45] or None,
        created_at=utcnow(),
    )
    db.add(session)
    db.flush()
    return session


def get_by_refresh_token(db: Session, raw_token: str) -> AuthSession | None:
    return db.scalar(select(AuthSession).where(AuthSession.refresh_hash == hash_token(raw_token)))


def get_by_id(db: Session, session_id: str) -> AuthSession | None:
    return db.get(AuthSession, session_id)


def touch(db: Session, session: AuthSession) -> None:
    session.last_used_at = utcnow()


def revoke(db: Session, session: AuthSession, *, replaced_by: str | None = None) -> None:
    session.revoked_at = utcnow()
    if replaced_by:
        session.replaced_by = replaced_by


def revoke_family(db: Session, family_id: str) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)


def revoke_owner_sessions(db: Session, owner_id: str, *, keep_id: str | None = None) -> int:
    stmt = update(AuthSession).where(
        AuthSession.owner_id == owner_id, AuthSession.revoked_at.is_(None)
    )
    if keep_id:
        stmt = stmt.where(AuthSession.id != keep_id)
    result = db.execute(stmt.values(revoked_at=utcnow()))
    return int(result.rowcount or 0)


def list_active(db: Session, owner_id: str) -> list[AuthSession]:
    now = utcnow()
    return list(
        db.scalars(
            select(AuthSession)
            .where(
                AuthSession.owner_id == owner_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.last_used_at.desc(), AuthSession.created_at.desc())
        )
    )


def purge_expired(db: Session, *, days: int = 30) -> int:
    cutoff = utcnow() - timedelta(days=days)
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at < cutoff)
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)
