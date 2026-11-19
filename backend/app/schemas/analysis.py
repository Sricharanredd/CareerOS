from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.ai.output import Finding
from app.db.enums import AnalysisStatus


class AnalysisSubmit(BaseModel):
    resume_version_id: str
    jd_id: str | None = None
    jd_text: str | None = Field(default=None, max_length=200_000)

    @model_validator(mode="after")
    def _single_source(self) -> AnalysisSubmit:
        pasted = bool(self.jd_text and self.jd_text.strip())
        if bool(self.jd_id) == pasted:
            raise ValueError(
                "Choose a saved job description or paste job description text, not both."
            )
        return self


class AnalysisResumeRef(BaseModel):
    id: str
    resume_id: str
    resume_name: str
    version_no: int
    label: str | None


class AnalysisJobRef(BaseModel):
    id: str
    title: str
    company_name: str | None = None


class AnalysisResultView(BaseModel):
    score: int
    summary: str
    alignment_explanation: str
    findings: list[Finding]
    schema_version: str
    created_at: datetime


class AnalysisJobView(BaseModel):
    id: str
    status: AnalysisStatus
    resume_version: AnalysisResumeRef
    job_description: AnalysisJobRef | None
    jd_excerpt: str | None
    provider: str
    model: str
    prompt_version: str
    attempts: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    result: AnalysisResultView | None


class AnalysisStats(BaseModel):
    total: int
    succeeded: int
    failed: int
    running: int
    average_score: float | None


class ResumeScore(BaseModel):
    resume_version_id: str
    resume_name: str
    version_no: int
    label: str | None
    analyses: int
    average_score: float
