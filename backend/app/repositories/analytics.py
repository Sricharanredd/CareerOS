"""Analytics aggregates. Every value is derived from stored rows; nothing is mocked."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import AnalysisStatus, FollowUpStatus, TaskStatus
from app.db.models import (
    AnalysisJob,
    AnalysisResult,
    Application,
    FollowUp,
    JobDescription,
    Resume,
    ResumeVersion,
    Task,
    TimeEntry,
)


def by_source(db: Session, owner_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Application.source, func.count(Application.id))
        .where(
            Application.owner_id == owner_id,
            Application.archived_at.is_(None),
            Application.source.is_not(None),
            Application.source != "",
        )
        .group_by(Application.source)
        .order_by(func.count(Application.id).desc(), Application.source.asc())
    ).all()
    return [{"source": str(source), "count": int(count)} for source, count in rows]


def submitted(db: Session, owner_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.owner_id == owner_id, Application.applied_on.is_not(None)
            )
        )
        or 0
    )


def follow_up_performance(db: Session, owner_id: str, *, today: date) -> dict[str, int]:
    base = (
        select(func.count(FollowUp.id))
        .join(Application, FollowUp.application_id == Application.id)
        .where(Application.owner_id == owner_id)
    )
    due = base.where(FollowUp.due_on <= today)
    return {
        "total_due": int(db.scalar(due) or 0),
        "completed_on_time": int(
            db.scalar(
                due.where(
                    FollowUp.status == FollowUpStatus.DONE,
                    FollowUp.done_at.is_not(None),
                    func.date(FollowUp.done_at) <= FollowUp.due_on,
                )
            )
            or 0
        ),
        "completed": int(db.scalar(base.where(FollowUp.status == FollowUpStatus.DONE)) or 0),
        "skipped": int(db.scalar(base.where(FollowUp.status == FollowUpStatus.SKIPPED)) or 0),
        "pending": int(db.scalar(base.where(FollowUp.status == FollowUpStatus.PENDING)) or 0),
        "pending_overdue": int(
            db.scalar(
                base.where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.due_on < today)
            )
            or 0
        ),
    }


def tasks_completed(db: Session, owner_id: str, *, since: date) -> list[tuple[date, int]]:
    rows = db.execute(
        select(func.date(Task.completed_at), func.count(Task.id))
        .where(
            Task.owner_id == owner_id,
            Task.status == TaskStatus.DONE,
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
        )
        .group_by(func.date(Task.completed_at))
        .order_by(func.date(Task.completed_at).asc())
    ).all()
    return [(row[0], int(row[1])) for row in rows]


def time_entries_since(
    db: Session, owner_id: str, *, since: datetime
) -> list[tuple[datetime, datetime | None]]:
    rows = db.execute(
        select(TimeEntry.started_at, TimeEntry.ended_at)
        .where(TimeEntry.owner_id == owner_id, TimeEntry.started_at >= since)
        .order_by(TimeEntry.started_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def analysis_history(db: Session, owner_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            AnalysisJob.id,
            AnalysisResult.score,
            AnalysisResult.created_at,
            ResumeVersion.id,
            Resume.name,
            ResumeVersion.version_no,
            ResumeVersion.label,
            JobDescription.title,
        )
        .join(AnalysisResult, AnalysisResult.job_id == AnalysisJob.id)
        .join(ResumeVersion, ResumeVersion.id == AnalysisJob.resume_version_id)
        .join(Resume, Resume.id == ResumeVersion.resume_id)
        .outerjoin(JobDescription, JobDescription.id == AnalysisJob.jd_id)
        .where(
            AnalysisJob.owner_id == owner_id,
            AnalysisJob.status == AnalysisStatus.SUCCEEDED,
        )
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "job_id": row[0],
            "score": int(row[1]),
            "created_at": row[2],
            "resume_version_id": row[3],
            "resume_name": row[4],
            "version_no": row[5],
            "label": row[6],
            "jd_title": row[7],
        }
        for row in rows
    ]


def average_alignment(db: Session, owner_id: str) -> float | None:
    value = db.scalar(
        select(func.avg(AnalysisResult.score))
        .join(AnalysisJob, AnalysisResult.job_id == AnalysisJob.id)
        .where(
            AnalysisJob.owner_id == owner_id,
            AnalysisJob.status == AnalysisStatus.SUCCEEDED,
        )
    )
    return round(float(value), 1) if value is not None else None
