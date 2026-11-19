from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def count_of(db: Session, stmt: Select[Any]) -> int:
    subquery = stmt.order_by(None).subquery()
    return int(db.scalar(select(func.count()).select_from(subquery)) or 0)


def paginate(db: Session, stmt: Select[Any], *, page: int, page_size: int) -> tuple[list[Any], int]:
    total = count_of(db, stmt)
    items = list(db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique().all())
    return items, total
