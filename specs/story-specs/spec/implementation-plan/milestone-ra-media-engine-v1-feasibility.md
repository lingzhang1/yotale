# Milestone R-a — Media Engine V1 Design + Rendering Feasibility

**Status: DESIGN + FEASIBILITY SPIKE ONLY — STOP for owner review.** No full production Media Engine, no
Create/Result UX, no Creative Editing V2, no commercial export, no production usage-report/safelisting, nothing
pushed. The Swift spike (`apps/ios/Story/Story/Media/Render/MediaEngineV1.swift`) is `swiftc -parse` clean but
**NOT rendered** — AVFoundation export cannot run in the Kiro sandbox. Rendering is explicitly REQUIRES
PHYSICAL IPHONE/XCODE.

---

## 1. Media Engine V1 architecture
Pure-execution, on-device AVFoundation. **It executes a frozen EditPlan/2; it makes no creative decisions and
never reinterprets Story intelligence.**
```
EditPlan/2 (+ MusicAnalysis/1, + optional LOCAL soundtrack)
  -> resolve each segment.asset_id (Moment id) -> on-device file URL via MediaStore (media/<uuid>.mov)
  -> per segment: AVURLAsset -> trim (CMTimeRange from source_start/end) -> speed (scaleTimeRange, 0.5–2.0x)
                 -> 9:16/sq/landscape aspect-fill transform (AVVideoCompositionLayerInstruction)
  -> concatenate into AVMutableComposition (video + capture-audio tracks)
  -> transitions: cut (frame-accurate) | crossfade (0.3s dissolve, overlap)
  -> native-audio mix: per-segment capture gain keep=1.0/duck=0.25/mute=0.0 (AVMutableAudioMix)
     + optional soundtrack track gained by MusicPlan.audio_strategy (see §5)
  -> optional cut-snap to beat/downbeat/highlight (±0.15s) ONLY when alignment requested AND tempo_reliable
  -> AVAssetExportSession -> H.264 MP4 (1080x1920 vertical default) -> local file -> playback / Photos|Files
```
Depends only on AVFoundation + the frozen contracts + `MediaStore`. No new backend, no server video, no new infra.

## 2. On-device vs server — **RECOMMENDATION: on-device (A)**
Originals already live on-device (`MediaStore` resolves `media/<uuid>.mov`); on-device rendering avoids uploading
private source media, needs no cloud infra, and keeps the privacy posture (local-first). AVFoundation
`AVMutableComposition` + `AVAssetExportSession` is the standard, battery/throughput-reasonable path for 5–60s
Stories. **Server-side rendering is REJECTED for MVP** (would require uploading originals + building render infra
with no evidence of need). Revisit only if device export latency/thermals prove unacceptable on real hardware
(a device-gate measurement, §9/§14). No cloud rendering built.

## 3. EditPlan/2 field execution mapping
| Field | V1 handling | AVFoundation support |
|---|---|---|
| `segments[].asset_id` (Moment id) | resolve to local URL via MediaStore; **missing ⇒ hard fail** (never skip) | direct (AVURLAsset) |
| `source_start_seconds` / `source_end_seconds` | `CMTimeRange` trim | direct |
| `output_duration_seconds` | segment length on the timeline; with speed, drives `scaleTimeRange` | direct |
| `speed` (0.5–2.0) | `scaleTimeRange(inserted, toDuration:)` | direct |
| `output_format` (vertical/square/landscape) | render size 1080×1920 / 1080×1080 / 1920×1080 | direct |
| `native_audio` (keep/duck/mute) | per-segment capture-audio gain via AVMutableAudioMix (§5) | **custom composition** (gain envelope) |
| `music_alignment.anchor` (beat/downbeat/highlight) | snap the segment's cut to the nearest grid point ±0.15s, **only if tempo_reliable** | **custom** (uses MusicAnalysis/1 times) |
| `music_asset_id` | load the authorized LOCAL soundtrack file; mix per audio_strategy | custom (single AVMutableCompositionTrack) |
| `target_duration_seconds` | invariant check (sum of outputs ≈ target); the planner already enforced ±20% | n/a (validation) |
| `crop` (CropInstruction) | **present in the contract but the planner does NOT populate it** → V1 uses deterministic center aspect-fill; honor explicit crop in a later pass | custom (transform) — **deferred, not ignored** |
| `transition` (TransitionInstruction) | planner currently emits none (engine set it None); V1 realizes `cut` always + `crossfade` 0.3s if ever present | cut=direct; crossfade=custom |
| `narrative_role` | not an execution instruction (planning provenance) | ignored by design (documented) |

