# 10 — Media Engine

> **SUPERSEDED-IN-PART / RECONCILED (R-a, 2026-10-07).** The archived body below is **pre-E2** and stale: it
> references `EditPlan.segment.crop`/`style`, `CreativeIntent.style`, and a single `music_track_id` + bundled
> beat-marker JSON, predating frozen `edit_plan/2`, `music_analysis/1`, and `music_plan/1`. The still-valid
> decisions — **on-device AVFoundation, pure execution, no AI, EditPlan is the only creative input, fail (don't
> skip) on a missing asset** — are carried forward. Current design is this top section; see
> `milestone-ra-media-engine-v1-feasibility.md` and the spike
> `apps/ios/Story/Story/Media/Render/MediaEngineV1.swift`. **Design + feasibility only — the production Media
> Engine is NOT implemented; nothing has been rendered (AVFoundation export is not runnable in the design
> sandbox; it requires Xcode/device).**

## Current design (R-a, E2-aware)

### Role
Deterministic on-device renderer. Consumes a frozen **EditPlan/2** (+ **MusicAnalysis/1**, + optional authorized
**MusicAsset**) and produces a playable H.264 MP4. **Executes the plan; never reinterprets Story intelligence.**

### Location — on-device (AVFoundation)
Originals already live on-device (`MediaStore`: `media/<uuid>.mov`). On-device `AVMutableComposition` +
`AVAssetExportSession` avoids uploading private source media and needs no cloud infra. Server-side rendering is
rejected for MVP. (R-a §2.)

### Pipeline
`EditPlan/2 → resolve each segment.asset_id (Moment id) via MediaStore → per segment: trim (CMTimeRange) → speed
(scaleTimeRange 0.5–2.0x) → aspect-fill reframe (vertical 1080×1920 default / square / landscape) →
concatenate → transitions (cut | 0.3s crossfade) → native-audio mix (keep=1.0/duck=0.25/mute=0.0) + optional
soundtrack gained by MusicPlan.audio_strategy → optional beat/downbeat/highlight cut-snap (±0.15s, ONLY when
alignment requested AND tempo_reliable) → AVAssetExportSession → MP4 → playback / Photos|Files when authorized.`

### EditPlan/2 field mapping + native-audio policy
See `milestone-ra-media-engine-v1-feasibility.md` §3 (field-by-field execution) and §5 (native-audio gain policy:
`keep` preserves captured audio AND steps the soundtrack back per `audio_strategy` — the real sound leads; it does
NOT let the soundtrack drown the source). No model-authored sample-level audio curves. A missing Moment is a hard
failure, never a silent skip. Instructions the renderer cannot execute → a typed capability rejection, never a
silent drop. `crop`/`transition` are expressible but planner-unused today → documented V1 defaults (center
aspect-fill; always-cut), honored if a future plan emits them.

### V1 scope
trim, order, output duration, aspect/crop-fit, straight cuts, basic 0.3s crossfade, 0.5–2.0x speed, native-audio
keep/duck/mute, optional single soundtrack, export, playback, Photos/Files save. **NOT V1** (Creative Editing V2):
masking, split-screen, layered compositing, generative footage, motion transitions, speed ramps, color grading.

### Status
R-a = design + a `swiftc -parse`-clean spike whose EditPlan/2 + MusicAnalysis/1 decode is field-aligned to the
frozen contracts. Rendering/latency/memory are REQUIRES-DEVICE (the §14 acceptance gate). No contract change
needed. R-b = build V1 for real + run the device gate.

---
---ARCHIVED (pre-E2, retained for history; NOT the current design)---

## Overview

Deterministic video processing. Consumes an `EditPlan` and produces a finished vertical MP4. No AI, no creative decisions — pure execution. The hard boundary between intelligence and output.

---

## Requirements

- `EditPlan` is the only input — media engine makes no creative decisions
- Supported operations in MVP: trim, concatenate, crop/reframe (to 9:16), speed adjustment (0.5x–2.0x), transitions (cut and crossfade only), music overlay, basic beat alignment, export
- No timeline editor exposed to user
- No generative AI, no frame synthesis
- Export time: < 15 seconds for a 5–15 second Story on iPhone
- Output: H.264 vertical MP4, 1080×1920, suitable for direct posting to Instagram/TikTok
- Music library: 5–10 curated licensed tracks, one mapped to each style template
- If a segment references a missing asset: fail the export with a clear error — do not silently skip

---

## Design

**Implementation:** AVFoundation `AVMutableComposition` on-device. All processing on iPhone — no server-side video in MVP.

**Processing pipeline:**
```
EditPlan
        ↓
For each segment:
  Load asset (AVURLAsset)
  Apply trim (CMTimeRange)
  Apply speed (scaleTimeRange)
  Apply crop/reframe (AVVideoComposition transform)
        ↓
Concatenate (AVMutableComposition)
        ↓
Apply transitions (AVVideoCompositionInstruction crossfade = 0.3s dissolve)
        ↓
Mix music (AVMutableAudioMix)
        ↓
Beat sync (snap cuts to nearest beat marker within ±0.15s)
        ↓
Export (AVAssetExportSession → MP4, 1080×1920, H.264)
```

**Crop to 9:16:** Center crop for landscape source. Use explicit `EditPlan.segment.crop` offsets when provided.

**Transitions:** `cut` = frame-accurate. `crossfade` = 0.3-second dissolve.

**Music tracks:** Stored in app bundle. Each track has AAC audio file + beat marker JSON (array of timestamps). Default track selected by matching `CreativeIntent.style`.

---

## Tasks

**Phase 1:**
- [ ] Implement basic AVMutableComposition (trim + concatenate)
- [ ] Implement 9:16 center crop
- [ ] Implement static music overlay (no beat sync yet)
- [ ] Implement AVAssetExportSession → MP4 1080×1920
- [ ] Measure export time on iPhone (target < 15s)
- [ ] Run end-to-end: hard-coded EditPlan → finished MP4 on device

**Phase 9 (full implementation):**
- [ ] Implement speed adjustment
- [ ] Implement crossfade transition
- [ ] Implement explicit crop from EditPlan segment
- [ ] Implement beat marker loading and cut snapping
- [ ] Curate and license 5–10 music tracks; produce beat marker JSON for each
- [ ] Map tracks to style templates
- [ ] Add export error handling with clear user-facing messages
- [ ] Test with: landscape clips, portrait clips, mixed orientations, slow/fast clips
