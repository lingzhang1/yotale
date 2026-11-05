# Milestone — Capture Anywhere (Figma MVP V0.2.2)

Status: implementation complete through Priority 3; awaiting final physical-device
acceptance (Priority 4). Not pushed, not deployed.

## Goal

Capture from Home and Shoot-a-Moment inside a Story share ONE camera, ONE scene
scan, ONE AI Director integration, and ONE persistence implementation. The only
differences are (a) the creative context fed to AI and (b) the Story association
after save. No second camera engine, no second AI pipeline, no fabricated Story.

Baseline: continued from the committed seam `75435fa` (`CaptureContext` enum).

## Architecture — the single seam

`CaptureContext` (`Features/SceneScan/CaptureContext.swift`) is the only fork:

- `.standalone(direction: String?)` — launched from Home. No Story, no StoryGuide,
  no StoryMomentLink. `directorIntent()` returns a NEUTRAL scene-only
  `CreativeIntentContractDTO` built from the optional user direction: fresh
  ephemeral `id`, empty subject/feeling/style — it carries no Story identity, so a
  previously-opened Story's creative context cannot leak in.
- `.story(StoryModel)` — launched from inside a Story. `directorIntent()` returns
  that Story's `CreativeIntentContractDTO`; each saved Moment gets exactly one
  `StoryMomentLink` (capture order preserved).

Everything else is shared and context-agnostic:
- Camera + continuous recording: `Media/Camera/ContinuousCameraController.swift`.
- Scene scan (frame grab): a second `AVCaptureVideoDataOutput` on the SAME session.
- Scene Understanding + Director: `SceneUnderstandingService`, `StoryDirectorService`.
- Persistence: `StoryUseCases.shootStandaloneMoment` / `.shootMoment(for:)`.
- AU: `AssetUnderstandingQueue.enqueue` (async, idempotent per Moment).

## Increments / Priorities

Commits (unpushed):
- `75435fa` — CaptureContext seam (pre-existing baseline).
- `24ed753` — Increment 1: `SceneScanFlowView` consumes `CaptureContext` instead of
  a required `StoryModel`; persistence branches by context; both existing call
  sites migrated to `.story`.
- `27c4ec0` — Increment 2 (continuous recording engine + screen) + Increment 3
  (Figma V0.2.2 Home: Capture / Start a Story primary, Moments / Stories secondary;
  `StoriesListView`; removed obsolete disabled Home entries).
- `4ab2bb3` — Priority 1 (ShootMomentView -> ContinuousCaptureView(.story), camera
  usable immediately, scan-first retained only for the opportunity-driven path) +
  Priority 2 (optional AI Ideas wired into the continuous camera).
- `5302c29` — Priority 3 tests (CaptureContext + continuous-capture persistence).

## Continuous recording behavior (Figma V0.2.2)

Red record button is primary; tap to record, tap to stop; each finished clip is
finalized and persisted as exactly one Moment; the camera STAYS OPEN; no
post-capture confirmation page; subtle "Saved" pill; recent thumbnail updates only
after successful persistence; the next recording is allowed while a prior save/AU
runs.

Integrity guards (in `ContinuousCameraController` + `ContinuousCaptureModel`):
- Rapid taps / out-of-phase taps rejected by a strict phase machine
  (.idle→.starting→.recording→.stopping); stop enabled only after physical start.
- Exactly-once: finish callback honored once per recording (token + URL match);
  the model dedups by temp-URL (inFlight/persisted sets) so one clip = one Moment.
- Interruption (phone call) + backgrounding finalize the in-flight clip rather than
  lose it; disk/engine errors surface honestly (never a false "saved"); temp file
  cleaned up on failure.
- AU enqueue + Photos copy fire AFTER the row commits; never block the next clip.

## AI Ideas behavior (optional, user-initiated)

Pill "Get an AI shot idea" → SCANNING SCENE panel (keep-recording hint + Cancel
scan) → SHOT IDEA · N SEC card (concept title + shot.instruction, pagination +
"Next idea · i of n", "Scan again" + "Let's shoot"). Scan grabs ~4s of frames from
the live session (no second camera session), runs Scene Understanding + Director.
Standalone = scene-only intent; `.story` = Story intent/guide. "Next idea" cycles
cached candidates (no new call); "Scan again" fetches fresh evidence. AI failure /
quota exhaustion → honest note; the red record button is live in EVERY AI state.

## Tests

Automated (run in Xcode `StoryTests`, synchronized group auto-includes them; the
agent CLI cannot run them — the Swift macro plugin is blocked in the sandbox):
- `CaptureContextTests` — neutral standalone intent, no stale-Story leak, ephemeral
  ids, association/target-duration exposure.
- `CaptureAnywherePersistenceTests` — 5 standalone → 5 independent Moments / 0
  links; 5 Story → 5 Moments + exactly 5 links in order; coexist; AU enqueue
  idempotent per Moment; allMoments() global; restart persistence (fresh container,
  same on-disk store).

Device-only (Priority 4 acceptance, NOT asserted in XCTest): consecutive device
recordings, interrupted recording, camera permissions, failed media capture.

## UX differences from Figma V0.2.2 (to confirm on device)

- Record button + overlays were built from the recording's stills; exact spacing/
  sizing may need a pass once seen live on-device.
- Idea-card "title" maps to the Director concept title; body maps to
  `shot.instruction`. Figma's short title ("Follow the ridge") has no dedicated
  contract field — concept title is the closest real datum.

## Remaining before owner acceptance

Priority 4 physical-iPhone acceptance (10 steps): 5 consecutive standalone
recordings → 5 playable Moments → force-quit persistence; 5 Story-associated
recordings → exactly 5 links; standalone + Story-aware AI Ideas; AI failure does
not block recording; select existing Moments → create Story; generate/save/share.
No frozen prompts or contracts were changed.
