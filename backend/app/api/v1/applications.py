from __future__ import annotations

from datetime import date

from fastapi import Query, Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.db.enums import ApplicationStatus, EventType, WorkMode
from app.db.models import Application
from app.repositories import application as app_repo
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationUpdate,
    ApplicationView,
    KanbanBoard,
    KanbanColumn,
    NoteRequest,
    StatusChangeRequest,
    TimelineEvent,
)
from app.schemas.common import Page
from app.services import application as app_service
from app.services import audit

router = CommittingAPIRouter(prefix="/applications", tags=["applications"])

SORT_PATTERN = "^-?(applied_on|created_at|updated_at|title)$"


@router.get("", response_model=Page[ApplicationView])
def list_applications(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    status: list[ApplicationStatus] | None = Query(default=None),
    company_id: str | None = None,
    work_mode: WorkMode | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=120),
    include_archived: bool = False,
    sort: str = Query(default="-created_at", pattern=SORT_PATTERN),
):
    items, total = app_repo.list_page(
        db,
        owner.id,
        status=status,
        company_id=company_id,
        work_mode=work_mode,
        date_from=date_from,
        date_to=date_to,
        search=search,
        include_archived=include_archived,
        sort=sort,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[ApplicationView](
        items=[ApplicationView.model_validate(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/board", response_model=KanbanBoard)
def board(
    owner: CurrentOwner,
    db: DbSession,
    include_archived: bool = False,
):
    rows = app_repo.board(db, owner.id, include_archived=include_archived)
    grouped: dict[ApplicationStatus, list[Application]] = {
        status: [] for status in ApplicationStatus
    }
    for row in rows:
        grouped[ApplicationStatus(row.status)].append(row)
    return KanbanBoard(
        columns=[
            KanbanColumn(
                status=status,
                count=len(grouped[status]),
                items=[ApplicationView.model_validate(item) for item in grouped[status]],
            )
            for status in ApplicationStatus
        ]
    )


@router.post("", response_model=ApplicationView, status_code=201)
def create_application(payload: ApplicationCreate, owner: CurrentOwner, db: DbSession):
    application = app_service.create(db, owner.id, payload)
    return ApplicationView.model_validate(application)


@router.get("/{app_id}", response_model=ApplicationDetail)
def get_application(app_id: str, owner: CurrentOwner, db: DbSession):
    application = app_service.get(db, owner.id, app_id)
    detail = ApplicationDetail.model_validate(application)
    detail.jd_id = application.jd_id
    detail.resume_version_id = application.resume_version_id
    detail.events = [TimelineEvent.model_validate(event) for event in application.events]
    return detail


@router.patch("/{app_id}", response_model=ApplicationView)
def update_application(app_id: str, payload: ApplicationUpdate, owner: CurrentOwner, db: DbSession):
    application = app_service.update(db, owner.id, app_id, payload)
    return ApplicationView.model_validate(application)


@router.post("/{app_id}/status", response_model=ApplicationView)
def change_status(app_id: str, payload: StatusChangeRequest, owner: CurrentOwner, db: DbSession):
    application = app_service.change_status(db, owner.id, app_id, payload)
    return ApplicationView.model_validate(application)


@router.post("/{app_id}/archive", response_model=ApplicationView)
def archive_application(app_id: str, owner: CurrentOwner, db: DbSession, archived: bool = True):
    application = app_service.set_archived(db, owner.id, app_id, archived)
    return ApplicationView.model_validate(application)


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: str, owner: CurrentOwner, db: DbSession):
    app_service.delete(db, owner.id, app_id)
    return Response(status_code=204)


@router.get("/{app_id}/timeline", response_model=list[TimelineEvent])
def timeline(app_id: str, owner: CurrentOwner, db: DbSession):
    app_service.get(db, owner.id, app_id)
    return [TimelineEvent.model_validate(event) for event in app_repo.timeline(db, app_id)]


@router.post("/{app_id}/notes", response_model=ApplicationView)
def add_note(app_id: str, payload: NoteRequest, owner: CurrentOwner, db: DbSession):
    application = app_service.get(db, owner.id, app_id)
    app_repo.add_event(
        db,
        application_id=application.id,
        event_type=EventType.NOTE,
        payload={"note": payload.note},
    )
    audit.record(
        db, owner_id=owner.id, action="application.note", entity="application", entity_id=app_id
    )
    db.flush()
    return ApplicationView.model_validate(application)
