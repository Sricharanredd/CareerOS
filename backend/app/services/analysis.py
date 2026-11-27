"""Analysis orchestration: validation, idempotent submission, background execution."""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, undefer

from app.ai.base import AnalysisRequest, ProviderError, ProviderPrivacyDenied
from app.ai.health import health_store
from app.ai.output import AnalysisOutput
from app.ai.quota import quota_store
from app.ai.registry import get_provider
from app.ai.router import route_and_run
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import utcnow
from app.db.enums import AnalysisStatus
from app.db.models import AnalysisJob, AnalysisResult, JobDescription, Resume, ResumeVersion
from app.db.session import session_scope
from app.repositories import analysis as repo
from app.repositories import job as job_repo
from app.schemas.analysis import (
    AnalysisJobRef,
    AnalysisJobView,
    AnalysisResultView,
    AnalysisResumeRef,
    AnalysisStats,
    AnalysisSubmit,
    ResumeScore,
)
from app.services import audit

logger = logging.getLogger("careeros.analysis")

MIN_TEXT_CHARS = 200
PROMPT_VERSION_FALLBACK = "analysis-v1"
EXCERPT_CHARS = 320
AI_NOT_CONFIGURED = (
    "AI is not available. No configured provider passed the privacy gate: set "
    "AI_APPROVED_PROVIDERS and the matching credentials in backend/.env, then restart the "
    "backend. Resume text is never sent to an unapproved provider."
)


def submit(db: Session, owner_id: str, payload: AnalysisSubmit) -> tuple[AnalysisJob, bool]:
    """Create or reuse a job. Returns (job, created)."""
    version = _load_version(db, owner_id, payload.resume_version_id)
    jd, jd_text, jd_title, company_name = _resolve_jd(db, owner_id, payload)

    _require_text(version.extracted_text, "resume")
    _require_text(jd_text, "job description")

    settings = get_settings()
    try:
        provider = get_provider()
    except ProviderPrivacyDenied as denied:
        provider, denial = None, denied
    else:
        denial = None
    provider_name = provider.name if provider else ""
    model = provider.model if provider else ""
    prompt_version = settings.prompt_version or PROMPT_VERSION_FALLBACK
    text_hash = _sha(jd_text)
    input_hash = _sha(
        "|".join(
            [version.id, jd.id if jd else "pasted", text_hash, prompt_version, provider_name, model]
        )
    )

    existing = repo.get_by_hash(db, owner_id, input_hash)
    if existing is not None and existing.status in {
        AnalysisStatus.QUEUED,
        AnalysisStatus.RUNNING,
        AnalysisStatus.SUCCEEDED,
    }:
        return _fresh(db, existing), False
    if existing is not None:
        existing.status = AnalysisStatus.QUEUED
        existing.error_code = None
        existing.error_message = None
        existing.started_at = None
        existing.finished_at = None
        existing.jd_text = jd_text
        db.flush()
        audit.record(
            db,
            owner_id=owner_id,
            action="analysis.retry",
            entity="analysis_job",
            entity_id=existing.id,
        )
        db.commit()
        return _fresh(db, existing), False

    repo.stale_siblings(db, owner_id, resume_version_id=version.id, jd_id=jd.id if jd else None)

    job = AnalysisJob(
        owner_id=owner_id,
        resume_version_id=version.id,
        jd_id=jd.id if jd else None,
        jd_text=jd_text,
        jd_text_hash=text_hash,
        status=AnalysisStatus.QUEUED,
        input_hash=input_hash,
        provider=provider_name,
        model=model,
        prompt_version=prompt_version,
        attempts=0,
    )
    db.add(job)
    db.flush()

    audit.record(
        db, owner_id=owner_id, action="analysis.create", entity="analysis_job", entity_id=job.id
    )

    if provider is None:
        job.status = AnalysisStatus.FAILED
        job.error_code = denial.code if denial else "ai_not_configured"
        job.error_message = denial.message if denial else AI_NOT_CONFIGURED
        job.finished_at = utcnow()
        db.commit()
        return _fresh(db, job), True

    db.commit()
    return _fresh(db, job), True


