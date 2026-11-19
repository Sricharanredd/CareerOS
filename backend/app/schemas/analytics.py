from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.analysis import ResumeScore
from app.schemas.dashboard import CompanyCount, ConversionMetric, StatusCount


class SourceCount(BaseModel):
    source: str
    count: int


class WeeklyPoint(BaseModel):
    week: date
    count: int


class MonthlyPoint(BaseModel):
    month: date
    count: int


class WeeklyMinutes(BaseModel):
    week: date
    minutes: int


class FollowUpPerformance(BaseModel):
    total_due: int
    completed_on_time: int
    completed: int
    skipped: int
    pending: int
    pending_overdue: int
    rate: float | None
    label: str


class AnalysisHistoryPoint(BaseModel):
    job_id: str
    score: int
    created_at: datetime
    resume_version_id: str
    resume_name: str
    version_no: int
    label: str | None
    jd_title: str | None


class AnalyticsResponse(BaseModel):
    generated_at: datetime
    total_applications: int
    active_applications: int
    submitted: int
    by_status: list[StatusCount]
    by_company: list[CompanyCount]
    by_source: list[SourceCount]
    response: ConversionMetric
    interview_conversion: ConversionMetric
    offer_conversion: ConversionMetric
    applications_weekly: list[WeeklyPoint]
    applications_monthly: list[MonthlyPoint]
    average_days_to_response: float | None
    follow_up_performance: FollowUpPerformance
    tasks_completed_weekly: list[WeeklyPoint]
    time_logged_weekly: list[WeeklyMinutes]
    analysis_history: list[AnalysisHistoryPoint]
    resume_alignment: list[ResumeScore]
    average_alignment: float | None
