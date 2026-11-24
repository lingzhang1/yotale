# 09 — Edit Planner

> **SUPERSEDED-IN-PART / RECONCILED (M-d.2 + M-d.3, 2026-10-07).** The original design below the `---
> ARCHIVED` line is **pre-E2 / pre-M-b / pre-M-c** and stale: it consumes `AssetUnderstanding` with
> `usable_ranges`, a flat `CreativeIntent.desired_duration`, and a bare `music_track_id` + global `beat_sync`
> bool, and it has **no native-audio handling**. It predates StoryGuide/1, StoryCoverage/2, MomentUnderstanding,
> MusicDirection, MusicPlan/1, MusicAsset, and MusicAnalysis. The **one still-valid decision** — *AI/engine
> PLANS, Media Engine EXECUTES; never ask an LLM to edit the video* — is carried forward below. The current
> design is this top section; the archived body is kept only for history. Authoritative companions:
> `milestone-md3-api-validation-edit-planner-experiment.md` and `milestone-md3-editplan2-contract.md`.
> **Design/experiment only — no production Edit Planner or Media Engine is implemented.**

## Current design (E2-aware)

### Role
The Edit Planner finds the strongest achievable version of THIS Story from what was actually captured, and emits
a typed, executable **EditPlan** (proposed `edit_plan/2`). It plans; it does not render.

### Inputs (current contract set)
- **CreativeIntent** — the user's feel + `target_duration_seconds`.
- **StoryGuide/1** — the intended long-horizon narrative shape (dimensions).
- **StoryCoverage/2** — what the Story actually became (meaning, sufficiency) — anti-checklist; ENOUGH is
  first-class.
- **MomentUnderstanding[]** — the captured material: `observed` (summary, events with timestamps,
  `useful_segments`) + `story_context`. **Replaces the retired `AssetUnderstanding`/`usable_ranges`.**
- **MusicDirection** / **MusicPlan/1** — intended soundtrack feel + Story-level shape (`character`, `energy_arc`
  fractions, `audio_strategy{soundtrack_role, native_audio_priority}`).
- **MusicAsset** + **MusicAnalysis** — the chosen real track and its observed structure (duration, bpm, beats,
  downbeats, highlight, sections). Optional at plan time; when present, align to it.

