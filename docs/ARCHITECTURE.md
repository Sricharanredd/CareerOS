# Architecture

```
frontend (Vite dev server :5173)
      │  /api/v1/*  (proxied in dev, same origin in prod)
      ▼
FastAPI app  ── routers ── schemas (Pydantic v2)
                 │
                 ├─ services      business rules, transactions
                 ├─ repositories  SQLAlchemy queries, owner scoping
                 └─ core          config, security, logging, errors, rate limit
                        │
                        ▼
                 MySQL 8.0 (PyMySQL, utf8mb4, UTC)
```

Layer rules, enforced by review:

- **Routers** parse/validate input, call one service, serialize an explicit response schema.
  No queries, no branching business logic.
- **Services** own invariants (status transitions, duplicate detection, archive rules),
  raise `AppError` subclasses, and never touch `Request`/`Response`.
- **Repositories** own SQLAlchemy statements. Every read is owner-scoped through a required
  `owner_id` argument; there is no unscoped `get(id)` helper.
- **Schemas** are separate for input and output. ORM objects never leave the app boundary.

## Request lifecycle

1. `RequestContextMiddleware` assigns/propagates `X-Request-ID`, binds it to a contextvar
   used by the JSON logger and by error envelopes.
2. `SecurityHeadersMiddleware` adds CSP, `X-Content-Type-Options`, `X-Frame-Options`,
   `Referrer-Policy`, `Permissions-Policy`.
3. CORS handles the dev origin allow-list (production serves the SPA same-origin).
4. Route dependency supplies a SQLAlchemy `Session` inside a transaction: commit on success,
   rollback on exception. `CommittingAPIRouter` commits once the endpoint has produced its
   response, before it is sent, so an immediate client refetch sees the new rows; dependency
   teardown remains the fallback. Pool: `pool_pre_ping=True`, `pool_recycle=1800`.
5. Errors are normalized by handlers into the single error envelope; unexpected exceptions
   are logged with a stack trace but answered with a sanitized message.

## Authentication

| Concern | Implementation |
| --- | --- |
| Password hashing | Argon2id (`argon2-cffi`), rehash-on-login when parameters change |
| Access token | JWT HS256, 15 min, claims `sub`, `sid`, `typ=access`, `jti`, `exp` |
| Refresh token | 256-bit opaque, SHA-256 hashed at rest, 14 days, rotating |
| Reuse detection | Revoked token replayed → entire `family_id` revoked |
| Session list | `GET /auth/sessions`, revoke one/all |
| Rate limiting | In-process sliding window + exponential lockout per (IP, email) |
| CSRF | Double-submit cookie on the two cookie-authenticated routes |

The owner account is created only by `python -m app.cli bootstrap-owner`. There is no
registration route; the CLI refuses to create a second owner.

## Files

- Signature check on the first bytes (`%PDF-`, `PK\x03\x04` + `word/document.xml`), not the
  extension. MIME is derived from the sniffed type.
- 5 MB cap enforced while streaming, before anything is persisted.
- Stored as `storage/<kind>/<uuid4>`; original name stored as metadata only.
- `sha256` recorded for integrity and duplicate awareness.
- Downloads go through `GET /files/{id}/download`, authenticated and owner-scoped, with
  `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

## Extracted text

`pypdf` for PDF, `python-docx` for DOCX, strict UTF-8 with fallback for TXT. Text is cached
on `resume_version.extracted_text` and `job_description.raw_text`. A scanned PDF yields an
empty string, which the API reports as a 422 with an actionable message rather than a
silently empty analysis.

## Logging

One JSON object per line: `ts`, `level`, `logger`, `msg`, `request_id`, `method`, `path`,
`status`, `duration_ms`, `owner_id` (never email, password, token or document text).
