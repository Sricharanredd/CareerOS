# Stage 2 — B1 Implementation Report

- Date: 2026-11-22
- Scope: B1 only — error taxonomy, privacy-carrying model registry, provider registry, shared
  validate/repair helper.
- Result: **complete and green**. 84 collected tests pass (82 test functions), `ruff check` clean.
- **Gemini behaviour is unchanged.** `registry.get_provider()` still returns the Gemini adapter and
  nothing else. No config, schema, dependency, migration or endpoint changed.
- B2 was **not** started. The active provider was not switched.

## 1. Files

| File | Change | Why |
|---|---|---|
| `backend/app/ai/base.py` | Added `ProviderRateLimited` (with `retry_after_seconds`), `ProviderAuthFailed`, `ProviderBlocked`, `ProviderPrivacyDenied`; added `scope` to the `AnalysisProvider` protocol | B2 needs to classify quota, auth and safety failures separately. Today they all collapse into `ProviderError` / `ProviderInvalidOutput` |
| `backend/app/ai/models.py` | **New.** `ModelSpec`, `RESUME_DATA_CLASS`, `MODELS`, `models_for()`, `get_model()`, and the `privacy_approved` / `eligible_for_resume` properties | The privacy decision must live in data with verification dates, not in prose. `eligible_for_resume` requires documented retention + no-training + free tier + documented JSON output + a known context window |
| `backend/app/ai/providers.py` | **New.** `PROVIDERS` map and `build_adapter(provider, settings)` | One place that maps a provider name to an adapter and returns `None` when unconfigured |
| `backend/app/ai/repair.py` | **New.** `validate_or_repair(raw, regenerate, *, provider_name, max_repairs=0)`, fenced-JSON handling and the validation hint moved here verbatim from `gemini.py` | Every adapter validates output the same way. Default is 0 repairs; Gemini passes `max_repairs=1` |
| `backend/app/ai/gemini.py` | `analyze()` now calls the shared helper; removed the duplicate parse/repair code and the now-unused `json`/`logging`/`pydantic` imports; added `scope = "model"` | Behaviour-preserving refactor. Prompt, endpoint, retry statuses, `MAX_REPAIRS = 1`, repair temperature `0.0` and error messages are untouched |
| `backend/app/ai/registry.py` | Delegates construction to `build_adapter` behind the same `ai_provider == "gemini" and gemini_api_key` condition | Keeps B1's selection rule identical while giving B2 a seam |
| `backend/tests/test_ai_providers.py` | **New.** 10 tests | Registry privacy rules, error codes, adapter building, Gemini repair wiring |
| `backend/tests/test_ai_repair.py` | **New.** 5 tests | Validate/repair loop, repair limit, fenced JSON |
| `backend/tests/test_productivity.py` | Fixed three hard-coded interview dates to be relative to today | Pre-existing failure unrelated to B1; see §4 |

Not modified: `services/analysis.py`, `core/config.py`, `core/logging.py`, `ai/output.py`,
`ai/prompts.py`, `.env.example`, any migration, any frontend file, any dependency.

## 2. What the registry now enforces

| Row | Free | JSON | Context | Retention | Trains | Eligible for resumes |
|---|---|---|---|---|---|---|
| `cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast` | yes | yes | 24,000 | zero | no | **yes** |
| `cloudflare/@cf/meta/llama-3.1-8b-instruct` | yes | yes | **unknown** | zero | no | **no** — disabled until the context window is verified |
| `gemini/gemini-3.5-flash-lite` | yes | yes | 1,048,576 | free tier used to improve products | **yes** | no |
| `groq/openai/gpt-oss-120b` | yes | yes (`strict`) | 131,072 | ≤30-day abuse logs | **unknown** | no |
| `groq/openai/gpt-oss-20b` | yes | yes (`strict`) | 131,072 | ≤30-day abuse logs | **unknown** | no |

`eligible_for_resume` is the conjunction of `privacy_approved`, `free_tier`, `json_output` and a
known `context_tokens`. `privacy_approved` requires a data-class match, a `privacy_verified_on` date,
`trains_on_content is False` and a documented retention value. Free-tier eligibility alone cannot
produce `True` — the test asserts exactly that against Gemini.

OpenRouter has no row on purpose: a placeholder `:free` id would be a guess, and the registry rule is
"not listed = not routable". It gets a row at B3 only after an endpoint is pinned.

