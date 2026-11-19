from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.db.enums import ApplicationStatus


class StatusCount(BaseModel):
    status: ApplicationStatus
    count: int


class CompanyCount(BaseModel):
    company_id: str
    company_name: str
    count: int


class ConversionMetric(BaseModel):
    numerator: int
    denominator: int
    rate: float | None
    label: str


class FollowUpSummary(BaseModel):
    due_today: int
    overdue: int
    upcoming: int
    completed: int


class TaskSummary(BaseModel):
    pending: int
    overdue: int
    due_today: int
    completed_this_week: int


class UpcomingInterview(BaseModel):
    id: str
    application_id: str
    application_title: str
    company_name: str
    round_no: int
    type: str
    scheduled_at: datetime
    timezone: str


class ActivityItem(BaseModel):
    id: str
    application_id: str
    application_title: str
    company_name: str
    type: str
    from_status: str | None
    to_status: str | None
    created_at: datetime


class TrendPoint(BaseModel):
    bucket: date
    count: int


class DashboardResponse(BaseModel):
    total_applications: int
    active_applications: int
    archived_applications: int
    by_status: list[StatusCount]
    by_company: list[CompanyCount]
    offers: int
    rejections: int
    interviews_scheduled: int
    response: ConversionMetric
    interview_conversion: ConversionMetric
    offer_conversion: ConversionMetric
    follow_ups: FollowUpSummary
    tasks: TaskSummary
    upcoming_interviews: list[UpcomingInterview]
    recent_activity: list[ActivityItem]
    applications_trend: list[TrendPoint]
    average_days_to_response: float | None
    applied_this_week: int
    applied_this_month: int


class ExportPayload(BaseModel):
    exported_at: datetime
    owner: dict[str, Any]
    companies: list[dict[str, Any]]
    job_descriptions: list[dict[str, Any]]
    resumes: list[dict[str, Any]]
    resume_versions: list[dict[str, Any]]
    applications: list[dict[str, Any]]
    application_events: list[dict[str, Any]]
    interviews: list[dict[str, Any]]
    follow_ups: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    time_entries: list[dict[str, Any]]
    analysis_jobs: list[dict[str, Any]]
    analysis_results: list[dict[str, Any]]
    counts: dict[str, int]
