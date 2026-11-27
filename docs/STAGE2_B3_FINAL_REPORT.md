# Stage 2 — B3 Final As-Built Report

**Status:** B3 complete (M0–M6). Implemented, tested locally with mocked providers, and documented.
**Not** deployed to production; production-only checks are listed as NOT PERFORMED.

- Architecture: `docs/STAGE2_B3_ARCHITECTURE.md`
- Plan and milestone record: `docs/STAGE2_B3_IMPLEMENTATION_PLAN.md`
- Test strategy: `docs/STAGE2_B3_TEST_STRATEGY.md`
- Rollout and rollback: `docs/STAGE2_B3_ROLLOUT.md`
- AI architecture (updated): `docs/STAGE2_AI_ARCHITECTURE.md`

---

## 1. Executive summary

B3 replaced a single-shot, privacy-gated provider call with a reliability layer: a typed error
taxonomy, a passive health manager, a circuit breaker, a quota lifecycle manager, a deterministic
router that owns admission, and structured observability. The privacy gate remains the first and
strictest filter. Only Cloudflare is approved, only one provider is ever attempted, and
cross-provider fallback is not implemented.

The backend suite grew from 143 tests before B3 to **350 passing**. All provider traffic in tests is
mocked with `httpx.MockTransport`; no live request, credential or quota was used. The application was
not deployed, and no production behaviour is claimed beyond what the tests prove.

## 2. Original B3 objectives

1. Make provider failures typed and honest (401 vs 403, quota vs rate limit, JSON vs schema).
2. Stop retry amplification: one retry owner, bounded attempts.
3. Survive transient provider failures without sending resume data anywhere else.
4. Track free-tier quota without inventing capacity or enabling a paid path.
5. Route deterministically across configured providers, privacy first, with explainable skips.
6. Make every decision observable without logging content.
7. Ship with a rollback switch and a paper trail.

B3's earlier name in `STAGE2_AI_ARCHITECTURE.md` was "additional providers (conditional)". The
implemented scope became reliability and routing; no new provider was approved.

## 3. Milestone completion

| Milestone | Scope | Status | Evidence |
|---|---|---|---|
| M0 | Baseline and characterization | **Implemented, tested** | `test_ai_b3_baseline.py`; 151 tests after M0 |
| M1-A | Error taxonomy and 403 correction | **Implemented, tested** | `test_ai_cloudflare.py`, `test_ai_privacy.py` |
| M1-B | Centralized retry, attempt accounting | **Implemented, tested** | `test_ai_retry.py` |
| M2-A | Passive health manager | **Implemented, tested** | `test_ai_health.py` |
| M2-B | Circuit breaker | **Implemented, tested** | `test_ai_breaker.py` |
| M3 | Quota lifecycle (+ 3036 hardening) | **Implemented, tested** | `test_ai_quota.py` |
| M4 | Intelligent router, admission ownership | **Implemented, tested** | `test_ai_router.py` (57) |
| M5 | Observability | **Implemented, tested** | `test_logging.py` (7), router attempt/skip tests |
| M6 | Docs, rollout, rollback, final report | **Implemented, documented** | this report, `STAGE2_B3_ROLLOUT.md` |
| M7 | Multi-worker persistence | **Deferred** | design only, not B3 |

## 4. Final architecture

```
services/analysis.py:run()
  └─ registry.get_provider() → router.select_provider(settings)     submit-time, privacy only
        └─ privacy.approved_candidates() → providers.build_adapter()
  └─ router.route_and_run(provider, request, settings, health, quota)
        ├─ routing off / out-of-chain → retry.py (M3 path)
        └─ build_decision()
              ├─ enumerate AI_PROVIDER_ORDER
              ├─ privacy + capability gate (denial_reasons)
              ├─ read-only health filter (routing_status)
              ├─ read-only quota filter (known exhaustion)
              └─ rank: priority → health → quota → provider → model
        ├─ no matching candidate → typed error, no HTTP
        └─ analyze_with_retry(admit=router-owned)
              └─ per attempt: quota.admit → breaker.admit → adapter.analyze
```

Components: `privacy.py`, `models.py`, `providers.py`, `registry.py`, `cloudflare.py`, `base.py`,
`retry.py`, `health.py`, `quota.py`, `router.py`, `output.py`, `repair.py`. No new dependency, no
schema change, no frontend change.

## 5. Provider eligibility and privacy model

`privacy.denial_reasons()` runs before health or quota and returns every failed check:

