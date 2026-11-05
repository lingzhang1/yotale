# Milestone — AI Workload Isolation & Bedrock Quota Audit (P0, verification-only)

Status: 🔵 audit complete, read-only. NO infra provisioned, NO model/prompt changes, nothing deployed.
Dev acct 989088054552 us-east-1. All figures below are MEASURED from deployed AWS + committed code on
2026-10-15, not estimated.

## Executive answer

**The product requirement is currently at RISK, in exactly ONE dimension: the shared Opus Bedrock quota —
NOT the Lambda queue, and NOT Sonnet AU.**

- There is **one** job queue and **one** worker Lambda. My new async Coverage path **shares both** with Edit
  Planning. So Coverage CAN occupy Edit-Planning worker slots today (reserved concurrency = 2). This is the
  queue-contention risk the owner flagged, and it is real but small (dev volume).
- Measured throttling in the test window: **152 Bedrock `InvocationThrottles` in 2h, 100% on `opus-4-6`,
  zero on `sonnet-4-6`.** The owner's instinct is confirmed: **Sonnet AU and Opus workloads do NOT compete
  for the same quota.** The contention is Opus-only, shared by Coverage (×2 calls) + Guide + Edit Planning +
  Music Plan + Duration + Director.
- Asset Understanding runs **on-device, serially** (one job at a time) and hits the backend as a normal
  request — it is already bounded and is NOT a server-queue participant.

## Phase 0 — deployed topology (operation-by-operation)

| Operation | Endpoint | Sync/Async | Queue | Lambda | Model | Shares Opus quota? |
|---|---|---|---|---|---|---|
| Asset Understanding | POST /v1/asset-understanding | SYNC (device→API, device-serial queue) | none | none | **Sonnet 4.6** (`STORY_AU_MODEL`) | **No — Sonnet** |
| Scene Understanding | POST /v1/scene-understanding | SYNC | none | none | Nova Pro (`amazon.nova-pro-v1:0`) | No — Nova |
| Director / AI Ideas | POST /v1/director/{initialize,next} | SYNC | none | none | Opus **4.5** (`claude-opus-4-5`) | Partial (diff Opus ver) |
| CreativeIntent | POST /v1/creative-intent | SYNC | none | none | deterministic / categorical (no model by default) | No |
| StoryGuide | POST /v1/story-guide | SYNC | none | none | **Opus 4.6** | **Yes** |
| Coverage Mapper | (internal to /v1/story-coverage/v2[/jobs]) | ASYNC (new) + legacy SYNC | **edit-plan-jobs (SHARED)** | **edit-plan-worker (SHARED)** | **Opus 4.6**, 8192 tok | **Yes** |
| Coverage Judge | (internal, 2nd call) | same job as Mapper | SHARED | SHARED | **Opus 4.6**, 1200 tok | **Yes** |
| MusicPlan | POST /v1/music-plan | SYNC | none | none | **Opus 4.6** | **Yes** |
| Edit Planning | POST /v1/edit-plan[-mm] (sync) + /v1/edit-plan-jobs (async) | ASYNC primary | **edit-plan-jobs** | **edit-plan-worker** | **Opus 4.6** → Sonnet 4.6 fallback | **Yes** |
| NL Revision interpret | POST /v1/interpret-revision | SYNC | none | none | 1 structured call (Opus 4.6 gateway) | Yes |

Deployed vs local-only: the Coverage async **endpoints + worker dispatch are committed and DEPLOYED** this
session (App Runner image + worker Lambda both carry `operation_type=coverage_v2`). No NEW table/queue/Lambda
was created — the Coverage path reuses the edit-plan ones. Everything else above was already deployed.

### Concurrency configuration (MEASURED, live)
- Worker Lambda `story-development-edit-plan-worker`: **reservedConcurrentExecutions = 2**, timeout 900s,
  mem 2048MB, `batchSize=1`.
- SQS→worker event-source mapping: `BatchSize=1`, **ScalingConfig/MaximumConcurrency = unset** (so the ESM can
  scale Lambda up to the function's reserved cap of 2; no lower per-source cap).
- App Runner `story-development-api`: 1 vCPU / 2GB, single service, synchronous endpoints run in-process.
- iOS `backgroundSession` (AU uploads): `httpMaximumConnectionsPerHost = 2`; AU `drain()` loop is **serial**
  (`await run(job)` one at a time, `maxJobs=50` per drain). So one device issues AU essentially one-at-a-time.
- Reconcile: an EventBridge rule fires a `{reconcile:true}` sentinel to the worker every 1 min — a DynamoDB
  scan + bounded re-enqueue, **no model call**.

## Phase 1 — quota contention (MEASURED)

Bedrock service quotas (us-east-1, cross-region inference profiles):
- **Opus 4.6 V1:** 10,000 requests/min, **3,000,000 tokens/min**. (both regional + global profile)
- **Sonnet 4.6:** 10,000 requests/min, 6,000,000 tokens/min.
- No tokens-per-DAY quota surfaced for these two (the "Too many tokens per day" ProviderError the fallback
  guards against is an account/burst condition, not one of these listed quotas).
- These are DIFFERENT quota buckets per model family — **Sonnet AU does not draw down the Opus pool.**

Recent throttling (CloudWatch AWS/Bedrock InvocationThrottles): **opus-4-6 = 105 then 47 (2 hourly buckets);
sonnet-4-6 = 0.** The throttling coincided with this session's Coverage testing (each Coverage job = 2 Opus
calls, 8192+1200 tokens, plus repeated recompute-loop retries before the fixes landed). With a 3M TPM Opus
budget, steady state is not the cause — the throttles are **bursty concurrency** (several large Opus calls
landing together), which is exactly what an uncapped shared worker + the old retry loop produced.

