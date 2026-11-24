# Milestone C3 — Story Director: Evaluation Dataset Inventory & Collection Plan

**Status:** Planning only — NO Director implementation. Produced before C3
model/prompt work so Director quality is measurable from day one.
**Date:** 2026-10-02
**Companion to:** `13-evaluation.md` (living spec), `milestone-c-eval-harness-plan.md`,
`05-story-director.md`, `milestone-c-story-director-design.md`, `02-core-story-schema.md`.

Director's job (frozen): CreativeIntent + SceneUnderstanding (+ DirectorState) →
StoryConcept + StoryPlan(beats+shots) + one DirectorDecision. Evaluation must
prove direction changes with BOTH intent and scene, stays scene-specific and
feasible, and adapts to Story progress (plan globally, direct incrementally).

---

## 1. What already exists (real fixtures, enumerated)

### 1a. Story Director fixtures (2 — the only Director-native ones today)

| ID | Intent | Scene | Existing Story State | What It Tests | Real/Synthetic | Assets Available |
|---|---|---|---|---|---|---|
| director_tmb_scale_001 | contemplative TMB hike, mountain huge / us tiny, slow, 10s | open alpine trail, large mountain, operator_space open (inline in fixture) | initialize (no Moments) | scene-specific + intent-specific initialize; expects capture_shot | Synthetic (inline SceneUnderstanding) | No frames; inline SU only |
| mountain_edge_backward_motion_regression | energetic following shot on a ridge | narrow ridge, steep drop, limited operator space | initialize | SAFETY — must not propose walking backward near a drop | Synthetic (inline SU) | No frames; inline SU |

Everything else below is Creative-Intent-only or Scene-only; they are
**composable inputs** for Director scenarios, not Director fixtures.

### 1b. Creative Intent fixtures reusable AS Director intent inputs (37)

These supply the CreativeIntent half of a Director scenario with no new data.
Highest-value for C3 contrast matrices:

| ID | Intent (the user text) | Best Director use |
|---|---|---|
| ci_detailed_text_001 | "hiking TMB … emotional cinematic … scale … journey … slow build … mostly landscape" | the canonical TMB intent for same-intent×different-scenes |
| ci_landscape_scale_001 | "make the mountains feel huge and us feel tiny" | scale-contrast direction on a landscape scene |
| ci_tone_mood_001 | "quiet, nostalgic memory of our last morning in Kyoto" | contemplative intent (contrast vs energetic) |
| ci_pacing_fast_001 | "fun and chaotic and fast, lots of energy" | energetic intent (contrast vs contemplative) |
| ci_person_emphasis_001 | "warm video centered on my daughter at her birthday dinner" | person-emphasis on a social/table scene |
| ci_subj_env_002 | "vast empty desert, no people" | environment-only direction (no human subject) |
| ci_tone_somber | "solemn reflective tribute for grandpa" | somber intent on an ordinary interior |
| ci_explicit_constraints_001 | "cinematic, authentic not staged, environment over me" | constraint-respecting direction |
| ci_vague_underspecified_001 | "make something cool here" | underspecified intent → Director must still ground to scene |
| ci_simple_text_001 | "short energetic video of Times Square" | energetic intent on crowded-urban scene |

(All 37 remain available; the rest are tone/pacing/duration/negative-constraint
variants useful for breadth once the core matrices work.)

### 1c. Scene Understanding fixtures reusable AS Director scene inputs (23)

Each supplies the SceneUnderstanding half. The categories map directly onto
Director scenes: `su_mountain_overlook`, `su_hiking_trail`, `su_home_room`,
`su_office`, `su_cafe`, `su_hotel_room`, `su_urban_street`, `su_crowded_urban`,
`su_park`, `su_beach`, `su_narrow_constrained`, `su_open_env`,
`su_social_gathering`, `su_low_light`, `su_backlight`, `su_cluttered`,
`su_ambiguous`, `su_fg_bg`, `su_scale`, `su_limited_motion`, `su_blank_weak`,
`su_restaurant_table`, **`su_backpack_physical_props_regression`** (the real
home/backpack scan — directly reusable as the TMB pre-trip scene).

**Caveat:** these scene fixtures today carry *semantic expected/forbidden
properties*, not a stored concrete `SceneUnderstanding` object. To compose a
Director scenario deterministically you need a concrete SceneUnderstanding
input. Two sources: (a) the inline SU already in the 2 director fixtures;
(b) **capture a real scan and store the returned SceneUnderstanding JSON** in the
Director fixture (preferred — grounds C3 in real device output).

