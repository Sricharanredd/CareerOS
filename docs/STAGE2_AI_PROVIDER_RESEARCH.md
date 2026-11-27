# Stage 2 — AI Provider Research (revised)

Phase A research for a privacy-first, free-only, quota-aware multi-provider AI layer in CareerOS.

- Research date: **2026-11-21**, re-verified **2026-11-22**. Every figure was read from official
  provider documentation on those dates.
- Scope: text generation for the existing resume-vs-job-description analyzer only.
- No inference request was made. No API key was used, tested, printed or copied into this document.
- Where a provider does not publish a number, this document says so. It does not estimate.
- This revision implements the review changes: privacy is a gate, not a preference; unknown policy
  means no access to resumes; every claim below has a verification entry in §12.

## 0. Reading rules for this document

| Term | Meaning here |
|---|---|
| **Free tier** | A permanent, documented allowance that does not require payment. |
| **Trial credits** | Temporary promotional credit. Not a free tier and never treated as one. |
| **Quota** | A request/token/neuron counter enforced by the provider (RPM, RPD, TPM, TPD, Neurons). |
| **Billing** | Money charged to a payment method or prepaid balance. Separate from quota. |
| **Resume data class** | `resume_pii` — extracted resume text plus job-description text. The only class this stage sends. |
| **Privacy-approved** | The provider's official documentation states both what it retains and that it does not train on customer content. |

Two rules follow from the review and are applied throughout:

1. **Free-tier eligibility is not privacy eligibility.** A provider can be free and still be
   ineligible to receive a resume.
2. **Undocumented training policy = not approved.** Silence is treated as "may train".

## 1. Decision summary

| Provider | Free tier | Privacy-approved for `resume_pii` | Decision |
|---|---|---|---|
| Cloudflare Workers AI | 10,000 Neurons/day, permanent | **Yes** — zero retention, no training, documented | **Approved**, default primary |
| Google Gemini | Permanent, per-model | **No** — free tier content is used to improve products, human review possible | **Excluded** while free-only; paid tier would be policy-compliant but is paid |
| Groq | Free plan, rate-limited | **No** — retention documented, **training use not documented** | **Conditional / disabled by default** |
| OpenRouter | `:free` variants, 50–1,000 req/day | **No** — policy is per upstream provider, so unknown by default | **Conditional / disabled by default** |
| OpenAI | **None documented** | Yes (no training on API data) | **Excluded** — no free tier |

Consequence: **exactly one provider is approved today.** The designed chain therefore has no
cross-provider fallback until Groq or OpenRouter clears the privacy gate. That is a deliberate
availability-for-privacy trade, not an oversight.

## 2. Google Gemini

Sources:
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/terms

### Free tier

A real, permanent tier. The pricing page describes it as "limited access to certain models", "free
input & output tokens", and "content used to improve our products". The rate-limit page defines its
qualification as an "active project or free trial; some projects need verification".

Free-tier availability, read per model from the pricing page:

| Model | Free tier | Paid input / output per 1M | Used to improve products (free / paid) |
|---|---|---|---|
| `gemini-3.5-flash-lite` | **Free** | $0.30 / $2.50 | **Yes / No** |
| `gemini-3.6-flash` | **Free** | $0.75 / $3.75 (through 2026-12-31) | **Yes / No** |
| `gemini-3.8-flash` | **Free** | $0.75 / $3.75 (through 2026-12-31) | **Yes / No** |
| `gemini-4-hydrogen` | **Free** | $1.50 / $7.50 | **Yes / No** |
| `gemini-4-carbon` | **Not available** | $2.00→$4.00 / $10.00→$20.00 | n/a |
| `gemini-4-argon` | **Not available** | $2.00→$4.00 / $10.00→$20.00 | n/a |
| `gemini-4-neon` | **Not available** | $3.00 / $15.00 | n/a |
| `genie-4`, `gemini-omni-*` | **Not available** | video/audio pricing | n/a |

CareerOS's configured model `gemini-3.5-flash-lite` exists (stable, listed on the models page), is
free-tier eligible, and is priced at $0.30/$2.50 on the paid tier.

### Model facts

- `gemini-3.5-flash-lite`: 1,048,576-token input context, 65,536-token output (model page).
- Structured outputs are documented for the Gemini API; the model page for `gemini-3.5-flash-lite`
  lists structured outputs as supported. Confirmed, not assumed.
- Modalities: text, image, video, audio, PDF in; text out.

### Limits

