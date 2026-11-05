# 06 — Asset Understanding (MVP design — FROZEN 2026-10-05)

> **Status: FROZEN for MVP implementation.** This design supersedes the pre-experiment
> draft (5-frame sampler, `quality`/`story_roles` schema, <5s latency target). It is the
> product of three completed experiments — see rationale/history in
> `milestone-d-asset-understanding-experiment.md` (intelligence/transport, frame-density/cost,
> and the final human-ground-truth model-selection gate) and
> `milestone-d-au-ground-truth-owner-review.md`.
> **Do NOT implement yet — this document is the design to review before implementation.
> No canonical contract is modified by this document.**

---

## 0. What Asset Understanding owns (and does NOT)

Asset Understanding answers exactly one question:

> **"What useful Story material actually exists inside this Moment?"**

It does **NOT** own: final Story-coverage decisions · the next Director recommendation ·
global Moment ranking · final edit ordering · music · rendering. Those belong to future
**Story Coverage** (consumes `MomentUnderstanding`) and the future **Edit Planner**
(consumes `MomentUnderstanding.useful_segments`). Neither consumer is implemented in this
milestone. AU produces grounded per-Moment understanding; downstream systems make selection
decisions from it.

A hard conceptual boundary runs through the whole design: **OBSERVED REALITY** (what is in
the video, request-independent) is kept separate from **STORY-CONTEXT INTERPRETATION** (how
this Moment serves *this* request). The same media may later be re-interpreted under a
different Story context without re-observing it.

---

## 1. MomentUnderstanding contract (minimum, consumer-justified)

Every field below has a real consumer (Story Coverage / Director / future Edit Planner).
Fields that could not name a consumer were dropped (see §Rejected).

```jsonc
{
  "schema_version": "moment_understanding/1",          // see §3 versioning
  "moment_id": "uuid",                                  // the Moment this describes
  "source_capture_id": "uuid|null",                     // CaptureSession, when DIRECT
  "model_id": "us.anthropic.claude-sonnet-4-6",         // provenance (which model produced this)
  "evidence": { "kind": "frame_timeline", "n_frames": 24, "frame_policy": "au_frames/1" },

  // ───────── OBSERVED / ASSET-GROUNDED (request-independent) ─────────
  "observed": {
    "summary": "string",                                // concise whole-Moment summary
    "subjects": ["string"],                             // who/what matters
    "events": [                                         // ORDERED factual events
      { "start_time": 0.0, "end_time": 2.8, "description": "string" }
    ],
    "temporal_order_note": "string",                    // first/then/last; departure vs arrival,
                                                        //   reveal direction, progression, contradiction
    "useful_segments": [                                // ASSET-GROUNDED candidate material (NOT final cuts)
      { "start_time": 2.5, "end_time": 8.4, "why_useful": "string" }
    ]
  },

  // ───────── STORY-CONTEXT INTERPRETATION (depends on the request) ─────────
  "story_context": {
    "requested_shot_contribution": "string",            // does the footage serve the requested Shot purpose?
    "requested_beat_contribution": "string",            // how it contributes to the requested Beat
    "story_utility": "none | useful_elsewhere | strong_elsewhere"
  }
}
```

**`useful_segments` is asset-grounded, not Story-final.** It means *"coherent candidate
material worth considering for editing"*, e.g. `"complete action of subject picking up
backpack and exiting"` — **not** `"perfect opening for the TMB Story."` Final global
selection and ordering belong to the Edit Planner.

**Dropped for MVP** (no distinct consumer in the final experiment):
`environment` (subsumed by `summary`) and `dead_or_setup_segments` (weakly detected by every
finalist; segmentation value was carried by `useful_segments`). They may return **only if**
design reconciliation finds an existing consumer that genuinely requires them — none found as
of this freeze.

> This contract is the experimental AU schema MINUS the dropped fields, re-grouped into
> `observed` / `story_context`. Promoting it to a **canonical** contract (Pydantic + JSON
> Schema + Swift DTO + persistence model, the Milestone-B four-layer pattern) is an
> implementation step, **not done here**.

---

## 2. Frame extraction policy (`au_frames/1`) — FROZEN

```
Local Moment video (on device)
  → AVFoundation AVAssetImageGenerator (the proven C4 extraction path)
  → 24 ORDERED frames, evenly spaced across the full clip duration
  → each frame carries its timestamp (ms) — timestamps are REQUIRED
  → resize longest edge 768px, JPEG ~0.6 quality
  → total request payload ≈ 1–3 MB
```

