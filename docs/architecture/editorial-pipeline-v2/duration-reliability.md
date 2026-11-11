# Duration reliability — deterministic post-plan duration fit (+ planner provenance)

Status: implemented on `fix/editplan-duration-reliability`, NOT merged/deployed. Prompt stays edit_plan/5.3;
no model routing, prompt-version or feature-flag change; no new model calls.

## 1. Lifecycle audit (where the overshoot comes from)

| Stage | Code | Effect on length |
|---|---|---|
| Customize duration / recommendation | iOS Customize + `duration_recommendation/1` (feasible band, highlights 45–55 s) | sets `creative_intent.target_duration_seconds` (TMB: 50) |
| Request | `RenderSupport.swift` `EditPlanRequestBuilder.creativeIntentPayload` | target serialized verbatim |
| Prompt | `prompts/edit_plan/5.3/system.md` DURATION DISCIPLINE ("±20% is a hard feasibility TOLERANCE") + payload target | model told to aim at target |
| Model output | segments with `output_duration_seconds` | **overshoot originates here** |
| Validation | `validate_plan` | duration NEVER blocks (owner 2026-10-25) — only `_duration_delta_fraction` diagnostic |
| Objective scoring | `assess_creative_intent` | approx-duration objective counts as satisfied whenever soft mode is on |
| Repair prompt | `_build_repair` | tells the model overshoot "up to +50%" is acceptable |
| Contract | `_to_contract` | **drops every transition** (`transition=None`) → straight cuts |
| iOS refinement | `CreativeRefinementV2b` | never changes output durations; but refuses to run when total is outside ±20% of target |
| Timeline / render | `MediaEngineV1` | renders Σ output durations (+ beat-snap ±0.15 s on anchored cuts) |

**Root cause:** nothing after the model pulls an over-long but valid cut back toward the target — the
validator, the objective scorer and the repair wording all accept it — and the renderer reproduces the planned
length faithfully. Side effects: an over-±20% plan also silently skips iOS creative refinement; and
`timeline_total_seconds` subtracts crossfade overlaps that never render (the contract strips transitions), so
its diagnostic understates the delivered length whenever the model emits crossfades.

## 2. Planner vs rendered duration (CONFIRMED runtime, dev Story TMB Hiking)

| Output | Target | Plan Σ | Rendered | Plan vs target | Render − plan |
|---|---|---|---|---|---|
| 88BE8992 (original) | 16 | 19.43 | 19.433 | +21% | +0.003 s |
| 60434A62 (explore) | 16 | 23.30 | 23.300 | +46% | 0.000 s |
| E00179C3 (explore) | 50 | 49.65 | 49.740 | −1% | +0.090 s |
| 0EA53C3D (explore) | 50 | 57.56 | 57.585 | +15% | +0.025 s |

The overshoot is in the planner output and the validated plan; timeline and file match it (no crossfades).
REPLAY-based (reconstructed inputs, 30 runs): v5.3/v5.4 +19…+74% over a 50 s target.

## 3. Correction: `packages/edit_planner/duration_fit.py` (engine step 6c)

Runs after the plan is valid (and after critique), before the completion/disclosure scoring. Trigger: delivered
total (Σ output durations — what the device renders) > target +10%. Aim: the target.
1. **A — redundant re-cuts**: drop a later segment of a Moment already in the edit when ≥50% of it repeats
   footage an earlier kept segment shows, or it holds no AU payoff of its own.
2. **B — proportional slack trim**: shrink each segment's source range away from its protected core: the AU
   visual-candidate peak ±1.25 s, widened to the whole containing AU event when the segment keeps native audio
   or the type is Full Story (complete actions); floor 2.0 s; never outside the original range.
3. **C — optional low-value drops** (only if still > +10%): segments without an AU payoff, lowest value first.

Never: drop the opening/ending segment, drop a directive-referenced Moment (opening/ending/must_include/
ordering/adjacency — trimmed only), touch a music-anchored segment, change speed/native_audio/order semantics,
extend or invent footage (undershoot is reported, never "fixed"). Revise is exempt (preserves the base edit).
**Adoption gate:** the fitted plan ships only if `validate_plan` passes and creative satisfaction does not drop;
otherwise the original valid plan ships. If the cut is still > +10% after the fit, the video still ships and
`material_unmet` gains `approx_duration` (honest partial disclosure). Diagnostics: `diag.duration_fit`
(before/after/target, trimmed, dropped + why, adopted) — persisted on the job item by the worker.

## 4. Replay of the fit on every saved plan (offline, deterministic)

| Group | n | Before (mean / max) | After (mean / max) | Outside ±10% after |
|---|---|---|---|---|
| Highlights (Original) | 8 | +38% / +51% | 0% / 0% | 0 |
| Explore Highlights | 8 | +33% / +43% | 0% / 0% | 0 |
| Full Story (Original) | 8 | +36% / +65% | +1.7% / +9% | 0 |
| Explore → Full Story | 6 | +46% / +74% | +2.2% / +8% | 0 |
| Runtime plans (2×50 s, 2×16 s) | 4 | +20% / +46% | +6.7% / +20% | 1 (60434A62: 6 payoff shots, disclosed) |

All 34: 33/34 outside ±10% before → 1/34 after; 0 new validation errors; every AU payoff peak still on screen
(drops were only repeated footage). Side-by-side frame review: runtime 1408674a keeps all 10 shots (incl. the
#2 smile payoff) with lead-ins/tails shaved; a 15-shot Full Story loses only two literal re-cuts of #17/#24.

## 5. Provenance

- `commit_sha: unknown`: `Info.plist GitCommitSHA = $(GIT_COMMIT_SHA)`, and the project pins
  `GIT_COMMIT_SHA = unknown` at target level (`project.pbxproj`), which no xcconfig can override; no build phase
  populates it. Fix here: `apps/ios/Story/ci_scripts/ci_pre_xcodebuild.sh` stamps the real commit in Xcode
  Cloud (no pbxproj change). Local CLI builds: pass `GIT_COMMIT_SHA=$(git rev-parse --short=12 HEAD)`. Local
  Xcode GUI builds stay "unknown" until a Run Script phase is added — needs a pbxproj edit, deferred until the
  owner's uncommitted pbxproj work lands.
- Selection policy: `build_provenance.selection_policy = "evidence_select/2"` (iOS), separate from
  `frame_policy` (AU extraction). Backend stores the dict verbatim — no backend change.
- Planner revisions: job diagnostics gain `prompt_version` (effective, from the worker's planner module),
  `worker_build_sha` and `api_build_sha` (from `STORY_BUILD_SHA`, set by CDK from `-c buildSha=${GITHUB_SHA::12}`
  in both deploy workflows; "unknown" until the next deploy). No raw sheets or user content are logged.

## 6. Remaining limitations

- Deterministic trimming uses AU payload hints (peaks/events), not pixels; a shot whose real payoff falls
  outside its AU peak window can lose part of it (same advisory evidence the planner already uses).
- Undershoot is not corrected (no footage is invented or extended).
- The system prompt's "±20% hard tolerance" and the repair prompt's "+50% acceptable" wording are unchanged
  (prompt changes need a proposal); the deterministic fit makes them moot for the delivered length.
- `timeline_total_seconds` still subtracts crossfades for its own diagnostic; delivered length uses Σ output.
