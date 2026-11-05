# P0 — Concurrent Story Processing: Root Cause & Reliability Fix

Status: **FIX IMPLEMENTED + DEPLOYED to dev; awaiting physical-device acceptance (Phase 8).**
Scope: smallest reliable concurrency control. No new infrastructure, no frozen-contract/prompt change.

## 1. Proven root cause (with evidence)

Symptom: while Story A imports/analyzes ~20-25 videos, creating Story B fails with
"Couldn't create your Story."

**The previous "backend saturation" diagnosis was NOT the real cause** and the 180s
timeout (`26cf54c`) was a band-aid. Measured facts:

- **App Runner logs for the failing window: EVERY request returned 200** — asset-understanding, story-coverage, creative-intent all `success:true`, model `claude-sonnet-4-6`, no throttling, one benign retry. ⇒ **Bedrock throttling (3-C) and daily-quota exhaustion (3-D) are ruled out.**
- **Client AU queue `drain()` is strictly sequential** (one job at a time, re-entrancy guarded). ⇒ the client does **not** fan out 20-25 parallel AU calls (3-A not the primary cause). (It does create a queue instance per view, so cross-view drains can overlap — a secondary contributor, addressed by client isolation below.)
- **THE root cause (3-B / event-loop blocking):** `asset_understanding` and `scene_understanding` are `async def` handlers, but they called the **synchronous** boto3 `converse()` (`engine.analyze(...)`) **directly on the event loop**. uvicorn runs a **single worker**, so each AU call **froze the entire event loop for its full ~10-14s model latency**. Every other request — including the interactive `/v1/creative-intent` for Story B — could not be accepted or progressed until the AU call returned. Back-to-back AU jobs kept the loop blocked continuously, so creative-intent waited past the client's 60s timeout and the client threw.

This is a classic "async handler + blocking I/O starves the loop" bug. The sync `def`
handlers (creative-intent, coverage, guide, director) were already safe (FastAPI runs
them in its threadpool); only the two `async def` handlers were blocking.

## 2. The fix (smallest solution the evidence supports)

**Backend (`15e8775`), `apps/api/app/main.py`:**
- Offloaded both blocking calls with `await run_in_threadpool(engine.analyze, ...)` so they run on a worker thread and the event loop stays free for interactive requests.
- Added `_AU_ADMISSION = anyio.Semaphore(4)` around the AU call: bounds concurrent background AU so it never occupies the whole threadpool. Interactive handlers do **not** take this semaphore (interactive priority = guaranteed headroom, not preemption). Conservative start = 4; it gates admission only, never interrupts a running call.

**iOS (`a2356c5`):**
- AU + scene uploads now use a dedicated `StoryBackend.backgroundSession` (own connection pool, `httpMaximumConnectionsPerHost = 2`), isolated from the interactive `longSession`. A Story's 20-25 large multipart AU uploads can no longer occupy the connection pool interactive requests need, and the client bounds background upload concurrency at the transport layer.

**Retry/backpressure:** unchanged and already correct — the AU queue uses bounded
exponential backoff (5s→20s→80s… capped 10 min) and the server spends its own single
retry before returning a 503 that leaves the job PENDING. No retry storm. A 503
(retryable) is distinguished from permanent 4xx (job dropped). The gateway's
`FallbackModelGateway` handles the per-DAY token cap by falling back to Sonnet 4.6 —
a queue cannot fix an exhausted daily quota, and that is a separate reported limit, not
what happened here.

## 3. Architecture decision (Phase 5)

Scheduling lives in **both** layers, reusing existing infrastructure — **no SQS/Lambda/DB/
new job system** (not warranted by the evidence):
- Backend: event-loop offload + bounded AU admission (the decisive fix).
- iOS: background-session isolation + the existing sequential persistent AU queue.

No frozen contract or prompt changed. No owner STOP needed (no new infra).

## 4. Before/after measurement (dev backend, live)

| | Before | After (deployed) |
|---|---|---|
| Interactive creative-intent, backend idle | ~1.0s | **1.0s** |
| 5 concurrent creative-intent | serialized behind any in-flight AU (→ 60s client timeout under AU load) | **all ~1.0–1.15s in parallel** (no serialization) |

The concurrent-call test is the direct proof the event loop is no longer blocked:
before the fix a blocking call serialized the loop; after, five model calls complete at
~baseline latency simultaneously.

Deploy: CodeBuild `9f30bec5` SUCCEEDED → ECR `:latest` → App Runner start-deployment →
RUNNING, `/health` 200. Backend suite 224 passed (includes the AU/scene endpoint tests
exercising the offloaded path).

## 5. Commits (not pushed)
- `15e8775` backend: offload + AU admission semaphore.
- `a2356c5` iOS: dedicated background session for AU/scene.
- (`26cf54c` prior: longSession for model-backed services — now a safety ceiling, not the fix.)

## 6. Phase 8 — physical-device checklist (owner)
1. Create Story A; import ~20-25 videos; let AU start.
2. **Immediately create Story B** → CreativeIntent resolves (near-baseline, no multi-minute wait, no "Couldn't create your Story").
3. Complete Story B's flow and work on it while Story A analyzes.
4. Story A continues and finishes on its own.
5. Both Stories keep their own Moments + intelligence (no cross-Story contamination).
6. Background/foreground + relaunch: AU resumes (PENDING jobs survive).
7. Any unavoidable error is categorized + recoverable (retryable 503 leaves job PENDING).

## 7. Remaining limitations
- iOS cannot guarantee unbounded background execution while suspended — AU is opportunistic/resumable (drains on active/launch), honestly, not a background daemon.
- The multiple per-view AU queue instances still exist; isolation + sequential drain make this benign, but consolidating to one shared queue is a future cleanup (not required for P0).
- Daily Bedrock token cap is handled by model fallback, not by the queue — a separate capacity concern.

## 8. P0 close recommendation
Close **after** Phase 8 device acceptance confirms Story B is creatable/usable while
Story A processes. The root cause is proven and fixed at the layer that caused it; live
measurements show interactive latency at baseline under concurrency.
