# Stage 2 — B3 Test Strategy

**Status:** M0, M1-A, M1-B, M2-A, M2-B, M3 (including the 3036 hardening patch), M4, M5 and M6 are
implemented; B3 is complete. Every test below is offline. The B2 suite (143 tests before M0) is the
regression baseline, extended by M0/M1/M2/M3/M4/M5.

**Principle:** every B3 behaviour is proven with mocked providers, a fake clock and an in-memory store.
No network, no real credential, no quota consumed.

---

## 1. Objectives

1. Prove the privacy gate still runs first and cannot be bypassed by health, quota or fallback.
2. Prove every circuit-breaker transition and concurrency rule deterministically.
3. Prove quota logic never invents a number, never spends money, and honours account scope.
4. Prove routing order, skip reasons, attempt cap, attribution and fail-closed behaviour.
5. Prove the 403 correction and the new taxonomy without breaking persisted codes.
6. Prove no secret or resume content reaches logs, exceptions, job rows or API responses.
7. Prove `AI_BREAKER_ENABLED=false` reproduces B2.

Non-goals: load tests, chaos tests, live contract tests, performance benchmarks. Those need paid
capacity or live keys and are out of scope.

---

## 2. Test architecture

```
tests/
  conftest.py                 # existing fixtures: ai_settings, auth_client, company
  fakes.py                    # NEW: FakeClock, FakeHealthStore, FakeQuotaStore, scripted adapter
  test_ai_health.py           # M2-A: passive health recording and states
  test_ai_breaker.py          # M2-B: transitions, concurrency, retry integration
  test_ai_quota.py            # M3: store, parser, rate-limit vs exhaustion, admission
  test_ai_routing.py          # NEW
  test_ai_privacy.py          # existing, unchanged
  test_ai_cloudflare.py       # existing, extended for 403/classes and one request
  test_ai_providers.py        # existing, extended
  test_ai_retry.py            # M1-B: policy and job-level retry ownership
  test_ai_router.py           # existing, extended for compatibility
  test_ai_repair.py           # existing, unchanged
  test_ai_integration.py      # existing, extended for routing/attribution
  test_logging.py             # existing, extended canaries
```

### 2.1 Fakes

```python
class FakeClock:
    def __init__(self, t: float = 1_000_000.0): self.t = t
    def now(self) -> float: return self.t
    def advance(self, seconds: float) -> None: self.t += seconds

class ScriptedAdapter:
    """Returns/raises a scripted sequence; records calls. No httpx."""
    def __init__(self, *steps): ...
    def analyze(self, request): ...
```

- `FakeClock` is injected into the health and quota stores; no `time.sleep`, no wall-clock flake.
- `ScriptedAdapter` implements the existing `AnalysisProvider` protocol (`name`, `model`, `scope`,
  `analyze`). It never touches `httpx`.
- `FakeHealthStore` / `FakeQuotaStore` are the real in-memory implementations with an injected clock;
  no separate mock of the FSM (that would test the mock).

### 2.2 Adapter tests keep using `httpx.MockTransport`

For the Cloudflare adapter, continue the B2 pattern: build `CloudflareProvider(settings,
transport=httpx.MockTransport(handler))` and assert URL, headers, body and parsing. This exercises the
real request-building code without a socket.

### 2.3 No-network guard

Add a session-scoped autouse fixture that monkeypatches `httpx.Client.send` (or the transport) to fail
if a test outside `test_ai_cloudflare.py` tries a real connection. This is the enforcement of "no live
provider requests".

---

## 3. Coverage matrix

### 3.1 Privacy gate (regression + B3 invariants)

| # | Test | Expected |
|---|---|---|
| P1 | Approved Cloudflare 70B | `denial_reasons == ()` |
| P2 | Unapproved provider | `not_approved` |
| P3 | Unregistered model | denied |
| P4 | Unknown training policy | `training_unknown` |
| P5 | Training allowed but unknown | still denied |
| P6 | Allowlist alone | never approves an unverified row |
| P7 | Unknown retention | `retention_unknown` |
| P8 | Unknown context (8B) | `context_unknown` |
| P9 | Paid-only under free-only | `not_free` |
| P10 | No JSON mode | `no_json` |
| P11 | Gemini first in chain | never selected |
| P12 | **B3:** healthy + quota-rich but denied | never called (health/quota cannot admit) |
| P13 | **B3:** denied fallback destination | skipped, never called |

