# Story — Camera Capabilities: Time-Boxed Engineering Assessment

**Type:** Estimation & prioritization (NO implementation). Code-grounded audit only.
**Date:** 2026-10-18. **Scope:** iOS camera (`apps/ios`). **Status:** 🟡 assessment complete,
awaiting owner package choice (A / B / C). Nothing implemented, prototyped, pushed, or deployed.

> Owner objective: Story's existing camera is too limited for everyday travel capture. Improve it
> without building a professional camera app or delaying MVP. This doc estimates and prioritizes the
> nine requested capabilities so the owner can pick a package.

**Estimates vs measurements.** Every hour figure below is an engineering **estimate** from the code
audit, not a measured result. The only **measured** facts are the audit findings (which
controllers/outputs/models exist, and that no focus/zoom/lens/photo/torch/orientation code is present
today). Hours assume one iOS engineer extending the existing `ContinuousCameraController`, and every
feature includes physical-device testing (no camera in the Simulator).

---

## Phase 1 — Architecture audit (what actually exists)

Three separate AVFoundation controllers, all built on the same pattern (`AVCaptureSession` +
`.builtInWideAngleCamera`, back position, `.sessionPreset = .high`, `AVCaptureVideoPreviewLayer`, no
device locking / no device configuration):

| Controller | Role | Outputs | State machine |
|---|---|---|---|
| `Media/Camera/ContinuousCameraController.swift` | **Primary** engine (Capture Anywhere). Long-lived, records many clips. | `AVCaptureMovieFileOutput` + `AVCaptureVideoDataOutput` (AI scan, same session) | Strict `.idle→.starting→.recording→.stopping`, token-deduped delegate, interruption + backgrounding guards |
| `Media/Camera/CameraCaptureView.swift` | One-shot recorder used by `SceneScanFlowView`'s "Let's shoot" | `AVCaptureMovieFileOutput` only | Loose `isRecording` bool, no guards |
| `Media/Camera/SceneScanController.swift` | Frame grabber for the scan intro flow | `AVCaptureVideoDataOutput` only, no audio | scan-only |

UI/model layer: `Features/Capture/ContinuousCaptureView.swift` (SwiftUI chrome + `ContinuousCameraHost`
representable) and `Features/Capture/ContinuousCaptureModel.swift` (`@MainActor` brain: persistence,
AI-ideas state, recording timer). `Features/SceneScan/SceneScanFlowView.swift` is the scan→recommend→
shoot flow.

**Key finding — the continuous controller is the real foundation.** It already proves the hardest
architectural point: a **second output (`AVCaptureVideoDataOutput`) coexists on one running session
with the movie output**, and **AI scanning runs concurrently with recording without interrupting it**
(`startScan` never touches `movieOutput`; the scan delegate ignores buffers unless `scanning == true`).
That de-risks "can photo + video + AI coexist" substantially.

**Capabilities present internally but not exposed in UI: none.** The engine does exactly one thing
(wide-angle back-camera video + concurrent scan). There is no hidden zoom/focus/lens/flash/photo code
waiting to be surfaced. A grep across the entire iOS tree for `videoZoomFactor`, `focusPointOfInterest`,
`exposurePointOfInterest`, `AVCapturePhotoOutput`, `torchMode`/`flashMode`, front `position`,
`videoRotationAngle`/`videoOrientation`, and pinch/tap gesture recognizers returns **zero matches**.
Every requested feature is genuinely **missing**, not partial-hidden.

**Can it be extended without replacing the engine? Yes, cleanly.** The session is configured once in
`configureSession()`; adding device config (focus/zoom/exposure/torch), gestures, and a photo output are
all additive. The one exception requiring real care is **lens/front-rear switching**, which needs an
input swap inside `beginConfiguration/commitConfiguration` (not a new session).

