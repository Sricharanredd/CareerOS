from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.schemas.common import ORMModel


class CompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Company name is required.")
        return value

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        HttpUrl(value)
        return value


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Company name is required.")
        return value

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        HttpUrl(value)
        return value


class CompanyView(ORMModel):
    id: str
    name: str
    website: str | None
    industry: str | None
    location: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    application_count: int = 0
    job_description_count: int = 0


class CompanyOption(ORMModel):
    id: str
    name: str
    archived_at: datetime | None = None
