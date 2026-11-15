# Editorial Pipeline vNext — Phase A report (read-only): Highlights vs Full Story

**Status: PHASE A (read-only design + owner-decision report), 2026-11-15, master `e339173` — ACCEPTED by the owner as the design baseline (decisions below).** Phase A itself changed no code, prompt, contract,
config, branch or deployment; beta and dev were read only.

Evidence sources: beta jobs `8f138425` (Highlights, Original) and `f9690044` (Full Story, **Explore**), the owner's beta
story doc (`story_doc/2`), 381 AU records, three stored AU evidence packs (viewed in scratch, deleted), the current
`master` source, and the specs `milestone-duration-reliability-and-provenance`, `proposal-chronology-metadata` and
`milestone-editplan-v54-prompt-evaluation`. "Inference" marks anything not directly observed.

## Owner decisions recorded (2026-11-15) — Phase A accepted as the design baseline

- **D1 approved:** the candidate is `edit_plan/5.5` (isolated; 5.3 unchanged; v5.4 not promoted; never auto-active).
- **D2 approved:** optional relative `chronology {rank, day?, source}` in its own later milestone (M3); backend must strip it from older versions (normal and repair
  requests) before any client emission; no absolute timestamps; do not use the current device timezone to infer the original capture day.
- **D3 approved with limit:** deterministic `diagnostics.selection` only. **No model-written omission rationales** until an evaluation shows a concrete need.
- **D4 approved:** remove the Highlights Moment-count floor and feed compact AU evidence into the existing single duration call (M2). No per-candidate minimum.
- **D5 approved:** internal Moment-ID aliases, in a separate reliability PR (M4), not mixed with the creative-prompt experiment.
- **D6 approved:** type-aware brief; Full Story keeps an editorial objective; one authoritative `editorial_type`.
- **D7 approved with limits:** offline first; the first live evaluation is four matched Original jobs; an Explore is never compared with an Original; stop and report.
- **D8 approved:** one short-lived branch and PR per milestone; M1 branch `feat/editorial-vnext-m1`.
Implementation record for M1: [milestone-editorial-vnext-m1-editplan-v55](./milestone-editorial-vnext-m1-editplan-v55.md).

## 0. Corrections to what I told you earlier in this thread

1. I said I rebuilt "what the planner sees" with the code's own renderer `_editorial_evidence_lines`. **That function is
   never called.** Only its unit test references it. The planner actually receives each Moment's editorial block as JSON
   inside `INPUT.moments[]` (visual/narrative candidates without the `evidence` string, plus `events` and
   `sampled_frame_ms`). The text I showed was the right *content* in the wrong *shape*.
2. I attributed the omission of `b0c69213` to near-duplicate filtering. The frames do not support that (§5).
3. The 5.3 `system.md` header comment still says 5.2; the live prompt is 5.3 (env + job `prompt_version`).

## 1. Verified beta comparison

| | Highlights `8f138425` | Full Story `f9690044` |
|---|---|---|
| Operation | **Original** | **Explore** ("Create another version") of the Highlights output |
| `editorial_type` / legacy mode | highlights / highlights | full_story / full |
| Target (source) | 90 s = midpoint of `highlights_range [80,100]` | 155 s = midpoint of `recommended_range [140,170]` |
| Planned before fit | 158.6 s (25 shots, mean **6.34 s**) | 172.4 s (30 shots, mean **5.75 s**) |
| Delivered | 128.7 s (24 shots, mean 5.36, median 4.77) | 156.0 s (29 shots, mean 5.38, median 4.80) |
| Fit | applied, 1 drop, `over_band_after_fit`, status `partial` | applied, 1 drop, `fitted`, `complete` |
| Calls / latency | 1 call, 22.9 s | 2 calls (repair), 45.7 s |
| Tokens in/out | 76.7k / 2.2k | 136.6k / 5.5k |
| Sheets | 35/35, reconciles | 35/35, reconciles |
| Native audio | 15 keep / 9 duck | 22 keep / 7 duck |
| Music anchors / transitions | none / none | none / none |
| Build | API+worker `72e9e07` | same |

Findings from this table:
- **Pre-fit, Highlights shots were longer than Full Story shots (6.34 vs 5.75 s).** The identical 5.37/5.38 s means are
  largely produced by the deterministic fitter trimming Highlights harder. Nothing in the planner output makes Highlights
  brisker.