- Three dimensions: RPM, TPM (input), RPD. Some models add TPD. Images per minute apply only to
  image models.
- **Per project, not per API key.** Extra keys do not add quota.
- **RPD resets at midnight Pacific time.**
- Limits vary per model. Google does not publish a fixed free RPM/RPD table for standard models; the
  live per-model values are shown in AI Studio per project and are explicitly "not guaranteed".
- Spend-based rate limits are evaluated on a rolling 10-minute window. The Free tier row is
  **N/A** — those limits apply only from Tier 1 upward.
- Experimental and preview models are more restricted.

### Data policy — why Gemini free is excluded

- The pricing page marks every free-tier Gemini 3/4 model as "Used to improve our products: **Yes**".
  The paid column is "No".
- The Gemini API Additional Terms describe unpaid quota as an "Unpaid Service" and permit Google to
  use submitted content and responses to improve products and machine learning technologies,
  including human review. They instruct users not to submit sensitive, confidential or personal
  information to Unpaid Services.
- Paid quota is not used to improve products and is covered by the Data Processing Addendum.
- Regional: API clients made available in the **EEA, Switzerland or the UK must use Paid Services**.
- No payment method is required for the free quota, but linking Cloud Billing upgrades the project to
  a Paid Service.

**Verdict:** policy-compliant only on the paid tier. Under `AI_FREE_ONLY=true` and
`AI_ALLOW_TRAINING_PROVIDERS=false`, Gemini is excluded from resume processing. The adapter is not
deleted; it remains selectable behind an explicit, logged waiver (see architecture §10).

### Quota scope

Per **project per model**. Two models in one project have separate RPM/TPM/RPD buckets. Project
verification state is shared.

## 3. Groq

Sources:
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/models
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/your-data

### Free plan

A Free plan exists and is the default; the Developer plan is the paid upgrade. The rate-limit page
publishes a "Free Plan Limits" table. No payment method is documented as required for the Free plan.
The Free plan is a **rate-limited allowance**; the published per-token prices apply to the paid
Developer plan.

Free Plan rows relevant to text generation:

| Model | RPM | RPD | TPM | TPD | Class |
|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 | Production |
| `openai/gpt-oss-20b` | 30 | 1,000 | 8,000 | 200,000 | Production |
| `qwen/qwen3.8-27b` | 30 | 1,000 | 8,000 | 200,000 | **Preview** |
| `openai/gpt-oss-safeguard-20b` | 3 | 1,000 | 2,000 | 200,000 | Preview |
| `meta-llama/llama-prompt-guard-2-*` | 30 | 14,400 | 15,000 | 500,000 | Guard model, not generative |
| `whisper-large-v3*` | 20 | 2,000 | — | — (ASH/ASD) | Audio |

Developer-plan prices for reference: `gpt-oss-120b` $0.15/$0.60 per 1M; `gpt-oss-20b`
$0.075/$0.30. Context 131,072; max completion 65,536.

Preview models are documented as "for evaluation purposes only and should not be used in production
environments". They are therefore excluded from the production chain.

### Limits and headers

- Limits apply at the **organization level, not per user or key**, and are checked per model.
- Cached tokens do not count toward limits.
- Some organizations also have separate ITPM/OTPM limits; whether they apply is shown on the account
  limits page.
- `429` carries `retry-after`. All responses carry
  `x-ratelimit-limit-requests` / `remaining-requests` / `reset-requests` (RPD) and
  `x-ratelimit-limit-tokens` / `remaining-tokens` / `reset-tokens` (TPM).
- Header semantics are documented: the request headers are **RPD**, the token headers are **TPM**.

### Structured outputs — verified per model

Groq's Structured Outputs page lists explicit model support:

| Model | `strict: true` (constrained) | `strict: false` (best effort) |
|---|---|---|
| `openai/gpt-oss-20b` | **Yes** | Yes |
| `openai/gpt-oss-120b` | **Yes** | Yes |
| `qwen/qwen3.8-27b` | Yes | Yes |
| `openai/gpt-oss-safeguard-20b` | No | Yes |
| all other models | No | JSON object mode only |

So `gpt-oss-120b`/`20b` are verified for guaranteed-schema output. This corrects the earlier draft,
which marked Groq support as "verify".

### Data policy — why Groq is conditional

- Inference requests are **not retained by default**.
- Inputs/outputs may be logged for up to **30 days** only for reliability troubleshooting or abuse
  investigation; this can be turned off.
- **Zero Data Retention is available to all customers** in Data Controls; enabling it disables
  batch and fine-tuning.
