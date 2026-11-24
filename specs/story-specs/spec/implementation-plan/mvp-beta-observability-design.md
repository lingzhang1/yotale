# P0 Beta Observability — CloudWatch Metrics, Dashboards & Alarms (Design)

**Status:** DESIGN + PROPOSAL (Phases 0–6). No code changed; NO infrastructure provisioned or changed;
nothing deployed. STOP at owner approval before provisioning/changing production infrastructure.
**Date:** 2026-10-18
**Owner decision:** CloudWatch observability is a MANDATORY external-beta release gate (not optional
polish). Integrate with the auth/quota/production-readiness beta milestone
(`mvp-beta-readiness-assessment.md`). This design REVISES that milestone's "~1 day monitoring" line
upward (see Phase 5 effort).

---

## Phase 0 — Existing telemetry audit (what's already there)

**Reusable — structured logging ALREADY exists** (keyed `log.info("<event>", {fields})`, App Runner +
Lambda → CloudWatch Logs). Named events found in `apps/api/app`:
- `edit_plan_generated`, `edit_plan_job_submitted`, `coverage_job_submitted`, `story_coverage_resolved`,
  `story_coverage_v2_*`, `story_guide_resolved`, `music_direction_inferred`, `music_plan_generated`,
  `duration_recommendation_done`, `music_candidates_ranked`, `music_search_page`, `music_soundtrack_link`,
  `interpret_revision_ok` — each carries `latency_ms`.
- `worker_plan_diag` (worker): `model_calls`, `repairs` (`executability_repairs_used`), `any_fallback`,
  `first_fallback_error`, `first_pass_executable`, `revision_path`, `calls`.
- Per-endpoint `latency_ms` on ~20 handlers.

**Reusable infra (CDK `story-api-stack.ts`):** DynamoDB `EditPlanJobsTable` (job lifecycle + TTL), SQS
`EditPlanJobsQueue` + **DLQ `EditPlanJobsDLQ` (maxReceiveCount=2, 14-day retention)**, Lambda
`EditPlanWorker` (reservedConcurrency=2, batchSize=1), App Runner `CfnService`. These emit **free AWS
service metrics** (SQS `ApproximateAgeOfOldestMessage`/`ApproximateNumberOfMessagesVisible`, DLQ depth,
Lambda `Errors`/`Throttles`/`Duration`/`ConcurrentExecutions`, App Runner `5xx`/`RequestLatency`,
DynamoDB throttles) — prefer these over custom metrics wherever possible.

**Missing (confirmed gaps):**
- **No EMF / custom CloudWatch metrics, no Metric filters, no Dashboard, no Alarms, no SNS, no Budget** in
  CDK (grep = zero).