- **Fixed 24 frames for all durations.** The density experiment found 24 is the quality/cost
  knee (12→24 is a real gain; 24→48 marginal; **96 regressed**). Not duration-scaled, not
  "every frame."
- Timestamps are passed to the model as `frameN@<t_ms>ms` alongside the images so temporal
  ordering is explicit.
- Extraction is on-device (no clip leaves the phone); only the derived frames cross the
  boundary (local-first media invariant preserved).
- Extraction cost is operational (sub-second, bounded CPU/battery) — not a dollar cost.

---

## 3. Prompt / schema versioning

- `frame_policy = "au_frames/1"` — the 24-frame/768px/timestamped policy above.
- `au_prompt_version = "au_prompt/1"` — the frozen AU instruction (observe the whole clip;
  ordered events with timestamps; temporal note; asset-grounded useful_segments; honest
  shot/beat/story_utility; observed events stay grounded regardless of the request).
- `schema_version = "moment_understanding/1"` — the §1 contract.
- All three version strings are recorded on every persisted `MomentUnderstanding` so a corpus
  re-score (§12) can tell which policy/prompt/schema produced a result. Bumping any of them is
  a new evaluation, not a silent change.

---

## 4. Model / ModelGateway configuration — FROZEN

| | |
|---|---|
| **Production model** | `us.anthropic.claude-sonnet-4-6` (frame-timeline / image path, Bedrock Converse) |
| Max output tokens | **2400** (↑ from 1800 — the only Sonnet failure in the gate was the 154s clip truncating at 1800; a larger allowance removes that failure mode) |
| Temperature | 0 |
| Evidence | 24 timestamped frames (§2) as Converse `image` blocks + one text block (prompt + schema + timestamps + capture_context) |
| Routing / escalation | **NONE.** One model, all durations. No Nova/Opus fallback, no Pegasus, no native video, no duration-based routing. |

Sonnet is reached through the **generic ModelGateway** (same interface the C-series engines
use) — AU does not get a bespoke client. The gateway already force-mints UUIDs / strips
model-supplied optional ids for structured-output contracts (see Milestone-B lesson); AU
reuses that discipline for any id fields the canonical contract later adds.

**Why Sonnet (the frozen decision):** on owner-approved ground truth it won the primary
grounded-understanding objective — highest event F1 (0.80), highest recall (0.85), fewest
hallucinations (10), strong segmentation (0.81), near-ceiling temporal (16/17) — at ~1/5 the
cost of Opus. Opus's marginally better temporal/reliability did not justify 5× cost when
Sonnet is more grounded on event extraction, the field the Edit Planner most depends on.

---

## 5. Retry / error policy — FROZEN

```
Sonnet call (2400 out-tok)
  → validate against MomentUnderstanding schema
  → if VALID:            persist, mark job complete
  → if malformed / truncated / provider failure:
        retry ONCE (same model, same evidence, same prompt)
        → if retry VALID: persist, mark job complete
        → if retry FAILS: leave the AU job RETRYABLE / pending (do NOT fall back to Opus/Nova)
```

- Exactly one retry. No model fallback in MVP — a persistent failure leaves the Moment's AU
  pending and is picked up by the queue later (§6), never silently dropped and never
  downgraded to a weaker model.
- Validation is strict and **outputs are never hand-repaired** (the gate measured reliability
  without repair; production honours the same rule).

---

## 6. Local persistent AU job state machine (iOS) — FROZEN

**Moment creation must NEVER block on AU.**

```
Moment added  →  enqueue AU job (persisted on device)  →  user continues immediately
```

Job states and transitions:

```
            enqueue
  (none) ─────────────▶ PENDING
                           │  eligible to run (app active / background-eligible / network up)
                           ▼
                        RUNNING ──success──▶ COMPLETE  (MomentUnderstanding persisted locally)
                           │
             failure/interruption (incl. the §5 single-retry already spent)
                           ▼
                        PENDING  (retryable; resumes on next eligibility)
```

- The queue is **persisted** (survives app kill/relaunch). On launch, any `RUNNING` job
  orphaned by a crash is reset to `PENDING`.
