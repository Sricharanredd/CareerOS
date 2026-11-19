from __future__ import annotations

from fastapi import BackgroundTasks, Query, Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.db.enums import AnalysisStatus
from app.repositories import analysis as repo
from app.schemas.analysis import (
    AnalysisJobView,
    AnalysisStats,
    AnalysisSubmit,
    ResumeScore,
)
from app.schemas.common import Page
from app.services import analysis as service

router = CommittingAPIRouter(prefix="/analyses", tags=["analyses"])

SORT_PATTERN = "^-?(created_at|finished_at)$"


@router.post("", response_model=AnalysisJobView, status_code=201)
def submit_analysis(
    payload: AnalysisSubmit,
    owner: CurrentOwner,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
):
    job, created = service.submit(db, owner.id, payload)
    if not created:
        response.status_code = 200
    if job.status == AnalysisStatus.QUEUED:
        background.add_task(service.run, job.id)
    return service.view(job, detail=True)


@router.get("", response_model=Page[AnalysisJobView])
def list_analyses(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    status: list[AnalysisStatus] | None = Query(default=None),
    resume_id: str | None = None,
    resume_version_id: str | None = None,
    jd_id: str | None = None,
    application_id: str | None = None,
    sort: str = Query(default="-created_at", pattern=SORT_PATTERN),
):
    items, total = repo.list_page(
        db,
        owner.id,
        status=status,
        resume_id=resume_id,
        resume_version_id=resume_version_id,
        jd_id=jd_id,
        application_id=application_id,
        sort=sort,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[AnalysisJobView](
        items=[service.view(job) for job in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/stats", response_model=AnalysisStats)
def analysis_stats(owner: CurrentOwner, db: DbSession):
    return service.stats(db, owner.id)


@router.get("/resume-scores", response_model=list[ResumeScore])
def resume_scores(owner: CurrentOwner, db: DbSession):
    return service.resume_scores(db, owner.id)


@router.get("/{job_id}", response_model=AnalysisJobView)
def get_analysis(job_id: str, owner: CurrentOwner, db: DbSession):
    return service.view(service.get(db, owner.id, job_id), detail=True)


@router.post("/{job_id}/cancel", response_model=AnalysisJobView)
def cancel_analysis(job_id: str, owner: CurrentOwner, db: DbSession):
    return service.view(service.cancel(db, owner.id, job_id), detail=True)


@router.delete("/{job_id}", status_code=204)
def delete_analysis(job_id: str, owner: CurrentOwner, db: DbSession):
    service.delete(db, owner.id, job_id)
    return Response(status_code=204)
