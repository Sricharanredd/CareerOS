"""Import every model so Alembic autogenerate and relationship resolution see them."""

from app.db.models.analysis import AnalysisJob, AnalysisResult
from app.db.models.application import Application, ApplicationEvent
from app.db.models.auth import AuditLog, AuthSession, Owner
from app.db.models.company import Company
from app.db.models.files import FileObject
from app.db.models.job import JobDescription
from app.db.models.productivity import FollowUp, Interview, Task, TimeEntry
from app.db.models.resume import Resume, ResumeVersion

__all__ = [
    "AnalysisJob",
    "AnalysisResult",
    "Application",
    "ApplicationEvent",
    "AuditLog",
    "AuthSession",
    "Company",
    "FileObject",
    "FollowUp",
    "Interview",
    "JobDescription",
    "Owner",
    "Resume",
    "ResumeVersion",
    "Task",
    "TimeEntry",
]
