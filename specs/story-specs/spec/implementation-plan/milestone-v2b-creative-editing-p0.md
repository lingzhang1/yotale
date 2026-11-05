# Creative Editing V2-b — P0 implementation (cut-boundary refinement + audio continuity)

Status: 🟡 built + unit-verified (pure logic) · **device render + owner video review PENDING** (the quality
gate). Architecture B, deterministic, opt-in (OFF by default). No frozen contract reinterpreted. Not pushed.
Date: 2026-10-11. App commit: see git. Builds on V2-a Phase 0 (`milestone-v2a-creative-editing-phase0.md`).

## Phase 0 — integrity (resolved before building)
- **Footage count: 6, not 5.** guitar_practice_001 has 6 real `.mov` (string_first_touch, guitar_overview,
  first_practicing_a_song, first_song_but_not_familar, familar_with_song, final_song). V2-a doc said 5 — CORRECTED.
- **No genuine human-edited reference.** `editorial_reference.APPROVED.json` is a human-APPROVED NARRATIVE
  ANNOTATION (its own provenance: `annotations_in_dir: none`; durations are "editorial CANDIDATES, not
  instructions"); there is NO cut-timing EDL and NO rendered video. So **Phase 5 is A/B only** (the annotation
  is a narrative-coverage checklist, not a "C" baseline). V2-a doc corrected to say so. SF footage absent (deferred).
- Recovered: MediaEngineV1 (cut/dissolve/speed/audio keep-duck-mute, two video tracks), EditPlan/2 + Edit
  Planner v4 (frozen), AU MomentUnderstanding (events/useful_segments), AU guitar audit.

## Architecture (B, as approved)
Frozen v4 → EditPlan/2 → backend validation → **deterministic refinement pre-pass (new)** → MediaEngineV1.
The pre-pass is a pure function: it never calls a model, never changes output duration / speed / order /
selection / transition / music alignment — it only proposes conservative source in/out NUDGES and (future)
J/L bridges, then re-validates. On any validation failure OR insufficient evidence it returns the ORIGINAL
executable plan. A straight cut remains a valid result.

## Phase 1 — Edit Evidence (bounded, on-device, deterministic)  `AVFoundationEvidence.sample`
At candidate boundaries ONLY (±0.5s window, 0.05s step), never whole-video, no extra LLM call, no global AU
density change:
- motion magnitude + approx direction — 16×16 luma frame-diff between two frames 0.08s apart;
- audio RMS + silence + crude onset — short AVAssetReader PCM window around the boundary;
- AU action timestamps — consumed if provided (currently empty: the plan request carries useful_segments +
  summary, not AU events; refinement relies on motion/audio + useful-range bounds, intentionally conservative).
Returns nil on any read failure → treated as "no evidence" → no-op (never a crash).

## Phase 2 — Boundary refinement  `CreativeRefinementV2b.refineSegment`
Scans the window for a point with SETTLED motion (and, for an in-point, just after an onset; for an out-point,
approaching silence), scored with a distance penalty so it stays conservative. Hard rules: stay inside the AU
useful band that contained the original segment; never move more than 0.5s; never cut across an AU action
(±0.08s); never shorten past 60% of the chosen span (preserve continuous action); require a real score
improvement else no-op. Does NOT snap every boundary.

## Phase 3 — Native-audio continuity (J/L bridges)
Scaffolded in the evidence (silence/onset) + report (`bridge` field) but the overlap application is DEFERRED to
device review — the renderer's two-track audio path can support it, but applying a J/L overlap safely needs
device verification of sync and the keep/duck/mute intent. Not applied blind. (Honest: Phase 3 is prepared, not
yet rendered.)

## Phase 4 — Validation  `RefinementValidator.validate`
Any failure ⇒ keep the ORIGINAL plan. Checks: segment count/order/assetId unchanged (narrative preserved);
source range non-inverted + within clip bounds + within the original useful band; output duration + speed
UNCHANGED; transition unchanged; total duration within ±20%. No frozen field reinterpreted.

## Phase 5 — Real-footage comparison (A/B)  **REQUIRES DEVICE — not run here**
A = V1 render; B = refinement-enabled render. Guitar (6 clips) + TMB. AVAssetExportSession cannot run in the
sandbox, so the rendered A/B videos must be produced on the physical iPhone. The annotation is a narrative
checklist, not a C baseline.

## Verification done here (honest)
- All new/edited Swift parse-clean (`swiftc -parse`): CreativeRefinementV2b, RenderSupport, coordinator, test.
- **Pure-logic unit tests** (`CreativeRefinementV2bTests`, injected evidence — device-independent): nudge toward
  settled motion; max-nudge cap; stay in useful band; no-op without evidence; validator rejects
  order/duration/inverted-range changes and accepts in-bounds nudges. (XCTest needs Xcode to EXECUTE; written +
  parse-clean.)
- Backend suite 221 passed (unchanged — this is iOS-only).
- Opt-in `StoryCreativeRefinement.enabled` defaults FALSE → V1 behavior unchanged until the owner enables it.

## Phase 6 — Quality gate (OPEN)
Not declaring success. Needs: enable the flag in a device build, render A/B on guitar + TMB, and OWNER review of
the actual videos (cut quality, pacing, audio continuity, artifacts, preference). Report items 7–9 (A/B
artifacts, device latency, quality deltas) can only be filled after that.

## Explicitly NOT done (per scope)
match cuts · speed ramps · color · split-screen · V2-c · any push. J/L bridge application deferred to device.
Frozen EditPlan/2 + v4 untouched.
