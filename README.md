# CareerOS

A private, single-owner career management platform: job descriptions, resume versions,
resume/JD analysis, application tracking, interviews, follow-ups, tasks and analytics.

- Backend: Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · MySQL 8.0 (PyMySQL)
- Frontend: React · TypeScript · Vite · Tailwind CSS · React Router · TanStack Query
- Storage: private local filesystem directory (no public URLs)
- AI: provider-independent adapter layer (Google Gemini adapter for v1)

## Layout

```
backend/      FastAPI application, Alembic migrations, tests
frontend/     React single-page app
db/           Database bootstrap SQL (run once in MySQL Workbench)
docs/         Architecture, data model, decisions
```

## Quick start

Full instructions: [docs/SETUP.md](docs/SETUP.md).

```powershell
# 1. Database (already created on this machine)
mysql -u root -p < db/bootstrap.sql

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m app.cli bootstrap-owner --email you@example.com
uvicorn app.main:app --reload --port 8000

# 3. Frontend
cd ..\frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the owner account created by the CLI.

## Phase status

| Phase | Scope | State |
| --- | --- | --- |
| 0 | Architecture, scaffold, decisions | done |
| 1 | Config, MySQL engine, migrations, logging, errors, test isolation | done |
| 2 | Auth: bootstrap CLI, login, refresh rotation, sessions, rate limiting | done |
| 3 | Companies, job descriptions, applications, timeline | done |
| 4 | Resumes, versions, private file storage | done |
| 5 | AI analyzer, jobs, history | done |
| 6 | Tasks, follow-ups, interviews, time entries | done |
| 7 | Dashboard and analytics | done |
| 8 | Hardening, deployment, backup/restore | pending |

The database schema covers every entity in the PRD. Phases 0–7 are exposed as API
endpoints and linked in the UI; phase 8 (hardening and deployment) is still pending.

## What the app does

- **Applications** — list/board views, status moves with an immutable timeline, notes,
  archiving, and follow-up scheduling inside each application drawer.
- **Resumes** — private uploads (PDF/DOCX/TXT) with immutable versions and a current-version
  marker. Extracted text is stored server-side for analysis.
- **Analyzer** — compares one resume version with a saved job description or pasted JD text.
  Results are stored, idempotent per input pair, and every finding is tagged as resume
  evidence, JD requirement, or inferred recommendation. The score is an alignment indicator,
  never a hiring probability.
- **Tasks** — today/overdue/upcoming buckets, priorities, optional application links, and
  per-task time tracking (one running timer at a time, no overlapping entries).
- **Interviews** — rounds auto-number per application, prep notes, meeting links, outcomes,
  and feedback.
- **Analytics** — response/interview/offer conversions, follow-up performance, application
  trends, task completions, time logged, and resume alignment. Any ratio with a zero
  denominator renders as “Not enough data”.

## AI configuration

The analyzer uses a provider-independent adapter with a Google Gemini REST implementation.
Without a key the app stays honest: the job is created and immediately marked `failed` with
`error_code=ai_not_configured`; nothing is fabricated.

```powershell
# backend/.env
AI_PROVIDER=gemini
GEMINI_API_KEY=<your key>
GEMINI_MODEL=gemini-2.0-flash
```

Restart the API after changing the key. Failed analyses can be re-submitted once the key is
present; completed analyses for the same resume/JD pair are returned from storage instead of
being duplicated.


## Non-negotiables encoded in this repo

- MySQL 8.0 only. Startup fails closed on any other server or dialect.
- No registration endpoint, no public signup, exactly one owner created via CLI.
- Every query is owner-scoped; authorization is enforced in the backend.
- Uploads are validated by content signature, size-capped and stored outside the web root.
- No secrets in git; `.env` is ignored, `.env.example` is committed.
