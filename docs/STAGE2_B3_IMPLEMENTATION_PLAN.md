# Stage 2 — B3 Implementation Plan

**Status:** B3 complete (M0–M6). Implemented, tested and documented. The final state is recorded in
`docs/STAGE2_B3_FINAL_REPORT.md`; rollout and rollback are in `docs/STAGE2_B3_ROLLOUT.md`.

**Hard constraints for every milestone:** no new provider, no model change, no privacy-rule change,
no paid fallback, no new dependency, no schema change, no live provider request in tests, no commit
until approved.

---

## 1. Baseline and guardrails

Before any milestone:

- Capture the B2 baseline: `pytest` (143 tests), `ruff check app tests alembic`, current `.env` AI
  flags, and the retained B2 synthetic rows. Do not touch those rows.
- Add a characterization test that pins current routing: Cloudflare configured + approved → selected;
  Gemini-only → `ProviderPrivacyDenied`; no credentials → `None`. This is the safety net for M4.
- Confirm `AI_BREAKER_ENABLED=false` reproduces B2 exactly; that is the rollback switch.

**Definition of done for B3 overall:** all existing tests pass unchanged (except the documented 403
test), new tests pass with no network, `ruff` clean, `AI_BREAKER_ENABLED=false` behaves like B2, and
the privacy gate remains the first filter in every code path.

---

## 2. Milestone map

```
M0 characterization
   │
M1 error taxonomy + 403 ─────────┐
   │                             │
M2 health + breaker ──┐          │
   │                  ├── M4 router attempt loop ── M5 observability ── M6 docs/rollout
M3 quota ─────────────┘          │
                                 └── M7 deferred multi-worker persistence (not B3)
```

- M2 and M3 are independent and can be reviewed in either order.
- M2-A, M2-B, M3, M4, M5 and M6 are implemented; B3 is complete. M7 remains out of scope.
- M4 depends on M1, M2, M3.
- M5 depends on M4.
- M7 is explicitly **not** part of B3; listed so the design does not dead-end.

---

## 3. M0 — Baseline and characterization

**Goal:** prove the current behaviour before changing it.

**Status: complete (2026-11-25).**

### 3.1 Baseline captured

| Item | Result |
|---|---|
| Pre-M0 suite | 143 tests passed |
| Post-M0 suite | **151 passed in 274.53 s** |
| Ruff | `ruff check app tests alembic` → **All checks passed** |
| Approved provider | `cloudflare` only; chain `['cloudflare']` |
| Approved model | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (24k context, account scope) |
| Free-only / training | `true` / `false` |
| Denied rows | Gemini, Groq 120B/20B, Cloudflare 8B (`context_unknown`) |
| Adapter retry | Cloudflare retries 5xx once (2 HTTP requests), 401/403/429 once (1 request) |
| Job attempt count | `attempts=1` per `run()`, independent of adapter HTTP retries |
| Success attribution | `provider=cloudflare`, `model=<70B>`, one `AnalysisResult` row |
| Failure persistence | job `failed` + typed code, **no** `AnalysisResult` row |
| No provider | `ai_not_configured`, no HTTP client constructed |
| Gate denial | `provider_privacy_denied`, no HTTP client constructed |
| Invalid JSON | `invalid_output`, one request, no repair prompt |

### 3.2 Tests added

`backend/tests/test_ai_b3_baseline.py` (8 tests, all offline):

| Test | Pins |
|---|---|
| `test_only_cloudflare_is_approved_and_free` | single approved free provider; every other row denied; 8B `context_unknown`; no paid provider in `PROVIDERS` |
| `test_privacy_denied_provider_is_never_called` | Gemini configured + allowlisted + training allowed is still denied; no HTTP; job `provider_privacy_denied` |
| `test_no_eligible_provider_fails_without_http` | no credentials → `ai_not_configured`; no client constructed |
| `test_success_persists_result_and_attribution` | actual provider/model, `attempts=1`, one result row, stored findings, `raw_response` not returned |
| `test_auth_failure_persists_no_result` | 401 → `provider_auth_failed`, one request, no result row, token absent |
| `test_server_error_retries_once_but_counts_one_attempt` | 503 → 2 HTTP requests, `attempts=1`, `provider_unavailable`, no result row |
| `test_rate_limit_is_one_request_and_no_retry` | 429 → 1 request, `attempts=1`, `provider_rate_limited` |
| `test_invalid_json_fails_without_repair` | malformed JSON → `invalid_output`, 1 request, no result row |

Existing suites already pin selection (`test_ai_router`), the adapter contract
(`test_ai_cloudflare`), the gate (`test_ai_privacy`) and the API flow (`test_ai_integration`,
`test_analysis`); the new module covers the cross-layer contract and the gaps.

### 3.3 Discrepancies found (B2 code vs B3 docs)

1. **Transient failure code.** B2 `analysis.run()` stores the exception's code, so a 5xx/timeout
   surfaces `provider_unavailable` / `provider_timeout`. The B3 target table (§9.5) aggregates
   "all candidates transiently failed" to `ai_unavailable`. The aggregate is new behaviour for M4;
   B2 is unchanged and the baseline pins `provider_unavailable`.
2. **No-candidate shorthand.** B3 §5 writes `ai_unavailable / privacy_denied`; the as-built codes are
   `ai_not_configured` (no credentials) and `provider_privacy_denied` (gate refusal). Both pinned.
3. **Retry ownership.** B3 §2.3 already flags this; the baseline confirms it: one job attempt can be
   two HTTP requests because the adapter retries 5xx. M1 centralized retries; M4 moved admission into
   the router, leaving retry timing in `retry.py`.