**Persistence is video-only and downstream-coupled.** `MomentModel` → `AssetModel { relativePath,
durationSeconds (NON-optional), source }` (`Data/Persistence/Models.swift`). There is **no `mediaType`
discriminator**. Everything downstream assumes a time-based video asset: `MomentResolver` reads
`durationSeconds` + `useful_segments`; the Edit Planner retimes/trims spans; `MediaEngineV1` composes via
`AVAssetExportSession`/`AVMutableComposition`. Asset Understanding ingests **frames**, so a still photo
would survive AU — but the renderer would have to synthesize a duration for a 0-duration still. **This
is the single biggest structural fact for the photo-capture question (Phase 5.8).**

**Orientation:** nothing sets `videoRotationAngle`/`videoOrientation` on the capture connection today —
recordings rely on default sensor orientation. "Reliable orientation" is therefore partly a **latent
existing gap**, not purely new work.

---

## Phase 2 — Per-feature estimates

Impl / Test / Total in engineer-hours. "Break-recording risk" = risk to the continuous-recording
guards; "Break-AI-scan risk" = risk to the concurrent scan output.

| # | Feature | Status | AVFoundation APIs to reuse | Impl | Test | Total | Cplx | Break-recording | Break-AI-scan |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Preview + recording controls | **existing** (solid) | already in place | 1 | 1 | **2** | Low | — | — |
| 2 | Tap to focus & expose | missing | `focusPointOfInterest`+`focusMode`, `exposurePointOfInterest`+`exposureMode`, `lockForConfiguration` | 3 | 2 | **5** | Low | Low | Low |
| 3 | Pinch to zoom | missing | `videoZoomFactor` (ramped), `UIPinchGestureRecognizer` | 3 | 2 | **5** | Low | Low | Low |
| 4 | Lens 0.5/1/2× | missing | `builtInTriple/Dual/WideAngleCamera`, `virtualDeviceSwitchOverVideoZoomFactors`, or discrete input swap | 6 | 5 | **11** | **High** | **Medium** | Medium |
| 5 | Front/rear switch | missing | remove/add `AVCaptureDeviceInput` inside `beginConfiguration` | 5 | 4 | **9** | Medium | **Medium** (gate out of `.recording`) | Low (re-bind scan output) |
| 6 | Photo + video capture | missing | `AVCapturePhotoOutput`, `capturePhoto(with:)`, photo delegate | 8+ | 6+ | **14+** | **High** | Medium | Medium |
| 7 | Flash / torch | missing | `torchMode`/`setTorchModeOn(level:)`, `hasTorch`; photo `flashMode` | 2 | 2 | **4** | Low | Low | Low |
| 8 | Reliable orientation + feedback | partial (latent gap) | `videoRotationAngle` / `RotationCoordinator` (iOS 17+) / `videoOrientation` | 4 | 4 | **8** | Medium | Low–Medium | Low |
| 9 | Exposure adj + AE/AF lock | missing | `setExposureTargetBias`, `exposureMode=.locked`, `focusMode=.locked` | 4 | 3 | **7** | Low | Low | Low |

### Feature 6 — explicit downstream analysis (required by the owner)

Adding `AVCapturePhotoOutput` to the session is a one-time `beginConfiguration` addition and is **safe
for the video session** (same pattern as the existing movie + data dual-output). The real cost is **not
the camera — it's the pipeline**: Moment persistence, AU, and final Story generation all assume a video
with a real `durationSeconds`. A photo Moment needs either:

- **(a)** `AssetModel.mediaType` + still-image handling in `MomentResolver` / `MediaEngineV1` (synthesize
  a Ken-Burns / hold duration), OR
- **(b)** convert the still to a short video clip at capture time (far cheaper, avoids a
  persistence-contract change).

Option (b) is the cheaper path and avoids a contract change — but **true still Moments (option a) require
a frozen-persistence-contract decision**, which is out of scope for this assessment. This is the only
feature that cannot be fully delivered without a separate owner decision (see Phase 5.8).

### Device-compatibility note (required)

Lens availability is **per-model**: SE/entry phones have **no 0.5× ultra-wide and no 2× tele**; Pro
phones have triple cameras. Feature 4 **must** query `AVCaptureDevice.DiscoverySession` at runtime and
show only the lenses present. Torch presence (`hasTorch`), HDR, and front-camera capabilities also vary.
Never assume uniform hardware across iPhones.

