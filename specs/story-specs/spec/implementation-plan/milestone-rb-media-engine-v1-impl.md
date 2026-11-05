# Milestone R-b — Production Media Engine V1 + First Rendered Story: REPORT

**Status: IMPLEMENTED (iOS), parse-clean + unit-tested; STOP at the physical-device gate.** First real render is
the device gate — AVFoundation export is NOT runnable in the design sandbox, so no MP4 is produced here and no
rendering is claimed. No Create/Result UX, no Creative Editing V2, no commercial Epidemic export, no new infra,
nothing pushed. Backend unchanged (199 tests). App commit `8e67f23`; specs `41435b2`. Unrelated untracked
`milestone-e2c-phase1-reconciliation.md` preserved.

---

## 1. Commits by batch
Single iOS commit `8e67f23` covering Batches A–D + harness + tests (one cohesive Swift module; the batches are
layers of the same engine, kept in one commit for a coherent parse/compile unit). Breakdown:
- **A (basic render):** `MediaEngineV1.buildComposition` + `render`/export + `RenderOutputStore`.
- **B (native audio):** `NativeAudioPolicy` + time-ranged `buildAudioMix` with boundary ramps.
- **C (format/transitions/speed):** `OutputSize`, `aspectFillTransform`, speed `scaleTimeRange`, crossfade hook.
- **D (duration/persistence/failure):** duration verify, cancellation, partial-output cleanup, persistent
  `rendered/<uuid>.mp4`, Photos (`PhotosSaver`) + Files (`ShareLink`).
- Harness `RenderTestHarnessView` (DEBUG-only) + `MomentResolver`/`DebugEditPlanFixture` + `MediaEngineV1Tests`.

## 2. Architecture
On-device AVFoundation, pure execution of a frozen `edit_plan/2`:
`resolve Moment id→local URL (MediaStore) → AVURLAsset → trim (CMTimeRange) → speed (scaleTimeRange 0.5–2.0x) →
aspect-fill reframe → concatenate (AVMutableComposition) → cut / 0.3s crossfade → native-audio AVMutableAudioMix
(+ optional local soundtrack) → optional tempo-gated cut-snap → AVAssetExportSession → H.264 MP4 (1080×1920
default) → persist under <Documents>/rendered → playback / Photos|Files.` No server rendering, no network, no AI.

## 3. EditPlan/2 field execution coverage
`asset_id` (local resolve; **missing ⇒ `MediaEngineError.missingMoment`, hard fail**), `source_start/end` (trim),
`output_duration` (timeline length), `speed` (scaleTimeRange), `output_format` (vertical/square/landscape),
`native_audio` (per-segment capture gain), `music_alignment` (tempo-gated snap), `music_asset_id` (optional local
soundtrack track), `target_duration` (duration verify). `crop`/`transition` honored if present (planner emits
none today → center aspect-fill + always-cut defaults). An unexecutable instruction → typed error, never silent.

## 4. AVFoundation composition / export
`buildComposition` returns the composition + video composition + per-segment time ranges + optional soundtrack
track + total duration (separated from export so unit tests can assert timing without exporting). `render(...)`
is `async`, cancellable (polls `shouldCancel` → `cancelExport`), reports `progress`, verifies output duration vs
plan (±0.3s), and **cleans up partial output on failure/cancel**. Source Moments are never modified.

## 5. Audio-mixing behavior
Per-segment capture gain keep=1.0 / duck=0.25 / mute=0.0 applied over each segment's time range with short 0.08s
linear ramps (no clicks). Soundtrack gain *under* each segment is set by `MusicPlan.audio_strategy`: keep+important
+sparse → 0.0 (music silent, real sound leads); keep+important → 0.12; duck/continuous → 1.0. **No model
sample-level curves.**

## 6. Transition / speed handling
Straight cut (frame-accurate, default). 0.3s crossfade hook present (realized when a plan carries a crossfade
transition). Speed 0.5–2.0x via `scaleTimeRange` to the planned output duration. Beat/downbeat/highlight cut-snap
(±0.15s) applies ONLY when alignment is requested AND `tempo_reliable` — ambient (bpm=0) is never snapped.

## 7. Local output persistence
`RenderOutputStore` writes `<Documents>/rendered/<uuid>.mp4` (relative path persists across relaunch, like
`MediaStore`). Playable via AVKit; savable to Photos (add-only) and Files (ShareLink). Survives relaunch.

