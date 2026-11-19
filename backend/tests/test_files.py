from __future__ import annotations

import io

import docx
import pytest
from fastapi.testclient import TestClient

RESUME_TEXT = (
    "Sri Charan — Backend Engineer\n"
    "Experience: 6 years building Python and FastAPI services on AWS.\n"
    "Skills: Python, FastAPI, SQLAlchemy, MySQL, Docker, Kubernetes, Terraform.\n"
    "Education: B.Tech Computer Science.\n"
    "Projects: CareerOS — single-owner career platform with MySQL 8 and React.\n"
)


def docx_bytes(text: str = RESUME_TEXT) -> bytes:
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client: TestClient, *, name: str = "Backend Engineer", payload: bytes | None = None):
    return client.post(
        "/api/v1/resumes",
        data={"name": name, "headline": "Backend engineer"},
        files={
            "file": (
                "resume.docx",
                payload if payload is not None else docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )


def test_upload_resume_creates_version_and_extracts_text(auth_client: TestClient):
    response = upload(auth_client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version_count"] == 1
    assert body["current_version_no"] == 1
    assert body["versions"][0]["extracted_chars"] > 100
    assert body["versions"][0]["is_current"] is True


def test_no_public_file_url_and_authenticated_download(auth_client: TestClient):
    body = upload(auth_client).json()
    file_id = body["versions"][0]["file_id"]

    assert auth_client.get(f"/api/v1/files/{file_id}/download").status_code == 200

    anonymous = TestClient(auth_client.app)
    assert anonymous.get(f"/api/v1/files/{file_id}/download").status_code == 401
    assert anonymous.get(f"/storage/{file_id}").status_code == 404


def test_new_upload_never_overwrites_previous_version(auth_client: TestClient):
    resume = upload(auth_client).json()
    second = auth_client.post(
        f"/api/v1/resumes/{resume['id']}/versions",
        data={"label": "Tailored for Northstar", "make_current": "true"},
        files={
            "file": (
                "resume-v2.docx",
                docx_bytes(RESUME_TEXT + "Tailored for platform roles.\n"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["version_count"] == 2
    assert [v["version_no"] for v in body["versions"]] == [2, 1]
    assert body["current_version_no"] == 2
    assert body["versions"][0]["label"] == "Tailored for Northstar"


def test_switch_current_version(auth_client: TestClient):
    resume = upload(auth_client).json()
    auth_client.post(
        f"/api/v1/resumes/{resume['id']}/versions",
        files={
            "file": ("v2.docx", docx_bytes(RESUME_TEXT + "Extra.\n"), "application/octet-stream")
        },
    )
    first_version = next(v for v in resume["versions"] if v["version_no"] == 1)
    response = auth_client.post(
        f"/api/v1/resumes/{resume['id']}/versions/{first_version['id']}/current"
    )
    assert response.status_code == 200
    assert response.json()["current_version_no"] == 1


def test_rejects_fake_pdf_by_signature(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Fake PDF"},
        files={"file": ("resume.pdf", b"This is definitely not a PDF", "application/pdf")},
    )
    assert response.status_code == 422
    assert "PDF" in response.json()["error"]["message"]


def test_rejects_executable_disguised_as_docx(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Binary"},
        files={"file": ("resume.docx", b"MZ\x90\x00binary\x00payload", "application/msword")},
    )
    assert response.status_code == 422


def test_rejects_empty_and_oversized_uploads(auth_client: TestClient):
    empty = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Empty"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert empty.status_code == 422

    oversized = auth_client.post(
        "/api/v1/resumes",
        data={"name": "Too big"},
        files={"file": ("big.txt", b"a" * (6 * 1024 * 1024), "text/plain")},
    )
    assert oversized.status_code == 413


def test_duplicate_resume_name_rejected(auth_client: TestClient):
    upload(auth_client, name="Primary")
    second = upload(auth_client, name="primary")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_resume"


def test_resume_delete_blocked_when_used(auth_client: TestClient, company: dict):
    resume = upload(auth_client).json()
    version_id = resume["versions"][0]["id"]
    auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Engineer",
            "resume_version_id": version_id,
        },
    )
    blocked = auth_client.delete(f"/api/v1/resumes/{resume['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "in_use"

    archived = auth_client.post(f"/api/v1/resumes/{resume['id']}/archive")
    assert archived.json()["archived_at"] is not None


def test_resume_delete_when_unused(auth_client: TestClient):
    resume = upload(auth_client, name="Scratch").json()
    assert auth_client.delete(f"/api/v1/resumes/{resume['id']}").status_code == 204
    assert auth_client.get("/api/v1/resumes").json()["total"] == 0


@pytest.mark.parametrize("path", ["/api/v1/resumes?page_size=0", "/api/v1/resumes?page_size=500"])
def test_pagination_bounds(auth_client: TestClient, path: str):
    assert auth_client.get(path).status_code == 422
