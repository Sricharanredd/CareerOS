from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FileRef(ORMModel):
    id: str
    original_name: str
    mime: str
    size_bytes: int


class ResumeVersionView(ORMModel):
    id: str
    version_no: int
    label: str | None
    notes: str | None
    created_at: datetime
    file_id: str
    extracted_chars: int = 0
    is_current: bool = False


class ResumeView(ORMModel):
    id: str
    name: str
    headline: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    current_version_no: int | None = None
    current_file_name: str | None = None


class ResumeDetailView(ResumeView):
    versions: list[ResumeVersionView] = Field(default_factory=list)


class ResumeVersionUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=20_000)


class ResumeCreateMeta(BaseModel):
    """Validated part of the multipart create request."""

    name: str = Field(min_length=1, max_length=200)
    headline: str | None = Field(default=None, max_length=250)
    label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=20_000)


class ResumeUsage(BaseModel):
    application_count: int
    analysis_count: int
