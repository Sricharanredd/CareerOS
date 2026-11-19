from __future__ import annotations

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import FileKind
from app.db.models import JobDescription
from app.repositories import company as company_repo
from app.repositories import job as job_repo
from app.schemas.job import JobDescriptionCreate, JobDescriptionUpdate
from app.services import storage

MIN_USEFUL_CHARS = 80


def create_manual(db: Session, owner_id: str, payload: JobDescriptionCreate) -> JobDescription:
    _require_company(db, owner_id, payload.company_id)
    if not payload.raw_text.strip():
        raise UnprocessableError(
            "Paste the job description text or upload a file so the JD can be analyzed."
        )
    return job_repo.create(
        db,
        owner_id=owner_id,
        company_id=payload.company_id,
        title=payload.title,
        location=payload.location,
        url=payload.url,
        raw_text=payload.raw_text.strip(),
        seniority=payload.seniority,
        employment_type=payload.employment_type,
        required_skills=payload.required_skills,
        preferred_skills=payload.preferred_skills,
        responsibilities=payload.responsibilities,
        notes=payload.notes,
        source_file_id=None,
    )


def create_from_file(
    db: Session, owner_id: str, *, company_id: str, title: str, upload: UploadFile
) -> tuple[JobDescription, int]:
    _require_company(db, owner_id, company_id)
    file_object, payload = storage.save_upload(
        db, owner_id=owner_id, kind=FileKind.JOB_DESCRIPTION, upload=upload
    )
    text = storage.extract_text(file_object, payload)
    if len(text) < MIN_USEFUL_CHARS:
        storage.delete_file(file_object)
        raise UnprocessableError(
            "No usable text was found in that file. Scanned PDFs are not supported; paste the "
            "text manually instead.",
            details={"extracted_chars": len(text)},
        )
    jd = job_repo.create(
        db,
        owner_id=owner_id,
        company_id=company_id,
        title=title,
        location=None,
        url=None,
        raw_text=text,
        seniority=None,
        employment_type=None,
        required_skills=None,
        preferred_skills=None,
        responsibilities=None,
        notes=None,
        source_file_id=file_object.id,
    )
    return jd, len(text)


def update(db: Session, owner_id: str, jd_id: str, payload: JobDescriptionUpdate) -> JobDescription:
    jd = get(db, owner_id, jd_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("company_id"):
        _require_company(db, owner_id, data["company_id"])
    for field, value in data.items():
        setattr(jd, field, value)
    db.flush()
    return jd


def get(db: Session, owner_id: str, jd_id: str) -> JobDescription:
    jd = job_repo.get(db, owner_id, jd_id)
    if jd is None:
        raise NotFoundError("Job description not found.")
    return jd


def archive(db: Session, owner_id: str, jd_id: str, archived: bool) -> JobDescription:
    jd = get(db, owner_id, jd_id)
    jd.archived_at = utcnow() if archived else None
    db.flush()
    return jd


def delete(db: Session, owner_id: str, jd_id: str) -> None:
    jd = get(db, owner_id, jd_id)
    used = job_repo.application_count(db, jd.id)
    if used:
        raise ConflictError(
            "This job description is linked to applications. Archive it instead of deleting.",
            code="in_use",
            details={"applications": used},
        )
    db.delete(jd)
    db.flush()


def _require_company(db: Session, owner_id: str, company_id: str) -> None:
    from app.core.errors import UnprocessableError as Invalid

    if company_repo.get(db, owner_id, company_id) is None:
        raise Invalid("Select a company that belongs to this account.", code="invalid_company")
