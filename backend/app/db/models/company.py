from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPkMixin, timestamp_column

if TYPE_CHECKING:
    from app.db.models.application import Application
    from app.db.models.job import JobDescription


class Company(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "company"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_company_owner_id_name"),
        Index("ix_company_owner_archived", "owner_id", "archived_at"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(timestamp_column())

    job_descriptions: Mapped[list[JobDescription]] = relationship(back_populates="company")
    applications: Mapped[list[Application]] = relationship(back_populates="company")
