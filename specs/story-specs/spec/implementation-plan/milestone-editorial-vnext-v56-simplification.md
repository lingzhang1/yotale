# Editorial vNext — EditPlan 5.6 "radical simplification"

**Status:** implemented on `feat/editorial-vnext-v56` (draft PR). Offline tests green. **No live model call was made, nothing is deployed, nothing is merged, beta is untouched.** Selected only by `STORY_EDIT_PLAN_VERSION=5.6` (never the default). **Quality is not accepted:** the numbers below are deterministic descriptors of the prompt and its input; whether 5.6 produces better videos is decided by the owner watching rendered output.

## 1. Why

The Highlights-vs-Full-Story evaluation of 5.5 on the 38-Moment TMB data was inconclusive (PR #126). The prompt was long (≈1,640 words), carried a narrative-first system prompt, and sent the same AU facts three or four times. 5.6 tests the opposite hypothesis: *a much shorter prompt with one image-led strategy per type will behave more like an editor.*

## 2. Audit of 5.5 (what competes with what)

| # | Finding | Effect |
|---|---|---|
| 1 | `summary`, `evidence`, `events` repeat the same AU facts; `narrative_candidates` repeats them again (~17k + 5k tokens for 38 Moments) | Highlights is fed a narrative record of every Moment. |
| 2 | System prompt: "strongest achievable version of THIS Story", "coherent narrative progression grounded in Guide/Coverage", significance-weighted screen time | Narrative-first selection even for Highlights. |
| 3 | Native audio "DEFAULT TO keep" (~330 words) | Conflicts with fast Highlights cuts and music-led pacing. |
| 4 | "Plan TO the target / ±10%" in three places vs "a shorter excellent video is better" | Pushes toward padding with weaker footage. |
| 5 | Server brief (CREATIVE DIRECTION) restates the TYPE STRATEGY | Two statements of the same instruction. |
| 6 | BUDGET block restates the duration rule | Third statement. |
| 7 | Guide (2.4k tokens) + Coverage (3.4–3.8k): shooting-script and Chinese note prose | Irrelevant to cutting; 5.8k tokens. |
| 8 | `sampled_frame_ms` (3.5k tokens) | Duplicates timestamps already burned into the contact sheets. |
| 9 | Typical shot 3–5 s (Highlights) / 5–9 s (Full Story) | Mean Highlights shot far longer than the owner's reference. |
| 10 | Duration Intelligence floor `n_moments × 2 s` | 38 Moments ⇒ 76 s floor ⇒ a Highlights recommendation of 80–100 s. |

## 3. What changed

### 3.1 Prompt (`prompts/edit_plan/5.6/system.md`, new; 5.5 and 5.3 untouched)
Shared role + mechanical rules only: 665 words (5.5: 1,638; 5.3: 1,793), 935 tokens (5.5: 2,373). It contains no type, breadth, Guide/Coverage, narrative-progression or pacing language (asserted by a test). It states: frames are the primary evidence and text is a hint; never invent footage or chronology; priority = user directives > STRATEGY > defaults; duration is a strong objective, never a reason to pad, and `feasible=false` is **not** for ending somewhat short; sound; music anchors only with a real MusicAnalysis; and the mechanical rules (ids, ranges, output = span / speed, speed 0.5–2.0 and **not** used to shorten the edit, mostly cuts, `narrative_role`). The validator is unchanged and remains the final authority; a playable plan is never rejected for editorial or duration shortfall.

### 3.2 Strategies (user message, one block per request)
**Highlights (image-led):** "MAKE THE MOST VISUALLY EXCITING SHORT VIDEO POSSIBLE." Compare ALL Moments visually (confidence is not appeal); front-load, several distinct payoffs in the first ~10 s; typical shots 1–2.5 s as a preference; start on the action and cut sooner, no speed-ups; no routine establishing shots, no forced chronology, not every Moment; pace to the real beats when a MusicAnalysis exists, otherwise to the music plan; sound default music-forward.
**Full Story (narrative-led):** thread from events / narrative candidates / interactions with Guide and Coverage as context; never invent; complete actions, typical 4–10 s or longer; keep natural audio (default keep); chronology only where the material shows it (import order is not chronology); choose by meaning, short inserts allowed.
Both: the user's own instructions win; REVISE preserves the base edit. The client's generic brief (a fixed boilerplate string, not user text) is dropped. There is **no CREATIVE DIRECTION block, no legacy `editorial_mode` line and no `editorial_type` field** in the 5.6 payload, so three instructions can no longer compete. A client brief only gates the critique pass (unchanged, off by default).

### 3.3 Input projections (built from `inputs.moments`, which is never modified; validation sees the full Moment)
- **Highlights Moment:** `id`, `duration_seconds`, `useful_segments`, ≤5 `subjects`, `visual_candidates` {start, end, peak, role, value≤140 chars}. A Moment with no visual candidates gets ≤2 short events (or a ≤160-char summary) so it is not invisible. Dropped: `summary`, `evidence`, `narrative_candidates`, `confidence`, `sampled_frame_ms`, `analysis_version`; `story_guide` and `story_coverage` omitted.
- **Full Story Moment:** `id`, duration, `useful_segments`, `summary` (≤240), ≤5 `subjects`, ≤6 timed `events` (≤120), `narrative_candidates` {start, end, role, what_happens≤200}, `visual_candidates` ranges only. Guide = `framing_summary` + scenes {id, title, why_it_matters}; Coverage = dimensions {id, state}, strengths, redundancies, sufficiency.
- **Both:** compact `music_plan` (`audio_strategy`, character, energy arc without notes/provenance), `music_analysis` unchanged when present, `creative_intent` without nulls, `target_duration_seconds`, the image-order list (needed for sheet↔Moment identity).
- No AU persistence change, no AU beauty score, no iOS change.

### 3.4 Pacing
Typical shot ranges are versioned: Highlights 1–2.5 s and Full Story 4–10 s in 5.6 (5.5 keeps 3–5 / 5–9; its prompts are byte-identical to master, golden-tested). The shot-count hint is capped at 2 shots per Moment and is advisory only: the validator and the deterministic fitter do not read it (asserted).

### 3.5 Duration
- **Sizing is NOT changed by this PR.** An earlier commit changed `compute_duration_evidence` (floor `max(4, 2·n_moments)` → 4 s). That function feeds the duration recommender for every planner version, so it altered the default path independently of `STORY_EDIT_PLAN_VERSION`; it was reverted (`789db45`) to keep the 5.5-vs-5.6 comparison prompt-only. The type-aware fix belongs to the separate `duration_recommendation/2` milestone (§8).
- Explicit Custom (e.g. 90 s) stays authoritative: carried verbatim as `target_duration_seconds`, never silently changed.
- v5.6 only: when the delivered cut is more than 20% under target, the job still ships (`partial`, `approx_duration` in `material_unmet`) with a neutral, factual note: "It runs about Xs instead of the requested Ys." It does not claim the footage was exhausted. The 20% is a labeling threshold, not a rejection: nothing is ever rejected for length.
- `duration_recommendation/1` stays frozen. Whether a 20–40 s Highlights recommendation for a 35–40-Moment scenic trip is right remains a hypothesis; see §8.

### 3.6 Diagnostics and harness
`diagnostics.selection.pacing` (v5.6 only): cuts, share of shots ≤2.5 s, duration buckets, opening-10 s shots / payoff shots / distinct payoff Moments (recomputed independently in tests). `scripts/editorial_eval.py` rows gain `cuts`, `share_le_2_5`, `opening10_*` for every version, and `compare` prints a Highlights-vs-Full-Story difference per version. `scripts/editorial_frozen.py` (`freeze`, `breakdown`, `replay` dry run) turns durable AU + Story data into one frozen request used by both arms; `--live` is intentionally not wired.


## 3.7 User creative direction (verified through the real worker path)
Where user text actually travels: `creative_intent` (raw_text, tone, target), `revision_context.soft_direction` and `.directives` (Customize text and resolved Moment references), `sound_preference`, and `duration_target_source`. The removed CREATIVE DIRECTION block carried only the fixed app brief. Two pre-existing renderer gaps were found and fixed **for 5.6 only** (5.3/5.5 stay byte-identical):
- A directed Create-Another-Version (mode `explore`) carries the user's text in `soft_direction`, which the older renderer printed only for Revise, so it was silently dropped.
- An Original create with Customize text arrives as mode `revise` **without a base plan** and was framed as "revise your existing edit, the BASE PLAN below". 5.6 renders it as `USER INSTRUCTIONS` (soft text + HARD REQUIREMENTs + "these win over the STRATEGY").
Tests drive `worker._run_edit_plan` with a recording gateway: Start with Moment 15 (opening directive), most beautiful views first and cinematic/emotional (soft text), keep original sound (Sound preference), must-include and ordering, Custom duration, Revise with a base plan (unchanged), directed Explore; each makes exactly one model call with no critique. Observation, not changed: the worker and the engine treat an Original-with-Customize-text as `revise` (metrics label and duration-fit exemption).

## 3.8 Frozen-request replay (`scripts/editorial_replay.py`)
Built on the existing staging bucket: the API stages the exact body JSON and contact-sheet JPEGs in S3 for the worker and the worker deletes them at job end. `capture` (read-only) copies them while a job is in flight; `verify` re-hashes 14 components (Moment ids/order and payload, Guide, Coverage, intent+target, type, operation+instructions, sound, music, brief text, sheet order, sheet bytes); `run` replays ONE arm in a child process pinned by `STORY_EDIT_PLAN_VERSION`, through the worker's input construction (a test proves the prompt equals the worker's), `RealEditPlannerEngine`, the existing provider gateway and the technical validator. It refuses a tampered case, critique, Explore/Revise/directed requests, and a second attempt on the same arm. No endpoint, AWS resource, flag or worker change. Private data lives under a 0700 directory and `purge` removes it. Per arm it records system / user-text / AU-projection / image tokens (image = estimate), real input/output tokens, model and repair calls, planner wall time, cost, the pre-fit and fitted durations and the pacing metrics.

