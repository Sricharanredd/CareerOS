from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, undefer

from app.db.enums import AnalysisStatus
from app.db.models import (
    AnalysisJob,
    AnalysisResult,
    Application,
    JobDescription,
    Resume,
    ResumeVersion,
)
from app.repositories.base import paginate

_EAGER = (
    joinedload(AnalysisJob.resume_version).joinedload(ResumeVersion.resume),
    joinedload(AnalysisJob.job_description).joinedload(JobDescription.company),
)


def get(db: Session, owner_id: str, job_id: str) -> AnalysisJob | None:
    return db.scalar(
        select(AnalysisJob)
        .options(*_EAGER, undefer(AnalysisJob.jd_text))
        .where(AnalysisJob.id == job_id, AnalysisJob.owner_id == owner_id)
    )


def get_by_id(db: Session, job_id: str) -> AnalysisJob | None:
    return db.scalar(
        select(AnalysisJob)
        .options(
            joinedload(AnalysisJob.resume_version).undefer(ResumeVersion.extracted_text),
            joinedload(AnalysisJob.resume_version).joinedload(ResumeVersion.resume),
            joinedload(AnalysisJob.job_description).joinedload(JobDescription.company),
            undefer(AnalysisJob.jd_text),
        )
        .where(AnalysisJob.id == job_id)
    )


def get_by_hash(db: Session, owner_id: str, input_hash: str) -> AnalysisJob | None:
    return db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.owner_id == owner_id, AnalysisJob.input_hash == input_hash
        )
    )


def list_page(
    db: Session,
    owner_id: str,
    *,
    status: list[AnalysisStatus] | None,
    resume_id: str | None,
    resume_version_id: str | None,
    jd_id: str | None,
    application_id: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[AnalysisJob], int]:
    clauses: list[Any] = [AnalysisJob.owner_id == owner_id]
    if status:
        clauses.append(AnalysisJob.status.in_(status))
    if resume_version_id:
        clauses.append(AnalysisJob.resume_version_id == resume_version_id)
    if resume_id:
        clauses.append(
            AnalysisJob.resume_version_id.in_(
                select(ResumeVersion.id).where(ResumeVersion.resume_id == resume_id)
            )
        )
    if jd_id:
        clauses.append(AnalysisJob.jd_id == jd_id)
    if application_id:
        application = db.scalar(
            select(Application).where(
                Application.id == application_id, Application.owner_id == owner_id
            )
        )
        if application is None:
            return [], 0
        matches = [AnalysisJob.resume_version_id == application.resume_version_id]
        if application.jd_id:
            matches.append(AnalysisJob.jd_id == application.jd_id)
        clauses.append(or_(*matches))

    ordering = {
        "created_at": AnalysisJob.created_at.asc(),
        "-created_at": AnalysisJob.created_at.desc(),
        "finished_at": AnalysisJob.finished_at.asc(),
        "-finished_at": AnalysisJob.finished_at.desc(),
    }.get(sort, AnalysisJob.created_at.desc())

    stmt = select(AnalysisJob).options(*_EAGER).where(*clauses).order_by(ordering)
    return paginate(db, stmt, page=page, page_size=page_size)


def stale_siblings(
    db: Session, owner_id: str, *, resume_version_id: str, jd_id: str | None
) -> None:
    """Older queued/running jobs for the same resume + JD can no longer be trusted."""
    statement = select(AnalysisJob).where(
        AnalysisJob.owner_id == owner_id,
        AnalysisJob.resume_version_id == resume_version_id,
        AnalysisJob.status.in_([AnalysisStatus.QUEUED, AnalysisStatus.RUNNING]),
    )
    if jd_id:
        statement = statement.where(AnalysisJob.jd_id == jd_id)
    for job in db.scalars(statement):
        job.status = AnalysisStatus.STALE
        job.error_code = "superseded"
        job.error_message = "A newer analysis replaced this one before it finished."


def stats(db: Session, owner_id: str) -> dict[str, Any]:
    rows = db.execute(
        select(AnalysisJob.status, func.count(AnalysisJob.id))
        .where(AnalysisJob.owner_id == owner_id)
        .group_by(AnalysisJob.status)
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    average = db.scalar(
        select(func.avg(AnalysisResult.score))
        .join(AnalysisJob, AnalysisResult.job_id == AnalysisJob.id)
        .where(
            AnalysisJob.owner_id == owner_id,
            AnalysisJob.status == AnalysisStatus.SUCCEEDED,
        )
    )
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "average_score": round(float(average), 1) if average is not None else None,
    }


def resume_scores(db: Session, owner_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            ResumeVersion.id,
            ResumeVersion.version_no,
            ResumeVersion.label,
            Resume.name,
            func.count(AnalysisResult.id),
            func.avg(AnalysisResult.score),
        )
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .join(AnalysisJob, AnalysisJob.resume_version_id == ResumeVersion.id)
        .join(AnalysisResult, AnalysisResult.job_id == AnalysisJob.id)
        .where(
            AnalysisJob.owner_id == owner_id,
            AnalysisJob.status == AnalysisStatus.SUCCEEDED,
        )
        .group_by(ResumeVersion.id, ResumeVersion.version_no, ResumeVersion.label, Resume.name)
        .order_by(func.avg(AnalysisResult.score).desc())
    ).all()
    return [
        {
            "resume_version_id": row[0],
            "version_no": row[1],
            "label": row[2],
            "resume_name": row[3],
            "analyses": int(row[4]),
            "average_score": round(float(row[5]), 1),
        }
        for row in rows
    ]