## 3. Behaviour preservation, point by point

| Gemini behaviour | Status |
|---|---|
| Endpoint, request payload, `maxOutputTokens=4096`, `responseMimeType=application/json`, safety settings | unchanged |
| Retry statuses `{429,500,502,503,504}`, one `sleep(1.5)`, then `ProviderUnavailable` | unchanged |
| `x-goog-api-key` header, timeout from `ai_timeout_seconds` | unchanged |
| One repair on validation/JSON error, at `temperature=0.0`, warning logged with provider name | unchanged (`max_repairs=MAX_REPAIRS` = 1) |
| Terminal `ProviderInvalidOutput` message and exception chaining | unchanged (raised from the final parse error) |
| Fenced ```json handling | unchanged (moved into `repair.py`) |
| `_first_text()` blocked/empty handling | unchanged |
| `_provider_message()` truncation | unchanged |
| `input_hash`, `job.provider`, `job.model`, `AI_NOT_CONFIGURED` message | unchanged |

`services/analysis.py` is untouched, which is why the `ai_not_configured` message still names
`GEMINI_API_KEY` as the existing test expects. Changing that wording belongs to B2, where the test is
updated with it.

## 4. Test results

```
backend> .venv\Scripts\python.exe -m ruff check app tests
All checks passed!

backend> .venv\Scripts\python.exe -m pytest -q
84 tests collected, 84 passed        (exit code 0)
```

| File | Test functions |
|---|---|
| `test_ai_providers.py` | 10 (new) |
| `test_ai_repair.py` | 5 (new) |
| `test_analysis.py` | 4 |
| `test_analytics.py` | 2 |
| `test_auth.py` | 18 |
| `test_crud.py` | 14 |
| `test_files.py` | 11 |
| `test_guards.py` | 11 |
| `test_productivity.py` | 5 |
| `test_workflow.py` | 2 |
| **Total** | **82 functions, 84 collected** |

Phase A recorded 67 functions / 69 collected; B1 adds 15 functions and 15 cases.

**Pre-existing failure found and fixed.** `test_productivity.py::test_interviews_auto_round_and_outcomes`
used fixed dates (`2026-11-20`, `2026-11-25`, `2026-01-05`). By 2026-11-22 the first had become "past",
so `scope=upcoming` returned 1 instead of 2. This was a date-rotten test, not a regression: the
interview query filters on `scheduled_at >= now`. The three dates are now relative
(`today ± N days`), which also keeps the round-order assertion stable. No application file was
involved.

## 5. Deliberate omissions (B2 work, not forgotten)

| Omitted | Reason |
|---|---|
| `privacy.py` / the gate function itself | Gate behaviour is B2; B1 only carries the data it will read |
| `build_adapters(settings)` fan-out | Nothing builds a chain until the router exists; an unused fan-out would be dead code |
| Cloudflare / Groq / OpenRouter adapters | B2 (Cloudflare) and B3 (the rest), per approval |
| `core/logging.py` allowlist formatter | B2, together with the first adapter that logs provider events |
| Config changes (`AI_APPROVED_PROVIDERS`, `AI_ALLOW_TRAINING_PROVIDERS`, …) | B2; defaults are documented but not yet read by code |
| Changing `ProviderBlocked` usage in Gemini | Gemini currently maps blocked content to `ProviderInvalidOutput`; changing it would alter behaviour before B2's router can act on the distinction |

## 6. Deviations from the architecture draft

1. `providers.build_adapters()` is not implemented, only `build_adapter()` (the used one).
2. The shared helper lives in `ai/repair.py` rather than inside `output.py` or `gemini.py`.
3. `analysis.py` was not touched at all, so the B1 exit criterion "same provider/model/hash" is
   guaranteed by construction rather than by a code path change.

None of these changes the B2 plan.

## 7. State and next gate

- Working tree: the five B1 files above plus the three Stage 2 docs, alongside the earlier Stage 1
  frontend work. Nothing committed or pushed.
- Active provider: **Gemini**, unchanged. No credentials were added, read from disk, or logged.
- Next: review of B1. B2 (privacy gate + router + Cloudflare adapter) remains **not started** and
  needs separate approval, credentials, and validation of the 70B model's real JSON behaviour.

Risk to know: the privacy metadata is inert until B2 ships — the app still sends resumes to Gemini
free tier on the current configuration, exactly as before B1.