## 3.9 Activation plan
Live effective dev version: 5.5 (worker Lambda `STORY_EDIT_PLAN_VERSION=5.5` from `release.json` `environment_overrides.development`, expiring 2026-11-30); dev queue and jobs table empty. The four replay arms need **no dev change**: the version is pinned per child process. A dev pin to 5.6 is needed only to have the app produce rendered MP4s. If wanted: a one-line `release.json` change (`development: "5.6"`, expiry kept or reset), PR, CI gate, `deploy-dev` after a no-job-in-flight check, and a revert PR afterwards. Beta, gamma and production are never touched. Not executed.

## 4. Size (tiktoken o200k_base; the 38-Moment TMB case)

| Component (tokens) | 5.3 | 5.5 | 5.6 Highlights | 5.6 Full Story |
|---|---|---|---|---|
| System prompt | 2,604 | 2,373 | **935** | 935 |
| User directives + strategy + image-order list | 1,313 | 1,840 | 1,393 | 1,330 |
| Moments (remainder of the measured total) | ≈34,000 | ≈34,000 | ≈6,300 | ≈12,100 |
| Guide / Coverage | 2,369 / 3,371 | same | omitted | 425 / 560 |
| Music plan | 610 | 610 | 237 | 244 |
| **Text total** | **59,817** | **60,103** | **8,981** | **15,753** |
| Images (estimate, 38 sheets × ≈765) | 29,070 | 29,070 | 29,070 | 29,070 |
| **Input estimate** | ≈88.9k | ≈89.2k | **≈38.1k** | **≈44.8k** |

