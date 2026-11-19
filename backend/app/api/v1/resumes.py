from __future__ import annotations

from fastapi import File, Form, Query, Response, UploadFile

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.repositories import resume as resume_repo
from app.schemas.common import Page
from app.schemas.resume import (
    ResumeCreateMeta,
    ResumeDetailView,
    ResumeUsage,
    ResumeVersionUpdate,
    ResumeVersionView,
    ResumeView,
)
from app.services import resume as resume_service

router = CommittingAPIRouter(prefix="/resumes", tags=["resumes"])


def _version_view(version, current_id: str | None) -> ResumeVersionView:
    return ResumeVersionView(
        id=version.id,
        version_no=version.version_no,
        label=version.label,
        notes=version.notes,
        created_at=version.created_at,
        file_id=version.file_id,
        extracted_chars=len(getattr(version, "extracted_text", "") or ""),
        is_current=version.id == current_id,
    )


def _detail(resume) -> ResumeDetailView:
    current = resume.current_version_id
    versions = [
        _version_view(version, current)
        for version in sorted(resume.versions, key=lambda v: v.version_no, reverse=True)
    ]
    current_version = next((v for v in resume.versions if v.id == current), None)
    return ResumeDetailView(
        id=resume.id,
        name=resume.name,
        headline=resume.headline,
        archived_at=resume.archived_at,
        created_at=resume.created_at,
        updated_at=resume.updated_at,
        version_count=len(resume.versions),
        current_version_no=current_version.version_no if current_version else None,
        current_file_name=current_version.file.original_name
        if current_version and current_version.file
        else None,
        versions=versions,
    )


@router.get("", response_model=Page[ResumeView])
def list_resumes(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
):
    items, total = resume_service.list_page(
        db,
        owner.id,
        search=search,
        include_archived=include_archived,
        page=page.page,
        page_size=page.page_size,
    )
    views: list[ResumeView] = []
    for resume in items:
        current_version = next(
            (v for v in resume.versions if v.id == resume.current_version_id), None
        )
        views.append(
            ResumeView(
                id=resume.id,
                name=resume.name,
                headline=resume.headline,
                archived_at=resume.archived_at,
                created_at=resume.created_at,
                updated_at=resume.updated_at,
                version_count=len(resume.versions),
                current_version_no=current_version.version_no if current_version else None,
                current_file_name=(
                    current_version.file.original_name
                    if current_version and current_version.file
                    else None
                ),
            )
        )
    return Page[ResumeView](items=views, total=total, page=page.page, page_size=page.page_size)


@router.post("", response_model=ResumeDetailView, status_code=201)
def create_resume(
    owner: CurrentOwner,
    db: DbSession,
    name: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
    headline: str | None = Form(default=None, max_length=250),
    label: str | None = Form(default=None, max_length=120),
    notes: str | None = Form(default=None, max_length=20000),
):
    meta = ResumeCreateMeta(name=name, headline=headline, label=label, notes=notes)
    resume, _version, _chars = resume_service.create_with_file(db, owner.id, meta, file)
    return _detail(resume_service.get(db, owner.id, resume.id))


@router.get("/{resume_id}", response_model=ResumeDetailView)
def get_resume(resume_id: str, owner: CurrentOwner, db: DbSession):
    return _detail(resume_service.get(db, owner.id, resume_id))


@router.get("/{resume_id}/usage", response_model=ResumeUsage)
def resume_usage(resume_id: str, owner: CurrentOwner, db: DbSession):
    resume = resume_service.get(db, owner.id, resume_id)
    apps, analyses = resume_repo.usage_counts(db, resume.id)
    return ResumeUsage(application_count=apps, analysis_count=analyses)


@router.post("/{resume_id}/versions", response_model=ResumeDetailView, status_code=201)
def add_version(
    resume_id: str,
    owner: CurrentOwner,
    db: DbSession,
    file: UploadFile = File(...),
    label: str | None = Form(default=None, max_length=120),
    notes: str | None = Form(default=None, max_length=20000),
    make_current: bool = Form(default=True),
):
    resume_service.add_version(
        db,
        owner.id,
        resume_id,
        label=label,
        notes=notes,
        upload=file,
        make_current=make_current,
    )
    return _detail(resume_service.get(db, owner.id, resume_id))


@router.patch("/{resume_id}/versions/{version_id}", response_model=ResumeVersionView)
def update_version(
    resume_id: str,
    version_id: str,
    payload: ResumeVersionUpdate,
    owner: CurrentOwner,
    db: DbSession,
):
    resume = resume_service.get(db, owner.id, resume_id)
    version = resume_service.update_version(db, owner.id, version_id, payload)
    return _version_view(version, resume.current_version_id)


@router.post("/{resume_id}/versions/{version_id}/current", response_model=ResumeDetailView)
def set_current_version(resume_id: str, version_id: str, owner: CurrentOwner, db: DbSession):
    resume_service.set_current(db, owner.id, resume_id, version_id)
    return _detail(resume_service.get(db, owner.id, resume_id))


@router.post("/{resume_id}/archive", response_model=ResumeDetailView)
def archive_resume(resume_id: str, owner: CurrentOwner, db: DbSession, archived: bool = True):
    resume_service.set_archived(db, owner.id, resume_id, archived)
    return _detail(resume_service.get(db, owner.id, resume_id))


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: str, owner: CurrentOwner, db: DbSession):
    resume_service.delete(db, owner.id, resume_id)
    return Response(status_code=204)
