# Milestone: Pre-Beta Concurrency Audit & Optimization

**Status:** Audit complete; one P0 correctness fix shipped to PR (not merged), one iOS reliability fix to PR (not merged), live-infra + provider values pending owner access.
**Date:** 2026-10-27
**Scope boundary:** audit + offline tests + narrowly-justified correctness fixes only. No new queue, no Lambda-concurrency change, no infra redesign, no model/prompt/render change, no beta deploy, no paid load test.
**Environments:** dev `989088054552`, beta `224033508028`.

---

## 0. Executive summary

YoTale's backend architecture supports concurrent multi-user load, but one genuine
correctness bug was found and fixed, one iOS reliability gap was found and fixed, and two
classes of value remain **NOT VERIFIED** because they require owner-only access (live AWS
SSO, provider consoles).

| Area | Finding | Status |
|---|---|---|
| Active-job slot cap atomicity | **Race: concurrent distinct job_ids over-admit past the cap** | **FIXED** (PR #74) |
| Budget (USD/gens) reservation atomicity | Same race shape; bounded exposure | Documented; post-beta fix |
| AU 429 handling (iOS) | 429 was terminal → transient rate limit permanently failed a Moment | **FIXED** (PR #75) |
| Coverage vs Create slot contention | Auto-Coverage shares the 2-slot budget, can 429 a user's Create | Policy finding |
| AU synchronous 120s App Runner wall | Valid response can arrive after client timeout on fallback | Finding |
| Redelivery double-charge / double-invoke | Prevented by lease + token fencing + idempotent settle | VERIFIED safe |
| Leaked slot / stuck job recovery | `sweep_quota_orphans()` + terminal `release_slot` | VERIFIED safe |
| Live Lambda/SQS/DLQ values | — | **NOT VERIFIED** (owner: `aws sso login --profile yotale-beta`) |
| OpenAI / Gemini project rate limits | — | **NOT VERIFIED** (owner provider dashboards) |

---

## 1. Request-path taxonomy (what runs where)

| Flow | Endpoint | Execution | Queue? | Throttle class |
|---|---|---|---|---|
| Asset Understanding (AU) | `POST /v1/asset-understanding` | **Synchronous** (in App Runner request; model call off the event loop) | No | `ai_sync` |
| Story Guide (generation) | `POST /v1/story-guide-v2`, `/story-guide-refine` | **Synchronous** | No | `ai_sync` |
| Create a story | `POST /v1/edit-plan-jobs` (mode=`original`) | **Async** → SQS → worker Lambda | Yes | `ai_job_submit` |
| Revise | `POST /v1/edit-plan-jobs` (mode=`revise`) | **Async** | Yes | `ai_job_submit` |
| Create another version | `POST /v1/edit-plan-jobs` (mode=`explore`) | **Async** | Yes | `ai_job_submit` |
| Coverage/v2 (async) | `POST /v1/story-coverage/v2/jobs` | **Async** (reuses edit-plan job store, `coverage_v2` op discriminator) | Yes (**same** queue + worker) | `ai_job_submit` |

**Key facts**
- Create / Revise / Create-Another-Version are the **same endpoint and job type** (`OP_EDIT_PLAN`), differing only by `revision_context.mode`.
- Coverage/v2 async **shares the same SQS queue and worker Lambda** as the edit-plan family (op-type discriminated in `worker.py`). There is **no** separate coverage queue/worker.
- AU and Story-Guide generation are **not** queued — synchronous, bounded only by the `ai_sync` 20/min per-user rate limit and App Runner's 120s request wall.

---

## 2. Concurrency control layers

### 2.1 Per-user rate limit (`apps/api/app/throttle.py`)
Fixed-window counter in DynamoDB keyed by `story_user_id`. Beta = **enforce**; dev = **observe**.

| Class | Default/min | Routes |
|---|---|---|
| `ai_sync` | 20 | AU, scene-understanding, story-guide(-v2/-refine), creative-intent, sync edit-plan, music-plan, director |
| `ai_job_submit` | 10 | `edit-plan-jobs`, `story-coverage/v2/jobs` (**create/revise/explore + coverage share this bucket**) |
| `music_provider` | 20 | music candidates/search/analysis/soundtrack, scene-image |
| reads / writes / presign | 120 / 60 / 30 | polling, metadata, presign |

A `429` under throttle returns body `error:"rate_limited"` + `Retry-After` (seconds).

### 2.2 Per-user active-job cap (`packages/user_quota/__init__.py` → `reserve_slot`/`release_slot`)
`STORY_QUOTA_MAX_ACTIVE_JOBS` (beta **2**). A per-user cap on **queued + running** async jobs
combined, taken at submit and released by the worker on terminal (exactly-once via a
`slot#<job_id>` marker). Spans **all** async jobs together: create + revise + explore +
coverage draw from the same budget. AU and sync Guide do **not** consume a slot. Denial →
`429` body `error:"quota_exceeded"`, `scope:"active_jobs"`.

### 2.3 Worker Lambda concurrency (CDK `infrastructure/cdk/lib/story-api-stack.ts`)
SQS event source `batchSize: 1`, `reportBatchItemFailures: true`, **no `maxConcurrency`**.
Worker has **no reserved concurrency on beta** (`STORY_WORKER_CONCURRENCY` unset → shared
unreserved pool; a fresh-account Lambda limit of 10 forbids reserving). Timeout 900s,
`STORY_WORKER_DEADLINE_S=840`, memory 2048MB. App Runner 1 vCPU / 2GB, **default**
autoscaling (100 req/instance, up to 25 instances — AWS defaults, not pinned in CDK).

**`batchSize:1` is NOT serialization** — Lambda fans out one invocation per message.

### 2.4 Cost breakers (same UserUsage table, `reserve`/`settle`/`release`)
Per-user **$8/month**, per-user **20 generations/day** (per-UTC-day attribute `gens#YYYY-MM-DD`),
global **$60/month** (below the $100 beta AWS Budget alert). Reserve-estimate-then-settle-actual;
failed/retry/repair/fallback attempts **keep incurred spend** (never erased), allowance refunded.

---

## 3. P0 — Active-job cap atomicity race (FIXED, PR #74)

### 3.1 The bug
`reserve_slot()` did: (1) `get_item` → read `active_jobs`; (2) check `cur+1 > max` **in Python**;
(3) conditional `update_item` guarded **only** by `attribute_not_exists(slot#<job_id>)`.

That guard is per-job **idempotency, not a cap**. Two concurrent submits with **distinct
job_ids** both read the same `active_jobs=N`, both pass the Python check, both write distinct
markers → `active_jobs` over-admits past `max`. Real DynamoDB does the Python read **outside**
the conditional write, so the gap is genuine. The pre-existing concurrency test gave false
confidence: the in-memory fake held a lock across the whole read-check-write, hiding the race.

### 3.2 The fix (smallest correct change)
Fold the cap into the conditional write as a **non-arithmetic comparison** — DynamoDB supports
`<`, only arithmetic (`#aj + :one`) is rejected:

```
ConditionExpression = "attribute_not_exists(#sm) AND (attribute_not_exists(#aj) OR #aj < :max)"
```

Because the counter moves by exactly +1 per slot, `#aj < :max` before `ADD :one` ≡
`(#aj+1) <= :max` after. The single-item conditional UpdateItem serializes concurrent reservers
→ admits at most `max`. Python pre-check kept as a cheap early-out. **Observe mode unchanged.**
A rejected write is disambiguated: held marker → idempotent success; else → `QuotaDenied("active_jobs")`.

### 3.3 Verification
- **Faithful stale-read interleave test** models real DynamoDB (both racers read the pre-write
  snapshot; writes evaluate against live state): **pre-fix → `active_jobs=3` (over-admit);
  post-fix → capped at 2.**
- Structural assertion that the cap lives in the `ConditionExpression`, not only Python.
- Failed-submit release, redelivery idempotency, concurrent double-release never negative.
- **560 backend tests pass.** Both new guard tests **fail against the pre-fix code** (real regression guards).

### 3.4 429-not-500 mapping (confirmed)
`QuotaDenied` → `_denied()` = **HTTP 429** (`Retry-After:3600`, body `{error:"quota_exceeded",scope,retry_after_seconds}`).
`QuotaStoreError` (DynamoDB outage) → **HTTP 503** (`Retry-After:30`). A conditional failure can **never** surface as 500.

---

## 4. P2 — AU 429 retryable handling (FIXED, PR #75)

### 4.1 The bug
`AssetUnderstandingService` mapped **every** 429 → terminal `badStatus(429)`. A transient
per-user rate limit (`ai_sync` 20/min) therefore **permanently failed** a Moment's AU, with no
retry and no `Retry-After` honored. (Only `503 → unavailableRetryable` and transport errors retried.)

### 4.2 The fix
Classify the two distinct 429s the backend returns:

| Server body | Meaning | Client action |
|---|---|---|
| `error:"rate_limited"` | temporary rate cap | **RETRY** — PENDING, wait `max(Retry-After, exponential backoff)` + full jitter; completes on first 200 |
| `error:"quota_exceeded"` | spent allowance (daily gens / monthly USD / global) | **NOT retried this session** — deferred to next UTC-day boundary (daily reset); no attempt burned |

Hard errors (`badStatus`/`decoding`) are bounded by `attempts` (`maxHardAttempts=4`) then parked
(`hardErrorParkInterval=24h`). Transient 503/transport unchanged. Ambiguous 429 → safe non-retry branch.

### 4.3 No schema change
Retry state uses **only** existing persisted fields (`attempts`/`nextEligibleAt`/`lastError`/`state`)
— **no SwiftData `@Model` change, no migration** — so it survives app restart (tested with a fresh
queue over the same store). Honors the FROZEN AU model and the device-build gate.

### 4.4 Verification
Regression tests: rate-limit retry honoring `Retry-After` (+ no-header backoff fallback),
quota-exhausted no-retry + next-day deferral + no attempt burn, hard-error attempt bounding,
restart persistence, `isRetryable` classifier, jitter range, UTC-day boundary.

> **Build gate:** parse-clean in the sandbox only; the SwiftData macro cannot run there. The
> authoritative compile + `StoryTests Cmd-U` + a device AU-burst check is the owner's Xcode.
> Device verification pending.

### 4.5 Bulk-import (30 Moments) behavior
The AU queue drains **serially** (`fetchLimit=1`), persists across restarts, dedupes by Moment,
and defers while signed out. So a 30-Moment import does **not** burst past 20/min; with the fix,
a 429 no longer fails a Moment — it waits the window and completes. All 30 eventually complete.

---

## 5. Coverage vs Create slot contention (POLICY FINDING — not auto-fixed)

Coverage/v2 submit uses the **identical** `quota_gate.submit_reserve → reserve_slot` path, so
two in-flight auto-Coverage jobs **can consume both slots and 429 a user's Create**. iOS surfaces
the 429 correctly (`EditPlanJobClient.quotaExceeded`, honest message, no blind retry, no duplicate op).

**Smallest recommended policy (owner decides; cap NOT raised):** do not charge an active-job slot to
*automatic* Coverage (it already has idempotency + its own rate limit), or give Coverage a small
separate budget. Either keeps `max_active_jobs=2` for user-initiated work.

---

## 6. AU synchronous reliability (FINDING)

AU + Story-Guide generation run inside the App Runner HTTP request, which has a **hard ~120s wall**.
A provider fallback can push total elapsed toward/over 120s → App Runner cuts the response, so a
**valid AI response can arrive after the client has timed out**. (This is exactly why async Coverage
jobs were introduced.) AU uses the iOS background session, which is more tolerant, but there is no
async AU path. **Do not add a server-side AU queue without a demonstrated reliability problem and
owner-approved design** (explicit scope boundary).

---

## 7. Cost & recovery correctness (P4)

### 7.1 Redelivery cannot double-charge or double-invoke — VERIFIED
Worker holds a **lease + token** (`LEASE_SECONDS=900`); `complete()`/`settle()`/`release_slot()` are
token-fenced and idempotent. A redelivery of a live-leased or terminal job is dropped/acked → no
second model call, no second charge.

### 7.2 Leaked slots / stuck jobs recover — VERIFIED
`release_slot` runs on **every** terminal (`finally`). A worker that crashes mid-run is swept to
terminal via `expires_at`; **`sweep_quota_orphans()`** on the EventBridge reconcile tick releases
leaked slots + allowances **exactly once** (`quota_released=1`). `reconcile_lost_enqueue()` re-enqueues
never-leased stranded jobs. A crashed attempt's cost is an accepted **under-count, never an over-charge**.

### 7.3 Budget (USD/gens) over-admission — BOUNDED, post-beta fix
`reserve()` checks the USD/gens **sum** in Python then writes with an idempotency-only condition —
the same race shape as the slot bug. A budget *sum* needs arithmetic a DynamoDB condition cannot
express, so the slot one-liner does not apply.

- **Worst-case exposure:** `(concurrent requests − 1) × per-op estimate (~$0.15)` of transient
  over-admission at the $8-user / $60-global boundary — a few dollars, self-correcting as settles land.
- Estimates are conservative vs actual (settle records real cost).
- **Smallest remedy = a TransactWriteItems conditional redesign → post-beta.** Not urgent for 5–50
  users; the enforced per-request global $60 breaker is the real ceiling.

---

## 8. Live beta verification (PARTIALLY NOT VERIFIED)

| Item | Source | Value / status |
|---|---|---|
| Worker timeout / memory | CDK | 900s / 2048MB |
| Reserved concurrency (beta) | CDK | unset → unreserved pool |
| Event-source batch / scaling | CDK | `batchSize:1`, no `maxConcurrency` |
| Lease backstop | code | `LEASE_SECONDS=900` |
| **Live Lambda account concurrency** | AWS | **NOT VERIFIED** |
| **Live SQS visibility timeout vs 900s** | AWS | **NOT VERIFIED** — must be ≥ 900s or slow jobs redeliver |
| **DLQ `maxReceiveCount`** | AWS | **NOT VERIFIED** |
| **OpenAI / Gemini project RPM/TPM/tier** | provider consoles | **NOT VERIFIED** (not inferred) |

**Owner actions:** `aws sso login --profile yotale-beta` (then the agent pulls AWS values read-only);
check OpenAI + Google AI Studio usage/limits pages for the live provider tiers.

---

## 9. Observability (existing CloudWatch / EMF — no new infra)
Measure: API 429/5xx rates; AU latency p50/p95; AU fallback frequency; SQS queue depth +
approximate age of oldest message; Lambda concurrent executions / throttles / errors; EditPlan
queue-wait p50/p95; worker-execution p50/p95 (`WorkerProcessingMs`, separate from `QueueWaitMs`);
failed + DLQ job counts; active-slot reserve/release; actual model usage + cost (`bedrock_usage`
log stream, per-user reconstructed via Logs Insights — never a high-cardinality metric dimension).
No raw user media, prompts, or secrets in diagnostics.

**Latency separation (important):** a "3-minute generation" is **not** 3 min of Lambda. It is
queue wait (≈0 at low load) + worker execution (tens of seconds) + device media restore + **local
on-device render** + playback. The long tail is on-device, not Lambda.

---

## 10. Bounded live acceptance test (owner approval required before any paid run)
- **Users:** 3 (`+alias` beta accounts).
- **Calls:** ≤ 15 total — each user: 1 bulk-import of 3 Moments (AU) + 1 Create + 1 Revise.
- **Cost ceiling:** ~$5 (< $8/user, < $60 global).
- **Duration:** ~20 min. **Env:** beta.
- **Metrics:** §9 list. **Stop conditions:** any 5xx, any duplicate generated output, any slot stuck
  past lease, or global spend > $8.
- Prefer this small controlled test over a large performance benchmark.

---

## 11. Launch-readiness verdict (simulated vs measured)

All verdicts are **simulated/analytical** — nothing above 1 user has been measured.

| Concurrent users | Verdict | Basis |
|---|---|---|
| **5** | PASS (simulated) | Slot atomicity fixed+tested; redelivery/leak recovery verified in code; cost caps far exceed this. |
| **10** | CONDITIONAL PASS (simulated) | Needs: merge PR #74; verify live SQS visibility ≥ 900s; check provider RPM tier. |
| **20** | CONDITIONAL PASS (simulated) | Same + $60 global breaker is the ceiling (~120–400 gens/mo) — raise or cap testers; ship + device-verify PR #75. |
| **50** | NOT VERIFIED | Needs live provider quotas + the measured bounded smoke test; budget-atomicity follow-up advisable. |
| **5–10 EditPlan submissions/sec (future)** | FAIL as a promise | Not supported on evidence; needs reserved worker concurrency + provider burst headroom + a measured load test. Never claim TPS from Lambda account concurrency alone. |

---

## 12. Release blockers & follow-ups

**Blockers (pre-beta):**
1. Merge PR #74 (slot race is a real over-admission correctness bug).
2. Verify live SQS visibility timeout ≥ 840s worker deadline (else duplicate worker runs — results safe, cost wasted).
3. Check provider RPM/TPM tier before >10 concurrent.

**Non-blocking, recommended before external testers:**
- Ship + device-verify PR #75 (AU 429 retryable).
- Coverage/Create slot-priority policy (§5).
- `reserve()` budget-atomicity follow-up (§7.3).
- Raise the $60 global breaker if > ~15 testers.

---

## 13. Artifacts

- **PR #74** — `fix/prebeta-concurrency-readiness` — atomic active-job cap (backend).
  Files: `packages/user_quota/__init__.py`, `packages/user_quota/fakes.py`,
  `packages/user_quota/tests/test_user_quota.py`.
- **PR #75** — `fix/ios-au-429-retryable` — AU 429 retryable handling (iOS).
  Files: `apps/ios/Story/Story/Data/Contracts/AssetUnderstandingService.swift`,
  `apps/ios/Story/Story/Media/AssetUnderstanding/AssetUnderstandingQueue.swift`,
  `apps/ios/Story/StoryTests/AssetUnderstandingQueueTests.swift`.

Both PRs are **open, not merged, not deployed.**
