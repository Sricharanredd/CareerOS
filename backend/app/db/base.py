"""Declarative base, naming conventions and shared column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import MetaData, String
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.security import utcnow

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def new_uuid() -> str:
    return str(uuid.uuid4())


def enum_column(enum_cls: type[StrEnum], *, length: int = 32) -> Any:
    """VARCHAR + CHECK persisting the enum *value* (lowercase), never the member name.

    Storing values matters: CHECK constraints in the schema reference literals such as
    'done', and MySQL Workbench shows lowercase values that match the API payloads.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


class UuidPkMixin:
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
        comment="UUID v4",
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6), nullable=False, default=utcnow, onupdate=utcnow
    )


def timestamp_column() -> MySQLDateTime:
    return MySQLDateTime(fsp=6)


def utc_datetime() -> datetime:
    return utcnow()