- **No per-generation cost** (tokens captured in-engine — `input_tokens`/`output_tokens` in edit/duration/
  asset engines — but NOT forwarded into the worker's published diag or any log line).
- **No queue-wait metric** (no enqueue/dequeue timestamp).
- **No device/iOS telemetry** (MediaEngineV1 has zero timing; no client event pipe).
- **No explicit log retention** set on the log groups (App Runner/Lambda defaults — a privacy + cost gap).
- No auth/authz/quota events (those surfaces don't exist yet — they arrive with the auth milestone).

**Principle:** extend the existing structured events; emit metrics via **CloudWatch EMF**
(Embedded Metric Format — a specially-shaped JSON log line becomes a metric, no extra API call, no added
latency). Do NOT duplicate a free AWS service metric with a custom one.

## Phase 1 — Structured logging schema

One canonical JSON envelope for every backend event (extend, don't replace):

```
{ "ts": iso8601, "env": "dev|prod", "service": "api|worker",
  "event": "<name>", "op_type": "original|another_version|revision|coverage|music_plan|...",
  "correlation_id": "<operation_id>",        // request/job correlation — LOG only, NEVER a metric dimension
  "job_id": "<uuid>", "job_state": "submitted|planning|plan_ready|rendering|saved|failed|expired",
  "model_id": "<bedrock id or none>",
  "stage": "coverage|guide|duration|edit_plan|repair|critique|music_plan",  // LOGICAL model stage
  "provider_attempt": 1,                      // PHYSICAL Bedrock invocation # (fallback => 2)
  "error_category": "throttle|quota|validation|provider|transport|none",
  "latency_ms": int, "input_tokens": int, "output_tokens": int,
  "fallback": bool, "throttled": bool,
  "owner_sub": "<principal>" }                // added with the auth milestone; hashed if needed
```

Rules enforced:
- **Logical stage ≠ physical invocation:** `stage` is the logical step; `provider_attempt` counts real
  Bedrock calls (a fallback is stage=edit_plan, attempt=2). This separation is what makes "3 model calls
  for 1 generation" legible.
- **Never logged:** raw contact sheets, user instruction text, precise GPS, credentials, personal media.
  (Contact sheets already stay in S3, never in logs; GPS is device-side and never sent to the API.)
- **correlation_id** is for troubleshooting joins only — never a metric dimension (cardinality).
- **Retention + access:** set log-group retention explicitly (proposal: 30 days dev, 90 days prod) via
  CDK; restrict log read to the ops role.

## Phase 2 — CloudWatch custom metrics (via EMF; low-cardinality dims only)

Dimensions allowed: `env`, `service`, `op_type`, `stage`, `error_category`, `model_id`. NEVER
`correlation_id`/`job_id`/`owner_sub` as dimensions.

**Product** (emit from api/worker EMF):
- `GenerationStarted` / `GenerationCompleted` / `GenerationFailed` (count, dim op_type)
- `OperationSuccessRate` (derived: completed / started)
- `TimeToPlayableVideo` (client-reported, see Phase 3 — distinct from backend planning)
- `GenerationCancelled`, `GenerationRecovered`
- `DuplicateInferencePrevented` (count — the payload-fingerprint idempotency already fires)

**AI:**
- `ModelInvocations` (dim model_id, stage), `InputTokens` / `OutputTokens` (dim model_id)
- `EstimatedModelCostUSD` = tokens × a CDK-config pricing table (dim model_id) — NEW; needs tokens
  surfaced out of the engine into the worker diag first
- `ModelLatencyMs` (dim stage, model_id), `BedrockThrottles` (dim model_id),
  `ModelFallbacks` (dim model_id), `RepairCount`, `CritiqueCount`

**Async jobs** (prefer free SQS/Lambda metrics; custom only where absent):
- `QueueWaitMs` — NEW (needs enqueue ts on the message → dequeue delta in worker)
- `WorkerProcessingMs` (worker wall), `JobCompletionLatencyMs` (submit→plan_ready)
- `JobFailed` / `JobExpired` (dim error_category); DLQ depth + queue age = **free SQS metrics**
- `JobReconciled` / `JobRecovered` (the recovery path)

**Security & quota** (arrive with the auth milestone — schema defined now):
- `AuthFailures`, `AuthorizationDenials` (dim reason: no_token|bad_token|not_owner)
- `QuotaConsumed`, `QuotaDenials`, `RateLimitDenials`
- `ActiveUsers` (daily unique — bounded), `GenerationsPerUserDay` (histogram-ish via statistics)

## Phase 3 — iOS telemetry

A **best-effort, non-blocking** client event pipe (a batched POST to a new `/v1/telemetry` ingest, or
CloudWatch RUM if preferred). Events, each carrying the `operation_id` so they JOIN backend logs:
- `tap_to_submit_ms` (user tap → job submit), `contact_sheet_ms` (extract + upload),
  `planning_observed_ms` (submit → device sees plan_ready), `render_start`/`render_end_ms`,
  `export_ms` + `export_failed`, `first_playable_ms` (the true tap-to-playable), `recovery_after_background`.
Design constraints (owner): intermittent connectivity tolerated (local queue + bounded retry);
**duplicate-event dedup by a client event-id**; **telemetry delivery is NEVER on the create path** — a
dropped telemetry event never affects Story creation. No PII in client events (no GPS, no instruction text).

## Phase 4 — Dashboards (CDK/IaC, not manual)

Four `cloudwatch.Dashboard`s defined in CDK:
1. **Product & Generation Health** — started/completed/failed, success rate, cancellation/recovery,
   duplicate-prevention; **TimeToPlayableVideo (client) side-by-side with backend JobCompletionLatency**,
   explicitly labeled so client time is never confused with planning time; p50/p95.
2. **AI Usage/Latency/Throttling/Cost** — invocations + tokens + EstimatedModelCostUSD by model_id;
   ModelLatency p50/p95 by stage; throttles + fallbacks; repair/critique counts.
3. **Infra & Async Queue Health** — SQS depth + ApproximateAgeOfOldestMessage, DLQ depth, Lambda
   Errors/Throttles/Duration/Concurrency, App Runner 5xx/RequestLatency, DynamoDB throttles (mostly free metrics).
4. **Auth, Quota & Beta Usage** — auth failures, authz denials, quota consumption/denials, rate-limit
   denials, active users, generations/user/day.

## Phase 5 — Alarms (+ budgets), low-noise

CDK `cloudwatch.Alarm`s → one SNS topic → **owner-approved destination** (email/Slack — owner provides):
| Alarm | Metric | Threshold / window |
|---|---|---|
| DLQ non-empty | SQS DLQ `ApproximateNumberOfMessagesVisible` | ≥1 for 1 datapoint / 5 min |
| Queue backlog/age | `ApproximateAgeOfOldestMessage` | > 5 min for 2 of 3 × 5 min |
| Lambda failures | Lambda `Errors` | ≥ 3 in 5 min |
| Lambda timeouts | `Duration` p99 near limit OR timeout errors | sustained 2 × 5 min |
| App Runner 5xx | `5xxStatusResponses` | > 2% of requests, 2 × 5 min |
| Generation failures | `GenerationFailed` rate | > 20% of started, 2 × 10 min (low-volume safe) |
| Bedrock sustained throttling | `BedrockThrottles` | > N/5 min sustained 15 min (not a single spike) |
| Quota enforcement failure | `QuotaDenials` anomaly OR quota-check error | error > 0 |
| Abnormal cost | `EstimatedModelCostUSD` daily sum | > owner budget line |
| Unauthorized-access anomaly | `AuthorizationDenials` (not_owner) | > N/5 min (possible probing) |
| **AWS Budget** | real billing | monthly budget + 50/80/100% actual-spend alerts |

Noise control: multi-datapoint evaluation windows, percentage-of-volume (not raw count) where low-volume,
one SNS topic, no per-request alarms.

## Phase 6 — Acceptance (dev-only, safe fault injection)

1. Successful create → appears in Product dashboard. 2. Failed gen → classified by error_category.
3. **Simulated Lambda failure** (dev flag throws) → Lambda-failure alarm. 4. **Hand-put a DLQ message** →
DLQ alarm. 5. Throttle visible (from the existing fallback path; do NOT exhaust real quota — inject a
synthetic ProviderError). 6. Quota denial visible (dev quota=0). 7. **Unauthorized job access** (fetch a
job as a different principal) → 403 + `AuthorizationDenials` recorded. 8. Client render failure
distinguishable from backend success (backend JobCompleted but client export_failed). 9. EstimatedModelCost
recorded. 10. Dashboard shows recovery after backgrounding. 11. Alarm notification reaches the recipient.
12. Log scrub test: assert no contact sheet / instruction / GPS / credential in a sample log.
**Constraints:** safe dev-only injection; never deliberately exhaust Bedrock quota or trigger expensive
production failures.

## Deliverables summary

- **Telemetry architecture:** extend existing structured logs → EMF metrics (no extra API latency) +
  free AWS service metrics + a best-effort non-blocking iOS event pipe; 4 CDK dashboards; CDK alarms →
  SNS → owner destination; AWS Budget.
- **Schemas:** the Phase-1 log envelope + the Phase-2 metric catalog (names + bounded dims) above.
- **CDK changes:** log-group retention; EMF metric emission (code, not infra); 4 Dashboards; ~11 Alarms +
  1 SNS topic + Budget; (telemetry ingest endpoint if not using RUM).
- **Cost estimate:** EMF custom metrics are the main cost — keep to the bounded catalog above
  (~30–40 metric streams); CloudWatch custom-metric pricing ≈ $0.30/metric/mo + modest Logs ingestion;
  dashboards ~$3/dash/mo; alarms ~$0.10 each. Rough: **< ~$30–50/mo at beta scale** (refine on real volume).
- **Automated tests:** EMF-shape unit tests (metric lines parse to the right namespace/dims); log-scrub
  test (no PII); alarm-threshold unit tests on the CDK synth (assert alarms exist with the stated config).
- **Dev acceptance results:** the Phase-6 matrix, run in dev with safe fault injection.
- **Remaining production gaps / dependencies:** (a) the **auth milestone must land first** for the
  security/quota metrics to have data; (b) **tokens must be surfaced out of the engines** into the worker
  diag before EstimatedModelCost works; (c) owner must provide the SNS destination + budget number +
  prod account; (d) queue-wait needs an enqueue timestamp on the message.

## Revision to the beta-readiness milestone

The prior assessment budgeted "~1 day monitoring." This design is materially larger:
**structured-log standardization + EMF metrics ≈ 2 days; 4 dashboards + alarms + budget (CDK) ≈ 2 days;
iOS telemetry pipe ≈ 2 days; token-cost surfacing ≈ 0.5 day; acceptance ≈ 1 day → ≈ 7–8 engineering
days**, interleaved with (not after) the auth/quota work since they share the metric surfaces. Observability
is now a co-equal beta gate, not a tail task.

## Decision gate

STOP at owner approval before provisioning or changing production infrastructure. No public deploy.

---

## APPROVED for DEV implementation (2026-10-18) — 7 amendments

Owner approved dev implementation in reviewable increments; dev-only provisioning (account
989088054552); no prod/public deploy. Amendments folded into the contracts:

1. **Backend-plan vs client-playback are SEPARATE state machines.** Backend: submitted→planning→
   plan_ready→(worker done). Client: render_start→render_end→export→first_playable. `PlanCompleted` is
   NEVER counted as `VideoPlayable`; `TimeToPlayableVideo` is a CLIENT metric only. Dashboards show them
   as distinct series, explicitly labeled.
2. **Logical stage ≠ physical invocation ≠ billable attempt.** `stage` (coverage|guide|duration|edit_plan|
   repair|critique|music_plan) is logical; `provider_attempt` is the physical Bedrock call #; a billable
   attempt is any provider call that consumed tokens (including a fallback attempt and a repair call).
   `EstimatedModelCostUSD` sums ALL billable attempts, includes **multimodal/image token usage** (edit-plan-mm
   contact sheets) and **fallback** attempts. **Documented estimation limits:** image-token accounting is
   Bedrock's reported input tokens (we do not re-derive tile cost); pricing is a CDK-config table that can
   drift from real Bedrock prices; a crash mid-call may under-count. Metric is labeled "estimated".
3. **Low-volume alarm safeguards:** every rate/percentage alarm carries a MINIMUM SAMPLE COUNT (e.g.
   GenerationFailed% only evaluates with ≥5 starts in the window) so one failure in two requests is not a
   page; `treatMissingData` set explicitly (notBreaching for health %, breaching for DLQ depth); thresholds
   are actionable (tied to a human response, not vanity). **Quota DENIALS (normal: user hit cap) are a
   separate metric from quota-ENFORCEMENT ERRORS (the quota check itself failed)** — only the latter alarms.
4. **iOS telemetry endpoint hardening:** `/v1/telemetry` requires the SAME auth principal as the rest of
   the API (arrives with auth milestone; until then dev-gated), VALIDATES the event schema, enforces a
   BODY SIZE LIMIT and a PER-USER RATE LIMIT. Client telemetry is NEVER authoritative for billing or
   quotas (those are server-measured only). Client durations use a MONOTONIC clock (not wall time) for
   time-to-playable, so a clock change can't produce negative/huge spans.
5. **Low-cardinality dimensions, no PII** — reaffirmed: dims limited to env/service/op_type/stage/
   error_category/model_id. NEVER a raw user id, job id, GPS, prompt, or media in a dimension OR a log.
6. **Dev independence:** infrastructure + AI observability (SQS/Lambda/App Runner/DynamoDB metrics,
   model usage/latency/throttle/fallback/cost) ship in DEV NOW, independently. Security + per-user metrics
   (auth failures, authz denials, quota, active users) integrate WITH the auth/quota milestone (no principal
   exists yet). Dashboards reserve those widgets with "pending auth" placeholders.
7. **Acceptance includes REAL notification delivery** via safe dev fault injection (owner provides the SNS
   destination; alarm fires → notification actually received).

**Dev provisioning dependency:** alarm-notification acceptance (#7) needs the owner's SNS destination
(email or Slack webhook). Everything else (EMF metrics, dashboards, alarm definitions, token-cost
surfacing, iOS endpoint) is built + dev-provisioned without it; the SNS subscription is the one value to fill.

---

## Implementation checkpoint — feat/observability-completion (2026-10-21) [committed, NOT deployed]

Worktree `story-wt-observability`, branch `feat/observability-completion` off master `c7e4b0a`, app commit
`743a49b`. STOP gate honored: code + CDK definitions + tests only, **nothing provisioned/deployed**. Frozen
EditPlan/2 + prompts untouched; `enableObservability` defaults OFF so a plain synth/deploy is byte-unchanged.

### Phase 0 — what already existed (reused, not redesigned)
`packages/observability` already had the EMF emitter (`emit_metrics`, dimension allow-list), `estimated_cost_usd`,
and worker wiring (commit `9d7ca94`) emitting ModelInvocations/InputTokens/OutputTokens/RepairCount/
CritiqueCount/ModelFallbacks/EstimatedModelCostUSD + GenerationCompleted, plus GenerationFailed/
BedrockThrottles by error_category. CDK dashboards/alarms/SNS/budget were entirely absent.

### Phase 1 — Bedrock cost accounting (completed)
Physical invocation count, in/out tokens, model_id + stage dims, repair + critique counts, fallback-model
metric (already emitted; retained). **Versioned pricing:** added PRICING_VERSION="beta-pricing/2026-10-21",
surfaced on the worker diag line so a cost figure is traceable. estimated_cost_usd sums ALL billable attempts
(fallback + repair + multimodal via reported input tokens); unknown model -> 0.0, labeled estimate. Retries are
NOT free and physical calls are NOT merged.

### Phase 2 — generation + client telemetry (completed backend; client schema reserved)
Queue-wait separated from worker-exec: new QueueWaitMs (from the FREE SQS SentTimestamp — no API send-path
change) + WorkerProcessingMs; GenerationStarted added for rate denominators. Validator error categories already
on GenerationFailed. PII scrub: new scrub_log_fields() redacts instruction/soft_direction/gps/credential/
contact_sheet/email keys, keeps token counts. Client TimeToPlayableVideo/cancellation/recovery shown as a
DISTINCT client series on the dashboards; /v1/telemetry ingest + auth hardening reserved for the auth milestone.

### Phase 3 — CloudWatch IaC (completed, opt-in, env-parameterized)
New infrastructure/cdk/lib/observability.ts, instantiated only on `-c observability=true`. Names story-<env>-*
(development|beta|gamma|production). 4 dashboards (Product & Generation Health; AI Usage/Latency/Throttling/
Cost; Infra & Async Queue Health — mostly free metrics; Auth/Quota/Beta reserved); 10 alarms -> one SNS topic
(DLQ non-empty, queue age, Lambda errors, Lambda p99 duration, App Runner 5xx, generation-failure-rate with a
>=5-starts min-sample guard, Bedrock sustained throttling, quota-enforcement-error distinct from a normal
denial, abnormal daily cost, unauthorized-access anomaly; explicit treatMissingData, multi-datapoint windows);
SNS topic + optional email/https subscription; AWS Budget (monthly 50/80/100% actual-spend) when an email is
given; explicit log retention 30d dev / 60d beta / 90d gamma+prod.

### Phase 4 — tests (all green)
Python apps/api + packages **450 pass** (incl. new PII-scrub + pricing-version tests). CDK **jest 35 pass**
(30 pre-existing + 5 new: off-by-default = 0 resources; enabled = 4 dashboards / 10 alarms / 1 topic, every
alarm has an SNS action; DLQ alarm config + treatMissingData; email -> SNS subscription + Budget w/ 3
thresholds; env-parameterized names). `cdk synth -c observability=true` succeeds (16 observability resources).

### Expected CloudWatch cost (beta scale)
Bounded EMF catalog (~15-20 metrics x a few dims) ~$0.30/metric/mo; 4 dashboards ~$3/mo each; 10 alarms ~$0.10
each; modest Logs ingestion + retention. Rough **< ~$30-50/mo at beta scale**. Free AWS service metrics add $0.

### Remaining beta-account dependencies & deploy plan
Owner-supplied: SNS alarm destination (email or Slack webhook) + monthly budget number. Auth-milestone-gated:
the Auth/Quota dashboard + auth/quota/active-user metrics + /v1/telemetry client ingest. Deploy (after B0 beta
infra accepted): `cdk deploy story-<env>-api -c observability=true -c alarmDestination=<owner>
-c monthlyBudgetUsd=<n>` through the approved beta pipeline; do NOT merge to master without coordinating with
B0; dev acceptance (safe fault injection) runs per the Phase-6 matrix once a destination is set.

### Parallel-work safeguards honored
Isolated worktree/branch; no B0/worktree edits; no AWS account/DNS/SES/OIDC changes; nothing deployed; no
Bedrock load test; frozen EditPlan/2 + prompts untouched; unrelated uncommitted work preserved; env-
parameterized + opt-in.


---

## Increment A — Final integration-readiness review (2026-10-21)

**Owner decision:** Increment A accepted as code-complete and locally tested; NOT deployed. Beta account is
being provisioned by the separate B0 workstream. The bounded final review below was performed on branch
`feat/observability-completion` (worktree `story-wt-observability`); hardening committed as `5580441` on
top of `743a49b`. Python **453 pass**, CDK jest **37 pass**. Frozen EditPlan/2 + prompts untouched.

1. **Trusted per-user Bedrock attribution (privacy-safe, no high-cardinality dim).** The worker now emits a
   `bedrock_usage` structured LOG line carrying the TRUSTED backend-minted `story_user_id` (from the job
   row's `owner`, never client-supplied) + model_calls / in-out tokens / fallback / `estimated_cost_usd` /
   `pricing_version` / `pricing_known`. It is a LOG field, NOT a metric dimension — the EMF allow-list
   (`env,service,op_type,stage,error_category,model_id,reason`) would drop it, keeping metric cardinality
   bounded. Per-user cost is reconstructed via Logs Insights. `scrub_log_fields` guarantees no
   instruction/gps/token field rides along; `story_user_id` is an opaque id, not PII, and survives scrubbing.
2. **Unknown pricing ≠ zero cost.** New `price_lookup()` returns `(cost, priced)`; an unmatched model_id
   yields `priced=False` (cost 0.0 is an accounting GAP) distinct from a genuine zero-token attempt
   (`priced=True`, cost 0.0). Surfaced as the `MissingModelPricing` metric + an AI-dashboard widget so the
   gap is visible/alarmable. `estimated_cost_usd` kept backward-compatible.
3. **Cost covers all physical attempts.** Engine accumulates `input_tokens`/`output_tokens` with `+=` across
   every call incl. the 2 executability repairs and the Sonnet fallback (edit_planner `__init__.py`
   ~1473/1510); `ModelInvocations` counts physical calls (retries never free, never merged); the billed
   model is the FALLBACK when one fired. Repairs/critiques/fallbacks each emitted as their own metric.
4. **Merge-clean after PR #17.** `origin/master` (c7e4b0a, the PR-#17 merge) is a direct ANCESTOR of the
   branch — zero divergence, no conflict surface. B0 touches AWS accounts/DNS/SES/OIDC only, none of the 7
   changed code/CDK files, so no file-level conflict with B0 either.
5. **B0 budget reconciliation.** The AWS Budget is GATED on `-c createBudget=true` (default FALSE), so this
   stack never DUPLICATES B0's account-level budget. Alarms/dashboards/SNS are independent of that flag; the
   `abnormal-model-cost` CloudWatch alarm (independent of AWS Budgets) still pages on cost when B0 owns the
   budget.
6. **SNS destination.** Default `alerts@yotale.ai` (req), subject to VERIFIED email forwarding before it
   receives alarms/budget notices. Overridable via `-c alarmDestination=`.
7. **Beta budget.** `$100`/month default in beta, ACTUAL-spend alerts at **50 / 80 / 100%** (asserted in the
   CDK test).

**Req 8 — iOS time-to-playable & Auth/Quota metrics NOT yet wired (data sources absent):**
- `TimeToPlayableVideo` (p50/p95), `GenerationCancelled`, `GenerationRecovered`, `DuplicateInferencePrevented`
  — dashboard widgets exist but **no backend emitter and no `/v1/telemetry` client-ingest endpoint** exists.
  Requires: an authenticated client-telemetry endpoint + iOS MediaEngineV1 timing. Separate increment.
- `AuthFailures`, `AuthorizationDenials`, `QuotaConsumed`, `QuotaDenials`, `RateLimitDenials`, `ActiveUsers`,
  `GenerationsPerUserDay`, `QuotaEnforcementError` — Dashboard 4 + the `quota-enforcement-error` /
  `unauthorized-access-anomaly` alarms are SCHEMA-ONLY; they populate with the **auth/quota milestone** (no
  principal/quota surface exists yet). Alarms safely stay in INSUFFICIENT_DATA (treatMissingData set).

**STOP gate preserved:** no infra provisioned, no deploy, no B0/DNS/SES/OIDC/CI-CD change, no Bedrock load
test, unrelated uncommitted work preserved. After B0 beta infra is accepted → protected merge → deploy via
the approved immutable beta pipeline with `-c observability=true -c alarmDestination=alerts@yotale.ai`
(+`-c createBudget=true` only if B0 does not own the account budget).
