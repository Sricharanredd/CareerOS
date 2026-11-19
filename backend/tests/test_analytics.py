from __future__ import annotations

import io
from datetime import date, timedelta

import docx
from fastapi.testclient import TestClient

from app.ai.output import AnalysisOutput, Finding
from app.core.security import utcnow

RESUME_TEXT = (
    "Sri Charan — Senior Backend Engineer\n"
    "Seven years of Python, FastAPI and MySQL experience. Designed event-driven services "
    "on AWS, led migrations, and mentored four engineers. Comfortable with Docker and CI.\n"
    "Owned production on-call and wrote the incident review process.\n"
)
JD_TEXT = (
    "Staff Backend Engineer. Own Python services and MySQL schemas, lead design reviews, "
    "and improve reliability. Required: Python, FastAPI, MySQL, Docker, AWS. Preferred: "
    "Kubernetes and Terraform. At least six years of professional experience.\n"
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
            score=78,
            summary="Strong overlap on Python, FastAPI and MySQL with room on Kubernetes.",
            alignment_explanation="The resume covers the core stack; Kubernetes is not shown.",
            findings=[
                Finding(
                    kind="resume_evidence",
                    category="matched_skill",
                    label="Python and FastAPI",
                    detail="The resume shows seven years of Python and FastAPI work.",
                    evidence="Seven years of Python, FastAPI and MySQL experience.",
                ),
                Finding(
                    kind="jd_requirement",
                    category="missing_skill",
                    label="Kubernetes",
                    detail="The job description prefers Kubernetes, which the resume omits.",
                    evidence="Preferred: Kubernetes and Terraform.",
                ),
                Finding(
                    kind="inferred_recommendation",
                    category="suggestion",
                    label="Add a Kubernetes example",
                    detail="Describe one deployment you operated if that experience exists.",
                ),
            ],
        )


def _application(auth_client: TestClient, company: dict) -> dict:
    return auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Staff Backend Engineer",
            "status": "applied",
            "source": "referral",
        },
    ).json()


def test_analytics_empty_account_is_null_not_zero(auth_client: TestClient):
    analytics = auth_client.get("/api/v1/analytics")
    assert analytics.status_code == 200, analytics.text
    body = analytics.json()

    assert body["total_applications"] == 0
    assert body["response"]["rate"] is None
    assert body["interview_conversion"]["rate"] is None
    assert body["offer_conversion"]["rate"] is None
    assert body["follow_up_performance"]["rate"] is None
    assert body["follow_up_performance"]["total_due"] == 0
    assert body["average_days_to_response"] is None
    assert body["average_alignment"] is None
    assert body["resume_alignment"] == []
    assert body["analysis_history"] == []
    assert len(body["applications_weekly"]) == 12
    assert len(body["applications_monthly"]) == 6
    assert len(body["tasks_completed_weekly"]) == 12
    assert len(body["time_logged_weekly"]) == 12
    assert all(point["count"] == 0 for point in body["applications_weekly"])
    assert all(point["minutes"] == 0 for point in body["time_logged_weekly"])


def test_analytics_reflects_real_records(auth_client: TestClient, company: dict, monkeypatch):
    application = _application(auth_client, company)

    # Two follow-ups are due by today; one is completed on time.
    done = auth_client.post(
        "/api/v1/follow-ups",
        json={"application_id": application["id"], "due_on": str(date.today())},
    ).json()
    auth_client.patch(f"/api/v1/follow-ups/{done['id']}", json={"status": "done"})
    auth_client.post(
        "/api/v1/follow-ups",
        json={
            "application_id": application["id"],
            "due_on": str(date.today() - timedelta(days=1)),
        },
    )
    auth_client.post(
        "/api/v1/follow-ups",
        json={
            "application_id": application["id"],
            "due_on": str(date.today() + timedelta(days=10)),
        },
    )

    task = auth_client.post("/api/v1/tasks", json={"title": "Prep interview"}).json()
    auth_client.post(f"/api/v1/tasks/{task['id']}/complete", json={"completed": True})

    started = utcnow().replace(microsecond=0) - timedelta(minutes=45)
    entry = auth_client.post(
        "/api/v1/time-entries",
        json={
            "task_id": task["id"],
            "started_at": started.isoformat(),
            "ended_at": utcnow().isoformat(),
        },
    )
    assert entry.status_code == 201, entry.text

    # Run a stubbed analysis so alignment metrics have real rows.
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
    version_id = resume["versions"][0]["id"]
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Staff Backend Engineer", "raw_text": JD_TEXT},
    ).json()

    from app.services import analysis as analysis_service

    monkeypatch.setattr(analysis_service, "get_provider", lambda: StubProvider())
    job = auth_client.post(
        "/api/v1/analyses",
        json={"resume_version_id": version_id, "jd_id": jd["id"]},
    )
    assert job.status_code == 201, job.text
    detail = auth_client.get(f"/api/v1/analyses/{job.json()['id']}").json()
    assert detail["status"] == "succeeded"
    assert detail["result"]["score"] == 78

    body = auth_client.get("/api/v1/analytics").json()
    assert body["total_applications"] == 1
    assert body["submitted"] == 1
    assert body["response"]["numerator"] == 0
    assert body["response"]["rate"] == 0.0
    assert body["by_source"] == [{"source": "referral", "count": 1}]

    performance = body["follow_up_performance"]
    assert performance["total_due"] == 2
    assert performance["completed_on_time"] == 1
    assert performance["pending_overdue"] == 1
    assert performance["rate"] == 0.5

    assert body["tasks_completed_weekly"][-1]["count"] == 1
    assert body["time_logged_weekly"][-1]["minutes"] >= 45
    assert body["applications_weekly"][-1]["count"] == 1

    assert body["average_alignment"] == 78.0
    assert body["analysis_history"][0]["score"] == 78
    assert body["analysis_history"][0]["jd_title"] == "Staff Backend Engineer"
    assert body["resume_alignment"][0]["analyses"] == 1
    assert body["resume_alignment"][0]["average_score"] == 78.0
    assert body["resume_alignment"][0]["resume_name"] == "Backend"
