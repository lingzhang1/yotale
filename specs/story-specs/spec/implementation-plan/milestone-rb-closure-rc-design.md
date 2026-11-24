# Milestone R-b Closure + R-c Create/Result Design Reconciliation

**R-b status:** Case G ACCEPTED on device (first real render). B/F now exercisable via DEBUG fixtures;
D-speed exercisable; **D-crossfade is a real engine gap (documented, not faked).** R-c = DESIGN ONLY here.
Nothing pushed. Creative Editing V2 NOT started.

Commits (app): Case G `0a1cb28`, visible entry `8236b8c`, id-case fix `9a0c353`, D/F fixtures + picker (this).

---

## 1. R-b remaining checks

### B — Native audio (device listen required)
The accepted Case G render contains **1 audio track**; probe of the exported MP4 = 720×1280, 30fps, 9.0s,
upright. The capture-audio mix applies keep=1.0 time-ranged with 0.08s ramps. **Audibility + sync is a direct
LISTENING check only** — I cannot hear the file. STOP for owner: play the exported MP4 and confirm the guitar
is audible, in sync, no discontinuity. Code path verified; perceptual check is device-only.

### D — Crossfade and speed
- **Speed (0.5x / 2.0x): exercisable now.** New DEBUG fixture `DebugEditPlanFixture.speedCases` (seg0 0.5x,
  seg1 2.0x, output_duration = span / speed). The engine implements speed via `scaleTimeRange`. Device check:
  harness → fixture → "Speed 0.5x/2x (D)" → render → confirm slow-then-fast, no black frames.
