from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Application, JobDescription
from app.repositories.base import count_of


def _clauses(
    owner_id: str,
    *,
    search: str | None,
    company_id: str | None,
    date_from: date | None,
    date_to: date | None,
    include_archived: bool,
) -> list[Any]:
    clauses: list[Any] = [JobDescription.owner_id == owner_id]
    if not include_archived:
        clauses.append(JobDescription.archived_at.is_(None))
    if company_id:
        clauses.append(JobDescription.company_id == company_id)
    if search:
        like = f"%{search.strip()}%"
        clauses.append(JobDescription.title.like(like) | JobDescription.location.like(like))
    if date_from:
        clauses.append(JobDescription.created_at >= date_from)
    if date_to:
        clauses.append(JobDescription.created_at < date_to)
    return clauses


def get(db: Session, owner_id: str, jd_id: str) -> JobDescription | None:
    return db.scalar(
        select(JobDescription)
        .options(joinedload(JobDescription.company))
        .where(JobDescription.id == jd_id, JobDescription.owner_id == owner_id)
    )


def list_page(
    db: Session,
    owner_id: str,
    *,
    search: str | None,
    company_id: str | None,
    date_from: date | None,
    date_to: date | None,
    include_archived: bool,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[tuple[JobDescription, int]], int]:
    clauses = _clauses(
        owner_id,
        search=search,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        include_archived=include_archived,
    )
    total = count_of(db, select(JobDescription).where(*clauses))

    ordering = {
        "created_at": JobDescription.created_at.asc(),
        "-created_at": JobDescription.created_at.desc(),
        "title": JobDescription.title.asc(),
        "-title": JobDescription.title.desc(),
        "updated_at": JobDescription.updated_at.asc(),
        "-updated_at": JobDescription.updated_at.desc(),
    }.get(sort, JobDescription.created_at.desc())

    chars = func.char_length(JobDescription.raw_text).label("text_chars")
    rows = (
        db.execute(
            select(JobDescription, chars)
            .options(joinedload(JobDescription.company))
            .where(*clauses)
            .order_by(ordering)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .unique()
        .all()
    )
    return [(row[0], int(row[1] or 0)) for row in rows], total


def create(
    db: Session,
    *,
    owner_id: str,
    company_id: str,
    title: str,
    location: str | None,
    url: str | None,
    raw_text: str,
    seniority: str | None,
    employment_type: str | None,
    required_skills: list[str] | None,
    preferred_skills: list[str] | None,
    responsibilities: list[str] | None,
    notes: str | None,
    source_file_id: str | None,
) -> JobDescription:
    jd = JobDescription(
        owner_id=owner_id,
        company_id=company_id,
        title=title,
        location=location,
        url=url,
        raw_text=raw_text,
        seniority=seniority,
        employment_type=employment_type,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities=responsibilities,
        notes=notes,
        source_file_id=source_file_id,
    )
    db.add(jd)
    db.flush()
    return jd


def application_count(db: Session, jd_id: str) -> int:
    return int(db.scalar(select(func.count(Application.id)).where(Application.jd_id == jd_id)) or 0)


def options(db: Session, owner_id: str, company_id: str | None = None) -> list[JobDescription]:
    stmt = select(JobDescription).where(
        JobDescription.owner_id == owner_id, JobDescription.archived_at.is_(None)
    )
    if company_id:
        stmt = stmt.where(JobDescription.company_id == company_id)
    return list(db.scalars(stmt.order_by(JobDescription.created_at.desc()).limit(200)))