P1–P11 already exist in `test_ai_privacy.py`; keep them unchanged. P12–P13 are new and are the core
privacy invariant for B3.

### 3.2 Health manager

**M2-A implemented** in `test_ai_health.py`; H6 is covered by `test_ai_breaker.py`. H8 is covered at
both levels: transient failures update model and provider, quality failures update the model only.

| # | Test | Expected | Status |
|---|---|---|---|
| H1 | Success | `consecutive_failures=0`, `successes++`, `last_success_at` set | M2-A |
| H2 | Failure | `failures++`, `consecutive_failures++`, `last_failure_class` set | M2-A |
| H3 | Failure then success | consecutive resets, counters retained | M2-A |
| H4 | Latency | EWMA moves toward the sample; sample count increments | M2-A |
| H5 | Degraded | 1..threshold−1 failures → `degraded`, still usable | M2-A |
| H6 | Open | threshold failures → `open` | M2-B |
| H7 | Disabled | auth/permission sets `disabled_reason`, survives failures | M2-A |
| H8 | Provider vs model key | both updated on transient failure; independent otherwise | M2-A |
| H9 | Snapshot | returns a copy, not mutable shared state | M2-A |
| H10 | Non-health failures | 429/quota/invalid model/blocked/privacy create no record | M2-A |
| H11 | Latency excludes sleep | retry sleep advances the clock but not measured latency | M2-A |
| H12 | Concurrent updates | 8 threads × 100 successes → exact count, no corruption | M2-A |
| H13 | No sensitive data | stored record/repr contains no resume or token text | M2-A |
| H14 | Retry integration | each intermediate failure and the final success are recorded | M2-A |

### 3.2.1 Circuit breaker

Implemented in `test_ai_breaker.py`. All cases use a fake clock and a scripted provider.

| # | Test | Expected |
|---|---|---|
| B1 | Three transient failures | `open`, `opened_at` set, cooldown 120 |
| B2 | Two transient failures | still `degraded`, not open |
| B3 | Open admission | `ProviderCircuitOpen`, provider calls 0 |
| B4 | Before cooldown | still open, rejected |
| B5 | After cooldown | `half_open`, probe admitted |
| B6 | Concurrent probes | exactly one admitted, seven rejected |
| B7 | Probe success | `healthy`, counters and cooldown reset |
| B8 | Probe transient failure | `open`, cooldown ×2 |
| B9 | Repeated probe failures | 120 → 240 → 480 → 900 → 900 |
| B10 | Auth/permission/entitlement | `disabled`, breaker untouched |
| B11 | Rate limit / quota | no record, breaker untouched |
| B12 | Invalid JSON/schema | quality only, breaker untouched |
| B13 | Non-transient probe failure | closes (provider answered), no reopen |
| B14 | Manual disable | survives success and `recover_credentials` |
| B15 | Credential disable | survives success; explicit recovery clears it |
| B16 | `AI_BREAKER_ENABLED=false` | M2-A behaviour, 10 failures stay `degraded` |
| B17 | Retry integration | retry stops at open breaker; same attempt accounting |
| B18 | Circuit-open recording | no failure/latency/outcome added |
| B19 | Unexpected exception | half-open slot released, breaker stays open |
| B20 | Job-level open | `circuit_open`, `attempts=1`, no extra HTTP calls |
| B21 | Privacy gate | denial precedes admission; health store empty |

### 3.3 Circuit breaker

