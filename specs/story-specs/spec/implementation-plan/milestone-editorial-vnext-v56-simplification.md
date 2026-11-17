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
