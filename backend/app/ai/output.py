"""Validated shape of an analysis result.

Every finding carries the evidence it is based on. The model is never allowed
to invent experience: resume evidence quotes the resume, JD requirements quote
the posting, and recommendations are explicitly labelled as inferred.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FindingKind = Literal["resume_evidence", "jd_requirement", "inferred_recommendation"]
FindingCategory = Literal[
    "matched_skill",
    "missing_skill",
    "weak_skill",
    "experience",
    "keyword_gap",
    "suggestion",
]


class Finding(BaseModel):
    kind: FindingKind
    category: FindingCategory
    label: str = Field(min_length=1, max_length=160)
    detail: str = Field(min_length=1, max_length=1200)
    evidence: str | None = Field(default=None, max_length=600)


class AnalysisOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=1200)
    alignment_explanation: str = Field(min_length=1, max_length=1200)
    findings: list[Finding] = Field(min_length=1, max_length=60)


SCHEMA_HINT = """{
  "score": <integer 0-100 alignment indicator, never a hiring probability>,
  "summary": "<2-3 sentence plain-language summary>",
  "alignment_explanation": "<why the score is what it is, in terms of overlap and gaps>",
  "findings": [
    {
      "kind": "resume_evidence" | "jd_requirement" | "inferred_recommendation",
      "category": "matched_skill" | "missing_skill" | "weak_skill" | "experience"
                  | "keyword_gap" | "suggestion",
      "label": "<short label>",
      "detail": "<one or two sentences>",
      "evidence": "<verbatim snippet from the resume or the job description, or null>"
    }
  ]
}"""
