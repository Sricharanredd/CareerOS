from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.enums import (
    FollowUpChannel,
    FollowUpStatus,
    InterviewOutcome,
    InterviewType,
    TaskPriority,
    TaskStatus,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """The database stores naive UTC; accept offset-aware input and normalise it."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class ApplicationRef(BaseModel):
    id: str
    title: str
    company_name: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=20_000)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: Literal[TaskStatus.TODO, TaskStatus.IN_PROGRESS] = TaskStatus.TODO
    due_on: date | None = None
    application_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=20_000)
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    due_on: date | None = None
    application_id: str | None = None


class TaskCompleteRequest(BaseModel):
    completed: bool = True


class TaskView(BaseModel):
    id: str
    title: str
    description: str | None
    priority: TaskPriority
    status: TaskStatus
    due_on: date | None
    completed_at: datetime | None
    is_overdue: bool
    application: ApplicationRef | None
    created_at: datetime
    updated_at: datetime


class FollowUpCreate(BaseModel):
    application_id: str
    due_on: date
    channel: FollowUpChannel = FollowUpChannel.EMAIL
    notes: str | None = Field(default=None, max_length=2000)


class FollowUpUpdate(BaseModel):
    due_on: date | None = None
    channel: FollowUpChannel | None = None
    status: FollowUpStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class FollowUpView(BaseModel):
    id: str
    application: ApplicationRef
    due_on: date
    channel: FollowUpChannel
    status: FollowUpStatus
    done_at: datetime | None
    is_overdue: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class InterviewCreate(BaseModel):
    application_id: str
    round_no: int | None = Field(default=None, ge=1, le=99)
    type: InterviewType = InterviewType.VIDEO
    scheduled_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    interviewer: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    link: str | None = Field(default=None, max_length=1000)
    prep_notes: str | None = Field(default=None, max_length=20_000)

    @field_validator("scheduled_at")
    @classmethod
    def _normalise_scheduled(cls, value: datetime) -> datetime:
        return _as_utc(value) or value


class InterviewUpdate(BaseModel):
    round_no: int | None = Field(default=None, ge=1, le=99)
    type: InterviewType | None = None
    scheduled_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    interviewer: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    link: str | None = Field(default=None, max_length=1000)
    prep_notes: str | None = Field(default=None, max_length=20_000)
    outcome: InterviewOutcome | None = None
    feedback: str | None = Field(default=None, max_length=20_000)

    @field_validator("scheduled_at")
    @classmethod
    def _normalise_scheduled(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class InterviewView(BaseModel):
    id: str
    application: ApplicationRef
    round_no: int
    type: InterviewType
    scheduled_at: datetime
    timezone: str
    interviewer: str | None
    location: str | None
    link: str | None
    prep_notes: str | None
    outcome: InterviewOutcome
    feedback: str | None
    is_upcoming: bool
    created_at: datetime
    updated_at: datetime


class TimeEntryCreate(BaseModel):
    started_at: datetime
    ended_at: datetime | None = None
    task_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("started_at")
    @classmethod
    def _normalise_start(cls, value: datetime) -> datetime:
        return _as_utc(value) or value

    @field_validator("ended_at")
    @classmethod
    def _normalise_end(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _ordered(self) -> TimeEntryCreate:
        if self.ended_at is not None and self.ended_at <= self.started_at:
            raise ValueError("The end time must be after the start time.")
        return self


class TimeEntryUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    task_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("started_at")
    @classmethod
    def _normalise_start(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @field_validator("ended_at")
    @classmethod
    def _normalise_end(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)

    @model_validator(mode="after")
    def _ordered(self) -> TimeEntryUpdate:
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at <= self.started_at
        ):
            raise ValueError("The end time must be after the start time.")
        return self


class TimeEntryView(BaseModel):
    id: str
    task_id: str | None
    task_title: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_minutes: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
