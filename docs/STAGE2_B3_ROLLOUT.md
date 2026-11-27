# Stage 2 — B3 Rollout and Rollback

Operational procedure for releasing the B3 provider layer (health, breaker, quota, router,
observability) and for returning to the previous behaviour. Written from the code and tests in this
repository; no production deployment has been performed.

**Scope:** backend only. No schema change, no dependency change, no frontend change, no credential
rotation.

---

## 1. Pre-rollout checklist

### 1.1 Mandatory

| # | Check | How | Pass condition |
|---|---|---|---|
| 1 | Branch and review | `git status`, `git log -1` | Expected branch; only reviewed B3 files changed; nothing unrelated staged |
| 2 | Test suite | `cd backend` then `.\.venv\Scripts\python.exe -m pytest` | Full suite green (350 at B3 completion) |
| 3 | Lint | `.\.venv\Scripts\python.exe -m ruff check app tests alembic` | `All checks passed!` |
| 4 | Privacy settings | Inspect the deployed environment (not a committed file) | `AI_APPROVED_PROVIDERS=cloudflare`, `AI_FREE_ONLY=true`, `AI_ALLOW_TRAINING_PROVIDERS=false` |
| 5 | Provider chain | Same | `AI_PROVIDER_ORDER=cloudflare`; no unapproved provider listed |
| 6 | Credentials present | Confirm `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are set **without printing them** | Both non-empty; token has Workers AI permission (verified out of band) |
| 7 | Model | `CLOUDFLARE_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Matches the registry row; no unverified model |
| 8 | Fallback | `AI_ALLOW_CROSS_PROVIDER_FALLBACK` | `false` (the code never enables fallback regardless) |
| 9 | Routing flag | `AI_ROUTING_ENABLED` | `true` for B3; `false` only for rollback |
| 10 | Breaker | `AI_BREAKER_ENABLED`, `AI_BREAKER_FAILURES`, cooldowns | Intended values; defaults are `true`, `3`, `120`, `900`, `2.0` |
| 11 | Quota | `AI_QUOTA_ENABLED` | `true`; no fabricated remaining counts |
| 12 | Retry | `AI_MAX_ATTEMPTS`, `AI_RETRY_BASE_DELAY_SECONDS`, `AI_RETRY_MAX_DELAY_SECONDS` | `2`, `1.0`, `10.0` for B2-equivalent retry behaviour |
| 13 | Database | `GET /ready` after deploy, plus `assert_mysql_8()` at startup | MySQL 8; `ready` |
| 14 | Logging | `LOG_LEVEL=INFO`, `CAREEROS_ENV=production` | JSON formatter active; `httpx` remains at WARNING |
| 15 | No live call in CI | Test logs / network | No provider request made during tests |

### 1.2 Optional operational checks

- Snapshot current breaker/quota state expectations (both are in-memory and reset on restart).
- Confirm log collection is receiving stdout JSON and that `dropped_fields` is absent in normal
  records.
- Confirm an on-call owner for the rollback decision.

Do **not** rotate credentials, change provider approvals or edit privacy fields as part of rollout.

---

## 2. Deployment sequence

### 2.1 Configuration preparation (mandatory)

1. Set the values in §1.1 in the deployment environment. Keep credentials in the secret store, never
   in the repository.
2. Keep `AI_ALLOW_CROSS_PROVIDER_FALLBACK=false`.
3. Do not add a provider to `AI_APPROVED_PROVIDERS` or `AI_PROVIDER_ORDER`; only Cloudflare is
   approved.

### 2.2 Application deployment (mandatory)

1. Deploy the B3 backend artifact using the normal process.
2. No database migration is required. Do not run one for B3.
3. No dependency installation change is required beyond the existing lockfile.

### 2.3 Startup verification (mandatory)

1. `GET /health` returns `200` with `{"status": "ok", ...}`.
2. `GET /ready` returns `200` with `"status": "ready"` and MySQL reported healthy.
3. The startup log contains `careeros started` with `mysql`, `env`, `recovered_analyses`.
4. No startup traceback; no privacy self-check exists (deferred), so credential readiness is proven
   by §2.5 rather than at boot.

### 2.4 Provider initialization (mandatory)

1. Confirm `registry.get_provider()` selects Cloudflare by running one controlled analysis (owner
   account, synthetic or owner-approved text). This is the only supported initialization check;
   there is no startup provider probe.
2. Confirm the job row records `provider=cloudflare` and the configured model.
3. If the job fails `ai_not_configured`, credentials are missing; if it fails
   `provider_privacy_denied`, approval settings are wrong. Fix configuration, do not bypass the gate.

### 2.5 Health and quota checks (optional at rollout, mandatory before declaring success)

