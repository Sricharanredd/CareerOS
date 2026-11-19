"""Shared schema primitives: pagination, list envelopes, ids."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class IdResponse(BaseModel):
    id: str


class MessageResponse(BaseModel):
    message: str


class ArchiveRequest(BaseModel):
    archived: bool = True


class Timestamped(ORMModel):
    created_at: datetime
    updated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: object | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
