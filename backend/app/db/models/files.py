from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import utcnow
from app.db.base import Base, UuidPkMixin, enum_column, timestamp_column
from app.db.enums import FileKind


class FileObject(UuidPkMixin, Base):
    """Metadata for a private file on disk. Bytes are never served without auth."""

    __tablename__ = "file_object"
    __table_args__ = (Index("ix_file_object_owner_kind", "owner_id", "kind"),)

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("owner.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[FileKind] = mapped_column(
        enum_column(FileKind),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(timestamp_column(), nullable=False, default=utcnow)
