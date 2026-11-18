# Billing input: measured AI cost per component and per video (dev + beta, real data)

Status: **MEASURED 2026-11-18 (read-only).** No deploy, no live inference, no data mutated. Companion code change
(per-call token/cost logging for every capability) is on `feat/cost-logging-all-ai-handlers`, **not deployed**.
This is the cost-of-goods input for the external-user billing plan (free trial + paid plans). It is **not** a
pricing decision.

Supersedes the single-session sample in `docs/architecture/billing/per-video-cost-and-pricing-inputs.md`
(branch `docs/billing-per-video-cost`, 2026-11-02, n=7 edit-plan ops on beta). Same method, wider sample, both
accounts, plus an audit of what the accounting does NOT see.

## 1. Sources and method

| Source | Account | Used for |
|---|---|---|
| `/aws/lambda/story-<env>-edit-plan-worker` `bedrock_usage` (Logs Insights) | dev `989088054552`, beta `224033508028` | edit-plan cost per job (op_type, model, tokens) |
| App Runner application log `asset_understanding_resolved`, `director_resolved` | both | AU and AI Ideas tokens per call |
| App Runner application log, count of `*_resolved` / `*_submitted` events | both | call counts per capability |
| `story-<env>-user-usage` (DynamoDB scan) | both | quota ledger: settled USD, per-reservation markers |
| `story-<env>-edit-plan-jobs` | both | retained job rows (TTL: only 24 dev / 13 beta rows survive) |
| CloudWatch `AWS/S3` BucketSizeBytes / NumberOfObjects | both | media storage |

Every token count was **re-priced** with the current `_DEFAULT_PRICING` (`beta-pricing/2026-11-01-direct-providers`),
not the cost logged at the time. Older log lines priced gpt-4o at $0.00.

Window for "current routing" figures: **2026-11-01 onward**, when planning runs on `gpt-5.1` and asset
understanding on `gemini-3.8-flash` (`STORY_MODEL_PROVIDER=direct`). Earlier October data used Bedrock
Opus/Sonnet and is shown separately.

## 2. Measured components (current routing, Nov 1+)

| Component | Beta | Dev |
|---|---|---|
| Edit plan, original | **$0.136** avg (n=13, 2.1 model calls, max $0.334) | $0.046 avg (n=77, max $0.276) |
| Edit plan, explore | $0.087 avg (n=14) | $0.073 avg (n=27) |
| Edit plan, revise | $0.086 avg (n=6) | $0.046 avg (n=9) |
| Edit plan, all | **$0.106** avg; $3.50 total (n=33) | $0.053 avg; $5.96 total (n=113) |
| Asset understanding (per call) | **$0.0107** (n=439; about 30,200 in / 640 out tokens) | $0.0107 (n=196) |
| AI Ideas director (per call) | $0.024 (n=17) | $0.023 (n=16) |
| **Measured total** | **$8.60 / 33 videos** | **$8.42 / 113 videos** |

A "video" here is one edit-plan job (original, explore or revise). Asset understanding is charged once per imported
moment, not per video.

### Correction: dev vs beta is not like-for-like until synthetic traffic is removed

The dev column above includes **58 edit-plan "original" jobs from the legacy `dev` principal on 2026-11-10/11**
(about 10k input tokens, 3 model calls each, about $0.01 per job). That is automated test or load traffic, not
real clips. It pulled the dev average down. Restricting both environments to the owner's real user
(dev `854abd33`, beta `61310227`) gives:

| Real user only (Nov 1+) | Beta | Dev |
|---|---|---|
| Original | $0.130 avg (n=12, median input 51.8k tok, 1.9 calls) | $0.123 avg (n=19, median input 80.7k tok, 1.5 calls) |
| Explore | $0.088 (n=12) | $0.073 (n=27) |
| Revise | $0.086 (n=6, 1.7 calls) | $0.046 (n=9, 1.4 calls) |
| All | **$0.104** avg, $3.13 total | **$0.086** avg, $4.72 total |

Remaining variance is mostly planner input size (moment count per story, 19k to 200k tokens) and the number of
model calls per job (1 versus 3 when a repair or critique pass runs); both vary job to job even on the same
footage. Revise has the smallest samples, so treat its gap as noise until more data exists.

Asset-understanding call counts also differ (beta 439, dev 196) for a reason that is not the same-clips effect:
the AU log has no user id, but the beta ledger shows a second user active on 2026-11-08 (85 generations, owner had
none that day) while beta AU logged 61 calls that day. At least part of beta's AU volume is another user's imports.
Per-call AU cost is identical ($0.0107). The `model_call_usage` logging should carry a user id to settle this.

### Per video

| | Beta | Dev |
|---|---|---|
| Edit plan | $0.106 | $0.053 |
| Asset understanding, amortized | $0.138 (about 13 AU calls per video) | $0.019 (about 1.7) |
| AI Ideas, amortized | $0.012 | $0.003 |
| **Measured total** | **about $0.26** | **about $0.07** |

The AU amortization depends on how many versions a user makes from the same moments. With many versions per story
the per-video cost tends toward the edit-plan cost alone, about $0.05 to $0.14.

