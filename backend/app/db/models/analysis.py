from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utcnow
from app.db.base import Base, TimestampMixin, UuidPkMixin, enum_column, timestamp_column
from app.db.enums import AnalysisStatus
from app.db.models.job import JobDescription
from app.db.models.resume import ResumeVersion


class AnalysisJob(UuidPkMixin, TimestampMixin, Base):
    """Persistent asynchronous job. `input_hash` makes submissions idempotent."""

    __tablename__ = "analysis_job"
    __table_args__ = (
        Index("ix_analysis_job_owner_status", "owner_id", "status"),
        Index("ix_analysis_job_resume_version", "resume_version_id"),
        Index("ix_analysis_job_jd", "jd_id"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    resume_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resume_version.id", ondelete="CASCADE"), nullable=False
    )
    jd_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_description.id", ondelete="SET NULL")
    )
    jd_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, deferred=True)
    jd_text_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[AnalysisStatus] = mapped_column(
        enum_column(AnalysisStatus, length=16),
        nullable=False,
        default=AnalysisStatus.QUEUED,
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    finished_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    resume_version: Mapped[ResumeVersion] = relationship(ResumeVersion, lazy="joined")
    job_description: Mapped[JobDescription | None] = relationship(JobDescription, lazy="joined")
    result: Mapped[AnalysisResult | None] = relationship(
        "AnalysisResult",
        back_populates="job",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AnalysisResult(UuidPkMixin, Base):
    __tablename__ = "analysis_result"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_analysis_result_job", "job_id"),
    )

    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_job.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    alignment_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    findings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(LONGTEXT)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)

    job: Mapped[AnalysisJob] = relationship("AnalysisJob", back_populates="result")
