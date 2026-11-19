from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Application, Company, JobDescription
from app.repositories.base import paginate


def _base(owner_id: str, include_archived: bool) -> Select[Any]:
    stmt = select(Company).where(Company.owner_id == owner_id)
    if not include_archived:
        stmt = stmt.where(Company.archived_at.is_(None))
    return stmt


def get(db: Session, owner_id: str, company_id: str) -> Company | None:
    return db.scalar(select(Company).where(Company.id == company_id, Company.owner_id == owner_id))


def get_by_name(db: Session, owner_id: str, name: str) -> Company | None:
    return db.scalar(select(Company).where(Company.owner_id == owner_id, Company.name == name))


def list_page(
    db: Session,
    owner_id: str,
    *,
    search: str | None,
    include_archived: bool,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[Company], int]:
    stmt = _base(owner_id, include_archived)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Company.name.like(like) | Company.industry.like(like))

    ordering = {
        "name": Company.name.asc(),
        "-name": Company.name.desc(),
        "created_at": Company.created_at.asc(),
        "-created_at": Company.created_at.desc(),
    }.get(sort, Company.name.asc())
    return paginate(db, stmt.order_by(ordering), page=page, page_size=page_size)


def counts(db: Session, owner_id: str, company_ids: list[str]) -> dict[str, tuple[int, int]]:
    """Return {company_id: (applications, job_descriptions)} in two aggregate queries."""
    if not company_ids:
        return {}
    apps = dict(
        db.execute(
            select(Application.company_id, func.count(Application.id))
            .where(Application.owner_id == owner_id, Application.company_id.in_(company_ids))
            .group_by(Application.company_id)
        ).all()
    )
    jds = dict(
        db.execute(
            select(JobDescription.company_id, func.count(JobDescription.id))
            .where(
                JobDescription.owner_id == owner_id,
                JobDescription.company_id.in_(company_ids),
            )
            .group_by(JobDescription.company_id)
        ).all()
    )
    return {cid: (int(apps.get(cid, 0)), int(jds.get(cid, 0))) for cid in company_ids}


def list_options(db: Session, owner_id: str) -> list[Company]:
    return list(
        db.scalars(
            select(Company)
            .where(Company.owner_id == owner_id)
            .order_by(Company.archived_at.isnot(None), Company.name.asc())
        )
    )


def create(
    db: Session,
    *,
    owner_id: str,
    name: str,
    website: str | None,
    industry: str | None,
    location: str | None,
    notes: str | None,
) -> Company:
    company = Company(
        owner_id=owner_id,
        name=name,
        website=website,
        industry=industry,
        location=location,
        notes=notes,
    )
    db.add(company)
    db.flush()
    return company


def usage(db: Session, company_id: str) -> tuple[int, int]:
    apps = (
        db.scalar(select(func.count(Application.id)).where(Application.company_id == company_id))
        or 0
    )
    jds = (
        db.scalar(
            select(func.count(JobDescription.id)).where(JobDescription.company_id == company_id)
        )
        or 0
    )
    return int(apps), int(jds)