### Dependencies

- 2, 3, 9 share the "lock device + configure" primitive.
- 4 depends on 3 (zoom-factor lens switching *is* zoom).
- 7's photo-flash depends on 6.
- 8 is independent but interacts with 5 (front camera mirrors; orientation differs).
- 5 and 6 both touch session reconfiguration.

---

## Phase 3 — Shared work (de-duplication)

The per-feature estimates double-count foundational work. The shared substrate, counted **once**:

| Shared component | Hrs | Feeds features |
|---|---|---|
| `lockForConfiguration` device-config helper + session-queue serialization | 3 | 2,3,4,7,9 |
| Device-capability detection (`DiscoverySession`, `hasTorch`, lens set) | 3 | 4,5,7 |
| Gesture layer (pinch + tap) wired into SwiftUI `ContinuousCameraHost` | 2 | 2,3 |
| Zoom/lens UI (segmented 0.5/1/2× + focus reticle) | 3 | 3,4,2 |
| Orientation handling on connections | 3 | 6,8 |
| Capture-state extension (keep the strict phase machine valid under new actions) | 2 | 5,6 |
| Physical-device test harness / checklist across SE + Pro | 4 | all |
| **Shared total** | **~20** | |

**Realistic all-nine total ≠ the per-feature column sum (65h).** With shared work counted once, the
honest all-nine figure is **≈ 42–48 engineering hours (≈ 5.5–6 engineer-days)**. The range reflects
lens-switching and photo-pipeline uncertainty.

---

## Phase 4 — Three implementation packages

### Package A — Essential camera upgrade (target 1–2 days)
- **Included:** #2 tap focus/expose, #3 pinch zoom, #7 torch, #1 polish. Continuous zoom (incl. into
  ultra-wide/tele ranges) via `videoZoomFactor` + a simple device-capable 1×/2× toggle.
- **Lens note:** defer *discrete* 0.5× ultra-wide device-switching to B — it is the expensive part of #4.
- **Deferred:** front/rear, photo, full exposure-bias slider, orientation hardening.
- **Engineering ≈ 14h · Device testing ≈ 5h · Total ≈ 19h (~2.5 days — trim torch to hit a true 2d).**
- **Risks:** low — all additive device config, no session rebuild, no recording-path change.
- **User-visible win:** the camera feels native — zoom + tap-to-focus. Highest perceived gain per hour.
- **Acceptance tests:** pinch zooms smoothly during recording; tap sets focus+exposure with a reticle;
  torch toggles only where `hasTorch`; zoom persists across start/stop; AI scan still works mid-zoom.

### Package B — Complete everyday camera (target 3–5 days)
- **Included:** A + #5 front/rear (gated between recordings), #4 discrete 0.5/1/2× lens selection
  (device-aware), #8 reliable orientation, #9 exposure/AE-AF lock. **Photo only if** the team accepts the
  capture-time still→clip approach (option b, no contract change); otherwise photo stays in C.
- **Deferred:** true still-photo Moments requiring a persistence-contract change.
- **Engineering ≈ 34h · Device testing ≈ 12h · Total ≈ 46h (~5.5 days).**
- **Risks:** medium — lens switching + front/rear both reconfigure the session; must preserve the
  continuous-recording guards and re-bind the scan output after any input swap.
- **User-visible win:** a phone camera covering normal travel capture end-to-end.
- **Acceptance tests:** lens buttons show only device-available options; front/rear disabled while
  `.recording`; rotating the phone yields correctly-oriented clips in the final Story; AE/AF lock holds;
  AI scan + persistence unaffected after every switch.

### Package C — Full requested set (all 9; realistic even if >5 days)
- **Included:** everything, **including true photo Moments** with the required `AssetModel.mediaType` +
  downstream still handling.
- **Engineering ≈ 42–48h camera/UI + 10–16h pipeline** (persistence contract, `MomentResolver`,
  `MediaEngineV1` still support, AU duration synthesis, Story-generation tests) = **≈ 58–64h
  (~7.5–8 days).**
