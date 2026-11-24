# Story — Video Generation Latency Analysis (for optimization review)

**Purpose:** a complete, self-contained description of the three video-generation flows in the Story iOS app
and their backend, with measured latencies, where the time goes, and every optimization experiment already
tried. Hand this to an external reviewer to propose latency optimizations.

**Environment:** dev backend `story-development-api` (AWS account 989088054552, us-east-1).
Models: **Opus 4.6** (`us.anthropic.claude-opus-4-6-v1`) for the Edit Planner; **Sonnet 4.6**
(`us.anthropic.claude-sonnet-4-6`) as a fallback-on-ProviderError only; **Nova Lite** (`amazon.nova-lite-v1:0`)
for the lightweight NL revision interpreter. All via AWS Bedrock.

---

## 1. System architecture (how a video is made)

### Components
- **iOS app (SwiftUI + SwiftData).** Captures Moments (video clips), runs on-device Asset Understanding (AU)
  to summarize each Moment, builds the request, downloads the chosen soundtrack, and renders the final video
  locally with AVFoundation (MediaEngineV1). The device does the pixel work; the backend only plans.
- **API (FastAPI on AWS App Runner).** Stateless planning/endpoints. **Hard constraint: App Runner has a
  non-configurable ~120s HTTP request ceiling** — this is why planning was moved to an async job model.
- **Async job infra.** `POST /v1/edit-plan-jobs` returns a job id immediately → SQS → **worker Lambda** runs
  the Edit Planner (up to ~15 min) → writes the plan to DynamoDB → iOS polls `GET /v1/edit-plan-jobs/{id}`.
  There is also a 1-minute reconciler that re-enqueues any job whose enqueue was dropped.
- **Edit Planner (the expensive LLM step).** Opus 4.6, **multimodal**: the device sends one contact-sheet
  JPEG per Moment (so a 36-Moment Story = 36 images) plus a text prompt (frozen `edit_plan/5.2`). The model
  returns an `EditPlanV2` (ordered segments: asset_id, source in/out, output duration, speed, native-audio,
  transitions). A **deterministic validator** then checks executability; on failure a **bounded repair** pass
  (1 attempt) re-calls the model with the exact errors. On a ProviderError (throttle) it falls back to Sonnet.
- **NL revision interpreter (lightweight LLM step).** Nova Lite, text-only, `revision_interpret/2`. Turns a
  free-form instruction ("Start with Moment 5, then Moment 2") into typed directives (opening/ending/
  include/exclude/order). ~0.6–1.1s. Only called when the on-device deterministic parser cannot fully cover
  the instruction.
- **Music.** Separate: `/v1/music/candidates` (ranked tracks), `/v1/music/soundtrack` (download), analysis;
  the soundtrack is a render-time overlay (the renderer loops/fades it to the video length).

### Request shape sent to the Edit Planner (multimodal)
- `moments[]`: for each Moment `{id, duration_seconds, useful_segments, summary}` (text only — the planner is
  otherwise text; the contact-sheet images are the multimodal addition).
- 1 contact-sheet JPEG per Moment (bounded by an adaptive visual budget: resize → compress → fewer frames →
  fewer Moments). A 36-Moment Story sends 36 images, a few MB total.
- Optional `revision_context` (directives + soft_direction) for "another version" / "revise".
- Frozen `edit_plan/5.2` system prompt + a per-request creative brief in the USER message.

---

## 2. The three flows

### Flow A — First generate ("Create my Story")
1. On-device AU for each Moment (serial, Sonnet, device-driven) — happens earlier, not in the create path.
2. Duration recommendation (1 Opus call, ~1s) — advisory.
3. Music resolve: candidates + download the chosen track.
4. **Submit edit-plan job → worker runs Opus 4.6 multimodal (36 sheets) → validate → (repair if needed).**
5. iOS polls to completion, then **renders locally** (AVFoundation) and muxes the soundtrack.

### Flow B — Create another version (Explore)
Same as A, but carries `revision_context.mode=explore` (prior-plan digest) so the new plan differs. By owner
decision the **critique/refinement pass is OFF by default**, so this is **1 planning call**, not 3. (A prior
version ran 3 calls — 1 plan + 2 critique/revision — measured at 167s; disabling critique removed 2 calls.)

### Flow C — Revise (natural-language change on a selected version)
1. **NL interpret:** deterministic on-device parse first; if incomplete, call `/v1/interpret-revision`
   (Nova Lite, ~0.7–1.3s) → typed directives.
