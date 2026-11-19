from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPkMixin, enum_column, timestamp_column
from app.db.enums import (
    FollowUpChannel,
    FollowUpStatus,
    InterviewOutcome,
    InterviewType,
    TaskPriority,
    TaskStatus,
)

if TYPE_CHECKING:
    from app.db.models.application import Application


class Interview(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "interview"
    __table_args__ = (
        Index("ix_interview_application", "application_id"),
        Index("ix_interview_scheduled", "scheduled_at"),
    )

    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    type: Mapped[InterviewType] = mapped_column(
        enum_column(InterviewType),
        nullable=False,
        default=InterviewType.VIDEO,
    )
    scheduled_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    interviewer: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))
    link: Mapped[str | None] = mapped_column(String(1000))
    prep_notes: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    outcome: Mapped[InterviewOutcome] = mapped_column(
        enum_column(InterviewOutcome, length=16),
        nullable=False,
        default=InterviewOutcome.PENDING,
    )
    feedback: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="interviews")


class FollowUp(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "follow_up"
    __table_args__ = (
        Index("ix_follow_up_application", "application_id"),
        Index("ix_follow_up_status_due", "status", "due_on"),
        CheckConstraint("status <> 'done' OR done_at IS NOT NULL", name="done_requires_timestamp"),
    )

    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("application.id", ondelete="CASCADE"), nullable=False
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[FollowUpChannel] = mapped_column(
        enum_column(FollowUpChannel, length=16),
        nullable=False,
        default=FollowUpChannel.EMAIL,
    )
    status: Mapped[FollowUpStatus] = mapped_column(
        enum_column(FollowUpStatus, length=16),
        nullable=False,
        default=FollowUpStatus.PENDING,
    )
    done_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    notes: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="follow_ups")


class Task(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "task"
    __table_args__ = (
        Index("ix_task_owner_status_due", "owner_id", "status", "due_on"),
        CheckConstraint(
            "status <> 'done' OR completed_at IS NOT NULL", name="done_requires_completed_at"
        ),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("application.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(MEDIUMTEXT)
    priority: Mapped[TaskPriority] = mapped_column(
        enum_column(TaskPriority, length=16),
        nullable=False,
        default=TaskPriority.MEDIUM,
    )
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, length=16),
        nullable=False,
        default=TaskStatus.TODO,
    )
    due_on: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    application: Mapped[Application | None] = relationship()


class TimeEntry(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "time_entry"
    __table_args__ = (
        Index("ix_time_entry_owner_started", "owner_id", "started_at"),
        Index("ix_time_entry_task", "task_id"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ended_after_started"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("task.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(timestamp_column())
    notes: Mapped[str | None] = mapped_column(Text)

    task: Mapped[Task | None] = relationship()