1. provider is in `AI_APPROVED_PROVIDERS`;
2. model is registered;
3. model is approved for the resume data class;
4. retention is documented (`retention_unknown` denies);
5. training use is known and allowed (`training_unknown`, `training_not_allowed` deny);
6. free-tier eligibility holds under `AI_FREE_ONLY`;
7. structured JSON output is documented;
8. context window is known and large enough (`max(8_000, estimate)`).

Unknown fails closed. Adding a name to the allowlist cannot approve an unverified registry row.
Today only `cloudflare` / `@cf/meta/llama-3.3-70b-instruct-fp8-fast` passes; Gemini, Groq,
OpenRouter and OpenAI are denied. Free-only, retention and training settings were not weakened.

## 6. Routing and ranking

Deterministic total order: configured priority (index in `AI_PROVIDER_ORDER`), health
(`healthy < degraded < half_open < open < disabled`), quota (`available/unknown < rate_limited <
exhausted`), then provider and model names. Capability and context are filters, not scores: a model
that cannot hold the request is ineligible. `select_provider()` remains the submit-time,
privacy-only selector; the run-time decision is recomputed immediately before execution so stale
state cannot reach the network.

Failure mapping: privacy → `ProviderPrivacyDenied`; quota → `ProviderQuotaExhausted`;
breaker/disabled → `ProviderCircuitOpen`; capability/context → `ProviderUnsupportedCapability`;
otherwise `ProviderNoEligibleCandidate` (`ai_unavailable`).

## 7. Health, quota and breaker lifecycle

**Health/breaker (`health.py`).** Per provider and per model. Transient failures (timeout,
unavailable, network) count toward opening; quality failures are model-level evidence only; auth and
permission disable the provider for the process; quota/rate-limit and blocked content do not count.
States are `healthy`, `degraded`, `open`, `half_open`, `disabled`. `routing_status()` is read-only;
`admit()` atomically claims the single half-open probe. Defaults: 3 failures, 120 s cooldown, 900 s
cap, 2.0 multiplier. `AI_BREAKER_ENABLED=false` makes admission a no-op while evidence is recorded.

**Quota (`quota.py`).** Process-local account/model bucket. Unknown is `None`, never zero. `admit()`
blocks only known exhaustion. Cloudflare error `3036` is confirmed daily exhaustion and is protected
until the documented 00:00 UTC reset; `3040` and other 429s are temporary rate limits carrying
`Retry-After` when valid. A success cannot clear an active `3036` window. No remaining-capacity
header exists, so `remaining`/`limit`/`unit` stay unknown. `AI_QUOTA_ENABLED=false` makes admission a
no-op but keeps evidence.

**Interaction.** Privacy first, then read-only operational filters, then ranking. At execution:
quota admission before breaker admission, so a quota rejection cannot consume the half-open probe.
Admission repeats before every attempt.

## 8. Retry and admission ownership

`retry.py` owns retry timing, caps and retryable classes. It retries timeout/network/5xx with bounded
exponential backoff and a bounded 429 `Retry-After`; auth, permission, privacy, invalid model,
invalid output, unsupported capability and quota exhaustion are terminal. `job.attempts` still
increments once per run; provider attempts are internal.

Admission has exactly one owner per mode:

- routing on + in-chain provider → the router (`admit` callable supplied to retry);
- routing off, or an injected out-of-chain provider → `retry.py` (M3 path).

`AI_MAX_ATTEMPTS=2` preserves B2's effective one retry. `AI_ROUTING_ENABLED=false` reproduces M3,
not B2; full B2 parity needs routing, breaker and quota off plus `AI_MAX_ATTEMPTS=2` (see the rollout
doc).

## 9. Observability and security

| Record | Level | Fields |
|---|---|---|
| `route candidate skipped` | DEBUG | `provider`, `model`, `reason` |
| `route selected` | INFO | `provider`, `model`, `priority`, `health`, `quota` |
| `provider attempt` | INFO/WARNING | `provider`, `model`, `attempt`, `latency_ms`, `status`, plus `code`, `failure_class`, `delay_seconds` on failure |
| `analysis succeeded` / `analysis failed` | INFO/WARNING | `job_id`, `provider`, `score` or `code` |

The allowlist formatter is the only egress for extras; unknown fields are dropped and counted.
`priority`, `health`, `quota`, `failure_class` and `delay_seconds` were added in M5. Sensitive names
(`resume_text`, `jd_text`, `prompt`, `token`, `authorization`, `account_id`, `body`,
`error_message`) are not allowlisted. Attempt records use `error.code` and `classify_failure()`,
never `str(error)`. Exception messages are replaced by type and last frame. `httpx` stays at WARNING
so request URLs (account id) are not formatted. Canary tests cover logs, `str(exc)`, API responses
and `job.error_message`.

