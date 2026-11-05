# Milestone C3 — Real Story Director: Close Report

**Date:** 2026-10-02
**Status:** C3 CLOSED (pending the user's final on-device confirmation of the
corrected rescan presentation — see Physical Gate). No Shot Validation / no C4.

## What C3 delivered
The real Story Director, end to end: a user's CreativeIntent (C1) + a real scanned
scene (C2) produce, through a configured model, ONE strong, scene- and
narratively-grounded capture recommendation — or an honest "this scene doesn't
serve your Story" — surfaced in a consumer iPhone flow and leading into the real
camera. Architecture unchanged throughout: **DirectorEngine → ModelGateway →
configured model**, output composed from the frozen contracts (Concept → Beats →
Shots + DirectorDecision + DirectorState).

## Journey
- **C3A** (offline): built the engine + prompt + endpoints + fixtures; offline gate
  passed on Nova Pro.
- **C3B** (device): deployed + wired the consumer DIRECT flow; first device run
  worked but exposed two Director-quality failures.
- **Quality iteration**: one general prompt change (narrative grounding +
  scene-contribution scope). On Nova Pro it did NOT land — diagnosed as a
  model-capability limit, not prompt wording (3 variants, 0/15 rescans).
- **Model-ceiling experiment**: Nova Pro vs Claude Sonnet 4.5 vs Claude Opus 4.5
  (5.5 tier not enabled for the account), same prompt/corpus/contracts. **Opus 4.5
  won (Outcome B)** — the only model that declines an irrelevant scene AND uses the
  same scene when the intent makes it relevant, with real capture restraint.
- Deployed Opus 4.5; device-verified; fixed the iOS presentation of the decline path.

## Final configuration
- Director model: `us.anthropic.claude-opus-4-5-20251101-v1:0` (config
  `STORY_DIRECTOR_MODEL`; switchable, incl. to a 5.5 tier once that account access
  is enabled). prompt `story_director/v1`; schema `story_director.envelope/1`.
- Live: `POST /v1/director/initialize` on App Runner
  `https://ydmju5wdps.us-east-1.awsapprunner.com`.

## Close-gate criteria (§C3 close) — evidence
1. **Physical scene grounding** ✅ — uses only reported scene elements (device R1:
   backpack/hallway).
2. **Narrative grounding** ✅ — device R2 (TMB + music room) → `rescan_scene`
   instead of forcing a hiking story onto a guitar. Offline triad B confirms.
3. **Intent sensitivity** ✅ — same scene, different intents yield materially
   different concepts (offline home×{TMB,ordinary,somber}).
4. **Scene sensitivity** ✅ — same intent, different scenes differ (home vs trail
   vs market).
5. **Useful low-value-scene rejection** ✅ — `rescan_scene` on the irrelevant room,
   device + offline (Opus chose it 2/15; Nova never did).
6. **Minimum-sufficient planning** ✅ — Opus mean 1.27 beats / 1.13 shots (Nova
   2.53/2.73); device R1 was 1 beat / 1 shot.
7. **Useful ordinary-scene creativity where relevant** ✅ — triad C (music intent +
   music room) → uses the room ("The Quiet Work of Getting Better"); device R1
   backpack → "The Departure".
8. **Understandable, executable direction** ✅ — device R1: "Walk toward the camera
   down the hallway with purpose, like you're heading out the door" (+ Subject/You/
   Hold rows). No jargon.
9. **Safety** ✅ — ridge/edge case stays conservative (follow shot, no backward-
   near-edge); deterministic guard + prompt; `mountain_edge_backward_motion_regression`
   green across models.
10. **Successful capture transition** ✅ — device R1 → Open Camera → record → Moment
    (the C1/C2/A capture path, unchanged).

## Physical gate — status
- **R1 (TMB + backpack/home):** PASS on device — "The Departure", one strong shot,
  genuine preparation connection, clean guidance.
- **R2 (TMB + unrelated music/office room):** model PASS (`rescan_scene`). It
  exposed an iOS bug — the recommendation view rendered the decline as "Here's your
  shot" + Open Camera with a blank instruction. **Fixed** (`SceneScanFlowView`
  now branches on decision.action: rescan → "This scene doesn't quite fit your
  Story" + **Scan again** as primary, NO Open Camera, no empty body; create_now →
  "You've got what you need" + Done; capture/retry → shot + Open Camera). Verified
  in code: parse-clean, Open Camera only under capture/retry. **Remaining: the user
  rebuilds and confirms the corrected rescan screen on device** → then the physical
  gate is fully passed. (iOS-only change; backend unchanged, no redeploy.)
- **C scenario (relevant intent + same room)** and **rich scene**: verified live
  against the deployed endpoint (capture_shot with scene-appropriate plans).
- **`create_now` physical presentation:** DEFERRED to the Director-loop milestone
  (C4) per direction — its contract/state behavior is already covered offline
  (`dir_tmb_progress_enough` → create_now) and the iOS create_now branch is
  implemented ("You've got what you need" + Done), just not yet exercised on device
  because reaching it needs the capture→validation loop C4 introduces.

## Tracked pre-beta optimization item
**Director latency ~12-16s on device** (Opus 4.5; offline p50 11s / p90 14s vs Nova
p50 4s). Accepted for C3 (quality was the gate, per direction), covered by the
"Finding the best way to capture this…" state. Pre-beta options to investigate
later: a faster model for a first-pass with Opus escalation, prompt/token trimming,
streaming/partial UI, or caching the concept/plan across a session. Not addressed
in C3.

## Evaluation corpus & tests
15 Director fixtures (anchor, scene axis, intent axis, progress axis,
narrative-grounding triad A/B/C, min-capture axis incl. rich/weak/low-value),
safety regressions. Harnesses: `run_director_corpus.py`, `run_director_model_compare.py`.
98 backend pytest green; `DirectorDTOTests` + engine/endpoint tests; swiftc -parse
clean. DEBUG feedback panel captures reproducible fixture JSON on device (no frames).

## Architecture deviations
None. Contracts/Concept→Beats→Shots model unchanged. Two engine corrections, both
bugs not redesigns: (a) server mints UUID ids over model-supplied ones; (b)
`rescan_scene`/`create_now` may carry an empty plan (the frozen contracts already
allow a decision without a shot). Xcode project is filesystem-synchronized (new
Swift files auto-included).

## Recommendation for C4 (do NOT start automatically)
C4 = real Shot Validation + the validation-driven Director loop via the already-
deployed `/v1/director/next`: real ValidationResult from captured video → BeatProgress
→ adaptive retry_shot / capture_shot / create_now. Carry forward: the DEBUG feedback
panel (grow the corpus from real captures), the latency item, and a device pass of
the create_now presentation. Also consider requesting 5.5-tier model access and
re-running `run_director_model_compare.py` to see if the ceiling moves.

## Scope held
No Shot Validation, no video-quality understanding, no validation-driven retry, no
real beat fulfillment from video, no Edit Planner, Music Engine, rendering, cloud
sync, accounts, or UI redesign. STOP after C3.