def run(job_id: str) -> None:
    """Execute one queued job. Called from a background task."""
    with session_scope() as db:
        job = repo.get_by_id(db, job_id)
        if job is None or job.status != AnalysisStatus.QUEUED:
            return

        job.status = AnalysisStatus.RUNNING
        job.started_at = utcnow()
        job.attempts = (job.attempts or 0) + 1
        db.commit()

        try:
            provider = get_provider()
        except ProviderPrivacyDenied as exc:
            _fail(db, job, code=exc.code, message=exc.message)
            return
        if provider is None:
            _fail(
                db,
                job,
                code="ai_not_configured",
                message=AI_NOT_CONFIGURED,
            )
            return

        try:
            settings = get_settings()
            output = route_and_run(
                provider,
                _request_for(job),
                settings,
                health=health_store,
                quota=quota_store,
            )
            db.refresh(job)
            if job.status != AnalysisStatus.RUNNING:
                return  # cancelled while the provider was working
            _store(db, job, output)
            _succeed(db, job)
            logger.info(
                "analysis succeeded",
                extra={"job_id": job.id, "provider": provider.name, "score": output.score},
            )
        except ProviderError as exc:
            logger.warning(
                "analysis failed", extra={"job_id": job.id, "code": exc.code}, exc_info=False
            )
            _fail(db, job, code=exc.code, message=exc.message)
        except Exception:  # pragma: no cover - defensive
            logger.exception("analysis crashed", extra={"job_id": job.id})
            _fail(
                db,
                job,
                code="internal_error",
                message="The analysis failed unexpectedly. Try again.",
            )


def recover_interrupted() -> int:
    """Jobs cannot survive a process restart; mark them failed with a clear reason."""
    with session_scope() as db:
        jobs = list(
            db.scalars(
                select(AnalysisJob).where(
                    AnalysisJob.status.in_([AnalysisStatus.QUEUED, AnalysisStatus.RUNNING])
                )
            )
        )
        for job in jobs:
            job.status = AnalysisStatus.FAILED
            job.error_code = "interrupted"
            job.error_message = "This analysis was interrupted by a restart. Run it again."
            job.finished_at = utcnow()
        return len(jobs)


def get(db: Session, owner_id: str, job_id: str) -> AnalysisJob:
    job = repo.get(db, owner_id, job_id)
    if job is None:
        raise NotFoundError("Analysis not found.")
    return job


def cancel(db: Session, owner_id: str, job_id: str) -> AnalysisJob:
    job = get(db, owner_id, job_id)
    if job.status not in {AnalysisStatus.QUEUED, AnalysisStatus.RUNNING}:
        raise ConflictError(
            "Only queued or running analyses can be cancelled.", code="not_cancellable"
        )
    job.status = AnalysisStatus.CANCELLED
    job.finished_at = utcnow()
    audit.record(
        db, owner_id=owner_id, action="analysis.cancel", entity="analysis_job", entity_id=job.id
    )
    db.flush()
    return job


def delete(db: Session, owner_id: str, job_id: str) -> None:
    job = get(db, owner_id, job_id)
    db.delete(job)
    db.flush()
    audit.record(
        db, owner_id=owner_id, action="analysis.delete", entity="analysis_job", entity_id=job_id
    )


def stats(db: Session, owner_id: str) -> AnalysisStats:
    data = repo.stats(db, owner_id)
    counts: dict[str, int] = data["counts"]
    return AnalysisStats(
        total=data["total"],
        succeeded=counts.get(str(AnalysisStatus.SUCCEEDED), 0),
        failed=counts.get(str(AnalysisStatus.FAILED), 0),
        running=counts.get(str(AnalysisStatus.QUEUED), 0)
        + counts.get(str(AnalysisStatus.RUNNING), 0),
        average_score=data["average_score"],
    )


def resume_scores(db: Session, owner_id: str) -> list[ResumeScore]:
    return [ResumeScore(**row) for row in repo.resume_scores(db, owner_id)]


