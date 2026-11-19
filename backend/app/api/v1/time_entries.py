from __future__ import annotations

from datetime import date

from fastapi import Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.repositories import productivity as repo
from app.schemas.common import Page
from app.schemas.productivity import TimeEntryCreate, TimeEntryUpdate, TimeEntryView
from app.services import productivity as service

router = CommittingAPIRouter(prefix="/time-entries", tags=["time-entries"])


@router.get("", response_model=Page[TimeEntryView])
def list_time_entries(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    task_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    items, total = repo.list_time_entries(
        db,
        owner.id,
        task_id=task_id,
        date_from=date_from,
        date_to=date_to,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[TimeEntryView](
        items=[service.time_entry_view(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.post("", response_model=TimeEntryView, status_code=201)
def create_time_entry(payload: TimeEntryCreate, owner: CurrentOwner, db: DbSession):
    return service.time_entry_view(service.create_time_entry(db, owner.id, payload))


@router.get("/{entry_id}", response_model=TimeEntryView)
def get_time_entry(entry_id: str, owner: CurrentOwner, db: DbSession):
    return service.time_entry_view(service.get_time_entry(db, owner.id, entry_id))


@router.patch("/{entry_id}", response_model=TimeEntryView)
def update_time_entry(entry_id: str, payload: TimeEntryUpdate, owner: CurrentOwner, db: DbSession):
    return service.time_entry_view(service.update_time_entry(db, owner.id, entry_id, payload))


@router.delete("/{entry_id}", status_code=204)
def delete_time_entry(entry_id: str, owner: CurrentOwner, db: DbSession):
    service.delete_time_entry(db, owner.id, entry_id)
    return Response(status_code=204)
