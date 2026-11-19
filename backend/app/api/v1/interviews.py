from __future__ import annotations

from typing import Literal

from fastapi import Response

from app.core.deps import CurrentOwner, DbSession, Pagination
from app.core.routing import CommittingAPIRouter
from app.db.enums import InterviewOutcome
from app.repositories import productivity as repo
from app.schemas.common import Page
from app.schemas.productivity import InterviewCreate, InterviewUpdate, InterviewView
from app.services import productivity as service

router = CommittingAPIRouter(prefix="/interviews", tags=["interviews"])

Scope = Literal["all", "upcoming", "past"]


@router.get("", response_model=Page[InterviewView])
def list_interviews(
    owner: CurrentOwner,
    db: DbSession,
    page: Pagination,
    scope: Scope = "all",
    application_id: str | None = None,
    outcome: InterviewOutcome | None = None,
):
    from app.core.security import utcnow

    items, total = repo.list_interviews(
        db,
        owner.id,
        scope=scope,
        application_id=application_id,
        outcome=outcome,
        now=utcnow(),
        page=page.page,
        page_size=page.page_size,
    )
    return Page[InterviewView](
        items=[service.interview_view(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.post("", response_model=InterviewView, status_code=201)
def create_interview(payload: InterviewCreate, owner: CurrentOwner, db: DbSession):
    return service.interview_view(service.create_interview(db, owner.id, payload))


@router.get("/{interview_id}", response_model=InterviewView)
def get_interview(interview_id: str, owner: CurrentOwner, db: DbSession):
    return service.interview_view(service.get_interview(db, owner.id, interview_id))


@router.patch("/{interview_id}", response_model=InterviewView)
def update_interview(
    interview_id: str, payload: InterviewUpdate, owner: CurrentOwner, db: DbSession
):
    return service.interview_view(service.update_interview(db, owner.id, interview_id, payload))


@router.delete("/{interview_id}", status_code=204)
def delete_interview(interview_id: str, owner: CurrentOwner, db: DbSession):
    service.delete_interview(db, owner.id, interview_id)
    return Response(status_code=204)
