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
teardown commit remains as a fallback for requests that bypass a route handler. An
`IntegrityError` raised by the pre-response commit is not translated into the error
envelope; services must keep flushing so constraint failures surface inside the handler.
Fixing the residual 500 path is deferred to the v2 schema work.

## ADR-012 — `tzdata` is a runtime dependency (D11)
Accepted. Windows has no system IANA timezone database, so `zoneinfo.ZoneInfo("UTC")`
raises `ZoneInfoNotFoundError` on a fresh machine. `tzdata` is pinned in
`backend/requirements.txt` and installed with the rest of the runtime dependencies. No
application code uses `ZoneInfo` yet; the first consumer is the owner-timezone work in v2.

## ADR-013 — `Application.follow_up_on` is derived at read time (D12)
Accepted. The earliest pending follow-up due date is authoritative. The serializer computes
`MIN(follow_up.due_on)` for pending rows; the `application.follow_up_on` column becomes
dormant and is dropped in a later migration (M6). Until that migration, the column stays in
the table so the previous values remain recoverable; writes to it are removed together with
the projection, not before.

## ADR-014 — One-time backfill preserves the existing follow-up date (D13)
Accepted. Before derivation ships, rows whose `follow_up_on` is earlier than their earliest
pending follow-up (or that have none) get a pending follow-up inserted from the stored
value. Deferred data (a stale date) is preserved rather than silently discarded, and no
derived value changes on deploy day.

## ADR-015 — Explicit up/down ordering, no drag-and-drop (D14)
Accepted. Kanban columns sort by a server-defined order (updated or created) and each card
can be moved with an explicit control. Drag-and-drop needs pointer, keyboard and touch
fallbacks plus an ordering column; it is not part of v1.

## ADR-016 — Last contact is global, not per-application (D15)
Accepted. "Last contact" is the newest interaction timestamp for the owner, used where a
single recency signal is needed. Per-application recency stays available by filtering the
interactions relation; no denormalized per-application column is added.

## ADR-017 — Deleting a contact cascades to its interactions (D16)
Accepted. Interactions belong to a contact and have no meaning without it. The foreign key
is `ON DELETE CASCADE`, matching the owner-scoped delete endpoint, which is the only path
that removes a contact.

## ADR-018 — JD/company consistency is a separate change (D17)
Accepted. `validate_references` currently checks ownership only, so a job description from
company A can be attached to an application for company B. The fix validates
`job_description.company_id == application.company_id` in the service layer and adds a
regression test. It is deliberately not bundled into Stage 0 static validation.

## ADR-019 — Interview rounds stay free text (D18)
Accepted. `interview.round_no` remains an integer the owner chooses, and any round label
("System design", "Bar raiser") lives in the free-text fields. Auto-numbering and a rounds
catalog are out of scope; the API only supplies the next integer as a default.