### Legacy routing (October, not representative)

Bedrock Opus 4.6 edit plans cost $0.58 to $0.79 per job; Sonnet AU about $0.038 per call. Retired.

## 3. NOT measured (before the logging change in this PR)

No token or cost line existed for these, so their spend is invisible in the backend:

| Capability | Calls per beta video (Nov 1+, 34 videos) |
|---|---|
| Coverage v2 jobs | 2.6 |
| Story guide v2 | 1.4 |
| Duration recommendation | 0.94 |
| Music plan | 0.82 |
| Interpret revision | 0.8 |
| Creative intent | 0.65 |
| Scene understanding | 0.56 |
| Music candidates / soundtrack link (Epidemic) | 1.6 / 2.1 |
| Reference images (Unsplash/Pixabay) | 3.9 (free) |

Unmeasured AI cost per video is **unknown**. An unverified guess of $0.01 to $0.10 per call would add roughly
$0.05 to $0.50 per video; treat it as an assumption, not data. Epidemic per-call cost depends on a contract that does
not exist yet (see `milestone-md-music-sourcing-research-brief.md`).

## 4. The quota ledger is not real cost

`story-<env>-user-usage` settles **flat estimates**, not actuals. No sync handler sets `request.state.quota_actual_usd`
(`apps/api/app/quota_gate.py` falls back to the reserve estimate), and the worker settles separately. Retained
reservation markers:

| | `settled` $0.05 | `settled` $0.01 | `settled` $0.15 |
|---|---|---|---|
| dev (1,111 markers) | 476 | 396 | 114 |
| beta (497 markers) | 273 | 158 | 40 |

Beta November ledger: $38.27 settled, against $8.60 measured plus unmeasured. That is about $1.13 per video in the
ledger versus about $0.26 measured. Use the ledger as a rough guardrail, never as a pricing input. The earlier
"about $0.12 per generation" figure (`b0-p0sec-beta-acceptance-report.md`) came from this ledger in the Opus era.

## 5. Other costs

- **S3 media (storage only):** beta 5.4 GB / 312 objects (about $0.12/month at $0.023/GB-month); dev 30.9 GB / 876
  objects (about $0.71/month). Transfer/egress not measured.
- **Cognito:** about $0.015 per monthly active user (`milestone-p0-beta-auth-identity-job-ownership.md`).
- **App Store fee:** 15% (Small Business Program) or 30%.

## 6. Accuracy caveats

1. **Gemini AU is a lower bound.** Gemini `candidatesTokenCount` excludes thinking tokens, which are billed at the
   output rate, and the AU log does not record them. OpenAI `completion_tokens` already includes reasoning, so
   gpt-5.1 figures are not affected.
2. Prices are list-price estimates in `_DEFAULT_PRICING`; confirm against provider billing before pricing a plan.
3. Small samples: 33 beta edit-plan jobs, one user ran most of them. Failed and retried attempts bill; the
   `bedrock_usage` line is logged once per job and includes retries/repairs, AU lines are per successful call.
4. Worker log retention is 60 days on the beta log group; job table rows are TTL'd, so older data is partial.

## 7. Code change: per-call usage logging (this PR)

Every capability reaches OpenAI/Gemini through two adapters, each already building one `make_attempt` record per
provider attempt. `packages/model_gateway/__init__.py::log_model_call` now emits one `model_call_usage` log line from
that seam for **every billed attempt of every capability**, including repair, truncation and no-tool-call attempts.

Fields: `task` (e.g. `story_guide.v2`), `provider`, `model_id`, `attempt`, `outcome`, `latency_ms`, `input_tokens`,
`output_tokens`, `reasoning_output_tokens`, `billed_output_tokens`, `estimated_cost_usd`, `pricing_known`,
`pricing_version`. No prompts, media, GPS or user ids. Gemini billed output = output + thinking tokens, which also
closes the AU lower-bound gap above. Best-effort; a logging failure never breaks a model call.

Tests: `packages/model_gateway/test_model_call_usage.py` (7). Full `apps/api/tests` + `packages` suites pass.

**Do not add `model_call_usage` to the existing `bedrock_usage`, `asset_understanding_resolved` or
`director_resolved` totals.** They describe the same calls; `model_call_usage` is the authoritative per-call line
once deployed, the others stay for continuity.

Not in this change (decisions for later): attributing calls to `story_user_id` (needs a request-scoped context),
and settling real cost in the quota ledger via `quota_actual_usd`.

## 8. Follow-up queries (after deploy)

Logs Insights on the API log group and the worker log group:

```
filter message = "model_call_usage"
| stats count(*) as calls, sum(estimated_cost_usd) as usd by task, model_id
```

## 9. Implications for the billing plan

- Plan on **measured** cost, not the ledger. Measured beta cost is about $0.26 per video before unmeasured components.
- Re-measure after this logging is deployed, then set credit size and prices from the full per-video cost.
- Asset understanding is a capture-time cost; a credit that covers only video creation leaves it uncovered, so the
  USD cap stays as a backstop.
- Epidemic commercial terms remain the largest unknown for any paid plan.
