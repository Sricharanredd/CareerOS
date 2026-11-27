from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


def _application(auth_client: TestClient, company: dict) -> dict:
    response = auth_client.post(
        "/api/v1/applications",
        json={
            "company_id": company["id"],
            "title": "Backend Engineer",
            "status": "applied",
            "source": "referral",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_task_lifecycle_and_buckets(auth_client: TestClient, company: dict):
    application = _application(auth_client, company)
    today = date.today()

    overdue = auth_client.post(
        "/api/v1/tasks",
        json={
            "title": "Send follow-up",
            "due_on": str(today - timedelta(days=1)),
            "priority": "high",
            "application_id": application["id"],
        },
    )
    assert overdue.status_code == 201, overdue.text
    overdue_task = overdue.json()
    assert overdue_task["is_overdue"] is True
    assert overdue_task["application"]["title"] == "Backend Engineer"
    assert overdue_task["application"]["company_name"] == "Northstar Labs"

    auth_client.post("/api/v1/tasks", json={"title": "Review notes", "due_on": str(today)})
    auth_client.post(
        "/api/v1/tasks", json={"title": "Plan next week", "due_on": str(today + timedelta(days=3))}
    )
    auth_client.post("/api/v1/tasks", json={"title": "No date"})

    assert auth_client.get("/api/v1/tasks?bucket=overdue").json()["total"] == 1
    assert auth_client.get("/api/v1/tasks?bucket=today").json()["total"] == 1
    assert auth_client.get("/api/v1/tasks?bucket=upcoming").json()["total"] == 1
    assert auth_client.get("/api/v1/tasks?bucket=open").json()["total"] == 4
    assert auth_client.get("/api/v1/tasks?bucket=all").json()["total"] == 4

    completed = auth_client.post(
        f"/api/v1/tasks/{overdue_task['id']}/complete", json={"completed": True}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "done"
    assert completed.json()["completed_at"] is not None
    assert completed.json()["is_overdue"] is False

    assert auth_client.get("/api/v1/tasks?bucket=completed").json()["total"] == 1
    assert auth_client.get("/api/v1/tasks?bucket=open").json()["total"] == 3

    reopened = auth_client.patch(
        f"/api/v1/tasks/{overdue_task['id']}", json={"status": "in_progress"}
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["completed_at"] is None

    patched = auth_client.patch(
        f"/api/v1/tasks/{overdue_task['id']}",
        json={"title": "Send follow-up today", "priority": "low", "due_on": str(today)},
    )
    assert patched.json()["title"] == "Send follow-up today"
    assert patched.json()["priority"] == "low"

    assert auth_client.delete(f"/api/v1/tasks/{overdue_task['id']}").status_code == 204
    assert auth_client.get("/api/v1/tasks?bucket=all").json()["total"] == 3


def test_task_rejects_unknown_application(auth_client: TestClient):
    response = auth_client.post(
        "/api/v1/tasks",
        json={"title": "Ghost task", "application_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_application"


def test_follow_up_lifecycle(auth_client: TestClient, company: dict):
    application = _application(auth_client, company)
    today = date.today()

    created = auth_client.post(
        "/api/v1/follow-ups",
        json={
            "application_id": application["id"],
            "due_on": str(today - timedelta(days=2)),
            "channel": "linkedin",
            "notes": "Nudge the recruiter",
        },
    )
    assert created.status_code == 201, created.text
    follow_up = created.json()
    assert follow_up["status"] == "pending"
    assert follow_up["is_overdue"] is True
    assert follow_up["application"]["company_name"] == "Northstar Labs"

    upcoming = auth_client.post(
        "/api/v1/follow-ups",
        json={"application_id": application["id"], "due_on": str(today + timedelta(days=5))},
    )
    assert upcoming.status_code == 201

    assert auth_client.get("/api/v1/follow-ups?scope=overdue").json()["total"] == 1
    assert auth_client.get("/api/v1/follow-ups?scope=upcoming").json()["total"] == 1
    assert auth_client.get("/api/v1/follow-ups?scope=open").json()["total"] == 2

    done = auth_client.patch(f"/api/v1/follow-ups/{follow_up['id']}", json={"status": "done"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"
    assert done.json()["done_at"] is not None
    assert done.json()["is_overdue"] is False

    assert auth_client.get("/api/v1/follow-ups?scope=done").json()["total"] == 1
    assert auth_client.get("/api/v1/follow-ups?scope=open").json()["total"] == 1

    skipped = auth_client.patch(
        f"/api/v1/follow-ups/{upcoming.json()['id']}", json={"status": "skipped"}
    )
    assert skipped.json()["status"] == "skipped"
    assert skipped.json()["done_at"] is None

    assert auth_client.delete(f"/api/v1/follow-ups/{follow_up['id']}").status_code == 204


def test_interviews_auto_round_and_outcomes(auth_client: TestClient, company: dict):
    application = _application(auth_client, company)

    # Dates are relative to today: fixed calendar dates rot into the past and break "upcoming".
    soon = (date.today() + timedelta(days=2)).isoformat()
    later = (date.today() + timedelta(days=5)).isoformat()
    past_day = (date.today() - timedelta(days=30)).isoformat()

    first = auth_client.post(
        "/api/v1/interviews",
        json={
            "application_id": application["id"],
            "scheduled_at": f"{soon}T10:30:00",
            "type": "technical",
            "timezone": "Asia/Kolkata",
            "interviewer": "Priya",
            "link": "https://meet.example.com/abc",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["round_no"] == 1
    assert first.json()["outcome"] == "pending"

    second = auth_client.post(
        "/api/v1/interviews",
        json={"application_id": application["id"], "scheduled_at": f"{later}T15:00:00"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["round_no"] == 2

    past = auth_client.post(
        "/api/v1/interviews",
        json={"application_id": application["id"], "scheduled_at": f"{past_day}T09:00:00"},
    )
    assert past.status_code == 201

    upcoming = auth_client.get("/api/v1/interviews?scope=upcoming").json()
    assert upcoming["total"] == 2
    assert [item["round_no"] for item in upcoming["items"]] == [1, 2]
    assert auth_client.get("/api/v1/interviews?scope=past").json()["total"] == 1

    updated = auth_client.patch(
        f"/api/v1/interviews/{past.json()['id']}",
        json={"outcome": "passed", "feedback": "Strong systems knowledge"},
    )
    assert updated.status_code == 200
    assert updated.json()["outcome"] == "passed"
    assert updated.json()["feedback"] == "Strong systems knowledge"

    filtered = auth_client.get(f"/api/v1/interviews?application_id={application['id']}").json()
    assert filtered["total"] == 3

    assert auth_client.delete(f"/api/v1/interviews/{first.json()['id']}").status_code == 204
    assert auth_client.get("/api/v1/interviews").json()["total"] == 2


def test_time_entries_reject_overlap(auth_client: TestClient):
    task = auth_client.post("/api/v1/tasks", json={"title": "Deep work"}).json()

    first = auth_client.post(
        "/api/v1/time-entries",
        json={
            "task_id": task["id"],
            "started_at": "2026-11-17T09:00:00",
            "ended_at": "2026-11-17T10:00:00",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["duration_minutes"] == 60.0
    assert first.json()["task_title"] == "Deep work"

    overlap = auth_client.post(
        "/api/v1/time-entries",
        json={
            "task_id": task["id"],
            "started_at": "2026-11-17T09:30:00",
            "ended_at": "2026-11-17T10:30:00",
        },
    )
    assert overlap.status_code == 422
    assert overlap.json()["error"]["code"] == "time_overlap"

    adjacent = auth_client.post(
        "/api/v1/time-entries",
        json={
            "task_id": task["id"],
            "started_at": "2026-11-17T10:00:00",
            "ended_at": "2026-11-17T11:00:00",
        },
    )
    assert adjacent.status_code == 201, adjacent.text

    bad_range = auth_client.post(
        "/api/v1/time-entries",
        json={"started_at": "2026-11-17T12:00:00", "ended_at": "2026-11-17T11:00:00"},
    )
    assert bad_range.status_code == 422

    open_entry = auth_client.post(
        "/api/v1/time-entries",
        json={"task_id": task["id"], "started_at": "2026-11-17T12:00:00"},
    )
    assert open_entry.status_code == 201, open_entry.text
    assert open_entry.json()["ended_at"] is None
    assert open_entry.json()["duration_minutes"] is None

    closed = auth_client.patch(
        f"/api/v1/time-entries/{open_entry.json()['id']}",
        json={"ended_at": "2026-11-17T13:15:00"},
    )
    assert closed.status_code == 200
    assert closed.json()["duration_minutes"] == 75.0

    listed = auth_client.get("/api/v1/time-entries").json()
    assert listed["total"] == 3
    assert listed["items"][0]["started_at"].startswith("2026-11-17T12:00:00")

    assert auth_client.delete(f"/api/v1/time-entries/{first.json()['id']}").status_code == 204
    assert auth_client.get("/api/v1/time-entries").json()["total"] == 2