| # | Test | Expected |
|---|---|---|
| B1 | CLOSED, below threshold | allowed |
| B2 | CLOSED → OPEN at N | next call blocked |
| B3 | OPEN before cooldown | blocked, no state change |
| B4 | OPEN after cooldown | transitions to HALF_OPEN, one token |
| B5 | HALF_OPEN success | CLOSED, counters reset, base cooldown |
| B6 | HALF_OPEN failure | OPEN, cooldown ×2 |
| B7 | Backoff cap | never exceeds `AI_BREAKER_COOLDOWN_MAX_SECONDS` |
| B8 | Second concurrent caller in HALF_OPEN | skipped (`circuit_open`) |
| B9 | Two threads race the probe | exactly one token (thread test with a barrier) |
| B10 | Probe raises | slot released in `finally` |
| B11 | 429 | breaker untouched |
| B12 | Auth / permission | breaker untouched, provider disabled |
| B13 | Invalid output / schema | breaker untouched |
| B14 | Provider-level OPEN | all models skipped |
| B15 | Model-level OPEN | only that model skipped |
| B16 | `AI_BREAKER_ENABLED=false` | no filtering, B2 behaviour |

### 3.4 Quota lifecycle

Implemented in `test_ai_quota.py`. All cases use a fake clock, a scripted provider, synthetic
headers or a mocked transport.

| # | Test | Expected |
|---|---|---|
| Q1 | Unknown quota | `None` in every field, state `unknown`, admission allowed |
| Q2 | Known available capacity | `remaining`, `limit`, `unit`, `resets_at` stored |
| Q3 | Known exhaustion | state `exhausted`, admission rejected |
| Q4 | Account scope | exhaustion blocks every model on the provider |
| Q5 | Model scope | only that model bucket is affected; account stays unknown |
| Q6 | Snapshot | returns copies; mutation does not change the store |
| Q7 | Concurrency | 8 threads × 50 updates → exact count, no corruption |
| Q8 | No private data | snapshot repr has no token, account id or resume text |
| Q9 | 3036 | exhaustion until the next 00:00 UTC |
| Q10 | Missing headers | unknown, not zero |
| Q11 | Malformed numeric values | ignored, unknown |
| Q12 | Negative / non-finite values | ignored, unknown |
| Q13 | Invalid reset timestamp | stays `None` |
| Q14 | Contradictory exhaustion | exhaustion wins; `remaining` cleared |
| Q15 | Undocumented headers | ignored (`Ratelimit`, `X-RateLimit-*`) |
| Q16 | `Retry-After` | feeds the existing retry cap; date form stays unknown |
| Q17 | Temporary 429 / 3040 | rate-limited, not exhausted; admission allowed |
| Q18 | Confirmed exhaustion | admission rejected before HTTP |
| Q19 | Expired reset | re-evaluated to unknown, no capacity invented |
| Q20 | Unknown reset time | stays blocked; an already-elapsed reset does not |
| Q21 | Available observation | recovers quota |
| Q22 | Served request | clears exhaustion, capacity stays unknown |
| Q23 | Admission before HTTP | zero provider calls on rejection |
| Q24 | Privacy first | privacy denial reported before any quota admission |
| Q25 | Health isolation | quota rejection adds no failure record |
| Q26 | Latency isolation | quota rejection adds no latency sample |
| Q27 | Retry re-check | a retry is rejected after exhaustion appears |
| Q28 | No quota retry | `ProviderQuotaExhausted` is never retried |
| Q29 | Breaker unchanged | still opens and still blocks with quota enabled |
| Q30 | No fallback | one provider, zero HTTP calls on rejection |
| Q31 | Job accounting | `provider_quota_exhausted`, `attempts=1`, no result |
| Q32 | Flag off | `AI_QUOTA_ENABLED=false` reproduces M2-B exactly |

#### M3 hardening — 3036 protection

Added by the M3 hardening patch; all offline with a fake UTC clock.