### Responsibilities
**Edit Planner OWNS:**
- Select useful Moment **segments** (source in/out inside each Moment's `useful_segments`).
- Construct a coherent **narrative progression** grounded in Guide/Coverage — not a generic montage template; a
  minimal Story stays minimal, no manufactured quiet→build→climax.
- **Order** segments; set source in/out + `output_duration` per segment; keep total within ±20% of the **Story**
  target (never the track length).
- **Musical alignment** to real MusicAnalysis **within** MusicPlan intent — anchor the payoff near the real
  `highlight`, major cuts on `downbeat`s — **only where it serves the narrative** (alignment is optional,
  narrative-first).
- **Native-audio preservation INTENT** per segment (`keep | duck | mute`) driven by `audio_strategy`: a real
  guitar performance / birthday singing / meaningful dialogue → `keep`, music recedes; otherwise `duck`/`mute`.
- Produce a typed **EditPlan**; fail (503, never fabricate) only if no usable material exists.

**Media Engine OWNS (separate later milestone):** decode assets; apply cuts/transitions/crop/speed; **actual
audio mixing** (the real ducking/fades from the plan's intent, incl. exact snapping to the MusicAnalysis times a
segment's `music_alignment.anchor` names); render; export; (production) Epidemic download-for-render +
usage-report + safelisting.

**Hard boundary (preserved):** AI/engine generates the EditPlan; the Media Engine executes it. Never ask an LLM
to "edit the video." No model-authored sample-level mix curves.

### EditPlan contract
Proposed **`edit_plan/2`** — see `milestone-md3-editplan2-contract.md`. Extends the frozen `EditPlanContract`
additively: `+story_id, +music_plan_id, +music_analysis_ref`, per-segment `+native_audio{keep|duck|mute}` and
`+music_alignment{anchor: beat|downbeat|highlight|none}` (segment-level — **no global `beat_sync` bool**).

### Executability (deterministic gate — model never self-certifies)
Before any plan reaches the Media Engine, a deterministic validator checks: all `asset_id`s exist as Moments;
source in/out within Moment duration AND overlapping a `useful_segment`; positive output durations; monotonic
unique order; total within ±20% of target; `native_audio` present; alignment anchors only when a MusicAnalysis is
present. (Prototype + 8/8 self-test in `evals/edit_planner/`.)

### Experiment status (M-d.3)
5-scenario planning experiment (TMB real / guitar+real-audio / SF / solitude / energetic), ONE model
(`us.anthropic.claude-opus-4-6-v1`), A (MusicPlan only) vs B (+MusicAnalysis). 10/10 plans executable; native-
audio correct; MusicAnalysis helps payoff/major-cut placement on arc'd Stories but risks spurious alignment on
minimal ones → anchors default `none`, narrative-first. Two tweaks (duration discipline + alignment restraint)
pending before freezing `edit_plan/2`. No production implementation.

---
---ARCHIVED (pre-E2, retained for history; NOT the current design)---

## Overview

Takes `CreativeIntent` + understood assets and produces a complete `EditPlan`. This is Story Reconciliation — finding the best achievable story from what actually exists, not forcing assets into a predetermined structure.

---

## Requirements

- Output: typed `EditPlan` JSON — no prose. Media engine consumes this directly.
- Works for both paths:
  - **DIRECT:** original `StoryPlan` + captured assets → reconcile → `EditPlan`
  - **EDIT:** `CreativeIntent` + existing assets → discover achievable story → `EditPlan`
- Story Reconciliation: if actual assets tell a stronger narrative than the original plan, use that narrative instead
- Handles imperfect assets: produce an `EditPlan` even if some shots failed or some clips are poor quality
- Only fails if no usable material exists at all
- Every segment references `asset_id`, `start`, `end`, `speed` — no ambiguity for media engine
- Output duration within ±20% of `creative_intent.desired_duration`
- `EditPlan` includes `music_track_id` and `beat_sync` flag

---

## Design

**Pipeline:**
```
CreativeIntent
  +
AssetUnderstanding[] (all available assets with usable_ranges)
  +
StoryPlan (DIRECT only; null for EDIT)
        ↓
LLM call (reconciliation mode)
        ↓
EditPlan JSON
```

**DIRECT path prompt:** "Here is the original shot plan and the clips that were actually captured. Some shots may have failed. Produce an EditPlan that achieves the intended story as closely as possible using the available clips."

**EDIT path prompt:** "Here are the available clips and the user's creative intent. Discover the strongest story achievable from this material. You are not bound to any pre-existing plan."

**EditPlan example:**
```json
{
  "total_duration": 9.2,
  "segments": [
    {
      "asset_id": "asset_03",
      "start": 1.1,
      "end": 4.8,
      "speed": 1.0,
      "crop": null,
      "transition_in": "cut"
    }
  ],
  "music_track_id": "track_cinematic_01",
  "beat_sync": true
}
```

**Validation before passing to media engine:**
- All `asset_id` values exist in project
- All `start`/`end` within asset `usable_range`
- `total_duration` matches sum of segment durations ± rounding

**Hard boundary:** AI generates the EditPlan. Media engine executes it. Never ask an LLM to "edit the video."

---

## Tasks

**Phase 1 (fake):**
- [ ] Hard-code EditPlan: clips in order, full usable_range, default music
- [ ] Validate hard-coded plan passes schema checks

**Phase 8 (real AI):**
- [ ] Design DIRECT reconciliation prompt → EditPlan JSON
- [ ] Design EDIT discovery prompt → EditPlan JSON
- [ ] Implement EditPlan schema validation
- [ ] Test DIRECT path: original plan vs. what was actually captured (including failed shots)
- [ ] Test EDIT path: random unplanned clips → achievable story
- [ ] Verify output duration accuracy (within ±20% of target)
- [ ] Handle edge case: < 2 usable clips (return error, not crash)
- [ ] Test Story Reconciliation: verify it surfaces stronger narratives when available