Calibration: the estimate for 5.3 (88.9k) is within 5% of a real job's measured 84.5k. Images are an estimate; the worker records the provider's real `input_tokens`. A smaller prompt is not evidence of a better video.

## 5. Tests (offline, no model)
`test_edit_plan_v56.py` (36 test functions, some parametrized): 5.3 goldens and a new **5.5 golden generated from master `929a060`** stay byte-identical; version resolution; 5.6 prompt length, no type/breadth bias, every mechanical rule present; strategies exclusive per type; no brief/legacy line/type field; projections (what is dropped, what survives, inputs never mutated); pacing hint numbers per version; directives, Custom, Revise/Explore; one model call; short cut ships `partial` and is never rejected; pacing diagnostics vs independent recomputation. Plus `test_editorial_frozen.py`, harness additions and plus replay tests. One existing 5.5 test used `5.6` as its "unknown version" example; it now uses `5.7`, the same intent.

## 6. Evaluation plan (not run)
Arms: 5.5 vs 5.6 on one **frozen** request per type (`editorial_frozen.py freeze`, same Moments, same Coverage snapshot, same music/sound), Full Story as Original in both, Highlights Original, critique OFF, requested duration equal (90 s / 155 s Custom) so the prompt is the only variable. Include the red-jacket / smile-reveal / arms-wide / mountain-reveal / fog-clearing / playful-action footage with **no Moment id forced**. Four planner calls; dry-run estimate ≈ $0.45 total (assumed 3k output tokens each; pricing table estimate), one call each, no 30-call sweep. Success criteria are the harness rows (shot median/mean/distribution, cuts, opening-10 s payoffs, type gap, valid, one call, latency) **plus owner video review**.
Matched arms are produced by §3.8 replay; the whole-request fingerprint is not used to judge equivalence, the component hashes are. Rendered MP4s need the app (§3.9) and are not frozen.

## 7. Owner decisions
Merged since: #124 and #126. Approved by the owner: bounded dev evaluation, replay mechanism, four matched attempts, `duration_recommendation/2` as a separate milestone. Pending: owner captures two dev jobs (§6), then four replay attempts; an optional dev pin for rendered MP4s; no beta promotion.

## 8. Separate Sizing milestone (`duration_recommendation/2`, not started)
Direction: Highlights duration from the number of distinct attractive opportunities (compact AU payoff windows from iOS `momentsPayload`), not Moment count; Full Story from meaningful narrative material; no per-Moment floor; no second mandatory inference call; Custom stays authoritative; no creative-only rejection. Needs a new prompt version, evidence plumbing in iOS and the backend, and its own test and evaluation.

## 9. Controlled replay results (2026-11-17; plan-level only, NOT quality-accepted)
Frozen requests captured from two real dev jobs (same Story, 38 Moments, 38 contact sheets, Original, no directives, critique off). Component hashes verified before each arm; both arms of a pair share one source hash (Highlights `36f7984f…`, Full Story `44e9fb4f…`). One planner attempt per arm, gpt-5.1 via the existing gateway, validator unchanged. Aggregates only; the frozen data stays local and is purged after review.

