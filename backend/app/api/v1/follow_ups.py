from __future__ import annotations

from typing import Literal

from fastapi import Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.db.enums import FollowUpStatus
from app.repositories import productivity as repo
from app.schemas.common import Page
from app.schemas.productivity import FollowUpCreate, FollowUpUpdate, FollowUpView
from app.services import productivity as service

router = CommittingAPIRouter(prefix="/follow-ups", tags=["follow-ups"])

Scope = Literal["all", "overdue", "today", "upcoming", "open", "done"]


@router.get("", response_model=Page[FollowUpView])
def list_follow_ups(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    scope: Scope = "open",
    status: FollowUpStatus | None = None,
    application_id: str | None = None,
):
    items, total = repo.list_follow_ups(
        db,
        owner.id,
        scope=scope,
        status=status,
        application_id=application_id,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[FollowUpView](
        items=[service.follow_up_view(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.post("", response_model=FollowUpView, status_code=201)
def create_follow_up(payload: FollowUpCreate, owner: CurrentOwner, db: DbSession):
    return service.follow_up_view(service.create_follow_up(db, owner.id, payload))


@router.get("/{follow_up_id}", response_model=FollowUpView)
def get_follow_up(follow_up_id: str, owner: CurrentOwner, db: DbSession):
    return service.follow_up_view(service.get_follow_up(db, owner.id, follow_up_id))


@router.patch("/{follow_up_id}", response_model=FollowUpView)
def update_follow_up(
    follow_up_id: str, payload: FollowUpUpdate, owner: CurrentOwner, db: DbSession
):
    return service.follow_up_view(service.update_follow_up(db, owner.id, follow_up_id, payload))


@router.delete("/{follow_up_id}", status_code=204)
def delete_follow_up(follow_up_id: str, owner: CurrentOwner, db: DbSession):
    service.delete_follow_up(db, owner.id, follow_up_id)
    return Response(status_code=204)