- **0.3s crossfade: NOT IMPLEMENTED (genuine R-b gap).** `MediaEngineV1.buildComposition` builds a single
  video-composition instruction with per-segment transforms and **straight cuts only** — no overlapping track,
  no opacity ramp — and the renderer `EditSegmentV2` DTO does not even decode a `transition` field. The frozen
  Opus prompt also emits `transition=none` today. So crossfade cannot be verified without ENGINE work (a second
  video track + overlap window + opacity ramp during the transition). Per the task ("do not alter the Opus
  prompt to force these effects") I did NOT fake it. **Recommendation:** implement crossfade as its own small
  verified batch (R-b.1) OR defer to R-c; it is V1-scope ("basic crossfades where supported") but was never
  built. Flagged for owner decision — NOT silently closed.

### F — Missing Moment: exercisable now.
New DEBUG fixture `DebugEditPlanFixture.missingMoment` (seg0 = unresolvable all-zero UUID, segs1-2 valid). The
engine throws `MediaEngineError.missingMoment` on the first unresolved id BEFORE export, so there is no partial
MP4 and no silent skip; source Moments are read-only (never written). Device check: harness → fixture →
"Missing Moment (F)" → expect a clear "Render failed: missingMoment(…)" status and NO result.

### R-b closure verdict
Case G (the primary goal) is **device-accepted**. B needs a 30-second listen; D-speed + F need a device tap each
(fixtures shipped); **D-crossfade needs engine work before it can pass.** I am NOT marking R-b fully CLOSED while
crossfade is unimplemented and B/D-speed/F are unrun on device — that would be claiming an unverified pass.
R-b is **substantially accepted, closure pending**: (a) owner runs B/D-speed/F, (b) owner decides crossfade now
(R-b.1) vs deferred.

## 2. First-video quality findings (honest)
- Coherent **three-shot sequence**: fretboard close → picking detail → wider performance. Narrative order tracks
  the Story Guide arc. GOOD for a first execution.
- **Simple straight-cut montage** — no transitions, no pacing sophistication. Expected: the engine does cuts.
- The **guitar-learning narrative is not fully told by 9s / 3 similar clips** — this is a SOURCE-FOOTAGE limit
  (one framing family, no "struggle→breakthrough" range), NOT a Media Engine defect. More/varied Moments would
  give the planner material to shape.
- Native-audio **quality** is unverified pending a listen.
- This is **execution proof, not finished cinematic quality.** Not claimed otherwise.

## 3. R-c Figma reconciliation (Create My Story → Result)
Frozen Figma (`prototypes/story-figma/src/App.tsx`): **Create my Story → Screen10Creating** (italic "Creating
your Story…", rotating status lines, thin progress bar; ~fixed-time simulation) **→ Screen11Result** ("Your
Story is ready.", play/preview, feedback, change-music/re-edit, implicit save/share). Music line is present but
disabled in the native build (M-c). The simulation has NO real plan/render — R-c replaces that with the real
pipeline while keeping the exact visual surface.

## 4. Current → target flow (R-c, no-music)
```
Story Home → Create my Story
  → [Creating] prepare Story intelligence (persisted CreativeIntent + completed MomentUnderstanding[])
  → (MusicPlan: SKIPPED — no production MusicPlan engine; no-music mode)
  → POST /v1/edit-plan (real Opus 4.6) → EditPlan/2
  → local validation + asset resolution (case-insensitive id → MediaStore file)
  → MediaEngineV1.render → local H.264 MP4 (RenderOutputStore)
  → persist a GeneratedOutput (real: file path + plan provenance, NOT the mock)
  → [Result] playback (AVPlayer) + Save to Photos / Share to Files
```
The DEBUG harness stays as the engineering surface; R-c is the CONSUMER surface (no diagnostics, no raw plan).

## 5. Creation lifecycle (design)
States: `idle → planning (/v1/edit-plan) → validating → rendering (progress) → done | failed | cancelled`.
- **Progress:** drive Screen10's bar from real `MediaEngineV1.render` progress (0→1), not a timer.
- **Cancellation:** harness already supports `shouldCancel`; Result-flow Cancel returns to the preview, cleans
  partial output (engine already deletes partial files on cancel/fail).
- **Failure/retry:** 503 (planner) / 422 (infeasible, show the reason) / missingMoment / export failure →
  friendly message + Retry; NEVER a fabricated montage, NEVER a partial MP4. Preserve the Story + Moments.
- **Persistence:** rendered MP4 in `<Documents>/rendered/<uuid>.mp4`; a real `GeneratedOutputModel` records the
  path + source Moment ids + plan provenance (duration, segment count, model). Survives relaunch.
- **Reopening:** Result screen for a completed Story loads the persisted output file.
- **Invalidation when Moments change:** if a Story's Moment set changes after a render, mark the output STALE
  (fingerprint of source Moment ids, like the Coverage/Guide staleness seam) and offer re-create — do not
  silently show an outdated video.
- **Duplicate-job guard:** a per-Story `isRendering` flag; a second Create tap while rendering is a no-op.

## 6. Persistence / cancellation summary
Reuse the existing `RenderOutputStore` + a new real `GeneratedOutput` (replace the Milestone-A mock). No new AWS
infra (on-device render; backend only plans). No duplicate render jobs. Source Moments never mutated/deleted.

## 7. Minimum R-c implementation scope (NOT built here)
1. Real `GeneratedOutput` persistence (file path + provenance), replacing the mock `createStoryOutput`.
2. A `StoryCreationCoordinator`: Story → `EditPlanRequestBuilder` → `/v1/edit-plan` → validate → render →
   persist, with the lifecycle states + duplicate guard + staleness fingerprint.
3. Wire Screen10Creating to real progress; wire Screen11Result to the persisted MP4 (AVPlayer + Save/Share).
4. Enable the Figma "Create my Story" button (currently a disabled `StoryUnavailableButton`) in no-music mode.
5. Failure/retry UX per §5. Keep the DEBUG harness separate and unchanged.
6. Tests: coordinator state machine, persistence/reopen, staleness, failure routing; parse-clean + XCTest.

## 8. Physical-device acceptance plan (R-c)
Create a Story (≥3 analyzed Moments) → Create my Story → see real progress → Result plays the real MP4 →
Save to Photos / Share → relaunch shows the same output → add/remove a Moment → output marked stale, re-create
works → force a planner failure (airplane mode) → friendly retry, Story intact.

## 9. Contract gaps
- **Crossfade:** EditPlan/2 CAN carry a transition (frozen contract has it), but the renderer DTO does not decode
  it and the engine does not render it. No frozen-contract change needed — this is an ENGINE gap. (R-b.1 or R-c.)
- Otherwise none: `/v1/edit-plan` + EditPlan/2 + MediaEngineV1 cover the no-music R-c flow as proven by Case G.

## 10. Recommended R-c sequence
R-b.1 (optional, small): implement + device-verify the 0.3s crossfade in the engine → closes Case D fully.
Then R-c: (1) real GeneratedOutput + coordinator → (2) wire Creating/Result screens → (3) enable Create button →
(4) failure/retry + staleness → (5) tests → (6) device gate. Production music (paid Epidemic) and Creative
Editing V2 (match cuts / motion / speed ramps / sound bridges / color / layers / split-screen / masking —
needs the R-a Edit Evidence experiment) remain SEPARATE, NOT started.

## 11. Creative Editing V2 backlog (recorded, not implemented)
match cuts · motion continuity · speed ramps · sound bridges · color matching · layered compositions ·
split screens · masking → all require the separate Edit Evidence experiment (R-a design). AU/Edit-Planner
contracts NOT reopened.

---

# R-b.1 — Crossfade IMPLEMENTED (2026-10-08). Device verification pending. App commit 7ec3762.

Owner authorized building the 0.3s crossfade. Done as a real engine change (NOT fake). Parse-clean; the actual
render is the device gate — swiftc -parse is NOT a render claim.

## Transition semantics (DECISION — no contract change)
Frozen `TransitionType = {cut, fade, dissolve}` (ai_contracts.py, UNCHANGED). The renderer maps:
- **`dissolve` = crossfade** (both clips visible, cross-dissolving opacity) — the standard meaning, and what
  Case D wants. `duration_seconds` defaults to **0.3** when omitted.
- **`fade`** = a single-clip fade (NOT a crossfade) — `crossfadeSeconds = 0`, so `fade` is never rendered as a
  fade-to-black-as-crossfade (the forbidden simulation).
- **`cut`** = straight cut (zero overlap).
This is an interpretation in the RENDERER only; the frozen contract is untouched. Not ambiguous enough to STOP:
`dissolve` is the unambiguous cross-dissolve type.

## Implementation (`MediaEngineV1.buildComposition`)
- **Two video tracks (ping-pong):** segment i on track i%2, so adjacent segments can OVERLAP. A cut is just a
  zero-overlap placement — the two-track arrangement is a superset of the old single-track cut path.
- **Overlap:** a `dissolve` on segment i pulls its start back by the clamped crossfade (< min(neighbour
  durations) − 0.05 so the timeline can never invert).
- **Opacity ramps:** per-time-range `AVVideoCompositionInstruction`s — solo ranges show one track; the overlap
  range shows both with outgoing opacity 1→0 and incoming 0→1 (incoming drawn over outgoing). No black frames
  (both layers are opaque footage through the blend), no fade-to-black.
- **Orientation/crop preserved through the transition:** each track's aspect-fill transform is set on BOTH the
  solo and overlap instructions.
- **Output duration:** total = Σ outputDuration − Σ overlaps (one 0.3s per dissolve) — the fixture asserts it.
- **Audio:** two capture tracks (A/B) matching the video ping-pong; each segment ramps in/out over its own
  range with the 0.08s click-guard, and the outgoing ramp-out coincides with the incoming ramp-in across the
  overlap, so the mix never spikes. keep/duck/mute preserved. No model curves.

## Fixtures + picker (DEBUG only, not in Release)
`DebugEditPlanFixture`: `montage` (cut) · `crossfade` (0.3s dissolve) · `speedCases` (0.5x/2x) · `missingMoment`
(unresolvable id). Harness `FixtureCase` picker selects all four; real-plan toggle unchanged.

## Tests (VERIFIED HERE — deterministic, no media)
transition decode; dissolve→0.3 / fade→0 crossfade mapping; crossfade fixture overlap + duration arithmetic;
speed→duration consistency; missing-Moment fixture unresolvable-first-segment; plus the pre-existing 8. REQUIRES
XCODE/DEVICE: the XCTest RUN + the actual crossfade RENDER (opacity blend, no black frames, audio continuity).

## Updated device acceptance checklist (B / D / F)
Rebuild in Xcode (new/changed files in target). Create preview → DEBUG → Render Test (dev).
- **B — native audio:** real-plan render → play → guitar audible, keep preserved, in sync, no discontinuity.
- **D — crossfade:** fixture → "Crossfade 0.3s (D)" → play → a REAL 0.3s cross-dissolve between clips, NO black
  frames, no stretch, audio continuous across the blend.
- **D — speed:** fixture → "Speed 0.5x/2x (D)" → play → seg1 slow, seg2 fast, audio synced, no black frames.
- **F — missing Moment:** fixture → "Missing Moment (F)" → clear "missingMoment" error, NO output, Moments intact.

## R-b.1 fix — exportFailed("Operation Stopped") on crossfade (app 7bb5755)
First device run of the crossfade fixture failed at export with `exportFailed("Operation Stopped")` and no
output file (diagnostics: planned 8.4s / 3 segments / dissolve, output size "—"). ROOT CAUSE: an invalid
`AVVideoComposition` timeline. `instructions` MUST tile `[0, total]` contiguously with NO gaps and NO overlapping
time ranges; the first implementation built instructions per-segment and DOUBLE-COVERED the crossfade window
(segment i's overlap instruction and segment i+1's solo instruction both began at the same boundary), which
AVAssetExportSession rejects outright. FIX: rebuild instructions by a BOUNDARY SWEEP — collect every segment
start+end, sort/dedupe, emit exactly one instruction per `[t_k, t_{k+1})` slice; a slice with 1 live segment is
solo (full opacity), 2 live segments is the crossfade (outgoing 1→0, incoming 0→1, drawn on top). Contiguous
non-overlapping coverage by construction. Added an arithmetic regression test locking the solo|crossfade|solo
|crossfade|solo tiling for the 3×3s/0.3s case.

## DEVICE ACCEPTANCE — RESULTS (2026-10-08, physical iPhone)
Owner rebuilt and rendered all three fixtures; all exported real MP4s (probed off-device):
- **Crossfade (D): PASS** — 8.40s (= 3×3.0 − 2×0.3), 720×1280 @30fps, 1 audio track. Frame inspection at both
  overlap midpoints (2.85s, 5.55s) shows a REAL cross-dissolve — two guitar clips blended at ~50% opacity, no
  black frame, upright/no stretch. The "Operation Stopped" failure is gone.
- **Speed (D): PASS** — 7.00s (0.5x→4s + 2.0x→1s + 1.0x→2s), 720×1280 @30fps, 1 audio track. Speed scaling
  demonstrably applied (would be 6s unscaled).
- **Montage (A): PASS** — 12.00s, 720×1280 @30fps, 1 audio track.

## Closure
**Case D (crossfade + speed) and Case A: CLOSED on device.** R-b REMAINS PENDING on the two gates that need the
owner's direct observation and cannot be verified off-device:
- **B — native audio:** audible guitar + sync is a listening check only (track present; gain path verified).
- **F — missing Moment:** owner runs the "Missing Moment (F)" fixture → confirm clear error, no output, Moments
  intact (engine throws `missingMoment` pre-export by construction, but the on-device UX is the gate).

When B and F are confirmed, R-b is CLOSED and R-c implementation is the next milestone (design already written
above — no re-reconciliation needed).

## R-c IMPLEMENTATION COMPLETE (2026-10-09) — awaiting device acceptance
Built in 4 verified batches on app `master` (not pushed), tests-first, mock removed from the consumer path.
- Batch A `752714e`: real GeneratedOutputModel persistence (file ref + sourceMomentIds + FNV-1a fingerprint +
  provenance + dimensions + isStale; no video bytes in SwiftData, migration-safe) + StoryCreationCoordinator
  (8-state lifecycle idle/preparing/planning/validating/rendering/completed/failed/cancelled, music-ready nil
  seam, 10 pre-AVFoundation validations, duplicate guard, cancel/retry; reuses EditPlanRequestBuilder +
  EditPlannerService + MediaEngineV1 + RenderOutputStore) + 17 tests.
- Batch B `fe123bf`: StoryCreatingView (coordinator-driven real progress, cancel/retry, no fake timer) +
  StoryResultView (AVPlayer playback, Save to Photos via PhotosSaver, Share to Files, reopen persisted output,
  stale->Re-create keeping old output, honest no-music copy, Change-music disabled until R-d) + 16 tests.
- Batch C `7956ad4`: real consumer Create My Story on Story Home + preview, readiness-gated by the SAME rule as
  EditPlanRequestBuilder (>=1 Moment with local file AND completed AU; test asserts agreement), honest status
  copy, mock GeneratedOutput removed from consumer path (DEBUG-only now), DEBUG harness intact + 13 tests.
- Batch D `2361538`: failure/regression coverage (transport/503+retry/422/invalid-plan/cancel+source-preservation/
  duplicate/persistence/reopen/staleness/recreation) + 10 tests. Audit found NO production bug; source Moments
  never deleted on any failure path.
TOTAL 56 deterministic tests; all touched Swift parse-clean. Backend /v1/edit-plan verified LIVE (422 on empty).
No new AWS infra, Epidemic off. DEVICE-GATE (not claimed): real render/export, AVPlayer, Save/Share, XCTest run,
@Model/@Observable macro build — need Xcode/iPhone. R-c NOT marked closed until owner device acceptance (14-step
checklist). STOP before R-d. Fingerprint semantics: source-media replacement under an unchanged Moment id DOES
invalidate (relativePath+duration in the hash).

---

## R-c BLOCKER FIX — Edit Planner executability repair (2026-10-09, device-reproduced, deployed)

ROOT CAUSE (confirmed from App Runner logs + deterministic repro). The R-c app flow worked end-to-end on device
(Home enable, Create, Creating lifecycle, honest 503 failure + Try again, no fake montage, Moments preserved),
but PLANNING failed: the real Opus call returned schema-valid but NON-EXECUTABLE plans that the deterministic
validator correctly refused (503, never fabricate). Two real device failures (corr ids in logs):
  (1) `total output 15.0s is >20% off target 12s` — segment outputs summed past the ±20% tolerance;
  (2) `seg3: output 2.5s inconsistent with source span 7.5s @ speed 1.0 (expected ~7.5s)` — output ≠ span/speed.
There was NO executability-repair feedback: a non-executable plan went straight to StructuredOutputError→503, so
Opus never saw its own arithmetic error. SEPARATE latent bug: dict-shaped `useful_segments` hit `u[0]`→KeyError→
unhandled 500 (the device sends `[[a,b]]` pairs and never hit it; a malformed/legacy shape would).

FIX (owner-approved C+D; commit story 5be33ba). NO EditPlan/2 contract change, NO model comparison.
- SHARED TIMELINE ARITHMETIC: one source of truth (`SegmentTimeline`, `timeline_total_seconds`,
  `_useful_ranges`) used by BOTH the validator and the repair/normalize layer, so they cannot disagree. The
  total accounts for crossfade overlap (a crossfade overlaps two clips, shortening wall-clock).
- PROMPT edit_plan/3 (prompts/edit_plan/3/system.md). v2 body VERBATIM + ONE added section "EXECUTABILITY
  INVARIANTS (MECHANICAL)" stating the pre-existing validator rules in the model's terms: valid source range;
  output = (source_end−source_start)/speed; total within ±20% of target; transitions accounted for; Story target
  beats track length; honest infeasibility (feasible=false, never invent footage). NO change to creative
  selection / narrative / native-audio / music-alignment. edit_plan/2 PRESERVED on disk for reproducibility
  (switch _PROMPT_PATH back to "2" to reproduce pre-R-c behavior). Contract schema_version stays edit_plan/2.
- SAFE DETERMINISTIC NORMALIZATION (`normalize_plan`): the ONLY auto-correction is snapping a segment's redundant
  output_duration to the exact span/speed when already within 0.15s (a rounding artefact). NEVER truncates a
  source range, changes speed, drops/reorders a segment, or alters emphasis. A 7.5s-span-vs-2.5s mismatch is NOT
  snappable → goes to model repair.
- EXECUTABILITY-REPAIR LOOP (`RealEditPlannerEngine`, MVP bounded): generate → normalize → validate → if invalid,
  ONE additional model turn carrying the EXACT validator errors + the model's own bad plan, asking it to fix only
  those while preserving narrative intent → normalize → revalidate → else honest fail. Deterministic validator
  ALWAYS authoritative; model never self-certifies. No nested/duplicate loops (model_calls ≤ 2).
- ERROR SEMANTICS: MalformedPlanError → 422 ("input malformed", no 500); infeasible → 422; model-invalid-after-
  repair → 503 "could not be made executable; retry" (distinct detail from provider outage → 503 "temporarily
  unavailable"). iOS already maps 503→retryable, 422→infeasible/needs-material.

TESTS: 28 edit-planner tests (both device failures reproduced deterministically; safe-rounding; large-mismatch
NOT normalized; repair success; repair-still-invalid → structured fail; bounded no-dup-loop; no invented ids;
crossfade duration accounting; native-audio + music-alignment unchanged; malformed→422; dict-shape tolerated;
503 distinct). Full backend suite 135 passed, contracts 60 passed, eval validator self-test 8/8.

RELIABILITY (live Opus us.anthropic.claude-opus-4-6-v1, 5 frozen scenarios + 1 adversarial 6s-target guitar,
NO-MUSIC): first-pass executable 6/6; 4 clean, 1 safe-normalized, 1 honest-infeasible (30s material vs 60s
target); 0 model repairs needed, 0 final failures. ~27k tokens total, avg 9.7s/call, ≈$0.68. The v3 invariants
ELIMINATED the arithmetic-failure class on first pass; the repair loop is the backstop (its live path was not
triggered because first-pass kept succeeding — repair-loop correctness is proven by the deterministic SeqGateway
tests, not claimed from a live retry).

DEPLOY (existing authorized env only). Built via CodeBuild story-rb-caseg-build (S3-zip source → ECR
story-development-api:latest, buildspec fixed to the project's ECR_URI env) → App Runner start-deployment →
RUNNING. Verified: /health 200; malformed useful_segments → 422 (was 500); real Guitar-Practice-shape request →
200 executable (3 segments, each out=span/speed, total 12.0s=target); success log carries repair diagnostics
(first_pass/normalized/repaired/model_calls), no secrets/private media. No new infra, Epidemic off.

STATUS: backend fix COMPLETE + deployed + verified server-side. R-c still at the PHYSICAL-DEVICE gate — owner must
repeat Create on the Guitar Practice Story and confirm planning now succeeds (or fails honestly), real render,
Moments intact, retry, no fake footage/soundtrack. R-c NOT closed until that. STOP before R-d.

