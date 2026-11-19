from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    analytics,
    applications,
    auth,
    companies,
    dashboard,
    files,
    follow_ups,
    interviews,
    job_descriptions,
    resumes,
    tasks,
    time_entries,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(job_descriptions.router)
api_router.include_router(applications.router)
api_router.include_router(resumes.router)
api_router.include_router(files.router)
api_router.include_router(analyses.router)
api_router.include_router(tasks.router)
api_router.include_router(follow_ups.router)
api_router.include_router(interviews.router)
api_router.include_router(time_entries.router)
api_router.include_router(analytics.router)
api_router.include_router(dashboard.router)
