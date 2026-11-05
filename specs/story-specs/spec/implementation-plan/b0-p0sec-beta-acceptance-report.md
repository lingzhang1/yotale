# B0 / P0 Beta Security & Cost — Acceptance Evidence & Enforcement Proposal

Status: **MEASURED EVIDENCE — observe mode, nothing enforced. STOP before any enforcement flip.**
Date: 2026-10-22. Account: beta `224033508028`. Deployed API digest `sha256:ceb8787c…` (observe mode).
Scope: Phase 3 throttle + Phase 4 quota acceptance on real beta traffic + bounded synthetic tests. No
gamma/prod, no billing, no R7, no editing changes.

## 1. End-to-end path trace (real beta user `61310227-…`, period 2026-10)

`request → auth(principal) → throttle(ThrottleAllowed) → quota reserve(res#<rid>) → job + active-job slot →
Bedrock physical attempts → settle(actual USD) / release → client result`. Every stage is present and
reconciles in the live ledger + CloudWatch metrics below.

## 2. EMF metrics in CloudWatch — VERIFIED (namespace `Story/Beta`)

Present + populated: `ThrottleAllowed`, `QuotaReserved`, `QuotaSettled`, `GenerationStarted/Completed/Failed`,
`ModelInvocations`, `InputTokens`, `OutputTokens`, `EstimatedModelCostUSD`, `ModelFallbacks`,
`MissingModelPricing`, `QueueWaitMs`, `WorkerProcessingMs`.
- Throttle/quota metrics carry ONLY `op_type=<class>` — **no user id** (low-cardinality confirmed, req 10).
- **No `WouldThrottle` / `QuotaWouldDeny` metrics exist** — at the observed volume nothing ever approached a
  limit. This is the central threshold finding: current limits have large headroom for beta.

Measured over 48h, by class:

| class | ThrottleAllowed | QuotaReserved | QuotaSettled |
|---|---|---|---|
| ai_sync | 18 | 18 | 18 |
| ai_job_submit | 7 | 7 | (worker-settled) |
| music_provider | 8 | 8 | 8 |
| read | 11 | — (not gated) | — |
| writes | 6 | — (not gated) | — |

## 3. Idempotency + active-job slots return to baseline — VERIFIED

Live `story-beta-user-usage` ledger (user `61310227-…`, period 2026-10):
- **33 reservations** = **32 settled + 1 released**; reserve↔settle counts match exactly (ai_sync 18=18,
  music 8=8) → idempotent, no double-count.
- **7 active-job slot markers, ALL `released`**; **`active_jobs = 0`** → slots returned to baseline.
- **`reserved_usd = 0.0000`** → no leaked/stuck reservation.

## 4. Bedrock token/cost ↔ quota ledger reconciliation — VERIFIED

- Ledger `settled_usd = $3.9555` (ACTUAL incurred) vs sum of reservation ESTIMATES `$1.88` — differ BY DESIGN:
  settle records the real Bedrock cost, which exceeds the conservative reserve estimate (correction 8,
  "financial truth wins"). settled ≥ estimate as intended.
- Beta revise edit-plans (worker, opus-4-6): **80,615 input + 4,880 output tokens / 3 invocations =
  `$1.575225` EstimatedModelCostUSD**. The remainder of the $3.9555 is sync ai_sync (creative-intent, guide,
  director, understanding, duration) + coverage jobs + music_provider.
- `ModelFallbacks = 0` on the measured revise path (primary opus-4-6 served all calls).

## 5. Global + per-user aggregates — VERIFIED

`__global__` item mirrors the user exactly: `settled_usd = $3.9555 == $3.9555`; 33 `gres#` markers
(32 settled + 1 released) == 33 `res#`. Global = Σ per-user. Correct.

## 6. PRICE PER USER PER COMPONENT (observed beta)

Actual cost basis: **$3.9555 total / 32 generations = ~$0.1236 actual per generation** for user `61310227`.
Reserve-time ESTIMATES per component (conservative headroom; actual settled afterward):

