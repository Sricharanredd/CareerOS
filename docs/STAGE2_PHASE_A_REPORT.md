# Stage 2 — Phase A Completion Report (revised)

- Date: 2026-11-22
- Scope: documentation revision only. **No application code, config, schema or dependency was
  changed.** Nothing was committed or pushed.
- Documents revised: `docs/STAGE2_AI_ARCHITECTURE.md`, `docs/STAGE2_AI_PROVIDER_RESEARCH.md`, this
  report.
- Outcome: architecture **approved in principle**, implementation **not started**. The default
  provider decision has been reversed to Cloudflare; Gemini free is no longer the resume processor by
  default.

## 1. What this revision changed

| # | Review item | Resolution |
|---|---|---|
| 1 | `ai_allow_training_providers` must default to false | Default reversed to `False`. A provider whose training policy is undocumented or positive is skipped with reason `privacy` |
| 2 | Unknown training/retention policy must not receive resumes | Registry requires `retention` and `trains_on_content=False`, both with a `privacy_verified_on` date. Missing either = ineligible |
| 3 | Explicit privacy-approved allowlist | New `AI_APPROVED_PROVIDERS` (default `cloudflare`). It is a second gate: allowlisting cannot make an undocumented provider eligible |
| 4 | Free tier must never imply privacy eligibility | The privacy gate (gates 1–3) runs before the free-only gate (gate 4). The previous draft's ordering made the free check look like the admission test |
| 5 | Cloudflare as preferred primary | Cloudflare is now the sole approved provider and the default chain. Groq moved from "secondary" to conditional/disabled; OpenRouter conditional; OpenAI excluded |
| 6 | Fallback must not bypass privacy | Every attempt passes the same gate. A fallback only reaches another provider approved for the **same** data class (`resume_pii`) |
| 7 | Disclose multi-provider transmission | Documented: each fallback attempt may transmit the same resume to another external processor. Enabling a second processor is blocked until the privacy notice names it |
| 8 | Fail safely with no approved provider | New scenario 7: empty candidate list → `ai_unavailable`, no outbound request |
| 9 | Allowlist-only logging | Deny-list removed. `log_event()` + formatter both filter against `ALLOWED_LOG_FIELDS`; unknown fields are dropped and counted |
| 10 | Content, keys, headers cannot reach logs or errors | Fixed adapter error messages; no provider body in `message`; `exc_type` only in place of exception text; canary tests for resume, JD, key and bearer values |
| 11 | Complete data security assessment | Architecture §12, split into existing vs proposed across storage/DB access, encryption, backups, access control, deletion, third-party processing |
| 12 | Auth-failure contradiction | Resolved to one rule (§7.1): disable that provider for the process; continue only to another privacy-approved candidate; terminal with today's single-provider chain |
| 13 | Billing vs request quota | Separate buckets and separate rules: 429 is never a billing event; billing is never a fallback signal (research §8, architecture §11) |
| 14 | Reconcile the test count | Corrected to **67 `def test_` functions across 8 files** (see §4) |
| 15 | No "suitable for raw resumes" label without documented training policy | Groq and OpenRouter are labelled conditional/disabled for `resume_pii`; Gemini free and OpenAI are excluded |
| 16 | Reverify every model ID, structured-output claim and price | 25 claims re-read from official docs; 3 errors found and corrected (§3) |
| 17 | Preserve constraints | Free-only default, no paid fallback, no new dependencies, no migrations, Gemini code retained, no application-code change |

## 2. Provider decision table

| Provider | Free tier | Retention documented | Training on content documented | Approved for `resume_pii` | Decision | When it can change |
|---|---|---|---|---|---|---|
| **Cloudflare Workers AI** | 10,000 Neurons/day, 00:00 UTC reset | Yes — zero retention (standard inference) | **Yes — does not train** | **Yes** | **Approved — default primary** | n/a |
| **Groq** | Free plan: 30 RPM / 1k RPD / 8k TPM / 200k TPD | Yes — ≤30-day abuse logs, ZDR available | **No — not stated** | **No** | **Conditional / disabled** | Groq documents in writing that customer content is not used for training, and ZDR is enabled |
| **OpenRouter** | `:free`: 20 RPM, 50 RPD (<10 credits) or 1,000 RPD (≥10 ever purchased) | OpenRouter: no default storage; upstream varies | **Depends on upstream endpoint** | **No** | **Conditional / disabled** | Prompt logging off, product-improvement off, training-capable providers excluded, ZDR-only on, a `:free` model pinned to documented endpoints, and a privacy notice naming it |
| **Google Gemini — free tier** | Yes, per-model | Yes | **Yes — "used to improve our products"; human review possible** | **No** | **Excluded while free-only** | Only via a logged `AI_ALLOW_TRAINING_PROVIDERS=true` waiver, or by moving to the paid tier (out of scope) |
| **Google Gemini — paid tier** | n/a | Yes (DPA) | No | Yes | **Excluded — paid** | A deliberate paid-tier decision, which the requirement forbids |
| **OpenAI** | **None documented** | Yes — 30-day abuse logs | No (API data not used for training) | Policy passes | **Excluded — no free tier** | A paid decision, out of scope |
| **Groq preview models** (`qwen/qwen3.8-27b`) | Yes | as above | as above | No | **Excluded** | Not for production per Groq's own docs |