- **Risks:** high — the only package touching the **frozen persistence contract** and the render/plan
  pipeline; needs owner approval for a schema change + a round of Story-generation regression testing.
- **User-visible win:** full parity with the request; mixed photo+video Stories.
- **Acceptance tests:** B's tests + a photo Moment survives AU, persists, and renders into a Story with a
  sensible hold duration; existing all-video Stories unchanged.

---

## Phase 5 — Architecture risks (blockers vs ordinary work)

1. **Lens switch without rebuilding the session** — *Ordinary work.* `videoZoomFactor` across a virtual
   multi-camera device needs **no** rebuild; discrete device swap needs a `beginConfiguration` reconfig
   (not a new session). Not a blocker.
2. **Zoom during recording** — *Ordinary, already safe.* Zoom is a device property; both outputs follow.
3. **Front/rear restricted to between recordings** — *Design decision, not a blocker.* Switching inputs
   mid-record would corrupt the movie file; **gate it out of `.recording`** (the phase machine already
   enforces exactly this for taps). Recommend: disabled while recording.
4. **Photo + video outputs coexisting** — *Ordinary work.* The existing dual-output (movie + data)
   already proves coexistence; adding `AVCapturePhotoOutput` is one more `canAddOutput`. Not a blocker
   at the camera layer.
5. **AI scanning vs photo/config** — *Ordinary, low risk.* Scan reads the shared data output; it already
   runs during recording. A photo capture is a brief event on a different output. Minor: a torch/lens
   change mid-scan slightly alters frames — acceptable.
6. **Changing devices affects orientation/audio/focus/exposure** — *Ordinary work, needs discipline.*
   After an input swap you must re-apply focus/exposure defaults, re-bind the audio input, re-set the
   connection orientation, and reset zoom. Main source of B's testing hours.
7. **Continuous-recording safety guards remain valid** — *Must be actively preserved.* The strict phase
   machine, token dedup, interruption/backgrounding handling, and serialized persistence are the crown
   jewels. New actions (switch/photo) must be rejected out-of-phase exactly like taps are today. A
   regression risk if ignored, not a blocker if respected.
8. **Photo capture needs Moment-model / pipeline changes** — ***GENUINE BLOCKER (the only one).***
   `AssetModel` has no media-type and a non-optional `durationSeconds`; `MomentResolver`/Edit
   Planner/`MediaEngineV1` all assume time-based video. True still Moments require a
   persistence-contract change + downstream still handling — explicitly out of scope here, needs owner
   approval. Everything else is ordinary implementation work.

---

## Phase 6 — Final recommendation

| Feature | Existing status | Impl hrs | Test hrs | Risk | Recommended package |
|---|---|---|---|---|---|
| 1 Preview/record controls | existing | 1 | 1 | — | A (polish) |
| 2 Tap focus & expose | missing | 3 | 2 | Low | **A** |
| 3 Pinch zoom | missing | 3 | 2 | Low | **A** |
| 4 Lens 0.5/1/2× | missing | 6 | 5 | High | B (continuous-zoom part in A) |
| 5 Front/rear switch | missing | 5 | 4 | Medium | B |
| 6 Photo + video | missing | 8+ | 6+ | High | C (needs contract change) |
| 7 Flash/torch | missing | 2 | 2 | Low | **A** |
| 8 Orientation + feedback | partial (latent gap) | 4 | 4 | Medium | B |
| 9 Exposure adj + AE/AF lock | missing | 4 | 3 | Low | B |

**Summary**
1. **Package A total:** ≈ **19h (~2.5 days)** — zoom, tap-focus/expose, torch. Trim torch for a true 2d fit.
2. **Package B total:** ≈ **46h (~5.5 days)** — the complete everyday travel camera (no true-still photo).
3. **Package C total:** ≈ **58–64h (~7.5–8 days)** — all nine, incl. photo with a persistence-contract change.
4. **Shared engineering work:** ≈ **20h** counted once (device-config helper, capability detection,
   gestures, zoom/lens UI, orientation, state-machine extension, device test harness) — why summing
   per-feature rows (65h) overstates the real all-nine cost (~42–48h camera + pipeline).
