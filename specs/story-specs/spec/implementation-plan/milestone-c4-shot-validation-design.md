# Milestone C4 — Shot Validation: Design Reconciliation (DESIGN ONLY)

> # ⛔ REJECTED FOR INLINE MVP IMPLEMENTATION (2026-10-05, approved)
> **This full inline semantic Shot Validation design is NOT the active MVP plan.** The
> GO/NO-GO audit (`milestone-c4-go-no-go-audit.md`) — on evidence from the C4A model
> evaluation (`milestone-c4a-shot-validation-eval-report.md`) and the C4A.2 Capture
> Evidence experiment (`milestone-c4a2-capture-evidence-report.md`) — concluded **B:
> BUILD C4-LITE**. Inline semantic validation does not earn its ~4–5s blocking latency,
> recurring per-capture inference cost, network dependency, implementation complexity, or
> its trust-breaking false-GOT-IT failure mode on the ≤10s DIRECT-like band.
>
> **The active MVP is `milestone-c4-lite-capture-integrity-design.md`** (local-only
> integrity checks; no AI/AWS/Bedrock/network). **This document is PRESERVED in full as
> rationale and research** — the corpus, harness, prompt, four-axis judgment model, model
> comparison, derivation logic, Moment lifecycle, and CaptureEvidence experiment are all
> valuable inputs for the **future asynchronous Asset Understanding**, where the semantic
> responsibilities (execution_match, shot_purpose, story_utility, Shot/Beat contribution,
> useful-elsewhere reasoning) now live. The old C4B/C/D build sequence below is **not**
> being executed. Do not erase this; do not implement it inline.
>
> ---

> **Status: DESIGN / RECONCILIATION — DECISIONS APPROVED (2026-10-04). Not implemented.**
> No production contract is modified by this document. No raw corpus file is moved, renamed,
> or transcoded. The contract-affecting choices approved by the user are now **authoritative**
> here (see §16 Decision register and §20); three items remain explicitly open (§16).
>
> Scope rule honored: C1/C2/C3, Opus, prompts, ModelGateway, frozen contracts,
> AWS — all untouched. This is the analysis requested before C4 implementation.

Authoritative inputs read for this reconciliation:
- Frozen product spec `08-shot-validation.md` (binary PASS/RETRY, PASS-biased, <3 s,
  gross-failures-only, 3-frame sampler).
- Frozen Director design `05-story-director.md` (Concept→Beats→Shots, decision loop
  §19, "Validation needs to know what matters" §627/§653, the SCALE example §182-208).
- Canonical contracts: `contracts/schemas/ai_contracts.py` (`ValidationResultContract`,
  `ShotContract`, `StoryBeat`, `BeatProgress`, `DirectorState`, `DirectorDecision`),
  and the generated `validation-result.schema.json` / `director-*.schema.json`.
- Current server loop: `apps/api/app/main.py` (`/v1/director/initialize`, `/v1/director/next`)
  and `packages/story_director/__init__.py` (`RealStoryDirectorEngine`).
- The ACTUAL corpus inventoried under `evals/assets/videos/` (10 categories, 66 clips).

---

## 0. The single most important finding

**The validation→Director loop is not wired today, and the frozen written design and
the frozen contract disagree about what validation produces.**

1. `05-story-director.md` repeatedly describes a loop where **ValidationResult +
   current beat** drive the next decision (§340 "validate", §374-376 "captured Moments /
   validation results / current beat", §979-1010 decision flow). The SCALE example
   (§189-208) explicitly shows a clip that is **`usable` but only *partially fulfills*
   the beat** — i.e. two separate axes.
2. The frozen `ValidationResultContract` is **shot-level usability only**: `usable`,
   `recommendation ∈ {accept, retake}`, `issues[]` (gross failures), `confidence?`.
   It deliberately carries **no** purpose-fulfillment and **no** beat signal
   ("Beat fulfillment is DIRECTOR state, NOT ValidationResult", 05 header §23).
3. **But the running `/v1/director/next` never receives a `ValidationResult` at all.**
   Its request body is `{"prior": {...}}` → `engine.next(prior)`, and the model is
   simply asked to "update director_state and return exactly ONE next decision". Beat
   progress is **model-asserted**, not **derived from validation**. There is no
   `/v1/shot-validation` endpoint and no validation engine.

So C4 is not "add a model behind an existing contract." C4 **decides** (approved, §20) that
the purpose/beat judgment lives in a **new internal `ShotValidationJudgment`** feeding the
Director loop, while `ValidationResult` keeps its simple external role, and the loop is
closed by passing that judgment into `/v1/director/next` so `beat_progress` becomes derived,
not model-asserted (§3, §4, §5).

---

## 1. Corpus → current-contract mapping (Deliverable 1)

Every clip, run through today's frozen `ValidationResultContract` (`usable`,
`recommendation`, `issues[]∈{too_short, severe_shake, subject_missing,
severe_underexposure, severe_overexposure, instruction_not_followed}`, `confidence?`).

Measured corpus facts used below: durations **0.47 s–154 s**; portrait 1080×1920 +
landscape 1920×1080 + two 1280×720; **H.264 (avc1)** majority, **HEVC (hvc1)** for S01/
S02/T01 and two A01; all ~30 fps; file sizes ~0.4 MB–214 MB; `_2` retakes real; S05/S06
prefix collisions real; S06/S08 re-themed per actual filenames; `IMG_8712.MOV`
unclassified (excluded from semantic fixtures).

Legend for the "today maps to" column: `usable` / `recommendation` / dominant `issue`.

### S01 backpack static (static-subject usability baseline)
| Clip | Intended meaning (filename) | Today's contract says | Information LOST |
|---|---|---|---|
| S01_A_exact_good | exact, good | usable / accept | — (clean fit) |
| S01_B_too_short (0.47 s) | duration failure | ¬usable / retake / `too_short` | — (gross failure fits) |
| S01_C_shaky | technical shake | ¬usable / retake / `severe_shake` | severity vs "minor, Edit-Planner can handle" is binary-only |
| S01_D_poor_framing | framing weak | **ambiguous** → PASS-biased usable | "poor framing" has **no issue code**; collapses to accept |
| S01_E_wrong_subject | wrong subject present | ¬usable / retake / `subject_missing`? | "wrong" ≠ "missing"; no code for *present-but-wrong* |
| S01_F_alternative_good | different but good | usable / accept | that it was an **alternative** execution is invisible |