- Customer data is retained in **Google Cloud Platform buckets in the United States**.
- **The reviewed policy does not state whether customer data is used to train models.** Groq serves
  third-party open-weight models and documents retention, not training use.

Under the review rule, an undocumented training policy means **not approved for resumes**. Groq can
become approvable if Groq confirms in writing (or in an official policy page) that customer content is
not used for training. Enabling ZDR is necessary but not sufficient, because ZDR governs retention
after the request, not what happens during it.

### Quota scope

Per **organization per model**. A model switch buys a separate bucket; the organization and its
account limits are shared. Multiple keys share the same limit.

## 4. Cloudflare Workers AI

Sources:
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/workers-ai/platform/limits/
- https://developers.cloudflare.com/workers-ai/platform/data-usage/
- https://developers.cloudflare.com/workers-ai/features/json-mode/
- https://developers.cloudflare.com/workers-ai/get-started/rest-api/
- https://developers.cloudflare.com/workers-ai/models/llama-3.3-70b-instruct-fp8-fast/

### Free tier

- Permanent allocation: **10,000 Neurons per day** on the Workers Free plan.
- Resets at **00:00 UTC** daily.
- Above that, Workers Paid is required ($5/month) with **$0.011 per 1,000 Neurons**.
- Some models require a paid billing method. The documented list is
  `@cf/moonshotai/kimi-k2.6`, `kimi-k2.7-code`, `@cf/zai-org/glm-5.2`, `glm-5.3`, `glm-5.3-flash`,
  `@cf/deepseek-ai/deepseek-v4-flash-0731`, `deepseek-v4.1-flash-1017`, `deepseek-v4-pro-0813`,
  `@cf/thinkingmachines/inkling-2-small`. The Llama models used below are not on that list.
- Text-generation rate limit: **300 requests/minute** per task type (Workers AI limits page).

### Cost model

Neurons are charged per token, so the daily budget is consumed by volume:

| Model | Input neurons / 1M | Output neurons / 1M | ~Cost of 4k in + 1.5k out | ~Analyses/day on 10k |
|---|---|---|---|---|
| `@cf/meta/llama-3.1-8b-instruct-fp8-fast` | 4,119 | 34,868 | ~69 | ~144 |
| `@cf/meta/llama-3.1-8b-instruct` | 25,608 | 75,147 | ~215 | ~46 |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 26,668 | 204,805 | ~414 | ~24 |
| `@cf/openai/gpt-oss-20b` | 18,182 | 27,273 | ~114 | ~88 |

### Capability verification — this is where the earlier draft was wrong

Cloudflare's JSON Mode page lists the models that support `response_format`:

`@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `@cf/meta/llama-3-8b-instruct`,
`@cf/meta/llama-3.1-8b-instruct`, `@hf/nousresearch/hermes-2-pro-mistral-7b`,
`@hf/thebloke/deepseek-coder-6.7b-instruct-awq`,
`@cf/deepseek-ai/deepseek-r1-distill-qwen-32b`.

**The `@cf/openai/gpt-oss-*` models are not on that list.** The earlier draft proposed
`@cf/openai/gpt-oss-20b` as the Cloudflare model; that was unsupported by the docs and is withdrawn.

Cloudflare also states that JSON Mode "can't guarantee that the model responds according to the
requested JSON Schema" and may return a `JSON Mode couldn't be met` error. So even a documented model
needs validation and a repair path.

Approved models (JSON Mode is the entry requirement, not an assumption):

| Model | JSON mode | Context | Function calling | ZDR | Free-plan eligible | Notes |
|---|---|---|---|---|---|---|
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Yes | **24,000 tokens** | Yes | Yes | Yes | Better quality; tight context |
| `@cf/meta/llama-3.1-8b-instruct` | Yes | verify at B2 | Yes | Yes | Yes | Cheaper, lower quality |

The 24,000-token context matters: CareerOS accepts up to 400,000 characters of extracted text. The
adapter must budget input tokens per model and must **not silently truncate the resume**. Truncating
the job description tail is acceptable with a marker; an oversized resume is a user-facing 422.

### REST contract

```
POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}
Authorization: Bearer {API_TOKEN}
{ "messages": [...], "max_tokens": 4096, "temperature": 0.2, "response_format": {...} }

200 → { "result": { "response": <string or object> }, "success": true, "errors": [] }
```

Notes that the adapter must honour:

