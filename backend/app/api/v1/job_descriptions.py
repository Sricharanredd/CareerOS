from __future__ import annotations

from datetime import date

from fastapi import File, Form, Query, Response, UploadFile

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.repositories import job as job_repo
from app.schemas.common import Page
from app.schemas.job import (
    JobDescriptionCreate,
    JobDescriptionListItem,
    JobDescriptionUpdate,
    JobDescriptionView,
)
from app.services import job_description as jd_service

router = CommittingAPIRouter(prefix="/job-descriptions", tags=["job-descriptions"])


def _item(jd, chars: int) -> JobDescriptionListItem:
    return JobDescriptionListItem(
        id=jd.id,
        title=jd.title,
        location=jd.location,
        seniority=jd.seniority,
        created_at=jd.created_at,
        updated_at=jd.updated_at,
        archived_at=jd.archived_at,
        company=jd.company,
        text_chars=chars,
    )


@router.get("", response_model=Page[JobDescriptionListItem])
def list_job_descriptions(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    search: str | None = Query(default=None, max_length=120),
    company_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    include_archived: bool = False,
    sort: str = Query(default="-created_at", pattern="^-?(created_at|updated_at|title)$"),
):
    rows, total = job_repo.list_page(
        db,
        owner.id,
        search=search,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        include_archived=include_archived,
        sort=sort,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[JobDescriptionListItem](
        items=[_item(jd, chars) for jd, chars in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/options", response_model=list[JobDescriptionListItem])
def job_options(owner: CurrentOwner, db: DbSession, company_id: str | None = None):
    return [_item(jd, 0) for jd in job_repo.options(db, owner.id, company_id)]


@router.post("", response_model=JobDescriptionView, status_code=201)
def create_job_description(payload: JobDescriptionCreate, owner: CurrentOwner, db: DbSession):
    jd = jd_service.create_manual(db, owner.id, payload)
    return JobDescriptionView.model_validate(jd)


@router.post("/from-file", response_model=JobDescriptionView, status_code=201)
def create_from_file(
    owner: CurrentOwner,
    db: DbSession,
    company_id: str = Form(...),
    title: str = Form(..., min_length=1, max_length=250),
    file: UploadFile = File(...),
):
    jd, _chars = jd_service.create_from_file(
        db, owner.id, company_id=company_id, title=title, upload=file
    )
    return JobDescriptionView.model_validate(jd)


@router.get("/{jd_id}", response_model=JobDescriptionView)
def get_job_description(jd_id: str, owner: CurrentOwner, db: DbSession):
    return JobDescriptionView.model_validate(jd_service.get(db, owner.id, jd_id))


@router.patch("/{jd_id}", response_model=JobDescriptionView)
def update_job_description(
    jd_id: str, payload: JobDescriptionUpdate, owner: CurrentOwner, db: DbSession
):
    return JobDescriptionView.model_validate(jd_service.update(db, owner.id, jd_id, payload))


@router.post("/{jd_id}/archive", response_model=JobDescriptionView)
def archive_job_description(jd_id: str, owner: CurrentOwner, db: DbSession, archived: bool = True):
    return JobDescriptionView.model_validate(jd_service.archive(db, owner.id, jd_id, archived))


@router.delete("/{jd_id}", status_code=204)
def delete_job_description(jd_id: str, owner: CurrentOwner, db: DbSession):
    jd_service.delete(db, owner.id, jd_id)
    return Response(status_code=204)