4. **Global no-network guard.** `STAGE2_B3_TEST_STRATEGY.md` §2.3 proposes a session-scoped guard.
   M0 uses per-test client patches and `MockTransport`; the global guard is deferred to M1.
5. **`test_ai_cloudflare` 401/403 pair.** The current test deliberately treats both as
   `ProviderAuthFailed`; that is the B2 baseline and the 403 remap remains an M1 approval item.

### 3.4 Acceptance

- [x] New tests pass against unmodified code.
- [x] Full suite green (151).
- [x] Ruff clean.
- [x] No production code, config, schema, dependency or provider change.
- [x] No live request; no B2 synthetic row touched.

**Risk:** Low. The only coupling is importing helpers from `tests.test_ai_integration`; if that module
is renamed, the baseline module must be updated.


---

## 4. M1 — Error taxonomy and the 403 correction

**Goal:** make failure classes express what actually happened, without changing success paths.

**Status: M1-A and M1-B complete (2026-11-25).**

### M1-A implemented

- `backend/app/ai/base.py` — additive subclasses:
  - `ProviderPermissionDenied(ProviderError)` → `provider_permission_denied`
  - `ProviderEntitlementDenied(ProviderPermissionDenied)` → `provider_entitlement_denied`
  - `ProviderQuotaExhausted(ProviderRateLimited)` → `provider_quota_exhausted` (reserved; not emitted)
  - `ProviderNetworkError(ProviderUnavailable)` → `provider_network_error`
  - `ProviderInvalidModel(ProviderError)` → `provider_invalid_model`
  - `ProviderUnsupportedCapability(ProviderError)` → `provider_unsupported_capability`
  - `ProviderJsonParseError(ProviderInvalidOutput)` → `invalid_json`
  - `ProviderSchemaError(ProviderInvalidOutput)` → `invalid_schema`
- `backend/app/ai/cloudflare.py` — `401 → auth`; `403 → permission` or `entitlement` from documented
  codes; `404 → invalid model`; transport → `ProviderNetworkError`; JSON parse → `ProviderJsonParseError`;
  unregistered/context-unknown → `ProviderUnsupportedCapability`. The internal 5xx retry is
  **unchanged** in M1-A.
- `backend/app/ai/repair.py` — parse failure and schema failure now raise their specific subclasses.
  The fixed message is unchanged, so no parser detail leaks.
- `backend/tests/test_ai_cloudflare.py`, `test_ai_providers.py`, `test_ai_b3_baseline.py` — updated and
  extended.

### Tests (all offline)

| Test | Asserts |
|---|---|
| 401 | `ProviderAuthFailed`, one request, fixed text |
| 403 unknown | `ProviderPermissionDenied`, not auth, one request |
| 403 documented `5035/5016/5018/3041` | `ProviderEntitlementDenied` |
| 403 `3023` / no code / non-JSON | `ProviderPermissionDenied` |
| 403 body leak | resume canary and token absent from `str(exc)` |
| 429 | `ProviderRateLimited` with `retry_after_seconds`, one request |
| timeout | `ProviderTimeout`, fixed text |
| network | `ProviderNetworkError`, fixed text, canary absent |
| 5xx | `ProviderUnavailable`, adapter retry unchanged in M1-A (2 requests); removed in M1-B |
| 404 | `ProviderInvalidModel` |
| malformed JSON | `ProviderJsonParseError` (`invalid_json`) |
| schema mismatch | `ProviderSchemaError` (`invalid_schema`) |
| unregistered model | `ProviderUnsupportedCapability`, no HTTP |
| inheritance | `except ProviderInvalidOutput` / `ProviderRateLimited` still match |

### M1-A validation

- Ruff: `All checks passed`.
- Full suite: **162 passed** (151 baseline + 11 new/extended).
- No production retry, breaker, quota, routing or fallback change.
- No provider, model, allowlist, privacy, schema or dependency change.

### M1-B implemented

- `backend/app/ai/retry.py` (**new**) — the only retry owner.
  - `retry_delay_seconds()` classifies a typed error into a delay or `None`.
  - `analyze_with_retry()` reuses the same adapter instance, respects
    `AI_MAX_ATTEMPTS`, and accepts an injected `sleep` for deterministic tests.
  - Terminal: auth, permission/entitlement, privacy, invalid model, unsupported capability,
    blocked, invalid output (JSON/schema), quota exhaustion, other provider rejections.
  - Retryable: timeout, network, 5xx (exponential backoff, capped); 429 only when a
    `Retry-After` is present and within the cap.
- `backend/app/core/config.py` — additive settings:
  - `AI_MAX_ATTEMPTS` (default 2; B2’s effective one retry)
  - `AI_RETRY_BASE_DELAY_SECONDS` (default 1.0)
  - `AI_RETRY_MAX_DELAY_SECONDS` (default 10.0)
- `backend/app/services/analysis.py` — `run()` calls `analyze_with_retry()` instead of
  `provider.analyze()` directly. `job.attempts` is still incremented once per run.
- `backend/app/ai/cloudflare.py` — internal 5xx retry removed. One HTTP request per
  `analyze()`; 5xx raises `ProviderUnavailable` for the orchestration layer.
- `backend/app/ai/gemini.py` — 429/5xx retry removed and `MAX_REPAIRS` set to 0, so one HTTP
  request per `analyze()`. Gemini remains gate-denied and is never routed.

### Attempt accounting (M1-B)

