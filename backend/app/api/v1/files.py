from __future__ import annotations

from fastapi.responses import FileResponse

from app.core.deps import CurrentOwner, DbSession
from app.core.routing import CommittingAPIRouter
from app.services import resume as resume_service

router = CommittingAPIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/download")
def download_file(file_id: str, owner: CurrentOwner, db: DbSession):
    file_object, path = resume_service.download_target(db, owner.id, file_id)
    return FileResponse(
        path=path,
        media_type=file_object.mime,
        filename=file_object.original_name,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
