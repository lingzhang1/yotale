# Milestone — Async Story Coverage & Guide-Matching Reliability (P0)

Status: 🟡 Phase 0 verified; design fixed; implementation in progress. STOP at owner device acceptance.
App repo: `/Users/lingzhang/Workplace/story` (`master`, local only). Dev backend: App Runner
`story-development-api`, acct 989088054552 us-east-1.

## Problem

Opening a Story that has completed Asset Understanding no longer marks the Story Guide checklist
(every item showed "Shoot"). Investigation (device beacons + App Runner logs) found a stack of three
causes, two already fixed locally and one — the load-bearing one — requiring this milestone:

1. **Mapper truncation** (fixed, commit `7bc135f`): Coverage Mapper `max_tokens=1800` truncated its
   structured output on 26–50-moment Stories; the truncated result validated as an *empty*
   `dimension_coverage: []`, so every Guide item stayed "Shoot". Raised to 8192 + a guard that treats an
   empty mapping for a populated guide as `CoverageUnavailableError`. **Verified**: every Story now
   resolves real coverage (50→5 dims, 35→3, 26→4, all `sufficient`).
2. **iOS stale-cache** (fixed, commit `9d143d1`): the broken empty caches looked "fresh" to `isStale`
   (unchanged fingerprints), so the device never re-called the fixed backend. An empty cached mapping
   with completed AU now counts as stale → self-heal recompute.
3. **App Runner request-timeout wall** (THIS milestone): the fixed call is now *correct* but *slow*.

## Phase 0 — verified execution boundary

- **Endpoint that exceeded the timeout:** `POST /v1/story-coverage/v2` (`apps/api/app/main.py`).
- **Coverage vs Guide matching — separate operations.** The StoryGuide is generated ONCE
  (`/v1/story-guide`, `StoryGuideEngine`, text-only, fast) and persisted on device by
  `StoryGuideCoordinator`. Coverage/2 is a *separate*, Guide-relative operation. This milestone is
  about **Coverage** (`/v1/story-coverage/v2`); the Guide endpoint is not the slow path.
- **Model calls run SEQUENTIALLY — this is the root cause of the latency.**
  `RealStoryCoverageV2Engine.compute` (`packages/story_coverage_v2/__init__.py` lines 280–283):
  1. `RealStoryCoverageMapper.map()` — Opus 4.6, prompt `story_coverage/mapper-v1`, `max_tokens=8192`.
  2. `build_judge_evidence()` — deterministic, no model.
  3. `RealStoryJudgmentEngine.judge()` — Opus 4.6, prompt `story_coverage/judge-...`, `max_tokens=1200`.
  TWO back-to-back Opus 4.6 calls. Measured cold latency `latency_ms=190663` (~191s); warm 51–74s.
- **App Runner hard limit:** AWS App Runner enforces a **non-configurable 120-second** per-request
  timeout (AWS docs, "Developing application code for App Runner"). The ~191s call therefore cannot
  complete over App Runner; the handler finishes internally (`success=True` in logs) but App Runner has
  already severed the HTTP response, so the client never receives it. **Not a cold-start-only artifact:**
  two sequential Opus calls structurally risk >120s whenever either call is cold or the moment set is
  large. Raising the iOS client timeout (done provisionally in `coverageSession` 300s) is necessary but
  insufficient — it cannot beat the 120s App Runner wall.
- **Where the result is persisted:** on device only, by `StoryCoverageEngine.cache()` into the
  `StoryCoverageModel` SwiftData row (keyed by storyId). The server does NOT persist Coverage today.
- **What triggers client retries:** `StoryCoverageEngine.recomputeIfNeeded` is called on Guide/Story
  open; a failed/timed-out compute hits the `catch` (KEEP LAST VALID), keeps the empty cache, and the
  next open re-triggers — an uncontrolled recompute loop that re-spends two Opus calls each time.
- **Can completed results be recovered today?** No. The server discards the result once the HTTP
  response is severed; nothing persists it server-side.
- **Existing edit-plan job infrastructure — safe to reuse.** `packages/edit_plan_jobs` already provides
  everything Phases 1/2/4 need: `job_id = UUIDv5(operation_id)` idempotent submission; `payload_fingerprint`
  + `PayloadConflict` (409 on same op-id / different payload); DynamoDB status store with
  `lease_until`/`lease_token` fencing (stale worker cannot publish); SQS enqueue; S3 request staging;
  `expires_at` expiry on read; conditional status transitions; cancel re-check before publish. Worker
  `apps/api/app/worker.py` is the mirror: claim_lease → running → compute (identical engine path) →
  cancel-recheck → conditional complete. Infra (CDK `story-api-stack.ts`): DynamoDB
  `story-development-edit-plan-jobs`, SQS `story-development-edit-plan-jobs` (+ DLQ), Lambda
  `story-development-edit-plan-worker`.