### S02 departure (TEMPORAL direction + contradiction)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S02_A_exact_good | walk toward camera, depart | usable / accept | — |
| S02_B_stand_still | action absent | usable? (subject present) OR `instruction_not_followed` | **purpose unfulfilled** not expressible except as a gross "instruction_not_followed" |
| S02_D_walk_away_through_door | literal differs, purpose (departure) succeeds | usable / accept | **alternative_success** collapses to plain accept — the win is invisible |
| S02_E_pickup_backpack_and_leave | different execution, strong narrative | usable / accept | same — alternative success unlabeled |
| S02_F_slightly_shaky_but_good | correct semantics, minor defect | usable / accept (PASS-bias) OR `severe_shake` | "minor, usable anyway" vs "severe" is a single bit |
| S02_G (→ shared source A05) | approaches, removes pack, sits — contradicts departure | usable (subject present!) | **semantic contradiction** is nearly invisible: everything looks fine frame-by-frame |

### S03 scenic reveal (TEMPORAL ordering: friend → landscape)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S03_A_exact_friend_to_landscape (+_2) | correct reveal order | usable / accept | — (but ordering not represented) |
| S03_B_landscape_only | missing the human half | usable (landscape present) | reveal **relationship** absent — looks fine as a static frame |
| S03_C_friend_only (+_2) | missing the landscape half | usable | same |
| S03_D_reverse_reveal (+_2) | landscape→friend (wrong direction) | usable | **direction reversed** — invisible to unordered frames |
| S03_E_bad_whip_pan | motion ruins it | ¬usable / `severe_shake`? | whip-pan is a *motion-quality*, not shake, failure |

### S04 human scale (spatial semantics)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S04_A_exact_small_person_landscape (+_2) | scale contrast achieved | usable / accept | **scale** is the purpose; unmeasured |
| S04_B_person_too_large | scale contrast fails | usable (person+landscape present) | the SCALE purpose fails while usability passes — exactly the 05 §189 case |
| S04_C_landscape_no_person | no subject for scale | usable (landscape) | purpose impossible, usability says fine |
| S04_D_small_person_moving | scale ok + motion | usable / accept | — |
| S04_E_two_people_small (720p MP4) | scale with 2 subjects | usable / accept | resolution/format variance only |

### S05 trail progression (TEMPORAL progression; prefix collision)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S05_A_follow_behind | progression, camera follows | usable / accept | progression over time unrepresented |
| S05_B_static_camera_walk_away | subject recedes | usable | "progression" vs "departure" ambiguity |
| S05_C_subject_static_camera_moves | camera dollies | usable | who-moved is a temporal fact |
| S05_D_follow_but_shaky | right idea, shaky | PASS-bias usable OR `severe_shake` | minor/severe binary again |
| S05_E_feet_walking_alternative (+_2) **and** S05_E_static_camera_two_people | **TWO different clips share `E_`** | each usable | the two are different cases → need **distinct fixture IDs** (not file renames) |

### S06 difficulty (RE-THEMED vs plan; two `G_`)
Actual clips: B_tired_face(+_2), C_hand_trekking_pole, D_heavy_footsteps, **E_cross_river**,
**F_eat_food_in_snow**, **G_storm_cold**, **G_storm_wind**. (No A_muddy_boots.)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S06_B_tired_face (+_2) | difficulty via exhaustion | usable | "shows difficulty" is a *purpose*, not a usability fact |
| S06_C_hand_trekking_pole | effort evidence | usable | same |
| S06_E_cross_river | difficulty via obstacle | usable | same |
| S06_G_storm_cold / S06_G_storm_wind | two takes, same prefix | usable | need distinct IDs; both are *purpose=difficulty* |

### S07 companionship (people semantics; unclassified file)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S07_A_natural_conversation (95 s) | companionship, authentic | usable | authenticity/relationship is a purpose |
| S07_C_one_person_only | companionship fails (one person) | usable (person present) | purpose fails, usability passes |
| S07_D_imperfect_but_natural | imperfect but real | usable | "imperfect but acceptable" has no representation |
| S07_E_wrong_people | wrong subjects | usable? | *present-but-wrong-subject* again |
| S07_F_two_people_sel-ph / S07_G_walking_together (720p MP4) | companionship variants | usable | — |
| **IMG_8712.MOV** | **UNCLASSIFIED** | n/a | excluded from semantic fixtures until a purpose is assigned |

### S08 end of day (RE-THEMED; long clips)
Actual: A_quiet_window, B_quiet_stove, C_sleepy_person, D_cooking_dinner (154 s!),
E_tired_face, F_nice_dinner_with_window_view. (Not the planned boots/sunset/phone set.)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| S08_D_cooking_dinner (154 s) | end-of-day mood | usable | **duration** blows every transport budget (see §7); mood=purpose |
| S08_E_tired_face | winding down | usable | purpose = emotional beat, not usability |

### T01 technical controls (same subject, variable quality)
This set is the **one place today's contract is almost sufficient** — it is pure gross-failure.
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| T01_A_clean_4s | clean baseline | usable / accept | — |
| T01_B_too_short_08s (0.47 s) | duration fail | ¬usable / `too_short` | — |
| T01_C_moderate_shake | moderate | **PASS-bias** usable | moderate-vs-severe is the whole point; binary can't grade |
| T01_D_severe_shake | severe | ¬usable / `severe_shake` | — |
| T01_E_underexposed | exposure low | ¬usable / `severe_underexposure` | "severe" threshold undefined |
| T01_F_overexposed | exposure high | ¬usable / `severe_overexposure` | same |
| T01_G_out_of_focus (NEW) | focus fail | **no issue code** → PASS-biased usable | **`out_of_focus` is missing from the enum** |
| T01_H_partial_occlusion | partial block | usable? (PASS-bias) | occlusion severity ungraded |
| T01_I_camera_points_away | subject never framed | ¬usable / `subject_missing` | — |