| Layer | Meaning | Persisted? |
|---|---|---|
| HTTP request | One `httpx` send | No |
| Provider attempt | One `provider.analyze()` call | No |
| Analysis job attempt | One `analysis.run()` invocation (`job.attempts`) | Yes, unchanged |

For Cloudflare, one provider attempt equals one HTTP request. A retried job still has
`attempts=1` but can make two provider attempts. Persisting the provider-attempt count would
need a schema migration; it is deliberately deferred. The future-compatible proposal is a
separate nullable `provider_attempts` column populated in M4, leaving `attempts` as the run
counter.

### M1-B tests (all offline)

| Test | Asserts |
|---|---|
| transients | exponential backoff, cap, same provider reused |
| cap | stops at `AI_MAX_ATTEMPTS` |
| terminal classes | auth, permission, invalid output not retried |
| 429 short | exact `Retry-After` delay, then success |
| 429 long / missing | no retry |
| quota exhaustion | no retry |
| Cloudflare one-request | 400/401/403/404/429/500/503 each make exactly one call |
| job 5xx | two provider attempts, `attempts=1`, `provider_unavailable` |
| job timeout / network | two attempts, `attempts=1`, typed code |
| job 403 | one attempt, `provider_permission_denied` |
| job 429 short | two attempts, `attempts=1`, success |
| job 429 long | one attempt, `provider_rate_limited` |
| Gemini | no internal retry, no repair, one request on 429 |
| B2 regression | success/auth/privacy/JSON paths keep their codes and `attempts=1` |

### M1-B validation

- Ruff: `All checks passed`.
- Targeted suite (adapters, taxonomy, retry, baseline, integration, analysis): **93 passed**.
- Full suite: **193 passed in 247.52 s** (162 before M1-B; +31 new/parametrized).
- No breaker, health, quota, candidate loop, fallback, provider, model, allowlist, privacy,
  schema or dependency change.
- No live request; no B2 synthetic row touched.

### M1-B unresolved

- A `429` whose `Retry-After` exceeds `AI_RETRY_MAX_DELAY_SECONDS` is terminal. This is
  intentional (no unbounded wait) and leaves the job `provider_rate_limited`.
- `Retry-After` is parsed as numeric seconds only. An HTTP-date value is treated as absent,
  so the 429 is terminal rather than guessed.
- Cancellation is not checked between retries; the existing post-call `db.refresh` still
  prevents storing a result for a cancelled job. M4 does not add per-attempt cancellation checks.
- `ai/retry.py` owns retry timing and caps; M4 moved quota/breaker admission into `ai/router.py`.
- Gemini’s legacy status mapping is only partially aligned; it is not routed, so it cannot
  affect resume processing.

### Risks / mitigation

- **403 behaviour change.** Approved for M1-A; the body is never echoed and the fixed message does not
  reveal account state.
- **Retry ownership split.** Resolved in M1-B: adapters make one request and `ai/retry.py`
  owns the decision, budget and delay. The candidate attempt loop remains M4 work.

---

## 5. M2 — Health Manager and circuit breaker

**Goal:** stop hammering a dead provider; never affect privacy.

**Status: M2-A and M2-B complete (2026-11-25).**

### M2-A implemented — passive health manager

- `backend/app/ai/health.py` (**new**):
  - `HealthRecord` dataclass with success/failure counts, `quality_failures`, consecutive transient
    failures, last success/failure timestamps and class, latency EWMA + sample count, a 20-entry
    `recent_outcomes` ring, and the reserved breaker fields (`opened_at`, `cooldown_seconds`,
    `half_open_in_flight`).
  - `state` is a read-only property. Derivation order: `disabled` → `half_open` → `open` →
    `degraded` → `healthy`. M2-A never sets the breaker fields, so `open`/`half_open` are
    unreachable and nothing is filtered.
  - `HealthStore` protocol: `get`, `record_success`, `record_failure`, `disable`, `snapshot`,
    `reset`.
  - `InMemoryHealthStore`: one `threading.RLock` guards all reads and writes; `get`/`snapshot`
    return copies. Injected `clock` defaults to `time.monotonic`.
  - `classify_failure()`: transient (timeout, network, 5xx), auth, permission, quality (invalid
    JSON/schema). Rate limit, quota, invalid model, blocked, other provider errors and privacy
    denial do not affect health.
  - Model-level key `(provider, model)` and provider-level key `(provider, None)`. Transient and
    auth/permission failures update both; quality failures update the model only.
  - Module singleton `health_store` for the app.
- `backend/app/ai/retry.py` — `analyze_with_retry()` accepts optional `health` and `clock`.
  It records every intermediate failure and the terminal outcome, times only the provider call
  (retry sleep excluded), and treats recording as a best-effort side effect.
- `backend/app/services/analysis.py` — passes the singleton `health_store` into the retry call.
  `job.attempts`, retry policy, selection and privacy are unchanged.

### M2-A attempt/latency accounting

| Observation | Where recorded | Notes |
|---|---|---|
| provider attempt failure | `analyze_with_retry` except block | one per retryable or terminal failure |
| provider attempt success | `analyze_with_retry` success path | latency from the same clock |
| retry sleep | not recorded | outside the timed window |
| job attempt | `job.attempts` | unchanged; health never writes it |

### M2-A tests (all offline)

