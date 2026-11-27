# Stage 2 — B2 Implementation Report

- Date: 2026-11-23
- Scope: B2 — privacy gate, Cloudflare Workers AI adapter, safe provider selection, free-only
  enforcement, allowlist logging, mocked tests.
- Result: **implemented and green**. 143 collected tests pass (137 test functions), `ruff check app
  tests alembic` clean.
- All automated tests are mocked. Two **approved** live validation attempts were made with synthetic
  text; both returned HTTP 401 and the adapter surfaced `provider_auth_failed`. One request per
  attempt, no retry, no provider switch. A **replacement token** was later verified live: token-verify
  `200 active`, Workers AI model search `200`, and one minimal `/ai/run` against the configured 70B
  model `200` with a JSON-object response (§14.10). A **full synthetic end-to-end analysis** then
  succeeded through the application API — `succeeded`, `attempts=1`, score 80, five findings (§15).
- Cloudflare credentials are configured only in the untracked local `backend/.env`. No token, auth
  header, resume text or provider body appears in this report, the tests, or Git. The one leak found
  during live validation — the account id inside `httpx`'s INFO request URL — is **fixed and
  regression-tested** (§7, §10.2).
- B3 was **not** started. There is no cross-provider fallback, no health manager, no quota manager.

## 1. Privacy gate architecture

`backend/app/ai/privacy.py` is a pure module over `Settings` + the registry. It never performs I/O and
never constructs an adapter.

`denial_reasons(spec, settings, *, required_context_tokens=8000)` returns a tuple of reason codes; an
empty tuple is approval. All checks must pass, in this order:

| # | Check | Failure reason |
|---|---|---|
| 1 | Provider is in `AI_APPROVED_PROVIDERS` | `not_approved` |
| 2 | Registry row approves `RESUME_DATA_CLASS` (`resume_pii`) | `data_class_not_approved` |
| 3 | Registry row has a `privacy_verified_on` date | `privacy_unverified` |
| 4 | Retention is documented and not `"unknown"` | `retention_unknown` |
| 5 | Training policy is known; `True` requires `AI_ALLOW_TRAINING_PROVIDERS=true` | `training_unknown`, `training_not_allowed` |
| 6 | `free_tier` holds while `AI_FREE_ONLY=true` | `not_free` |
| 7 | JSON output is documented | `no_json` |
| 8 | Context window is known and ≥ the required minimum | `context_unknown`, `context_insufficient` |

`approved_candidates(settings)` walks `AI_PROVIDER_ORDER`, resolves each provider's configured model,
requires a registry row, and keeps only models with no denial reason. Unknown is denial: a missing row,
a missing verification date, `retention="unknown"`, `trains_on_content="unknown"`, or an unverified
context window all exclude the model.

Consequences enforced by tests:

- Adding a name to `AI_APPROVED_PROVIDERS` cannot approve a model the registry has not verified
  (`test_allowlist_alone_never_approves_a_model`).
- A free tier alone cannot approve a model (same test: Gemini is free and still denied).
- `AI_ALLOW_TRAINING_PROVIDERS=true` still does not approve a model with
  `trains_on_content="unknown"` or with no approved data class.
- The Cloudflare 8B row is privacy-approved but stays ineligible because its context window is not
  verified.
- Only `cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast` passes the gate in the shipped registry
  (`test_every_registry_row_but_the_verified_cloudflare_model_is_denied`).

The gate runs inside `select_provider()` before any adapter is returned; the adapter is only
constructed after the gate approves it, and handling a provider request happens inside `analyze()`.
`test_denied_selection_makes_no_http_call` fails the test if an `httpx.Client` is constructed while the
gate denies.

## 2. Provider selection and failure behaviour

`backend/app/ai/router.py`:

```python
select_provider(settings) -> AnalysisProvider | None
```

1. Build the approved candidate list (gate, §1).
2. Return the first candidate whose adapter can be constructed from settings.
3. If no candidate survives, but a provider in the chain **is** configured and was refused by the
   gate, raise `ProviderPrivacyDenied`.
4. Otherwise return `None`.

`registry.get_provider()` calls that with `get_settings()`. There is no runtime loop over providers,
no second attempt on failure, no paid escalation, and no Gemini fallback.

`services/analysis.py` maps the two selection failures onto existing job fields:

| Situation | `error_code` | `error_message` |
|---|---|---|
| Nothing approved and configured | `ai_not_configured` | Fixed text naming `AI_APPROVED_PROVIDERS` + `backend/.env`, and stating that resume text is never sent to an unapproved provider |
| Configured provider refused by the gate | `provider_privacy_denied` | `No configured AI provider is approved to process resume data.` |

When no provider was selected, `job.provider` and `job.model` are stored empty — the job does not
claim Gemini or Cloudflare processed anything. A selected job records the actual
`provider`/`model` returned by the adapter, reusing the existing columns (no migration).

## 3. Cloudflare adapter

`backend/app/ai/cloudflare.py`, native REST endpoint:

```
POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
Authorization: Bearer <CLOUDFLARE_API_TOKEN>
```

Request body:

```json
{
  "messages": [{"role": "user", "content": "<shared CareerOS prompt>"}],
  "max_tokens": 4096,
  "temperature": 0.2,
  "response_format": {"type": "json_object"}
}
```

- `messages`, not `prompt`, matching Cloudflare's current text-generation examples.
- `max_tokens` is always sent: the Workers AI default is 256 and would truncate the analysis JSON.
- `json_object` is used instead of `json_schema`. Cloudflare documents `json_object` and `json_schema`;
  Pydantic's `model_json_schema()` emits `$defs`/`$ref`, and Cloudflare does not document `$ref`
  support. The prompt already carries the full `SCHEMA_HINT`, and the shared validator enforces the
  shape. This is recorded as a deliberate shortcut in the code.
