"""Aggregate queries for the dashboard. Every number originates in MySQL."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, literal_column, select, text
from sqlalchemy.orm import Session

from app.db.enums import (
    ApplicationStatus,
    EventType,
    FollowUpStatus,
    InterviewOutcome,
    TaskStatus,
)
from app.db.models import (
    Application,
    ApplicationEvent,
    Company,
    FollowUp,
    Interview,
    Task,
)

RESPONSE_STATUSES = (
    ApplicationStatus.SCREENING,
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.ACCEPTED,
    ApplicationStatus.REJECTED,
)
INTERVIEW_STATUSES = (
    ApplicationStatus.INTERVIEWING,
    ApplicationStatus.OFFER,
    ApplicationStatus.ACCEPTED,
)
OFFER_STATUSES = (ApplicationStatus.OFFER, ApplicationStatus.ACCEPTED)


def status_counts(db: Session, owner_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.owner_id == owner_id, Application.archived_at.is_(None))
        .group_by(Application.status)
    ).all()
    return {str(status): int(count) for status, count in rows}


def totals(db: Session, owner_id: str) -> tuple[int, int, int]:
    total = (
        db.scalar(select(func.count(Application.id)).where(Application.owner_id == owner_id)) or 0
    )
    active = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id, Application.archived_at.is_(None)
            )
        )
        or 0
    )
    return int(total), int(active), int(total) - int(active)


def company_counts(db: Session, owner_id: str, *, limit: int = 6) -> list[tuple[str, str, int]]:
    rows = db.execute(
        select(Company.id, Company.name, func.count(Application.id))
        .join(Application, Application.company_id == Company.id)
        .where(Application.owner_id == owner_id, Application.archived_at.is_(None))
        .group_by(Company.id, Company.name)
        .order_by(func.count(Application.id).desc(), Company.name.asc())
        .limit(limit)
    ).all()
    return [(str(cid), str(name), int(count)) for cid, name, count in rows]


def conversions(db: Session, owner_id: str) -> dict[str, int]:
    submitted = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id, Application.applied_on.is_not(None)
            )
        )
        or 0
    )

    change_exists = exists().where(
        ApplicationEvent.application_id == Application.id,
        ApplicationEvent.type == EventType.STATUS_CHANGE,
    )
    responded = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id,
                Application.applied_on.is_not(None),
                Application.status.in_(RESPONSE_STATUSES) | change_exists,
            )
        )
        or 0
    )

    interview_exists = exists().where(Interview.application_id == Application.id)
    interviewed = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id,
                Application.applied_on.is_not(None),
                Application.status.in_(INTERVIEW_STATUSES) | interview_exists,
            )
        )
        or 0
    )

    offered = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id,
                Application.applied_on.is_not(None),
                Application.status.in_(OFFER_STATUSES) | Application.offer_amount.is_not(None),
            )
        )
        or 0
    )

    offered_without_applied_on = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id,
                Application.applied_on.is_(None),
                Application.status.in_(OFFER_STATUSES) | Application.offer_amount.is_not(None),
            )
        )
        or 0
    )

    return {
        "submitted": int(submitted),
        "responded": int(responded),
        "interviewed": int(interviewed),
        "offered": int(offered),
        "offered_unsubmitted": int(offered_without_applied_on),
    }


def follow_up_summary(db: Session, owner_id: str) -> dict[str, int]:
    today = date.today()
    base = (
        select(func.count(FollowUp.id))
        .join(Application, FollowUp.application_id == Application.id)
        .where(Application.owner_id == owner_id)
    )

    due_today = (
        db.scalar(base.where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on == today))
        or 0
    )
    overdue = (
        db.scalar(base.where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on < today))
        or 0
    )
    upcoming = (
        db.scalar(base.where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on > today))
        or 0
    )
    completed = db.scalar(base.where(FollowUp.status == FollowUpStatus.DONE)) or 0
    return {
        "due_today": int(due_today),
        "overdue": int(overdue),
        "upcoming": int(upcoming),
        "completed": int(completed),
    }


def task_summary(db: Session, owner_id: str) -> dict[str, int]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    base = select(func.count(Task.id)).where(Task.owner_id == owner_id)

    pending = db.scalar(base.where(Task.status != TaskStatus.DONE)) or 0
    overdue = db.scalar(base.where(Task.status != TaskStatus.DONE, Task.due_on < today)) or 0
    due_today = db.scalar(base.where(Task.status != TaskStatus.DONE, Task.due_on == today)) or 0
    completed = (
        db.scalar(base.where(Task.status == TaskStatus.DONE, Task.completed_at >= week_start)) or 0
    )
    return {
        "pending": int(pending),
        "overdue": int(overdue),
        "due_today": int(due_today),
        "completed_this_week": int(completed),
    }


def upcoming_interviews(
    db: Session, owner_id: str, *, now: datetime, limit: int = 5
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Interview.id,
            Interview.application_id,
            Application.title,
            Company.name,
            Interview.round_no,
            Interview.type,
            Interview.scheduled_at,
            Interview.timezone,
        )
        .join(Application, Interview.application_id == Application.id)
        .join(Company, Application.company_id == Company.id)
        .where(
            Application.owner_id == owner_id,
            Interview.scheduled_at >= now,
            Interview.outcome == InterviewOutcome.PENDING,
        )
        .order_by(Interview.scheduled_at.asc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row[0],
            "application_id": row[1],
            "application_title": row[2],
            "company_name": row[3],
            "round_no": row[4],
            "type": str(row[5]),
            "scheduled_at": row[6],
            "timezone": row[7],
        }
        for row in rows
    ]


def interviews_scheduled(db: Session, owner_id: str, *, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count(Interview.id))
            .join(Application, Interview.application_id == Application.id)
            .where(
                Application.owner_id == owner_id,
                Interview.scheduled_at >= now,
                Interview.outcome == InterviewOutcome.PENDING,
            )
        )
        or 0
    )


def recent_activity(db: Session, owner_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            ApplicationEvent.id,
            ApplicationEvent.application_id,
            Application.title,
            Company.name,
            ApplicationEvent.type,
            ApplicationEvent.from_status,
            ApplicationEvent.to_status,
            ApplicationEvent.created_at,
        )
        .join(Application, ApplicationEvent.application_id == Application.id)
        .join(Company, Application.company_id == Company.id)
        .where(Application.owner_id == owner_id)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row[0],
            "application_id": row[1],
            "application_title": row[2],
            "company_name": row[3],
            "type": str(row[4]),
            "from_status": row[5],
            "to_status": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]


def daily_applications(db: Session, owner_id: str, *, since: date) -> list[tuple[date, int]]:
    rows = db.execute(
        select(Application.applied_on, func.count(Application.id))
        .where(Application.owner_id == owner_id, Application.applied_on >= since)
        .group_by(Application.applied_on)
        .order_by(Application.applied_on.asc())
    ).all()
    return [(row[0], int(row[1])) for row in rows]


def applied_counts(db: Session, owner_id: str) -> tuple[int, int]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    this_week = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id, Application.applied_on >= week_start
            )
        )
        or 0
    )
    this_month = (
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id, Application.applied_on >= month_start
            )
        )
        or 0
    )
    return int(this_week), int(this_month)


def average_days_to_response(db: Session, owner_id: str) -> float | None:
    first_response = (
        select(
            ApplicationEvent.application_id.label("application_id"),
            func.min(ApplicationEvent.created_at).label("first_at"),
        )
        .where(
            ApplicationEvent.type == EventType.STATUS_CHANGE,
            ApplicationEvent.to_status.in_([str(s) for s in RESPONSE_STATUSES]),
        )
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )
    value = db.scalar(
        select(
            func.avg(
                func.timestampdiff(
                    literal_column("DAY"), Application.applied_on, first_response.c.first_at
                )
            )
        )
        .join(first_response, first_response.c.application_id == Application.id)
        .where(Application.owner_id == owner_id, Application.applied_on.is_not(None))
    )
    return float(value) if value is not None else None


def ai_ready(db: Session) -> bool:  # pragma: no cover - placeholder for phase 5 wiring
    return db.scalar(select(text("1"))) == 1
