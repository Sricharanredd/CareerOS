from __future__ import annotations

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import FileKind
from app.db.models import Resume, ResumeVersion
from app.repositories import resume as resume_repo
from app.schemas.resume import ResumeCreateMeta, ResumeVersionUpdate
from app.services import storage

MIN_USEFUL_CHARS = 120


def list_page(
    db: Session,
    owner_id: str,
    *,
    search: str | None,
    include_archived: bool,
    page: int,
    page_size: int,
) -> tuple[list[Resume], int]:
    return resume_repo.list_page(
        db,
        owner_id,
        search=search,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
    )


def get(db: Session, owner_id: str, resume_id: str) -> Resume:
    resume = resume_repo.get(db, owner_id, resume_id)
    if resume is None:
        raise NotFoundError("Resume not found.")
    return resume


def create_with_file(
    db: Session, owner_id: str, meta: ResumeCreateMeta, upload: UploadFile
) -> tuple[Resume, ResumeVersion, int]:
    name = " ".join(meta.name.split())
    if resume_repo.get_by_name(db, owner_id, name) is not None:
        raise ConflictError(
            f"A resume named '{name}' already exists.",
            code="duplicate_resume",
            details={"name": name},
        )

    file_object, payload = storage.save_upload(
        db, owner_id=owner_id, kind=FileKind.RESUME, upload=upload
    )
    text = storage.extract_text(file_object, payload)
    if len(text) < MIN_USEFUL_CHARS:
        storage.delete_file(file_object)
        raise UnprocessableError(
            "That file has little or no extractable text. Scanned images are not supported — "
            "export the resume as a text-based PDF or DOCX.",
            details={"extracted_chars": len(text)},
        )

    resume = resume_repo.create_resume(db, owner_id=owner_id, name=name, headline=meta.headline)
    version = resume_repo.add_version(
        db,
        resume=resume,
        file_id=file_object.id,
        label=meta.label or "Initial version",
        notes=meta.notes,
        extracted_text=text,
    )
    db.flush()
    return resume, version, len(text)


def add_version(
    db: Session,
    owner_id: str,
    resume_id: str,
    *,
    label: str | None,
    notes: str | None,
    upload: UploadFile,
    make_current: bool,
) -> tuple[ResumeVersion, int]:
    resume = get(db, owner_id, resume_id)
    if resume.archived_at is not None:
        raise ConflictError("Restore this resume before adding a version.", code="archived")

    file_object, payload = storage.save_upload(
        db, owner_id=owner_id, kind=FileKind.RESUME, upload=upload
    )
    text = storage.extract_text(file_object, payload)
    if len(text) < MIN_USEFUL_CHARS:
        storage.delete_file(file_object)
        raise UnprocessableError(
            "That file has little or no extractable text. Export a text-based PDF or DOCX.",
            details={"extracted_chars": len(text)},
        )

    version = resume_repo.add_version(
        db,
        resume=resume,
        file_id=file_object.id,
        label=label,
        notes=notes,
        extracted_text=text,
    )
    if make_current:
        resume.current_version_id = version.id
    db.flush()
    return version, len(text)


def set_current(db: Session, owner_id: str, resume_id: str, version_id: str) -> Resume:
    resume = get(db, owner_id, resume_id)
    version = next((v for v in resume.versions if v.id == version_id), None)
    if version is None:
        raise NotFoundError("Resume version not found.")
    resume.current_version_id = version.id
    db.flush()
    return resume


def update_version(
    db: Session, owner_id: str, version_id: str, payload: ResumeVersionUpdate
) -> ResumeVersion:
    version = resume_repo.get_version(db, owner_id, version_id)
    if version is None:
        raise NotFoundError("Resume version not found.")
    if payload.label is not None:
        version.label = payload.label
    if payload.notes is not None:
        version.notes = payload.notes
    db.flush()
    return version


def set_archived(db: Session, owner_id: str, resume_id: str, archived: bool) -> Resume:
    resume = get(db, owner_id, resume_id)
    resume.archived_at = utcnow() if archived else None
    db.flush()
    return resume


def delete(db: Session, owner_id: str, resume_id: str) -> None:
    resume = get(db, owner_id, resume_id)
    apps, analyses = resume_repo.usage_counts(db, resume.id)
    if apps or analyses:
        raise ConflictError(
            "This resume is referenced by applications or analyses. Archive it instead of "
            "deleting it, so history stays intact.",
            code="in_use",
            details={"applications": apps, "analyses": analyses},
        )
    files = [version.file for version in resume.versions if version.file is not None]
    db.delete(resume)
    db.flush()
    # FileObjects use ON DELETE RESTRICT from resume_version, so they can only go
    # after the cascade above has removed the versions.
    for file_object in files:
        storage.delete_file(file_object)
        db.delete(file_object)
    db.flush()


def download_target(db: Session, owner_id: str, file_id: str):
    from sqlalchemy import select

    from app.db.models import FileObject
    from app.repositories import base as base_repo  # noqa: F401  (keeps import graph honest)

    file_object = db.scalar(
        select(FileObject).where(FileObject.id == file_id, FileObject.owner_id == owner_id)
    )
    if file_object is None:
        raise NotFoundError("File not found.")
    return file_object, storage.absolute_path(file_object)