- Eligibility to run: while the app is active; when eligible background execution is available;
  when network becomes available; on a subsequent app activation. **No assumption of unlimited
  iOS background execution** — the queue is opportunistic and resumable, not a daemon.
- Backoff: a failed job waits (bounded exponential backoff) before re-eligibility, so a
  provider outage does not hot-loop.

---

## 7. Network / offline / resume behaviour

- Offline at capture: Moment is created and the AU job sits `PENDING`; nothing blocks.
- Network returns: eligible `PENDING` jobs run opportunistically.
- App killed mid-analysis: persisted job state is reloaded on next launch; orphaned `RUNNING`
  → `PENDING`; resumes.
- The individual App Runner request stays **synchronous** (p50 ~26s, p95 ~33s for Sonnet @
  24fr — comfortably inside the 120s budget). The **product** workflow is asynchronous via the
  on-device queue. These are deliberately decoupled: a sync model call inside an async product
  flow (see §8).

---

## 8. App Runner endpoint — FROZEN

```
POST /v1/asset-understanding          (existing App Runner service; new route)
  request:  { moment_id, source_capture_id?, capture_context?, frames: [ {t_ms, jpeg_b64} ×24 ],
              frame_policy, au_prompt_version }
  response: { MomentUnderstanding }    // §1 contract, schema-validated server-side
```

- Served by the **existing** App Runner service — the same always-on container that serves the
  C1–C3 interactive APIs. **No new compute.**
- Server path: route → `AssetUnderstandingEngine` → generic `ModelGateway` → Sonnet 4.6 →
  schema-validate → return.
- Request body is small (~1–3 MB of frames), well inside App Runner's request limits; the call
  returns synchronously inside the 120s budget.
- **No** temp-S3, **no** presigned upload, **no** SQS, **no** Lambda/Fargate worker, **no**
  Bedrock async invocation. See §Architecture-supersession.

---

## 9. Idempotency — FROZEN

- An AU job is keyed by `(moment_id, frame_policy, au_prompt_version, schema_version)`.
- Persisting a result is an **upsert** on `moment_id`: re-running the same Moment replaces its
  single `MomentUnderstanding` record — it never creates a duplicate understanding row.
- A retry (§5) or a resumed job (§6) that completes after an earlier partial attempt therefore
  cannot produce two records for one Moment. Safe to retry freely.
- If any version string changes, the key changes → a deliberate re-analysis, recorded as such.

---

## 10. Local persistence

- `MomentUnderstanding` is persisted on-device alongside the Moment (SwiftData), as the Moment's
  single current understanding record (per §9 upsert).
- The AU **job queue** is persisted independently of the result (so a pending/failed job
  survives relaunch even with no result yet).
- Originals never leave the device; only the 24 derived frames are transmitted and are not
  retained server-side after the response.

---

## 11. Privacy / logging

- Local-first invariant preserved: the clip stays on device; derived frames are transient
  request inputs, not stored in the cloud.
- Server logs record **metadata only** (moment_id, latency, token usage, valid/invalid, model_id)
  — never frame bytes, never the summary/subject text.
- No full Photos read permission is requested anywhere in AU (Photos add-only is a separate
  concern, §13).

---

## 12. Evaluation / regression plan

- **Frozen ground truth:** `evals/asset_understanding/ground_truth.json`
  (`au.ground_truth/1-approved`, 18 owner-approved clips).
- **Scorer:** `evals/score_au_finalists.py` (LLM judge, tolerant ±3s temporal matching;
  separates hallucination from over-segmentation; deterministic reliability without repair).
- **Regression gate:** any change to model, `au_frames/1`, `au_prompt/1`, or
  `moment_understanding/1` re-runs the 18-clip gate and must not regress Sonnet's frozen
  baseline (event F1 ≈ 0.80, hallucinations ≤ ~10, temporal ≈ 16/17, valid rate with the
  single-retry policy = 18/18). Baseline numbers live in the experiment report.
- **Optional pre-implementation strengthening:** expand ground truth 18 → ~30 clips for tighter
  confidence before coding (not blocking the freeze).

---

## 13. Photos persistence (companion, independent of AU model)

