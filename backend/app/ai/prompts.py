"""Prompt construction for the resume-vs-JD analyzer."""

from __future__ import annotations

from app.ai.output import SCHEMA_HINT

SYSTEM_RULES = """You compare one resume with one job description for a single job seeker.

Rules:
1. Never invent skills, employers, dates or achievements missing from the resume.
2. A "resume_evidence" finding must quote a short verbatim snippet from the resume in `evidence`.
3. A "jd_requirement" finding must quote a short verbatim snippet from the job description.
4. An "inferred_recommendation" is advice. Mark it inferred; never present it as experience.
5. The score is an alignment indicator (0-100), never a hiring probability or prediction.
6. Report missing or weak skills honestly, only from requirements in the job description.
7. Respond with JSON only, matching the schema exactly. No markdown, no commentary."""


def build_prompt(*, resume_text: str, jd_text: str, jd_title: str, company_name: str | None) -> str:
    header = f"Job title: {jd_title}"
    if company_name:
        header += f"\nCompany: {company_name}"

    return (
        f"{SYSTEM_RULES}\n\n"
        f"=== JOB DESCRIPTION ===\n{header}\n\n{jd_text.strip()}\n\n"
        f"=== RESUME ===\n{resume_text.strip()}\n\n"
        "Produce at least one matched skill or experience finding, and at least one gap when the "
        "job description asks for something the resume does not show. Include actionable "
        "suggestions tagged kind=inferred_recommendation, category=suggestion.\n\n"
        f"JSON schema:\n{SCHEMA_HINT}"
    )


def build_repair_prompt(original: str, problem: str) -> str:
    return (
        f"{original}\n\n"
        "Your previous reply could not be used because it failed validation:\n"
        f"{problem}\n\n"
        "Return the corrected JSON object only. Keep every rule above."
    )