## Phase 2 — minimal safeguards (RECOMMENDED, not yet applied)

Smallest changes, config/bounded-concurrency first, no new infra, no model changes:

1. **Cap the SQS→worker MaximumConcurrency and/or raise reserved concurrency with a split.** Today Coverage
   and Edit Planning share 2 worker slots. Two cheap options:
   - (a) Add an ESM `ScalingConfig.MaximumConcurrency` so background Coverage cannot consume all worker slots,
     leaving headroom; OR
   - (b) give Edit Planning its own small reserved pool. **(a) is the smaller change** (one ESM field, no new
     Lambda). A SECOND queue+worker for Coverage is the clean separation but is NEW INFRA — only if (a) proves
     insufficient. **Recommend (a) first.**
2. **Bound per-wake worker Opus concurrency implicitly** — `batchSize=1` + reserved=2 already means at most 2
   concurrent Opus *workflows*, but each Coverage job fires 2 Opus calls sequentially (not parallel), so the
   instantaneous Opus concurrency ceiling from the worker is ~2. That is already bounded; the burst came from
   the device retry LOOP (now fixed by the async idempotent job: a duplicate submit recovers the running job,
   `created=false`, launching NO new inference).
3. **AU import concurrency** is already bounded (device-serial + 2 conns/host). No change needed.
4. **Reuse valid results** — the async Coverage op-id (sha256 of the canonical body) already guarantees
   repeated Coverage requests for the same evidence recover the existing job instead of launching inference.
   Edit Planning has the same idempotency. **This is the single biggest real-world protection and it is now
   in place.**
5. **Foreground protection where Opus overlaps:** StoryGuide, MusicPlan, Edit Planning and interactive
   revision all draw the Opus pool synchronously on App Runner. If background Coverage bursts must never slow
   a user's Edit Plan, the only true isolation is a separate Opus allocation OR running Coverage on a
   DIFFERENT model — explicitly OUT OF SCOPE this milestone (no model changes). Short of that, (1a) + the
   idempotent-recovery reuse is the proportionate dev-stage safeguard.

**No global scheduler recommended** — the audit does not demonstrate the need at dev volume. The real
historical burst source (the recompute loop) is already eliminated.

## Phase 3 — capacity scenarios (MEASURED inputs)

- **A. 100-video import + another user's Story:** AU is **device-serial** per user and runs on **Sonnet**
  (separate quota). It cannot starve the Opus worker or Opus foreground. Low risk.
- **B. 5 simultaneous Story generations:** each generation issues several SEQUENTIAL Opus calls (Guide,
  MusicPlan, Edit Plan). 5× concurrent is well under 10,000 RPM but can bunch on TPM/burst — this is the most
  likely real throttle source. Edit Planning's Opus→Sonnet fallback absorbs some; worker reserved=2 bounds the
  async portion. Medium risk under burst; mitigated by (1a).
- **C. 2 long Coverage jobs + 3 Edit Plan jobs arrive:** ALL FIVE land on the SAME queue/worker with reserved
  concurrency 2 → at most 2 run, the other 3 **queue** behind them. A long Coverage job (2 Opus calls, up to
  minutes) can therefore **delay an Edit Plan job** — the concrete starvation case. Existing protection: FIFO
  SQS + lease; missing: no priority / no Coverage-vs-EditPlan slot split. **This is the one gap worth (1a) or
  a dedicated Coverage queue.**
- **D. Multiple imports + one NL revision:** imports are Sonnet/device-serial; the revision's interpret call
  is one Opus structured call on App Runner. No queue contention; only shares the Opus TPM pool briefly. Low
  risk.

## Final report — bottom line

1. **Queue topology:** ONE DynamoDB table + ONE SQS queue (+DLQ) + ONE worker Lambda, now shared by Edit
   Planning AND Coverage via `operation_type`. AU/Scene/Guide/MusicPlan/Director/CreativeIntent/Revision are
   synchronous on App Runner (no queue).
2. **Worker concurrency:** reserved=2, batchSize=1, ESM MaximumConcurrency unset.
3. **Model/quota:** AU=Sonnet 4.6 (own quota); Scene=Nova; Director=Opus 4.5; Guide/Coverage/MusicPlan/
   EditPlan/Revision=Opus 4.6 (SHARED pool: 10k RPM / 3M TPM). Edit Plan has Opus→Sonnet fallback.
4. **Background AU:** device-serial, 2 conns/host, Sonnet — well bounded, not a server bottleneck.
5. **Real bottleneck:** the shared **Opus 4.6 quota under burst**, and the shared worker's **2 reserved
   slots** letting a long Coverage job delay an Edit Plan job (scenario C). The historical throttles were the
   now-fixed recompute LOOP, not steady state.
6. **Recommended minimal change:** add an SQS ESM `MaximumConcurrency` so background Coverage leaves worker
   headroom for Edit Planning (config, no new infra); rely on the already-landed idempotent job reuse to stop
   duplicate inference. Only escalate to a dedicated Coverage queue if scenario C proves limiting.
7. **Scaling risks (prod):** single 1-vCPU App Runner instance for all synchronous Opus calls; reserved=2
   worker; shared Opus TPM. At production concurrency these need: App Runner autoscaling, a larger/again-split
   worker pool, and possibly a quota increase or a cheaper model for background Coverage (model change =
   separate, explicitly-authorized milestone).

STOP before provisioning or changing infrastructure (owner constraint). No model/prompt/deploy changes made.
