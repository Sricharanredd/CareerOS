"""Queries for tasks, follow-ups, interviews and time entries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.enums import FollowUpStatus, InterviewOutcome, TaskStatus
from app.db.models import Application, FollowUp, Interview, Task, TimeEntry
from app.repositories.base import paginate


def _application_path(relationship: Any) -> Any:
    return joinedload(relationship).joinedload(Application.company)


# --- tasks -----------------------------------------------------------------


def get_task(db: Session, owner_id: str, task_id: str) -> Task | None:
    return db.scalar(
        select(Task)
        .options(_application_path(Task.application))
        .where(Task.id == task_id, Task.owner_id == owner_id)
    )


def list_tasks(
    db: Session,
    owner_id: str,
    *,
    bucket: str,
    status: TaskStatus | None,
    priority: str | None,
    application_id: str | None,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Task], int]:
    today = date.today()
    clauses: list[Any] = [Task.owner_id == owner_id]
    if bucket == "today":
        clauses += [Task.status != TaskStatus.DONE, Task.due_on == today]
    elif bucket == "overdue":
        clauses += [Task.status != TaskStatus.DONE, Task.due_on < today]
    elif bucket == "upcoming":
        clauses += [Task.status != TaskStatus.DONE, Task.due_on > today]
    elif bucket == "open":
        clauses.append(Task.status != TaskStatus.DONE)
    elif bucket == "completed":
        clauses.append(Task.status == TaskStatus.DONE)
    if status:
        clauses.append(Task.status == status)
    if priority:
        clauses.append(Task.priority == priority)
    if application_id:
        clauses.append(Task.application_id == application_id)
    if search:
        like = f"%{search.strip()}%"
        clauses.append(or_(Task.title.like(like), Task.description.like(like)))

    stmt = (
        select(Task)
        .options(_application_path(Task.application))
        .where(*clauses)
        .order_by(
            case((Task.status == TaskStatus.DONE, 1), else_=0).asc(),
            Task.due_on.is_(None).asc(),
            Task.due_on.asc(),
            Task.created_at.desc(),
        )
    )
    return paginate(db, stmt, page=page, page_size=page_size)


# --- follow-ups ------------------------------------------------------------


def get_follow_up(db: Session, owner_id: str, follow_up_id: str) -> FollowUp | None:
    return db.scalar(
        select(FollowUp)
        .join(Application, FollowUp.application_id == Application.id)
        .options(joinedload(FollowUp.application).joinedload(Application.company))
        .where(FollowUp.id == follow_up_id, Application.owner_id == owner_id)
    )


def list_follow_ups(
    db: Session,
    owner_id: str,
    *,
    scope: str,
    status: FollowUpStatus | None,
    application_id: str | None,
    page: int,
    page_size: int,
) -> tuple[list[FollowUp], int]:
    today = date.today()
    clauses: list[Any] = [Application.owner_id == owner_id]
    if scope == "overdue":
        clauses += [FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on < today]
    elif scope == "today":
        clauses += [FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on == today]
    elif scope == "upcoming":
        clauses += [FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on > today]
    elif scope == "open":
        clauses.append(FollowUp.status == FollowUpStatus.PENDING)
    elif scope == "done":
        clauses.append(FollowUp.status == FollowUpStatus.DONE)
    if status:
        clauses.append(FollowUp.status == status)
    if application_id:
        clauses.append(FollowUp.application_id == application_id)

    stmt = (
        select(FollowUp)
        .join(Application, FollowUp.application_id == Application.id)
        .options(joinedload(FollowUp.application).joinedload(Application.company))
        .where(*clauses)
        .order_by(
            case((FollowUp.status == FollowUpStatus.PENDING, 0), else_=1).asc(),
            FollowUp.due_on.asc(),
        )
    )
    return paginate(db, stmt, page=page, page_size=page_size)


# --- interviews ------------------------------------------------------------


def get_interview(db: Session, owner_id: str, interview_id: str) -> Interview | None:
    return db.scalar(
        select(Interview)
        .join(Application, Interview.application_id == Application.id)
        .options(joinedload(Interview.application).joinedload(Application.company))
        .where(Interview.id == interview_id, Application.owner_id == owner_id)
    )


def list_interviews(
    db: Session,
    owner_id: str,
    *,
    scope: str,
    application_id: str | None,
    outcome: InterviewOutcome | None,
    now: datetime,
    page: int,
    page_size: int,
) -> tuple[list[Interview], int]:
    clauses: list[Any] = [Application.owner_id == owner_id]
    if scope == "upcoming":
        clauses.append(Interview.scheduled_at >= now)
    elif scope == "past":
        clauses.append(Interview.scheduled_at < now)
    if application_id:
        clauses.append(Interview.application_id == application_id)
    if outcome:
        clauses.append(Interview.outcome == outcome)

    ordering = (
        Interview.scheduled_at.asc() if scope == "upcoming" else Interview.scheduled_at.desc()
    )
    stmt = (
        select(Interview)
        .join(Application, Interview.application_id == Application.id)
        .options(joinedload(Interview.application).joinedload(Application.company))
        .where(*clauses)
        .order_by(ordering)
    )
    return paginate(db, stmt, page=page, page_size=page_size)


def next_round(db: Session, application_id: str) -> int:
    current = db.scalar(
        select(func.max(Interview.round_no)).where(Interview.application_id == application_id)
    )
    return int(current or 0) + 1


def interview_counts(db: Session, owner_id: str, *, now: datetime) -> dict[str, int]:
    base = (
        select(func.count(Interview.id))
        .join(Application, Interview.application_id == Application.id)
        .where(Application.owner_id == owner_id)
    )
    return {
        "total": int(db.scalar(base) or 0),
        "upcoming": int(
            db.scalar(
                base.where(
                    Interview.scheduled_at >= now,
                    Interview.outcome == InterviewOutcome.PENDING,
                )
            )
            or 0
        ),
        "pending_outcome": int(
            db.scalar(base.where(Interview.outcome == InterviewOutcome.PENDING)) or 0
        ),
        "passed": int(db.scalar(base.where(Interview.outcome == InterviewOutcome.PASSED)) or 0),
        "failed": int(db.scalar(base.where(Interview.outcome == InterviewOutcome.FAILED)) or 0),
    }


# --- time entries ----------------------------------------------------------


def get_time_entry(db: Session, owner_id: str, entry_id: str) -> TimeEntry | None:
    return db.scalar(
        select(TimeEntry)
        .options(joinedload(TimeEntry.task))
        .where(TimeEntry.id == entry_id, TimeEntry.owner_id == owner_id)
    )


def list_time_entries(
    db: Session,
    owner_id: str,
    *,
    task_id: str | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[TimeEntry], int]:
    clauses: list[Any] = [TimeEntry.owner_id == owner_id]
    if task_id:
        clauses.append(TimeEntry.task_id == task_id)
    if date_from:
        clauses.append(TimeEntry.started_at >= date_from)
    if date_to:
        clauses.append(TimeEntry.started_at < date_to)

    stmt = (
        select(TimeEntry)
        .options(joinedload(TimeEntry.task))
        .where(*clauses)
        .order_by(TimeEntry.started_at.desc())
    )
    return paginate(db, stmt, page=page, page_size=page_size)


def overlapping_entry(
    db: Session,
    owner_id: str,
    *,
    task_id: str,
    started_at: datetime,
    ended_at: datetime | None,
    exclude_id: str | None = None,
) -> TimeEntry | None:
    clauses: list[Any] = [
        TimeEntry.owner_id == owner_id,
        TimeEntry.task_id == task_id,
        or_(TimeEntry.ended_at.is_(None), TimeEntry.ended_at > started_at),
    ]
    if ended_at is not None:
        clauses.append(TimeEntry.started_at < ended_at)
    if exclude_id:
        clauses.append(TimeEntry.id != exclude_id)
    return db.scalar(select(TimeEntry).where(*clauses).limit(1))