- **The Full Story job is not a clean baseline.** It was an Explore, so it received the VERSION CONTEXT block
  ("produce a MEANINGFULLY DIFFERENT… alternative… different opening, ordering or source-range emphasis") plus a summary of
  the Highlights plan. Any evaluation must compare like with like (both Original, or both Explore).
- Sound differs only modestly by type (kept audio on 63% of Highlights shots vs 76% of Full Story shots): both inherit the
  user's *balanced* preference and the type directives say nothing about sound.
- Both runs: 24/29 shots and 23/28 distinct Moments out of 35.

## 2. Active prompt analysis (v5.3, what the model reads)

System prompt (`prompts/edit_plan/5.3/system.md`, shared by both types) contains, in tension:
- "`highlights` = favor the STRONGEST material… fewer, higher-value Moments" (editorial mode clause).
- "CREATIVE FREEDOM OVER PACING… when the footage offers lots of distinct material… **favor BREADTH — more distinct shots,
  each shorter**… visual variety is itself a reason to include a shot **even when its action is ordinary**."
- "DURATION DISCIPLINE… ±20% is a hard feasibility tolerance" (runtime policy is non-blocking; fitter exists since #103-105).
- Repair prompt tells the model overshoot up to +50% is acceptable (duration milestone §1).

User message adds, in order: `CREATIVE DIRECTION` brief → VERSION CONTEXT → VISUAL EVIDENCE → sound directive →
**legacy `EDITORIAL MODE` line** → **`EDITORIAL TYPE` directive** → JSON INPUT. So Highlights receives three overlapping
breadth instructions (system mode clause, legacy line, type directive) and Full Story the same three.

The most consequential item: **`MM_CREATIVE_BRIEF`** (`apps/api/app/main.py:179`, mirrored in iOS
`StoryMultimodalPlanning.creativeBrief`) is sent for *every* multimodal create, including Full Story:
"When user intent does not require chronology, prioritize visually engaging and meaningful footage. Find a compelling
opening… Do not force a conventional travel-diary structure." That is a Highlights instruction. It tells Full Story that
chronology is optional and to open on the most compelling footage.

The Highlights type directive already asks for "strongest visual payoffs… attractive compositions… SELECT the best
available footage". It never tells the model to *compare similar clips*, to open on a payoff, how many shots a target
implies, or what pace to use. The system prompt's breadth clause outweighs it in practice (24 of 35 Moments used).

## 3. Actual routing and duration sources

- **Type routing is sound.** iOS resolves one `pendingEditorialType` per attempt (`StoryCreationCoordinator.swift:546`,
  Explore inherits parent type, persisted for resume); #112 records it on the job. Both jobs carry matching
  `editorial.requested/effective` and legacy mode. Revise base inheritance: `nil` only for a legacy base (line 576).
  No type/duration/operation coupling bug found in these jobs. Risk: the legacy `editorial_mode` is still sent beside the type.
- **Sizing (P1-D)**: the stored `duration_rec` shows `highlights_range [80,100]`, `recommended_range [140,170]`, ceiling
  439.4 s, `uncertain: true`. So 90 s was a genuine Highlights recommendation, not a persisted Custom or an inherited
  Explore target (`duration_choice_explicit = recommended`, no explicit target). It comes from one model call that sees
  only `n_moments=35`, total useful seconds 439.4, longest span 89.8 s and a feasible band of **[70, 439.4]**.
  The band floor is `n_moments × 2 s`, so **the Highlights floor grows with Moment count** (35 Moments ⇒ 70 s). It receives
  no AU candidate or payoff data. The same Story has 21 payoff-role visual windows totalling 99.2 s.
- **Fitter (#103–#105, merged)**: works as designed: protects every AU payoff peak, never drops opening/ending/directive
  Moments, drops only no-payoff optional shots. It cannot rescue a plan that selected 13 payoff-bearing shots too many.
  No concrete defect found in it, so §8's "do not change the fitter" holds. The overshoot is upstream.

## 4. Root causes (evidence-ranked)

1. **Shared Highlights-style creative brief on Full Story** (code-verified).
2. **Breadth-favoring system prompt + three overlapping mode instructions** (code-verified); consistent with Highlights
   using 23 of 35 Moments (inference for causation).
3. **No upstream duration arithmetic**: the model is told "plan to the target" with no shot-count/pace guidance, and
   proposes +76% (Highlights) / +11% (Full). The fitter then masks it. (observed)
4. **No comparative-selection step** and no keep/drop trace (§5, §13).
5. **No trustworthy chronology** reaches the planner (§9) while Full Story's brief says chronology is optional.
6. **Highlights opens on ordinary footage** because nothing asks for a payoff-first hook; both videos open on
   `70510a4b` ("dawn village"), which was captured **20th of 35** (mid-trip).
7. Explore context biases the Full Story run (§1).

## 5. Red-jacket findings (frames viewed, 8 of 24 evenly spaced frames per Moment)

Matched by AU text to my viewing; my judgement is subjective and unscored.

| Moment | What the frames show | Plan use |
|---|---|---|
| `b0c69213` (7.8 s, capture rank 30) | Close, large red jacket, arms thrown wide against sky and rocky peaks, then a profile looking up. Highest subject prominence and color contrast of the three. | **Omitted in both** |
| `9f0e6e90` (6.4 s, rank 29) | Wide Mont Blanc panorama, arms spread, saturated blue sky and snow. Strongest scenic composition. | Used both (Highlights: last shot) |
| `e10209e6` (15 s, rank 24) | Small figure on a hazy meadow, arms up then hands behind head. Visually the weakest of the three. | Used both ("primary emotional summit beat") |

- The omitted clip is **not weaker**; the planner kept the weakest of the three over it in both plans. The planner is
  **not comparing appeal**. It is not near-duplicate filtering either: Full Story placed two arms-raised clips back to back.
- Why `b0c69213` lost cannot be proven: no omission record exists. AU gives it a payoff candidate (0–3 s, conf 0.90) and
  narrative 0–7.5 s; `e10209e6` has the same confidence band. AU confidence does not separate them (payoff confidences
  across the Story range 0.80–0.95, median 0.93).
- No change should hardcode this Moment. Acceptance is on selection quality across the Story (§17).

## 6. P0 — Highlights strategy (proposal; one coherent policy, version-isolated)

Delivered as a **single new planner prompt candidate** (`edit_plan/5.5-cand`, name is the owner's call; 5.3 stays live and
unchanged during baseline; v5.4 not reused). The policy replaces the conflicting clauses instead of stacking:

1. **Type-specific system section.** Keep the 5.3 executability invariants verbatim. Replace the shared breadth/pacing
   paragraph with two short per-type policies selected by `editorial_type`; delete the legacy `EDITORIAL MODE` user line
   when a type is present; reword duration discipline to "aim within ±10%; a playable plan is never rejected".
2. **Comparative selection (no extra call).** Highlights directive instructs: group the candidates by action/location; from
   each group keep the one whose *visible frames* show the strongest outcome (subject prominence, expression, composition,
   color/contrast, motion, scenic drama), keep a second only for a genuinely different action; AU confidence is
   not appeal; if the frames contradict an AU peak, trust the frames (IMG_9091 behavior preserved).
3. **Payoff-first hook.** "Consider opening on the most arresting visible payoff; do not open on arrival/town/packing/walking
   footage unless it is itself arresting; explicit opening directives always win."
4. **Deterministic budget hint (advisory, computed server-side from type + target, no model).** e.g.
   `budget: {target_s, typical_shot_s: [3,5] for highlights | [5,9] for full_story, suggested_shots: [lo,hi]}` with
   "a payoff or continuous action may exceed this". For 90 s Highlights this suggests ~18–26 shots, not 25 at 6.3 s.
5. **Pacing differs by tendency, not quota**: Highlights starts payoffs at the action and skips lead-in; Full Story keeps
   complete actions and context inserts. The fitter stays as the safety net.

Decision sequences from §9–§10 of the brief map onto this without a second LLM call. Anything needing a plan-output field is
isolated in §13.

## 7. P0 — Pacing and upstream duration

- Proposal in §6.4 attacks the root (selection volume) before the fitter. Expected: Highlights plans closer to target,
  fewer fitter edits. Target-adherence tolerance for Full Story stays looser (fitter already trades it for complete actions).
- **Sizing defect to decide on (P1-D)**: `floor = n_moments × 2 s` couples the Highlights band to Moment count, and the
  recommender sees no payoff/candidate data. Options in §12.

## 8. P0 — Evidence completeness

Verified: 35/35 eligible Moments sheeted, `evidence_funnel_consistent`, 0 cut-without-sheet, cache/extraction policy fields
present. **Not verifiable** from jobs: per-sheet frames/tier/bytes and the actual images sent (staging is deleted by design).
This is the diagnostics gap in §13, not a P1-F defect, so the accepted P1-F design is not reopened.

Additional defect found: both recent beta jobs that needed a repair call did so for a **mistyped 36-character Moment id**
(`…C55DD…` for `…C55DC…`; earlier job: an id that mixes two real ones). Each repair costs a call and ~15–25 s. A backend-only
internal alias (`M01…M35`, mapped back after parsing) would remove this class; it touches planner I/O, so it needs approval.

## 9. P1 — Chronology (smallest backward-compatible change)

Measured on this Story: all 35 `moment_refs.captured_at` are present (source `existing_media`, i.e. embedded file metadata),
spanning 2026-09-06…09-12 (about six calendar days, tz-dependent). Kendall τ(import/sheet order, capture order) = **−0.04**.
Plan order vs capture: Highlights +0.37, Full Story +0.26, so Full Story is barely chronological. Both open on a Moment
captured 20th of 35, with roles such as "establishes basecamp".

The existing proposal stands unchanged: relative `chronology {rank, day?, source}` per Moment, only for known valid capture
times, never from import/upload/restore time, never reorder `moments[]`, directives/storyboard outrank it.
- **Contract impact:** none on the backend schema (`moments` items are free-form dicts; `extra=forbid` is top-level only).
  Needs a **version-scoped planner gate** and the rollback projection extended in `_sanitize_moment` and the repair payload
  (`packages/edit_planner/__init__.py` ~1360 and ~1664). Ship backend before the client emits. No feature flag.
- **iOS:** one shared helper + emission in `RenderSupport.swift` (`EditPlanRequestBuilder.build`); fix G4 (restore must fill a
  nil local `capturedAt`) and the stale model comment.
- Per the brief: this is a request/prompt-version change, so **stop for approval before implementing** (decision D2).

## 10. P1 — Full Story narrative

Grounded in AU events, narrative candidates, chronology rank, Guide and Coverage. Rules in the Full Story policy: follow
chronology by default when ≥2 Moments carry it; establish thread from observed events (no assumed departure/return from
town footage); give meaningful actions continuous time; keep contextual inserts that add meaning; avoid repeated shots unless
they add something; no required arc. Coverage already says `scene_01` ("preparation") is `unknown` for this Story, so the
planner must not invent a start.

## 11. P1 — Sound

Keep user preference authoritative. Add to the per-type policies only: Highlights "keep original sound for payoffs/reactions,
otherwise music-forward"; Full Story "prefer keeping complete natural-audio sequences". No transcription, no new model,
AU event edges are not treated as audio-safe cuts. Music anchors are `none` in both jobs, so music-aware pacing cannot
be evaluated until `MusicAnalysis` is present; flagged as a limitation, not changed.

## 12. P1 — Sizing

1. Remove the count-based floor from the **Highlights** recommendation (keep a small absolute minimum), because the brief
   forbids "more Moments ⇒ longer Highlights".
2. Pass compact deterministic AU facts to the existing recommender call (no new call): payoff-window count/seconds,
   distinct narrative events, longest continuous action. Highlights ← payoff density; Full Story ← events + continuous actions.
3. Keep explicit Custom independent (already persisted separately). This is a `duration_recommendation/1` input change plus a
   frozen-prompt wording decision, so needs approval (D4).

## 13. P1 — Selection diagnostics (proposal)

Deterministic, no model, privacy-safe, stored in `diagnostics.selection`:
`{used: [{alias, range, out_s, payoff_overlap}], unused_with_payoff: [{id, best_candidate_role, conf, dur}],
 budget: {target, planned, delivered, hint}, sheets: {tier, frames_per_moment, bytes}, fit: {...}}`.
Optional model-side rationale needs a new optional output field (`editorial_notes.omitted[{id,reason}]`) in the planner tool
schema only (not `edit_plan/2`), labeled diagnostic, bounded length. Needs approval before the schema/prompt change (D3).
No raw images stored.

## 14. Files expected to change (after approval)

Backend: `packages/edit_planner/__init__.py` (version gate, per-type directives, budget hint, sanitize/repair projection, optional
alias map, optional notes), `prompts/edit_plan/<new>/system.md` (new, isolated), `apps/api/app/main.py` (brief becomes type-aware),
`packages/duration_planner/__init__.py` + `prompts/duration_recommendation/` (P1-D, if approved), `apps/api/app/worker.py` (diag).
Tests: `apps/api/tests/test_edit_plan_v53.py`, `test_edit_planner.py`, `test_edit_plan_duration_fit.py`, new selection/chronology tests.
iOS: `RenderSupport.swift` (chronology), `StoryMultimodalPlanning.swift` (brief), `StorySyncCoordinator.swift` (G4),
duration request payload, plus XCTest. CDK/env: none.

## 15. Compatibility

Version-scoped prompt candidate (rollback = unset the version env, existing mechanism); all new request keys optional and
dropped under older versions; old/new client × old/new backend matrix covered by the projection fix shipping first; no change to
stored outputs, Original/Revise/Explore semantics, or pending jobs.

## 16. Branch/PR conflict assessment

Open PRs: #84 (CDK OIDC), #79 (billing doc), #44 (org IaC): no overlap with planner/iOS files. Merged duration work #103–#105 and
#121 (critique off) are the base. Worktrees `story-wt-p1a-semantics`, `story-wt-p0-evidence`, `story-wt-observability` are older
feature branches and were not touched; check `feat/editorial-p1a-semantics` for overlap before editing `EditorialType`/AU files.
Master has only the owner's untracked `xcodecloud/` folder.

## 17. Evaluation plan (small, no bake-off)

Same TMB 35 Moments, **both types as Originals** (and one Explore pair separately), baseline v5.3 vs candidate, 2 runs each,
plus fixtures: girl-with-dress, Egypt interactions, a scenic/static set, a no-chronology set, a directive set. Judge **rendered
videos** with the owner. Record for each: opening quality, payoff visibility, strongest-of-group choice (the three red-jacket
Moments as a regression group, not a pass/fail), mean/median/IQR shot length, duration error, shots/Moments used, calls,
latency, tokens, cost, sheet coverage, fitter changes, narrative coherence and τ vs capture (Full Story).

## 18. Acceptance criteria

- Highlights: pre-fit total within ±25% of target (baseline +76%); fewer Moments than Full Story on the same Story; median
  shot shorter than Full Story's by a visible margin; opening on an arresting payoff in the owner's review; owner prefers
  Highlights over baseline in a blind pair.
- Full Story: τ vs capture ≥ 0.6 when chronology exists; no invented departure/return; ≥ as many complete actions as baseline;
  owner prefers it over baseline.
- Both: 0 new validation failures, no added mandatory calls, repair-call rate not worse (alias change should lower it),
  p50 latency not worse than baseline by more than ~20%, tokens ≤ +10%, same-or-better input cost.
- Never reject a playable plan for editorial shortfall; partial notes stay truthful.

## 19. Milestones and dependencies

M1 prompt-consistency + type-aware brief + budget hint + comparative selection + per-type pacing (P0, one PR, new isolated
version) → M2 diagnostics (`selection`, optional notes) → M3 chronology (needs D2; backend gate first, then iOS) →
M4 sizing (needs D4) → M5 evaluation and owner acceptance → M6 promotion decision. M1 and M2 are independent of M3/M4; M3 depends
on M1's version gate.

## 20. Decisions required from the owner

- **D1.** Approve one new isolated planner version (name?) as the vehicle for M1, with 5.3 untouched as baseline.
- **D2.** Approve the additive `chronology {rank, day?, source}` request key and its version gate (frozen-contract boundary).
- **D3.** Approve diagnostics: deterministic `selection` block now; optional model `editorial_notes` (new tool-schema field) yes/no.
- **D4.** Approve changing Duration Intelligence inputs and removing the Moment-count floor for Highlights.
- **D5.** Approve the internal Moment-id alias (removes repair-call typos; touches planner I/O).
- **D6.** Make the creative brief type-aware (drop it for Full Story) as part of M1, or leave it.
- **D7.** Evaluation: both types as Originals on the TMB Story; OK to run live dev/beta planner calls (about 30 calls).
- **D8.** Branching: one branch off `origin/master` per milestone, each its own PR, no worktrees; confirm.

## 21. Not verified

Rendered videos (only plans); exact sheet frames and quality sent; why the model omitted `b0c69213`; the app commit on the
device (`unknown`); per-call latency within a job; effect of any proposed change.