`backend/tests/test_ai_health.py` (26 tests): initial state; success at both levels; timeout,
network and 5xx degradation; auth/permission/entitlement disable; rate limit, quota, invalid model,
blocked, privacy and generic errors ignored; JSON/schema quality-only; EWMA; bounded recent
outcomes; consecutive-failure reset; all five state derivations; administrative vs failure disable;
concurrent updates; no private text stored; retry records each attempt and excludes sleep from
latency; job-level success and transient failure recording.

### M2-A validation

- Ruff: `All checks passed`.
- Health tests: **26 passed**.
- Targeted suite (health, retry, integration, baseline, analysis, cloudflare, providers):
  **119 passed**.
- Full suite: **219 passed in 290.68 s** (193 before M2-A; +26).
- No breaker, filtering, quota, routing, fallback, provider, model, privacy, retry-policy, schema or
  dependency change.

### M2-B implemented — circuit breaker

**Goal:** stop hammering a dead provider; never affect privacy.

- `backend/app/ai/base.py` — `ProviderCircuitOpen(ProviderError)` with code `circuit_open`.
  Raised by admission before any HTTP request.
- `backend/app/ai/health.py`:
  - `BreakerPolicy` (enabled, threshold, initial cooldown, max cooldown, multiplier) built from
    settings per call, so a config change needs no restart.
  - `admit()`: atomic. Rejects `disabled`, rejects `OPEN` before cooldown, admits exactly one
    `HALF_OPEN` probe, and is a no-op when the breaker is disabled.
  - `record_failure(..., policy=...)`: transient failures increment consecutive failures on model
    and provider; the provider-level record opens at the threshold. A failed half-open probe
    reopens with `min(cooldown × multiplier, cap)`. Auth/permission set `disabled`; rate limit,
    quota, invalid output, invalid model, blocked and generic errors do not open.
  - `record_success()`: closes the breaker, clears the probe slot and resets consecutive failures.
    It never clears `disabled_reason`.
  - `recover_credentials()`: explicit operator recovery for `auth`/`permission` only. A manual
    disable is untouched.
  - `abandon()`: releases a half-open slot after an unexpected exception.
- `backend/app/ai/retry.py` — builds the policy from settings and calls `health.admit()` before
  every provider invocation, including retries. Records the outcome of every attempt and releases
  the probe slot on a non-`ProviderError` exception. Retry limits, sleep timing and job attempts
  are unchanged.
- `backend/app/core/config.py` — `AI_BREAKER_ENABLED`, `AI_BREAKER_FAILURES`,
  `AI_BREAKER_COOLDOWN_SECONDS`, `AI_BREAKER_COOLDOWN_MAX_SECONDS`,
  `AI_BREAKER_BACKOFF_MULTIPLIER`.
- `backend/tests/conftest.py` — resets the process-local singleton before every test.

### M2-B state transitions

| From | Event | To | Effect |
|---|---|---|---|
| CLOSED | transient failure below threshold | CLOSED / degraded | consecutive +1 |
| CLOSED | transient failure at threshold | OPEN | `opened_at=now`, cooldown=120 |
| OPEN | admission before cooldown | OPEN | `ProviderCircuitOpen`, no HTTP |
| OPEN | admission after cooldown | HALF_OPEN | one probe slot taken |
| HALF_OPEN | second concurrent admission | HALF_OPEN | rejected |
| HALF_OPEN | success | CLOSED | counters and cooldown reset |
| HALF_OPEN | transient failure | OPEN | cooldown ×2, capped at 900 |
| HALF_OPEN | non-transient failure | CLOSED | provider answered; counters reset |
| any | auth/permission failure | DISABLED | no transient streak |
| any | manual `disable()` | DISABLED | not cleared by success |

Only the provider-level record owns the breaker. Model-level records keep counters and latency;
this avoids a second FSM and matches the single-provider deployment.

### M2-B accounting

- One `admit()` per provider attempt; a rejected attempt makes zero HTTP requests.
- A retry re-checks admission, so it cannot bypass an `OPEN` breaker.
- Circuit-open rejections are not recorded as provider failures or latency samples.
- `job.attempts` still increments once per `analysis.run()`.

### M2-B tests (all offline)

`backend/tests/test_ai_breaker.py` (26 tests): open at three failures; two failures stay degraded;
open rejects without a provider call; still open before cooldown; half-open after cooldown; exactly
one concurrent probe; probe success closes; probe failure reopens; exponential cooldown and cap;
auth/permission/entitlement do not count; rate limit/quota/quality do not open; network and timeout
are transient; non-transient probe failure does not reopen; manual disable survives success and
recovery; credential disable needs explicit recovery; disabled mode matches M2-A; retry stops at an
open breaker with the same attempt accounting; circuit-open is not recorded as a failure;
unexpected exception releases the probe slot; job-level `circuit_open` with no extra HTTP calls;
privacy denial precedes any admission.

### M2-B validation

- Ruff: `All checks passed`.
- Breaker + health tests: **52 passed**.
- Targeted suite (breaker, health, retry, integration, baseline, analysis, cloudflare,
  providers): **145 passed**.
- Full suite: **245 passed in 386.55 s** (219 before M2-B; +26).
- No quota manager, routing, fallback, provider, model, privacy, retry-policy, schema or dependency
  change.

### M2-B risks

- **Over-opening on a slow-but-working provider.** Threshold 3, cooldown 120 s; the flag turns it
  off. Latency is recorded but does not open the circuit.
- **Half-open slot leak.** Every outcome releases the slot; `abandon()` covers unexpected
  exceptions. No timeout guard is needed because the adapter has `AI_TIMEOUT_SECONDS`.