## 8. Debug test harness
`RenderTestHarnessView` — **`#if DEBUG` only, never in Release / consumer flow**. Select a Story → render a
deterministic montage fixture over its local Moments → progress + cancel → play the MP4 → inspect duration +
dimensions → Save to Photos / Share to Files. The real-Edit-Planner toggle is present but **disabled** pending a
backend deploy (§9). No Epidemic; optional local soundtrack only.

## 9. Real EditPlan integration status — REQUIRES BACKEND DEPLOY
Case G (real `/v1/edit-plan` → renderer) is wired but gated: the deployed App Runner backend currently exposes
**only `/v1/music-direction`** (verified: `POST /v1/edit-plan` → **404**, `/health` → 200). `/v1/edit-plan` +
`/v1/music/candidates` were added in M-d but **not yet deployed**. Exact action to enable Case G: **redeploy the
backend** (the frozen throwaway CodeBuild → ECR → App Runner path used in prior milestones) after confirming the
regression gate — which is green now (**199 backend tests pass**). I did NOT deploy (no auto-push / stop posture).
Once deployed, flip the harness toggle and the real-AI-plan path runs.

## 10. Tests actually run
- **VERIFIED HERE:** `swiftc -parse` clean on all 4 R-b Swift files; `MediaEngineV1Tests` authored (8 cases:
  output size, aspect-fill uniform-scale, capture gain, soundtrack step-back, cut-snap tempo-gating,
  EditPlan/2 decode, missing-Moment hard-fail, infeasible rejection) — pure logic, no export; backend suite
  **199 pass** (unchanged).
- **REQUIRES XCODE / PHYSICAL IPHONE:** the XCTest run itself (needs the SwiftData macro + simulator), and all
  actual rendering/export/playback. **No video produced; no render claimed.**

## 11. Known unverified device-only behavior
Actual MP4 render + playback; orientation/crop pixels; crossfade frames; audio sync + gain audibility; export
latency/memory/thermals; Photos/Files save; cancellation mid-export; partial-cleanup on real failure. All are the
§13 device gate.

## 12. Deployment status
Nothing deployed. Backend redeploy is REQUIRED only for Case G (real AI plan); Cases A–F render from a local
fixture and need no backend. Regression gate green (199). Owner authorizes the redeploy.

## 13. Physical-iPhone acceptance gate (rebuild in Xcode; open the DEBUG harness on a Story with local Moments)
- **A Basic montage:** 3 real Moments → one playable MP4, correct order + trims, no black frames.
- **B Native audio:** include a meaningful-audio Moment → `keep` audible, `duck` lowered, `mute` removed; optional
  local music does not drown kept native audio.
- **C Orientation:** mixed portrait + landscape → correct orientation, no stretch, aspect-fill, true 1080×1920.
- **D Transitions/speed:** straight cut; 0.3s crossfade (no invalid overlap / black frames); 0.5x & 2x where set
  (no audio desync).
- **E Duration/persistence:** output ≈ plan ±0.3s; survives relaunch; Photos/Files export when authorized; source
  Moments intact.
- **F Failure:** reference a nonexistent Moment → clear error, no partial output, no silent skip.
- **G Real AI plan (after backend redeploy):** `/v1/edit-plan` plans real Moments → renderer executes → playable
  result, no fabricated assets.

## 14. Performance measurements
None (device-only). Targets to confirm: render < ~15s for a 5–15s Story; bounded memory; responsive UI;
clean cancellation; no thermal failure. Report actual numbers from the device run.

## 15. Remaining Media Engine limitations
V1 only: trim/order/reframe/cut/crossfade/speed/native-audio/optional-soundtrack/export. No masking, split-screen,
layered compositing, motion transitions, continuous speed ramps, color grading, generative footage (Creative
Editing V2). Audio ramps are simple linear boundary fades. Soundtrack is a single track. Crop uses center
aspect-fill (explicit crop honored if a plan ever carries it).

## 16. Is R-b ready for device acceptance? — **YES**
Engine + harness + tests are implemented and parse-clean, EditPlan/2 field execution is complete, failure/
cancellation/persistence are handled, and the decode contract is field-aligned to the frozen contracts. The owner
can rebuild in Xcode and run Cases A–F now; Case G after a backend redeploy. No frozen contract needs to change.

## 17. Recommended next milestone (after device acceptance)
**R-c — Create/Result UX** (wire the real renderer into the frozen Figma Create My Story → Result flow, replacing
the mock GeneratedOutput; keep the DEBUG harness for diagnostics). Then production music (paid Epidemic tier +
authorized download + usage-report/safelisting) and, separately, **Creative Editing V2** (begins with the R-a
Edit Evidence stage). None started.

**STOP at the device gate. No R-c, no Creative Editing V2, no commercial Epidemic export, nothing pushed.**