**No plan instruction is silently ignored.** The two fields the planner does not currently emit (`crop`,
`transition`) are handled by documented defaults; if a future plan DOES carry a `crop`/`transition` the engine
honors it. Anything the renderer genuinely cannot execute → a deterministic `MediaEngineError` (capability
rejection), never a silent drop.

## 4. Unsupported-field analysis / capability negotiation
V1 cannot do (→ Creative Editing V2): masking, split-screen, layered compositing, generative footage, motion
transitions, speed ramps (continuous), color grading. The frozen EditPlan/2 **cannot express any of these**
(no such fields), so there is no silent-ignore risk. If V2 later adds such fields, the engine must advertise a
capability set and **reject** a plan that needs an unsupported one (typed error), rather than approximate it.
**No frozen-contract change is proposed in R-a.**

## 5. Native-audio mix policy (deterministic, no model curves)
`native_audio` controls the Moment's OWN captured audio: **keep=1.0, duck=0.25, mute=0.0** (coarse per-segment
gain). Crucially, **`keep` does not mean the soundtrack drowns the source** — the SOUNDTRACK gain *under* a kept
segment is set by `MusicPlan.audio_strategy`, not by the model:
| native_audio | audio_strategy | soundtrack gain under the segment |
|---|---|---|
| keep | priority=important, role=sparse | **0.0** (silence the music; the real sound leads) |
| keep | priority=important | 0.12 |
| keep | priority=selective | 0.2 |
| keep | priority=low | 0.35 |
| duck/mute | role=continuous / supportive / sparse | 1.0 / 0.8 / 0.5 |

Mapped to the five cases: **guitar performance** (keep + important) → music steps to ~0.12/0.0; **birthday
singing** (keep + important) → same; **solitude room tone** (keep + sparse) → barely-there pad; **energetic skate
impact** (keep + selective, continuous role) → loud music but the board-clack punches through; **ordinary montage**
(duck, continuous) → music carries. Exact fade ramps are a bounded V1 follow-up (linear volume ramps at segment
boundaries) — still deterministic, still no AI.

## 6. Music asset handling
First render experiment uses a **locally owned/licensed test audio file OR no soundtrack** — never Epidemic
Free-tier music in a distributed/exported result. Future production path: the renderer accepts an **authorized,
temporary MusicAsset download** (expiring link from the paid-tier adapter), holds it only for the render job,
discards the source audio after export, and respects the no-cache/retention terms. **No production usage-report
or safelisting is implemented in R-a.**

## 7. Technical spike — implementation + results
`apps/ios/Story/Story/Media/Render/MediaEngineV1.swift` (275 lines): EditPlan/2 + MusicAnalysis/1 `Decodable`
DTOs, `buildComposition` (trim/speed/concat/reframe + hard-fail on missing Moment), `aspectFillTransform`,
`buildAudioMix`, `snappedCut` (beat/downbeat/highlight, tempo-gated), `NativeAudioPolicy`, typed errors, output
sizing for all three formats.
- **VERIFIED IN ENVIRONMENT:** `swiftc -parse` clean (syntax); **the renderer's EditPlan/2 + MusicAnalysis/1
  decode field names match the frozen contracts exactly** (cross-checked every Swift CodingKey against the
  generated JSON — all present; the DTO is a safe subset, extra contract fields ignored by Decodable).
- **REQUIRES PHYSICAL IPHONE/XCODE (not run here):** AVMutableComposition assembly, AVAssetExportSession export,
  the actual MP4, orientation/crop pixels, crossfade frames, audio mix, latency/memory. AVFoundation export has
  no sandbox path.

## 8. Actual rendered output
**None produced** — rendering cannot run in the sandbox. The five spike CASES (A montage / B native audio /
C orientation / D crossfade / E duration) are specified as the on-device acceptance set (§14); they are the
device-gate, not claimable here. I will not assert a successful render from a parse.

## 9. Performance observations
Not measurable in-env. Targets to confirm on device: export < ~15s for a 5–15s Story; peak memory bounded (stream
export, don't hold all frames); thermals acceptable; export reliable (handle `AVAssetExportSession` interrupted/
failed). All flagged REQUIRES DEVICE.

## 10. Test coverage
- **VERIFIED IN ENVIRONMENT:** parse-clean; DTO↔contract field alignment; the deterministic policy functions
  (`captureGain`, `soundtrackGainUnder`, `snappedCut`) are pure and unit-testable in Xcode (XCTest authored
  alongside when the engine is built). Backend suite remains **199 pass** (no backend change this milestone).