- **Backoff wait before a rejected retry.** If the threshold is reached exactly when a retry is
  scheduled, the loop sleeps the (bounded) backoff before admission rejects it. With defaults
  (`AI_MAX_ATTEMPTS=2`, threshold 3) this cannot happen inside one run.
- **Provider-level gate only.** Model-level records are observational; a model-specific outage
  still opens the provider breaker through the shared transient failures.
- **Disabled providers fail fast.** After the first 401/403, later jobs get `circuit_open` (with a
  disabled message) instead of repeating the auth call. This is intentional; recovery is explicit.
- **Process-local state.** A restart closes every breaker and clears credential disables.

---

## 6. M3 — Quota Lifecycle Manager

**Status: M3 complete (2026-11-25).**

**Goal:** consume documented quota signals; never invent a number; never spend money.

### M3 implemented

- `backend/app/ai/quota.py` (new): `QuotaObservation`, `QuotaBucket`, `QuotaPolicy`,
  `QuotaStore` protocol, `InMemoryQuotaStore`, `parse_cloudflare_quota_headers`,
  `next_utc_midnight`, process-local `quota_store`.
- `backend/app/ai/cloudflare.py`: records 2xx availability and 429 evidence as a side effect;
  error `3036` raises `ProviderQuotaExhausted`, `3040` stays `ProviderRateLimited`.
- `backend/app/ai/retry.py`: quota admission before every attempt and before breaker admission;
  every retry re-checks it.
- `backend/app/services/analysis.py`: passes the process-local store into `analyze_with_retry`.
- `backend/app/core/config.py`: `AI_QUOTA_ENABLED` (default `true`).
- `backend/tests/conftest.py`: resets the quota singleton between tests.
- `backend/tests/test_ai_quota.py` (new): 44 offline tests.

### M3 scope and evidence

Cloudflare is account-scoped. The only documented signals used are:

| Evidence | Source | Meaning |
|---|---|---|
| 429 + code `3036` | Workers AI errors page | daily free allocation exhausted; reset next 00:00 UTC |
| 429 + code `3040` | Workers AI errors page | temporary capacity, not exhaustion |
| numeric `Retry-After` | HTTP | bounded retry hint, owned by `retry.py` |
| 00:00 UTC daily reset | Workers AI pricing page | the only reset clock used |

No remaining-capacity or limit header is documented for Workers AI, so `remaining`, `limit` and
`unit` stay `None`. `Ratelimit` / `X-RateLimit-*` are ignored rather than misread. No account id,
token or response body is stored.

### M3 unknown quota

Unknown is `None`, never zero and never unlimited. It does not block admission. A model name never
implies account quota, and no reset time is invented. Four states are distinguished: known
available, known exhausted, temporarily rate-limited, unknown.

### M3 rate limit vs exhaustion

A generic 429 stays `ProviderRateLimited` and is retried only within the existing `Retry-After` cap.
`3036` becomes `ProviderQuotaExhausted`, which `retry_delay_seconds` never retries. Exhaustion
blocks admission until the documented reset passes; after the reset the bucket is `unknown` again,
not refilled. Exhaustion with no reset time stays blocked until a later authoritative observation.

### M3 admission and accounting

Order per attempt: privacy gate (earlier, in `registry.get_provider()`) → quota admission → breaker
admission → adapter HTTP. Quota runs before the breaker so a quota rejection cannot consume a
half-open probe. A quota rejection makes no HTTP request, adds no health failure or latency sample,
creates no result and leaves `job.attempts` unchanged. The job error code is
`provider_quota_exhausted`.

### M3 hardening patch — 3036 exhaustion protection

**Status: complete (2026-11-25). Narrow patch on M3; not M4.**

- `QuotaBucket` now records `exhausted_source`. `error_3036` is protected until its documented
  reset.
- `observe_success()` no longer clears active `3036` exhaustion. A 200 from a request that was
  already in flight is not evidence that the daily allocation reset.
- While `3036` is active, `observe()` ignores generic 429/`3040`, empty/malformed evidence and
  explicit `remaining > 0` observations. It cannot clear or shorten the window.
- `_expire()` runs before every write; reaching `exhausted_until` clears both `exhausted_until` and
  `exhausted_source` and returns the bucket to `unknown` without inventing capacity.
- Generic (non-`3036`) exhaustion still recovers on a success or an explicit available observation.
- All transitions remain under the existing `RLock`; no lock is held during HTTP or retry sleep.

Regression tests added to `backend/tests/test_ai_quota.py` (13 new cases, 56 total):

success cannot clear active 3036; success after reset returns to unknown; generic 429, 3040,
explicit available and empty observations cannot clear active 3036; both observation orders;
concurrent success and 3036; admission stays blocked after a success; success on an unknown bucket
still records evidence; adapter 200 cannot clear confirmed 3036. Existing success-recovery tests
were narrowed to generic exhaustion so their intent is preserved.

### M3 tests (all offline)

`backend/tests/test_ai_quota.py` (56 tests): unknown is `None`; known available/exhausted storage;
account scope shared across models; model scope separate; snapshot copies; concurrent updates; no
identifiers stored; invalid reset/negative values ignored; 3036 exhaustion; missing/malformed/
negative/date-form `Retry-After`; undocumented headers ignored; 3040 capacity; non-429 yields
nothing; `Retry-After` feeds the retry cap; contradictory exhaustion wins; rate limit is not
exhaustion; expired reset re-evaluates; unknown reset stays blocked; an already-elapsed reset does
not block; generic exhaustion recovers on availability/success; 3036 protection and order
independence; admission before HTTP; quota rejection adds no health failure or latency; every retry
re-checks quota; exhaustion is not retried; breaker still opens and still blocks; flag-off
reproduces M2-B; adapter records 3036/3040/success and cannot clear 3036 with a 200; malformed
headers do not break the request; no provider text leaks; job-level quota failure with zero HTTP
calls, `attempts=1` and no result; flag-off job success; privacy denial precedes quota admission.

