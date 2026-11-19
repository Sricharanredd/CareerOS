from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utcnow
from app.db.base import Base, TimestampMixin, UuidPkMixin, enum_column, timestamp_column
from app.db.enums import Theme


class Owner(UuidPkMixin, TimestampMixin, Base):
    """Exactly one row exists. Created only by `python -m app.cli bootstrap-owner`."""

    __tablename__ = "owner"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    theme: Mapped[Theme] = mapped_column(
        enum_column(Theme, length=16),
        nullable=False,
        default=Theme.SYSTEM,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class AuthSession(UuidPkMixin, Base):
    """One row per issued refresh token. Rotation revokes the old row."""

    __tablename__ = "session"
    __table_args__ = (
        Index("ix_session_owner_family", "owner_id", "family_id"),
        Index("ix_session_expires_at", "expires_at"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip: Mapped[str | None] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    replaced_by: Mapped[str | None] = mapped_column(String(36))
    last_used_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)

    owner: Mapped[Owner] = relationship(back_populates="sessions")


class AuditLog(UuidPkMixin, Base):
    """No payload and no free text: sensitive content must never reach this table."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_owner_created", "owner_id", "created_at"),)

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)
