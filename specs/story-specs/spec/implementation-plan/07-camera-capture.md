# 07 — Camera Capture

## Overview

Real-time capture UI driven by `StoryPlan`. Presents one guidance instruction at a time, records each shot, and associates each clip with its shot in the project.

---

## Requirements

- Show ONE instruction at a time from `shot.guidance_instructions[]` — never the full plan
- Instructions progress automatically; countdown ("3… 2… 1… go.") is the cue to start recording
- Every captured clip tagged with `shot_id` and `story_project_id` immediately on capture
- No filmmaking terminology — "Walk toward the signs" not "Track the subject"
- Retake replaces the previous clip for that shot
- Skip shot marks it `status: failed`; Edit Planner handles gracefully
- Show target duration indicator — visual only, not a hard enforced limit
- No exposure, focus, zoom, or format controls in MVP — default camera settings throughout
- Zero AI calls during capture — all guidance is pre-computed

---

## Design

**Capture flow per shot:**
```
Show: shot purpose (plain language)
  ↓
Instruction 1: "Walk toward the signs."
  ↓
Instruction 2: "Ready?"
  ↓
Countdown: "3… 2… 1… go."
  ↓
Auto-start recording
  ↓
Duration bar fills
  ↓
Auto-stop (or user taps stop)
  ↓
"Got it." → validation
```

**UI layout:** Full-screen viewfinder. Bottom overlay: current instruction (large), shot progress ("Shot 1 of 2"), duration bar. No controls visible during active instruction sequence.

**Recording:** `AVCaptureMovieFileOutput` to temp file. On completion, copy to project asset directory and create `Asset` object with `shot_id`.

**Post-capture actions:**
- Primary: "Got it" (proceed to validation)
- Secondary: "Try again" (retake, replaces previous clip)
- Tertiary: "Skip this shot" (mark failed, continue)

---

## Tasks

**Phase 1 (walking skeleton):**
- [ ] Build full-screen camera viewfinder (AVFoundation)
- [ ] Implement instruction overlay (text + shot progress)
- [ ] Implement countdown animation
- [ ] Auto-start recording on "go", auto-stop at target duration
- [ ] Associate captured clip with `shot_id`, write `Asset` object
- [ ] Implement "Got it / Try again / Skip" actions
- [ ] Test on physical device: complete 2-shot DIRECT flow

**Phase 5 (connect to real StoryPlan):**
- [ ] Replace hard-coded instructions with `shot.guidance_instructions[]`
- [ ] Handle variable instruction count per shot
- [ ] Handle skipped shots in StoryState
