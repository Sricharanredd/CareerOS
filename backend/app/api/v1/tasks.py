from __future__ import annotations

from typing import Literal

from fastapi import Query, Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.db.enums import TaskPriority, TaskStatus
from app.repositories import productivity as repo
from app.schemas.common import Page
from app.schemas.productivity import (
    TaskCompleteRequest,
    TaskCreate,
    TaskUpdate,
    TaskView,
)
from app.services import productivity as service

router = CommittingAPIRouter(prefix="/tasks", tags=["tasks"])

Bucket = Literal["all", "today", "overdue", "upcoming", "open", "completed"]


def _view(task) -> TaskView:
    return service.task_view(task)


@router.get("", response_model=Page[TaskView])
def list_tasks(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    bucket: Bucket = "open",
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    application_id: str | None = None,
    search: str | None = Query(default=None, max_length=120),
):
    items, total = repo.list_tasks(
        db,
        owner.id,
        bucket=bucket,
        status=status,
        priority=priority,
        application_id=application_id,
        search=search,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[TaskView](
        items=[_view(task) for task in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.post("", response_model=TaskView, status_code=201)
def create_task(payload: TaskCreate, owner: CurrentOwner, db: DbSession):
    return _view(service.create_task(db, owner.id, payload))


@router.get("/{task_id}", response_model=TaskView)
def get_task(task_id: str, owner: CurrentOwner, db: DbSession):
    return _view(service.get_task(db, owner.id, task_id))


@router.patch("/{task_id}", response_model=TaskView)
def update_task(task_id: str, payload: TaskUpdate, owner: CurrentOwner, db: DbSession):
    return _view(service.update_task(db, owner.id, task_id, payload))


@router.post("/{task_id}/complete", response_model=TaskView)
def complete_task(task_id: str, payload: TaskCompleteRequest, owner: CurrentOwner, db: DbSession):
    return _view(service.complete_task(db, owner.id, task_id, completed=payload.completed))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, owner: CurrentOwner, db: DbSession):
    service.delete_task(db, owner.id, task_id)
    return Response(status_code=204)