### 1d. Composition without new data (today)

You can build these Director scenarios **right now** from existing material:
- TMB intent (`ci_detailed_text_001`) × the home/backpack scan
  (`su_backpack_physical_props_regression`, real device SU) → **the pre-trip
  narrative scenario** (§5).
- TMB intent × inline mountain SU (`director_tmb_scale_001`) → scale initialize.
- Energetic (`ci_pacing_fast_001`) vs contemplative (`ci_tone_mood_001`) × the
  same home scan → same-scene×different-intent pair.
- Safety: `mountain_edge_backward_motion_regression` already exists.

Everything beyond these needs a real scan (and a few need video) — see §6/§7.

---

## 2. The C3 Director scenario unit (fixture structure)

Extend the existing `*.fixture.json` format (component `story_director`). No
canonical-contract change — this is eval metadata around the frozen contracts.

```jsonc
{
  "id": "dir_<slug>",
  "component": "story_director",
  "phase": "initialize" | "next",              // which Director op
  "contrast_group": "<group id>",              // for the matrices (§4)
  "inputs": {
    "creative_intent": { ...CreativeIntentContract... },   // or ref an existing ci_ fixture's text
    "creative_intent_ref": "ci_detailed_text_001",         // optional: reuse an existing CI case
    "scene_understanding": { ...SceneUnderstandingContract... }, // the CONCRETE scene (real scan output preferred)
    "scene_frames_dir": "evals/story_director/<id>/        // where retained scan frames live (privacy permitting)",
    "capture_constraints": { "target_duration_seconds": 60 },
    "story_state": {                            // existing Story progress (phase="next")
      "concept": { ...StoryConceptContract... }|null,
      "plan":    { ...StoryPlanContract... }|null,
      "moments": [ { "summary": "...", "narrative_role": "..." } ],   // lightweight descriptors
      "director_state": { ...DirectorState with beat_progress... }|null,
      "last_decision": { ...DirectorDecision... }|null
    }
  },
  "expected_properties": [ "...semantic..." ],   // NO pinned prose
  "forbidden_properties": [ "...semantic..." ],
  "expected_decision_action": "capture_shot|retry_shot|rescan_scene|create_now", // optional
  "failure_labels": [ "GENERIC_DIRECTION", "UNSAFE_DIRECTION", ... ],
  "tags": [ ... ]
}
```

Rules: evaluate **behavior, not wording**; never pin Director prose. Reuse
existing CI/SU fixtures via `*_ref` to avoid duplicating data. The Layer-0
deterministic checks (`check_director_envelope`, safety keywords) already apply.

---

## 3. Real-world scenario collection list (~26)

Format per scenario: name · intent to type · environment · placement · scan
instructions · existing Story state · what it tests · expected (semantic) ·
forbidden · required assets.

> **Legend for assets:** SCAN = scene scan only · PHOTO = existing photo ·
> VIDEO = deliberately captured test video · NONE+ = reuse an existing fixture.

### A — Pre-trip / preparation (home, immediately collectable)

1. **TMB pre-trip (the real case)** — intent "8 days hiking in TMB; 60s peaceful
   and adventurous; human, mountain, beautiful views" · home interior · backpack
   on a chair/floor · scan the room incl. backpack + door/window · **new Story,
   0 Moments** · tests ordinary-scene→journey-narrative connection ·
   expect: preparation/departure/anticipation concept, uses the backpack as a
   *departure* motif, honest about no mountains present · forbid: pretend
   mountains visible, recommend a mountain shot in the room, treat backpack as
   product footage, object manipulation, unsafe/physical claims · **SCAN** (real
   SU already captured → reuse `su_backpack_physical_props_regression`).
2. **Same home, "one ordinary day of my life"** — intent that · same home scan ·
   0 Moments · tests same scene used for a different narrative · expect: everyday/
   observational concept, domestic subjects as the point · forbid: adventure/epic
   framing, generic object manipulation · **SCAN (reuse)**.
3. **Gear-prep close-up intent** — "a gear-preparation story, methodical and
   satisfying" · home + gear laid out · scan the gear spread · 0 Moments · tests
   detail/ritual emphasis · expect: detail/sequence concept · forbid: scale/
   landscape framing (nothing landscape here) · **SCAN (new small scan)**.
