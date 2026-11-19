from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utcnow
from app.db.base import Base, UuidPkMixin, timestamp_column

if TYPE_CHECKING:
    from app.db.models.files import FileObject


class Resume(UuidPkMixin, Base):
    __tablename__ = "resume"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_resume_owner_id_name"),
        Index("ix_resume_owner_archived", "owner_id", "archived_at"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(250))
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "resume_version.id",
            use_alter=True,
            name="fk_resume_current_version",
            ondelete="SET NULL",
        ),
    )
    archived_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        timestamp_column(), nullable=False, default=utcnow, onupdate=utcnow
    )

    versions: Mapped[list[ResumeVersion]] = relationship(
        back_populates="resume",
        foreign_keys="ResumeVersion.resume_id",
        order_by="ResumeVersion.version_no.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    current_version: Mapped[ResumeVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )


class ResumeVersion(UuidPkMixin, Base):
    """Immutable. A new upload always creates a new version."""

    __tablename__ = "resume_version"
    __table_args__ = (
        UniqueConstraint("resume_id", "version_no", name="uq_resume_version_resume_id_version_no"),
        Index("ix_resume_version_resume", "resume_id"),
    )

    resume_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resume.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_object.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    extracted_text: Mapped[str] = mapped_column(LONGTEXT, nullable=False, default="", deferred=True)
    notes: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)

    resume: Mapped[Resume] = relationship(back_populates="versions", foreign_keys=[resume_id])
    file: Mapped[FileObject] = relationship(foreign_keys=[file_id])