def view(job: AnalysisJob, *, detail: bool = False) -> AnalysisJobView:
    version = job.resume_version
    resume = version.resume
    jd = job.job_description
    excerpt = None
    if detail:
        text = job.jd_text or (jd.raw_text if jd else "") or ""
        excerpt = text[:EXCERPT_CHARS] + ("…" if len(text) > EXCERPT_CHARS else "")
    return AnalysisJobView(
        id=job.id,
        status=job.status,
        resume_version=AnalysisResumeRef(
            id=version.id,
            resume_id=resume.id,
            resume_name=resume.name,
            version_no=version.version_no,
            label=version.label,
        ),
        job_description=(
            AnalysisJobRef(
                id=jd.id,
                title=jd.title,
                company_name=jd.company.name if jd.company else None,
            )
            if jd
            else None
        ),
        jd_excerpt=excerpt,
        provider=job.provider,
        model=job.model,
        prompt_version=job.prompt_version,
        attempts=job.attempts,
        error_code=job.error_code,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        result=AnalysisResultView(
            score=job.result.score,
            summary=job.result.summary,
            alignment_explanation=job.result.alignment_explanation,
            findings=job.result.findings_json,
            schema_version=job.result.schema_version,
            created_at=job.result.created_at,
        )
        if job.result
        else None,
    )


def _fresh(db: Session, job: AnalysisJob) -> AnalysisJob:
    loaded = repo.get(db, job.owner_id, job.id)
    return loaded or job


def _load_version(db: Session, owner_id: str, version_id: str) -> ResumeVersion:
    version = db.scalar(
        select(ResumeVersion)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .options(joinedload(ResumeVersion.resume), undefer(ResumeVersion.extracted_text))
        .where(ResumeVersion.id == version_id, Resume.owner_id == owner_id)
    )
    if version is None:
        raise NotFoundError("That resume version does not exist.", code="unknown_resume_version")
    return version


def _resolve_jd(
    db: Session, owner_id: str, payload: AnalysisSubmit
) -> tuple[JobDescription | None, str, str, str | None]:
    if payload.jd_id:
        jd = job_repo.get(db, owner_id, payload.jd_id)
        if jd is None:
            raise NotFoundError("That job description does not exist.", code="unknown_job")
        return jd, jd.raw_text or "", jd.title, jd.company.name if jd.company else None

    text = (payload.jd_text or "").strip()
    return None, text, "Pasted job description", None


def _require_text(text: str | None, label: str) -> None:
    cleaned = (text or "").strip()
    if len(cleaned) < MIN_TEXT_CHARS:
        raise UnprocessableError(
            f"The {label} does not have enough extractable text to analyze "
            f"({len(cleaned)} of {MIN_TEXT_CHARS} characters). "
            "Add the full text, or upload a text-based file instead of a scan.",
            code="insufficient_text",
        )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_for(job: AnalysisJob) -> AnalysisRequest:
    jd = job.job_description
    return AnalysisRequest(
        resume_text=job.resume_version.extracted_text or "",
        jd_text=job.jd_text or (jd.raw_text if jd else "") or "",
        jd_title=jd.title if jd else "Pasted job description",
        company_name=jd.company.name if jd and jd.company else None,
    )


def _store(db: Session, job: AnalysisJob, output: AnalysisOutput) -> None:
    result = AnalysisResult(
        job_id=job.id,
        score=output.score,
        summary=output.summary,
        alignment_explanation=output.alignment_explanation,
        findings_json=[finding.model_dump(mode="json") for finding in output.findings],
        schema_version="1.0",
    )
    db.add(result)


def _succeed(db: Session, job: AnalysisJob) -> None:
    job.status = AnalysisStatus.SUCCEEDED
    job.finished_at = utcnow()
    job.error_code = None
    job.error_message = None
    audit.record(
        db,
        owner_id=job.owner_id,
        action="analysis.succeed",
        entity="analysis_job",
        entity_id=job.id,
    )


def _fail(db: Session, job: AnalysisJob, *, code: str, message: str) -> None:
    job.status = AnalysisStatus.FAILED
    job.error_code = code[:64]
    job.error_message = message[:2000]
    job.finished_at = utcnow()
    audit.record(
        db, owner_id=job.owner_id, action="analysis.fail", entity="analysis_job", entity_id=job.id
    )
