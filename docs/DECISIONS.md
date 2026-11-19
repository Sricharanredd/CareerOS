# Architecture Decision Record

## ADR-001 — MySQL 8.0 as the only database
Accepted. Single deployment target, transactions and constraints we rely on, and the owner
inspects the schema in MySQL Workbench. `app/db/session.py` refuses to build an engine for
any dialect other than `mysql+pymysql`, and `app/main.py` calls `assert_mysql_8()` at startup.
There is no SQLite fallback in runtime code. Tests use a separate MySQL schema whose name
must end in `_test`, guarded by `CAREEROS_ENV=test`.

## ADR-002 — UUID (CHAR(36)) primary keys
Accepted. PRD allows BIGINT or UUID. UUIDs keep client-side optimistic creation and merging
trivial, and CHAR(36) keeps rows readable when browsing in Workbench. Index bloat is
irrelevant at single-owner scale.

## ADR-003 — Access token in memory, refresh token in an HttpOnly cookie
Accepted. Access token: JWT, 15 minutes, sent as `Authorization: Bearer`. Refresh token:
opaque 256-bit value, stored hashed (SHA-256) in `session.refresh_hash`, sent only as an
HttpOnly cookie scoped to `/api/v1/auth`. The SPA never persists the access token, so XSS
cannot exfiltrate a long-lived credential. Rotating refresh tokens with family-based reuse
detection: presenting a revoked token revokes the whole family.

## ADR-004 — Double-submit CSRF for cookie-authenticated endpoints
Accepted. `POST /auth/refresh` and `/auth/logout` are the only cookie-authenticated routes.
They require `X-CSRF-Token` to equal the readable `careeros_csrf` cookie. Bearer-authenticated
routes are immune to CSRF by construction.

## ADR-005 — Alembic owns the schema; nothing is auto-created at startup
Accepted. `Base.metadata.create_all` appears only in the test fixture. Startup validates
connectivity and version, nothing more.

## ADR-006 — Full entity graph in one initial migration
Accepted. The initial revision creates every PRD entity, including tables whose endpoints
arrive in later phases. This is preferable to five migrations that rewrite relationships
later, and it lets the owner review the complete model in Workbench on day one.

## ADR-007 — Local private filesystem for uploads
Accepted. Files are written to `backend/storage/<kind>/<uuid>` with generated names, the
original name kept only as metadata, and served exclusively through an authenticated
endpoint. Object storage stays out of v1 (PRD non-goal without approval).

## ADR-008 — Provider-independent AI adapter
Accepted. `app/ai/` defines the `AnalysisProvider` protocol, a Gemini REST implementation and
a deterministic stub used by tests. Prompt version and input hash live with the job row, so
results are reproducible and duplicate requests are idempotent. A missing key marks the job
failed with `ai_not_configured` instead of fabricating a result. The analyzer exposes
`/api/v1/analyses`, `/stats` and `/resume-scores`; jobs run through FastAPI background tasks.

## ADR-009 — Soft archive instead of hard delete for user data
Accepted. Companies, job descriptions, resumes and applications archive. Hard delete is
blocked when a resume version is referenced by an application or analysis, and the API
explains why.

## ADR-010 — Error envelope and pagination contract
Accepted. Errors always return `{"error": {"code", "message", "details", "request_id"}}`.
Lists return `{"items": [...], "total": n, "page": p, "page_size": s}`, `page_size <= 100`.

## ADR-011 — Commit before the response leaves the app
Accepted. FastAPI exits `yield` dependencies after sending the response, so a client that
immediately refetches a list after a mutation could read pre-commit rows. `app/core/routing.py`
defines `CommittingAPIRouter`/`CommitBeforeResponseRoute`; the session is exposed on
`request.state` by `get_db` and committed once the endpoint has produced its response. The
teardown commit remains as a fallback for requests that bypass a route handler.
