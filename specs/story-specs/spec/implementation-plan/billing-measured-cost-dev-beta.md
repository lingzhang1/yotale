# Billing input: measured AI cost per component and per video (dev + beta, real data)

Status: **MEASURED 2026-11-18 (read-only).** No deploy, no live inference, no data mutated. Companion code change
(per-call token/cost logging for every capability) is on `feat/cost-logging-all-ai-handlers`, **not deployed**.
This is the cost-of-goods input for the external-user billing plan (free trial + paid plans). It is **not** a
pricing decision.

Supersedes the single-session sample in `docs/architecture/billing/per-video-cost-and-pricing-inputs.md`
(branch `docs/billing-per-video-cost`, 2026-11-02, n=7 edit-plan ops on beta). Same method, wider sample, both
accounts, plus an audit of what the accounting does NOT see.

## 0. Current configuration (verified 2026-11-18) versus the historical data below

Several figures in this document and in older milestone reports were measured under configurations that no longer apply. Current values,
from `release/release.json` and CDK (not from older reports):

| Setting | Historical (older reports) | Current |
|---|---|---|
| Planner | Opus 4.6 (October), `edit_plan/5.3` | `edit_plan/5.6`, time-boxed owner-approved pin in **development and beta** until 2026-11-30 |
| Providers | Bedrock Anthropic | `STORY_MODEL_PROVIDER` removed; OpenAI `gpt-5.1` (plan, guide, coverage, ...) and Gemini `gemini-3.8-flash` (AU); Bedrock/Anthropic routing is disabled in code |
| Beta quota posture | observe, $5 to $8 per user (B0 Phase 4 design) | **enforce**, $50 per user per month, 500 gens per day, 2 active jobs, $60 global (`quota_mode`, `user_monthly_usd` in release.json; CDK defaults) |
| Evidence persistence | off (P1-F design) | **on** in development and beta (`evidence_persist: "1"`); stored evidence is therefore a real, unmeasured storage cost |
| Sign-up | invite-only (Cognito email OTP milestone) | Cognito `selfSignUpEnabled: true` in CDK; the **development** pool has `AllowAdminCreateUserOnly=false` and no pre-sign-up trigger (live check). The **beta** pool was not live-checked (SSO session expired); it is built from the same CDK. `IdentityStore` marks every first sign-in `beta_access_status=invited`, which is admitted. Effective behaviour: anyone who can complete email OTP sign-up gets in. |

Everything below this section reports data from the stated windows; read it against this table.

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

### Re-query: only data after the edit-plan 5.6 pin (from 2026-11-17 00:07 PST = 08:07 UTC)

Cutoff is the owner-stated "Nov 17, 12:07 AM"; commits are timestamped PST, and the beta 5.6 pin merged at
00:01 PST on 2026-11-17, so 12:07 AM is read as PST. Retained job rows after the cutoff all show
`prompt_version = edit_plan/5.6` (dev 10 completed + 1 failed, beta 5 completed). Both environments, real user only
(dev `854abd33`, beta `61310227`), `gpt-5.1`, current prices. Queried 2026-11-18.

| After cutoff | Beta | Dev |
|---|---|---|
| Original | **$0.079** avg (n=6, median input 29.1k tok, 1.0 calls) | $0.113 avg, $0.072 median (n=5, max $0.276) |
| Explore | $0.101 (n=3) | $0.071 (n=5) |
| Revise | no jobs | $0.015 (n=2, one logged 0 tokens) |
| **All edit plans** | **$0.086 avg**, $0.072 median, $0.78 total (n=9) | **$0.079 avg**, $0.048 median, $0.95 total (n=12) |
| Model calls per job | 1.0 | 1.0 |
| Asset understanding | 95 calls, $1.02 ($0.0107 each) | 0 calls (no new imports; all cache hits) |
| **Measured per video** | **about $0.20** (edit plan $0.086 + AU $0.113 amortized over 9 videos) | **about $0.08** (edit plan only) |

Versus the earlier real-user window (Nov 1 onward): beta all-edit-plan $0.104 to $0.086, dev $0.086 to $0.079.
Model calls per job fell to 1.0 (previously 1.5 to 1.9) and beta median input fell from 51.8k to 29.1k tokens.
Samples are small (9 and 12 jobs), so the improvement is directional, not proven.

Unmeasured-component call counts after the cutoff (beta / dev): coverage jobs 15 / 16, story guide v2 7 / 6,
music plan 9 / 10, duration 6 / 5, creative intent 4 / 5. No token cost exists for these yet (section 3).

### Case study: one beta story, "Iceland" (90 moments), 2026-11-18

Story `BA07A414-B660-4DD6-97EC-8C7952686B37`, user `61310227`, created 07:49:41 UTC. Everything below is logged
between that time and 08:33 UTC: assets imported, then Highlights original, another version as Full Story, and a
revise. All three plans ran `edit_plan/5.6` on `gpt-5.1`, 1 model call each, 0 repairs.

| Step | Time (UTC) | Mode | Input / output tokens | Cost |
|---|---|---|---|---|
| Asset understanding, 95 calls for 90 moments (`gemini-3.8-flash`, about 30.2k in / 640 out each) | 07:51 to 08:15 | one-time import | n/a | **$1.019** ($0.0113 per moment) |
| Original, Highlights | 08:17 | multimodal, 89 sheet images | 69,463 / 6,101 | **$0.148** |
| Another version, Full Story | 08:24 | multimodal, 89 sheet images | 89,186 / 5,659 | **$0.168** |
| Revise | 08:32 | text only | 23,653 / 4,151 | **$0.071** |
| **Measured total** | | | | **$1.406** |

- Edit plans total $0.387 for three videos, about $0.13 each. Asset understanding is 72% of the measured total.
- Marginal cost of one more version from the same moments is $0.07 to $0.17. Import is a one-time cost per story.
- Not measured for this story (counts only): 6 coverage job submissions (5 completed), 2 story guide v2, 2 music plan,
  1 duration recommendation, 1 creative intent, 3 music candidate lookups and 3 soundtrack links, 3 reference images.
  No token cost exists for these (section 3), so $1.406 is a **lower bound**; asset understanding is also a lower
  bound because Gemini thinking tokens are not in the AU log.

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

Not in this change: settling real cost in the quota ledger via `quota_actual_usd`. User attribution has since been added
(see `billing-b0-cost-attribution-and-unit-economics.md`).

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