## 10. B2 compatibility

- Historical error codes remain valid; no data migration.
- The one intentional non-additive change is the 403 mapping: B2 mapped 401 and 403 to
  `provider_auth_failed`; B3 maps 401 to `provider_auth_failed`, documented 403 plan/terms codes to
  `provider_entitlement_denied`, and other 403s (including `3023` and unknown) to
  `provider_permission_denied`. `ProviderEntitlementDenied` subclasses `ProviderPermissionDenied`.
  Full note: `docs/STAGE2_B2_IMPLEMENTATION_REPORT.md` §14.8.
- Gemini's 403 still maps to generic `provider_rejected`, but Gemini is structurally denied and never
  routed.
- API shape, status codes, job fields and existing endpoints are unchanged. The frontend does not key
  on the specific AI error strings.
- `select_provider()` and `registry.get_provider()` signatures are unchanged.
- No schema, dependency, provider approval, free-only, retention or training change.

## 11. Configuration reference

| Setting | Default | Effect |
|---|---|---|
| `AI_PROVIDER` | `cloudflare` | Legacy single-provider fallback when the order is blank |
| `AI_PROVIDER_ORDER` | `cloudflare` | Candidate chain and priority |
| `AI_APPROVED_PROVIDERS` | `cloudflare` | Privacy allowlist; adding a name cannot approve an unverified row |
| `AI_FREE_ONLY` | `true` | Paid models are denied |
| `AI_ALLOW_TRAINING_PROVIDERS` | `false` | Training providers are denied |
| `AI_TIMEOUT_SECONDS` | `90` | Adapter HTTP timeout |
| `AI_MAX_ATTEMPTS` | `2` | Adapter invocations per run; 2 = B2's one retry |
| `AI_RETRY_BASE_DELAY_SECONDS` | `1.0` | Exponential base |
| `AI_RETRY_MAX_DELAY_SECONDS` | `10.0` | Cap; longer `Retry-After` is terminal |
| `AI_BREAKER_ENABLED` | `true` | `false` = admission no-op, evidence still recorded |
| `AI_BREAKER_FAILURES` | `3` | Consecutive transient failures to open |
| `AI_BREAKER_COOLDOWN_SECONDS` | `120` | First cooldown |
| `AI_BREAKER_COOLDOWN_MAX_SECONDS` | `900` | Backoff cap |
| `AI_BREAKER_BACKOFF_MULTIPLIER` | `2.0` | Cooldown growth |
| `AI_QUOTA_ENABLED` | `true` | `false` = admission no-op, evidence still recorded |
| `AI_ROUTING_ENABLED` | `true` | `false` = M3 path exactly |
| `AI_ALLOW_CROSS_PROVIDER_FALLBACK` | `false` | Accepted, never read to add candidates or attempts |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | unset | Credential presence; never logged |
| `CLOUDFLARE_MODEL` | 70B instruct fp8 fast | Must match a verified registry row |
| `LOG_LEVEL` | `INFO` | `DEBUG` shows skip records |
| `CAREEROS_ENV` | `development` | `production` in deployment |

`.env.example` documents the pre-B3 core settings only; B3 knobs use safe defaults and are listed in
`STAGE2_AI_ARCHITECTURE.md` §14. Updating `.env.example` is a B4 task.

## 12. Rollout procedure (summary)

Full detail: `docs/STAGE2_B3_ROLLOUT.md`.

1. **Pre-rollout:** green suite and Ruff; verify approval/free-only/chain/model/credentials without
   printing them; fallback off; breaker/quota/routing values intended; `/ready` and MySQL 8.
2. **Deploy:** config first, then the backend artifact. No migration, no dependency change.
3. **Startup:** `/health`, `/ready`, `careeros started` log, no traceback.
4. **Provider init:** one controlled analysis; correct `provider`/`model` attribution; typed failure
   if credentials or approvals are wrong.
5. **Health/quota/routing/observability:** check the `route selected` record, one attempt record per
   attempt, one terminal record, and no content in logs.
6. **Post-rollout:** the measurable checks in the rollout doc, including a staging-only privacy
   denial and routing-off parity run.

## 13. Rollback procedure (summary)

Triggers: unapproved egress, unknown-evidence admission, content leak, startup/readiness failure, or
an unexplained rise in AI failure codes.

1. Immediate mitigation: `AI_ROUTING_ENABLED=false` (M3 path; privacy still enforced).
2. B2 parity: also `AI_BREAKER_ENABLED=false`, `AI_QUOTA_ENABLED=false`, `AI_MAX_ATTEMPTS=2`.
3. Redeploy the last good artifact. No schema/data reversal, no credential or approval change.
4. Verify `/health`, `/ready`, one controlled analysis, logs and typed errors.
5. Run the regression suite on the restored artifact.

