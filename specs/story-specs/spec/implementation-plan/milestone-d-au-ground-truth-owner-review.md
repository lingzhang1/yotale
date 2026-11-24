# Asset Understanding — Ground-Truth OWNER REVIEW (Milestone D)

**Status:** AI-PROPOSED, awaiting owner approval. These annotations become the AU
evaluation ground truth **only after you approve them.** Nothing has been scored
against them yet, and **no finalist model has been run** — that spend is gated on
this review.

**How these were produced:** each clip was reviewed from a timestamped contact
sheet of the *actual footage* (not the filename). Contact sheets:
`/Users/lingzhang/Workplace/story/evals/assets/private_local/frames/au_contact_sheets/<fixture>.png`
(denser for long/multi-event clips — 40 frames for the 95s and 154s clips — so the
event list is reviewable without blind scrubbing). Proposed annotations:
`/Users/lingzhang/Workplace/story/evals/asset_understanding/ground_truth.proposed.json`.

**Subset (18 clips) — §1 coverage check**

| band | clips |
|---|---|
| short ≤10s | T01_A_clean_4s, T01_I_camera_points_away, S01_A_exact_good, S02_D_walk_away, S04_A_small_person (6.1s), S07_E_wrong_people (9.5s), S08_F_window_view (9.1s) |
| medium 10–30s | S01_F_alternative_good (15.7s), S02_A_exact_good (22.2s), S02_G_contradictory (14.3s), S03_D_reverse_reveal (15.0s), S05_A_follow_behind (19.6s), A03_arrival_not_departure (15.1s) |
| long >30s | S06_E_cross_river (38.0s), A01_hiking_not_difficulty (38.9s), A06_beautiful_wrong_beat (38.9s), **S07_A_natural_conversation (95.3s)**, **S08_D_cooking_dinner (154.1s)** |

Temporal semantics covered: departure (S02_A), arrival-not-departure (A03),
reveal-direction/reverse (S03_D), progression (S05_A), contradiction (S02_G),
subject movement (S04_A person enters). Story semantics: difficulty (S06_E),
difficulty-adversarial (A01), companionship (S07_A), wrong-people (S07_E),
end-of-day (S08_D), beautiful-but-wrong-purpose (A01/A06/S08_F),
useful-elsewhere (most). Multi-event: S08_D, S07_A, S06_E (late 2nd figure).
Controls (easy / hallucination / over-segmentation): T01_A, T01_I, S01_A.

---

## Clips needing a decision (ambiguity flags you should rule on)

These are the subjective calls I will NOT silently resolve. Your ruling becomes
ground truth.

1. **S02_A_exact_good — where does "departure" begin?** Gear-up indoors is 0–4s,
   the walk-out is 4–20s. I annotated 0–4s as *setup* and 4–20s as the departure
   useful segment. **Confirm or move the boundary.**

2. **S02_D_walk_away_through_door — departure or approach?** She crosses *out*
   through a doorway (threshold = setting out) but then walks *toward* the camera.
   C4 scored it "alternative_fulfilled". I kept it as a departure/threshold
   variant. **Is that right, or is this really an approach/arrival?**

3. **S07_A_natural_conversation (95s) — companionship strength.** It's mostly ONE
   person reclining for ~55s; other hikers appear ~55s; end selfie ~90s. I scored
   requested-shot contribution as *partial* (weak genuine two-person interaction)
   and story_utility *useful_elsewhere*. **Agree, or is this a fulfilled companion
   moment?** This clip is also the key over-segmentation + late-multi-event probe.

4. **S08_D_cooking_dinner (154s) — it is EATING, not cooking.** They open and eat
   a dehydrated pouch meal; nobody cooks. I annotated "eating". **Confirm**, so a
   model saying "cooking" is correctly scored as a filename-driven hallucination.

5. **S08_F_window_view — the meal looks like breakfast muesli, not dinner.** I kept
   story_utility *strong_elsewhere* (the window vista is the payoff). **Confirm the
   meal description and that it still serves the end-of-day mood.**

6. **S04_A_small_person — the person is tiny and enters only ~3.5s.** This is a
   deliberate recall probe (a frame-timeline model may miss the human). Ground
   truth: a small person DOES appear. **Confirm you can see it on the sheet.**

