from __future__ import annotations

from app.core.deps import CurrentOwner, DbSession
from app.core.routing import CommittingAPIRouter
from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as dashboard_service

router = CommittingAPIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(owner: CurrentOwner, db: DbSession):
    return dashboard_service.build(db, owner.id)