- The response is wrapped in `result`. In JSON Mode, `result.response` can be an object; in plain
  mode it is a string.
- `max_tokens` defaults to **256** in the model parameter list. Leaving it unset truncates the JSON.
- Workers AI also exposes an OpenAI-compatible `/v1/chat/completions` endpoint. This design uses the
  native `/ai/run` endpoint because that is the one the JSON Mode documentation specifies.

### Data policy — the only approved provider

Quoted commitments from the data-usage page:

- **Zero data retention:** "For standard inference requests that do not invoke a stateful feature,
  Cloudflare does not retain inputs or outputs after they are no longer needed to process the request
  and deliver the response", subject to legal/safety exceptions.
- **No training:** "Cloudflare does not use Customer Content processed by Workers AI to train AI
  models."
- **No sharing:** content is not made available to other Cloudflare customers.
- Retained operational metadata (timestamps, token/neuron counts, latency, status) excludes content.
- Legal/safety retention, if required, is still not used for training.
- Cloudflare does not create or train the third-party models it hosts; upstream model licences still
  apply. This does not reintroduce training on Customer Content.
- No per-request region selector is documented for inference.

**Verdict: approved for `resume_pii`.** This is the strongest documented position of the five and the
only one that satisfies both "retention documented" and "no training documented".

### Quota scope — the one that shapes the router

Neurons are **account-wide and shared by every Workers AI model**. Model fallback inside Cloudflare
does not buy a fresh daily allowance. RPM is per task type across all text-generation models. The
router must treat Cloudflare as a provider-level bucket.

## 5. OpenRouter

Sources:
- https://openrouter.ai/docs/api-reference/limits
- https://openrouter.ai/docs/guides/privacy/data-collection
- https://openrouter.ai/docs/guides/features/structured-outputs

### Free tier

Free models are catalogue entries whose id ends in `:free`. Platform limits for `:free` variants:

| Credits purchased (all time) | RPM | Requests/day |
|---|---|---|
| Less than 10 | 20 | **50** |
| At least 10 | 20 | **1,000** |

Two precise readings that matter:

- The daily cap is **global across all free models** and cannot be raised with extra accounts or keys.
- The higher ceiling is triggered by **purchase history**, not by spending. Buying ≥10 credits once is
  an account-state change; it does not by itself consume money. It is still a payment, so under a
  strict free-only reading it must not be done without approval.

Operational details:

- `GET /api/v1/key` reports `free_model_daily_requests.used/limit/remaining` and
  `is_free_tier`.
- **Successful inference responses do not include `X-RateLimit-*` headers.** Only 429 responses for
  free-model/key-management limits carry them. This corrects the earlier draft, which assumed
  per-response quota headers.
- A negative account balance can block even free models.
- Upstream providers can rate-limit a specific model; OpenRouter may retry other providers of the
  same model and can fall back to models you list explicitly.

### Structured outputs — per model and per endpoint

- Supported for compatible models via `response_format` (`type: json_schema`) on
  `/api/v1/chat/completions`, or `text.format` on the Responses API.
- Support is determined **per endpoint, not just per model**: one model can be served by several
  providers and only some support structured outputs.
- To force a capable endpoint: set `require_parameters: true` in provider preferences.
- Exact free models and their endpoint support must be pinned from the live catalogue at B3. This
  document deliberately names no `:free` model.

### Data policy — why OpenRouter is conditional

- OpenRouter itself does not store prompts or responses unless you opt into private logging or into
  product-improvement use; both are off by default.
- It stores request metadata (token counts, latency), not content.
- CSAM screening applies to all traffic, including ZDR traffic.
- **Upstream provider policies still apply.** OpenRouter documents which providers may capture data
  for training and offers settings and a ZDR-only mode, but the effective policy depends on the
  endpoint that serves the request.

Unknown-at-runtime training policy means **not approved for `resume_pii` by default**. It can become
conditional if all of the following are true and verified on the account: prompt logging off,
product-improvement off, training-capable providers excluded, ZDR-only mode on, and a `:free` model
pinned to a set of endpoints whose policies are documented.

### Quota scope

Two layers: an account-wide free-request bucket (50 or 1,000/day, 20 RPM) plus per-endpoint upstream
limits. Model switching never resets the account bucket.

## 6. OpenAI

Sources:
- https://platform.openai.com/docs/pricing
- https://platform.openai.com/docs/guides/your-data

- **No free API tier is documented.** The pricing page lists paid per-token rates only; usage is
  prepaid/pay-as-you-go. Any promotional credits are temporary and classified as trial, not free tier.
