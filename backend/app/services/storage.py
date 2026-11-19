"""Private file storage: signature sniffing, size caps, text extraction."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import FileKind
from app.db.models import FileObject

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"

MAX_TEXT_CHARS = 400_000


@dataclass(frozen=True)
class Sniffed:
    mime: str
    extension: str


def _sniff(prefix: bytes, payload: bytes, filename: str) -> Sniffed:
    if prefix.startswith(PDF_MAGIC):
        return Sniffed("application/pdf", "pdf")
    if prefix.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise UnprocessableError("The uploaded archive is corrupt.") from exc
        if "word/document.xml" in names:
            return Sniffed(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
            )
        raise UnprocessableError("Only DOCX documents are supported for zipped uploads.")
    if b"\x00" in prefix:
        raise UnprocessableError("The file looks binary. Upload a PDF, DOCX or TXT file.")
    try:
        payload.decode("utf-8")
        return Sniffed("text/plain", "txt")
    except UnicodeDecodeError:
        try:
            payload.decode("cp1252")
            return Sniffed("text/plain", "txt")
        except UnicodeDecodeError as exc:
            raise UnprocessableError(
                f"Could not read '{filename}' as text. Use UTF-8, PDF or DOCX."
            ) from exc


def save_upload(
    db: Session, *, owner_id: str, kind: FileKind, upload: UploadFile
) -> tuple[FileObject, bytes]:
    settings = get_settings()
    limit = settings.max_upload_bytes

    buffer = bytearray()
    size = 0
    while chunk := upload.file.read(64 * 1024):
        size += len(chunk)
        if size > limit:
            raise PayloadTooLargeError(
                f"File exceeds the {limit // (1024 * 1024)} MB limit.",
                details={"max_bytes": limit},
            )
        buffer.extend(chunk)

    payload = bytes(buffer)
    if not payload:
        raise UnprocessableError("The uploaded file is empty.")

    sniffed = _sniff(payload[:8], payload, upload.filename or "upload")

    storage_dir = settings.storage_path / kind.value
    storage_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload + utcnow().isoformat().encode()).hexdigest()[:32]
    generated = f"{digest}.{sniffed.extension}"
    target = storage_dir / generated
    target.write_bytes(payload)

    original_name = Path(upload.filename or f"upload.{sniffed.extension}").name[:255]
    file_object = FileObject(
        owner_id=owner_id,
        storage_key=f"{kind.value}/{generated}",
        original_name=original_name,
        mime=sniffed.mime,
        size_bytes=size,
        sha256=hashlib.sha256(payload).hexdigest(),
        kind=kind,
        created_at=utcnow(),
    )
    db.add(file_object)
    db.flush()
    return file_object, payload


def absolute_path(file_object: FileObject) -> Path:
    settings = get_settings()
    storage_root = settings.storage_path.resolve()
    candidate = (storage_root / file_object.storage_key).resolve()
    if storage_root not in candidate.parents:
        raise UnprocessableError("Invalid file reference.")
    if not candidate.exists():
        raise UnprocessableError("The stored file is missing from disk.")
    return candidate


def extract_text(file_object: FileObject, payload: bytes | None = None) -> str:
    if payload is None:
        payload = absolute_path(file_object).read_bytes()

    if file_object.mime == "application/pdf":
        text = _extract_pdf(payload)
    elif file_object.mime.endswith("wordprocessingml.document"):
        text = _extract_docx(payload)
    else:
        text = _decode_text(payload)

    text = text.replace("\x00", "").strip()
    return text[:MAX_TEXT_CHARS]


def _extract_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as exc:
        raise UnprocessableError(
            "The PDF could not be read. It may be encrypted or corrupted."
        ) from exc


def _extract_docx(payload: bytes) -> str:
    try:
        import docx

        document = docx.Document(io.BytesIO(payload))
        blocks = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(blocks)
    except Exception as exc:
        raise UnprocessableError("The DOCX document could not be read.") from exc


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def delete_file(file_object: FileObject) -> None:
    try:
        absolute_path(file_object).unlink(missing_ok=True)
    except UnprocessableError:
        return