| # | Test | Expected |
|---|---|---|
| Q33 | 200 after active 3036 | still exhausted, `exhausted_until` unchanged, no remaining invented |
| Q34 | 200 at/after reset | window expires, state `unknown`, no capacity invented |
| Q35 | Generic 429 / 3040 after 3036 | still exhausted, reset unchanged |
| Q36 | Explicit `remaining > 0` after 3036 | still exhausted, reset unchanged |
| Q37 | Empty/malformed evidence after 3036 | still exhausted |
| Q38 | Both observation orders | exhaustion wins regardless of completion order |
| Q39 | Concurrent success + 3036 | atomic; still exhausted, reset unchanged |
| Q40 | Admission after a success | `ProviderQuotaExhausted`, zero HTTP calls |
| Q41 | Adapter 200 after 3036 | does not clear the bucket |
| Q42 | Generic exhaustion | still recovers on success/available evidence (unchanged) |

### 3.5 Router (M4, implemented)

Implemented in `test_ai_router.py`; all offline with fake clocks, scripted providers and the existing
registry facts.

| # | Test | Expected |
|---|---|---|
| R1 | Approved Cloudflare | selected, priority 0, privacy-approved |
| R2 | Gemini candidate | denied by the gate |
| R3 | Groq candidate | denied (training unknown) |
| R4 | OpenRouter candidate | denied (unregistered) |
| R5 | OpenAI candidate | denied (unregistered) |
| R6 | Unknown privacy evidence | `privacy_unverified`, no candidate |
| R7 | Disallowed data class | `data_class_not_approved` |
| R8 | Training violation | `training_not_allowed` |
| R9 | Retention violation | `retention_unknown` |
| R10 | Free-only | paid candidate excluded |
| R11 | Unsupported capability | `no_json` excluded |
| R12 | Insufficient context | `context_insufficient` |
| R13 | Oversized request | excluded before any call |
| R14 | Disabled provider | excluded, `disabled` |
| R15 | Open breaker | excluded, `circuit_open` |
| R16 | Half-open probe | routable, probe **not** claimed by ranking |
| R17 | Quota exhaustion | excluded, `quota_exhausted` |
| R18 | Unknown quota | allowed |
| R19 | Degraded health | still routable |
| R20 | Temporary rate limit | still routable; retry owns timing |
| R21 | Quota disabled | exhausted bucket does not exclude |
| R22 | Breaker disabled | open breaker does not exclude |
| R23 | Explicit priority | lower priority index wins |
| R24 | Stable tie-break | provider/model name order |
| R25 | No invented fields | candidate has no cost/latency |
| R26 | Deterministic decision | repeated calls identical |
| R27 | Quota before breaker | quota rejection leaves probe unclaimed |
| R28 | Breaker rejection | zero HTTP requests |
| R29 | Retry re-check | exhaustion appearing mid-run blocks the next attempt |
| R30 | No duplicate admission | quota and breaker each admitted once per attempt |
| R31 | Retry cap | stops at `AI_MAX_ATTEMPTS` |
| R32 | Same provider | retries reuse one adapter |
| R33 | Typed no-candidate | capability error, zero HTTP |
| R34 | Unregistered model | `ai_unavailable`, zero HTTP |
| R35 | Quota failure | `provider_quota_exhausted`, zero HTTP |
| R36 | Selection log | provider/model only, no resume content |
| R37 | Privacy first | denial before execution |
| R38 | Fallback setting | adds no candidates |
| R39 | Failure isolation | no second provider invoked |
| R40 | Routing disabled | exact M3 admission |
| R41 | Job accounting | success, `attempts=1` |
| R42 | Result count | exactly one result row |
| R43 | Existing B2/M1/M2/M3 suites | unchanged and green |

### 3.6 Error taxonomy and 403

| # | Test | Expected |
|---|---|---|
| E1 | 401 | `ProviderAuthFailed` |
| E2 | 403 | `ProviderPermissionDenied` |
| E3 | 403 body | not in `str(exc)`, not in logs, not in `job.error_message` |
| E4 | 429 | `ProviderRateLimited` + `retry_after_seconds` |
| E5 | 5xx | `ProviderUnavailable` subclass, one HTTP request |
| E6 | 404 model | `ProviderInvalidModel` |
| E7 | malformed JSON | `ProviderJsonParseError` (subclass of `ProviderInvalidOutput`) |
| E8 | schema mismatch | `ProviderSchemaError` (subclass) |
| E9 | existing catches | `except ProviderInvalidOutput` / `ProviderRateLimited` still match |
| E10 | persisted codes | B2 codes unchanged |