Design + implementation detail in `milestone-d-photos-persistence.md`. Summary:
successful Moment → Story working copy remains → original also saved to **Apple Photos
(add-only)**, fire-and-forget, never blocking or failing Moment creation; graceful degradation
on denial/failure; no full Photos read permission; duplicate storage accepted for MVP.
`PhotosSaver.swift` + the `NSPhotoLibraryAddUsageDescription` key are **implemented and complete**.
The Story iOS project uses `PBXFileSystemSynchronizedRootGroup` (objectVersion 77): every `.swift`
under `Story/` is automatically target-included, so `PhotosSaver.swift` compiles with **no manual
pbxproj edit** — there is no Xcode wiring open item. The only remaining step is the **physical-iPhone
verification** (checklist in that doc). This is deliberately **not entangled** with AU model selection.

---

## 14. Tests (planned for implementation, not built here)

- **Contract:** `MomentUnderstanding` round-trips domain ⇄ API DTO ⇄ SwiftData ⇄ JSON Schema
  (the Milestone-B four-layer discipline), observed/story_context separation preserved.
- **Engine:** `AssetUnderstandingEngine` returns a schema-valid result for a canned 24-frame
  fixture; malformed model output triggers exactly one retry then leaves the job pending.
- **Idempotency:** two completions for one `moment_id` yield one persisted record.
- **Queue state machine:** enqueue → run → complete; interruption → pending → resume; orphaned
  RUNNING reset on launch; offline enqueue does not block Moment creation.
- **Regression:** the §12 ground-truth gate.

---

## 15. Physical-iPhone acceptance plan

1. Capture a DIRECT Moment → it appears in Story immediately (AU does not block).
2. AU job enqueues; with network, it completes and a `MomentUnderstanding` is persisted.
3. Airplane mode at capture → Moment created, AU `PENDING`; restore network → AU completes.
4. Kill the app mid-analysis → relaunch → orphaned job resumes and completes (no duplicate).
5. Force a malformed/truncated response (test hook) → one retry → on repeated failure the job
   stays `PENDING`, never falls back to another model, never blocks the UI.
6. Long clips (95s, 154s) complete within the request budget with the 2400-token allowance.
7. Photos add-only save verified per §13's own checklist (independent).

---

## 16. Future Story Coverage integration boundary (NOT this milestone)

Story Coverage will read persisted `MomentUnderstanding` records (summary / subjects / events /
story_utility / shot+beat contribution) to decide what the Story has and what it lacks. AU
publishes understanding; Coverage decides coverage. AU must not pre-empt coverage decisions.

## 17. Future Edit Planner integration boundary (NOT this milestone)

The Edit Planner will consume `observed.useful_segments` (and `events`) as **candidate**
material and make the global selection/ordering decisions. AU's `useful_segments` stay
asset-grounded (§1) precisely so the Edit Planner — not AU — owns the final cut.

---

## Rejected alternatives (recorded for history)

| Alternative | Verdict | Why |
|---|---|---|
| **Nova Pro as default AU** | REJECTED | Weakest grounded quality on ground truth: event F1 0.56, 35 hallucinated events, temporal 9/18 — despite 100% validity and lowest cost. Not acceptable for a layer feeding Director + Edit Planner. |
| **Opus as default AU** | REJECTED | More temporal/reliability but Sonnet is **more grounded on event extraction** (higher F1/recall, fewer hallucinations) at ~1/5 the cost; Opus's edge did not justify 5× cost as the default. |
| **TwelveLabs Pegasus / native video** | REJECTED | §7 of the gate showed the gap was MODEL-limited, not evidence-limited: native video recovered **nothing** the 24-frame timeline lost (Pegasus temporal 10/17 < Sonnet/Opus), while demanding whole-video upload + temp-S3 + worker + a second model path. |
| **Native whole-video transport** | REJECTED for MVP | Operationally heavy (19–214 MB mobile upload, temp-S3, cleanup) for no quality win. |
| **48 / 96 / every-frame evidence** | REJECTED | 24 is the quality/cost knee; 48 marginal, **96 regressed**, every-frame unjustified. |
| **Model routing / escalation** | REJECTED | Duration did not predict semantic difficulty (6s/10s clips broke Nova harder than 154s broke Opus). Routing adds logic, a failure surface, a model dependency and an eval problem it did not earn. One model, all durations. |
| **Hierarchical multi-pass analysis** | DEFERRED | Not needed for MVP single-pass understanding; revisit only if a future consumer demands region-deep analysis. |

---

## Architecture supersession note