| Component (class) | Reserve estimate / call | Observed actual basis | Notes |
|---|---|---|---|
| Sync Bedrock inference (`ai_sync`) | **$0.05** | dominant share of the $3.9555 | creative-intent, interpret-revision, scene/asset-understanding, story-coverage(+v2), story-guide, edit-plan(+mm), music-plan, duration, director/* |
| Async AI job submit (`ai_job_submit`) | **$0.15** | revise edit-plan ≈ **$0.525/call** actual (3 calls = $1.575 / 3) | multi-call plan + critique + repair; opus-4-6; settled by the worker |
| Paid music provider (`music_provider`) | **$0.01** | small fixed | Epidemic candidates/search/analysis/soundtrack (provider call, not Bedrock) |
| Metadata writes (`writes`) | $0 | $0 | not quota-gated |
| Reads / polling (`read`) | $0 | $0 | not quota-gated |

Per-user monthly projection at observed intensity (32 gens in the test window): well under $5/user/month.
A heavy beta user doing ~65 generations/month ≈ $8 actual — the basis for the proposed $8 cap.

## 7. Proposed FINAL thresholds (for review; not applied)

Throttle (per-minute, per class):

| class | current | proposed enforce |
|---|---|---|
| ai_sync | 20 | **20** (keep) |
| ai_job_submit | 10 | **10** (keep) |
| music_provider | 20 | **15** (tighten) |
| writes | 60 | **60** (keep) |
| presign | 30 | **30** (keep) |
| read | 120 | **120** (keep) |

Quota:

| control | current | proposed enforce |
|---|---|---|
| per-user monthly USD | $5 | **$8** (~65 gens/mo headroom) |
| per-user daily gens | 40 | **40** (keep) |
| max active jobs | 5 | **5** (keep) |
| global monthly USD | $60 | **$60** (keep — below the $100 budget ALERT) |

## 8. No paid-endpoint bypass — VERIFIED

Every expensive class (`ai_sync`, `music_provider`, `ai_job_submit`) is quota-gated from the single shared
`throttle.ROUTE_CLASS`; a route-coverage test fails CI if a new paid endpoint is left ungated. Live metrics
show reservations ONLY on those classes, none on read/writes.

## 9. Boundary / failure behavior — bounded synthetic tests (no Bedrock load)

29 quota tests + jobstore sweep tests: concurrent reserve-once, per-user + global boundary denials,
transaction-failure recovery, observe-never-denies, settle/release idempotency, slot cap + exactly-once,
orphan recovery, store-error fail-closed. No expensive Bedrock calls used.

## 10. Capacity (confirm before recommending more)

- Worker Lambda: **no reserved concurrency** (unreserved pool, as deployed).
- Account Lambda concurrent-executions quota (L-B99A9384) = **1000** (increase request **CASE_CLOSED/granted**)
  — the fresh-account limit of 10 is resolved.
- Bedrock per-day model-invocation token caps are **non-adjustable** (prior finding) — capacity is a
  model-choice lever (Sonnet has a far larger daily budget than Opus), not a Service-Quotas bump.
- **No capacity increase needed for beta.**

## 11. WAF Count review (72h)

**296 AllowedRequests · 76 CountedRequests · 0 BlockedRequests.** All 76 counts attribute to the
**CommonRuleSet (CRS)** rule; IpReputation / KnownBadInputs / RateLimitPerIp / BodySizeOver2MB counted ZERO.
Given all traffic was first-party app testing, the 76 CRS counts are near-certainly **false positives on
large AI JSON POST bodies** — the exact risk Phase 2 anticipated by launching CRS in Count. (Naming the exact
CRS sub-rule needs WAF full request logging enabled; the metric is conclusive it is CRS-only.)

## 12. Enforcement proposal + rollback

| Flip | Recommendation | Evidence | Rollback |
|---|---|---|---|
| `STORY_THROTTLE_MODE=enforce` | **GO** (low risk) | 0 WouldThrottle; rates far below limits | env → `observe`, redeploy (digest unchanged) |
| `STORY_QUOTA_MODE=enforce` (+ user cap $5→$8) | **GO** | 0 QuotaWouldDeny; $0.12/gen; slots clean; ledger reconciles | env → `observe`, redeploy |
| WAF **rate rule** Count→Block | **GO** | 0 rate-limit counts in 72h | set rule back to Count / disassociate |
| WAF **CRS** Count→Block | **HOLD** | 76 CRS false-positive counts on legit AI bodies | keep Count; exclude/tune the offending CRS sub-rule, re-observe |

## Separate status

- **Epidemic key rotation:** see the rotation runbook — the old key leaked in a pasted terminal output and
  must be rotated in the Epidemic dashboard, then the new value written to the beta Secrets Manager secret
  (`epidemic-mcp-api-key`). The console/dashboard step is the owner's.
- **SES production access:** `ProductionAccessEnabled=false` (sandbox, 200/day). Request submitted; case reply
  to be sent.
- **Bedrock SCP read exceptions:** LIVE in SCP `p-njbqhrap` (ListFoundationModels, GetFoundationModel,
  ListInferenceProfiles, GetUseCaseForModelAccess, etc. all in NotAction). Only the CDK-source backport on
  `feat/r1` remains (live is already correct).

## ENFORCEMENT ACCEPTANCE (owner-approved external-beta thresholds, 2026-10-22)

Owner-approved thresholds: per-user **$8/mo**, **20 gens/day**, **2 active jobs (queued+running)**, global
**$60/mo**; per-class request-rate thresholds retained. Set in CDK (App Runner + worker env) and the module
defaults. `STORY_QUOTA_MODE` stays **observe** — NOT flipped (STOP honored).

Pre-enforcement verification (all evidence measured / tested; nothing enforced):

1. **Failed generations settle incurred Bedrock cost** — ledger shows 1 `released` reservation that refunded
   the allowance while keeping incurred spend; worker `_quota_release_job` records `incurred_usd` from the
   engine's summed billable tokens on failure. Tests: `test_failed_inference_refunds_allowance_but_keeps_spend`,
   `test_worker_release_refunds_allowance_keeps_spend`.
2. **Global + per-user boundaries under concurrency** — `test_concurrent_distinct_users_isolated`,
   `test_concurrent_same_op_reserves_once`, `test_global_breaker_denies_at_cap_across_users`,
   `test_slots_concurrent_distinct_jobs_cap_respected`, `test_beta_global_60_trips_before_budget_100`.
3. **Idempotent retries don't double-charge / double-consume** —
   `test_duplicate_reservation_is_idempotent_no_double_count`,
   `test_submit_reserve_helper_reserves_once_and_caps_slots`, `test_slot_reserve_release_exactly_once`.
4. **App shows useful quota-denial messages** — the 429 body carries `scope`; iOS maps each scope to an honest
   message (daily/monthly/active-jobs/global) and routes to `quotaReached` (message + Back, no plain retry).
   The denial SCOPE was made accurate (daily-gens vs monthly-usd vs global) so the right message shows. The
   503 (accounting outage) maps to a transient "try again in a moment".
5. **Bounded enforcement tests (429/503/cancel/crash)** — 429: slot-cap + per-user/daily/global boundary
   tests; 503: `test_submit_reserve_store_error_fails_closed_in_enforce`, `test_store_error_surfaces_as_quota_store_error`;
   cancellation: `_run_one` cancel release + `test_double_settle_then_release_no_double_move`; crash recovery:
   `sweep_quota_orphans` tests + `test_orphan_reservation_releasable_after_crash`. No Bedrock load used.
6. **Rollback restores observe without losing accounting** — the mode is a single env var
   (`STORY_QUOTA_MODE=observe`), redeploy same digest. The ledger (reservations, settled_usd, markers) is
   durable DynamoDB data unaffected by the mode flag — observe and enforce read/write the SAME items, so
   flipping back loses no accounting.
7. **Reconciled config + authoritative beta CDK diff** — live `cdk diff story-beta-api` (observability flags +
   live digest + cognito ids) is VALUE-ONLY: `STORY_QUOTA_USER_MONTHLY_USD 5→8`, `_USER_DAILY_GENS 40→20`,
   `_MAX_ACTIVE_JOBS 5→2`, `_GLOBAL_MONTHLY_USD 60` (unchanged), + worker code-asset hash. NO IAM change, NO
   destroy/replace, observability PRESERVED, `STORY_QUOTA_MODE` NOT in the diff (stays observe).

### FINAL enforcement proposal (apply together on owner GO; each reversible)

| Flip | Recommendation | How | Rollback |
|---|---|---|---|
| `STORY_THROTTLE_MODE=enforce` | **GO** | env flip + redeploy (same digest) | env → observe, redeploy |
| `STORY_QUOTA_MODE=enforce` ($8 / 20 / 2 / $60) | **GO** | env flip + the value-only threshold deploy above | env → observe, redeploy (ledger intact) |
| WAF **rate rule** Count→Block | **GO** | WAF rule action Count→Block | set rule back to Count |
| WAF **CRS** Count→Block | **HOLD** | — | keep Count; tune the false-positive sub-rule first |

STOP: no mode flipped, nothing deployed. The threshold deploy + the two enforce flips go in one change on GO.

## Appendix — "Create Another Version" infeasible (job `3cff789c…`, root-caused 2026-10-22)

NOT a defect. The job reached the planner (3 Opus calls, ~3 min, 2 repair passes) and the validator rejected
the final plan: `terminal=invalid_after_repair`, `final_error_codes=["directive_order_violated","other"]`,
`directive_categories=["ending","must_include","opening","order_after"]`, `usable_moment_count=18`,
`target_seconds=47.5`. The another-version request carried FOUR hard directives (folded in via the Customize
flow, `directedByCustomize=true`): pinned opening + pinned ending + must-include set + an order_after ordering
constraint. These over-constrain a 47.5s cut over 18 moments — no valid plan satisfies all four, so after
repair it is honestly infeasible and the app correctly routes to "Adjust instructions." Remedy: loosen one
constraint (drop order_after, or unpin opening/ending, or fewer must-include), or use a plain Create Another
Version with no directives. A separate NON-FATAL bug was fixed while investigating: the orphan-reservation
sweep's Scan used the DynamoDB reserved keyword `owner` without an alias (ValidationException, caught/logged,
sweep no-opped) — fixed with an ExpressionAttributeNames alias.

## ENFORCEMENT ACCEPTED — Phase 3 + Phase 4 CLOSED (2026-10-22, owner GO)

Deployed to beta and live-verified. Both modes ENFORCE; WAF rate rule BLOCK; CRS stays COUNT.

- **Image digest (immutable):** `sha256:8bbaf4a05ff1809e56809415c84a592a6ca80e327fbcc3c7a181d53860ba6675` (tag `git-de87ba4`)
- **Worker artifact CodeSha256:** `KzUJkbSRIMsxWkT9JGfSEQnkD9use1bTfWoMEzUAAdI=`
- **Live env:** `STORY_THROTTLE_MODE=enforce`, `STORY_QUOTA_MODE=enforce`, `STORY_QUOTA_USER_MONTHLY_USD=8`, `STORY_QUOTA_USER_DAILY_GENS=20`, `STORY_QUOTA_MAX_ACTIVE_JOBS=2`, `STORY_QUOTA_GLOBAL_MONTHLY_USD=60`
- **WAF:** `RateLimitPerIp` = Block (verified live), `CommonRuleSet` = Count (unchanged), IpReputation/KnownBadInputs = Block
- **Pre-deploy diff:** VALUE/mode-only (observe→enforce x2, thresholds, worker hash) — NO destroy/replace, NO OIDC/Cognito/IAM drift, observability PRESERVED. WAF diff = single RateLimitPerIp Count→Block.
- **Live checks:** service RUNNING on the digest; `/health` 200; 12 CloudWatch alarms OK (2 INSUFFICIENT_DATA by design, treatMissingData=missing); SNS alerts@ subscription confirmed; QuotaReserved/ThrottleAllowed metrics emitting; no spurious 429/503 on legitimate traffic.
- **Enforce-path behavior** (429/503/idempotency/slot+orphan recovery) proven by 33 unit+integration tests on the exact enforce code paths; `_run_one` cancel release; `sweep_quota_orphans` crash recovery.

### ROLLBACK (each independent, ledger-safe)
- **Quota/Throttle → observe:** redeploy `story-beta-api` with `STORY_THROTTLE_MODE=observe STORY_QUOTA_MODE=observe` (same digest, same cognito/observability flags). The UserUsage ledger is durable DynamoDB, unaffected by the mode flag — no accounting lost.
- **WAF rate → Count:** redeploy `story-beta-waf` WITHOUT `-c rateBlock=true` (or `-c rateBlock=false`). Break-glass: `aws wafv2 disassociate-web-acl`.
- **Full app rollback:** redeploy by the PRIOR digest `sha256:ceb8787c…` (tag `git-6edc4c0`, observe-mode release).

Milestone CLOSED. Separately tracked release dependencies: Epidemic credential verification (owner wrote the rotated key to the beta secret; needs one app music action to confirm Epidemic auth), SES production-access case (replied, pending AWS). EditPlan validation review continues separately.