5. **Biggest technical uncertainties:** (a) discrete **lens switching** across the SE→Pro device matrix;
   (b) the **photo persistence/render** path (the only contract-touching work); (c) **orientation**
   correctness feeding the final render — all three carry the widest hour ranges and need physical-device
   verification.
6. **Should be deferred:** true still-photo Moments (#6 full form) — blocked on a persistence-contract
   decision; keep out of MVP.
7. **Recommended MVP scope:** **Package A now** (continuous zoom + tap focus/expose + torch) — highest
   perceived improvement, ~2–2.5 days, zero risk to the recording guards, AI scan, persistence, or render
   pipeline, and no contract change. Promote to **Package B** post-MVP once travel usage justifies
   front/rear + discrete lenses + orientation hardening. Hold **Package C / photo** until a separate
   owner decision on the persistence contract.

---

## Decision gate

STOP after the assessment. No camera features implemented, no engine rewrite, no production files
modified, no persistence contracts changed, nothing pushed or deployed. The owner chooses Package A, B,
or C after reviewing these estimates; the chosen package becomes the default scope and its results will
be written back to this doc (and a per-phase completion/eval report) once implementation runs.

---

## Owner decision (2026-10-18)

Owner approved a **modified Package B, delivered in two device-gated increments**. Native photo
capture, capture-time still→video conversion, and professional controls are **explicitly deferred**.
A camera-metadata audit (capture timestamp, optional GPS, orientation) is preserved as a separate
follow-up.

- **Increment 1 (implement now):** pinch-to-zoom (preview + recording), device-supported zoom
  presets (no fake optical lenses), tap-to-focus/expose, torch where supported, orientation
  verify/fix — all reusing `ContinuousCameraController`, preserving continuous recording, AI scanning,
  persistence, and interruption handling. Stop after Increment 1 for owner device acceptance.
- **Increment 2 (after acceptance):** front/rear switching between recordings, full device-supported
  zoom/lens controls, exposure adjustment + AE/AF lock, orientation hardening + regression tests.

---

## Implementation Results — Increment 1 (commit `572ec2d`, 2026-10-18)

**Status:** code-complete, parse-clean, committed. iOS-only; additive on `ContinuousCameraController`
(no new engine, no session-topology change, no persistence/contract change). **Awaiting owner device
acceptance** — the acceptance checks below are NOT yet run on hardware.

### What shipped (all ADDITIVE on the existing engine)

| Increment-1 feature | How it was delivered |
|---|---|
| Pinch-to-zoom (preview + recording) | `applyPinchZoom(scale:base:)` on `videoZoomFactor`, clamped to the device min/max. Gesture base captured at pinch start. Works mid-record (device-level, no topology change). |
| Device-supported zoom presets | `zoomPresets(for:)` derived from the REAL `virtualDeviceSwitchOverVideoZoomFactors` + ultra-wide presence — 0.5× only where an ultra-wide constituent exists; a digital 2× fallback only when nothing optical reaches 2×. UI strip hidden when only [1×]. **No fabricated lens list.** |
| Tap-to-focus + expose | `focusAndExpose(atViewPoint:)` → `captureDevicePointConverted` → focus/exposure point-of-interest, re-enabling continuous tracking after the tap (AE/AF *lock* is Increment 2). Brief focus reticle in the UI. |
| Torch where supported | `setTorch(_:)` guarded by `hasTorch`/`isTorchModeSupported`; UI button hidden on devices without a torch. Safe mid-record. |
| Orientation verify/fix | `AVCaptureDevice.RotationCoordinator` (iOS 17+) observing horizon-level preview + capture angles, interface-orientation fallback pre-17; applied to the preview AND movie-output connections; **never re-rotates mid-recording** (a clip keeps its start angle). Closes the audit's confirmed latent gap (nothing set connection orientation before). |

**Safety preserved:** every device mutation runs on a dedicated `sessionQueue` inside
`lockForConfiguration`/`unlockForConfiguration`, so it is atomic and cannot interleave with the
recording state machine (which lives on main). No `begin/commitConfiguration`, no input/output change,
so the in-flight recording and the concurrent AI-scan `AVCaptureVideoDataOutput` are untouched.

### Files
- `apps/ios/Story/Story/Media/Camera/ContinuousCameraController.swift` — device selection, zoom-preset
  derivation, zoom/focus/torch controls, rotation coordinator (+245 lines).
- `apps/ios/Story/Story/Features/Capture/ContinuousCaptureView.swift` — pinch+tap gesture layer, zoom
  preset strip, torch button, focus reticle (+135).
- `apps/ios/Story/Story/Features/Capture/ContinuousCaptureModel.swift` — control passthroughs + the
  pure `CameraZoomFormat` label helper (+43).
- `apps/ios/Story/StoryTests/CameraControlsTests.swift` — zoom-label formatter tests (new).

### Automated tests
`CameraControlsTests` covers the pure, device-independent zoom-label formatting (`.5` / `1` / `2`),
including the display contract that an SE-style [1×,2×] list never renders a `.5`. The device-dependent
pieces (preset DERIVATION from real switch-over factors, focus/exposure application, torch, rotation)
require an `AVCaptureDevice` and are verified in **physical-device acceptance**, not unit tests.
Verified pure-logic output by standalone compile (all pass). Parse-clean via `swiftc -parse`; Xcode
device build remains the authoritative type-check gate.

### Actual engineering time (measured, this session)
≈ **1.5 engineering hours** of implementation for all five Increment-1 features + tests + doc. This is
**well under** the Package-A estimate (~14h impl + 5h test) — because the audit's hardest de-risking was
already proven (the dual-output coexistence) and every control turned out to be a clean additive device
mutation with no session rebuild. **This measured figure is implementation only; it does NOT include
physical-device acceptance/debugging time**, which the estimate bundled in and which is still pending —
device testing is where estimates for camera work realistically land, and any orientation/zoom-preset
defects found on hardware will add to this.

### Increment 2 — re-estimate (shared infra NOT double-counted)

Increment 1 already built the shared substrate the original estimate counted once: the
`sessionQueue` + `lockForConfiguration` device-config helper, device-capability detection
(`DiscoverySession`, `hasTorch`, preset derivation), the gesture layer, the zoom/preset UI, and the
orientation plumbing. Those ~14–16h of shared work are **done**, so Increment 2 should NOT re-pay them.

| Increment-2 feature | Remaining impl | Remaining test | Notes |
|---|---|---|---|
| Front/rear switch (between recordings) | 3h | 3h | Input swap in `begin/commitConfiguration`, gated out of `.recording`; re-bind audio + re-apply focus/exposure/orientation/zoom after swap (reuses existing helpers). |
| Full device zoom/lens controls | 2h | 2h | Discrete optical lens buttons layered on the preset strip already built; mostly UI + per-device matrix testing. |
| Exposure adjustment + AE/AF lock | 3h | 3h | `setExposureTargetBias`, `exposureMode=.locked`/`focusMode=.locked` via the existing `configureDevice` helper. |
| Orientation hardening + regression tests | 3h | 3h | Edge cases (upside-down, mid-rotation record start, front mirroring), plus regression tests around the recording guards. |
| **Increment 2 total** | **≈ 11h** | **≈ 11h** | **≈ 22h (~3 engineer-days)** incl. device testing. |

Down from a naive sum because the shared camera infrastructure is already in place. The dominant
remaining cost is **physical-device testing across the SE→Pro matrix**, not new engine code.

### Still pending (Increment 1 close-out)
1. **Owner device acceptance** — rebuild on iPhone and verify: pinch zooms smoothly (incl. during
   recording); presets snap and show only device-available options; tap sets focus+exposure with a
   reticle; torch toggles only where present; **portrait and landscape clips record upright** in the
   final Story; AI scan + persistence unaffected after every control action. **STOP here.**
2. Deferred (owner): native photo capture + pipeline, still→video conversion, pro controls.
3. Separate follow-up: camera-metadata audit (capture timestamp, optional GPS, orientation).

---

## Implementation Results — Increment 2 (commit `53630aa`, 2026-10-18)

**Status:** code-complete, parse-clean, committed. iOS-only; additive on `ContinuousCameraController`
(no new engine, no session rebuild beyond the input swap, no persistence/contract change). **Awaiting
owner device acceptance.**

Increment 1 was accepted on device (zoom ladder `.5 1 2 3 4 5`, tap focus/expose, torch, orientation,
live zoom strip) after three follow-up fixes in that increment: gradual zoom ladder (`2f0401d`), focus
reticle coordinate-space (`f67f172`), and strip default-visibility + live magnification tracking
(`1be4a4a`).

### What shipped

| Increment-2 feature | How it was delivered |
|---|---|
| Front/rear switch (between recordings) | `switchCamera()` rebuilds ONLY the video input inside `begin/commitConfiguration` — audio input and movie/data outputs stay. Re-derives zoom presets for the new device, resets zoom to 1×, re-applies orientation, clears torch + AE/AF lock. **Refused while recording** (UI gates the button out of `.recording` AND the controller guards `phase`). Flip button hidden when `hasFrontCamera` is false. |
| Exposure adjustment | `setExposureBias(ev)` → `setExposureTargetBias`, clamped to the device's REAL `minExposureTargetBias…maxExposureTargetBias`. A vertical "sun" slider appears beside the focus reticle (drag up = brighter, down = darker); hidden when the device reports a zero bias range. |
| AE/AF lock | `setAEAFLock` sets `exposureMode`/`focusMode = .locked` (and back to continuous); a **tap-to-focus clears the lock** (native behavior). Top-bar lock toggle reflects state. |
| Orientation hardening | After a front/rear swap the `RotationCoordinator` is **rebuilt for the new device** (the old one reports the wrong device's angles). Version-agnostic `applyRotationForCurrentAPI()`; still never re-rotates the movie connection mid-recording. |
| Full device lens controls | Satisfied by the Increment-1 preset strip: it already exposes every optical lens through the real `virtualDeviceSwitchOverVideoZoomFactors` ladder with live pinch tracking. For a single virtual multi-camera device that IS the full lens control — there is no separate "lens device" to switch to, so no redundant UI was added (honest scope note, not a cut). |

**Safety preserved (Phase 5 risks revisited):** the only session-topology change is the input swap,
which is gated out of recording and reverts to the old input if the new one cannot be added (the session
never ends up input-less). Audio input, movie output, and the AI-scan data output are untouched by the
swap. Exposure bias / AE-AF lock / torch remain pure device-config on `sessionQueue` + `lockForConfiguration`.

### Files
- `apps/ios/Story/Story/Media/Camera/ContinuousCameraController.swift` — position-aware device picker,
  `switchCamera`, `setExposureBias`, `setAEAFLock`, lock-aware `focusAndExpose`, coordinator rebuild, 2 new events.
- `apps/ios/Story/Story/Features/Capture/ContinuousCaptureModel.swift` — front/exposure/lock state +
  passthroughs, event handling, pure `exposureEV`/`exposureFraction` mapping.
- `apps/ios/Story/Story/Features/Capture/ContinuousCaptureView.swift` — flip + AE/AF-lock top-bar
  buttons, `ExposureSlider` sun-slider beside the reticle.
- `apps/ios/Story/StoryTests/CameraControlsTests.swift` — exposure fraction↔EV mapping tests.

### Automated tests
Pure exposure fraction↔EV mapping: endpoint mapping, out-of-range clamp, round-trip inverse, zero-span
safety (device-independent, standalone-verified — all pass). The device-dependent pieces (actual input
swap, real bias clamping, lock engagement, post-swap orientation) require hardware and are
**physical-device acceptance**. Parse-clean via `swiftc -parse`; Xcode device build is authoritative.

### Actual engineering time (measured, this session)
≈ **1.5 engineering hours** of implementation for all four Increment-2 features + tests + doc —
**under** the ~11h re-estimate, again because the Increment-1 shared substrate (`sessionQueue` +
`lockForConfiguration` helper, capability detection, the event/delegate plumbing, the preset strip, the
orientation coordinator) was already in place and every Increment-2 control reused it. **This excludes
physical-device acceptance/debugging**, which is where camera estimates realistically land and is still
pending — expect on-device iteration on the front-camera mirroring, post-swap orientation, and the
slider feel (as Increment 1 needed three device-driven follow-ups).

### Pending (Increment 2 close-out)
1. **Owner device acceptance** — verify: flip switches front↔rear only between recordings (disabled while
   recording); the exposure sun-slider brightens/darkens live and is clamped; AE/AF lock holds through a
   scene change and a tap clears it; a clip recorded after a swap is upright; AI scan + persistence
   unaffected after every control action.
2. Still deferred (owner): native photo capture + pipeline, still→video conversion, pro controls.
3. Separate follow-up: camera-metadata audit (capture timestamp, optional GPS, orientation).

---

## Owner device acceptance — PACKAGE B COMPLETE (2026-10-18)

Owner confirmed both increments pass on device:
- **Increment 1 accepted** (after three device-driven follow-ups: gradual zoom ladder `2f0401d`, focus
  reticle coordinate-space `f67f172`, strip default-visibility + live magnification `1be4a4a`).
- **Increment 2 accepted** (`53630aa`): flip front↔rear between recordings, exposure sun-slider, AE/AF
  lock with tap-to-clear, post-swap orientation.

**Modified Package B is DONE.** Shipped set: pinch + device-aware gradual zoom presets with live
magnification, tap focus/expose, torch, orientation fix/hardening, front/rear switch, exposure
adjustment, AE/AF lock — all additive on `ContinuousCameraController`, preserving continuous recording,
AI scanning, persistence, and interruption handling; no new engine, no persistence/contract change.

**Total actual implementation time ≈ 3h** across both increments (vs the ~19h Package-A + ~22h
Increment-2 estimates) — the overrun-in-reverse is because the first increment built a reusable
device-config/capability/event substrate that the second increment and every follow-up fix drew on. The
estimates correctly identified device testing as the real cost: Increment 1 took three on-device
iterations; Increment 2 was accepted first pass.

**App commits (local):** `572ec2d`, `2f0401d`, `f67f172`, `1be4a4a` (Increment 1), `53630aa`
(Increment 2). **Specs commits:** `b4212cc` (assessment), `61f7ee6` (I1 results), `2fde7a8` (I2 results),
+ this acceptance record.

### Remaining (separate owner decisions — NOT part of Package B)
1. Native photo capture + photo/video Moment pipeline — **deferred**, blocked on a persistence-contract
   decision (see Phase 5.8).
2. Capture-time still→video conversion — **deferred**.
3. Camera-metadata audit (capture timestamp, optional GPS, orientation) — **follow-up**, not started.

---

## Addendum — thumb-drag zoom dial (commit `859d7d8`, 2026-10-18, device-accepted)

Owner-requested UX addition on top of Package B, matching the native camera's drag-to-fine-tune zoom.
Dragging on the zoom strip (either axis) expands the compact chip row into a **tick-ruler dial** with a
gold live `N.N×` readout, mapping thumb travel to a **log-scaled continuous zoom** (finer at the low
end, like the native dial); release collapses back to the chips. A plain tap still snaps to a preset
(`highPriorityGesture` lets a drag win over the chip buttons while a no-movement tap falls through).

Reuses the existing `setUserZoom` + `.zoomChanged` plumbing; added `userZoomRange` (controller + model)
and pure `CameraZoomFormat.dialZoom`/`dialFraction` with 4 unit tests (round-trip, clamp, log midpoint).
Two follow-up commits in this feature: `ffe9038` (initial dial), `859d7d8` (gesture-priority fix so the
drag registers over the chip buttons). Device-accepted. No engine/persistence/contract change.