This freeze **supersedes** the earlier AU infrastructure assumption in `03-system-architecture.md`
(§"AssetUnderstanding: eager and parallel", eager server-side Bedrock fan-out) and
`04-aws-infrastructure.md` (presigned upload / SQS → Lambda/Fargate AU worker / temp-S3 for AU).
For the MVP, Asset Understanding uses **an on-device persistent job queue + the existing App
Runner inference endpoint**, with **no** temp-S3, presigned upload, SQS, Lambda/Fargate worker,
or Bedrock async invocation. The general async-scaling guidance in those docs still applies to
*other* future heavy jobs (generative media, rendering); it no longer describes AU.


---

## Scale / Bedrock throttling note (scale-time concern — NOT an MVP change)

Added 2026-10-05 after device verification. This records the throttling behaviour and the scale
path. **Nothing here changes the frozen MVP** — the MVP is already throttle-SAFE; these are the
levers for when real user volume arrives.

### Where the limit is
Bedrock on-demand is throttled per account+model+region on **requests-per-minute (RPM)** and
**tokens-per-minute (TPM)**. AU calls are **~21k input tokens each** (the 24 frames dominate; measured
13.7k–21.6k in / 0.6–1k out on device), so **TPM is the binding limit, not RPM**. Example: a ~200k
TPM quota allows only ~9 AU analyses/minute regardless of user count. A burst — e.g. 100 users each
finishing a trip and importing/capturing ~10 Moments at once — far exceeds that and WILL throttle.

### What the MVP already does under throttling (safe by design)
A Bedrock throttle surfaces as `ProviderError` → the engine's one retry (§5) → if still throttled,
`AURetryableError` → the endpoint returns **503** → the on-device queue leaves the job **PENDING with
bounded exponential backoff** (5s→20s→80s… cap 10 min) and retries on a later eligibility (§6). So
throttling means **"understanding lands later," never a user-facing failure or data loss** — exactly
the async property the design targets. Moment creation is never affected.

### Gaps at scale (not failures — capacity/efficiency)
1. **No server-side flow control** — every device calls Bedrock directly; under a burst, devices back
   off independently (uncoordinated thundering-herd retries) and effective throughput is still capped
   at TPM. Backoff prevents failure but creates no capacity.
2. **The one retry can burn both attempts** during a genuine spike before the device backoff kicks in.
3. **No concurrency cap** on the server — N devices = N concurrent Bedrock calls, bounded by nothing
   the service controls.

### Scale path (in order of leverage; build only when measured load requires it)
1. **Request a Bedrock TPM/RPM quota increase** (Service Quotas → Bedrock → Sonnet 4.6). Cheapest first
   move; usually enough for early cohorts. Do this when onboarding the first real users.
2. **Server-side token-bucket / concurrency gate** in the App Runner service in front of the
   ModelGateway: cap concurrent Bedrock calls to stay under TPM; return **503 (retryable)** when the
   bucket is empty. The device queue ALREADY handles 503 correctly, so this turns chaotic per-device
   backoff into coordinated flow control. **Highest-value change, fits the existing design, no new
   infra.** This is the recommended first real scale step.
3. **Provisioned Throughput** for Bedrock if volume becomes steady and high (reserved TPM, predictable,
   billed hourly whether used or not — only at real scale).
4. **The deferred SQS→worker architecture** (03/04) — a true server-side queue with centralized rate
   control + retries off the device. The frozen design left this as the escalation path precisely for
   this situation; the device queue is the MVP, the SQS worker is the scale answer. Do NOT reach for it
   until the in-service gate (#2) is proven insufficient.
5. **Cross-region inference profile** — the `us.` profile already load-balances across regions, raising
   effective throughput somewhat for free.

### Cost scales linearly and invisibly (separate from throttling)
At ~**$0.078/analyzed Moment** (measured, Sonnet 4.6 @ 24 frames, us-east-1 on-demand ESTIMATE
2026-10-05): 1,000 users × ~30 analyzed Moments ≈ **~$2,300/month in AU alone**. Throttling protects
*availability*; it does nothing for *spend*. If spend matters at scale, the frame count (24) and the
model are the levers — both already measured in the finalist/density experiments.

### Recommendation
- **Dogfood / early users:** do nothing — the device queue + backoff makes throttling a non-event.
  Request a TPM quota increase (#1) when the first real cohort onboards.
- **First real scale step:** add the server-side concurrency/token-bucket gate (#2). Do NOT build
  SQS/workers until measured load proves the in-service gate insufficient.