| | A 5.5 H 35s | B 5.6 H 35s | C 5.5 F 155s | D 5.6 F 155s |
|---|---|---|---|---|
| Model plan / fitted (s) | 50.5 / 42.0 | 54.6 / 54.6 | 204.4 / 182.6 | 205.3 / 189.1 |
| Segments / Moments used | 8 / 8 | 20 / 20 | 29 / 25 | 30 / 26 |
| Shot mean / median (s) | 5.25 / 4.46 | 2.73 / 2.90 | 6.30 / 4.97 | 6.30 / 5.40 |
| Shots ≤ 2.5 s | 12.5% | 30% | 6.9% | 6.7% |
| Distinct payoff Moments in first 10 s | 0 | 4 | 0 | 0 |
| Native audio keep / duck / mute | 5 / 3 / 0 | 5 / 12 / 3 | 15 / 14 / 0 | 13 / 16 / 1 |
| Model / repair calls, critique | 1 / 0, off | 1 / 0, off | 1 / 0, off | 1 / 0, off |
| Input / output tokens | 84,396 / 730 | 33,511 / 2,025 | 83,533 / 2,947 | 40,423 / 2,995 |
| System / user-text / AU-projection tokens (chars/4 ESTIMATE; see §14) | 2,960 / 51,078 / 49,641 | 1,294 / 6,527 / 5,644 | 2,960 / 50,656 / 49,333 | 1,294 / 12,732 / 11,916 |
| Planner wall time (s) | 18.4 | 22.0 | 32.2 | 26.1 |
| Est. cost (USD) | 0.113 | 0.062 | 0.134 | 0.081 |

Findings (deterministic): 5.6 Highlights cuts about twice as often (20 vs 8 shots) with a lower median shot and more distinct AU-payoff Moments in the opening, at 60% fewer input tokens. It did not reach the 1–2.5 s tendency (no shot ≤1 s; 14 of 20 shots are 2.5–4 s) and it overshot 35 s by 56%; the deterministic fit did not trim it (5.5 was fitted from 50.5 to 42.0). Full Story 5.5 and 5.6 are nearly the same edit shape; the type gap (Full median ÷ Highlights median) rises from 1.11 under 5.5 to 1.86 under 5.6, mostly from the Highlights side. Both Full Story plans exceed 155 s. Not measured: opening-shot quality, visual variety, near-duplicates, narrative event coverage, rendered MP4 durations. Those need video review. Output-token and latency numbers are single samples.

## 10. Why the 35 s Highlights plan was not fitted, and the bounded correction (2026-11-17)
**Confirmed from the saved diagnostics and the fitter code (no model call).** The fitter ran (target read as 35 s; 54.55 s is above the 38.5 s trigger), produced no proposal (`applied=false`, `trimmed=0`, `dropped=[]`) and so nothing was adopted or rejected; no validation failure, no directive protection (`protected_ids` empty, no directives), no payoff-core effect. The cause is the music-anchor rule: nothing at or before the last anchored shot may move. The request carried a tempo-only MusicAnalysis (bpm 105; `beats=[]`, `downbeats=[]`, no highlight window); the 5.6 Highlights strategy said "pace the cuts to the real beats", and the model set anchors on 13 of 20 shots including the last (index 19, `highlight`). All 20 shots were therefore locked. 5.5 set no anchors on the same request (its fit ran: 50.5 -> 42.0 s). This is a design gap, not a coding bug: the lock exists to keep cuts on a real beat grid, and here no grid existed.
Per-segment evidence for B (all 20 locked; the table was produced by the analysis script from the saved plan): 11 shots hold an AU payoff peak (protected core 1.6-2.4 s, trim slack 0-1.5 s each), 9 shots hold no payoff peak and were "optional" (2.0-3.3 s, slack 0-1.65 s). Without the lock the same plan fits to **37.87 s** (16 trims, no drops, still 20 shots, median 2.0 s, validator clean); the model's plan is unchanged. That is an offline simulation of the fitter on the saved plan, not a new model result.

**Correction (v5.6 only; 5.3/5.5 call and behavior unchanged):** (1) `fit_plan_duration(..., grid_aware_anchors=True)`: an anchor binds only when the MusicAnalysis really lists the structure it names; the report adds `anchors_binding` and `anchors_without_grid`. (2) The Highlights strategy says "set no music anchors" for a tempo-only track and "anchor only a few key cuts" when beats exist; the system prompt limits anchors to structure the analysis lists. (3) The shot-count hint ends at the mid-range shot length (35 s -> 14-20 shots, not 14-35) and the budget states that the shots must total about the target and that whole weakest shots should be removed when the total passes target x 1.1. (4) The over-length note for v5.6 is the measured difference only ("It runs about Xs instead of the requested Ys.") and no longer asserts that shortening would cut key moments. Items (2)-(3) are prompt text and are **unverified without a new model call**; (1) is deterministic and tested. Shared-fitter scope: 5.3/5.5 have the same lock whenever a model anchors against a MusicAnalysis without beat times; left unchanged, report only.