2. Preflight validation (contradictions / unknown refs / over-exclusion) — instant, no model.
3. Carry the base version's soundtrack forward (resolve the known track directly).
4. **Submit edit-plan job with `mode=revise` + the exact base plan + directives → worker Opus 4.6 multimodal.**
   - A **deterministic fast path** exists for pure structural directives (reorder/prune of the base plan with
     NO soft_direction) = **0 model calls**. Any soft/creative clause or broad change falls to the model path.
5. Validate → (repair) → poll → render locally, reusing the base soundtrack.

---

## 3. Measured latencies (real dev jobs, worker wall time)

| job | flow | status | wall time | model calls | repairs | mode | sheets |
|---|---|---|---|---|---|---|---|
| 8f3efc20 | revise (clean directives) | completed | **36s** | 1 | 0 | multimodal | 36 |
| 1545575c | first/another version | completed | **46s** | 1 | 0 | multimodal | 36 |
| ca1504ee | another version | completed | 45s | 1 | 0 | multimodal | 36 |
| 246d88b8 | another version | completed | 46s | 1 | 0 | multimodal | 36 |
| e045ec48 | revise (compound) | completed | **76s** | 3 | 0 | multimodal | 36 |
| 7d9010b2 | revise (compound, 1 repair) | completed | **172s** | 4 | 1 | multimodal | 36 |
| (historical) | another version w/ critique ON | completed | **167s** | 3 | — | multimodal | — |
| interpret (Nova Lite) | NL interpret | ok | **0.6–1.3s** | 1 | — | text | 0 |

**Reading the numbers:**
- A clean single Opus multimodal call over 36 sheets ≈ **36–46s**. This is the floor today.
- Each extra model call adds ~35–45s (they are sequential): 3 calls ≈ 76s, 4 calls (incl. a repair) ≈ 172s.
- The NL interpret step is cheap (~1s) and is NOT the bottleneck.
- On-device render (AVFoundation) is separate and typically seconds, not the dominant cost.

**The dominant latency driver is the number of sequential Opus-4.6 multimodal calls, each carrying ~36 images.**
A first pass that validates cleanly = 1 call. Repairs, critique, and model fallback each add a full call.

---

## 4. Where the time goes (decomposition of a single Opus multimodal call)
- **Input:** 36 contact-sheet JPEGs (a few MB) + the text prompt. Image tokens dominate the input.
- **Inference:** Opus 4.6 generating a ~14–25-segment structured plan (thousands of output tokens).
- Per-call cost scales with (image count × resolution) on input and (segment count) on output.
- Sequential dependency: repair/critique calls cannot start until the prior call returns and is validated.

---

## 5. What makes a run take MORE than one call (the real latency multipliers)
1. **Executability repair** (+1 call). The first plan fails the deterministic validator (duration tolerance,
   segment min-length, speed bounds [0.5–2.0], source-range-in-useful-segment, OR a hard directive like
   "ending must be Moment 6"). Hard directives make the first pass tighter → more repairs. (Fixed-cause
   example: an over-constrained/invented exclude set forced a repair that still failed — job 7d9010b2.)
2. **Critique/refinement** (+2 calls). A critique pass then a revision pass. **OFF by default** by owner
   decision precisely for latency; turning it on triples the call count.
3. **Model fallback** (+1 call). Opus throttles (ProviderError) → retry on Sonnet. Historically Opus 4.6 was
   throttled heavily during bursts (152 throttles in a 2h window in one audit); Sonnet is a separate quota.
4. **Truncation escalation** (+1 call). A plan that hits max_tokens retries once at a higher cap.

---

## 6. Optimization experiments already run (and outcomes)

These are prior A/B/experiments on edit quality and latency; they bound what NOT to re-try:

1. **Critique/refinement default = OFF.** Turning critique on added 2 calls (167s vs ~46s) for marginal
   editorial gain; owner set it OFF. Biggest single latency win already taken.
2. **Multimodal vs text-only planning.** Multimodal (contact sheets) helped source-range nuance and found a
   payoff shot, but it is the per-call cost multiplier (images). A text-only A1 path exists as the graceful
   fallback and is far cheaper per call. Per-frame image blocks overflow Converse's "Input is too long" at
   36+ Moments, so the design tiles ONE contact sheet per Moment (not per frame).