- Cheapest listed text models (Standard, per 1M): `gpt-5-nano` $0.05/$0.40, `gpt-6-luna` $0.10/$0.50,
  `gpt-5.4-nano` $0.20/$1.25, `gpt-5.4-mini` $0.75/$4.50.
- Data: API data is not used to train or improve models (since 2023-03-01) unless explicitly opted in.
  Abuse-monitoring logs are retained up to 30 days by default. ZDR and modified abuse monitoring are
  available by approval. Data-residency endpoints exist.
- **Verdict: excluded** — no free tier. Privacy policy would pass; the cost model does not.

## 7. Free tier vs trial vs paid

| Provider | Permanent free | Trial credits | Paid path | Production allowed | Payment needed for free |
|---|---|---|---|---|---|
| Gemini | Yes (limited models) | Yes, temporary | Tier 1+ with billing | Yes, but free tier cannot serve EEA/CH/UK and trains on content | No |
| Groq | Yes (Free plan, rate-limited) | — | Developer plan | Yes on production models | Not documented |
| Cloudflare | Yes, 10k Neurons/day | — | Workers Paid + $0.011/1k Neurons | Yes | No |
| OpenRouter | Yes, `:free` variants | — | Any non-`:free` model | Yes, catalogue varies | No |
| OpenAI | **No** | Yes, temporary | Prepaid | Yes | Yes |

## 8. Quota vs billing — the distinction the router must encode

| Provider | Quota object | Scope | Model switch buys a new bucket? | Money at risk |
|---|---|---|---|---|
| Gemini | RPM/TPM/RPD per model | project × model | Yes | None while billing is unlinked |
| Groq | RPM/RPD/TPM/TPD per model | organization × model | Yes | None on Free plan |
| Cloudflare | **Neurons/day** | **account**, all models | **No** | None on Workers Free |
| Cloudflare | 300 RPM text generation | account × task type | No | None |
| OpenRouter | Free requests/day | **account**, all free models | **No** | None unless credits are purchased |
| OpenAI | Tiered org limits | org/project | n/a | Every request bills |

Three bucket shapes are required:

1. **`model`** — Gemini, Groq. A model change is a legitimate fallback.
2. **`account` / provider** — Cloudflare neurons and text-gen RPM, OpenRouter free requests. Once
   exhausted, skip every model of that provider.
3. **Monetary** — only reachable if `AI_FREE_ONLY=false` and a budget is configured. Not implementable
   in this stage by requirement.

Quota exhaustion is **not** a billing event. A 429 costs nothing and must never trigger a paid
escalation. Conversely, purchasing OpenRouter credits to raise a free quota is a billing event and is
therefore out of scope without explicit approval.

## 9. Privacy matrix for resume data

| Provider | Retention documented | Training documented | Human review | ZDR / control | Approved for `resume_pii` |
|---|---|---|---|---|---|
| Gemini free | Yes | **Trains** | Possible | None on free | **No** |
| Gemini paid | Yes | Does not train | Limited | DPA | Yes, but paid → excluded |
| Groq | Yes (≤30 days, opt-out) | **Not stated** | Not stated | ZDR self-serve | **No** (conditional) |
| Cloudflare | Yes (zero retention) | **No training** | Not stated | Default behaviour | **Yes** |
| OpenRouter | Yes (no storage by default) | **Per upstream provider** | Per provider | ZDR-only mode | **No** (conditional) |
| OpenAI | Yes (≤30-day abuse logs) | Does not train | Limited | ZDR by approval | Yes, but paid → excluded |

The uncomfortable, unchanged finding: **CareerOS's current production path (Gemini free) sends
resumes to a provider that documents training on the content and permits human review.** The revised
default removes that path from resume processing.

## 10. Recommended provider order after this review

1. **Cloudflare Workers AI** — the only privacy-approved free provider. Primary. Capability is
   verified; JSON quality is measured in B2.
2. **Groq** — second, only after the training-policy gap is closed in writing and ZDR is enabled.
   Production models only (`gpt-oss-120b`, `gpt-oss-20b`); preview models excluded.
3. **OpenRouter** — third, only after account-level ZDR + training-provider exclusion is verified and
   a specific `:free` endpoint is pinned. 50 requests/day makes it a floor, not a workhorse.
4. **Gemini** — retained as code and explicitly selectable, but **not** in the default resume chain.
   It returns only through a logged `AI_ALLOW_TRAINING_PROVIDERS=true` waiver.