### 3.6.1 Retry ownership (M1-B, implemented)

| # | Test | Expected |
|---|---|---|
| E11 | Adapter one-request | Cloudflare makes exactly one HTTP request for 200/400/401/403/404/429/5xx |
| E12 | Orchestration retry | timeout/network/5xx retried by `ai/retry.py`, `attempts=1` at job level |
| E13 | Attempt cap | stops at `AI_MAX_ATTEMPTS`; no unbounded loop |
| E14 | 429 short `Retry-After` | sleeps exactly the header value, then retries |
| E15 | 429 long or missing `Retry-After` | no retry; terminal `provider_rate_limited` |
| E16 | Terminal classes | auth/permission/privacy/invalid model/invalid output/quota not retried |
| E17 | Gemini | no internal retry, no repair, one request; still never routed |
| E18 | No fallback | the retry loop reuses the same provider instance only |

Existing suites: `test_ai_retry.py` (policy + job), `test_ai_cloudflare.py` (one request),
`test_ai_b3_baseline.py` (job accounting) and `test_ai_integration.py` (outage).

### 3.7 Logging and privacy

| # | Test | Expected |
|---|---|---|
| L1 | Resume canary | absent from `caplog`, `str(exc)`, API response, `job.error_message` (`test_typed_errors_do_not_echo_resume_content`, `test_attempt_records_never_carry_request_or_error_content`) |
| L2 | Token canary | absent everywhere (`test_analysis_uses_cloudflare_and_attributes_model`, `test_failed_job_logs_one_terminal_record_without_provider_content`) |
| L3 | Account-id canary | absent, including `httpx` records (`test_httpx_request_url_is_not_captured_while_app_errors_are`) |
| L4 | Provider body canary | absent from logs and job rows (`test_failed_job_logs_one_terminal_record_without_provider_content`) |
| L5 | Unknown extra field | dropped by the allowlist formatter (`test_only_allowlisted_fields_survive`) |
| L6 | `httpx` level | pinned to WARNING (`test_configure_logging_quiets_httpx_without_disabling_app_logs`) |
| L7 | Skip/attempt record | one per skip (`provider`, `model`, `reason`, DEBUG) and one per attempt (`attempt`, `latency_ms`, `status`, `code`, `failure_class`); no content (`test_every_skip_emits_one_debug_record`, `test_skip_records_stay_below_info`, `test_each_attempt_emits_exactly_one_record`) |
| L8 | Terminal record | exactly one `analysis failed` with `code`, no body content (`test_failed_job_logs_one_terminal_record_without_provider_content`) |
| L9 | Allowlist additions | `priority`, `health`, `quota`, `failure_class`, `delay_seconds` survive; sensitive names absent (`test_observability_fields_are_allowlisted_without_sensitive_names`, `test_routing_and_attempt_metadata_is_not_silently_dropped`) |

### 3.8 Integration (API-level, mocked provider)

| # | Test | Expected |
|---|---|---|
| I1 | Success | `POST /analyses` 201 → poll `succeeded`; `provider=cloudflare`, model, `attempts=1`, result retrievable |
| I2 | Gemini only | job failed `provider_privacy_denied`; Gemini never called |
| I3 | Cloudflare unconfigured | job failed `ai_not_configured`; no fallback |
| I4 | Auth failure | job failed `provider_auth_failed`; token not in response |
| I5 | Outage | job failed `provider_unavailable` (B2 as-built; B3 target aggregates to `ai_unavailable`); no provider switch |
| I6 | Quota | job failed `ai_quota_exhausted`; no paid path |
| I7 | Breaker open | no HTTP call; `ai_unavailable` |
| I8 | Idempotent submit | same hash returns the existing job, no duplicate |
| I9 | Retained B2 rows | untouched by tests (read-only assertion) |

