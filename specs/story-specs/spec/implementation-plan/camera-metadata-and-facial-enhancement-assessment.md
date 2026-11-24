# Camera Metadata (P0) + Facial Enhancement Feasibility — Assessment

**Status:** ASSESSMENT (Part A = audit + bounded-implementation proposal, cleared to build; Part B =
feasibility audit only, no implementation). No code changed. Nothing pushed/deployed.
**Date:** 2026-10-18
**Context:** Follows the completed + device-accepted modified Package B camera
(`camera-capabilities-engineering-assessment.md`). Must not destabilize that camera.

Owner objective: evaluate two remaining improvements — (A) accurate capture location & metadata
preservation, and (B) optional subtle facial enhancement for videos with people.

---

## Part A — Location Metadata (P0)

### Verified gaps (code-grounded, not assumed)

| Question | Finding | Evidence |
|---|---|---|
| GPS currently collected? | **No.** No `CLLocationManager` anywhere in the app. | grep: zero `CLLocation*` matches (the only "location" hits are `gesture.location` in the capture view). |
| Moments store location? | **No.** `AssetModel` = `relativePath`, `durationSeconds`, `sourceRaw`, `createdAt`. `MomentModel` = `caption`, `source`, `createdAt`, `asset`. No location/coordinate/accuracy field at all. | `apps/ios/Story/Story/Data/Persistence/Models.swift`. |
| Original video files contain GPS? | **No.** `AVCaptureMovieFileOutput` is used with no `metadata` and no connection location set — iOS does not auto-embed GPS, and the app never adds it. | `apps/ios/Story/Story/Media/Camera/ContinuousCameraController.swift` — zero `metadata`/`setLocation`/`AVMetadataItem`. |
| Photos copy preserves location? | **No.** `PHAssetChangeRequest.creationRequestForAssetFromVideo` called with no `.location`; source file has no GPS to carry. | `apps/ios/Story/Story/Media/Photos/PhotosSaver.swift`. |
| Capture timestamp survives persistence? | **Partially/weakly.** `AssetModel.createdAt = .now` at PERSIST time, not the true capture instant; the original file's creation date is not read. | `Models.swift` init default. |
| Orientation survives persistence? | **Yes (Package B).** The movie file is written upright via `RotationCoordinator`; the baked-in rotation survives because adopt is a pure file move. | `ContinuousCameraController` orientation + `MediaStore.adoptCapturedFile`. |
| Imported Photos assets retain original location + capture time? | **No — actively lost.** The picker does `loadTransferable(type: Data.self)` → raw bytes → reads only `AVURLAsset.duration`; never reads the `PHAsset` `creationDate`/`location`, and `Data` transferable can drop container metadata. `createdAt` becomes import time. | `apps/ios/Story/Story/Features/StoryHome/StoryPhotosPicker.swift`. |

**Net:** location is 100% absent end-to-end; capture timestamp is approximate (persist-time); orientation
is the one correct piece. Imported media loses its real date and location.

### Contract decision (the task's gate)

`AssetModel`/`MomentModel` are **local-only SwiftData models**, never serialized to any backend wire
contract (grep confirms zero DTO/encode coupling), and `Models.swift` already uses the optional-+-defaulted
additive-migration pattern 62 times. Adding location fields is a routine lightweight migration — **NOT a
frozen persistence-contract change.** The frozen contracts are the backend schemas (EditPlan/2,
music_plan/1, moment_understanding/1, etc.), none of which touch these models. **Therefore Part A is
cleared to proceed with bounded implementation — no contract stop required.**

### Smallest implementation proposal

1. **`CaptureLocationService`** — thin `CLLocationManager` wrapper; requests **When-In-Use** permission
   lazily on first camera open; keeps the most recent fix with timestamp + horizontal accuracy; recording
   NEVER awaits a fix (non-blocking).
2. **Associate fix with capture time** — on clip finish, take the cached fix only if its timestamp is
   within a freshness window (≈60 s) of recording start; else store `nil` (honest "unknown").
3. **Store on `AssetModel`** (additive, optional+defaulted, no migration step): `latitude: Double?`,
   `longitude: Double?`, `locationAccuracyMeters: Double?`, `capturedAt: Date?` (true capture instant).