Net result: **exactly one processor is approved today.** The default chain has no cross-provider
fallback. That is a deliberate availability-for-privacy trade, not an oversight, and it is stated in
both documents.

## 3. Verification log — what was wrong before

25 claims were re-read from official documentation on 2026-11-21/22. The full table is research §12.
Three real errors in the earlier drafts:

| # | Earlier claim | Verified reality | Effect |
|---|---|---|---|
| 1 | Cloudflare `@cf/openai/gpt-oss-20b` as the candidate model | `@cf/openai/*` models are **not** in Cloudflare's JSON Mode list. JSON-capable free models are `@cf/meta/llama-3.3-70b-instruct-fp8-fast` and `@cf/meta/llama-3.1-8b-instruct` (plus smaller/older ones) | Model replaced; registry rule: no JSON capability = not routable |
| 2 | OpenRouter returns per-response `X-RateLimit-*` headers | No such headers on successful inference; only on 429. Quota must come from `GET /api/v1/key` | Quota design no longer depends on headers that do not exist |
| 3 | Groq structured output "verify" | `strict: true` is confirmed for `openai/gpt-oss-120b` and `openai/gpt-oss-20b` | Registry rows can be capability-verified, but privacy still blocks them |

Other facts that changed the design: Cloudflare's 70B model has a **24,000-token** context (not
128k) and `max_tokens` defaults to **256**; Cloudflare Neurons are an **account-wide** bucket shared
by all models; Gemini rate limits are per **project**, not per key, with RPD resetting at midnight
Pacific.

## 4. Backend test count — reconciliation

The earlier figure was not reproducible from the repository. The actual contents:

| File | `def test_` functions |
|---|---|
| `test_analysis.py` | 4 |
| `test_analytics.py` | 2 |
| `test_auth.py` | 18 |
| `test_crud.py` | 14 |
| `test_files.py` | 11 |
| `test_guards.py` | 11 |
| `test_productivity.py` | 5 |
| `test_workflow.py` | 2 |
| **Total** | **67 across 8 files** |

Method: counted `^\s*def test_` in every `backend/tests/test_*.py`. `pytest --collect-only` was not
run in this documentation revision, so parametrised cases may collect more than 67; 67 is the number
of test functions, which is the honest figure to quote. This is the baseline B1 must keep green.

## 5. Data security assessment — summary

Full tables are architecture §12, split into **existing** and **proposed**. Short form:

| Area | Existing (verified in repo) | Stage 2 proposes | Still missing |
|---|---|---|---|
| Resume storage / DB access | Private dir, generated names, 5 MB streamed cap, signature sniffing, authenticated ownership-checked download with `no-store` + `nosniff`, text in MySQL as a dedicated user | No new copy of text; prompts built per request in memory | Column encryption, object storage |
| Encryption at rest | **None at application layer**; plaintext files and rows; host disk encryption not documented | Document the gap only | Disk encryption, key management |
| Encryption in transit | HTTPS to the AI provider with default cert verification; dev HTTP locally; no DB TLS; `COOKIE_SECURE=false` | HTTPS asserted in adapter tests | DB TLS, HSTS, secure-cookie default |
| Backup retention | Manual `mysqldump` + copy storage dir; no schedule, retention, encryption, offsite or restore test | none | All of it |
| User access control | Single owner, Argon2id, 15-min JWT, hashed rotating refresh, CSRF, per-owner scoping, login lockout | none | MFA, RBAC, region data |
| Resume deletion | Archive by default; hard delete blocked while referenced; file unlinked best-effort; audit rows keep identifiers only | none | Secure erase; backups retain copies |
| Third-party processing | One processor (Gemini) receiving resume + JD text; free tier trains and permits human review | Cloudflare as default (zero retention, no training); Gemini only via logged waiver | DPA, in-product notice, per-user consent |