Limitations: in-memory state resets on restart; routing-off alone is M3, not B2; a pre-M1-A artifact
will again report 403s as `provider_auth_failed`; nothing can recall data already sent to an approved
provider.

## 14. Test coverage and exact results

All tests offline; no live provider call.

| Check | Result |
|---|---|
| `ruff check app tests alembic` | **All checks passed!** |
| `test_ai_router.py` | **57 passed** |
| `test_logging.py` | **7 passed** |
| B3 targeted suite (router, privacy, quota, breaker, health, retry, baseline, integration, Cloudflare, providers, analysis, analytics, logging) | **282 passed in 437.77 s** |
| Full backend suite | **350 passed in 509.75 s (0:08:29)** |

Baseline before B3: 143 tests. Growth: +207. No skipped or xfailed tests.

Focused M6 checks: **6 passed in 7.02 s** — routing-off M3 parity, fallback setting inert, privacy
denial before execution, typed errors without resume content, one terminal log with no provider body,
and attempt records without request content. Configuration parse confirmed the expected defaults and
the single approved provider.

Coverage by area: privacy gate (allowlist, unknown evidence, data class, retention, training,
free-only, context); adapter contract and 401/403/404/429/5xx; retry policy and attempt accounting;
health states and breaker transitions; quota unknown/exhaustion/rate-limit/3036 protection; routing
eligibility, ranking, admission ownership, no-fallback; API-level success/failure/attribution;
observability allowlist and canaries; B2 characterization.

## 15. Known limitations

1. **Process-local state.** Breaker and quota are per worker; multi-worker sharing is M7.
2. **No active health probe.** Recovery happens on a real request after cooldown.
3. **No remaining-quota truth.** Cloudflare publishes no usable header; the bucket stays unknown
   until an authoritative signal.
4. **Capability/context is a filter, not a rank score** — a model that cannot hold the request is
   ineligible.
5. **Cross-provider fallback is not implemented.** The flag is inert.
6. **Single approved provider**, so multi-provider ranking is exercised only by synthetic tests.
7. **No log aggregation/sampling/retention**; skips are DEBUG and invisible at INFO.
8. **No metrics/histograms**, only per-attempt `latency_ms`.
9. **No encryption at rest, DB TLS, HSTS or backup retention** — inherited Stage 2 gaps.
10. **403 remap is a deliberate contract change** (see §10).

## 16. Deferred M7 functionality

- `RedisHealthStore` / `RedisQuotaStore` or a MySQL `ai_provider_state` table for shared state.
- Atomic cross-worker half-open probe and quota admission (`INCR`+`EXPIRE`, Lua CAS, or
  `SELECT ... FOR UPDATE`).
- Requires an infrastructure/schema decision; the `HealthStore`/`QuotaStore` protocols make it a
  local change.

Also deferred: second approved provider and its privacy notice, active probes, per-user metering, a
UI provider selector, background retry scheduling, embeddings, any paid tier.

## 17. Production-readiness assessment

**Ready to deploy behind the documented switch, not proven in production.**

What is proven: privacy-first eligibility, no unapproved egress, deterministic routing, admission
ownership, typed errors, bounded retry, quota/breaker behaviour, redaction, B2 compatibility, and a
green 350-test suite.

What is not proven: a live call through the **B3** routing/breaker/quota path (B2's post-token live
analysis succeeded on 2026-11-24, but B3 made no live request, so its new paths are proven only with
mocks); live 403 classification; real quota exhaustion/breaker trips; multi-worker behaviour;
production log volume; and any load or latency target. Production-only checks are marked NOT
PERFORMED in the rollout doc.

Automated tests passing is necessary but not sufficient for a production-readiness claim.

## 18. Outstanding user decisions

1. **M7 scope:** shared state now, or accept single-worker operation?
2. **Second provider:** approve one (with a privacy notice) or keep the single-provider availability
   trade-off?
3. **B4 key rotation:** confirm every credential pasted in chat is treated as burned.
4. **Region rule:** accept "no region control, documented" or invest in region data?
5. **`.env.example`:** add the B3 tuning knobs in B4 (currently defaults-only).
6. **403 contract:** confirm external consumers accept `provider_permission_denied` /
   `provider_entitlement_denied` for new 403s.

---

## Completion statement

M6 deliverables are complete: the AI architecture sections were updated to the as-built, the B2 403
compatibility note was recorded, rollout and rollback procedures were written, local verification was
run, and this report records the exact state. B3 is complete at M6. M7 was not started.
