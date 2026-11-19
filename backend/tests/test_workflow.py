"""The PRD success criterion: the critical workflow end to end."""

from __future__ import annotations

import io

import docx
from fastapi.testclient import TestClient

JD_TEXT = (
    "Platform Engineer at Northstar Labs. Build Python services with FastAPI on AWS, own "
    "MySQL schemas, improve reliability, and partner with product. Required: Python, FastAPI, "
    "MySQL, Docker. Preferred: Kubernetes, Terraform. Minimum five years experience."
)

RESUME_TEXT = (
    "Sri Charan — Platform Engineer\n"
    "Six years of Python and FastAPI experience. Designed MySQL 8 schemas and Alembic "
    "migrations. Operated Docker and Kubernetes workloads on AWS. Led reliability work.\n"
)


def _docx() -> bytes:
    document = docx.Document()
    for line in RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_critical_workflow_end_to_end(auth_client: TestClient):
    # Empty account: every ratio is null, never 0% or NaN.
    empty = auth_client.get("/api/v1/dashboard").json()
    assert empty["total_applications"] == 0
    assert empty["response"]["rate"] is None
    assert empty["offer_conversion"]["rate"] is None
    assert len(empty["applications_trend"]) == 12
    assert all(point["count"] == 0 for point in empty["applications_trend"])

    company = auth_client.post(
        "/api/v1/companies", json={"name": "Northstar Labs", "industry": "Software"}
    ).json()

    resume = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Platform Engineer", "label": "v1"},
        files={
            "file": (
                "platform.docx",
                _docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    ).json()
    version_id = resume["versions"][0]["id"]

    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={
            "company_id": company["id"],
            "title": "Platform Engineer",
            "location": "Remote",
            "url": "https://northstar.dev/jobs/1",
            "raw_text": JD_TEXT,
        },
    ).json()

    application = auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Platform Engineer",
            "jd_id": jd["id"],
            "resume_version_id": version_id,
            "status": "applied",
            "work_mode": "remote",
            "source": "referral",
        },
    ).json()
    assert application["job_description"]["title"] == "Platform Engineer"
    assert application["resume_version"]["version_no"] == 1

    for target in ("screening", "interviewing", "offer"):
        step = auth_client.post(
            f"/api/v1/applications/{application['id']}/status",
            json={"status": target, "note": f"moved to {target}"},
        )
        assert step.status_code == 200, step.text

    accepted = auth_client.post(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "accepted", "note": "signed"},
    )
    assert accepted.json()["status"] == "accepted"

    detail = auth_client.get(f"/api/v1/applications/{application['id']}").json()
    assert len(detail["events"]) >= 5
    assert detail["events"][0]["to_status"] == "accepted"

    board = auth_client.get("/api/v1/applications/board").json()
    accepted_column = next(c for c in board["columns"] if c["status"] == "accepted")
    assert accepted_column["count"] == 1

    dashboard = auth_client.get("/api/v1/dashboard").json()
    assert dashboard["total_applications"] == 1
    assert dashboard["active_applications"] == 1
    assert dashboard["offers"] == 1
    assert dashboard["response"]["numerator"] == 1
    assert dashboard["response"]["denominator"] == 1
    assert dashboard["response"]["rate"] == 1.0
    assert dashboard["interview_conversion"]["rate"] == 1.0
    assert dashboard["offer_conversion"]["rate"] == 1.0
    assert dashboard["applications_trend"][-1]["count"] == 1
    assert dashboard["applied_this_month"] == 1
    assert dashboard["by_company"][0]["company_name"] == "Northstar Labs"
    assert dashboard["recent_activity"][0]["to_status"] == "accepted"

    # Job description and application remain linked for history.
    company_detail = auth_client.get(f"/api/v1/companies/{company['id']}").json()
    assert company_detail["application_count"] == 1
    assert company_detail["job_description_count"] == 1


def test_rejected_application_affects_metrics(auth_client: TestClient, company: dict):
    application = auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Rejected role",
            "status": "applied",
            "applied_on": "2026-10-01",
        },
    ).json()
    auth_client.post(
        f"/api/v1/applications/{application['id']}/status",
        json={"status": "rejected", "note": "Position closed"},
    )
    dashboard = auth_client.get("/api/v1/dashboard").json()
    assert dashboard["rejections"] == 1
    assert dashboard["response"]["rate"] == 1.0
    assert dashboard["interview_conversion"]["rate"] == 0.0
    assert dashboard["interview_conversion"]["denominator"] == 1
    detail = auth_client.get(f"/api/v1/applications/{application['id']}").json()
    assert detail["rejection_reason"] == "Position closed"