### A01 semantic adversarial (designed to fool shallow validation)
| Clip | Meaning | Today | LOST |
|---|---|---|---|
| A01_hiking_but_not_difficulty | hiking context, no difficulty | usable / accept | **the whole trap**: looks great, wrong purpose |
| A02_people_but_not_companionship | people present, no relationship | usable | purpose trap invisible |
| A03_backpack_but_arrival_not_departure | backpack, but arriving | usable | temporal-meaning trap |
| A04_person_mountain_but_no_scale | subjects present, no scale | usable | scale trap |
| A05_motion_but_wrong_motion (shared w/ S02_G) | motion exists, wrong motion | usable | temporal trap |
| A06_beautiful_but_wrong_beat (shared w/ A01) | beautiful, wrong beat | usable / accept | **the Story-material case**: technically great, wrong beat |

**A01 is the proof the current contract is insufficient:** every adversarial clip returns
`usable / accept` today, which is precisely the failure mode the set was built to expose.

---

## 2. Contract gap analysis (Deliverable 2)

Where `ValidationResultContract` loses information the corpus demands:

1. **Conflates five distinct axes into one bit (`usable`).** The corpus forces apart:
   - **(a) technical usability** — can the footage physically be used? (T01 set)
   - **(b) execution match** — did the user do the literal instruction? (S02_B stand-still)
   - **(c) shot-purpose fulfillment** — did it accomplish *why the shot was requested*?
     (S04_B person-too-large: usable, executed, purpose FAILED)
   - **(d) beat fulfillment** — does it move the current StoryBeat forward? (05 §189)
   - **(e) story utility** — is it good footage for *some* beat, even the wrong one? (A06)
2. **No vocabulary for alternative success.** S02_D/E, S01_F differ from the instruction
   yet fulfill the purpose. Today they are indistinguishable from a plain exact-match accept
   — so the system can't *learn* that creative deviation succeeded, and can't tell the
   Director "beat satisfied by a non-literal take."
3. **No vocabulary for semantic contradiction.** S02_G, A03, A05 are frame-by-frame fine
   but *mean the opposite*. `instruction_not_followed` is too blunt (it's also used for
   "stood still") and `usable=true` leaks them through.
4. **Missing gross-failure codes the corpus actually contains (APPROVED to add — §8/§16):**
   `out_of_focus` (T01_G), `wrong_subject` (present-but-wrong: S01_E, S07_E — distinct from
   `subject_missing`), and `unusable_motion` (S03_E whip-pan, distinct from `severe_shake`).
   No further taxonomy expansion.