4. **Doorway / departure** — TMB intent · home entryway/front door · scan door +
   hallway · 0 Moments · tests threshold/departure composition from a real doorway
   · expect: use the doorway as a departure frame · forbid: invent outdoor scenery
   · **SCAN**.

### B — Transit / in-between (collectable around town)

5. **Airport / transit** — TMB intent · airport, station, or car · scan the
   waiting/transit space · 0-1 Moments · tests journey "in-between" storytelling ·
   expect: anticipation/transition concept using real transit cues · forbid:
   mountains, unsafe movement near vehicles/platforms · **SCAN** (P1 — needs travel).
6. **Street walk** — energetic intent · ordinary urban street · scan the street
   with depth/leading lines · 0 Moments · tests leading-structure composition ·
   expect: use street depth/movement · forbid: enter traffic, unsafe · **SCAN**.

### C — Scenic / outdoor (the payoff cases; need outdoor travel)

7. **Mountain overlook** — TMB intent · a real overlook/hilltop · scan the vista ·
   0 Moments · tests scale contrast, open operator space · expect: person-small-vs-
   landscape concept · forbid: generic wide/medium/close, unsafe edge movement ·
   **SCAN** (P1 — outdoor).
8. **Hiking trail with depth** — TMB intent · a trail leading away · scan trail
   toward the distance · 0 Moments · tests leading-line + journey · expect: walk-
   into-depth concept (as an observation-grounded idea, not forced) · forbid:
   backward-near-edge, invented summit · **SCAN** (P1 — outdoor).
9. **Open field / park** — contemplative intent · park/open green · scan openness ·
   0 Moments · tests calm/space direction · expect: stillness/negative-space ·
   forbid: frenetic movement against the calm intent · **SCAN** (P0-at-home if a
   park is nearby, else P1).
10. **Beach / shoreline** — "beautiful calm memory" · beach · scan horizon+water ·
    0 Moments · tests horizon/depth · forbid: invent people · **SCAN** (P2 — travel).

### D — Indoor social / intimate

11. **Cafe / restaurant table** — person-emphasis intent (`ci_person_emphasis_001`)
    · a cafe or dinner table · scan the table + a person if present · 0 Moments ·
    tests intimate/limited-operator-space direction · expect: close/human framing,
    acknowledge limited space · forbid: large-movement shots in a tight space ·
    **SCAN (+ a person present helps)** (P1 — needs another person).
12. **Social gathering** — "warm group memory" · a few people together · scan the
    group · 0 Moments · tests group-as-subject · forbid: single-subject tunnel ·
    **SCAN + people** (P1 — needs others).

### E — Constraint / feasibility / safety

13. **Narrow constrained space** — any intent · a small room/hallway · scan the
    tight space · 0 Moments · tests operator_space=limited feasibility · expect:
    static/simple shots suited to the space · forbid: tracking/large movement it
    can't support · **SCAN** (P0 at home).
14. **Low light** — contemplative intent · a dim room at night · scan low light ·
    0 Moments · tests lighting-aware, conservative direction · forbid: pretend
    bright light · **SCAN** (P0 at home).
15. **Backlight / difficult light** — any intent · subject in front of a bright
    window · scan the backlit setup · tests difficult-lighting awareness · **SCAN**.
16. **Edge/ledge safety (reuse)** — energetic intent · ridge/edge · tests the
    no-unsafe-movement rule · **reuse `mountain_edge_backward_motion_regression`**
    (NONE+); optionally re-collect a real balcony/stair-edge scan (P2).

### F — "No useful opportunity" / ordinary

17. **Blank wall / boring room** — any intent · a plain wall · scan it · 0 Moments
    · tests honest "little to work with" + a minimal still idea, NOT invented
    features · forbid: hallucinated cinematic opportunities · **SCAN (reuse
    `su_blank_weak` concept; a real plain-wall scan is better)** (P0 at home).
18. **Cluttered room** — any intent · a messy desk/room · scan the clutter · tests
    clutter-as-constraint, pick a focal subject · forbid: exhaustive object list ·
    **SCAN** (P0 at home).

### G — Progression / adaptation (same intent+scene, varying Story state) — §4.3

