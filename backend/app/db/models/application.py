from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utcnow
from app.db.base import Base, TimestampMixin, UuidPkMixin, enum_column, timestamp_column
from app.db.enums import (
    ApplicationStatus,
    EmploymentType,
    EventType,
    SalaryPeriod,
    WorkMode,
)

if TYPE_CHECKING:
    from app.db.models.company import Company
    from app.db.models.job import JobDescription
    from app.db.models.productivity import FollowUp, Interview
    from app.db.models.resume import ResumeVersion


class Application(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "application"
    __table_args__ = (
        Index("ix_application_owner_status", "owner_id", "status"),
        Index("ix_application_owner_applied_on", "owner_id", "applied_on"),
        Index("ix_application_company", "company_id"),
        Index("ix_application_jd", "jd_id"),
        Index("ix_application_follow_up", "owner_id", "follow_up_on"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_ordered",
        ),
        CheckConstraint(
            "(salary_min IS NULL OR salary_min >= 0) AND (salary_max IS NULL OR salary_max >= 0)",
            name="salary_non_negative",
        ),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=False
    )
    jd_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_description.id", ondelete="SET NULL")
    )
    resume_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resume_version.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    employment_type: Mapped[EmploymentType | None] = mapped_column(enum_column(EmploymentType))
    work_mode: Mapped[WorkMode | None] = mapped_column(enum_column(WorkMode, length=16))
    job_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus),
        nullable=False,
        default=ApplicationStatus.SAVED,
    )
    applied_on: Mapped[date | None] = mapped_column(Date)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(enum_column(SalaryPeriod, length=16))
    source: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    rejection_reason: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    offer_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    offer_deadline: Mapped[date | None] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    company: Mapped[Company] = relationship(back_populates="applications")
    job_description: Mapped[JobDescription | None] = relationship()
    resume_version: Mapped[ResumeVersion | None] = relationship()
    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application",
        order_by="ApplicationEvent.created_at.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    interviews: Mapped[list[Interview]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )
    follow_ups: Mapped[list[FollowUp]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )


class ApplicationEvent(UuidPkMixin, Base):
    """Append-only timeline. One row per meaningful change."""

    __tablename__ = "application_event"
    __table_args__ = (
        Index("ix_application_event_application_created", "application_id", "created_at"),
    )

    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[EventType] = mapped_column(enum_column(EventType), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)

    application: Mapped[Application] = relationship(back_populates="events")
