# Setup

## Prerequisites

- Windows 10/11 (instructions use PowerShell), Python 3.12+, Node 20+
- MySQL Community Server 8.0 running as a service, plus MySQL Workbench for inspection
- No Docker required

## 1. Database

The databases and the application account already exist on this machine:

| Item | Value |
| --- | --- |
| Server | `127.0.0.1:3306` (service `MySQL80`) |
| Runtime schema | `careeros` |
| Test schema | `careeros_test` |
| App user | `careeros_app` (SELECT/INSERT/UPDATE/DELETE + DDL for Alembic) |

To reproduce elsewhere, run `db/bootstrap.sql` in Workbench as `root` (replace the
password placeholder) and put the same password in `backend/.env`.

Workbench connection:

```
Connection name: CareerOS (local)
Hostname: 127.0.0.1   Port: 3306
Username: careeros_app
Default schema: careeros
```

## 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # then edit values (see below)
alembic upgrade head
alembic current             # should print the head revision
```

Required `.env` values:

| Key | Meaning |
| --- | --- |
| `SECRET_KEY` | 64+ random chars, signs access tokens |
| `DATABASE_URL` | `mysql+pymysql://careeros_app:<password>@127.0.0.1:3306/careeros?charset=utf8mb4` |
| `CORS_ORIGINS` | Comma-separated dev origins, default `http://localhost:5173` |
| `STORAGE_DIR` | Private upload directory, default `./storage` |
| `GEMINI_API_KEY` | Required for the analyzer; without it analyses fail honestly with `ai_not_configured` |

Create the single owner (prompts for the password, never echoes it):

```powershell
python -m app.cli bootstrap-owner --email you@example.com --name "Your Name"
```

Run the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

- http://127.0.0.1:8000/health — liveness
- http://127.0.0.1:8000/ready — database check
- http://127.0.0.1:8000/docs — OpenAPI (development only)

### AI analyzer

Set `GEMINI_API_KEY` in `backend/.env` (see `.env.example`) and restart the API. The analyzer
runs as a background job: `POST /api/v1/analyses` stores the job, then performs the Gemini call.
Analysis jobs are idempotent per resume version + job description text hash; a newer submission
supersedes older queued/running jobs for the same pair. Jobs left `queued`/`running` by a
restart are marked failed at startup.

With no key configured, the job is marked `failed` with `error_code="ai_not_configured"` and a
message telling you to add the key — no result is invented. The analyzer UI polls the job every
2 seconds while it runs and renders findings grouped by kind (resume evidence, JD requirement,
inferred recommendation).

## 3. Frontend

```powershell
cd frontend
npm install
npm run dev
```

http://localhost:5173 — Vite proxies `/api` to the backend, so cookies stay same-origin.

## 4. Tests

```powershell
cd backend
pytest                                   # unit + API tests against careeros_test
cd ..\frontend
npm run test                             # component tests
npm run typecheck                        # strict TypeScript
```

The backend suite refuses to run unless `CAREEROS_ENV=test` and the database name ends in
`_test`, so it cannot point at `careeros`.

## 5. Migrations

```powershell
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1        # only in development, verify before shipping
```

Never edit an applied migration. Never call `create_all` outside tests.

## 6. Backup / restore (execute before calling this production-ready)

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
mysqldump -u careeros_app -p --single-transaction --routines --databases careeros > backups\careeros-$(Get-Date -f yyyyMMdd-HHmm).sql
Get-Item backups\*.sql | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Restore into a scratch schema first, verify row counts, then swap. Copy `backend/storage/`
alongside the dump — the database stores only file metadata.
