from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.enums import ApplicationStatus, WorkMode
from app.db.models import (
    Application,
    ApplicationEvent,
    Company,
    JobDescription,
    Resume,
    ResumeVersion,
)
from app.repositories.base import paginate

_EAGER = (
    joinedload(Application.company),
    joinedload(Application.job_description),
    joinedload(Application.resume_version),
)


def get(db: Session, owner_id: str, app_id: str) -> Application | None:
    return db.scalar(
        select(Application)
        .options(*_EAGER)
        .where(Application.id == app_id, Application.owner_id == owner_id)
    )


def get_with_events(db: Session, owner_id: str, app_id: str) -> Application | None:
    return db.scalar(
        select(Application)
        .options(*_EAGER, selectinload(Application.events))
        .where(Application.id == app_id, Application.owner_id == owner_id)
    )


def _clauses(
    owner_id: str,
    *,
    status: list[ApplicationStatus] | None,
    company_id: str | None,
    work_mode: WorkMode | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
    include_archived: bool,
) -> list[Any]:
    clauses: list[Any] = [Application.owner_id == owner_id]
    if not include_archived:
        clauses.append(Application.archived_at.is_(None))
    if status:
        clauses.append(Application.status.in_(status))
    if company_id:
        clauses.append(Application.company_id == company_id)
    if work_mode:
        clauses.append(Application.work_mode == work_mode)
    if date_from:
        clauses.append(Application.applied_on >= date_from)
    if date_to:
        clauses.append(Application.applied_on <= date_to)
    if search:
        like = f"%{search.strip()}%"
        clauses.append(or_(Application.title.like(like), Company.name.like(like)))
    return clauses


def list_page(
    db: Session,
    owner_id: str,
    *,
    status: list[ApplicationStatus] | None,
    company_id: str | None,
    work_mode: WorkMode | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
    include_archived: bool,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[Application], int]:
    clauses = _clauses(
        owner_id,
        status=status,
        company_id=company_id,
        work_mode=work_mode,
        date_from=date_from,
        date_to=date_to,
        search=search,
        include_archived=include_archived,
    )
    stmt = select(Application).join(Company, Application.company_id == Company.id)
    stmt = stmt.where(*clauses)

    ordering = {
        "applied_on": Application.applied_on.asc(),
        "-applied_on": Application.applied_on.desc(),
        "created_at": Application.created_at.asc(),
        "-created_at": Application.created_at.desc(),
        "updated_at": Application.updated_at.asc(),
        "-updated_at": Application.updated_at.desc(),
        "title": Application.title.asc(),
        "-title": Application.title.desc(),
    }.get(sort, Application.created_at.desc())

    stmt = stmt.options(*_EAGER).order_by(ordering)
    return paginate(db, stmt, page=page, page_size=page_size)


def board(
    db: Session, owner_id: str, *, limit: int = 400, include_archived: bool = False
) -> list[Application]:
    clauses: list[Any] = [Application.owner_id == owner_id]
    if not include_archived:
        clauses.append(Application.archived_at.is_(None))
    return list(
        db.scalars(
            select(Application)
            .options(*_EAGER)
            .where(*clauses)
            .order_by(Application.updated_at.desc())
            .limit(limit)
        ).unique()
    )


def find_duplicates(
    db: Session,
    owner_id: str,
    *,
    company_id: str,
    title: str,
    applied_on: date | None,
    exclude_id: str | None = None,
    window_days: int = 14,
) -> list[Application]:
    anchor = applied_on or date.today()
    lower = anchor - timedelta(days=window_days)
    upper = anchor + timedelta(days=window_days)
    stmt = (
        select(Application)
        .options(*_EAGER)
        .where(
            Application.owner_id == owner_id,
            Application.company_id == company_id,
            func.lower(Application.title) == title.strip().lower(),
            Application.archived_at.is_(None),
            or_(
                Application.applied_on.between(lower, upper),
                Application.applied_on.is_(None),
            ),
        )
        .limit(5)
    )
    if exclude_id:
        stmt = stmt.where(Application.id != exclude_id)
    return list(db.scalars(stmt).unique())


def create(db: Session, *, owner_id: str, data: dict[str, Any]) -> Application:
    application = Application(owner_id=owner_id, **data)
    db.add(application)
    db.flush()
    return application


def add_event(
    db: Session,
    *,
    application_id: str,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ApplicationEvent:
    from app.core.security import utcnow

    event = ApplicationEvent(
        application_id=application_id,
        type=event_type,
        from_status=from_status,
        to_status=to_status,
        payload=payload,
        created_at=utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def timeline(db: Session, application_id: str) -> list[ApplicationEvent]:
    return list(
        db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.created_at.desc())
        )
    )


def validate_references(
    db: Session,
    owner_id: str,
    *,
    company_id: str,
    jd_id: str | None,
    resume_version_id: str | None,
) -> tuple[Company | None, JobDescription | None, ResumeVersion | None]:
    company = db.scalar(
        select(Company).where(Company.id == company_id, Company.owner_id == owner_id)
    )
    jd = None
    if jd_id:
        jd = db.scalar(
            select(JobDescription).where(
                JobDescription.id == jd_id, JobDescription.owner_id == owner_id
            )
        )
    version = None
    if resume_version_id:
        version = db.scalar(
            select(ResumeVersion)
            .join(Resume, ResumeVersion.resume_id == Resume.id)
            .where(ResumeVersion.id == resume_version_id, Resume.owner_id == owner_id)
        )
    return company, jd, version
