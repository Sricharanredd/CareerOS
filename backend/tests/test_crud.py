from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

JD_TEXT = (
    "Senior Backend Engineer. You will design and operate Python services on AWS, own "
    "PostgreSQL schemas, and mentor engineers. Required: Python, FastAPI, SQL, Docker. "
    "Preferred: Kubernetes, Terraform. Five or more years of professional experience."
)


def test_company_crud_and_case_insensitive_uniqueness(auth_client: TestClient, company: dict):
    assert company["name"] == "Northstar Labs"
    duplicate = auth_client.post("/api/v1/companies", json={"name": "northstar labs"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_company"

    listed = auth_client.get("/api/v1/companies").json()
    assert listed["total"] == 1
    assert listed["items"][0]["application_count"] == 0

    patched = auth_client.patch(
        f"/api/v1/companies/{company['id']}", json={"website": "northstar.dev"}
    )
    assert patched.status_code == 200
    assert patched.json()["website"] == "https://northstar.dev"

    archived = auth_client.post(f"/api/v1/companies/{company['id']}/archive")
    assert archived.json()["archived_at"] is not None
    assert auth_client.get("/api/v1/companies").json()["total"] == 0
    assert auth_client.get("/api/v1/companies?include_archived=true").json()["total"] == 1


def test_company_delete_blocked_when_used(auth_client: TestClient, company: dict):
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Backend Engineer", "raw_text": JD_TEXT},
    ).json()
    response = auth_client.delete(f"/api/v1/companies/{company['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["job_descriptions"] == 1
    assert jd["id"]


def test_company_delete_when_unused(auth_client: TestClient, company: dict):
    assert auth_client.delete(f"/api/v1/companies/{company['id']}").status_code == 204
    assert auth_client.get("/api/v1/companies").json()["total"] == 0


def test_job_description_requires_text(auth_client: TestClient, company: dict):
    response = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Backend Engineer", "raw_text": "   "},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unprocessable"


def test_job_description_validation_and_search(auth_client: TestClient, company: dict):
    created = auth_client.post(
        "/api/v1/job-descriptions",
        json={
            "company_id": company["id"],
            "title": "Senior Backend Engineer",
            "location": "Remote",
            "raw_text": JD_TEXT,
            "required_skills": ["Python", "SQL", " "],
            "seniority": "senior",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["required_skills"] == ["Python", "SQL"]
    assert body["company"]["name"] == "Northstar Labs"

    listing = auth_client.get("/api/v1/job-descriptions?search=backend").json()
    assert listing["total"] == 1
    assert listing["items"][0]["text_chars"] == len(JD_TEXT)

    missing = auth_client.get("/api/v1/job-descriptions?company_id=does-not-exist").json()
    assert missing["total"] == 0


def test_job_description_update_and_archive(auth_client: TestClient, company: dict):
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Engineer", "raw_text": JD_TEXT},
    ).json()
    updated = auth_client.patch(
        f"/api/v1/job-descriptions/{jd['id']}",
        json={"seniority": "staff", "preferred_skills": ["Kubernetes"]},
    )
    assert updated.status_code == 200
    assert updated.json()["seniority"] == "staff"
    assert updated.json()["preferred_skills"] == ["Kubernetes"]

    archived = auth_client.post(f"/api/v1/job-descriptions/{jd['id']}/archive")
    assert archived.json()["archived_at"] is not None
    assert auth_client.get("/api/v1/job-descriptions").json()["total"] == 0


def test_application_lifecycle(auth_client: TestClient, company: dict):
    created = auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Backend Engineer",
            "status": "applied",
            "location": "Remote",
            "work_mode": "remote",
            "salary_min": 1800000,
            "salary_max": 2400000,
            "salary_currency": "INR",
            "salary_period": "year",
            "follow_up_on": (date.today() + timedelta(days=5)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    application = created.json()
    assert application["status"] == "applied"
    assert application["applied_on"] == date.today().isoformat()

    for target in ("screening", "interviewing", "offer", "accepted"):
        response = auth_client.post(
            f"/api/v1/applications/{application['id']}/status", json={"status": target}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target

    detail = auth_client.get(f"/api/v1/applications/{application['id']}").json()
    statuses = [
        event["to_status"] for event in detail["events"] if event["type"] == "status_change"
    ]
    assert statuses == ["accepted", "offer", "interviewing", "screening"]


def test_application_invalid_transition_rejected(auth_client: TestClient, company: dict):
    application = auth_client.post(
        "/api/v1/applications",
        json={"company_id": company["id"], "title": "Engineer", "status": "saved"},
    ).json()
    response = auth_client.post(
        f"/api/v1/applications/{application['id']}/status", json={"status": "offer"}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert set(error["details"]["allowed"]) == {"applied", "withdrawn"}


def test_application_duplicate_detection_and_override(auth_client: TestClient, company: dict):
    payload = {
        "company_id": company["id"],
        "title": "Data Engineer",
        "status": "applied",
    }
    first = auth_client.post("/api/v1/applications", json=payload)
    assert first.status_code == 201

    duplicate = auth_client.post("/api/v1/applications", json=payload)
    assert duplicate.status_code == 409
    body = duplicate.json()["error"]
    assert body["code"] == "duplicate_application"
    assert len(body["details"]["matches"]) == 1

    override = auth_client.post(
        "/api/v1/applications", json={**payload, "duplicate_override": True}
    )
    assert override.status_code == 201


def test_application_filters_and_board(auth_client: TestClient, company: dict):
    for title, status in (("Engineer A", "applied"), ("Engineer B", "saved")):
        auth_client.post(
            "/api/v1/applications",
            json={"company_id": company["id"], "title": title, "status": status},
        )

    filtered = auth_client.get("/api/v1/applications?status=applied").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["title"] == "Engineer A"

    searched = auth_client.get("/api/v1/applications?search=northstar").json()
    assert searched["total"] == 2

    board = auth_client.get("/api/v1/applications/board").json()
    by_status = {column["status"]: column["count"] for column in board["columns"]}
    assert by_status["applied"] == 1
    assert by_status["saved"] == 1


def test_salary_range_validation(auth_client: TestClient, company: dict):
    response = auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Engineer",
            "salary_min": 500,
            "salary_max": 100,
        },
    )
    assert response.status_code == 422


def test_page_size_cap(auth_client: TestClient):
    assert auth_client.get("/api/v1/companies?page_size=101").status_code == 422


def test_owner_scoping_isolates_foreign_ids(auth_client: TestClient, company: dict):
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Engineer", "raw_text": JD_TEXT},
    ).json()
    other = auth_client.post(
        "/api/v1/applications",
        json={"company_id": company["id"], "title": "Engineer", "status": "saved"},
    ).json()
    bogus = auth_client.post(
        "/api/v1/applications",
        json={"company_id": "00000000-0000-0000-0000-000000000000", "title": "X"},
    )
    assert bogus.status_code == 422
    assert bogus.json()["error"]["code"] == "invalid_company"
    assert auth_client.get(f"/api/v1/job-descriptions/{jd['id']}").status_code == 200
    assert auth_client.get(f"/api/v1/applications/{other['id']}").status_code == 200


def test_delete_job_description_blocked_when_linked(auth_client: TestClient, company: dict):
    jd = auth_client.post(
        "/api/v1/job-descriptions",
        json={"company_id": company["id"], "title": "Engineer", "raw_text": JD_TEXT},
    ).json()
    auth_client.post(
        "/api/v1/applications",
        json={"company_id": company["id"], "title": "Engineer", "jd_id": jd["id"]},
    )
    response = auth_client.delete(f"/api/v1/job-descriptions/{jd['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "in_use"