### M3 validation

- Ruff: `All checks passed`.
- Quota tests: **56 passed**.
- Targeted suite (quota, breaker, health, retry, baseline, analysis integration, Cloudflare adapter,
  provider registry): **211 passed in 252.68 s**.
- Full suite: **301 passed in 459.20 s** (245 before M3; +56).
- No quota persistence, routing, fallback, provider/model/privacy change, retry-policy change,
  schema migration or new dependency.

### M3 risks

- **Restart resets quota to unknown.** Accepted: the worst case is one wasted attempt.
- **Multi-worker state is not shared.** Each process observes independently; M7 is out of scope.
- **No documented remaining-quota header.** Cloudflare buckets are `unknown` until a 429 or a
  success; no UI should show a fabricated number.
- **No neuron accounting.** The adapter does not estimate neuron usage, so `limit` stays unknown.
- **Provider-level gate only.** M4 moved admission into `ai/router.py`; model-level routing still
  needs a model-list setting.
- **3036 without a reset time blocks until restart.** Defensive only: the parser always supplies
  the documented daily reset.

---

## 7. M4 — Intelligent Router

**Status: M4 complete (2026-11-26).** Cross-provider fallback is **not** implemented.

**Goal:** one deterministic, explainable decision point that owns operational admission, while the
existing privacy gate remains the first and strictest filter.

### M4 implemented

- `backend/app/ai/router.py`: `Skip`, `Candidate`, `RouteDecision`, `estimate_request_tokens()`,
  `build_decision()`, `rank_candidates()`, `admit_candidate()`, `route_and_run()`,
  `no_eligible_error()`. `select_provider()` is unchanged.
- `backend/app/ai/health.py`: read-only `routing_status()` on the store. It reports
  `disabled` / `circuit_open` / `circuit_half_open` / `half_open` / `healthy` without claiming a
  half-open probe.
- `backend/app/ai/base.py`: `ProviderNoEligibleCandidate` (`ai_unavailable`) for a generic
  no-candidate result.
- `backend/app/ai/retry.py`: optional `admit` callable. When supplied, `retry.py` does not admit
  itself; the router is the single admission owner. Retry timing and caps are untouched.
- `backend/app/services/analysis.py`: `run()` calls `route_and_run()`; `submit()` is unchanged.
- `backend/app/core/config.py`: `AI_ROUTING_ENABLED` (default `true`),
  `AI_ALLOW_CROSS_PROVIDER_FALLBACK` (default `false`, not implemented).
- `backend/tests/test_ai_router.py`: 51 offline tests (8 pre-existing + 43 M4).

### M4 eligibility

`build_decision()` walks `AI_PROVIDER_ORDER`, resolves the configured model, and applies the existing
`denial_reasons()` gate before any operational check:

provider approval → data class → privacy evidence → retention → training → free tier → JSON →
context (`max(8_000, chars/4 + 512)`). Failures become `Skip(provider, model, reason)`; nothing is
silently dropped. Unregistered models and missing configuration are recorded as `unregistered` and
`unconfigured`.

### M4 operational filters

| Condition | Routable | Reason |
|---|---|---|
| Disabled provider | no (breaker enabled) | `disabled` |
| Open breaker, cooldown active | no | `circuit_open` |
| Open breaker, cooldown elapsed | yes, probe not claimed | — |
| Probe already in flight | no | `circuit_half_open` |
| Quota exhausted | no (quota enabled) | `quota_exhausted` |
| Quota rate-limited / unknown | yes | — |
| Degraded health | yes | — |

`AI_BREAKER_ENABLED=false` and `AI_QUOTA_ENABLED=false` make the corresponding filter permissive.

### M4 ranking

Priority (`AI_PROVIDER_ORDER` index) → health (`healthy` < `degraded` < `half_open`) → quota
(`available`/`unknown` < `rate_limited`) → provider name → model id. No cost, price or latency
estimate is invented. Repeated calls return identical decisions.

### M4 admission and retry

`route_and_run()` matches the selected provider to an eligible candidate, then passes
`admit=lambda: admit_candidate(...)` into `analyze_with_retry()`. Admission is quota first, breaker
second, immediately before each attempt. Quota rejection therefore cannot consume the half-open
probe; breaker rejection makes no HTTP request; every retry re-checks both. When routing is off, or
when an adapter outside the configured chain is injected, the M3 path is exact.

### M4 failure mapping

Privacy reasons → `provider_privacy_denied`; quota → `provider_quota_exhausted`; breaker/disabled →
`circuit_open`; capability/context → `provider_unsupported_capability`; anything else →
`ai_unavailable`. All are existing job error codes; no schema change.

### M4 fallback

`route_and_run()` attempts only the selected candidate. `AI_ALLOW_CROSS_PROVIDER_FALLBACK=true` does
not add candidates or attempts. Only Cloudflare is approved, so a Cloudflare failure returns the
existing typed error and no other processor is contacted.

### M4 tests (all offline)

