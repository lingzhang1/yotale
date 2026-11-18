# Billing V1, Phase B0: cost attribution and provisional unit economics

Status: **B0 IMPLEMENTED offline on `feat/cost-logging-all-ai-handlers` (2026-11-18). Not merged, not deployed, no live inference, no
AWS change.** Builds on `billing-measured-cost-dev-beta.md` (measured data) and feeds `billing-v1-spec.md` (B1).

## 1. What B0 delivers

| Requirement | Status |
|---|---|
| `model_call_usage` for every capability (AU, Coverage, Guide, AI Idea, Creative Intent, Duration, Music Plan, EditPlan) | **Done.** One line per billed provider attempt at the OpenAI/Gemini adapter seam. |
| `story_user_id` on each line | **Done** (API: request middleware; worker: per-job context). |
| `story_id`, when available | **Done, optional by design.** Set where a request body already carries a story id: coverage, coverage v2, guide v2, guide refine, edit plan, music plan (handler) and worker jobs (job body). **AU, creative intent, duration, scene understanding and AI Idea intentionally carry none.** A Moment can belong to several Stories, so per-account Moment cost is the authoritative source cost; per-Story attribution of it is not meaningful and no `story_id` is added to AU requests for reporting. |
| operation type | **Done.** `operation` = `METHOD /route` on the API; `worker:edit_plan:<original|explore|revise>` or `worker:coverage_v2` in the worker. |
| served provider/model, input/output/thinking tokens | **Done** (`provider`, `model_id`, `input_tokens`, `output_tokens`, `reasoning_output_tokens`, `billed_output_tokens`). |
| actual model-call count | **Done.** `call_index` = nth billed attempt within the request/job. Sum per `job_id`. |
| estimated cost | **Done** (`estimated_cost_usd`, `pricing_known`, `pricing_version`). Gemini thinking tokens billed as output. |
| job/attempt id | **Done.** `job_id` (worker), `attempt` (provider attempt within one call), `correlation_id` (API request). |
| retry and failure metadata | **Done.** `outcome` (`ok`, `no_tool_call`, `truncated`, ...), `finish_reason`, `attempt`. A failed provider call with no usage reports no tokens, so it logs nothing (nothing billable is visible). |
| No private media, signed Apple transactions, credentials | **Verified by test** (`test_no_prompt_media_or_user_fields_are_logged`; scrubber leaves the attribution ids intact). |

Context mechanism: a `ContextVar` in `packages/model_gateway` (`set_call_context`, `call_context`). No engine signature changed.
The API middleware `apps/api/app/cost_context.py` is registered innermost. The worker wraps each job in `call_context(...)`.

Distinguishing provider-reported from estimated from unmeasured spend:
- **Provider-reported tokens, estimated USD:** every `model_call_usage` line. USD is tokens x list price, never the provider invoice.
- **Unmeasured:** S3 egress, evidence-package storage (reusable-evidence persistence is ON in dev and beta per `release/release.json`, so this is a real, unmeasured cost), music provider fees (no contract), fixed AWS infra, Cognito.
- **Retries are not double counted:** each provider attempt is one line with its own tokens. Aggregate with `sum(estimated_cost_usd)` grouped by
  `job_id` or `correlation_id`; do not add the older `bedrock_usage`, `asset_understanding_resolved`, `director_resolved` lines (same calls).

Aggregation query (Logs Insights, API and worker log groups):

```
filter message = "model_call_usage"
| stats count(*) as attempts, sum(estimated_cost_usd) as usd, max(call_index) as calls
  by story_user_id, story_id, operation
```

### Remaining measurement gaps

1. Nothing is deployed, so `model_call_usage` has no production data yet. Coverage, guide, creative intent, duration, music plan,
   interpret-revision and scene-understanding costs remain **unmeasured** until a deploy and a week of use.
2. Per-Story attribution is optional and absent for AU and the Moment-level calls (see above). Per-account cost per Moment is authoritative; per-Story figures derived from the optional field are indicative only.
3. Gemini thinking tokens were never logged before; AU cost in all historical data is a **lower bound**.
4. S3 egress, evidence storage, music provider cost and non-per-user AWS cost are not measured.
5. Failed-attempt cost with no usage metadata (transport errors) is invisible.

## 2. Measured inputs (Nov 17-18, edit_plan/5.6, gpt-5.1 + gemini-3.8-flash)

- AU: about 30.2k input / 640 output tokens per call, **$0.0107 per call**; Iceland used 95 calls for 90 moments ($0.0113 per moment).
- EditPlan 5.6, one model call: input tokens fit **5,454 + 827 per sheeted moment** (10 retained jobs, both accounts). Output 1.9k to 6.1k.
  Measured costs: 21 sheets $0.048; 30 to 34 sheets $0.054 to $0.076; 68 sheets $0.129 to $0.134; 89 sheets $0.126 to $0.168; text-only revise $0.071.