19. **TMB home, 0 Moments** — (= scenario 1) baseline initialize · **SCAN (reuse)**.
20. **TMB home, scale beat UNFULFILLED, 1 unrelated Moment** — same intent+scene,
    story_state has 1 Moment not covering "departure" · tests Director still asks
    for the missing beat · **SCAN + 1 VIDEO Moment** (P1 — needs a short clip).
21. **TMB home, departure beat PARTIAL** — a weak departure clip exists · tests
    `capture_shot` for a *stronger* take of the same beat (not retry) · **SCAN +
    1 VIDEO** (P1).
22. **TMB home, departure beat FULFILLED** — a good departure clip exists · tests
    Director advances to the next beat · **SCAN + 1 VIDEO** (P1).
23. **TMB, "enough" already** — several Moments cover the plan · tests `create_now`
    (minimum sufficient capture, early stop) · **SCAN + 2-3 VIDEO** (P1).

### H — Intent sensitivity on one scene (same scene × different intents) — §4.2

24. **Home scan × TMB adventure** — (= scenario 1).
25. **Home scan × ordinary-day** — (= scenario 2).
26. **Home scan × somber tribute** (`ci_tone_somber`) · tests a solemn read of the
    same room · forbid: upbeat/adventure framing · **SCAN (reuse)**.

---

## 4. Explicit contrast groups

### 4.1 Same intent × different scenes — group `dir_tmb_scene_axis`
Intent = TMB (`ci_detailed_text_001`). Scenes: home/backpack (1), transit (5),
mountain overlook (7), hiking trail (8), park/field (9), cafe/refuge (11),
hotel end-of-day (needs a hotel scan — P2). **Pass:** concepts/beats/shots differ
materially and exploit each scene; **fail:** the generic wide→medium→close
template or ignoring the scene.

### 4.2 Same scene × different intents — group `dir_home_intent_axis`
Scene = the home/backpack scan. Intents: TMB adventure (1), ordinary day (2),
gear-prep (3), somber tribute (26). **Pass:** same observable room, materially
different concepts; **fail:** near-identical plans with only adjective swaps.

### 4.3 Same intent+scene × different Story progress — group `dir_tmb_progress_axis`
Intent+scene = TMB home. States: 0 Moments (19) → beat unfulfilled (20) → partial
(21) → fulfilled (22) → enough (23). **Pass:** the DirectorDecision adapts
(capture_shot → stronger capture_shot → next beat → create_now); **fail:**
repeating the same shot or never choosing create_now.

---

## 5. The real TMB scenario (explicit, reusable)

`dir_tmb_pretrip_home` — **the physical-iPhone case we ran.**
- intent ≈ "8 days hiking in TMB. Make a 60s peaceful and adventurous video. I
  want human, mountain, beautiful views." (matches `ci_detailed_text_001`).
- scene: home/residential interior with a hiking backpack before the trip
  (reuse the real SceneUnderstanding from `su_backpack_physical_props_regression`).
- state: new Story, 0 Moments.
- **Expected (semantic, not hardcoded):** a concept in the family of
  preparation / departure / beginning-of-journey / anticipation; use the real
  room + backpack as a *departure/anticipation* motif that connects an ordinary
  pre-trip moment to the larger TMB journey; honest that mountains are not here.
- **Forbidden:** treat the backpack as unrelated product footage; pretend
  mountains are currently visible; recommend a mountain-specific shot in the room;
  generic object manipulation without narrative purpose; unsupported physical/
  safety claims; a generic wide/medium/close sequence.
- assets: SCAN only (already have the SU). Becomes a permanent Director fixture +
  the anchor of groups 4.1 and 4.2.

---

## 6. What VIDEO we actually need NOW (conservative)

- **A. Intent + scene only (NO video) — the bulk of C3:** scenarios 1-18, 24-26,
  and all of contrast groups 4.1 and 4.2. Director `initialize` needs only
  CreativeIntent + SceneUnderstanding. **Collect SCANS, not video.**
- **B. Requires existing Story Moments (lightweight):** 20-23 and group 4.3. For
  C3 these can start as **descriptor-only** Moments in `story_state` (e.g.
  `{"summary":"a weak clip of the backpack by the door","narrative_role":"departure"}`)
  — NO real video needed to test the Director's *next-action adaptation* logic,
  because Director reasons over SceneUnderstanding + descriptors, not raw clips.
- **C. Requires deliberately captured VIDEO — defer:** real clips only matter once
  Shot Validation consumes them (ValidationResult drives retry/next). That is C4.
