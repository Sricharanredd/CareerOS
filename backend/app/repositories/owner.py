from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Owner


def owner_exists(db: Session) -> bool:
    return db.scalar(select(Owner.id).limit(1)) is not None


def get_owner(db: Session) -> Owner | None:
    return db.scalar(select(Owner).limit(1))


def get_by_id(db: Session, owner_id: str) -> Owner | None:
    return db.get(Owner, owner_id)


def get_by_email(db: Session, email: str) -> Owner | None:
    return db.scalar(select(Owner).where(Owner.email == email))


def create_owner(db: Session, *, email: str, password_hash: str, full_name: str | None) -> Owner:
    owner = Owner(email=email.lower().strip(), password_hash=password_hash, full_name=full_name)
    db.add(owner)
    db.flush()
    return owner