**Why shots are 2.5-3 s, not 1-2.5 s.** Of B's 20 shots, 11 have a payoff core of 1.6-2.4 s plus planner lead-in; the model chose source windows of 2.4-3.3 s, roughly a core plus 0.5-1 s of lead-in. Distinguishing a genuine hold from dispensable lead-in needs the video. The fitter trimmed that lead-in to a 2.0 s median in the simulation above. The range stays an advisory preference.

**Full Story D (189.1 s for 155 s).** The fit ran (205.3 -> 189.1 s, 10 trims, 2 drops) and stopped because every remaining shot overlaps an AU visual candidate (Full Story drops only unannotated filler) and only 13.8 s of trim slack remains outside complete-event cores, against 18.6 s needed to reach the band. This is protection by design, not a bug. The planner chose too much, so the lever is selection (strategy/sizing), not the fitter. 5.5's C ended at 182.6 s for the same reason.

## 11. Rendered previews and first-ten-second review
Four ffmpeg previews (not the product renderer; no music; native audio only, duck = -9 dB; 1080x1920 center-crop; no effects) were built from the dev cloud copies of the 30 source Moments used, plus B2 = the same model plan after the corrected fit. See `scripts/editorial_preview.py`. Private files live outside the repo (paths in the owner message); nothing is uploaded.
Highlights B opening (frames reviewed): shot 0 (0-1.9 s) wide hiker in a yellow jacket, poles up, Mont Blanc behind, a clear and attractive image; shots 1-2 (1.9-6.7 s) are the red-jacket subject with arms wide, one close from behind and one wide, so the second is close to a repeat of the first; shot 3 (6.7-9.7 s) is a tiny figure with arms up in a large gray cirque, with the payoff hard to read at this size; shot 4 (9.75 s) is a hiker crossing a stream and shot 5 a creek close-up. Four AU payoff Moments therefore occur early, but three are the same arms-up gesture and one is small in frame. Whether the opening is compelling is the owner's judgment; the evidence suggests the variety is partly in places, less in actions.
Full Story: both plans open on the gear/church context and end on a look back to camera (C: Mont Blanc farewell vista; D: seated look to camera). D is not clearly more coherent than C: both move through town, ridge, fog, summit-pose and evening blocks (the video, not this note, must show whether that order is real); D lists several consecutive arms-up/celebration shots (21-24) like C (17-19), and C repeats Moment fbb64608 and 6a51e809 as "echo/same pass" shots. Whether any progression is invented is not decidable without chronology metadata (separate milestone).

## 12. Highlights B3: one authorized rerun on the same frozen request (2026-11-17)
Same frozen request as A and B (all 14 component hashes equal the manifest; source hash `36f7984f…`), Original, Custom 35 s, critique off, current v5.6 prompt and corrected fitter, one attempt, one model call, no repair. Local replay arm `B3` (no worker job id; plan and diagnostics are in the private result file). Plan-level metrics, not quality acceptance.