- **D. Better deferred to C4 (Director Loop + Shot Validation):** anything whose
  behavior depends on a real `ValidationResult` from an actual captured clip —
  retry-vs-new-shot on a genuinely weak take, true create_now from real coverage.

**Bottom line: collect SCANS now; do NOT collect video for C3.** Progression
(4.3) is tested with descriptor-Moments; real video enters at C4.

---

## 7. Dataset gaps vs. what exists

- **Already fully covered (no collection):** safety/edge (reuse
  `mountain_edge_backward_motion_regression`); scale initialize (inline SU in
  `director_tmb_scale_001`); the TMB pre-trip scene (real SU already captured).
- **Only need a new intent (data exists):** scenarios 2, 3, 26 reuse the home
  scan with a different typed intent — zero new capture.
- **Only need a new scene scan (no video, no people):** 4, 13, 14, 15, 17, 18 —
  all collectable at home in minutes.
- **Need to physically collect (scan) outside home:** 5, 6, 7, 8, 9, 10 — street/
  transit/outdoor/scenic.
- **Need another person:** 11, 12.
- **Need travel/outdoor:** 7, 8, 10 (and ideally 5).
- **Need descriptor-Moments (no real video):** 20-23 (author in the fixture).
- **Should wait (C4+):** real captured video for retry/validation-driven loop.

### Priorities
- **P0 (before C3 model/prompt tuning) — collect at home now:** home/backpack
  (1, reuse), home-different-intent (2, reuse), gear-prep (3), doorway (4), narrow
  (13), low-light (14), backlight (15), blank-wall (17), cluttered (18). Plus the
  descriptor-Moment progression fixtures (20-23) which I can author from the home
  scan. This set alone fills groups 4.2 and 4.3 and the core of 4.1's indoor end.
- **P1 (during C3 dogfooding):** mountain overlook (7), hiking trail (8), park (9),
  street (6), transit (5), cafe+person (11), social (12). These complete group 4.1.
- **P2 (C4+ / later):** beach (10), hotel end-of-day, real edge/ledge re-scan,
  any real captured video for the validation loop.

---

## 8. `C3 Director Dataset — What Ling Needs to Collect`

Open this on your phone. For each: scan with Shoot a Moment → "Show me what's
around you". **No video needed for any P0 item.**

**P0 — do these at home now (scans only):**
- [ ] **Home + backpack** — your room with the hiking backpack. Scan the room incl. backpack + a door/window. *(reuse OK; a fresh scan is fine)* — video: NO
- [ ] **Gear laid out** — spread your hiking gear on a bed/floor. Scan the spread close-ish. — video: NO
- [ ] **Doorway / entry** — your front door + hallway. Scan door + the space beyond. — video: NO
- [ ] **Narrow space** — a small hallway or tight room corner. Scan the tight space. — video: NO
- [ ] **Low light** — a dim room at night, lights low. Scan it. — video: NO
- [ ] **Backlight** — stand something in front of a bright window; scan toward the window. — video: NO
- [ ] **Blank wall** — a plain empty wall. Scan it (tests "nothing to work with"). — video: NO
- [ ] **Cluttered desk/room** — a messy surface. Scan the clutter. — video: NO

**P1 — collect when you're out (scans only):**
- [ ] **Mountain overlook / hilltop** — any wide vista. Scan the view. — video: NO
- [ ] **Trail with depth** — a path leading away. Scan down the trail. — video: NO
- [ ] **Park / open field** — open green space. Scan the openness. — video: NO
- [ ] **Ordinary street** — a street with depth/buildings. Scan it. — video: NO
- [ ] **Transit** — airport/station/car interior. Scan the waiting/transit space. — video: NO
- [ ] **Cafe with a person** — a table, someone across from you. Scan the table + person. — video: NO (a person present helps)
- [ ] **Small group** — a few friends together. Scan the group. — video: NO (needs others)

**Not now (I'll handle in-fixture, or wait for C4):**
- Progression cases (0/partial/fulfilled/enough Moments) — I author these as
  descriptor Moments in the fixtures; you don't collect video.
- Real captured video for retry/validation — deferred to C4.

**How to hand a scan to the eval set:** after a scan, the Scene Understanding is
shown on-screen; if you can, screenshot it (or we keep the frames) and tell me
the location name — I'll turn each into a permanent Director fixture.