## Design decision — reuse, with an operation discriminator (no duplicate infra)

Reuse the EXISTING `edit_plan_jobs.JobStore`, DynamoDB table, SQS queue and worker Lambda. Coverage jobs
are distinguished by an **`approach`/operation discriminator** already present in the job item
(`approach` field). This avoids provisioning a second table/queue/Lambda with no demonstrated need
(owner constraint). Coverage execution is added as a branch in the worker keyed on the operation, running
the IDENTICAL `RealStoryCoverageV2Engine.compute` path (same engine `deps` composition, same fallback
gateway, same frozen prompts, same validator). The Lambda timeout (currently generous, 15-min ceiling
available) comfortably covers two sequential Opus calls — no App Runner wall.

Coverage payload is small structured JSON (guide + intent + scope + completed MU values + pending count),
so it is staged as a single JSON body (no multi-file contact sheets); S3 staging is reused only if the
body exceeds the DynamoDB item limit, else inlined.

**Not forced into the EditPlan contract.** Coverage keeps its own `StoryCoverageV2RequestDTO` /
`StoryCoverageV2DTO` (frozen `story_coverage/2`). The job envelope is shared; the *payload* and *result*
schemas stay Coverage-specific to avoid unsafe coupling.

## Canonical operation identity & fingerprint (Phases 1 & 4)

`operation_id = coverage_v2:{story_id}:{guide_fingerprint}:{intent_fingerprint}:{sorted completed MU id+version set}:{MAPPER_PROMPT_VERSION}:{JUDGE_PROMPT_VERSION}`.
`payload_fingerprint` over the full request body. Identical inputs → `create_or_get` returns the existing
job (idempotent recovery, no new inference). Changed guide/intent/MU-set/prompt-version → new op-id → new
job (appropriate recompute). Same op-id, different payload → `PayloadConflict` → 409. Lease/fence prevents
a stale worker publishing over newer Story state.

## Endpoints (Phase 2)

- `POST /v1/story-coverage/v2/submit` → fast: compute op-id + fingerprint, `create_or_get`, enqueue if
  new, return `{job_id, status}` immediately (<1s, well under 120s).
- `GET /v1/story-coverage/v2/jobs/{job_id}` → durable status: `queued|running|completed|failed|cancelled|expired`
  + `failure_category` on failure + the `StoryCoverageV2DTO` result on completion.
- `POST /v1/story-coverage/v2/jobs/{job_id}/cancel` → cancel where supported (cancel_requested; worker
  re-checks before publish).
- Keep the legacy synchronous `POST /v1/story-coverage/v2` during migration for compatibility (it will
  still 504 on cold large Stories; iOS stops using it in Phase 5).

## iOS integration (Phase 5)

`StoryCoverageEngine.recomputeIfNeeded` becomes submit → poll → retrieve → persist. Job id stored on the
`StoryCoverageModel` row so an app restart recovers an in-flight job instead of re-submitting. Polling
reads status only (no inference). Progress states surfaced to the Guide view. Capture/library browsing
unaffected (coverage was already a background concern). Honest failure/throttle display.

## Guardrails (owner constraints)

- Frozen prompts (`story_coverage/mapper-v1`, judge) and the `story_coverage/2` output contract are
  **untouched**. `max_tokens=8192` stays (do not reduce without a versioned Phase-6 proposal).
- No speculative incremental coverage. No duplicate infra. No unrelated creative-editing features.
- A completed job yields a valid retrievable result; a failed job is never reported successful.
- STOP at owner device acceptance. No automatic public push/deploy.

## Phase 7 acceptance matrix

Normal · >120s cold · simulated 180s · duplicate submission while running · lost-HTTP-response recovery ·
app-restart recovery · completed retrieval · changed-moment-set invalidation · stale-job no-overwrite ·
cancellation · provider throttling · invalid model output · no-duplicate-inference-on-retry · existing
Story-creation/Guide behavior intact.

## Commits (running)

- `7bc135f` backend Mapper max_tokens 1800→8192 + empty-mapping guard (+test).
- `9d143d1` iOS empty-cache self-heal (isStale).
- `8ae5bb2` iOS dedicated `coverageSession` (300/420s) — provisional, superseded by async in Phase 5.
- (async implementation commits appended as landed.)
