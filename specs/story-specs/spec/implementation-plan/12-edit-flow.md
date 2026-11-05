# 12 — EDIT Flow

## Overview

End-to-end user journey for "I already have footage, make something." No camera, no capture guidance. Pure understanding → edit. **Build this first** — no hardware dependency, faster iteration cycle, validates the full AI → media pipeline before adding capture complexity.

---

## Requirements

- User selects 2–10 existing clips from camera roll — no scene scan, no capture guidance required
- Intent (template + text + reference) can be provided before or after clip selection
- Story analyzes actual clips and discovers the strongest achievable narrative — does not force clips into a generic template
- Handles random/imperfect footage: shaky clips, mixed orientations, clips from different days — all valid input
- If < 2 usable clips after asset understanding: tell the user clearly, do not produce broken output
- Result screen: same as DIRECT (full-screen video player, save/share/start over)

---

## Design

**Full screen sequence:**
```
Home
  ↓
"I already have footage"
  ↓
Clip picker
  Photo library, multi-select, 2–10 clips, thumbnail grid
  ↓
Intent screen
  Template + optional text + optional reference
  ↓
"Analyzing your footage…"
  Per-clip progress indicators; process in parallel
  ↓
"I found a Story."
  (or: "I don't have enough to work with.")
  ↓
Story idea card
  Title · description · estimated duration
  [Make this Story]   Try a different direction
  ↓
"Creating your Story…"
  ↓
Result Screen
  Video plays on loop
  [Save]  [Share]  [Start over]
```

**Story idea card:**
```
┌─────────────────────────────┐
│  Golden Hour Walk           │
│  A cinematic story moving   │
│  through the city at dusk   │
│                             │
│  ~10 seconds                │
│                             │
│  [Make this Story]          │
│  Try a different direction  │
└─────────────────────────────┘
```

**"Try a different direction":** Edit Planner called again with a variation hint. Returns an alternative `EditPlan` built from the same assets.

**Insufficient footage:**
```
"I couldn't find enough to work with."
"Your clips might work better if you add a few more."

[Add more clips]  [Cancel]
```

---

## Tasks

**Phase 1 (full fake end-to-end):**
- [ ] Build clip picker (photo library, multi-select, 2–10 clips, thumbnail grid)
- [ ] Wire: Intent → clip picker → fake asset understanding → fake story card → fake processing → result screen
- [ ] Run complete EDIT flow with real clips from camera roll
- [ ] Produce actual output video (even if trivially assembled)

**Integration (Phases 6–9):**
- [ ] Replace fake asset understanding with real pipeline (spec 06)
- [ ] Replace fake story card with real Edit Planner output (spec 09)
- [ ] Replace fake processing with real media engine (spec 10)

**Testing:**
- [ ] Old travel clips
- [ ] Random city clips
- [ ] Mixed orientations (landscape + portrait)
- [ ] Poor quality footage (shaky, bad lighting)
- [ ] Minimum input: exactly 2 clips
- [ ] Maximum input: 10 clips from different days/locations
- [ ] Insufficient footage path (< 2 usable after understanding)

**User testing:**
- [ ] Give users their own random footage and Story
- [ ] Compare output and time vs. their normal workflow
- [ ] Measure: perceived originality, time saved, intent match, willingness to use again
