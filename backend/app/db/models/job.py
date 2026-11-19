from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPkMixin, timestamp_column

if TYPE_CHECKING:
    from app.db.models.company import Company


class JobDescription(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "job_description"
    __table_args__ = (
        Index("ix_job_description_owner_created", "owner_id", "created_at"),
        Index("ix_job_description_company", "company_id"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    raw_text: Mapped[str] = mapped_column(LONGTEXT, nullable=False, default="", deferred=True)
    structured_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    seniority: Mapped[str | None] = mapped_column(String(64))
    employment_type: Mapped[str | None] = mapped_column(String(32))
    required_skills: Mapped[list[str] | None] = mapped_column(JSON)
    preferred_skills: Mapped[list[str] | None] = mapped_column(JSON)
    responsibilities: Mapped[list[str] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    source_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file_object.id", ondelete="SET NULL")
    )
    archived_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    company: Mapped[Company] = relationship(back_populates="job_descriptions")