4. **Embed where supported** — set `AVCaptureMovieFileOutput` metadata / connection location at record
   start so the `.mov` carries GPS; set `PHAssetChangeRequest.location` on the Photos copy. Both degrade
   silently with no fix.
5. **Imported media** — read the picked `PHAsset` `creationDate` + `location` (carry the asset identifier
   through the picker) and store on the import's `AssetModel`; stop losing them.
6. **Privacy** — the render/export path (`MediaEngineV1`) must NOT copy GPS into generated output by
   default. The renderer composes a fresh output (no container passthrough), so this is naturally satisfied;
   add an explicit assertion/test that the exported file has no GPS.

### Estimate (realistic)

- Implementation ≈ **6–8 h** · Physical-device testing ≈ **4–5 h** · **Total ≈ 10–13 h (~1.5 days).**
- Risk: **Low** — additive, no engine change, recording never gated on location.

---

## Part B — Facial Enhancement Feasibility (AUDIT ONLY — do not implement)

| | **A. Natural exposure/tone** (existing camera APIs) | **B. Face-aware skin enhancement** (capture-time) | **C. Post-capture at render** |
|---|---|---|---|
| APIs | `AVCaptureDevice` exposure/WB/`videoHDR`, `setExposureTargetBias` (already shipped in Increment 2) | Vision (`VNDetectFaceLandmarks`) + Core Image/Metal per-frame + `AVCaptureVideoDataOutput` | Core Image/Vision/Metal offline over rendered frames in `MediaEngineV1` |
| Appears in preview AND recording? | Both (device-level) | Preview + recording ONLY if you abandon `AVCaptureMovieFileOutput` and write processed frames via `AVAssetWriter` | Recording only (not live preview) |
| `ContinuousCameraController` changes | Minimal (reuse exposure/HDR config) | **Major** — replace `AVCaptureMovieFileOutput` with `AVCaptureVideoDataOutput`→Core Image→`AVAssetWriter` | None |
| Keep `AVCaptureMovieFileOutput`? | **Yes** | **No** — dealbreaker: removes the proven movie-output engine Package B is built on | **Yes** |
| Frame-rate / resolution impact | None | High — per-frame detect + filter; likely 30 fps / lower res on older devices | None live; adds render time |
| Audio-sync risk | None | **High** — manual `AVAssetWriter` audio interleave (the exact bug class Package B's engine avoids) | Low (audio already muxed) |
| HDR / color-space | Native | **Hard** — must handle 10-bit HDR / P3 in the filter chain or clip color | Must match render pipeline space |
| Device / battery | Negligible | Heavy (Vision + Metal per frame) | Moderate, one-time per render |
| Est. effort | ~4–6 h | ~5–8 days (new capture pipeline + safety re-proofing) | ~3–5 days (new render stage) |
| Story gen/export latency | None | None (capture-time) | + per-render cost (detect + filter per output frame) |

**Reading:** Option **B destabilizes the completed Package B camera** — it forces replacing
`AVCaptureMovieFileOutput` with a hand-rolled `AVAssetWriter` pipeline, re-introducing the
audio-sync/interruption/HDR risks the current engine was proven against. That violates "do not
destabilize." Option **A** is nearly free and half-present (exposure bias shipped) but is *tone*, not
skin-smoothing. Option **C** keeps the camera untouched and is the only place true face-aware enhancement
can live without risking capture — at the cost of per-render latency.

### Product requirements (if implemented later)

Optional + user-controlled; OFF by default initially; natural-looking; preserve facial features & skin
tone; no automatic reshaping; no silent enhancement of imported footage; clear indication when enabled.
Only Option **C** can satisfy all of these without touching the capture engine.

---

## Recommended scope

- **MVP (now, Part A):** location metadata — ~1.5 days, additive, low-risk, no contract change. **Build it.**
- **MVP-adjacent (optional, Part A-lite):** Option **A** natural tone (subtle auto-exposure/HDR nudge) for a
  cheap "looks better" win — but it is NOT beautification.
- **Post-MVP (Part B real beautification):** Option **C** (render-time, face-aware) — the only option
  satisfying all product requirements without touching the camera, at the cost of per-render latency.
- **Reject:** Option **B** (capture-time skin enhancement) — replaces the Package B recording engine.

## Required tests & risks (Part A)

- Tests: permission grant/deny/undetermined; fix-freshness association (stale → `nil`); no-fix path
  (airplane mode) stores unknown + still records; imported `PHAsset` date/location read; **exported Story
  has NO GPS** (privacy assertion); Photos copy carries location; additive migration loads an old store
  cleanly.
- Risks: location-permission UX (mitigated: lazy, non-blocking); battery (mitigated: significant-change /
  one-shot, not continuous high-accuracy); the privacy guarantee must be a real test, not an assumption.

## Decision gate

Stop before implementing any new video-processing or rendering engine. Part A is cleared to build (no
contract change); Part B remains audit-only. Owner chooses whether to implement Part A now.

---

## Implementation Results — Part A location metadata (commit `90651c5`, DEVICE-ACCEPTED 2026-10-18)

**Status:** implemented, parse-clean, committed, **device-accepted** (owner verified actual metadata in
all four file types). iOS-only; additive; no render-pipeline change (Part B remains deferred). Nothing
pushed/deployed.

### What shipped (all 7 safeguards met)

| # | Safeguard | Delivery |
|---|---|---|
| 1 | Permission UX | `CaptureLocationService` requests **When-In-Use only after** a benefit-first explainer (shown once via `@AppStorage`). Camera startup + recording never await authorization. `NSLocationWhenInUseUsageDescription` added to `Info.plist` (merged via `GENERATE_INFOPLIST_FILE`, confirmed by the already-working `UIAppFonts` from the same plist). |
| 2 | Location quality | `fix(at:)` validates **freshness (≤60 s of the capture instant) AND horizontal accuracy (>0, ≤100 m)**; else `nil` = unknown. No reverse-geocode, no venue/place name. |
| 3 | Persistence | `AssetModel` + optional/defaulted `capturedAt`, `latitude`, `longitude`, `locationAccuracyMeters` (lightweight additive migration — existing populated store loads clean). `capturedAt` (true capture instant) kept separate from `createdAt` (persist/import time). |
| 4 | Original + Photos | `.mov` carries ISO-6709 GPS via `movieOutput.metadata` at record start; `PhotosSaver` sets `creationDate` + `location` on the Photos copy. |
| 5 | Imports | `ImportedMediaMetadata` recovers creation date + ISO-6709 location from the file's OWN embedded metadata (no PHAsset/asset-id dependency; works without Photos read-auth); `nil` when absent. |
| 6 | Privacy | `MediaEngineV1` builds a fresh `AVMutableComposition` and sets NO metadata → exports carry no GPS by construction (render pipeline untouched). |
| 7 | Regression | Additive only; recording path, camera controls, AI scan, orientation, Moment persistence, Story generation unchanged. |

### Device acceptance — ACTUAL metadata verified by owner
- **Story-recorded `.mov`:** GPS present (when a trustworthy fix existed) + correct capture time. ✅
- **Apple Photos copy:** correct creation date + location. ✅
- **Imported media:** original creation date + location recovered from the file; graceful when absent. ✅
- **Generated Story export:** NO precise GPS. ✅ (the privacy guarantee, confirmed on the real file)

### Files
New: `apps/ios/Story/Story/Media/Camera/CaptureLocationService.swift`,
`apps/ios/Story/Story/Media/Photos/ImportedMediaMetadata.swift`,
`apps/ios/Story/StoryTests/CameraMetadataTests.swift`.
Changed: `Media/Photos/PhotosSaver.swift`, `Data/Persistence/Models.swift`,
`Media/Camera/ContinuousCameraController.swift`, `Features/Capture/ContinuousCaptureModel.swift`,
`Features/Capture/ContinuousCaptureView.swift`, `Features/StoryHome/StoryPhotosPicker.swift`,
`Domain/UseCases/StoryUseCases.swift`, `Story/Info.plist`.

### Tests
Pure fix-validation (fresh+accurate / stale / inaccurate / negative-accuracy) + ISO-6709 and capture-date
parsing (`CameraMetadataTests`). Device-dependent paths (CLLocationManager delegate, `.mov` embedding,
Photos metadata, live import recovery, no-GPS export) verified in physical-device acceptance above.

### Status of the overall task
- **Part A: DONE + device-accepted.**
- **Part B (facial enhancement): deferred** per owner — not implemented. Recommendation on record: Option
  C (render-time, post-MVP); reject Option B (capture-time, would replace the movie-output engine).