- Iceland, 90 moments, import + Highlights + Full Story + revise: **$1.406 measured** (lower bound).
- S3 media: beta 5.4 GB ($0.12/month at list price) for the heaviest user.

## 3. Workload costs (AI only, USD)

Produced by `scripts/billing_unit_economics.py` (stdlib, reproducible). "Model" rows apply the measured fit; they are not measurements.

| Workload | Cost | Basis |
|---|---|---|
| 1. 10-Moment Story, one video | $0.17 | model |
| 2. 30-Moment Story, two videos + one revise | $0.56 | model; revise measured n=1 |
| 3. 90-Moment Story, three outputs (Iceland) | **$1.41** | **measured**, lower bound |
| 4a. 30 reused Moments, five more versions | $0.36 | model |
| 4b. 90 reused Moments, five more versions | $0.67 | model; 89-sheet explores measured $0.13 to $0.17 each |
| 5a. Workload 2 with 1.25x retry factor | $0.70 | **simulation** |
| 5b. Workload 2 with 1.9x (pre-5.6 observed calls per job) | $1.06 | **simulation** |

Failed and retry-heavy: a failed generation still bills its tokens while the credit is released. Pre-5.6 original jobs averaged 1.5 to 1.9
model calls; 5.6 jobs since Nov 17 averaged 1.0. The 1.25x factor is an assumption, not an observed failure rate.
AU retry cost is small: 5 retryable failures in 633 AU attempts on beta (0.8%).

## 4. Provisional unit economics

Assumptions (all flagged, none measured): unmeasured components add **$0.10 per video**, retry factor **1.25x**, storage **$0.15** per user-month.
Revenue is the provisional $9.99. "Margin" is gross margin on AI plus storage only (no App Runner, Lambda, Cognito, music fees).

### Free starter (30 Moments + 2 videos, no revenue)

| Videos made from | Measured-model cost | With retry 1.25x and $0.10/video buffer |
|---|---|---|
| 10-sheet stories | $0.45 | $0.76 |
| 30-sheet stories | $0.49 | $0.81 |
| 90-sheet stories | $0.62 | $0.97 |

A fully used starter allowance costs **about $0.45 to $1.00** per user in AI spend.

### Plus $9.99/month at full allotment (100 Moments + 12 videos)

| Case | AI cost | Total cost | Net after 15% | Margin | Net after 30% | Margin |
|---|---|---|---|---|---|---|
| 12 videos on 30-sheet stories | $3.73 | $3.88 | $8.49 | **54%** | $6.99 | **45%** |
| 12 videos on 90-sheet stories | $4.66 | $4.81 | $8.49 | **43%** | $6.99 | **31%** |

Sensitivity (large stories, full allotment), margin at 15% / 30% commission:

| Retry factor | Unmeasured $/video | Total cost | Margin 15% | Margin 30% |
|---|---|---|---|---|
| 1.00x | $0.00 | $2.92 | 66% | 58% |
| 1.00x | $0.10 | $4.12 | 52% | 41% |
| 1.25x | $0.10 | $4.81 | 43% | 31% |
| 1.25x | $0.30 | $7.21 | 15% | -3% |
| 1.90x | $0.10 | $6.61 | 22% | 6% |
| 1.90x | $0.30 | $9.01 | -6% | -29% |

### Assessment of the provisional allowances

- **100 Moments + 12 videos at $9.99 is viable but thin in the pessimistic corners.** Expected margin is 43% to 54% at the 15% Apple rate and
  31% to 45% at 30%. It turns negative only if unmeasured components cost $0.30 or more per video together with heavy retries.
- **Asset analysis is the largest single cost.** 100 Moments is $1.13 of AU alone. A 90-Moment story uses 90% of a month's analysis allowance.
- **The unmeasured $0.10 per video is the biggest unknown.** Coverage jobs run about 2.6 times per video on beta. The real figure is only known
  after `model_call_usage` ships. Do not fix the allowances before that data exists.
- **A 70% margin needs about 6 large-story videos per month** at this cost, not 12 (see script output). Reaching 12 requires a lower per-video cost
  (cheaper unmeasured components, fewer retries) or a higher price. This is a decision for you, not a change made here.
- Prices and allowances stay configuration-driven (`packages/billing` config) and provisional.

## 5. Owner actions to complete B0

1. Approve a **dev** deploy of this branch so `model_call_usage` starts collecting (no deploy has been done).
2. After about a week of real use, re-run the aggregation query and `scripts/billing_unit_economics.py`, replace the three assumptions with measurements.
3. Pull OpenAI and Google billing exports for the same window to reconcile list-price estimates against invoices.
