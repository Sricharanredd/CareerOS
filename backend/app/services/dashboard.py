from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.enums import ApplicationStatus
from app.repositories import dashboard as repo
from app.schemas.dashboard import (
    ActivityItem,
    CompanyCount,
    ConversionMetric,
    DashboardResponse,
    FollowUpSummary,
    StatusCount,
    TaskSummary,
    TrendPoint,
    UpcomingInterview,
)


def build(db: Session, owner_id: str) -> DashboardResponse:
    status_counts = repo.status_counts(db, owner_id)
    total, active, archived = repo.totals(db, owner_id)
    conversions = repo.conversions(db, owner_id)
    follow_ups = repo.follow_up_summary(db, owner_id)
    tasks = repo.task_summary(db, owner_id)
    interviews_scheduled = repo.interviews_scheduled(db, owner_id, now=_now())
    week_count, month_count = repo.applied_counts(db, owner_id)

    offers = status_counts.get(str(ApplicationStatus.OFFER), 0) + status_counts.get(
        str(ApplicationStatus.ACCEPTED), 0
    )
    rejections = status_counts.get(str(ApplicationStatus.REJECTED), 0)

    return DashboardResponse(
        total_applications=total,
        active_applications=active,
        archived_applications=archived,
        by_status=[
            StatusCount(status=status, count=status_counts.get(str(status), 0))
            for status in ApplicationStatus
        ],
        by_company=[
            CompanyCount(company_id=cid, company_name=name, count=count)
            for cid, name, count in repo.company_counts(db, owner_id)
        ],
        offers=offers,
        rejections=rejections,
        interviews_scheduled=interviews_scheduled,
        response=_metric(
            conversions["responded"], conversions["submitted"], "applications answered"
        ),
        interview_conversion=_metric(
            conversions["interviewed"],
            conversions["submitted"],
            "applications reaching an interview",
        ),
        offer_conversion=_metric(
            conversions["offered"], conversions["interviewed"], "interviews producing an offer"
        ),
        follow_ups=FollowUpSummary(**follow_ups),
        tasks=TaskSummary(**tasks),
        upcoming_interviews=[
            UpcomingInterview(**row) for row in repo.upcoming_interviews(db, owner_id, now=_now())
        ],
        recent_activity=[ActivityItem(**row) for row in repo.recent_activity(db, owner_id)],
        applications_trend=_trend(db, owner_id),
        average_days_to_response=(
            round(value, 1)
            if (value := repo.average_days_to_response(db, owner_id)) is not None
            else None
        ),
        applied_this_week=week_count,
        applied_this_month=month_count,
    )


def _metric(numerator: int, denominator: int, label: str) -> ConversionMetric:
    rate = round(numerator / denominator, 4) if denominator else None
    return ConversionMetric(numerator=numerator, denominator=denominator, rate=rate, label=label)


def _trend(db: Session, owner_id: str, weeks: int = 12) -> list[TrendPoint]:
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    first_monday = current_monday - timedelta(weeks=weeks - 1)
    daily = dict(repo.daily_applications(db, owner_id, since=first_monday))

    points: list[TrendPoint] = []
    for index in range(weeks):
        start = first_monday + timedelta(weeks=index)
        end = start + timedelta(days=6)
        count = sum(value for day, value in daily.items() if start <= day <= end)
        points.append(TrendPoint(bucket=start, count=count))
    return points


def _now():
    from app.core.security import utcnow

    return utcnow()