- **REQUIRES DEVICE/XCODE:** frame accuracy, audio sync, duration tolerance, orientation, aspect ratio,
  transition correctness, playback, latency, memory, file persistence, cancellation/failure recovery.

## 11. Creative Editing V2 capability audit (design-only)
Techniques needing MORE visual evidence than current MomentUnderstanding provides:
| Technique | Needs | Current MU sufficient? |
|---|---|---|
| match cuts | shared motion/shape/position across clip ends | No — needs end-frame motion vectors / salient-region evidence |
| motion transitions | camera-motion direction at cut boundaries | No — needs per-clip boundary motion |
| speed ramps | moments of peak action within a clip | Partial — `events` timing helps; no intra-clip intensity curve |
| sound bridges | audio onset/continuity across cuts | No — needs audio-event timing (we have none per-Moment) |
| color continuity | per-clip color/white-balance summary | No |
| split screen / layered compositing | spatial salient-region maps | No |
**Proposal (DO NOT implement, do NOT reopen AU/Edit-Planner prompts):** a future **Edit Evidence** stage —
a cheap, deterministic per-Moment pass (end-frame motion, dominant color, audio-onset times) feeding V2 only.
MVP V1 needs none of it. Recorded as a V2 prerequisite.

## 12. Recommended V1 implementation sequence
1. Build `MediaEngineV1` for real against this spike: trim + concat + 9:16 reframe + straight cuts + export
   (spike Case A) — the smallest playable path.
2. Add native-audio mix (keep/duck/mute + soundtrack gain policy §5) — Cases B.
3. Add orientation/format handling + explicit crop fallback — Case C.
4. Add 0.5–2.0x speed + 0.3s crossfade — Case D.
5. Duration-tolerance assertion + typed failure/cancellation + Photos/Files export when authorized — Case E.
6. XCTest the pure policies + a device integration test harness.
7. Device gate (§14) + perf measurement. (Local licensed test track for soundtrack; no Epidemic export.)

## 13. Blockers / contract issues
- **No frozen-contract contradiction found.** `crop`/`transition` are expressible but planner-unused → V1
  defaults (documented), not a conflict.
- `10-media-engine.md` was **pre-E2 stale** (referenced `EditPlan.segment.crop`/`CreativeIntent.style`/
  `music_track_id`); reconciled this milestone (banner-superseded, E2-aware body added).
- **Environment blocker:** AVFoundation rendering is not runnable in the Kiro sandbox → all rendering claims are
  deferred to the device gate. This is a tooling limit, not a design gap.
- Production soundtrack needs the paid Epidemic tier + the authorized-download/retention terms (still open from
  M-d; the adapter stays prototyping-only).

## 14. Physical-iPhone acceptance checklist (rebuild in Xcode on device)
1. **Case A montage:** 3 real Moments → trims → straight cuts → ONE playable MP4; plays start to finish.
2. **Case B native audio:** a Moment with meaningful source audio (guitar-like) set `native_audio=keep` → its
   audio is clearly audible; a `duck` montage segment has the soundtrack on top.
3. **Case C orientation/format:** mixed portrait + landscape inputs → correct orientation, center-crop, output is
   true 1080×1920 (no squeeze, no black bars where fill is expected).
4. **Case D crossfade:** one 0.3s crossfade → smooth dissolve, no black frames, no invalid overlap.
5. **Case E duration:** rendered duration ≈ the EditPlan total within a small tolerance (±0.3s).
6. Export completes < ~15s for a ~12s Story; app stays responsive; no thermal/memory crash.
7. Output saves to Photos/Files when authorized; survives relaunch (local file).
8. A plan referencing a missing Moment fails with a clear error (no silent skip, no partial garbage).
Send pass/fail per case; I turn any failure into a fix or a regression test.

## 15. Is R-b ready to begin?
**Yes — R-a design is complete and unblocked for R-b (build V1 for real).** The architecture, field mapping,
native-audio policy, and the parse-clean spike with contract-aligned decode give R-b a concrete, low-risk start.
R-b should implement §12 steps 1–5 and run the §14 device gate. **No frozen contract needs to change.** The only
true external gate remains production music licensing (paid tier), which does NOT block basic local rendering
(local test track / no soundtrack).

**STOP for owner review. No production Media Engine, no Create/Result UX, no Creative Editing V2, no commercial
export, nothing pushed.**