- Response parsing follows the documented envelope: `{"success": ..., "result": {"response": ...}}`.
  `result.response` may be a JSON string or an object; both are accepted. Anything else is
  `ProviderInvalidOutput`.
- `validate_or_repair(..., max_repairs=0)`: no second prompt. Gemini keeps its historical single
  repair.
- Timeout uses `AI_TIMEOUT_SECONDS` through `httpx.Client(timeout=...)`.
- Budget check before any request: `(len(resume) + len(jd)) // 4 + 512 > 24_000 - 4_096` raises
  `ProviderError(code="resume_too_large_for_provider")` rather than truncating the resume. The JD is
  included in the estimate.
- The adapter never logs and never puts a response body, header, token or prompt in an exception.

## 4. Configuration

Added/changed in `backend/app/core/config.py` and documented in `backend/.env.example`:

| Setting | Default | Purpose |
|---|---|---|
| `AI_PROVIDER_ORDER` | `cloudflare` | Ordered, gate-approved selection chain |
| `AI_APPROVED_PROVIDERS` | `cloudflare` | Explicit allowlist; necessary but not sufficient |
| `AI_ALLOW_TRAINING_PROVIDERS` | `false` | Must stay false for privacy |
| `AI_FREE_ONLY` | `true` | Refuses models with no free tier |
| `AI_TIMEOUT_SECONDS` | `90` | Existing setting, reused by Cloudflare |
| `CLOUDFLARE_API_TOKEN` | empty | Bearer token; no default, never logged |
| `CLOUDFLARE_ACCOUNT_ID` | empty | Path parameter |
| `CLOUDFLARE_MODEL` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Approved model id |
| `AI_PROVIDER` | `cloudflare` | Legacy field; used only when `AI_PROVIDER_ORDER` is empty |

`GEMINI_API_KEY` / `GEMINI_MODEL` remain so existing local config still loads; Gemini is not eligible
under the registry and is not in the default chain.

`ai_configured` (returned by `/api/v1/auth/meta`) now means "Cloudflare credentials are present **and**
Cloudflare is on the allowlist". It is credential presence only; the gate remains authoritative.

## 5. Model compatibility findings (documentation, not live verification)

| Property | Value | Source |
|---|---|---|
| Model id | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare model page |
| Context window | 24,000 tokens | Cloudflare model page |
| Zero data retention | Yes | Cloudflare model page |
| JSON Mode | Supported (`response_format`; `json_object` / `json_schema`) | Cloudflare JSON Mode docs |
| Schema guarantee | **Not guaranteed**; Cloudflare documents a `JSON Mode couldn't be met` error | Cloudflare JSON Mode docs |
| Free allowance | Workers AI free allocation (Neurons/day) with per-task rate limits | Cloudflare limits docs |
| `max_tokens` default | 256 | Cloudflare model page |

The response envelope, error envelope (`success:false` + `errors[]`), 429/401/403 behaviour and the
JSON Mode error marker were implemented from those docs and exercised only through mocked HTTP.
**Live status:** both approved validation attempts with synthetic text were rejected at the edge with
HTTP 401 (`provider_auth_failed`), so the request never reached the model. Real-model JSON quality,
`json_object` adherence and the 24k-token budget remain unverified until a token with Workers AI access
is configured.

## 6. Error mapping

| Signal | Raised | Retry |
|---|---|---|
| 429 | `ProviderRateLimited` (+ numeric `Retry-After` when present) | No |
| 401 / 403 | `ProviderAuthFailed` (fixed message) | No |
| 500 / 502 / 503 / 504 | one `sleep(1.0)` retry, then `ProviderUnavailable` | Once |
| Other 4xx | `ProviderError(code="provider_rejected")` | No |
| Timeout / connect error | `ProviderTimeout` / `ProviderUnavailable` | No |
| `success:false` containing `JSON Mode couldn't be met` | `ProviderInvalidOutput` | No |
| `success:false` containing blocked/safety/moderation markers | `ProviderBlocked` | No |
| Empty or unexpected `result.response` | `ProviderInvalidOutput` | No |
| JSON invalid / fields missing | `ProviderInvalidOutput` from the shared validator | No repair |
| Resume+JD exceeds the model budget | `ProviderError(code="resume_too_large_for_provider")` | No request made |

429 is treated as "rate limited, try later", not as permanent daily exhaustion; `retry_after_seconds`
is exposed only when the header is numeric. No local counter pretends to know the provider's balance.
All adapter messages are fixed strings; provider bodies are inspected only in memory for classification
and are never copied into `message`, `str(exc)`, logs, or the job row.

## 7. Logging and credential protection

`backend/app/core/logging.py` is now allowlist-only:

- `JsonFormatter` copies an `extra` field only when its name is in `ALLOWED_LOG_FIELDS`; anything else
  is dropped and counted in `dropped_fields`.
- The same filter applies to extras from third-party loggers.
- Exception records carry `exc_type` and `exc_at` (basename:line of the last frame) only. The exception
  message is never serialised, because it can contain request or resume content.
- Existing call sites use only allowed names (`job_id`, `provider`, `code`, `path`, `status`, …).

Tests (`backend/tests/test_logging.py`) use `RESUME_CANARY_7f3c9a` and
`sk-CANARY-0000-not-a-key` and assert neither appears in formatted output for unapproved extras or an
exception message. Adapter and integration tests assert canaries and `test-token` never appear in
`str(exc)` or the API response.