The uncomfortable finding stands: **the current production path sends resumes to a provider that
documents training on the content and permits human review.** This revision stops routing there by
default, but the cutover only happens when B2 ships.

## 6. What was not done

- No application code, migration, schema, dependency or config file was modified.
- No inference request was made; no API key was used or tested.
- No document was committed or pushed. The working tree carries the three Stage 2 docs plus the
  earlier Stage 1 work on branch `main` (HEAD `faafe74`).
- `pytest` was not run; the 67 figure is a static count.
- EEA/CH/UK region enforcement, backup encryption/retention, DB TLS, HSTS and secure-cookie defaults
  are **not** fixed by this stage; they are documented gaps.

## 7. Remaining risks

| # | Risk | Severity | Note |
|---|---|---|---|
| 1 | **API keys pasted into chat earlier (Groq, Cloudflare, OpenRouter, OpenAI) are still live until rotated** | High | Treat as burned. Rotate before B4, ideally now. Only placeholders are in the docs |
| 2 | Single approved provider → a Cloudflare outage or quota exhaustion stops resume analysis | High | Deliberate. Mitigation is a second provider that clears the privacy gate, which does not exist yet |
| 3 | Cloudflare free allowance is small (≈24 analyses/day on the 70B model at 4k in / 1.5k out) | Medium | `ai_quota_exhausted` with the 00:00 UTC reset; buying more is out of scope |
| 4 | No encryption at rest, no encrypted/retained backups, no DB TLS, no HSTS | High | Outside Stage 2; blocks any production claim |
| 5 | Cloudflare JSON Mode is explicitly not schema-guaranteed | Medium | Validation + repair + fallback; quality measured in B2 |
| 6 | 24k-token context on the approved model; very long resumes become a `422` | Medium | Deterministic and disclosed; not a silent truncation |
| 7 | Provider privacy policies can change after verification | Medium | `privacy_verified_on` dates make staleness visible; the app cannot enforce a contract |
| 8 | In-memory breaker/quota state is lost on restart | Low | One wasted attempt, never spend |
| 9 | Allowlist logging depends on new call sites using `log_event` | Low | Formatter filtering is the second line of defence; canary tests |
| 10 | `job.error_message` is user-visible and persisted | Low | Fixed adapter messages + truncation + canary tests |
| 11 | Gemini free tier remains one env var away (`AI_ALLOW_TRAINING_PROVIDERS=true`) | Medium | Intentional rollback path; the waiver logs the provider it unlocks at startup |
| 12 | No MFA, no per-user region data, no admin separation | Medium | Unchanged; documented |

## 8. Unresolved questions (need your decision, not more code)

1. **Cutover.** B2 replaces Gemini free with Cloudflare for resume processing. Is that the intended
   migration point, and will a Cloudflare account + API token be provided for it?
2. **Cloudflare model.** `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (better quality, 24k context,
   ≈24 analyses/day) or `@cf/meta/llama-3.1-8b-instruct` (cheaper, more/day, context unverified)?
3. **Second processor.** Enabling Groq or OpenRouter requires a privacy notice that names the
   processor and warns that a failed attempt may re-send the same resume elsewhere. Is that notice in
   scope, and does it block B3?
4. **Regional rule.** Gemini free must not serve EEA/CH/UK users, and CareerOS has no region data.
   Accept "no region control, documented", or add region data?
5. **Key rotation.** Confirm the keys pasted in chat are treated as compromised and will be rotated.
6. **Phase naming.** The revised plan merges the old B2+B3 (gate + first approved adapter) because a
   gate without an approved provider is an outage. Approve that merge, or keep the old split and
   accept that the intermediate build is deliberately non-functional for analyses?

## 9. Approval gate

Phase A is complete. Nothing further will be implemented, installed, migrated, committed or pushed
until you approve **B1**.

B1 in one sentence: lift the error taxonomy, add the privacy-carrying model registry and the shared
JSON-repair helper, and keep `get_provider()` returning Gemini — behaviour identical to today, all 67
existing tests green.

B2 is the privacy cutover (gate + router + Cloudflare adapter, one release).