3. **Richer AU text forwarding (A0→A1).** Forwarding richer existing AU prose to the planner (bounded ~1400
   chars/Moment, +152 tokens/Moment) beat adding new structured fields; near-free, improved editorial variety.
   Lesson: the biggest quality lever was text forwarding + a brief/critique pass, NOT more pixels.
4. **Async job model.** Moved planning off the synchronous App Runner request (which has a ~120s ceiling that
   was severing long plans mid-response) to SQS + worker Lambda (up to ~15 min). This fixed correctness
   (plans no longer lost) but did not reduce per-call latency.
5. **Opus→Sonnet fallback.** Added to survive Opus throttling, not to speed anything up — a fallback is an
   EXTRA sequential call.
6. **Deterministic revision fast path.** Pure structural revises (reorder/prune of the base plan, no soft
   direction) run with **0 model calls**. The win only applies when there is no creative/soft clause.
7. **Bounded executability repair (1 attempt).** Keeps a bad first plan from looping, but each repair is a
   full extra multimodal call.
8. **Short-form editing A1/A1c/B/C/D experiment** (30s, girl_with_dress + hiking): the largest engagement win
   was explicit creative direction + a bounded critique/revision pass (arm D), NOT multimodal frames; images
   (arm B) were the first to hit the Bedrock daily token quota. Confirms images are expensive for their
   marginal benefit.
9. **Duration recommender** is a separate ~1s Opus call; advisory, not on the critical planning path.

### Known throttle/quota facts
- Opus 4.6: ~10k RPM / 3M TPM. Sonnet 4.6: ~10k RPM / 6M TPM (separate bucket). AU (Sonnet) is device-serial.
- One SQS queue + one worker Lambda (reserved concurrency 2, batchSize 1) shared by Edit Planning AND async
  Coverage; a long job can delay another in the 2 shared slots. Recommended (not yet done): SQS
  MaximumConcurrency to reserve headroom for Edit Planning.

---

## 7. Candidate optimization directions (for the reviewer to evaluate — NOT yet implemented)
These are hypotheses, not decisions. Frozen prompts/contracts (`edit_plan/5.2`, `EditPlanV2`) must not change
without versioned approval.
- **Cut image payload:** fewer/smaller contact sheets, or send sheets only for Moments the plan is likely to
  use; adaptive-budget already resizes/compresses but still sends one per Moment.
- **Reduce repair frequency on directive-heavy requests:** a tighter first-pass prompt (versioned) so hard
  opening/ending/order plans validate on the first try — removes the +1 repair call.
- **Text-only revise path:** a revise that only reorders/trims existing segments may not need the 36-image
  multimodal call at all (the deterministic fast path already proves 0-call structural edits).
- **Parallelize nothing that's truly sequential, but cache:** identical (fingerprinted) requests already
  reuse a cached plan; broaden caching to near-identical revises.
- **Smaller/faster model for the first pass**, Opus only on repair — unverified tradeoff on quality.
- **Streaming/partial results** to the device so perceived latency drops even if wall time is similar.
- **Worker warm-start / concurrency:** the Lambda cold start + the 2 shared slots add tail latency under load.

---

## 8. Hard constraints to respect in any proposal
- App Runner ~120s request ceiling → planning MUST stay async (job model).
- Frozen `edit_plan/5.2` prompt + `EditPlanV2` contract: additive/versioned only.
- Renderer speed bounds [0.5x, 2.0x]; the deterministic validator is authoritative and must stay.
- Device does the rendering; the backend never has the media files.
- Music is a render-time overlay; the soundtrack must survive a revise (carried by trackId).

---

## 9. One-paragraph problem statement (for ChatGPT)
"Story generates short videos by having an Opus-4.6 multimodal model (fed ~36 contact-sheet images) produce a
structured edit plan on an AWS Lambda worker, which the iOS device then renders locally. A clean plan is one
model call (~36–46s); the latency balloons to 76–172s whenever the run needs extra SEQUENTIAL model calls —
an executability-repair pass, a critique/refinement pass (off by default), a truncation retry, or an
Opus→Sonnet throttle fallback — each adding ~35–45s because every call re-sends the full image payload. The
NL-interpret step (Nova Lite, ~1s) is negligible. We cannot change the frozen plan prompt/contract without
versioned approval, planning must stay async (App Runner's 120s ceiling), and the device owns rendering. How
do we minimize end-to-end latency for first-generate, another-version, and revise without degrading edit
quality?"