Honest limit: the formatter filters *fields*, not the developer-supplied message string
(`record.getMessage()`). Our call sites only pass constant event strings; a future call that
interpolates content into the message would still leak. That is a review rule, and the canary tests
cover the paths that exist.

**Gap found during live validation, now fixed:** `httpx` logs each request at INFO with the full URL.
The Cloudflare URL contains the account id, so it appeared in the log even though the token did not:

```
{"logger": "httpx", "msg": "HTTP Request: POST https://api.cloudflare.com/client/v4/accounts/<account-id>/ai/run/..."}
```

The fix is one entry in the existing noisy-logger list in `configure_logging()`:

```python
for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine", "pypdf", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
```

An explicit level on the `httpx` logger stops the record being created at all, so the URL never
reaches any handler. The root logger and every application logger are untouched: provider errors
(`careeros.analysis`, WARNING with `code`) still reach the log, and nothing is disabled globally.

**Root cause of a second issue, also fixed:** `alembic/env.py` called `fileConfig(...)` without
`disable_existing_loggers=False`. `fileConfig` therefore disabled every already-created logger,
including `careeros.analysis` — any in-process migration silenced application error logs (and the
whole test suite had this state). The one-keyword fix keeps app loggers enabled; the regression test
depends on it.

`.env` remains untracked; `.env.example` contains placeholders only. No credential is in Git history.

## 8. Free-only enforcement

- No paid model exists in the registry. Every row has `free_tier=True` except none; a row with
  `free_tier=False` is refused while `AI_FREE_ONLY=true`.
- No code path reads an OpenAI or OpenRouter key, activates billing, or buys credit.
- A 429 never switches provider, and there is no second provider to switch to.
- Failure of the approved provider is terminal for that job and surfaces a typed error.
- The privacy gate is never bypassed to keep availability.

## 9. Provider-selection behaviour

| Configuration | Selected | Result |
|---|---|---|
| Cloudflare token + account, default allowlist/order | `CloudflareProvider` (70B) | Analysis runs on Cloudflare |
| Missing Cloudflare credentials | none | `ai_not_configured`, no outbound request |
| Cloudflare credentials but provider not allowlisted | none | `provider_privacy_denied`, no outbound request |
| `CLOUDFLARE_MODEL` set to an unregistered id | none | `provider_privacy_denied` (configured provider refused) |
| `CLOUDFLARE_MODEL` set to the 8B row | none | `provider_privacy_denied` (context unknown) |
| Gemini key + Gemini allowlisted + training waiver | none | `provider_privacy_denied`; Gemini is never contacted |
| Groq / OpenRouter / OpenAI | none | Not configured, not approved |

## 10. Tests and exact results

```
backend> .venv\Scripts\python.exe -m ruff check app tests alembic
All checks passed!

backend> .venv\Scripts\python.exe -m pytest
143 passed, 0 failed, 0 skipped, 0 errors (253.6s, exit 0)
[junit-xml: tests=143 failures=0 errors=0 skipped=0]
```

| File | Functions | Notes |
|---|---|---|
| `test_ai_privacy.py` | 15 (new) | Every gate check, deny-on-unknown, allowlist/registry interaction |
| `test_ai_cloudflare.py` | 23 (new) | Success, fenced JSON, malformed/empty/missing fields, object response, 429 ± Retry-After, 401/403, 5xx retry, 400, refusal, JSON-mode error, timeout, budget, unregistered model, documented request contract, missing-permission 401, missing credentials |
| `test_ai_router.py` | 8 (new) | Selection, missing credentials, denial before HTTP, no Gemini fallback, registry wiring |
| `test_ai_integration.py` | 4 (new) | Full job on mocked Cloudflare; Gemini-only config fails without fallback; auth failure does not leak; outage does not switch providers |
| `test_logging.py` | 5 (new) | Allowlist, exception-message suppression, third-party extras, `httpx` quieted without disabling app logs, synthetic account id absent from captured logs |
| `test_ai_providers.py` / `test_ai_repair.py` | 15 (B1) | Unchanged |
| Existing suite | 82 | All still pass; only `test_analysis.py`'s expected message changed |

B2 adds 56 test functions / 59 cases (84 collected before → 143 now).

Changes to existing tests:

- `tests/test_analysis.py`: `ai_not_configured` message assertion now checks `backend/.env` instead of
  `GEMINI_API_KEY`, because the message must no longer point users at Gemini.
- `tests/test_productivity.py`: the relative-date fix from B1 remains; it was pre-existing test rot, not
  a B2 regression.
- `tests/conftest.py`: clears Cloudflare credentials and the training flag, and adds an `ai_settings`
  factory that never reads a real credential from `backend/.env`.

No live network call in the automated suite, no real quota consumed, no MySQL schema change.

### 10.1 Logging regression tests (added in housekeeping)

| Test | What it pins |
|---|---|
| `test_configure_logging_quiets_httpx_without_disabling_app_logs` | after `configure_logging("INFO")`, `httpx` is at WARNING, `httpx.isEnabledFor(INFO)` is false, root stays at INFO with a handler |
| `test_httpx_request_url_is_not_captured_while_app_errors_are` | a synthetic account id (`0123…cdef`) in an `httpx` INFO URL never appears in captured logs, no `Authorization`/`Bearer` text appears, and a `careeros.analysis` WARNING with `code=provider_auth_failed` is still captured |

The synthetic identifier is deliberately fake and is not the real account id.

### 10.2 Housekeeping: synthetic database cleanup (Task 2)

Inspection first, then deletion through the application's own service functions, never raw `DELETE`s.

Verified before deleting:

| Check | Result |
|---|---|
| Resume versions whose text contains the synthetic canary | exactly 1 |
| Analysis jobs whose `jd_text` contains the synthetic JD title | exactly 1, and it is the same job |
| Version label / resume name | `b2-smoke` / `Synthetic Live Test` |
| Owner | single dev owner; resume, version, job and file object all share it |
| Applications referencing the version | 0 |
| Audit rows referencing the resume | 0 |
| Other versions on the same resume | 0 |
| `AnalysisResult` rows for the job | 0 (the 401 produced no result) |
| File object references | exactly 1 version, 0 job descriptions |

Deleted, in this order, using `services.analysis.delete()` then `services.resume.delete()` (which
cascades versions/jobs and removes the stored blob via `storage.delete_file`):

| Record | Identifier | Detail |
|---|---|---|
| Analysis job | `d91edeed-3483-4402-88c2-5d56a8d2dde6` | failed, `provider_auth_failed`, cloudflare / 70B, 1 attempt |
| Resume | `3e928878-a7ca-42db-8fa2-ef01559f7a68` | name `Synthetic Live Test` |
| Resume version | `496d7184-3b9d-46d2-98d0-c4e916a52672` | label `b2-smoke`, version 1 |
| File object | `59a66225-658c-4fdf-8940-851b60fb3db6` | `synthetic.docx`, 36,816 bytes |
| Stored blob | `storage/resume/4e04baf197aff212bd2181ddd9920ada.docx` | existed before, gone after |

Post-delete verification: versions containing the canary 0, jobs containing the synthetic JD 0, and
all four rows plus the stored file absent. Deleting the job also wrote one
`analysis.delete` audit row, as the service does for every deletion. No real user data was touched.


### Live validation run (manual, approved) — attempt 2, via the real API

