from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.enums import Theme
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    owner: OwnerProfile


class OwnerProfile(ORMModel):
    id: str
    email: str
    full_name: str | None
    timezone: str
    currency: str
    theme: Theme
    last_login_at: datetime | None
    created_at: datetime


class OwnerUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    theme: Theme | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, value: str) -> str:
        classes = sum(
            (
                any(c.islower() for c in value),
                any(c.isupper() for c in value),
                any(c.isdigit() for c in value),
                any(not c.isalnum() for c in value),
            )
        )
        if classes < 3:
            raise ValueError(
                "Use at least 12 characters mixing upper case, lower case, digits and symbols."
            )
        return value


class SessionView(ORMModel):
    id: str
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None
    current: bool = False


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str


class MetaResponse(BaseModel):
    app_name: str
    owner_configured: bool
    ai_configured: bool
    environment: str
    version: str


TokenResponse.model_rebuild()