`backend/tests/test_ai_router.py` (52 tests): approved candidate; unapproved Gemini/Groq/OpenRouter/
OpenAI; unknown privacy evidence; disallowed data class; training and retention violations; free-only;
JSON capability; insufficient context; oversized request; disabled provider; open breaker; half-open
does not consume a probe; quota exhaustion; unknown quota; degraded health; temporary rate limit;
disabled quota/breaker policies; priority; stable tie-break; no invented cost/latency fields;
deterministic decisions; quota-before-breaker admission; breaker rejection with zero HTTP; every retry
re-checks quota; no duplicate admission; retry cap unchanged; same provider reused; typed no-candidate
errors; unregistered model; quota failure with zero HTTP; selection log contains no content; privacy
denial before execution; fallback setting adds no candidates; failure does not invoke another
provider; routing disabled reproduces M3; job success creates exactly one result and `attempts=1`.

### M4 validation

- Ruff: `All checks passed`.
- Router tests: **52 passed**.
- Targeted suite (router, quota, breaker, health, retry, baseline, analysis, analytics, integration,
  Cloudflare adapter, providers): **255 passed in 428.92 s**.
- Full suite: **343 passed in 556.55 s** (301 before M4; +42).
- No fallback, provider approval, privacy policy, retry policy, quota semantics, breaker threshold,
  schema, dependency or frontend change.

### M4 risks

- **One model per provider.** Model-level routing needs a model-list setting and the 8B context
  verification; out of scope.
- **Submit vs run attribution can differ.** `submit()` keeps privacy-only attribution; `run()` uses
  current health/quota. With one provider the executor is the same.
- **Injected adapters bypass the decision.** Only tests/plugins pass a provider outside the chain;
  production selection cannot.
- **Ranking is only exercised with one approved provider today.** The ordering is deterministic and
  tested with synthetic candidates, but multi-provider production behaviour awaits future approvals.

---

## 8. M5 — Observability (implemented)

**Goal:** every routing decision is explainable from logs without content.

### Implemented

- `router.build_decision()` emits one DEBUG `route candidate skipped` record per `Skip`, with
  `provider`, `model`, `reason`. `route_and_run()` keeps the INFO `route selected` record with
  `priority`, `health`, `quota`.
- `retry.analyze_with_retry()` emits one `provider attempt` record per attempt: INFO on success,
  WARNING on failure, with `provider`, `model`, `attempt`, `latency_ms`, `status`, and on failure
  `code`, `failure_class`, and `delay_seconds` when another attempt is scheduled.
- The existing `analysis succeeded` / `analysis failed` records remain the single terminal record
  per job (`job_id`, `provider`, `score` or `code`).
- `ALLOWED_LOG_FIELDS` gained `priority`, `health`, `quota`, `failure_class`, `delay_seconds`.
  M4 already emitted the first three; they were silently dropped by the formatter. No sensitive
  name was added.
- `state` was not added: no record emits it. Breaker state is visible through skip reasons and
  attempt outcomes, so a separate transition record would duplicate the attempt record.

### Log volume

One record per skip + one per attempt + one terminal. Skips are DEBUG, so an INFO log shows only
attempts and the terminal; a long chain costs at most one DEBUG line per skipped model.

### M5 tests (all offline)

- `tests/test_logging.py` (7 tests): allowlist additions; sensitive names absent; routing/attempt
  metadata not dropped; existing canary, exception and `httpx` tests.
- `tests/test_ai_router.py` (57 tests): one DEBUG skip record per skip, none at INFO; exactly one
  attempt record per call with attempt/status/code/failure_class/latency; request and provider-body
  canaries absent from attempt records; one terminal record at job level with no body content.

### M5 validation

- Ruff: **All checks passed!**
- `test_logging.py` + `test_ai_router.py`: **64 passed**.
- Targeted suite: **267 passed in 389.48 s**.
- Full suite: **350 passed in 526.60 s** (343 before M5; +7).

### M5 risks

- Log volume grows linearly with chain length; bounded by DEBUG and by the configured chain.
- Structured records are only as good as the allowlist; a new field must be added deliberately.

---

## 9. M6 — Documentation, rollout and rollback (implemented)

**Goal:** ship with a switch and a paper trail.

### Implemented

- `docs/STAGE2_B3_FINAL_REPORT.md` — complete B3 as-built report (architecture, privacy, routing,
  health/quota, retry ownership, observability, B2 compatibility, config, tests, limitations).
- `docs/STAGE2_B3_ROLLOUT.md` — pre-rollout checklist, deployment sequence, measurable post-rollout
  checks, rollback procedure and rollback limitations.
- `docs/STAGE2_AI_ARCHITECTURE.md` — §9 (health/breaker), §11 (quota), §14 (router flow) and §15
  (phases and status) updated to the B3 as-built; header and §16 pointer corrected.
- `docs/STAGE2_B2_IMPLEMENTATION_REPORT.md` — §14.8 records the B3 403 compatibility note (the plan
  referred to "§14.11"; that subsection does not exist, so the note was added as §14.8).
- `docs/STAGE2_B3_TEST_STRATEGY.md` — M6 gate marked implemented; final counts recorded.

### Rollout verification

- No live provider call was made; all checks are local or mocked.
- The pre-rollout, deployment and post-rollout checks are documented with pass conditions.
- Production-only checks are explicitly marked **NOT PERFORMED**.

### Rollback verification

- `AI_ROUTING_ENABLED=false` reproduces the M3 single-provider path; pinned by
  `test_routing_disabled_reproduces_m3_admission`.