| Item | Result |
|---|---|
| Date/time (local) | 2026-11-23 21:23:59 (15:53:59 UTC) |
| Preflight | token and account id present; model `@cf/meta/llama-3.3-70b-instruct-fp8-fast`; `AI_FREE_ONLY=true`; `AI_ALLOW_TRAINING_PROVIDERS=false`; chain `['cloudflare']`; approved `['cloudflare']`; 70B gate denials `[]`; no other routable row; no paid row registered |
| Backend startup | started on `127.0.0.1:8000` (no `--reload`), `/health` returned `ok`; stopped again after the test |
| Workflow | existing endpoints only: `POST /resumes` (201) → `POST /analyses` (201) → `GET /analyses/{id}` |
| Provider / model attributed | `cloudflare` / `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| HTTP result | **401 Unauthorized**, one request, no retry |
| Normalised error | `provider_auth_failed`, `attempts=1`, job `failed` |
| JSON validation | not applicable — no response body was returned by the model |
| Pydantic validation | not applicable — no `AnalysisResult` row was created |
| Token usage | unavailable (no model response) |
| Job record | `provider`/`model` recorded truthfully; `error_message` contains no canary or token; `jd_excerpt` stored as normal |
| Security | no token in log; no `authorization`/`bearer` in log; no resume canary or synthetic email in log; no `gemini` anywhere in the log; exactly one upstream URL logged |
| Credential hygiene | `.env` line single, 53 chars, printable ASCII, no whitespace/quotes/BOM, `cfut_` prefix, account id 32 hex — copy/paste corruption ruled out |

**Log leak found.** `httpx` logs `HTTP Request: POST <url> "HTTP/1.1 401 Unauthorized"` at INFO. The
URL contains the Cloudflare account id (path segment), not the token. Everything else stayed clean.
Proposed one-line fix (not applied, awaiting approval): silence the `httpx` logger to WARNING in
`app/core/logging.py`, the same way SQLAlchemy engine logging is already suppressed.

**Classification.** 401 means the credential itself was rejected — invalid, revoked, or not a
Workers AI API token. It is explicitly **not** the 403 permission case, which the adapter also maps to
`provider_auth_failed`. Distinguishing 401 from 403 in the job row would be an error-mapping change and
was not made.

**Residue.** The API run left one synthetic resume version and one failed analysis job in the dev
database (labelled `Synthetic Live Test` / `b2-smoke`). Both were removed afterwards under approval —
see §10.2. The backend process was stopped and the temporary test scripts were deleted.


## 11. Files modified

New:

- `backend/app/ai/privacy.py`
- `backend/app/ai/router.py`
- `backend/app/ai/cloudflare.py`
- `backend/tests/test_ai_privacy.py`
- `backend/tests/test_ai_cloudflare.py`
- `backend/tests/test_ai_router.py`
- `backend/tests/test_ai_integration.py`
- `backend/tests/test_logging.py`

Modified:

- `backend/app/core/config.py` — AI/Cloudflare settings, chain/allowlist properties, `ai_configured`
- `backend/app/ai/providers.py` — `configured_model()` and `build_adapter()` for both providers
- `backend/app/ai/registry.py` — delegates to the router/gate
- `backend/app/ai/gemini.py` — fixed provider error text (no response-body echo)
- `backend/app/services/analysis.py` — privacy-denied handling, honest empty attribution, message
- `backend/app/core/logging.py` — allowlist formatter, exception type/location only, `httpx` URL
  logging quieted (housekeeping)
- `backend/alembic/env.py` — `fileConfig(..., disable_existing_loggers=False)` so migrations no longer
  silence application loggers (housekeeping)
- `backend/.env.example` — Cloudflare/AI placeholders
- `backend/tests/conftest.py`, `backend/tests/test_analysis.py`

B1 files (`base.py`, `models.py`, `repair.py`, `test_ai_providers.py`, `test_ai_repair.py`) are
unchanged in B2, except `providers.py` (adapter map, `configured_model`) which is listed above.

No frontend, authentication, schema, migration **script**, or dependency change. `alembic/env.py` is
the migration runner's logging setup, not a schema revision.

## 12. Remaining risks

1. **Live verification is complete for one synthetic case.** Both original approved attempts were
   rejected with HTTP 401 (`provider_auth_failed`); the request contract was checked against
   Cloudflare's docs and found correct (§14). A replacement token was verified live — token-verify,
   Workers AI model search and one minimal `/ai/run` all returned `200` (§14.10) — and one full
   synthetic resume analysis succeeded through the API (§15). Remaining unverified: output quality
   across varied resumes, schema adherence under adversarial prompts, and the 24k-token budget at its
   limit.
2. **`json_object` is looser than a JSON Schema.** Cloudflare does not document `$ref` support, so the
   full Pydantic schema is not sent. Invalid output fails the job; it is not repaired.
3. **24,000-token context.** Long resumes/JDs fail with `resume_too_large_for_provider`. The estimate
   (`chars/4 + 512`) is approximate and deliberately conservative on ASCII; non-Latin text may be
   underestimated by the character heuristic.
4. **Quota reality.** The free allowance (~10k Neurons/day, shared across models) is not tracked. A 429
   becomes a visible failure; there is no reset clock or retry schedule.
5. **429 classification is coarse.** Temporary rate limiting and daily exhaustion share
   `provider_rate_limited`; only a numeric `Retry-After` distinguishes them.
6. **Registry trust.** Retention/no-training claims are contractual, not enforceable in code.
   `privacy_verified_on` records when they were checked.
7. **`ai_configured` is credential presence only.** It can report true while the gate denies (for
   example, an unregistered model id); `/meta` is a hint, not an approval.
8. **Switching the default changes `input_hash` for new submissions** (provider/model are hashed).
   Existing rows keep their hash; a previously analyzed pair is analyzed once more, with no data loss.
9. **No encryption at rest / backup encryption / DB TLS / HSTS.** Unchanged gaps outside B2.
10. **Gemini key in the local `backend/.env`.** The key still exists locally and must be rotated.
    `AI_PROVIDER=gemini` may still appear there; it is ignored unless `AI_PROVIDER_ORDER` is empty, and
    Gemini cannot pass the registry gate.
11. **Logging limit** described in §7: message strings are developer-controlled and not filtered.
12. ~~**The account id is logged.**~~ **Resolved in housekeeping.** `httpx` is pinned to WARNING, so the
    URL is never formatted. Residual risk: a future handler that logs the request URL itself (for
    example a new HTTP client used at INFO) would reintroduce it. The regression test guards the
    client that exists.
13. **403 was reported as a credential failure (resolved in B3 M1-A).** B2 mapped all 403 responses
    to `provider_auth_failed`, but Cloudflare's documented 403s are entitlement/plan/model-terms
    errors. B2 left it unchanged because no 403 was observed and it alters the error contract. B3
    M1-A corrected it: `401 → provider_auth_failed`; `403 → provider_permission_denied` or
    `provider_entitlement_denied` for documented plan/terms codes (`5035`, `5016`, `5018`, `3041`);
    unknown 403 stays permission. See §14.4 and `docs/STAGE2_B3_ARCHITECTURE.md` §11.

## 13. Was the active provider switched?

- **In code: yes.** Gemini is no longer reachable for resume analysis. Cloudflare is the sole
  gate-approved model, and `get_provider()` selects it when credentials are present.
- **Configuration: Cloudflare credentials are set in the untracked local `backend/.env`.** The
  selection check confirms `CloudflareProvider` with the 70B model and an empty denial list; no
  request is needed for that check.
- **Live call: attempted twice, rejected both times.** The API-path attempt returned HTTP 401 and the
  job recorded `provider_auth_failed` with `attempts=1` and Cloudflare attribution. Until a token with
  Workers AI access is valid, analyses fail with `provider_auth_failed` — they do **not** fall back to
  Gemini.
- **Production cutover: not complete.** Requires a working Workers AI token, a passing live request,
  and a backend restart with the updated `.env`.

## 14. Cloudflare authentication investigation (2026-11-23)

No live request was made in this investigation. Everything below is static analysis, official
documentation, and offline tests.

### 14.1 Executive finding

**No defect was found in how CareerOS builds the request.** The URL, method, headers, body and model
id match Cloudflare's documented REST contract, the configured account id and token are the values
actually used, and no environment variable overrides them. The 401 is therefore a rejection of the
credential by Cloudflare, not a malformed request from the adapter.

Two documented conditions both return HTTP 401 and **cannot be distinguished without a live call**:

1. the token is invalid, revoked, deleted, rolled, or expired;
2. the token is valid but does not carry the **Workers AI** permission (Cloudflare documents
   `401` with error code `10000` for this case).

A token belonging to a different account, or an account id that is not the token's account, is also
consistent with the evidence but not provable offline. The concrete next step is a newly created
Workers AI token; the existing one should be treated as not usable for this endpoint.

### 14.2 Authentication request flow

`backend/app/ai/cloudflare.py`:

1. `CloudflareProvider.__init__` reads `settings.cloudflare_api_token`,
   `settings.cloudflare_account_id` and `settings.cloudflare_model`; if either credential is missing
   it raises `ProviderUnavailable("Cloudflare is not configured.")` before any HTTP client exists.
2. `_generate()` builds the JSON body (`messages`, `max_tokens=4096`, `temperature=0.2`,
   `response_format={"type": "json_object"}`).
3. `_post()` formats
   `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}` from those settings and
   sends `POST` with `Authorization: Bearer <token>` and `Content-Type: application/json` through
   `httpx.Client(timeout=AI_TIMEOUT_SECONDS)`.
4. `_interpret()` maps `401` and `403` to `ProviderAuthFailed`; the provider's body is never echoed.

| Element | Implementation | Cloudflare requirement | Verdict |
|---|---|---|---|
| Method | `POST` | `POST` | matches |
| URL | `/client/v4/accounts/{account_id}/ai/run/{model}` on `api.cloudflare.com` | same | matches |
| Auth header | `Authorization: Bearer <token>` | same | matches |
| Account placement | path segment, from settings | path segment | matches |
| Content type | `application/json` | JSON body | matches |
| Model id | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | catalog id, `@cf/` included once | matches |
| Body | `messages` + `max_tokens` + `temperature` + `response_format` | documented text-generation fields | matches |
| Retry on 401 | none | n/a | correct, 401 is not retryable |

### 14.3 Official documentation used

- **Workers AI — REST API** (`developers.cloudflare.com/workers-ai/get-started/rest-api/`): endpoint
  shape, `Authorization: Bearer {API_TOKEN}`, Account ID taken from the Workers AI page, and the note
  that a *custom* token needs **Workers AI - Read and Workers AI - Edit** (the Workers AI template
  token already includes them).
- **Token formats** (`/fundamentals/api/get-started/token-formats/`): user API tokens use
  `cfut_[40 characters][checksum]`; a user token is verified with
  `GET /client/v4/user/tokens/verify`; Cloudflare auto-revokes tokens found leaked by secret scanning.
- **AI Gateway — REST API authentication** (`/ai-gateway/usage/rest-api/`): *"All
  `/accounts/{account_id}/ai/*` endpoints require the Workers AI permission… A token that holds only
  an AI Gateway permission returns 401 with error code 10000."*
- **Workers AI — Errors** (`/workers-ai/platform/errors/`): the documented 403 codes are account
  blocked (`3023`), model requires Workers Paid plan (`5035`), private-model/terms (`5016`, `5018`,
  `3041`). None of them is an authentication error, and none is a 401.

### 14.4 Confirmed findings

1. **The adapter's request is correct** (table above; pinned by
   `test_request_matches_the_documented_rest_contract`).
2. **The configured values are used, unmodified.** No `CLOUDFLARE_API_TOKEN` or
   `CLOUDFLARE_ACCOUNT_ID` exists in the process environment, so `.env` is the only source; the value
   loaded by `Settings` is byte-identical to the `.env` entry; `CLOUDFLARE_API_TOKEN` appears on one
   line only; account id is 32 hex characters.
3. **The token has the shape of a current Cloudflare user token**: `cfut_` prefix, 53 characters,
   printable ASCII, no whitespace, quotes or BOM. This is consistent with `cfut_` + 40 + checksum but
   does not prove validity.
4. **A minor reporting defect exists, left unchanged:** `_interpret()` maps every `403` to
   `ProviderAuthFailed` ("rejected the API credentials"), but Cloudflare's documented 403s are
   entitlement/plan/model-terms errors. A 403 would therefore blame the credentials when the real
   cause is the account or model. No 403 was observed, and changing the error contract needs separate
   approval, so it is recorded here instead of edited.
5. **No credential or content leak in the auth-failure path**: the fixed `AUTH_MESSAGE` is returned,
   the provider body is dropped, and the token/account do not appear in logs or responses (existing
   tests plus the `httpx` WARNING fix in §7).

### 14.5 Unresolved possibilities

| # | Possibility | Evidence for | Evidence against | Distinguishable offline? |
|---|---|---|---|---|
| 1 | Token invalid, revoked, deleted, rolled, expired | exactly matches a 401; validity is unverified | format looks current and untruncated | no |
| 2 | Token valid but lacks Workers AI permission (e.g. an AI Gateway-only or unrelated custom token) | Cloudflare documents 401 code 10000 for this | token source/template unknown | no |
| 3 | Token belongs to another account, or account id is not the token's account (a zone id is also 32 hex) | 401/403 both occur for cross-account access | not provable from values alone | no |
| 4 | Wrong endpoint, header or body | none | implementation matches docs and mocked contract test | **ruled out** |
| 5 | Another undocumented auth requirement | none documented for `/ai/run` | docs require only the Bearer token | **ruled out** |
| 6 | Plan or model entitlement | 403 documented codes exist | those are 403, not the observed 401 | unlikely to explain a 401 |
| 7 | Credential copy/paste corruption | — | length, prefix, charset and whitespace all clean; `.env` value equals the loaded value | **ruled out** |

The provider's response body (which carries the Cloudflare error code, e.g. `10000` vs `9109`) is
deliberately discarded and never logged. It would separate possibilities 1–3, but surfacing it would
weaken the "no provider body in logs" guarantee; that trade-off is not taken without approval.

### 14.6 Tests added (mocked, no network)

| Test | Pins |
|---|---|
| `test_request_matches_the_documented_rest_contract` | POST, `https`, host, exact path with account + model, content type, exactly one `Bearer ` prefix, body keys |
| `test_documented_missing_permission_401_is_an_auth_failure` | the documented `401` / code `10000` body → `ProviderAuthFailed`, fixed message, one attempt |
| `test_missing_credentials_fail_before_any_http_call` (2 cases) | missing token or account → `ProviderUnavailable` at construction, message contains no credential |

### 14.7 Results

```
backend> .venv\Scripts\python.exe -m ruff check app tests alembic
All checks passed!

backend> .venv\Scripts\python.exe -m pytest
143 passed, 0 failed, 0 skipped, 0 errors (253.6s, exit 0)
```

### 14.8 Security review

- No live Cloudflare request, no backend/frontend start, no database or schema change, no migration.
- No token, header, prompt, resume text or provider body was printed, logged, stored or written to the
  report. The `.env` inspection compared lengths, prefixes and equality only.
- Privacy gate, allowlist, provider order, free-only flag, training flag, model and fallback behaviour
  are untouched; no new dependency.
- No commit or push; HEAD remains `faafe74`.

### 14.9 Exact next action required from the user

1. In the Cloudflare dashboard open **Workers AI → Use REST API → Create a Workers AI API Token**
   (template token), or create a custom token with **Account → Workers AI → Read** *and* **Edit**,
   scoped to the account whose id is already in `backend/.env`.
2. Copy the account id from that same Workers AI page and compare it with the existing
   `CLOUDFLARE_ACCOUNT_ID`; a zone id is the same length and looks identical.
3. Replace `CLOUDFLARE_API_TOKEN` in `backend/.env` yourself. Do not paste it into chat, a commit, or
   any other file.
4. Optional local sanity check (only proves the token is active, not that it has Workers AI access):
   `curl https://api.cloudflare.com/client/v4/user/tokens/verify -H "Authorization: Bearer $env:CLOUDFLARE_API_TOKEN"`.
5. Approve **one** live smoke request. A live request is still required, because only Cloudflare can
   confirm that the new token is accepted for `/ai/run` and that the model returns usable JSON.

### 14.10 Live token verification (approved, 2026-11-24)

One request was made, only to Cloudflare's documented verify endpoint
(`GET /client/v4/user/tokens/verify`). Result:

```
http_status 200
success True
result_status active
error_codes []
```

The token is **valid and active**. No token, header, or account id was printed, and no `/ai/run`
request was made. This removes "invalid/revoked/expired token" from §14.5 and leaves two causes for the
`/ai/run` 401: **the token lacks the Workers AI permission**, or **the configured account id is not the
token's account**. The dashboard shows the token's permission policies; a `GET
/accounts/{account_id}/ai/models/search` probe (no inference, no user data) would confirm which.

**Probe result (same day, approved):**

```
GET /client/v4/accounts/{account_id}/ai/models/search?per_page=1 → 403
success False, error_codes [10000]
```

Cloudflare accepted the token but refused this account/resource with the generic authentication error
(`10000`). Official docs state that every `/accounts/{account_id}/ai/*` endpoint requires the Workers AI
permission, and that a token without it (for example an AI-Gateway-only token) returns `10000`. A token
scoped to a different account produces the same refusal. The probe cannot separate those two on its own;
the token's permission policies and account resources in the dashboard are the deciding evidence. The
401/403 mix also means the response-code mapping in §14.4 is coarse, but no application change is needed
for the failure to be honest.

**Replacement token (2026-11-24, user-supplied):** the previous token had the wrong authorization; a
new token was placed in `backend/.env` by the operator. Live checks with the configured account and
model:

```
GET  /user/tokens/verify                                  → 200, success=true
GET  /accounts/{account_id}/ai/models/search?per_page=1    → 200, success=true
POST /accounts/{account_id}/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast
     minimal synthetic prompt, max_tokens=32, json_object → 200, success=true,
                                                            result.response is an object
```

So the credential and Workers AI access now work; the earlier 401 was the old token's authorization,
not the request. The inference probe used a two-line synthetic prompt (no resume, no personal data) and
consumed a negligible part of the free daily allocation. The full synthetic resume analysis was then run
through the application endpoint — see §15.

### 14.8 B3 compatibility note — HTTP 403 mapping (added in M6)

B2 mapped **both 401 and 403** to `ProviderAuthFailed` (`provider_auth_failed`), as recorded in
§14.4 item 4. B3 M1-A corrected only the 403 classification; the 401 path is unchanged.

| Response | B2 | B3 (current) | Persisted `error_code` |
|---|---|---|---|
| 401 (including Cloudflare `10000`) | `ProviderAuthFailed` | `ProviderAuthFailed` | `provider_auth_failed` |
| 403 with `5035`, `5016`, `5018`, `3041` | `ProviderAuthFailed` | `ProviderEntitlementDenied` | `provider_entitlement_denied` |
| 403 with `3023` or unknown/missing code | `ProviderAuthFailed` | `ProviderPermissionDenied` | `provider_permission_denied` |
| 403 with code `10000` | `ProviderAuthFailed` | `ProviderPermissionDenied` (not reclassified as auth) | `provider_permission_denied` |

Compatibility implications:

- Historical B2 rows keep `provider_auth_failed`; no migration or rewrite is needed.
- New 403s produce permission/entitlement codes. Any external consumer that treated
  `provider_auth_failed` as "403" must accept the two new codes. The CareerOS frontend does not key
  on these strings; it renders the stored message.
- `ProviderEntitlementDenied` subclasses `ProviderPermissionDenied`, so existing
  `except ProviderPermissionDenied` handlers also catch it.
- Neither auth nor permission/entitlement is retried or counted toward the breaker. The provider is
  disabled for the process on auth/permission failure.
- Gemini (structurally denied by the privacy gate, never routed) still maps 403 to a generic
  `provider_rejected`; this difference is unreachable for resume data.

Regression tests: `backend/tests/test_ai_cloudflare.py` —
`test_documented_missing_permission_401_is_an_auth_failure`,
`test_forbidden_is_permission_not_authentication`, `test_documented_403_entitlement_codes`,
`test_account_blocked_403_is_permission`, `test_unknown_403_is_permission_without_guessing`,
`test_403_non_json_body_is_permission_and_does_not_leak`, `test_one_http_request_per_analyze`.

No B2 behaviour was modified to produce this note; it records the M1-A change that B3 already made.

## 15. Final end-to-end validation (2026-11-24)

One synthetic analysis job through the existing HTTP API, on the restarted backend (PID 1388, started
23:38 local, after the token was replaced). No code, config, schema or dependency change.

### 15.1 Preconditions

| Check | Result |
|---|---|
| `/health` | `200 {"status":"ok"}` |
| `/ready` | `200`, MySQL `careeros` reachable |
| Selected provider / model | `cloudflare` / `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| Chain / allowlist | `['cloudflare']` / `['cloudflare']` |
| Free-only / training | `True` / `False` |
| Privacy gate denials | `[]` |
| Pre-test residue | 0 canary versions, 0 synthetic resume names, 0 canary jobs |
| Pre-test counts | owners 1, companies 2, resumes 2, versions 2, files 2, JDs 1, jobs 4, results 1, applications 3, sessions 42 |

### 15.2 Workflow and outcome

Existing endpoints only: `POST /resumes` → `POST /companies` → `POST /job-descriptions` →
`POST /analyses` (201) → `GET /analyses/{id}` until terminal.

| Item | Value |
|---|---|
| Job status | **succeeded** |
| Provider / model | `cloudflare` / `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| Attempts | **1** (no retry needed; no repair prompt) |
| Prompt version | `analysis-v1` |
| Score | 80 |
| Findings | 5 (kinds: resume_evidence, jd_requirement, inferred_recommendation; 4 carry evidence) |
| schema_version | 1.0 |
| summary / alignment | populated (326 / 358 chars) |
| Job duration | started 18:10:24.53Z, finished 18:10:52.57Z (~28 s; 30.8 s end-to-end incl. polling) |
| Error fields | `None` |
| Gemini / paid fallback | none; only Cloudflare attributed |

### 15.3 Validation results

| Requirement | Result | Evidence |
|---|---|---|
| Cloudflare returns a usable response | **PASS** | `result.response` parsed into a validated object |
| JSON parsing | **PASS** | `validate_or_repair` accepted the first response; no repair attempt |
| Shared validation/repair helper | **PASS** | `max_repairs=0` path, no error |
| Pydantic validation | **PASS** | stored fields re-validated with `AnalysisOutput.model_validate` |
| Required fields populated | **PASS** | score, summary, alignment, ≥1 finding, schema version |
| Persisted and retrievable | **PASS** | `GET /analyses/{id}` returned the result; DB rows confirmed |
| Exactly one provider attempt | **PASS** | `attempts=1` |
| No Gemini / paid provider | **PASS** | provider `cloudflare`, chain `['cloudflare']` |

### 15.4 Records created (retained for review)

| Record | Identifier |
|---|---|
| Resume | `81aecb98-b1ff-41ff-b803-7b001b9b4a37` — "B2 Final Synthetic Resume" |
| Resume version | `7e480059-6eee-4c90-90d9-3f6dbba54348` — label `b2-final`, 675 chars |
| File object | `0f0547d3-2622-4780-b176-7f9aed2cb51d` — `b2-final-synthetic.txt`, 676 bytes |
| Stored blob | `storage/resume/ec4f8801c3691811e5f6f2485d878778.txt` |
| Company | `d03183d7-884c-4231-b720-e5555e6b15dc` — "B2 Final Synthetic Co" |
| Job description | `e77a918c-7662-4d4c-94ab-7e1436e048c1` — "B2 Final Synthetic Backend Engineer", 576 chars |
| Analysis job | `b8a3f4ff-7bc3-4411-869c-429fe38ed811` |
| Analysis result | `e6c137fe-d191-4893-814f-db3726b94bc7` |
| Auth session (test) | `e98db182-f6a9-41e3-b703-05641dd04bd9` — user agent `b2-final-e2e` |
| Audit rows | `analysis.create`, `analysis.succeed` |

Post-test counts: owners 1, companies 3, resumes 3, versions 3, files 3, JDs 2, jobs 5, results 2,
applications 3, sessions 44, audit logs 52. Deltas: +1 company, resume, version, file, JD, job, result;
+2 sessions (one test session plus one browser sign-in by the operator after the restart). Nothing was
deleted.

### 15.5 Security review

| Check | Result | Basis |
|---|---|---|
| Token / Authorization header in logs | **PASS (structural)** | adapter never logs headers; allowlist formatter; token absent from API responses and job rows |
| Synthetic resume content in logs | **PASS (structural)** | adapter and service log only counts/codes; job `error_message` is `None` |
| Account id in `httpx` logs | **PASS (structural)** | `httpx` pinned to WARNING in `configure_logging`; regression test |
| Provider response body in logs | **PASS (structural)** | body stored only in `analysis_result.raw_response`; never logged or returned |
| Unexpected external calls | **PASS (observed)** | one attempt, one provider, no Gemini; no other HTTP client in the path |

**Limitation:** the backend was started by the operator in their own terminal with no file handler
(`StreamHandler(sys.stdout)` only), so this run's raw stdout lines were not captured. The security
checks above are configuration- and test-based, not a log-line inspection. No credential, canary or
account id appears in the API responses, job rows, result rows, or this report.

### 15.6 Remaining risks

- One synthetic case only; varied resumes, long inputs, and adversarial prompts are unverified.
- Runtime log inspection remains a manual step for whoever owns the terminal.
- The synthetic records above are intentionally retained; cleanup needs approval.
- The backend was left running because the operator started it; it was not stopped by this session.
