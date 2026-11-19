from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models import AnalysisJob, Application, Resume, ResumeVersion
from app.repositories.base import paginate


def list_page(
    db: Session,
    owner_id: str,
    *,
    search: str | None,
    include_archived: bool,
    page: int,
    page_size: int,
) -> tuple[list[Resume], int]:
    stmt = select(Resume).where(Resume.owner_id == owner_id)
    if not include_archived:
        stmt = stmt.where(Resume.archived_at.is_(None))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Resume.name.like(like) | Resume.headline.like(like))
    stmt = stmt.options(
        selectinload(Resume.versions).joinedload(ResumeVersion.file),
        joinedload(Resume.current_version),
    ).order_by(Resume.archived_at.isnot(None), Resume.updated_at.desc())
    return paginate(db, stmt, page=page, page_size=page_size)


def get(db: Session, owner_id: str, resume_id: str) -> Resume | None:
    return db.scalar(
        select(Resume)
        .options(
            selectinload(Resume.versions).joinedload(ResumeVersion.file),
            joinedload(Resume.current_version),
        )
        .where(Resume.id == resume_id, Resume.owner_id == owner_id)
    )


def get_by_name(db: Session, owner_id: str, name: str) -> Resume | None:
    return db.scalar(select(Resume).where(Resume.owner_id == owner_id, Resume.name == name))


def get_version(db: Session, owner_id: str, version_id: str) -> ResumeVersion | None:
    return db.scalar(
        select(ResumeVersion)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .options(joinedload(ResumeVersion.file), joinedload(ResumeVersion.resume))
        .where(ResumeVersion.id == version_id, Resume.owner_id == owner_id)
    )


def next_version_no(db: Session, resume_id: str) -> int:
    current = db.scalar(
        select(func.max(ResumeVersion.version_no)).where(ResumeVersion.resume_id == resume_id)
    )
    return int(current or 0) + 1


def create_resume(db: Session, *, owner_id: str, name: str, headline: str | None) -> Resume:
    resume = Resume(owner_id=owner_id, name=name, headline=headline)
    db.add(resume)
    db.flush()
    return resume


def add_version(
    db: Session,
    *,
    resume: Resume,
    file_id: str,
    label: str | None,
    notes: str | None,
    extracted_text: str,
) -> ResumeVersion:
    version = ResumeVersion(
        resume_id=resume.id,
        file_id=file_id,
        version_no=next_version_no(db, resume.id),
        label=label,
        notes=notes,
        extracted_text=extracted_text,
    )
    db.add(version)
    db.flush()
    if resume.current_version_id is None:
        resume.current_version_id = version.id
        db.flush()
    return version


def usage_counts(db: Session, resume_id: str) -> tuple[int, int]:
    version_ids = list(
        db.scalars(select(ResumeVersion.id).where(ResumeVersion.resume_id == resume_id))
    )
    if not version_ids:
        return 0, 0
    apps = (
        db.scalar(
            select(func.count(Application.id)).where(Application.resume_version_id.in_(version_ids))
        )
        or 0
    )
    analyses = (
        db.scalar(
            select(func.count(AnalysisJob.id)).where(AnalysisJob.resume_version_id.in_(version_ids))
        )
        or 0
    )
    return int(apps), int(analyses)