5. **OpenAI** — **excluded**. No free tier; unreachable while `AI_FREE_ONLY=true`.

## 11. Residual research gaps

- Groq training policy: not documented on the pages read. Must be resolved before approval.
- Cloudflare: `llama-3.1-8b-instruct` context window and JSON reliability were not verified for the
  smaller model; only the 70B model page was read.
- Cloudflare JSON Mode is documented as non-guaranteed; quality must be measured in B2.
- OpenRouter free catalogue contents and per-endpoint structured-output support change; pin at B3.
- Exact Gemini free RPM/RPD for the project is only visible in AI Studio.
- Cloudflare's paid-only model list changes; re-check at B3.

## 12. Verification log (2026-11-21 → 2026-11-22)

| # | Claim | Source | Result |
|---|---|---|---|
| 1 | Gemini free-tier model list | pricing page | Confirmed: 3.5-flash-lite, 3.6-flash, 3.8-flash, 4-hydrogen free; 4-carbon/argon/neon not free |
| 2 | Gemini free tier trains on content | pricing + terms | Confirmed ("Used to improve our products: Yes" on free; Unpaid Service terms) |
| 3 | Gemini limits per project, RPD midnight Pacific | rate-limits page | Confirmed verbatim |
| 4 | Gemini free spend limit | rate-limits page | Confirmed N/A on Free |
| 5 | `gemini-3.5-flash-lite` exists, 1M context, structured outputs | models + model page | Confirmed |
| 6 | Gemini price $0.30/$2.50 | pricing page | Confirmed; note scheduled price changes on other models |
| 7 | Groq free-plan numbers | rate-limits page (Free plan tab) | Confirmed unchanged |
| 8 | Groq limits per organization | rate-limits page | Confirmed |
| 9 | Groq cached tokens exempt | rate-limits page | Confirmed |
| 10 | Groq structured output per model | structured-outputs page | Confirmed strict mode on gpt-oss-120b/20b; **earlier "verify" corrected** |
| 11 | Groq production vs preview | models page | Confirmed: gpt-oss = production, qwen3.8 = preview |
| 12 | Groq training policy | your-data page | **Not stated** → provider downgraded to conditional |
| 13 | Cloudflare free allocation and reset | pricing page | Confirmed 10,000 Neurons/day, 00:00 UTC |
| 14 | Cloudflare paid-only models | pricing page | Confirmed list; Llama not included |
| 15 | Cloudflare JSON Mode model list | json-mode page | **Corrected: gpt-oss models are not supported** |
| 16 | Cloudflare JSON Mode is best-effort | json-mode page | Confirmed |
| 17 | Cloudflare REST envelope and `max_tokens` default | rest-api + model page | Confirmed `result.response`, default 256 |
| 18 | Cloudflare context window (70B) | model page | Confirmed **24,000 tokens** |
| 19 | Cloudflare data commitments | data-usage page | Confirmed zero retention, no training, no sharing |
| 20 | OpenRouter free limits | limits page | Confirmed 20 RPM / 50 RPD / 1,000 RPD |
| 21 | OpenRouter quota headers | limits page | **Corrected: no headers on success; headers on 429; use `/api/v1/key`** |
| 22 | OpenRouter structured outputs | structured-outputs page | Confirmed per-model **and per-endpoint**; `require_parameters` |
| 23 | OpenRouter data policy | data-collection page | Confirmed no default storage but upstream-dependent → not approved |
| 24 | OpenAI has no free tier | pricing page | Confirmed no free row; paid-only rates |
| 25 | OpenAI cheapest models | pricing page | Confirmed gpt-5-nano $0.05/$0.40 and others |

## 13. Source index

| Provider | Pages read |
|---|---|
| Gemini | `ai.google.dev/gemini-api/docs/{rate-limits,pricing,models,structured-output}`, `.../models/gemini-3.5-flash-lite`, `ai.google.dev/gemini-api/terms` |
| Groq | `console.groq.com/docs/{rate-limits,models,structured-outputs,your-data}` |
| Cloudflare | `developers.cloudflare.com/workers-ai/{platform/pricing,platform/limits,platform/data-usage,features/json-mode,get-started/rest-api,models/llama-3.3-70b-instruct-fp8-fast}` |
| OpenRouter | `openrouter.ai/docs/api-reference/limits`, `.../guides/privacy/data-collection`, `.../guides/features/structured-outputs` |
| OpenAI | `platform.openai.com/docs/{pricing,guides/your-data}` |