7. **story_utility vs prior C4 labels.** For several clips my AU story_utility
   matches the committed C4 `expectations.json`; for a few I propose a value (e.g.
   S07_A I set *useful_elsewhere* vs reasoning). Flag any you'd set differently.

---

## Per-clip proposed ground truth (summary)

Legend: **GT order** = temporal interpretation · **util** = story_utility ·
**shot** = requested-shot contribution.

| fixture | dur | GT observed events (count) | GT temporal order | shot contribution | util |
|---|---:|---|---|---|---|
| T01_A_clean_4s | 6.5 | 1 (static backpack) | none (static) | fulfilled | useful_elsewhere |
| T01_I_camera_points_away | 2.0 | 1 (mis-aimed) | none | unfulfilled | none |
| S01_A_exact_good | 6.5 | 1 (static backpack) | none (static) | fulfilled | useful_elsewhere |
| S01_F_alternative_good | 15.7 | 3 (gear→church→village) | object then place pan | alternative_fulfilled | strong_elsewhere |
| S02_A_exact_good | 22.2 | 5 (gearup→walk→corridor→depart→turn) | **departure (outbound)** | fulfilled | strong_elsewhere |
| S02_D_walk_away_through_door | 9.7 | 3 (door→emerge→approach) | **threshold then approach** ⚑ | alternative_fulfilled | strong_elsewhere |
| S02_G_contradictory_action | 14.3 | 4 (stand→lift pack→adjust→stay) | **preparation, NOT departure** | unfulfilled (contradicted) | useful_elsewhere |
| S03_D_reverse_reveal | 15.0 | 3 (landscape→tilt→person) | **landscape-first/person-last = REVERSE** | unfulfilled (contradicted) | useful_elsewhere |
| S05_A_follow_behind | 19.6 | 2 (follow→vista) | progression into landscape | fulfilled | strong_elsewhere |
| A03_backpack_arrival | 15.1 | 4 (walk→enter→set down→settled) | **ARRIVAL, not departure** | unfulfilled (contradicted) | useful_elsewhere |
| S04_A_small_person | 6.1 | 2 (landscape→tiny person) | person enters late | fulfilled | strong_elsewhere |
| S06_E_cross_river | 38.0 | 1 sustained (+late 2nd figure) | one continuous crossing | fulfilled | strong_elsewhere |
| S07_A_natural_conversation | 95.3 | 3 (rest 0–55 → others ~55 → selfie ~90) | **long rest, LATE 2nd event** ⚑ | partial | useful_elsewhere |
| S07_E_wrong_people | 9.5 | 1 (strangers on ridge) | one continuous | unfulfilled (wrong people) | useful_elsewhere |
| S08_D_cooking_dinner | 154.1 | 4 (open pouch→eat→eat→selfie) | **EATING a meal, not cooking** ⚑ | fulfilled | strong_elsewhere |
| S08_F_window_view | 9.1 | 2 (meal→mountain window) | meal-to-vista reveal | fulfilled (mood) | strong_elsewhere |
| A01_hiking_not_difficulty | 38.9 | 3 (speck→approach→valley) | easy approach, NOT difficult | unfulfilled | strong_elsewhere |
| A06_beautiful_wrong_beat | 38.9 | 3 (same bytes as A01) | easy approach | unfulfilled | strong_elsewhere |

Full event timings, useful/dead segments and per-clip flags are in
`ground_truth.proposed.json`. ⚑ = a flagged decision above.

---

## What happens after you approve

1. I promote `ground_truth.proposed.json` → `ground_truth.json` (applying your edits).
2. Run the 4 finalists on IDENTICAL 24-frame evidence (Nova Pro, Sonnet 4.6,
   strongest invocable Opus) + Pegasus native video (long/multi-event/temporal
   focus) — **projected spend reported for approval before the run.**
3. Score event P/R/F1, hallucination, over-segmentation, temporal, segmentation,
   Story-semantics; separate semantic-quality-when-valid from end-to-end
   structured reliability; classify model-limited vs evidence-limited failures.
4. Cost accounting + quality/latency/cost frontier → single MVP model recommendation
   + minimum MomentUnderstanding contract.

The Photos-persistence task (§13) is independent and I'll scope it in parallel.
