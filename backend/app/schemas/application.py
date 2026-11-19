from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.db.enums import (
    ApplicationStatus,
    EmploymentType,
    EventType,
    SalaryPeriod,
    WorkMode,
)
from app.schemas.common import ORMModel


class ApplicationCreate(BaseModel):
    company_id: str
    title: str = Field(min_length=1, max_length=250)
    jd_id: str | None = None
    resume_version_id: str | None = None
    location: str | None = Field(default=None, max_length=200)
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    job_url: str | None = Field(default=None, max_length=1000)
    status: ApplicationStatus = ApplicationStatus.SAVED
    applied_on: date | None = None
    salary_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=20_000)
    follow_up_on: date | None = None
    duplicate_override: bool = False

    @model_validator(mode="after")
    def _checks(self) -> ApplicationCreate:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("Minimum salary cannot exceed maximum salary.")
        if self.status not in {ApplicationStatus.SAVED, ApplicationStatus.APPLIED}:
            raise ValueError("New applications start as 'saved' or 'applied'.")
        if self.status == ApplicationStatus.APPLIED and self.applied_on is None:
            self.applied_on = date.today()
        if self.follow_up_on and self.applied_on and self.follow_up_on < self.applied_on:
            raise ValueError("Follow-up date cannot be before the application date.")
        return self


class ApplicationUpdate(BaseModel):
    company_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=250)
    jd_id: str | None = None
    resume_version_id: str | None = None
    location: str | None = Field(default=None, max_length=200)
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    job_url: str | None = Field(default=None, max_length=1000)
    applied_on: date | None = None
    salary_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    salary_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    salary_period: SalaryPeriod | None = None
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=20_000)
    follow_up_on: date | None = None
    rejection_reason: str | None = Field(default=None, max_length=20_000)
    offer_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    offer_deadline: date | None = None


class StatusChangeRequest(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=500)


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class CompanyRef(ORMModel):
    id: str
    name: str


class JobRef(ORMModel):
    id: str
    title: str


class ResumeVersionRef(ORMModel):
    id: str
    version_no: int
    label: str | None


class ApplicationView(ORMModel):
    id: str
    title: str
    status: ApplicationStatus
    location: str | None
    work_mode: WorkMode | None
    employment_type: EmploymentType | None
    job_url: str | None
    applied_on: date | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    source: str | None
    follow_up_on: date | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    company: CompanyRef
    job_description: JobRef | None = None
    resume_version: ResumeVersionRef | None = None


class TimelineEvent(ORMModel):
    id: str
    type: EventType
    from_status: str | None
    to_status: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class ApplicationDetail(ApplicationView):
    notes: str | None
    rejection_reason: str | None
    offer_amount: Decimal | None
    offer_deadline: date | None
    jd_id: str | None = None
    resume_version_id: str | None = None
    events: list[TimelineEvent] = Field(default_factory=list)


class KanbanColumn(BaseModel):
    status: ApplicationStatus
    count: int
    items: list[ApplicationView]


class KanbanBoard(BaseModel):
    columns: list[KanbanColumn]


class DuplicateWarning(BaseModel):
    code: Literal["duplicate_application"] = "duplicate_application"
    message: str
    matches: list[ApplicationView]
