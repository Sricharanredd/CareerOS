from __future__ import annotations

import io

import docx
from fastapi.testclient import TestClient

from app.ai.output import AnalysisOutput, Finding

RESUME_TEXT = (
    "Alex Doe — Backend Engineer\n"
    "Five years building Python APIs with FastAPI, MySQL and Docker on AWS. Led a small "
    "team, owned migrations, and improved p95 latency by 40 percent. Comfortable with "
    "GitHub Actions, on-call ownership and incident review.\n"
)
JD_TEXT = (
    "Senior Backend Engineer. Build Python and FastAPI services, own MySQL schemas, and "
    "operate Docker workloads on AWS. Required: Python, FastAPI, MySQL, Docker. Preferred: "
    "Kubernetes, Terraform. Five or more years of experience.\n"
)


def _docx() -> bytes:
    document = docx.Document()
    for line in RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class StubProvider:
    name = "stub"
    model = "stub-1"

    def analyze(self, request):
        return AnalysisOutput(
            score=74,
            summary="Good core-stack overlap; Kubernetes is not evidenced.",
            alignment_explanation="Python, FastAPI, MySQL and Docker appear in both documents.",
            findings=[
                Finding(
                    kind="resume_evidence",
                    category="matched_skill",
                    label="Python APIs",
                    detail="The resume shows production Python API work.",
                    evidence="Five years building Python APIs with FastAPI, MySQL and Docker on AWS.",
                ),
                Finding(
                    kind="jd_requirement",
                    category="missing_skill",
                    label="Kubernetes",
                    detail="Kubernetes is listed as preferred but absent from the resume.",
                    evidence="Preferred: Kubernetes, Terraform.",
                ),
                Finding(
                    kind="inferred_recommendation",
                    category="suggestion",
                    label="Quantify platform scope",
                    detail="Add service count or traffic volume to the platform sentence.",
                ),
            ],
        )


def _setup(auth_client: TestClient, company: dict) -> tuple[str, str]:
    resume = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Backend", "label": "v1"},
        files={
            "file": (
                "backend.docx",
                _docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    ).json()
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Senior Backend Engineer", "raw_text": JD_TEXT},
    ).json()
    return resume["versions"][0]["id"], jd["id"]


def test_analysis_without_provider_fails_honestly(auth_client: TestClient, company: dict):
    version_id, jd_id = _setup(auth_client, company)
    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "ai_not_configured"
    assert "GEMINI_API_KEY" in body["error_message"]

    stats = auth_client.get("/api/v1/analyses/stats").json()
    assert stats["total"] == 1
    assert stats["failed"] == 1
    assert stats["average_score"] is None


def test_analysis_success_is_idempotent_and_evidence_tagged(
    auth_client: TestClient, company: dict, monkeypatch
):
    version_id, jd_id = _setup(auth_client, company)

    from app.services import analysis as analysis_service

    monkeypatch.setattr(analysis_service, "get_provider", lambda: StubProvider())

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]

    detail = auth_client.get(f"/api/v1/analyses/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "succeeded"
    assert body["provider"] == "stub"
    assert body["model"] == "stub-1"
    assert body["attempts"] == 1
    assert body["result"]["score"] == 74
    kinds = {finding["kind"] for finding in body["result"]["findings"]}
    assert kinds == {"resume_evidence", "jd_requirement", "inferred_recommendation"}
    assert body["resume_version"]["resume_name"] == "Backend"
    assert body["job_description"]["title"] == "Senior Backend Engineer"

    again = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert again.status_code == 200
    assert again.json()["id"] == job_id
    assert auth_client.get("/api/v1/analyses").json()["total"] == 1

    stats = auth_client.get("/api/v1/analyses/stats").json()
    assert stats["succeeded"] == 1
    assert stats["average_score"] == 74.0

    scores = auth_client.get("/api/v1/analyses/resume-scores").json()
    assert scores[0]["resume_version_id"] == version_id
    assert scores[0]["average_score"] == 74.0

    # History filtered by resume and by job description both find the same job.
    assert (
        auth_client.get(f"/api/v1/analyses?resume_id={body['resume_version']['resume_id']}").json()[
            "total"
        ]
        == 1
    )
    assert auth_client.get(f"/api/v1/analyses?jd_id={jd_id}").json()["total"] == 1

    assert auth_client.delete(f"/api/v1/analyses/{job_id}").status_code == 204
    assert auth_client.get("/api/v1/analyses").json()["total"] == 0


def test_analysis_validates_inputs(auth_client: TestClient, company: dict):
    version_id, jd_id = _setup(auth_client, company)

    both = auth_client.post(
        "/api/v1/analyses",
        json={"resume_version_id": version_id, "jd_id": jd_id, "jd_text": JD_TEXT},
    )
    assert both.status_code == 422

    short = auth_client.post(
        "/api/v1/analyses",
        json={"resume_version_id": version_id, "jd_text": "Too short"},
    )
    assert short.status_code == 422
    assert short.json()["error"]["code"] == "insufficient_text"

    missing = auth_client.post(
        "/api/v1/analyses",
        json={
            "resume_version_id": "00000000-0000-0000-0000-000000000000",
            "jd_id": jd_id,
        },
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "unknown_resume_version"


def test_analysis_pasted_jd_is_kept_for_retry(auth_client: TestClient, company: dict, monkeypatch):
    resume = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Backend pasted", "label": "v1"},
        files={
            "file": (
                "pasted.docx",
                _docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    ).json()
    version_id = resume["versions"][0]["id"]

    from app.services import analysis as analysis_service

    monkeypatch.setattr(analysis_service, "get_provider", lambda: StubProvider())
    created = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_text": JD_TEXT}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["job_description"] is None
    assert body["jd_excerpt"].startswith("Senior Backend Engineer")

    detail = auth_client.get(f"/api/v1/analyses/{body['id']}").json()
    assert detail["status"] == "succeeded"
