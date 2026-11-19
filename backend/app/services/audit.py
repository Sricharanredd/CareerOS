from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.db.models import AuditLog


def record(
    db: Session,
    *,
    owner_id: str,
    action: str,
    entity: str,
    entity_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Audit entries carry identifiers and short enums only — never user content."""
    db.add(
        AuditLog(
            owner_id=owner_id,
            action=action[:64],
            entity=entity[:64],
            entity_id=entity_id,
            detail=(detail or "")[:255] or None,
            created_at=utcnow(),
        )
    )
