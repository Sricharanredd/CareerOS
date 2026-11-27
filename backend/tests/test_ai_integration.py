"""End-to-end analysis flow with a mocked Cloudflare transport. No real request is made."""

from __future__ import annotations

import io
import json

import docx
import httpx
from fastapi.testclient import TestClient

from app.ai import registry
from app.ai.cloudflare import AUTH_MESSAGE, CloudflareProvider

MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
RESUME_CANARY = "RESUME_CANARY_7f3c9a"

RESUME_TEXT = (
    "Alex Doe - Backend Engineer\n"
    "Five years building Python APIs with FastAPI, MySQL and Docker on AWS. Led a small "
    "team, owned migrations, and improved p95 latency by 40 percent. Comfortable with "
    "GitHub Actions, on-call ownership and incident review.\n"
)
JD_TEXT = (
    "Senior Backend Engineer. Build Python and FastAPI services, own MySQL schemas, and "
    "operate Docker workloads on AWS. Required: Python, FastAPI, MySQL, Docker. Preferred: "
    "Kubernetes, Terraform. Five or more years of experience.\n"
)

VALID_OUTPUT = {
    "score": 81,
    "summary": "Strong backend overlap with one infrastructure gap.",
    "alignment_explanation": "Python, FastAPI, MySQL and Docker appear in both documents.",
    "findings": [
        {
            "kind": "resume_evidence",
            "category": "matched_skill",
            "label": "Python APIs",
            "detail": "The resume shows production Python API work.",
            "evidence": "Five years building Python APIs with FastAPI, MySQL and Docker on AWS.",
        }
    ],
}


def _docx() -> bytes:
    document = docx.Document()
    for line in RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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


def _use_provider(monkeypatch, ai_settings, handler) -> list[httpx.Request]:
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    provider = CloudflareProvider(
        ai_settings(), transport=httpx.MockTransport(record)
    )
    monkeypatch.setattr(registry, "select_provider", lambda settings: provider)
    return calls


def _success(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "result": {"response": json.dumps(VALID_OUTPUT)}},
    )


def test_analysis_uses_cloudflare_and_attributes_model(auth_client, company, ai_settings, monkeypatch):
    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, _success)

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()
    assert body["status"] == "succeeded"
    assert body["provider"] == "cloudflare"
    assert body["model"] == MODEL
    assert body["attempts"] == 1
    assert body["result"]["score"] == 81
    assert body["result"]["schema_version"] == "1.0"
    assert body["result"]["findings"][0]["kind"] == "resume_evidence"
    assert len(calls) == 1
    prompt = json.loads(calls[0].content)["messages"][0]["content"]
    assert "Senior Backend Engineer" in prompt
    assert "Python APIs" in prompt
    assert "test-token" not in response.text


def test_gemini_is_not_a_fallback_when_cloudflare_is_unconfigured(
    auth_client, company, ai_settings, monkeypatch
):
    settings = ai_settings(
        ai_provider_order="gemini,cloudflare",
        ai_approved_providers="gemini,cloudflare",
        gemini_api_key="test-gemini-token",
        ai_allow_training_providers=True,
        cloudflare_api_token=None,
        cloudflare_account_id=None,
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    version_id, jd_id = _setup(auth_client, company)

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["error_code"] == "provider_privacy_denied"
    assert body["provider"] == ""
    assert body["model"] == ""
    assert "approved" in body["error_message"]


def test_auth_failure_is_reported_without_leaking_the_token(
    auth_client, company, ai_settings, monkeypatch
):
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "success": False,
                "errors": [{"message": f"invalid token test-token {RESUME_CANARY}"}],
            },
        )

    version_id, jd_id = _setup(auth_client, company)
    _use_provider(monkeypatch, ai_settings, unauthorized)

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["error_code"] == "provider_auth_failed"
    assert body["error_message"] == AUTH_MESSAGE
    assert "test-token" not in response.text
    assert RESUME_CANARY not in response.text


def test_provider_outage_fails_without_switching_providers(
    auth_client, company, ai_settings, monkeypatch
):
    monkeypatch.setattr("app.ai.retry.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.services.analysis.get_settings",
        lambda: ai_settings(
            ai_max_attempts=2, ai_retry_base_delay_seconds=1.0, ai_retry_max_delay_seconds=10.0
        ),
    )

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"success": False})

    version_id, jd_id = _setup(auth_client, company)
    calls = _use_provider(monkeypatch, ai_settings, down)

    response = auth_client.post(
        "/api/v1/analyses", json={"resume_version_id": version_id, "jd_id": jd_id}
    )
    assert response.status_code == 201, response.text
    body = auth_client.get(f"/api/v1/analyses/{response.json()['id']}").json()
    assert body["status"] == "failed"
    assert body["error_code"] == "provider_unavailable"
    assert body["provider"] == "cloudflare"
    assert body["attempts"] == 1
    assert len(calls) == 2

