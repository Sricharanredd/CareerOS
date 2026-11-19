from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import ApplicationStatus, EventType
from app.db.models import Application, Company, JobDescription, ResumeVersion
from app.repositories import application as app_repo
from app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationView,
    StatusChangeRequest,
)
from app.services import audit

EDITABLE_FIELDS = (
    "title",
    "location",
    "employment_type",
    "work_mode",
    "job_url",
    "applied_on",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "source",
    "notes",
    "follow_up_on",
    "rejection_reason",
    "offer_amount",
    "offer_deadline",
)


def create(db: Session, owner_id: str, payload: ApplicationCreate) -> Application:
    company, jd, version = _references(
        db,
        owner_id,
        company_id=payload.company_id,
        jd_id=payload.jd_id,
        resume_version_id=payload.resume_version_id,
    )

    duplicates = app_repo.find_duplicates(
        db,
        owner_id,
        company_id=payload.company_id,
        title=payload.title,
        applied_on=payload.applied_on,
    )
    if duplicates and not payload.duplicate_override:
        raise ConflictError(
            "A similar application already exists. Review it, or confirm to add anyway.",
            code="duplicate_application",
            details={
                "matches": [
                    ApplicationView.model_validate(match).model_dump(mode="json")
                    for match in duplicates
                ]
            },
        )

    data: dict[str, Any] = payload.model_dump(
        exclude={"duplicate_override", "company_id", "jd_id", "resume_version_id", "status"}
    )
    data.update(
        company_id=company.id,
        jd_id=jd.id if jd else None,
        resume_version_id=version.id if version else None,
        status=ApplicationStatus(payload.status),
    )
    if data["status"] == ApplicationStatus.APPLIED and data.get("applied_on") is None:
        from datetime import date

        data["applied_on"] = date.today()

    application = app_repo.create(db, owner_id=owner_id, data=data)
    app_repo.add_event(
        db,
        application_id=application.id,
        event_type=EventType.CREATED,
        to_status=str(application.status),
        payload={"status": str(application.status)},
    )
    audit.record(
        db,
        owner_id=owner_id,
        action="application.create",
        entity="application",
        entity_id=application.id,
    )
    db.flush()
    return application


def get(db: Session, owner_id: str, app_id: str) -> Application:
    application = app_repo.get_with_events(db, owner_id, app_id)
    if application is None:
        raise NotFoundError("Application not found.")
    return application


def update(db: Session, owner_id: str, app_id: str, payload: ApplicationUpdate) -> Application:
    application = app_repo.get(db, owner_id, app_id)
    if application is None:
        raise NotFoundError("Application not found.")
    if application.archived_at is not None:
        raise ConflictError("Restore this application before editing it.", code="archived")

    changes = payload.model_dump(exclude_unset=True)
    if "salary_min" in changes or "salary_max" in changes:
        low = changes.get("salary_min", application.salary_min)
        high = changes.get("salary_max", application.salary_max)
        if low is not None and high is not None and low > high:
            raise UnprocessableError("Minimum salary cannot exceed maximum salary.")

    if changes.get("company_id"):
        _references(
            db,
            owner_id,
            company_id=changes["company_id"],
            jd_id=changes.get("jd_id", application.jd_id),
            resume_version_id=changes.get("resume_version_id", application.resume_version_id),
        )

    changed: list[str] = []
    for field in (*EDITABLE_FIELDS, "company_id", "jd_id", "resume_version_id"):
        if field in changes:
            new_value = changes[field]
            if getattr(application, field) != new_value:
                setattr(application, field, new_value)
                changed.append(field)

    if changed:
        app_repo.add_event(
            db,
            application_id=application.id,
            event_type=EventType.UPDATED,
            payload={"fields": sorted(changed)},
        )
        audit.record(
            db,
            owner_id=owner_id,
            action="application.update",
            entity="application",
            entity_id=application.id,
        )
    db.flush()
    return application


def change_status(
    db: Session, owner_id: str, app_id: str, payload: StatusChangeRequest
) -> Application:
    from app.db.enums import ALLOWED_TRANSITIONS

    application = app_repo.get(db, owner_id, app_id)
    if application is None:
        raise NotFoundError("Application not found.")
    if application.archived_at is not None:
        raise ConflictError("Restore this application before changing its status.", code="archived")

    current = ApplicationStatus(application.status)
    target = ApplicationStatus(payload.status)
    if target == current:
        raise ConflictError(f"Application is already in '{target}'.", code="no_change")
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ConflictError(
            f"Cannot move an application from '{current}' to '{target}'.",
            code="invalid_transition",
            details={
                "from": str(current),
                "to": str(target),
                "allowed": sorted(str(s) for s in allowed),
            },
        )

    if target == ApplicationStatus.APPLIED and application.applied_on is None:
        from datetime import date

        application.applied_on = date.today()
    if target == ApplicationStatus.ACCEPTED and application.offer_amount is None:
        pass  # accepted without a recorded amount is valid

    application.status = target
    if payload.note:
        if target == ApplicationStatus.REJECTED:
            application.rejection_reason = payload.note
        else:
            application.notes = (
                application.notes or ""
            ) + f"\n[{utcnow():%Y-%m-%d}] {payload.note}"

    app_repo.add_event(
        db,
        application_id=application.id,
        event_type=EventType.STATUS_CHANGE,
        from_status=str(current),
        to_status=str(target),
        payload={"note": payload.note} if payload.note else None,
    )
    audit.record(
        db,
        owner_id=owner_id,
        action="application.status",
        entity="application",
        entity_id=application.id,
        detail=f"{current}->{target}",
    )
    db.flush()
    return application


def set_archived(db: Session, owner_id: str, app_id: str, archived: bool) -> Application:
    application = app_repo.get(db, owner_id, app_id)
    if application is None:
        raise NotFoundError("Application not found.")
    application.archived_at = utcnow() if archived else None
    app_repo.add_event(
        db,
        application_id=application.id,
        event_type=EventType.ARCHIVED if archived else EventType.UPDATED,
        payload={"archived": archived},
    )
    db.flush()
    return application


def delete(db: Session, owner_id: str, app_id: str) -> None:
    application = app_repo.get(db, owner_id, app_id)
    if application is None:
        raise NotFoundError("Application not found.")
    db.delete(application)
    db.flush()
    audit.record(
        db,
        owner_id=owner_id,
        action="application.delete",
        entity="application",
        entity_id=app_id,
    )


def _references(
    db: Session,
    owner_id: str,
    *,
    company_id: str,
    jd_id: str | None,
    resume_version_id: str | None,
) -> tuple[Company, JobDescription | None, ResumeVersion | None]:
    company, jd, version = app_repo.validate_references(
        db, owner_id, company_id=company_id, jd_id=jd_id, resume_version_id=resume_version_id
    )
    if company is None:
        raise UnprocessableError(
            "Select a company that belongs to this account.", code="invalid_company"
        )
    if jd_id and jd is None:
        raise UnprocessableError("That job description does not exist.", code="invalid_jd")
    if resume_version_id and version is None:
        raise UnprocessableError("That resume version does not exist.", code="invalid_resume")
    return company, jd, version
