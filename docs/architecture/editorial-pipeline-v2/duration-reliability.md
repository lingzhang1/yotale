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

Runs after the plan is valid (and after critique), before completion/disclosure scoring, for Original and
Explore (Revise is exempt — it preserves the base edit). Trigger: DELIVERED total (Σ output durations — what the
device renders; stripped crossfades are never subtracted) > target +10%. Aim: the target. Within-band and short
plans are returned unchanged (undershoot is reported, never extended).
1. **A — literal repeats**: a later segment ≥80% covered by footage an earlier kept segment of the same Moment
   already shows. Separate actions from one Moment and re-cuts the planner labels as a callback/reprise/echo/
   bookend/recap/motif/mirror/refrain/again are kept.
2. **B — slack trim, two passes**: shots longer than the plan's median absorb the cut first; shorter shots only if
   still needed. Each trim cuts lead-in/tail away from the protected core and keeps at least half of the planned
   shot. Core = AU payoff peak ±1.25 s, widened to the whole containing AU event for Full Story and for kept native
   audio; a kept-audio shot without a payoff keeps its main AU event.
3. **C — optional drops** (only if still > +10%): shots with no AU payoff, least valuable first (no visual-candidate
   overlap → non-kept audio → longest first). Full Story drops only unannotated filler (no visual-candidate overlap).

**No minimum shot length.** The previous 2.0 s floor is gone; a planner shot is never lengthened, a short shot is
never rejected, and the validator is unchanged. The only trim limits are the protected core and RETAIN_FRACTION
(0.5 of the planned shot), both relative to the planner's own choice.

Never: drop the opening/ending shot or any directive-referenced Moment (opening/ending/must_include/ordering/
adjacency — trimmed only); change anything at or before the last music-anchored segment (keeps anchored cuts on
the beat grid); change speed/native_audio/transition type/relative order; move a range outside the original.
**Adoption gate:** shipped only if `validate_plan` passes and creative satisfaction does not drop; otherwise the
original valid plan ships and `diag.duration_fit` reports `adopted:false`, `after_s == before_s`, no changes, and
the rejected proposal under `proposed`. A cut still > +10% after the fit ships with `completion: partial` and a
plain-language note ("It runs about 66s instead of the requested 50s — shortening it further would cut key
moments."); `material_unmet` carries `approx_duration` for diagnostics. `diag.duration_fit` lists every range
change (`changes[]`: order, asset, from/to) and every drop (`dropped[]`: order, range, planned length, reason).

Arithmetic: `validate_plan`'s `_duration_delta_fraction` now uses the delivered Σ output durations (the contract
strips transitions). `timeline_total_seconds` keeps its overlap arithmetic for iOS-authored dissolves, which the
renderer does play.

## 4. Replay of the fit on every saved plan (offline, deterministic — not rendered-quality evidence)

| Group | n | Before (mean / max) | After (mean / max) | Outside ±10% after |
|---|---|---|---|---|
| Highlights (Original) | 8 | +38% / +51% | +1.0% / +6% | 0 |
| Explore Highlights | 8 | +33% / +43% | 0% / 0% | 0 |
| Full Story (Original) | 8 | +36% / +65% | +9.1% / +31% | 2 (disclosed) |
| Explore → Full Story | 6 | +46% / +74% | +10.0% / +25% | 3 (disclosed) |
| Runtime plans (2×50 s, 2×16 s) | 4 | +20% / +46% | +5.6% / +20% | 1 (disclosed) |

All 34: 33/34 outside ±10% before → 6/34 after (all Full Story or payoff-only cuts, each disclosed); 0 new
validation errors; every AU payoff still on screen. Full Story deliberately trades target adherence for complete
actions and annotated context. Rendered quality is NOT claimed until device acceptance.

## 5. Provenance (identifies the code that ran, not a deploy label)

- `api_build_sha` / `worker_build_sha`: read by `observability.build_sha()` from a `BUILD_SHA` file baked INTO the
  artifact at build time — API image: `Dockerfile` `ARG BUILD_SHA` (deploy workflows pass the commit being built);
  worker zip: `scripts/build_worker_asset.sh` writes `git rev-parse --short=12 HEAD`, suffixed `-dirty` when the
  packaged backend sources differ from the commit. "unknown" when an artifact carries none. No environment
  variable or CDK change.
- `prompt_version`: the worker's loaded planner module (`edit_plan/5.3` today) — the prompt actually used.
- iOS `build_provenance.selection_policy` (`evidence_select/2`), separate from AU `frame_policy`; the backend stores
  the dict verbatim.
- iOS `commit_sha`: `Info.plist GitCommitSHA = $(GIT_COMMIT_SHA)`; `project.pbxproj` pins `GIT_COMMIT_SHA = unknown`
  at target level (xcconfig cannot override). Xcode Cloud: `apps/ios/Story/ci_scripts/ci_pre_xcodebuild.sh` stamps
  `CI_COMMIT`. CLI: `xcodebuild … GIT_COMMIT_SHA=$(git rev-parse --short=12 HEAD)`. **Local Xcode GUI builds:**
  needs a Run Script build phase on the Story target, placed after "Process Info.plist", running
  `/usr/libexec/PlistBuddy -c "Set :GitCommitSHA $(git -C "$SRCROOT" rev-parse --short=12 HEAD)" "$TARGET_BUILD_DIR/$INFOPLIST_PATH"`
  (with `-dirty` detection), with `ENABLE_USER_SCRIPT_SANDBOXING = NO` for that phase or declared input/output
  files — a `project.pbxproj` edit, deferred until the owner's uncommitted pbxproj work lands.

## 6. Remaining limitations

- Trim decisions use AU hints (peaks/events/candidates), not pixels; a real payoff outside its AU window can be
  shortened (the same advisory evidence the planner uses).
- Undershoot is not corrected. Full Story may stay above +10% by design (disclosed).
- The system prompt's "±20% hard tolerance" / crossfade-overlap wording and the repair prompt's "+50% acceptable"
  are unchanged (no prompt change in this milestone).
- Deliberate-repetition detection relies on the planner's `narrative_role` wording for overlapping re-cuts.