- B2-equivalent behaviour requires `AI_ROUTING_ENABLED=false`, `AI_BREAKER_ENABLED=false`,
  `AI_QUOTA_ENABLED=false` and `AI_MAX_ATTEMPTS=2`. The original plan's claim that
  `AI_BREAKER_ENABLED=false` alone restores B2 became stale when M3/M4 added quota and routing;
  the plan's `AI_MAX_ATTEMPTS=1` would also be one retry short of B2. The rollout doc states the
  verified four-flag set.
- No schema, dependency or credential change to reverse.

### M6 validation

- Ruff: **All checks passed!**
- Configuration validation: parsed defaults confirm `chain=['cloudflare']`,
  `approved=['cloudflare']`, free-only, no training, `max_attempts=2`, breaker/quota/routing on,
  fallback off, 70B model.
- B3 targeted suite (including privacy): **282 passed in 437.77 s**.
- Full suite: **350 passed in 509.75 s (0:08:29)**.

### Discrepancies recorded

- The plan's M6 section labels §9/§11/§14/§15 as "implementation phases / files / decisions /
  risks", but those headings actually belong to §9 health, §11 quota, §14 router flow and §15
  phases. The sections were updated by number, matching the plan's own instruction to "mark
  implemented".
- The plan references `STAGE2_B2_IMPLEMENTATION_REPORT.md` §14.11; the file has no §14.11. The note
  is in §14.8, with a cross-reference from §14.4 item 4.

### Risk

- Documentation drift is the main risk. The final report records the exact test count and the
  production-only checks that remain unverified.

---

## 10. M7 — Deferred: multi-worker persistence (not B3)

Documented only. When the app runs more than one worker:

- `RedisHealthStore` / `RedisQuotaStore` with `INCR`+`EXPIRE`, Lua CAS for the half-open token; or
- a MySQL `ai_provider_state` table with `SELECT ... FOR UPDATE`.

This requires a schema/infrastructure decision and is out of scope. The `HealthStore`/`QuotaStore`
protocols exist so this is a local change.

---

## 11. File-change summary

| File | M0 | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|---|
| `app/ai/base.py` | | ✎ | | | ✎ | |
| `app/ai/cloudflare.py` | | ✎ | | ✎ | | |
| `app/ai/gemini.py` | | ✎ | | | | |
| `app/ai/health.py` | | | **new** | | ✎ | |
| `app/ai/quota.py` | | | | **new** | | |
| `app/ai/retry.py` | | ✎ | | ✎ | ✎ | ✎ |
| `app/ai/router.py` | | | ✎ | ✎ | ✎ | ✎ |
| `app/ai/providers.py` | | | | | ✎ | |
| `app/ai/registry.py` | | | | | ✎ | |
| `app/services/analysis.py` | | | | ✎ | ✎ | |
| `app/core/config.py` | | | ✎ | ✎ | ✎ | |
| `app/core/logging.py` | | | | | | ✎ |
| `tests/test_ai_*.py` | ✎ | ✎ | ✎ | ✎ | ✎ | ✎ |

No `alembic/` change. No `requirements` change. No frontend change.

M6 is documentation-only: it adds `docs/STAGE2_B3_FINAL_REPORT.md` and
`docs/STAGE2_B3_ROLLOUT.md`, and updates `docs/STAGE2_AI_ARCHITECTURE.md`,
`docs/STAGE2_B2_IMPLEMENTATION_REPORT.md` and `docs/STAGE2_B3_TEST_STRATEGY.md`. No application or
test file changed.

---

## 12. Risks and mitigations (program level)

| Risk | Impact | Mitigation |
|---|---|---|
| Breaker opens on a healthy provider | user sees `ai_unavailable` | conservative threshold, flag, half-open probe, no latency-based opening |
| Fallback sends data to a new processor | privacy breach | default off; same gate per destination; notice required |
| 403 remap hides a real bad key | wrong operator action | 401 stays auth; 403 permission with fixed text; both disable |
| Quota guess causes premature skip | avoidable failure | unknown stays unknown; only authoritative signals skip |
| Adapter retry double-counts | attempt cap meaningless | one retry owner (router); M1 removes adapter retries |
| In-memory state lost on restart | one wasted attempt | accepted; no data loss; gate is stateless |
| `input_hash` mismatch after fallback | confusing dedupe | hash stable; documented limitation |
| Log noise / leak | ops + privacy | allowlist only; canary tests; no content fields |
| Scope creep into B4 providers | privacy regression | B3 adds no provider/model/allowlist entry |

---

## 13. Acceptance checklist (B3 done)

- [ ] Privacy gate is the first filter in `build_decision`; test proves a healthy denied provider is never called.
- [ ] `AI_BREAKER_ENABLED=false` reproduces B2 (selection, one call, same error codes).
- [ ] Breaker FSM: CLOSED/OPEN/HALF_OPEN, single probe, backoff cap, no quota/auth/quality opening.
- [ ] Quota: `Retry-After` consumed; unknown stays `None`; account scope shared; no billing path.
- [ ] Router: deterministic order, skip reasons, attempt cap, actual attribution, cancelled check.
- [ ] Observability: one record per skip/attempt/terminal; canaries absent from logs, errors and job rows.
- [ ] Fallback: default off; each destination gated; blocked/auth/permission never loop.
- [ ] 403 is permission, not auth; existing codes unchanged.
- [ ] All existing tests pass (except the documented 403 expectation); new tests are network-free.
- [ ] `ruff check app tests alembic` clean.
- [ ] No schema, dependency, `.env` or provider-allowlist change.
- [ ] B2 synthetic rows untouched.
- [ ] Docs updated; no commit/push without approval.
