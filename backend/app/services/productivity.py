"""Business rules for tasks, follow-ups, interviews and time entries."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import FollowUpStatus, InterviewOutcome, TaskStatus
from app.db.models import Application, FollowUp, Interview, Task, TimeEntry
from app.repositories import productivity as repo
from app.schemas.productivity import (
    ApplicationRef,
    FollowUpCreate,
    FollowUpUpdate,
    FollowUpView,
    InterviewCreate,
    InterviewUpdate,
    InterviewView,
    TaskCreate,
    TaskUpdate,
    TaskView,
    TimeEntryCreate,
    TimeEntryUpdate,
    TimeEntryView,
)
from app.services import audit


def _today() -> date:
    return date.today()


def _now() -> datetime:
    return utcnow()


# --- tasks -----------------------------------------------------------------


def create_task(db: Session, owner_id: str, payload: TaskCreate) -> Task:
    application = _application(db, owner_id, payload.application_id)
    task = Task(
        owner_id=owner_id,
        application_id=application.id if application else None,
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        due_on=payload.due_on,
    )
    db.add(task)
    db.flush()
    audit.record(db, owner_id=owner_id, action="task.create", entity="task", entity_id=task.id)
    return repo.get_task(db, owner_id, task.id) or task


def update_task(db: Session, owner_id: str, task_id: str, payload: TaskUpdate) -> Task:
    task = get_task(db, owner_id, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if "application_id" in changes:
        application = _application(db, owner_id, changes["application_id"])
        task.application_id = application.id if application else None
    if "title" in changes and changes["title"] is not None:
        task.title = changes["title"].strip()
    for field in ("description", "priority", "due_on"):
        if field in changes:
            setattr(task, field, changes[field])
    if "status" in changes and changes["status"] is not None:
        task.status = changes["status"]
        if task.status == TaskStatus.DONE and task.completed_at is None:
            task.completed_at = _now()
        elif task.status != TaskStatus.DONE:
            task.completed_at = None
    audit.record(db, owner_id=owner_id, action="task.update", entity="task", entity_id=task.id)
    db.flush()
    return repo.get_task(db, owner_id, task.id) or task


def complete_task(db: Session, owner_id: str, task_id: str, *, completed: bool) -> Task:
    task = get_task(db, owner_id, task_id)
    task.status = TaskStatus.DONE if completed else TaskStatus.TODO
    task.completed_at = _now() if completed else None
    audit.record(db, owner_id=owner_id, action="task.complete", entity="task", entity_id=task.id)
    db.flush()
    return repo.get_task(db, owner_id, task.id) or task


def get_task(db: Session, owner_id: str, task_id: str) -> Task:
    task = repo.get_task(db, owner_id, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    return task


def delete_task(db: Session, owner_id: str, task_id: str) -> None:
    task = get_task(db, owner_id, task_id)
    db.delete(task)
    db.flush()
    audit.record(db, owner_id=owner_id, action="task.delete", entity="task", entity_id=task_id)


def task_view(task: Task) -> TaskView:
    application = task.application
    return TaskView(
        id=task.id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        status=task.status,
        due_on=task.due_on,
        completed_at=task.completed_at,
        is_overdue=(
            task.status != TaskStatus.DONE and task.due_on is not None and task.due_on < _today()
        ),
        application=_application_ref(application) if application else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# --- follow-ups ------------------------------------------------------------


def create_follow_up(db: Session, owner_id: str, payload: FollowUpCreate) -> FollowUp:
    application = _application(db, owner_id, payload.application_id, required=True)
    follow_up = FollowUp(
        application_id=application.id,
        due_on=payload.due_on,
        channel=payload.channel,
        status=FollowUpStatus.PENDING,
        notes=payload.notes,
    )
    db.add(follow_up)
    db.flush()
    audit.record(
        db,
        owner_id=owner_id,
        action="follow_up.create",
        entity="follow_up",
        entity_id=follow_up.id,
    )
    return repo.get_follow_up(db, owner_id, follow_up.id) or follow_up


def update_follow_up(
    db: Session, owner_id: str, follow_up_id: str, payload: FollowUpUpdate
) -> FollowUp:
    follow_up = get_follow_up(db, owner_id, follow_up_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("due_on", "channel", "notes"):
        if field in changes:
            setattr(follow_up, field, changes[field])
    if "status" in changes and changes["status"] is not None:
        follow_up.status = changes["status"]
        if follow_up.status == FollowUpStatus.DONE:
            follow_up.done_at = follow_up.done_at or _now()
        else:
            follow_up.done_at = None
    audit.record(
        db,
        owner_id=owner_id,
        action="follow_up.update",
        entity="follow_up",
        entity_id=follow_up.id,
    )
    db.flush()
    return repo.get_follow_up(db, owner_id, follow_up.id) or follow_up


def get_follow_up(db: Session, owner_id: str, follow_up_id: str) -> FollowUp:
    follow_up = repo.get_follow_up(db, owner_id, follow_up_id)
    if follow_up is None:
        raise NotFoundError("Follow-up not found.")
    return follow_up


def delete_follow_up(db: Session, owner_id: str, follow_up_id: str) -> None:
    follow_up = get_follow_up(db, owner_id, follow_up_id)
    db.delete(follow_up)
    db.flush()
    audit.record(
        db, owner_id=owner_id, action="follow_up.delete", entity="follow_up", entity_id=follow_up_id
    )


def follow_up_view(follow_up: FollowUp) -> FollowUpView:
    return FollowUpView(
        id=follow_up.id,
        application=_application_ref(follow_up.application),
        due_on=follow_up.due_on,
        channel=follow_up.channel,
        status=follow_up.status,
        done_at=follow_up.done_at,
        is_overdue=follow_up.status == FollowUpStatus.PENDING and follow_up.due_on < _today(),
        notes=follow_up.notes,
        created_at=follow_up.created_at,
        updated_at=follow_up.updated_at,
    )


# --- interviews ------------------------------------------------------------


def create_interview(db: Session, owner_id: str, payload: InterviewCreate) -> Interview:
    application = _application(db, owner_id, payload.application_id, required=True)
    interview = Interview(
        application_id=application.id,
        round_no=payload.round_no or repo.next_round(db, application.id),
        type=payload.type,
        scheduled_at=payload.scheduled_at,
        timezone=payload.timezone,
        interviewer=payload.interviewer,
        location=payload.location,
        link=payload.link,
        prep_notes=payload.prep_notes,
        outcome=InterviewOutcome.PENDING,
    )
    db.add(interview)
    db.flush()
    audit.record(
        db,
        owner_id=owner_id,
        action="interview.create",
        entity="interview",
        entity_id=interview.id,
    )
    return repo.get_interview(db, owner_id, interview.id) or interview


def update_interview(
    db: Session, owner_id: str, interview_id: str, payload: InterviewUpdate
) -> Interview:
    interview = get_interview(db, owner_id, interview_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in (
        "round_no",
        "type",
        "scheduled_at",
        "timezone",
        "interviewer",
        "location",
        "link",
        "prep_notes",
        "outcome",
        "feedback",
    ):
        if field in changes and changes[field] is not None:
            setattr(interview, field, changes[field])
    if "outcome" in changes and changes["outcome"] is None:
        interview.outcome = InterviewOutcome.PENDING
    audit.record(
        db,
        owner_id=owner_id,
        action="interview.update",
        entity="interview",
        entity_id=interview.id,
    )
    db.flush()
    return repo.get_interview(db, owner_id, interview.id) or interview


def get_interview(db: Session, owner_id: str, interview_id: str) -> Interview:
    interview = repo.get_interview(db, owner_id, interview_id)
    if interview is None:
        raise NotFoundError("Interview not found.")
    return interview


def delete_interview(db: Session, owner_id: str, interview_id: str) -> None:
    interview = get_interview(db, owner_id, interview_id)
    db.delete(interview)
    db.flush()
    audit.record(
        db, owner_id=owner_id, action="interview.delete", entity="interview", entity_id=interview_id
    )


def interview_view(interview: Interview) -> InterviewView:
    return InterviewView(
        id=interview.id,
        application=_application_ref(interview.application),
        round_no=interview.round_no,
        type=interview.type,
        scheduled_at=interview.scheduled_at,
        timezone=interview.timezone,
        interviewer=interview.interviewer,
        location=interview.location,
        link=interview.link,
        prep_notes=interview.prep_notes,
        outcome=interview.outcome,
        feedback=interview.feedback,
        is_upcoming=interview.scheduled_at >= _now(),
        created_at=interview.created_at,
        updated_at=interview.updated_at,
    )


# --- time entries ----------------------------------------------------------


def create_time_entry(db: Session, owner_id: str, payload: TimeEntryCreate) -> TimeEntry:
    task = _task(db, owner_id, payload.task_id)
    if task is not None and payload.task_id:
        _ensure_no_overlap(
            db,
            owner_id,
            task_id=payload.task_id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
        )
    entry = TimeEntry(
        owner_id=owner_id,
        task_id=task.id if task else None,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        notes=payload.notes,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        owner_id=owner_id,
        action="time_entry.create",
        entity="time_entry",
        entity_id=entry.id,
    )
    return repo.get_time_entry(db, owner_id, entry.id) or entry


def update_time_entry(
    db: Session, owner_id: str, entry_id: str, payload: TimeEntryUpdate
) -> TimeEntry:
    entry = get_time_entry(db, owner_id, entry_id)
    changes = payload.model_dump(exclude_unset=True)
    if "task_id" in changes:
        task = _task(db, owner_id, changes["task_id"])
        entry.task_id = task.id if task else None
    if "started_at" in changes and changes["started_at"] is not None:
        entry.started_at = changes["started_at"]
    if "ended_at" in changes:
        entry.ended_at = changes["ended_at"]
    if "notes" in changes:
        entry.notes = changes["notes"]
    if entry.ended_at is not None and entry.ended_at <= entry.started_at:
        raise UnprocessableError("The end time must be after the start time.")
    if entry.task_id:
        _ensure_no_overlap(
            db,
            owner_id,
            task_id=entry.task_id,
            started_at=entry.started_at,
            ended_at=entry.ended_at,
            exclude_id=entry.id,
        )
    audit.record(
        db,
        owner_id=owner_id,
        action="time_entry.update",
        entity="time_entry",
        entity_id=entry.id,
    )
    db.flush()
    return repo.get_time_entry(db, owner_id, entry.id) or entry


def get_time_entry(db: Session, owner_id: str, entry_id: str) -> TimeEntry:
    entry = repo.get_time_entry(db, owner_id, entry_id)
    if entry is None:
        raise NotFoundError("Time entry not found.")
    return entry


def delete_time_entry(db: Session, owner_id: str, entry_id: str) -> None:
    entry = get_time_entry(db, owner_id, entry_id)
    db.delete(entry)
    db.flush()
    audit.record(
        db, owner_id=owner_id, action="time_entry.delete", entity="time_entry", entity_id=entry_id
    )


def time_entry_view(entry: TimeEntry) -> TimeEntryView:
    duration = None
    if entry.ended_at is not None:
        duration = round((entry.ended_at - entry.started_at).total_seconds() / 60, 1)
    return TimeEntryView(
        id=entry.id,
        task_id=entry.task_id,
        task_title=entry.task.title if entry.task else None,
        started_at=entry.started_at,
        ended_at=entry.ended_at,
        duration_minutes=duration,
        notes=entry.notes,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


# --- helpers ---------------------------------------------------------------


def _application(
    db: Session, owner_id: str, application_id: str | None, *, required: bool = False
) -> Application | None:
    if not application_id:
        if required:
            raise UnprocessableError("Choose an application.", code="application_required")
        return None
    application = db.get(Application, application_id)
    if application is None or application.owner_id != owner_id:
        raise UnprocessableError("That application does not exist.", code="invalid_application")
    return application


def _task(db: Session, owner_id: str, task_id: str | None) -> Task | None:
    if not task_id:
        return None
    task = repo.get_task(db, owner_id, task_id)
    if task is None:
        raise UnprocessableError("That task does not exist.", code="invalid_task")
    return task


def _ensure_no_overlap(
    db: Session,
    owner_id: str,
    *,
    task_id: str,
    started_at: datetime,
    ended_at: datetime | None,
    exclude_id: str | None = None,
) -> None:
    if repo.overlapping_entry(
        db,
        owner_id,
        task_id=task_id,
        started_at=started_at,
        ended_at=ended_at,
        exclude_id=exclude_id,
    ):
        raise UnprocessableError(
            "This time entry overlaps another entry for the same task.",
            code="time_overlap",
        )


def _application_ref(application: Application) -> ApplicationRef:
    return ApplicationRef(
        id=application.id,
        title=application.title,
        company_name=application.company.name if application.company else "",
    )


def summary(db: Session, owner_id: str) -> dict[str, int]:
    from app.repositories import dashboard as dashboard_repo

    tasks = dashboard_repo.task_summary(db, owner_id)
    follow_ups = dashboard_repo.follow_up_summary(db, owner_id)
    interviews = repo.interview_counts(db, owner_id, now=_now())
    return {
        "tasks_pending": tasks["pending"],
        "tasks_overdue": tasks["overdue"],
        "tasks_due_today": tasks["due_today"],
        "tasks_completed_this_week": tasks["completed_this_week"],
        "follow_ups_due_today": follow_ups["due_today"],
        "follow_ups_overdue": follow_ups["overdue"],
        "follow_ups_upcoming": follow_ups["upcoming"],
        "follow_ups_completed": follow_ups["completed"],
        "interviews_upcoming": interviews["upcoming"],
        "interviews_pending_outcome": interviews["pending_outcome"],
    }