1. After a successful job, the health store records a success (in-memory; visible through the next
   attempt's log fields, not through an endpoint).
2. Confirm no `quota_exhausted` skip appears in normal traffic.
3. Do not force a breaker or quota failure in production. Their behaviour is proven by mocked tests.

### 2.6 Routing verification (mandatory)

1. `AI_ROUTING_ENABLED=true` and the analysis succeeds.
2. The `route selected` INFO record names `provider`, `model`, `priority`, `health`, `quota`.
3. No second provider is contacted on failure (single-provider chain today; fallback is disabled).

### 2.7 Observability verification (mandatory)

1. Logs are JSON lines with `request_id` and allowlisted fields.
2. A successful analysis emits `route selected`, one `provider attempt` (success), and
   `analysis succeeded`.
3. No resume text, token, account id or provider body appears in logs or API responses.
4. At `INFO`, skip records are absent (they are DEBUG by design).

---

## 3. Post-rollout verification

Run these checks in order. Each is measurable; record the observed value.

| # | Check | Expected |
|---|---|---|
| 1 | `GET /health` | `200`, `status=ok` |
| 2 | `GET /ready` | `200`, `status=ready`, MySQL ok |
| 3 | Existing analysis | `POST /api/v1/analyses` returns `201`; polling ends `succeeded`; `attempts=1`; one result row |
| 4 | Attribution | Job `provider=cloudflare`, model equals `CLOUDFLARE_MODEL` |
| 5 | Provider selection | `route selected` log has `priority=0`, `health=healthy`, `quota=available|unknown` |
| 6 | Privacy denial | In staging only: configure Gemini-only, submit, expect `provider_privacy_denied`, empty provider/model, zero HTTP calls. Never change production approvals for this test |
| 7 | Quota enforcement | Mocked test only (`test_ai_quota.py`, `test_ai_router.py`); no production exhaustion test |
| 8 | Breaker enforcement | Mocked test only (`test_ai_breaker.py`, `test_ai_router.py`); no production trip |
| 9 | Retry | Mocked test only (`test_ai_b3_baseline.py`: 5xx retries once, `attempts=1`, two HTTP calls) |
| 10 | Failure handling | Typed `error_code` stored; message is fixed text; no provider body |
| 11 | Structured logs | One `provider attempt` per attempt; one terminal `analysis succeeded`/`analysis failed` |
| 12 | Redaction | Canary strings absent from `caplog`, `str(exc)`, API response and `job.error_message` |
| 13 | API compatibility | Existing endpoints, status codes and response shape unchanged; historical job rows readable |
| 14 | Routing-off parity | Staging: `AI_ROUTING_ENABLED=false` → M3 path; run `test_routing_disabled_reproduces_m3_admission` |

**NOT PERFORMED:** no production deployment, no live provider request, no production breaker/quota
exercise. Only the local test suite and mocked transports were executed.

---

## 4. Rollback procedure

### 4.1 Triggers

Roll back if any of these is observed after release:

- Resume content reaches a provider that is not on the approved list, or any cross-provider call
  occurs.
- The privacy gate admits a provider with unknown retention/training/privacy evidence.
- A sensitive string (resume text, token, account id, provider body) appears in logs, errors or API
  responses.
- Startup fails, or `/ready` stays unavailable.
- A sustained rise in `provider_auth_failed`, `provider_permission_denied`,
  `provider_entitlement_denied`, `ai_unavailable` or `provider_quota_exhausted` caused by B3.
- The breaker or quota blocks normal traffic unexpectedly and cannot be explained from logs.

### 4.2 Immediate mitigation (no code change)

Set `AI_ROUTING_ENABLED=false` and restart the backend.

- This takes the M3 path: `select_provider()` (privacy-only) still chooses the provider,
  `retry.py` owns admission, and retry/quota/breaker behaviour remains as configured.
- Privacy is still enforced; the gate is not disabled by this flag.

For closer B2 parity, also set:

```
AI_ROUTING_ENABLED=false
AI_BREAKER_ENABLED=false
AI_QUOTA_ENABLED=false
AI_MAX_ATTEMPTS=2
```

- `AI_BREAKER_ENABLED=false` and `AI_QUOTA_ENABLED=false` make admission a no-op while evidence is
  still recorded.
- `AI_MAX_ATTEMPTS=2` preserves B2's effective one retry (the adapter no longer retries internally).
  `AI_MAX_ATTEMPTS=1` is **not** B2 parity.
- Do not change `AI_APPROVED_PROVIDERS`, `AI_FREE_ONLY` or `AI_ALLOW_TRAINING_PROVIDERS` during a
  rollback.

### 4.3 Restore the previous application version

1. Redeploy the last known-good B2 artifact (or the last good commit).
2. No database migration to reverse: B3 added no schema change.
3. No data repair: job rows written by B3 use the existing columns and valid error codes.
4. Keep credentials and approval settings unchanged.

### 4.4 Configuration restoration

After the previous version is running, remove or reset only the B3 flags that the old version does
not read. Leave the privacy/approval/free-only settings exactly as they were.

### 4.5 Service recovery verification

1. `/health` and `/ready` return success.
2. `careeros started` appears once per process start.
3. Submit one controlled analysis and confirm `succeeded`, correct attribution and one result row.
4. Confirm no unexpected provider call in network logs.

### 4.6 Log and error inspection

1. Search for `provider attempt`, `route selected`, `route candidate skipped`, `analysis failed`.
2. Confirm no `dropped_fields` spike (would indicate a field the formatter is discarding).
3. Confirm no canary or credential material appears.
4. Inspect the failed job's `error_code` and `error_message`; both must be fixed/typed.

### 4.7 Post-rollback regression checks

Run the backend suite on the restored artifact:

```
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests alembic
```

At minimum confirm `test_ai_b3_baseline.py`, `test_ai_router.py`, `test_ai_privacy.py`,
`test_ai_quota.py`, `test_ai_breaker.py`, `test_ai_retry.py` and `test_logging.py` are green.

### 4.8 Rollback limitations

- In-memory breaker/quota state is lost on restart; that is safe (optimistic, never spend) but the
  first post-restart attempt is not protected by prior observations.
- `AI_ROUTING_ENABLED=false` alone reproduces M3, not B2; use the four-flag set in §4.2 for B2 parity.
- Cross-provider fallback was never enabled, so rollback does not need to undo fallback state.
- If the previous artifact predates the M1-A 403 correction, 403s will again be reported as
  `provider_auth_failed`. Historical rows remain valid either way.
- No rollback can recover a resume already sent to an approved provider; the privacy gate is the only
  control and it remains active throughout.
