"""Analytics assembly.

Definitions (also surfaced in the UI):
- response rate: applications with any response / applications submitted
- interview conversion: applications reaching an interview / applications submitted
- offer conversion: offers / applications reaching an interview
- follow-up performance: follow-ups completed on or before their due date / follow-ups due
- every ratio is null when its denominator is zero
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.db.enums import ApplicationStatus
from app.repositories import analysis as analysis_repo
from app.repositories import analytics as repo
from app.repositories import dashboard as dashboard_repo
from app.schemas.analysis import ResumeScore
from app.schemas.analytics import (
    AnalysisHistoryPoint,
    AnalyticsResponse,
    FollowUpPerformance,
    MonthlyPoint,
    SourceCount,
    WeeklyMinutes,
    WeeklyPoint,
)
from app.schemas.dashboard import CompanyCount, ConversionMetric, StatusCount

WEEKS = 12


def build(db: Session, owner_id: str) -> AnalyticsResponse:
    today = date.today()
    status_counts = dashboard_repo.status_counts(db, owner_id)
    total, active, _ = dashboard_repo.totals(db, owner_id)
    conversions = dashboard_repo.conversions(db, owner_id)
    first_monday = _week_start(today) - timedelta(weeks=WEEKS - 1)
    daily = dashboard_repo.daily_applications(db, owner_id, since=first_monday)
    monthly_since = _month_start(_add_months(today, -5))
    daily_for_months = dashboard_repo.daily_applications(db, owner_id, since=monthly_since)
    performance = repo.follow_up_performance(db, owner_id, today=today)
    resume_scores = analysis_repo.resume_scores(db, owner_id)
    average_days = dashboard_repo.average_days_to_response(db, owner_id)

    return AnalyticsResponse(
        generated_at=utcnow(),
        total_applications=total,
        active_applications=active,
        submitted=repo.submitted(db, owner_id),
        by_status=[
            StatusCount(status=status, count=status_counts.get(str(status), 0))
            for status in ApplicationStatus
        ],
        by_company=[
            CompanyCount(company_id=cid, company_name=name, count=count)
            for cid, name, count in dashboard_repo.company_counts(db, owner_id, limit=8)
        ],
        by_source=[SourceCount(**row) for row in repo.by_source(db, owner_id)],
        response=_metric(
            conversions["responded"], conversions["submitted"], "applications answered"
        ),
        interview_conversion=_metric(
            conversions["interviewed"],
            conversions["submitted"],
            "applications reaching an interview",
        ),
        offer_conversion=_metric(
            conversions["offered"],
            conversions["interviewed"],
            "interviews producing an offer",
        ),
        applications_weekly=_weekly(daily, first_monday, WEEKS),
        applications_monthly=_monthly(daily_for_months, monthly_since, 6),
        average_days_to_response=round(average_days, 1) if average_days is not None else None,
        follow_up_performance=_follow_ups(performance),
        tasks_completed_weekly=_weeks_of_counts(
            db,
            owner_id,
            first_monday=first_monday,
        ),
        time_logged_weekly=_weeks_of_minutes(
            db,
            owner_id,
            first_monday=first_monday,
            now=utcnow(),
        ),
        analysis_history=[
            AnalysisHistoryPoint(**row) for row in repo.analysis_history(db, owner_id)
        ],
        resume_alignment=[ResumeScore(**row) for row in resume_scores],
        average_alignment=repo.average_alignment(db, owner_id),
    )


def _metric(numerator: int, denominator: int, label: str) -> ConversionMetric:
    rate = round(numerator / denominator, 4) if denominator else None
    return ConversionMetric(numerator=numerator, denominator=denominator, rate=rate, label=label)


def _follow_ups(data: dict[str, int]) -> FollowUpPerformance:
    denominator = data["total_due"]
    numerator = data["completed_on_time"]
    return FollowUpPerformance(
        **data,
        rate=round(numerator / denominator, 4) if denominator else None,
        label="follow-ups completed on time",
    )


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _weeks_of_counts(db: Session, owner_id: str, *, first_monday: date) -> list[WeeklyPoint]:
    counts = dict(repo.tasks_completed(db, owner_id, since=first_monday))
    points: list[WeeklyPoint] = []
    for index in range(WEEKS):
        start = first_monday + timedelta(weeks=index)
        end = start + timedelta(days=6)
        points.append(
            WeeklyPoint(
                week=start, count=sum(value for day, value in counts.items() if start <= day <= end)
            )
        )
    return points


def _weeks_of_minutes(
    db: Session, owner_id: str, *, first_monday: date, now: datetime
) -> list[WeeklyMinutes]:
    entries = repo.time_entries_since(
        db, owner_id, since=datetime.combine(first_monday, datetime.min.time())
    )
    totals = {index: 0.0 for index in range(WEEKS)}
    for started_at, ended_at in entries:
        index = (started_at.date() - first_monday).days // 7
        if index < 0 or index >= WEEKS:
            continue
        finish = ended_at or now
        if finish <= started_at:
            continue
        totals[index] += (finish - started_at).total_seconds() / 60

    return [
        WeeklyMinutes(
            week=first_monday + timedelta(weeks=index),
            minutes=int(round(totals[index])),
        )
        for index in range(WEEKS)
    ]


def _weekly(daily: list[tuple[date, int]], first_monday: date, weeks: int) -> list[WeeklyPoint]:
    counts = dict(daily)
    points: list[WeeklyPoint] = []
    for index in range(weeks):
        start = first_monday + timedelta(weeks=index)
        end = start + timedelta(days=6)
        points.append(
            WeeklyPoint(
                week=start, count=sum(value for day, value in counts.items() if start <= day <= end)
            )
        )
    return points


def _monthly(daily: list[tuple[date, int]], first_month: date, months: int) -> list[MonthlyPoint]:
    counts = dict(daily)
    points: list[MonthlyPoint] = []
    for index in range(months):
        start = _add_months(first_month, index)
        end = _add_months(start, 1)
        points.append(
            MonthlyPoint(
                month=start,
                count=sum(value for day, value in counts.items() if start <= day < end),
            )
        )
    return points


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)
