from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Company
from app.repositories import company as company_repo
from app.schemas.company import CompanyCreate, CompanyUpdate


def create(db: Session, owner_id: str, payload: CompanyCreate) -> Company:
    existing = company_repo.get_by_name(db, owner_id, payload.name)
    if existing is not None:
        raise _duplicate(payload.name)
    return company_repo.create(
        db,
        owner_id=owner_id,
        name=payload.name,
        website=payload.website,
        industry=payload.industry,
        location=payload.location,
        notes=payload.notes,
    )


def update(db: Session, owner_id: str, company_id: str, payload: CompanyUpdate) -> Company:
    company = company_repo.get(db, owner_id, company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    if payload.name and payload.name.strip().lower() != company.name.lower():
        clash = company_repo.get_by_name(db, owner_id, payload.name)
        if clash is not None and clash.id != company.id:
            raise _duplicate(payload.name)
        company.name = payload.name
    for field in ("website", "industry", "location", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(company, field, value)
    db.flush()
    return company


def set_archived(db: Session, owner_id: str, company_id: str, archived: bool) -> Company:
    company = company_repo.get(db, owner_id, company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    from app.core.security import utcnow

    company.archived_at = utcnow() if archived else None
    db.flush()
    return company


def _duplicate(name: str):
    from app.core.errors import ConflictError

    return ConflictError(
        f"A company named '{name}' already exists.",
        code="duplicate_company",
        details={"name": name},
    )
