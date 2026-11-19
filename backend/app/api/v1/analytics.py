from __future__ import annotations

from app.core.deps import CurrentOwner, DbSession
from app.core.routing import CommittingAPIRouter
from app.schemas.analytics import AnalyticsResponse
from app.services import analytics as service

router = CommittingAPIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
def get_analytics(owner: CurrentOwner, db: DbSession):
    return service.build(db, owner.id)