5. **No severity gradation.** Spec 08 is deliberately binary & PASS-biased, which is right
   for the *user-facing* verdict — but the Director loop and the eval harness need
   *more* than a bit to make good next-shot decisions (05 §653 "Validation needs to know
   what matters"). The binary is a **presentation** concern; the Director feedback is a
   **loop** concern. Collapsing them loses the loop signal.
6. **No linkage of purpose/beat into the judgment INPUT.** The judgment can't be
   purpose-conditioned if the purpose/beat aren't given to the validator (they aren't,
   today — there's no validation call at all). This is why A01/A06 pass.

---

## 3. Validation semantics — APPROVED

> **DECIDED (user approval, this revision).** The 4-axis internal judgment below is the
> authoritative `ShotValidationJudgment` vocabulary. `ValidationResult` keeps its simple
> external/user-facing role (§20 strategy B+); the judgment is a **separate internal
> model-layer output** that drives the Director loop and the eval harness. Beat fulfillment
> remains **Director state** (`BeatProgress`), per 05 — validation *feeds* it, does not own it.

### 3.1 Internal judgment — `ShotValidationJudgment` (4 axes, APPROVED)
```
technical_usability : usable | minor_issues | unusable                 # axis (a)
execution_match     : matched | deviated | absent | contradicted       # axis (b)
shot_purpose        : fulfilled | partial | unfulfilled | alternative_fulfilled   # axis (c)
story_utility       : none | useful_elsewhere | strong_elsewhere       # axis (e)
```
These four are the **only** model-generated semantic axes. Everything downstream (clip
disposition, requested-shot status, user-facing state, Moment adoption, Director action)
is a **deterministic derivation** from these axes — not additional model fields.

### 3.2 Two distinct derived concepts — DO NOT CONFLATE (APPROVED correction)
"this clip should be kept" is **not** the same as "the requested Shot succeeded." They are
derived **separately** and deterministically from the axes:

**CLIP DISPOSITION ∈ { keep, discard }**
```
discard  ⇔  technical_usability == unusable
            OR (shot_purpose == unfulfilled AND story_utility == none)
keep     otherwise
```

**REQUESTED SHOT STATUS ∈ { fulfilled, partial, unfulfilled }**
```
fulfilled    ⇔  shot_purpose ∈ { fulfilled, alternative_fulfilled }   # (and technically usable/minor)
partial      ⇔  shot_purpose == partial
unfulfilled  ⇔  shot_purpose == unfulfilled  OR  execution_match == contradicted
                 OR technical_usability == unusable
```
Alternative fulfillment counts as **fulfilled** for the requested shot (purpose achieved by
a non-literal take); **contradiction** forces **unfulfilled** regardless of how clean the
footage looks (§5).

Worked examples (APPROVED):
| Axes | CLIP DISPOSITION | REQUESTED SHOT STATUS |
|---|---|---|
| usable + purpose `fulfilled` | **keep** | **fulfilled** |
| usable + `alternative_fulfilled` | **keep** | **fulfilled** |
| usable + purpose `partial` | **keep** | **partial** |
| usable + `unfulfilled` + `useful_elsewhere`/`strong_elsewhere` | **keep** | **unfulfilled** |
| `unusable` (technical) | **discard** | **unfulfilled** |
| usable + `unfulfilled` + utility `none` | **discard** | **unfulfilled** |

### 3.3 User-facing state — THREE states (APPROVED; replaces binary PASS/RETRY)
The old binary PASS/RETRY surface is insufficient for the corpus-derived "good footage,
wrong requested Shot" case. The user-facing surface is now three concise, non-technical
states, derived deterministically (no scores, no axes exposed):

```
GOT IT         ⇔  CLIP DISPOSITION == keep  AND  REQUESTED SHOT STATUS ∈ { fulfilled, partial }
KEEP + ONE MORE⇔  CLIP DISPOSITION == keep  AND  REQUESTED SHOT STATUS == unfulfilled
TRY AGAIN      ⇔  CLIP DISPOSITION == discard
```
- **GOT IT** — the captured Moment fulfills or sufficiently contributes to the requested Shot.
- **KEEP + ONE MORE** — useful Story material, retained, but the requested Shot/Beat isn't
  sufficiently fulfilled: *"We'll keep this, but let's get one more for what we're missing."*
- **TRY AGAIN** — technically unusable, or provides neither requested-purpose fulfillment
  nor useful Story value.

Retake stays optional (08): the user can proceed regardless of the state shown. This is a
corpus-driven product correction to the previously binary surface — see the 08 update.

**Obedience-checker principle, honored:** a clip that *deviated* from the instruction but
has `shot_purpose ∈ {fulfilled, alternative_fulfilled}` is **GOT IT** (S02_D/E, S01_F). A
`usable` clip with `shot_purpose == unfulfilled` is **not** a fulfilled beat even when it
looks clean (A01, S04_B) — it surfaces as **KEEP + ONE MORE** (if useful) or **TRY AGAIN**
(if not), and the Director, not the user, acts on the beat gap.

---

## 4. Moment / adoption lifecycle — APPROVED (Deliverable 4, 7, 8)

> **DECIDED (user approval).** Mapping internal judgment → clip disposition → Moment →
> requested-Beat effect. Keyed on the derived CLIP DISPOSITION / REQUESTED SHOT STATUS
> (§3.2), not on the raw bit.

| Case (axes) | Clip disposition | Becomes a Moment? | Requested Beat effect | User state |
|---|---|---|---|---|
| **Unusable take** (`technical=unusable`) | discard | **No** | stays `unfulfilled` | TRY AGAIN |
| **Fulfilled** (`purpose=fulfilled`) | keep | **Yes** | → `fulfilled` | GOT IT |
| **Alternative** (`purpose=alternative_fulfilled`) | keep | **Yes** | → `fulfilled` | GOT IT |
| **Partial** (`purpose=partial`) | keep | **Yes** | → `partial` | GOT IT |
| **Useful-elsewhere** (`unfulfilled` + `useful_elsewhere`/`strong_elsewhere`) | keep | **Yes** | **stays `unfulfilled`** | KEEP + ONE MORE |
| **Contradicted + useful** (`contradicted` + utility≠none) | keep | **Yes** | **stays `unfulfilled`** | KEEP + ONE MORE |
| **Contradicted, no utility** (`contradicted` + utility=none) | discard | **No** | stays `unfulfilled` | TRY AGAIN |
| **Failed, no utility** (`unfulfilled` + utility=none) | discard | **No** | stays `unfulfilled` | TRY AGAIN |

**The explicit Story-material resolution (approved):** technically good + does NOT fulfill
requested shot + useful elsewhere → **retain as a Moment, requested Beat stays unfulfilled,
Director asks for another shot.** Footage is never thrown away and the beat is never falsely
marked fulfilled. This is why `story_utility` is a first-class axis.

### 4.1 Promotion rule — transient CaptureAsset → persistent Moment (APPROVED, Deliverable 8)
- A capture is a **transient CaptureAsset** until validation returns.
- Promotion: a CaptureAsset becomes a **Moment** iff **CLIP DISPOSITION == keep** (§3.2),
  i.e. `technical_usability != unusable AND NOT (shot_purpose == unfulfilled AND
  story_utility == none)`.
- **Retries that produce `discard` are never promoted** → retries do not pollute Story
  Moments. Failed/non-Moment captures may remain **temporarily recoverable** through the
  CaptureSession / local-file lifecycle (`CaptureSession.capture_asset_ids` already lists
  them; local-first media keeps originals on device), but they are **not** Story Moments.
- A kept Moment records **which beat it supports** (`BeatProgress.supporting_asset_ids`)
  OR is marked **unassigned-but-useful** (`story_utility`) — distinct states.
- **Useful-elsewhere footage is NOT auto-assigned to another Beat by Shot Validation.**
  Validation stays shot-local (per 05); the **Director may claim it later**.

---

## 5. Director-loop integration (Deliverable 5, 10)

### 5.1 What the loop looks like today (verified in code)
`/v1/director/next` body = `{"prior": {...}}` → `engine.next(prior)` → model returns a full
`DirectorOutput{concept, plan, director_state, decision}`; the server **force-mints ids**
and runs integrity/safety guards; **`beat_progress` is whatever the model emitted**. There
is **no ValidationResult anywhere in the request** and **no validation endpoint**.

### 5.2 What C4 must add
1. A **validation step** after each capture (new engine + `POST /v1/shot-validation`),
   producing the §3 judgment.
2. The Director's `next` call must **receive** the validation judgment + which shot/beat it
   was for, so `beat_progress` becomes **derived from validation**, not model-asserted. This
   is the reconciliation 05 always intended (§979-1010) but the code never wired.
3. **Director actions use the EXISTING vocabulary — `skip_beat` is NOT added in C4 (APPROVED).**
   - `retry_shot` ⇐ `technical_usability == unusable` (execution/validation failed) — matches
     the pinned semantic ("recapture substantially the same shot because execution failed").
   - `capture_shot` ⇐ beat still `partial`/`unfulfilled` after a kept-but-not-fulfilling
     take (incl. the useful-elsewhere and contradicted-but-useful cases) — matches the pinned
     semantic ("a NEW shot, even for the same beat").
   - `create_now` / `rescan_scene` unchanged.
   - **Abandoning an unproductive beat** is modeled as `capture_shot` on the next beat while
     the prior stays `partial`/`unfulfilled` — no enum change. 05 §428/§457 prose mentions a
     `SkipBeat`, but per approval we do **not** add it now; if real dogfooding later proves
     the Director cannot gracefully abandon a beat with the existing actions, revisit the
     `DirectorActionType` enum then.

### 5.3 Minimal change vs the frozen Director design
No change to `StoryConcept/StoryPlan/StoryBeat/Shot` and **no `DirectorActionType` change**.
The loop change is **what goes INTO `next`** (add the validation judgment) and **how
`beat_progress` is computed** (derive from validation, don't trust the model). Both reconcile
with 05 without touching the planning contracts.

### 5.4 Semantic contradiction — APPROVED (distinct from alternative fulfillment)
Contradiction is **NOT** a simple pass. A `contradicted` execution means the **requested
Shot is UNFULFILLED**, regardless of how technically clean the footage is. Then disposition
decides the surface:

```
contradicted + useful Story footage (useful_elsewhere | strong_elsewhere)
    -> keep + REQUESTED SHOT STATUS = unfulfilled -> KEEP + ONE MORE
contradicted + no useful Story value (utility = none)
    -> discard + unfulfilled -> TRY AGAIN
```

**Alternative fulfillment is the opposite case and must not be confused with it:**
```
deviated + alternative_fulfilled
    -> keep + REQUESTED SHOT STATUS = fulfilled -> GOT IT
```
The difference is semantic, not technical: *deviated+alternative* achieved the shot's
**purpose** by other means (S02_D walk-away still communicates departure); *contradicted*
achieved the **opposite** meaning (S02_G approaches then sits — negates departure). Both can
be frame-by-frame clean; only the temporal/semantic judgment (§8) separates them, which is
exactly why the validator must receive ordered evidence and the shot purpose.

---

## 6. Validator input / minimum context (Deliverable 6, 9)

Minimum sufficient validator context (05 §627/§653 — "Validation needs to know what
matters"):

```
REQUIRED:
  - captured media (frames or clip — see §7 transport)
  - Shot.purpose          (internal semantic reason — axis c keys on this)
  - Shot.instruction      (user-facing direction — axis b keys on this)
  - Shot.subject_action, camera_motion, target_duration_seconds  (execution refs)
  - the Beat.purpose the shot serves      (axis d context; from StoryPlan.beats[beat_id])
OPTIONAL / STORY CONTEXT:
  - StoryConcept.summary (the thesis)     — helps judge story_utility (axis e)
  - current BeatProgress / other beats    — lets validator suggest useful_elsewhere target
EXPLICITLY NOT NEEDED:
  - full Story history, other Moments' media, provider/model metadata
```

Deterministic pre-checks (duration, motion energy) need **no** model and run first (spec 08
pipeline). The model call is purpose-conditioned on `purpose + instruction + beat.purpose`.
This is what makes A01/A06 catchable: the validator is *told the purpose* and asked
"did this accomplish THAT," not "is this a nice video."

---

## 7. Measured video transport recommendation (Deliverable 7, 11, 12)

Measured corpus reality (not the plan): **0.47 s–154 s**, portrait **1080×1920** +
landscape **1920×1080** + two **1280×720**, **H.264 + HEVC**, ~0.4 MB–**214 MB** per file,
~30 fps. Spec 08 says **3 frame samples (start, middle, end)** and <3 s latency.

Transport options evaluated against the corpus:

| Option | Fits <3 s? | Handles temporal (§13)? | HEVC/portrait/landscape? | Cost/complexity |
|---|---|---|---|---|
| **3 sampled frames** (08 default) | ✅ fast, tiny | ❌ **fails S02/S03/S05 direction** (unordered-ish, too sparse) | ✅ decode on device | lowest |
| **Ordered N-frame sequence** (e.g. 6–12 @ ~1–2 fps, timestamps attached) | ✅ (still small) | ⚠️ **mostly** — enough to see departure vs arrival, reveal direction, progression | ✅ device-side normalize to JPEG | low-moderate |
| **Compressed clip** (re-encode short H.264, downscaled) | ⚠️ for long clips | ✅ full temporal | needs device transcode (HEVC→H.264), heavy for 154 s | moderate |
| **Temp S3 upload + job** | ❌ breaks <3 s for big files | ✅ | ✅ | high infra (the design-corrections lesson says DON'T build this now) |
| **Native Bedrock video input** | model-dependent | ✅ | model-dependent | depends on chosen model (§9) |

**Recommendation: ordered frame sequence as the C4 baseline transport**, device-side:
decode locally (handles HEVC + both orientations without server transcode), sample an
**ordered, timestamped** set (not just 3; propose **6–10 frames spanning the clip, denser
where motion energy is high**), downscale+JPEG, send with per-frame timestamps. This keeps
the <3 s / small-payload budget AND preserves enough **temporal order** for §13. It is a
**superset of spec 08's 3-frame sampler** (3 frames is a special case) and matches the C2
path already in production (`/v1/scene-understanding` takes 3–6 JPEG frames, 2 MB/frame,
8 MB total — reuse that proven multipart budget).

**Long-clip rule (S07_A 95 s, S08_D 154 s):** sample across the **relevant window**, not
the whole file; a 154 s clip is almost certainly over-captured — validation samples the
span, and the Edit Planner (later) handles trimming. Do **not** upload 214 MB.

> **OPEN DECISION 7-A (needs approval):** frame count & fps policy (fixed 6 vs
> motion-adaptive 6–10) — resolve empirically on the corpus during C4, since the dataset
> was collected precisely to measure this. **OPEN DECISION 7-B:** if a chosen model has
> strong native short-video input and meets <3 s on H.264 ≤ ~15 s clips, prefer native
> video for the *short* sets and fall back to frame-sequence for long ones (hybrid). Defer
> until model eval (§9).

---

## 8. Temporal-understanding recommendation (Deliverable 8/13-temporal)

**Explicitly: Shot Validation is NOT unordered image recognition.** The corpus proves it:
- **departure vs arrival** (S02_A vs A03) — same objects, opposite time-order.
- **walk toward vs walk away** (S02 vs S05_B) — direction over time.
- **reveal direction** (S03_A friend→landscape vs S03_D reverse) — pan order.
- **progression** (S05) — change across the clip.
- **contradictory action** (S02_G: approach → remove pack → sit) — meaning emerges only
  from the *sequence*.

Therefore the validator MUST receive **ordered, timestamped** evidence (§7 recommendation)
and the prompt MUST ask about **change over time** ("what happens first / then / last; does
the motion go toward or away"). A pure 3-still sampler (frozen 08) is **insufficient** for
S02/S03/S05 and the temporal A01 traps — this is a concrete, corpus-driven reason to extend
08's sampler to an ordered sequence. (Deterministic motion-energy direction estimation can
assist but cannot replace semantic temporal reasoning.)

---

## 9. Model architecture (Deliverable 9, 14, 15)

**Do NOT assume Opus 4.5.** Shot Validation is a different task from Direction (05): it is
high-frequency, latency-critical (<3 s), PASS-biased, and mostly perceptual. Proposed
**minimal decomposition**:

```
Stage 1 — DETERMINISTIC (no model, on device / fast server):
  duration check (AVFoundation): clip ≥ shot.target_duration × 0.7
  motion-energy heuristic: catastrophic instability → severe_shake
  (cheap, catches T01_B/D and gross shake with zero model cost; spec 08 pipeline)

Stage 2 — MULTIMODAL SEMANTIC MODEL (purpose-conditioned):
  input: ordered frames + Shot.purpose + instruction + Beat.purpose (+ concept summary)
  output: the 4-axis ShotValidationJudgment (§3.1) → deterministically derived to the
          three-state surface (GOT IT / KEEP + ONE MORE / TRY AGAIN) + one plain reason
```

This two-stage split means the expensive model only judges **semantics/temporal purpose**,
while cheap deterministic checks handle gross technical failure — the right cost/latency
shape for a per-capture call. A single multimodal model doing everything is the fallback if
the deterministic stage proves redundant, but the corpus (T01) shows deterministic checks
are cheap wins.

**Model selection is its own evaluation** (not inherited from Director). C4 must run a model
comparison on the corpus measuring: false-RETRY rate (the PASS-bias KPI from 08), temporal
accuracy on S02/S03/S05, adversarial catch-rate on A01, and p95 latency < 3 s. Candidate
set should be *small, fast* multimodal models first (not Opus-class), escalating only if
temporal/adversarial accuracy is inadequate.

> **OPEN DECISION 9-A (needs approval):** the C4 model candidate list and the pass bar
> (target false-RETRY ≤ X%, adversarial-catch ≥ Y%). Propose we set these from a first
> corpus baseline run, then approve.

---

## 10. Evaluation / fixture ground-truth model (Deliverable 10, 16)

Each fixture = **(media_ref, requested Shot/Beat context, expected judgment)**. Ground truth
is expressed on the **4 axes** (not a single label), because that is what lets us score the
alternative-success and wrong-beat cases the corpus was built for.

```jsonc
// evals/shot_validation/scenarios/<FIXTURE_ID>/request.json   (committed; references media)
{
  "fixture_id": "S02_departure__D_walk_away_through_door",
  "media_ref": "evals/assets/videos/S02_departure/S02_D_walk_away_through_door.mov",
  "shot": { "purpose": "Communicate departure / beginning of journey.",
            "instruction": "Walk toward the camera down the hallway, like heading out.",
            "subject_action": "walk toward camera", "camera_motion": "static",
            "target_duration_seconds": 4 },
  "beat": { "id": "beat_departure", "purpose": "Beginning of the journey." },
  "concept_summary": "A quiet departure before a long hike."
}
// expectations.json   (committed)   — model-generated axes + DETERMINISTIC derivations
{
  "technical_usability": "usable",
  "execution_match": "deviated",
  "shot_purpose": "alternative_fulfilled",
  "story_utility": "strong_elsewhere",
  // derived (NOT model fields) — recorded for scoring the derivation too:
  "clip_disposition": "keep",
  "requested_shot_status": "fulfilled",
  "user_state": "got_it",
  "becomes_moment": true,
  "requested_beat_effect": "fulfilled",
  "notes": "Literal instruction was walk-toward; walk-away-through-door fulfills departure more strongly (alternative, not contradiction)."
}
```

Evaluation dimensions scored by the harness:
1. **user-state accuracy** — predicted {GOT IT | KEEP + ONE MORE | TRY AGAIN} vs expected,
   plus the **false-TRY-AGAIN rate** (the PASS-bias KPI, now three-state).
2. **purpose accuracy** (axis `shot_purpose`), the real quality signal.
3. **temporal accuracy** (S02/S03/S05 subset) incl. **contradiction vs alternative** split.
4. **adversarial catch-rate** (A01 subset): % of traps NOT marked requested-shot `fulfilled`.
5. **alternative-success recognition** (deviated+alternative_fulfilled → GOT IT, not merely kept).
6. **derivation correctness** — clip_disposition / requested_shot_status / user_state match
   the deterministic rules in §3.2–§3.3 given the axes.
7. **latency p95 < 3 s**.

> **DECIDED (user approval):** the four axis-vocabularies in §3.1 are the frozen
> `ShotValidationJudgment` ground-truth schema. Fixture `expectations.json` MAY now be
> authored against it. (Still not authored in this document — C4 is not being implemented
> yet; authoring happens when C4 work begins.)

---

## 11. Stable fixture-ID strategy — NO raw renames (Deliverable 11)

Raw files stay exactly as collected (incl. `_2` retakes and the S05/S06 prefix collisions).
Fixture IDs are a **committed mapping layer**, decoupled from filenames:

```
FIXTURE_ID = "<SET>__<VARIANT_SLUG>"      # e.g. S05_trail_progression__E_feet_walking
media_ref  = exact current path on disk    # the collision is resolved by DISTINCT fixture ids
```

- S05 collision → two fixtures: `S05_trail_progression__E_feet_walking` (→ `_E_feet_walking_alternative.MOV`)
  and `S05_trail_progression__E_static_two_people` (→ `_E_static_camera_two_people.mov`). **No file renamed.**
- S06 two-`G_` → `S06_difficulty__G_storm_cold` and `S06_difficulty__G_storm_wind`.
- `_2` retakes → `..._A_take1` / `..._A_take2`, both pointing at their real files; each is a
  distinct real take (per the user's interpretation rule).
- **Shared-source cases are first-class:** `S02_departure__G_contradictory` and
  `A01_semantic_adversarial__A05_wrong_motion` **both reference the same physical file**
  (`.../A05_motion_but_wrong_motion.mov`) under different Shot/Beat context — likewise
  `A01__A06_wrong_beat` and `A01__A01_not_difficulty` share `A01_hiking_but_not_difficulty.MOV`.
  The mapping stores one `media_ref`; **media is never duplicated**. This contextual reuse is
  itself a C4 property (same footage, different requested purpose → different expected
  judgment).

The ID↔path map lives in a single committed `evals/shot_validation/media-map.json`
(text, no media) so renames/reorganization later touch one file, not every fixture.

---

## 12. Raw / derived-media privacy strategy (Deliverable 12)

**Current protection is extension-based and therefore insufficient for derived artifacts.**
Today `.gitignore` ignores video + (just added) raster image extensions under
`evals/assets/`. But a future sampled-frame export named `.jpg` IS covered, while anything
with an unanticipated extension, or derived artifacts written *outside* `evals/assets/`
(e.g. a harness cache, a results dir), is not reliably covered.

**Recommendation (do NOT move anything yet — approval required):** adopt a **directory-level
ignored location** for ALL raw + derived personal media, so protection is by *location*, not
by guessing extensions:

```
evals/assets/private_local/           # already gitignored by directory — the intended home
    videos/                           # raw clips (currently they live one level up in videos/)
    frames/                           # DERIVED sampled frames (never committed)
    thumbs/                           # DERIVED
```

- Keep **committed, media-free** fixture metadata under `evals/shot_validation/`
  (request/expectations/media-map) — these reference the ignored media by path.
- A directory-level ignore is **fail-safe**: any derived artifact written under it is private
  regardless of extension.

> **OPEN DECISION 12-A (needs approval):** the corpus currently sits in the *committed-path*
> `evals/assets/videos/` (protected only by the extension ignore). Do we (A) **relocate** it
> under `private_local/` for directory-level safety [recommended, but it's a move → needs
> approval], or (B) **keep it in place** and rely on the extension ignore + a pre-commit
> guard that blocks any binary under `evals/assets/`? Either way: **derived frames must be
> written only to a directory-ignored path**, never beside the committed fixtures.

---

## 13. CURRENT vs PROPOSED ValidationResult (Deliverable 13)

### CURRENT (frozen `ValidationResultContract`)
```python
usable: bool
recommendation: ValidationRecommendation   # accept | retake
confidence: float | None                    # 0..1
issues: list[ValidationIssue]               # too_short, severe_shake, subject_missing,
                                            # severe_underexposure, severe_overexposure,
                                            # instruction_not_followed
shot_id: UUID | None
capture_asset_id: UUID | None
```

### PROPOSED — B+ : simple external `ValidationResult` + separate internal `ShotValidationJudgment`
```python
# ---- EXTERNAL: ValidationResult (user-facing role kept simple; NOT redesigned in place) ----
# user_state is the three-state surface (§3.3). No scores/axes exposed.
user_state: Literal["got_it", "keep_plus_one_more", "try_again"]
reason: str | None                           # one plain sentence (shown for keep_plus_one_more / try_again)
# issues: EXTENDED gross-failure enum (+ out_of_focus, wrong_subject, unusable_motion)
# confidence / shot_id / capture_asset_id: unchanged
# NOTE: the frozen ValidationResultContract is NOT edited this milestone; the only approved
# contract-level change is the ValidationIssue enum extension (§8 of the approval).

# ---- INTERNAL: ShotValidationJudgment (NEW model-layer output; drives loop + eval) ----
technical_usability: Literal["usable", "minor_issues", "unusable"]
execution_match:     Literal["matched", "deviated", "absent", "contradicted"]
shot_purpose:        Literal["fulfilled", "partial", "unfulfilled", "alternative_fulfilled"]
story_utility:       Literal["none", "useful_elsewhere", "strong_elsewhere"]
# DERIVED deterministically (NOT model fields): clip_disposition {keep,discard};
#   requested_shot_status {fulfilled,partial,unfulfilled}; user_state (above).
```

Representative mappings across ALL 10 categories (axes → derived disposition/status → user state):

| Category · clip | tech / exec / purpose / utility | disposition / shot-status | User state |
|---|---|---|---|
| S01 · D_poor_framing | minor_issues / matched / partial / none | keep / partial | **GOT IT** |
| S01 · F_alternative_good | usable / deviated / alternative_fulfilled / strong_elsewhere | keep / fulfilled | **GOT IT** |
| S02 · G_contradictory | usable / **contradicted** / unfulfilled / none | **discard** / unfulfilled | **TRY AGAIN** |
| S02 · D_walk_away | usable / deviated / **alternative_fulfilled** / strong_elsewhere | keep / fulfilled | **GOT IT** |
| S03 · D_reverse_reveal | usable / deviated / **unfulfilled** / useful_elsewhere | keep / unfulfilled | **KEEP + ONE MORE** |
| S04 · B_person_too_large | usable / matched / **unfulfilled** (scale) / useful_elsewhere | keep / unfulfilled | **KEEP + ONE MORE** |
| S05 · E_static_two_people | usable / deviated / partial / useful_elsewhere | keep / partial | **GOT IT** |
| S06 · G_storm_wind | usable / matched / **fulfilled** / strong_elsewhere | keep / fulfilled | **GOT IT** |
| S07 · C_one_person_only | usable / absent / **unfulfilled** / useful_elsewhere | keep / unfulfilled | **KEEP + ONE MORE** |
| S08 · D_cooking_dinner | usable / matched / fulfilled / strong_elsewhere | keep / fulfilled | **GOT IT** (sample window!) |
| T01 · G_out_of_focus | **unusable** / — / — / none + `out_of_focus` | **discard** / unfulfilled | **TRY AGAIN** |
| A01 · A06_wrong_beat | usable / matched / **unfulfilled** (this beat) / **strong_elsewhere** | keep / unfulfilled | **KEEP + ONE MORE** |

**Contradiction is caught, not leaked (approved §5.4):** S02_G `contradicted` forces
requested-shot `unfulfilled`; with no story utility it is **discard → TRY AGAIN** (if it had
utility it would be **KEEP + ONE MORE**). This is the corpus-driven correction to the former
binary surface — a clean-looking contradiction is never a silent GOT IT. The value C4 adds
lives in the internal axes **and** in the now-three-state surface that can finally express
"keep this, but we still need the beat."

---

## 14. (folded into §1 and §13 — representative mappings across all 10 categories)

---

## 15. C4 MUST-HAVE vs DEFER (Deliverable 15)

**MUST-HAVE for C4:**
- Deterministic Stage-1 checks (duration + motion energy) — cheap, corpus-proven.
- Ordered, timestamped frame-sequence transport (device-side decode; HEVC+both orientations).
- Purpose-conditioned Stage-2 multimodal validation producing the three-state surface
  (GOT IT / KEEP + ONE MORE / TRY AGAIN) + one plain reason.
- The internal `ShotValidationJudgment` feeding the Director loop so `beat_progress` is
  **derived**, not model-asserted.
- `/v1/shot-validation` endpoint + validation engine (mock first, per 08 Phase 1).
- Fixture schema + media-map + stable IDs (committed, media-free).
- Model evaluation on the corpus with the §10 dimensions.

**DEFER (explicitly out of C4):**
- S3 upload / async job infra (reference-media transport is a measured fallback only —
  per the standing design correction; don't build it now).
- Native-video transport unless the model eval shows it's necessary and meets <3 s.
- `AssetUnderstanding` / full Moment semantic indexing (Milestone H).
- Any Edit-Planner quality handling (08 says Edit Planner owns minor quality).
- `skip_beat` Director action — NOT added in C4 (approved §5.2); revisit only if dogfooding
  proves the existing actions can't abandon an unproductive beat.
- The three tracked future gaps are NON-blocking: contradictory departure (shared-source
  S02_G↔A05), out-of-focus control (have T01_G now), beautiful-wrong-beat (A06↔A01).
- NOTE: fixture `expectations.json` authoring is **now unblocked** (axis schema approved,
  §10) but is **not** done here — it belongs to C4 implementation, which is not started.

---

## 16. Decision register (Deliverable 16)

**DECIDED (user approval, this revision) — now authoritative in this document:**
1. **Contract strategy = B+** (§20): keep simple external `ValidationResult`; add separate
   internal `ShotValidationJudgment`; do NOT materially redesign `ValidationResult` in place.
2. **4-axis vocabulary frozen** (§3.1): `technical_usability` / `execution_match` /
   `shot_purpose` / `story_utility` with `story_utility = none | useful_elsewhere |
   strong_elsewhere`. Beat fulfillment stays Director state.
3. **Clip usefulness ≠ requested-shot success** (§3.2): CLIP DISPOSITION {keep, discard} and
   REQUESTED SHOT STATUS {fulfilled, partial, unfulfilled} are **deterministic derivations**
   from the axes, not extra model fields.
4. **Three user-facing states** (§3.3): GOT IT / KEEP + ONE MORE / TRY AGAIN — replaces the
   binary PASS/RETRY surface. No scores/axes exposed. (08 rationale updated.)
5. **Contradiction handling** (§5.4): `contradicted` ⇒ requested shot `unfulfilled`;
   +utility ⇒ KEEP + ONE MORE, no utility ⇒ TRY AGAIN. `deviated+alternative_fulfilled` ⇒
   GOT IT. The two are explicitly distinct.
6. **Moment lifecycle** (§4): promotion iff CLIP DISPOSITION == keep; retries that discard
   never pollute Story Moments; useful-elsewhere is kept but NOT auto-assigned to another
   beat (Director may claim later); non-Moment captures stay recoverable via the
   CaptureSession/local file lifecycle.
7. **No `skip_beat`** in C4 (§5.2): use the existing `DirectorActionType`; revisit only if
   dogfooding proves it necessary.
8. **`ValidationIssue` enum** (§8): add exactly `out_of_focus`, `wrong_subject`,
   `unusable_motion` — no further taxonomy expansion. (This is the one approved
   frozen-contract change; applied when C4 implementation begins, not now.)

**STILL OPEN (require your call before/at C4 implementation):**
- **7-A / 7-B** — frame count / fps sampling policy (fixed vs motion-adaptive); whether to
  use native-video transport for short H.264 sets as a hybrid. (Resolve empirically on the
  corpus during C4.)
- **9-A** — the C4 model candidate list and the pass bar (false-TRY-AGAIN ≤ X%, adversarial
  catch ≥ Y%, p95 < 3 s). Propose setting these from a first corpus baseline run.
- **12-A** — corpus privacy: relocate under `private_local/` (directory-level, recommended)
  vs keep in place + pre-commit guard. **Non-negotiable either way: derived frames MUST be
  written only to a directory-ignored path.**

---

## 20. DECISION — contract disposition = B+ (APPROVED)

> **DECIDED (user approval):** **B+ — keep the simple external/user-facing `ValidationResult`
> role; add a separate internal `ShotValidationJudgment` for the richer loop/eval signal; do
> NOT materially redesign `ValidationResult` in place, and do not edit it this milestone.**

Rationale (retained for the record):
- **A (keep as-is) is insufficient** — proven by A01: every adversarial clip returns
  `usable/accept`, and alternative-success / wrong-beat / out-of-focus are unrepresentable.
  The frozen contract cannot carry the loop signal 05 requires.
- **C (materially redesign in place) is premature** — it would mutate a frozen contract
  before the corpus-driven model eval shows which axes move quality, and contracts are not
  to be modified yet.
- **B+ is the reconciliation** — external surface stays simple (now the three-state GOT IT /
  KEEP + ONE MORE / TRY AGAIN, 08-updated), while the internal 4-axis `ShotValidationJudgment`
  feeds the Director loop and eval. The only approved frozen-contract change is the
  `ValidationIssue` enum extension (§8), applied at C4 implementation time. `skip_beat` is
  explicitly NOT added.

**STOP — design only. No C4 code, no contract edits now, no corpus moves.** With these
decisions authoritative, C4 implementation (mock-first per 08 Phase 1) and the model eval can
begin when you say go; the three still-open items (§16: 7-A/B, 9-A, 12-A) are resolvable
during that work.