| | B (first v5.6) | B2 (B's plan, corrected fit, offline) | B3 (new model plan, corrected fit) |
|---|---|---|---|
| Model plan before fit (s) | 54.6 | 54.6 | **44.2** |
| Fitted (s) | 54.6 (unfitted) | 37.9 | **35.0** |
| Shots / Moments | 20 / 20 | 20 / 20 | 18 / 15 |
| Shot mean / median (s) | 2.73 / 2.90 | 1.89 / 1.93 | 1.94 / 2.12 |
| Shots ≤ 2.5 s | 30% | 95% | 100% |
| Anchors set (binding / unsupported) | 13 (0 / 13) | 13 (0 / 13) | **0** |
| Fit trims / drops | none (locked) | 16 / 0 | 17 / 0 |
| Distinct payoff Moments in first 10 s | 4 | 4 | 3 |
| Native audio keep / duck / mute | 5 / 12 / 3 | 5 / 12 / 3 | 0 / 8 / 10 |
| Input / output tokens, wall, cost | 33.5k / 2.0k, 22.0 s, $0.062 | n/a (offline) | 33.6k / 1.8k, 24.6 s, $0.060 |
| Completion | partial | n/a | complete |

Reading: the planner improved before fitting (54.6 → 44.2 s, no unsupported anchors, fewer shots and Moments) but still planned 26% over the 35 s budget, so the fitter still carried 9.2 s (17 trims, none dropped). The wording change moved the model toward the budget; it did not make it select to the budget. Nothing is rejected or disclosed: the fitted 35.0 s lies in the band and completion is `complete`.
Visual review of B3 (frames; the owner decides): the first 10 s are a foggy slope reveal (no person), a hiker on a cloudy ridge, a hiker walking away on a trail, a tiny arms-up figure on a meadow, a distant paraglider and an empty ridge. These are varied but less human and less striking than B's opening; the yellow-jacket and red-jacket arms-up shots moved to 22-28 s and three celebration shots now run consecutively (V-pose, red jacket close, red jacket wide). One Moment (`6fc10d4c`) is used three times and `6fcdf1e0` twice. The ending is a quiet close-up of a face in a blue hood in whiteout: human and distinct, low energy. 10 of 18 shots are muted, so native sound is mostly absent. Preview is ffmpeg (not the product renderer).

## 13. Full Story: recorded limitation (no change made)
155 s requested; planner 205.3 s; fitted 189.1 s. Remaining shots are protected by AU candidate/complete-action rules (13.8 s trim slack against 18.6 s needed; no unannotated filler left to drop). This is an upstream selection and duration-allocation problem. A future Full Story strategy should select fewer, more meaningful scenes when the budget requires, instead of protecting an excessive set and trimming afterwards. The type-aware Sizing milestone complements this but does not by itself fix a Custom 155 s overshoot, because an explicit Custom duration stays authoritative and the planner must still select to it.


## 14. Owner review of B/B2/B3/C/D and the Highlights refinement (offline, 2026-11-17)
**Token-method correction.** The component rows in §9 and §12 (system / user-text / AU-projection) came from the replay child process, which had no tiktoken and so used a chars/4 estimate (recorded as `token_method`). The provider-reported input/output totals are exact and unaffected. With tiktoken on the saved prompts: A (5.5) system 2,644 / user 57,552 / AU 55,710; B (5.6) 1,169 / 8,086 / 6,678; B3 (5.6) 1,191 / 8,141 / 6,678. Run replay with the venv interpreter for exact splits.

**Owner decision.** B2 is the better creative reference; B3 hits the duration but has the weaker opening, with the strongest yellow/red-jacket footage at 22-28 s. Full Story D is not clearly better than C: both read as broad scenic travel edits with an atmospheric hiking section, not a structured personal story.

### First-ten-second comparison (frames reviewed; editorial observations, not scores)
| t (s) | B2 shot | Visible action | Notes |
|---|---|---|---|
| 0-1.7 | `8c43b8c9` src 4.11-5.8 (AU payoff, peak 5.36) | yellow-jacket hiker raises poles on a boulder, snowy range behind | clear action, strong sky/snow contrast, subject medium-small |
| 1.7-3.7 | `0bc5f375` src 0.35-2.4 (payoff) | red jacket from behind, arms raised, close | large subject, strong color; closest thing to a human hook |
| 3.7-6.1 | `c8b27de6` src 1.85-4.17 (payoff) | red jacket, arms spread, Mont Blanc behind | same gesture as the previous shot, wider |
| 6.1-8.6 | `6447f6d1` src 9.15-11.65 (payoff) | tiny figure, arms out, in a large meadow under a gray cirque | weak: figure is a few pixels; AU "payoff" overstates appeal |
| 8.6-10.8 | `59978263` src 0-2.2 (b_roll) | hiker crossing stream boulders | different action, low drama |

| t (s) | B3 shot | Visible action | Notes |
|---|---|---|---|
| 0-1.5 | `6a51e809` src 2.15-3.65 (AU role `opening`) | cloud sweeping a slope, peak above | atmospheric, no subject; muted |
| 1.5-3.0 | `4e9cc7f4` src 22.75-24.25 (payoff) | blue-jacket hiker on a cloudy ridge | clear, moderate impact |
| 3.0-5.2 | `6fc10d4c` src 2.83-5.07 (progression) | hiker walking away under cliffs | walking footage |
| 5.2-7.7 | `6447f6d1` src 8.87-11.3 (payoff) | the same tiny meadow figure as B2 | weak, now earlier |
| 7.7-9.4 | `6fcdf1e0` src 1.25-3.0 (establishing) | paraglider, tiny, over a glacier | scenic, hard to read |
| 9.4-11.7 | `cf6d09de` src 8.05-10.3 (payoff) | distant hiker on an empty ridge | scenic, small subject |

First 3 s: B2 gives a clear human celebration then a large red-jacket gesture; B3 gives a cloud slope then a distant hiker. First 6 s: B2 holds three strong human shots; B3 holds one moderate human shot and two walking/scenic shots. First 10 s: B2 has the tiny-figure weak spot and repeated arms-up gestures (shots 0-2); B3 has no shot of the footage owner called strongest. In both, "four AU payoff Moments in the first ten seconds" overstates appeal (the tiny meadow figure counts as a payoff in both). Stronger available footage for B3's early slots, by frames viewed: the yellow-jacket (`8c43b8c9`), red-jacket close (`0bc5f375`) and red-jacket wide (`c8b27de6`) shots, which B3 itself placed at 22-28 s as three consecutive celebration shots.

### Cause and change
In B3 the first shot was the only candidate tagged `opening` and the penultimate shot the one tagged `closing` (`7a4cf3ef`); B3's titles echo AU story-position labels ("opening", "establishing", "closing"). The image-led Highlights projection still carried those narrative-function roles. Change (v5.6 Highlights only, projection plus strategy):
1. Projection keeps only the neutral `payoff` tag per visual candidate; `opening`, `establishing`, `closing`, `progression`, `interaction`, `b_roll` are omitted (validation and the fitter still see the full Moment; Full Story keeps its roles).
2. Strategy rewritten, not stacked: judge by frames on visible impact (prominence, clarity, expression, movement, drama, composition, contrast, speed of payoff), the `payoff` tag and text only say where to look, a close gesture beats the same gesture as a tiny figure; open with the most striking shot clear within 2 s and put the strongest few shots in the first ~10 s; do not open on weather/walking/establishing footage unless it is the most striking available; vary the action, avoid back-to-back near-identical gestures but allow a repeat that shows something different; cut fast (1-2.5 s preference, no speed-ups); select for the budget. The old sentence "show several distinct payoffs within the first ~10 seconds" was removed because it invited counting AU payoff tags.
Highlights strategy length: 210 words before (no analysis) / 224 with a track; 244 / 258 now (+34), 289 tokens (was 275, tiktoken). Full Story strategy: byte-identical (hash pinned in tests). No new schema field, ranking JSON, model call or flag; system prompt unchanged.
Limit: this is a hypothesis about the label effect, not proven. Only a model run on the frozen request can show whether the model now leads with its strongest shot.

### Full Story (recorded, unchanged)
C (5.5) and D (5.6) both open on gear/church, move through town, forest, fog and panorama blocks, and group summit-pose shots; D has a long atmospheric hiking stretch. Neither reads as a structured personal story. Improvement path stays separate: reliable relative chronology, meaningful narrative selection, a stronger story thread, upstream duration allocation, natural-audio preservation. Making shots longer is not a fix.

### Prepared (not run): one frozen validation, arm B4
Same frozen Highlights request (`c2_1_highlights_35s`, source hash `36f7984f9087e130`, 14 components verified, 38 Moments, 38 sheets, Custom 35 s, Original, critique off, balanced sound, same tempo-only track, no directives). Command: `editorial_replay.py run --case <case> --arm B4 --version 5.6` using the venv interpreter; one attempt, one model call, a repair call reported separately, no reruns. Compare B4 with B2 and B3 on: first 3 s / 6 s / 10 s frames, strongest visible hook, action diversity in the first ten seconds, near-duplicate neighbors, median shot, pre/post-fit duration, model calls, tokens, latency, cost, and the ffmpeg preview. Estimated cost about $0.06. Needs owner approval; no Moment id is forced.

## 15. Highlights B4: the one validation run of the refined strategy (2026-11-17)
Same frozen request (source hash `36f7984f9087e130`, 14 components verified), commit `872c62f`, one attempt, one model call, no repair, critique off. Plan-level result, not quality acceptance.

| | B2 (B plan, corrected fit, offline) | B3 | B4 (refined strategy + roles dropped) |
|---|---|---|---|
| Model plan / fitted (s) | 54.6 / 37.9 | 44.2 / 35.0 | 51.4 / 35.65 |
| Shots / Moments | 20 / 20 | 18 / 15 | 20 / 18 |
| Median / mean shot (s) | 1.93 / 1.89 | 2.12 / 1.94 | 1.50 / 1.78 |
| Anchors set | 13 unsupported | 0 | 0 |
| Fit trims / drops | 16 / 0 | 17 / 0 | 16 / 0 |
| Input / output tokens, wall, cost | 33.5k / 2.0k, 22.0 s, $0.062 (B) | 33.6k / 1.8k, 24.6 s, $0.060 | 33.4k / 1.9k, 22.1 s, $0.061 |

Visual result (frames viewed): the first ~11 s are scenery with no person: cloud-covered slope (`6a51e809`, the same first shot as B3), sunbeams over a valley, a distant hiker on a ridge, tiny hikers, a paraglider, a panorama, an orbit. The yellow-jacket (`8c43b8c9`, t=11.3), red-jacket close (`0bc5f375`, 13.4) and red-jacket wide (`c8b27de6`, 15.3) shots begin at 11-17 s, earlier than B3's 22-28 s but still not an opening; the tiny meadow figure (`6447f6d1`) and a laughing turn follow. The ending is a 1.0 s shot of tiny hikers, a weak final image. B4 does not meet "strongest footage first": the strongest human footage is not in the first ten seconds, and B2's opening is still the better reference.
Reading: removing the story-position roles did not change B3's and B4's shared first pick (`6a51e809`), so the role-label hypothesis in §14 is at best incomplete. The first v5.6 prompt (B) produced the strong opening and the two later prompts did not, but each variant is one sample at one setting, so the differences cannot be attributed to the wording with confidence. No further model attempts were made.
Status: no dev pin, merge or deployment was performed. Open options, each needing owner approval: (a) accept B2's behavior as the reference and keep B's strategy text with the corrected fitter, accepting 20 shots and the repeated gestures; (b) an evaluation design with several samples per variant on the frozen request (a larger spend than authorized); (c) a deterministic, non-model hook rule, which the owner has so far declined because AU confidence does not measure appeal.


## 16. Decision: B2 is the Highlights reference; the original B strategy is restored (2026-11-17)
**Decision (owner).** B2 is the preferred Highlights reference; stop iterating on the Highlights prompt. Evidence behind it: B2 (37.9 s, 20 shots, median ~1.93 s) opens with the yellow-jacket celebration and follows with strong red-jacket shots; B3 hits 35.0 s but opens on a cloud slope with the best footage at 22-28 s; B4, after the visual-prioritization rewrite, opens on scenery for about 11 s. Each variant is a single sample, so the cause is not established.

**B2 is a saved plan, not a planner version.** It is B's model plan (repo commit `d4a6526`, frozen Highlights request, source hash `36f7984f9087e130`) after the corrected fitter. Its plan, shot metadata, B's exact prompts and the ffmpeg preview are kept privately under `/Users/lingzhang/Workplace/story-private-eval/v56-previews/` (no Moment ids are hard-coded in the product, nothing is added to production diagnostics, and a new model call is not expected to reproduce it).

**Observed B2 properties (visual reference, not a rule):** 37.87 s, 20 shots, median about 1.93 s, 95% of shots at or under 2.5 s; yellow-jacket poles-up shot first, then close and wide red-jacket arms-up shots; fast cutting; some repetitive arms-raised gestures and one weak tiny-figure shot.

**Restored (the code diff against `d4a6526` shows only the lines listed under "difference" below):** the Highlights strategy bullets, the Highlights projection (AU roles kept; confidence, evidence, narrative text and `sampled_frame_ms` stay omitted) and the budget block with its shot-count hint (14-76 shots for 90 s, i.e. target divided by 1 s, capped at 2 per Moment). The strategy is pinned by hash in tests (no-track hash `dd03d20b...`, identical to the B-time text). Rejected variants kept for the record: B3 (budget total/removal sentence, mid-range shot count, tempo-only music line) and B4 (rewritten strategy, roles stripped).

**Retained engineering (independent of creative wording):** grid-aware music anchors in the fitter; the tempo-only music instruction (no anchors); the system-prompt MUSIC sentence limiting anchors to structure the analysis lists; the neutral over-length disclosure; v5.6 user-direction rendering (directed Explore soft text, Original-with-Customize text); one planner call, no critique.

**Model-facing difference from historical B (documented):** exactly one user-message line changes when the track is tempo-only, from "Pace the cuts to the real beats of the supplied music analysis." to "Pace the cuts to the music plan's energy arc and tempo. The track analysis has no beat times, so set no music anchors.", plus one system-prompt MUSIC sentence. Checked by diffing the current prompt for the frozen request against B's saved prompt; every other line is identical. The restored request is therefore not byte-identical to B, and the saved B2 plan remains the reference regardless of future sampling.

**Compatibility results (offline).** Backend suite 1265 passed; v5.3 goldens and the v5.5 golden (generated from master `929a060`) are byte-identical; the Full Story strategy hash is pinned and unchanged; user opening, must-include and ordering directives are rendered and outrank the Highlights strategy; Original, directed Explore and Revise rendering is tested through the real worker path; no new schema, flag or model call; the fitter and validator are unchanged apart from the gated anchor correction; no iOS or renderer change. No model call was made in this task.

**Development activation and rollback (prepared, not deployed).** `release/release.json`: `planner.environment_overrides.development` is now `5.6` with a matching `approved_overrides` entry (expires 2026-11-30). The release gate accepts development and beta locally with a clean worker asset; the synthesized development template pins `STORY_EDIT_PLAN_VERSION=5.6` on both the API service and the worker, and beta has no pin (stays 5.3). Pending-job check: the dev queue is empty and all nine job rows are completed. The planner version is read per job inside the worker, so a deploy does not migrate jobs.

Steps that still need separate approval: (1) wait for CI on PR #127; (2) merge PR #127 into `master` (adds `prompts/edit_plan/5.6`, the planner changes and the pin; no default changes); (3) run `deploy-dev` after a no-job-in-flight check; (4) verify `STORY_EDIT_PLAN_VERSION=5.6` on the API service and worker (Lambda configuration and a completed job's `diagnostics.prompt_version` equal to `edit_plan/5.6`). Beta, gamma and production are never touched.

Rollback: one reviewed PR that sets `environment_overrides.development` and the `approved_overrides` value back to `5.5` (or removes both for 5.3), then `deploy-dev`. The entry expires on 2026-11-30, after which the gate fails until the pin is removed or renewed by the owner; it is not a permanent default.

**Remaining risks and device acceptance.** (1) 5.6 may not reproduce B2's opening: plans vary by run, and B3/B4 suggest the opening is sensitive to prompt and sampling. (2) The corrected fitter trims 16-17 shots to about 2 s; the product renderer's native/music mix, beat behavior and trim feel are untested. (3) The Highlights budget hint still suggests up to 76 shots for 90 s and 14-35 for 35 s; the fitter, not the hint, bounds duration. (4) Device acceptance should check quick-cut pacing, an immediate strong hook, soundtrack and native-audio behavior, duration near the target, no export or technical regression, and no dramatic departure from B2. Not promoted to beta.

**Full Story is unchanged.** Separate improvement path: reliable relative chronology, meaningful narrative selection, a stronger story thread, selective upstream duration allocation under a Custom target, and natural-audio preservation. Neither the strategy, the fitter nor shot length is changed here.
