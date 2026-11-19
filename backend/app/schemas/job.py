from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class CompanyRef(ORMModel):
    id: str
    name: str


class JobDescriptionCreate(BaseModel):
    company_id: str
    title: str = Field(min_length=1, max_length=250)
    location: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    raw_text: str = Field(default="", max_length=200_000)
    notes: str | None = Field(default=None, max_length=20_000)
    seniority: str | None = Field(default=None, max_length=64)
    employment_type: str | None = Field(default=None, max_length=32)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    responsibilities: list[str] | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Job title is required.")
        return value

    @field_validator("required_skills", "preferred_skills", "responsibilities")
    @classmethod
    def _clean_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned or None


class JobDescriptionUpdate(BaseModel):
    company_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=250)
    location: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    raw_text: str | None = Field(default=None, max_length=200_000)
    notes: str | None = Field(default=None, max_length=20_000)
    seniority: str | None = Field(default=None, max_length=64)
    employment_type: str | None = Field(default=None, max_length=32)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    responsibilities: list[str] | None = None


class JobDescriptionView(ORMModel):
    id: str
    title: str
    location: str | None
    url: str | None
    raw_text: str
    seniority: str | None
    employment_type: str | None
    required_skills: list[str] | None
    preferred_skills: list[str] | None
    responsibilities: list[str] | None
    notes: str | None
    source_file_id: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    company: CompanyRef


class JobDescriptionListItem(ORMModel):
    id: str
    title: str
    location: str | None
    seniority: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    company: CompanyRef
    text_chars: int = 0


class TextExtractionResponse(BaseModel):
    text: str
    chars: int
    mime: str
    original_name: str