I1–I5 mirror `test_ai_integration.py`; keep them and add I6–I9.

---

## 4. Determinism and isolation

- Fake clock everywhere; no real `time.sleep`, no `datetime.now()` in assertions. The M1-B retry
  tests inject/record the sleep function instead of waiting.
- Each test gets fresh stores; no module-level state leaks between tests.
- Adapter tests use `httpx.MockTransport`; other tests use `ScriptedAdapter`.
- No test reads `backend/.env`; `ai_settings` builds settings explicitly (existing fixture).
- Tests must not depend on execution order; the thread test uses a barrier with a timeout.
- The no-network guard fails loudly if a real client is constructed outside the allowed adapter tests.

---

## 5. Regression protection for B2

| B2 behaviour | Guard |
|---|---|
| Gate denies Gemini | `test_ai_privacy.py` P11 unchanged |
| 8B stays disabled | P8 unchanged |
| One provider, no fallback | R1/R15; `AI_ALLOW_CROSS_PROVIDER_FALLBACK=false` |
| Success path attribution | I1; `provider=cloudflare`, model unchanged |
| Auth failure text | I4; no token leak |
| Outage does not switch | I5; two provider attempts, one job attempt, same provider |
| `select_provider()` compatibility | `test_ai_router.py` unchanged |
| `get_provider()` compatibility | `test_ai_router.py` unchanged |
| Logging allowlist | L1–L7 |
| B2 synthetic rows | I9 read-only count/ID assertion |

`AI_BREAKER_ENABLED=false` + `AI_MAX_ATTEMPTS=1` + fallback off must pass the entire B2 suite unchanged.

---

## 6. Per-milestone test gate

| Milestone | Required before merge |
|---|---|
| M0 | characterization tests green on unmodified code |
| M1 | E1–E18 (taxonomy, 403 split, adapter one-request, centralized retry); full suite |
| M2 | M2-A: H1–H5, H7–H14, privacy P12, retry regression; M2-B: H6, B1–B21, flag-off test |
| M3 | Q1–Q42, account-scope test, no-network quota test, flag-off test, 3036-protection tests; full suite |
| M4 | R1-R43; I1-I9; privacy P12-P13; flag-off M3 parity |
| M5 | L1–L9; canary tests; log-volume sanity |
| M6 | **Implemented** — docs match code; routing-off parity and the four-flag B2 parity set verified; no live call |

A milestone is not mergeable if any existing test fails for a reason other than the documented 403
expectation.

---

## 7. What is deliberately not tested (and why)

| Not tested | Reason |
|---|---|
| Live Cloudflare 429/quota | would consume the free allowance and needs approval |
| Production deployment / rollout | not performed in B3; the procedure is in `docs/STAGE2_B3_ROLLOUT.md` |
| Real provider outage | not reproducible; mocked at the adapter boundary |
| Multi-worker shared state | not in B3 (memory-only) |
| Cross-provider fallback | not implemented in M4; enabling it would move resume data to another processor |
| Redis/MySQL store | not implemented |
| Load / latency SLO | needs paid capacity; contradicts free-only |
| Prompt quality across resumes | B2 scope; one synthetic case already validated |
| UI behaviour | no frontend change |

---

## 8. Acceptance summary

- Every row in §3 has a test or is explicitly waived above.
- All tests are deterministic, offline and order-independent.
- The privacy invariant (P12–P13) is asserted in at least two layers: router unit and API integration.
- M4 routing is deterministic and owns quota/breaker admission; fallback remains disabled.
- M5 emits one structured skip/attempt record and one terminal record per job; no content field is
  allowlisted.
- The B2 suite passes with the breaker flag off.
- No test prints or asserts on a real credential, account id, resume text or provider body.
- `ruff check app tests alembic` clean.
- Final counts: router **57 passed**, logging **7 passed**, B3 targeted **282 passed**, full **350 passed**.
- M6 documentation matches the code; the rollout/rollback procedure is documented and production-only
  checks are marked NOT PERFORMED.
