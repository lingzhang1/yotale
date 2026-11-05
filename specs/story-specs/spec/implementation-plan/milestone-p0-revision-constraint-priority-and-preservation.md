# P0 — Revision Constraint Priority & Preservation-Safe Fallback

**Status:** IMPLEMENTED (backend + iOS) + automated tests, DEPLOYED to dev, awaiting device acceptance. STOP at device gate.
**Owner decision date:** 2026-10-18
**Branch:** `fix/p0-recover-jobs-explore-latency` (commit `e657a17`; nothing pushed/public)
**Frozen contracts:** `edit_plan/5.2` SYSTEM prompt + `EditPlanV2` output contract — **UNTOUCHED** (all changes additive, request-only).

## Problem

On device, a pure pacing revise ("shorten each clip to ~5s and keep the highlights") produced an
entirely **new clip set** instead of re-timing the selected version's clips. Two architectural root
causes, verified in code (job `d25b9f63`: `model_calls=1`, clips re-picked):

1. **AI-recommended duration was a hard validation constraint.** `validate_plan` checks total output
   against `creative_intent.target_duration_seconds` with an asymmetric -20%/+50% tolerance —
   identically for every operation, with no knowledge of whether the target was a user requirement or
   an AI recommendation, and no knowledge it was a timing-only revise. A correctly-shortened retime
   fell below the AI's recommended length -> rejected.
2. **Silent fallthrough to unrestricted replanning.** When the deterministic retime/structural fast
   path was rejected, the engine proceeded to `_call(_build_user(inputs))` — a full from-scratch model
   plan with no preservation constraint — which re-picked clips. This applied to **all** targeted
   revises, not just the 5s case.

## Constraint hierarchy (owner-approved)

| Tier | Constraint | Policy |
|---|---|---|
| 1 | Renderer feasibility (speed in [0.5, 2.0], source ranges, useful-segment coverage, transitions) | **Mandatory — never relaxed** |
| 2 | Explicit user requirements (custom exact duration, named Moment directives) | **Authoritative**, subject to feasibility |
| 3 | Targeted-revision preservation (clip identities, order, source ranges, soundtrack, native audio, transitions, lineage) | Preserved by default |
| 4 | Soft user preferences ("~5s", "faster", "more energetic") | Optimized as closely as feasible |
| 5 | AI recommendations (inferred duration, pacing, breadth) | **Must NOT override a user's revise intent** |

## Duration provenance (numeric source != editorial mode)

Per owner correction: Highlights / Full Story are explicit **editorial preferences**, but their
**numeric** duration is AI-recommended. Provenance tracks the number, not the mode.

- **New additive request field:** `revision_context.duration_target_source in {user_exact, ai_recommended}`.
  Request-only; **not** an `EditPlan/2` change. Default (absent/unknown) = `user_exact` (strict, safe).
- **iOS** (`StoryCreationCoordinator.composeRevisionContext`) derives it from the persisted
  `StoryModel.editorialMode`: `custom -> user_exact`, `highlights|full -> ai_recommended`. A value the
  base context already carries (a newer explicit instruction) is never clobbered.

## Operation-scoped validation (no global weakening)

- `_undershoot_tolerance_for(inputs)` returns the strict default `DURATION_UNDERSHOOT_TOLERANCE` for
  initial creation and for any revise with a `user_exact` target; it returns **None (no lower bound)**
  only for a **timing-only revise** whose target is `ai_recommended`. Overshoot, speed, source-range,
  and feasibility checks are untouched.
- `apply_deterministic_retime` no longer lifts shot durations toward the old target for an
  `ai_recommended` target (lets the video shorten to honor the pacing); it keeps the `min_total` lift
  **only** for `user_exact` (honor the explicit length while preserving clips).

## Preservation-safe fallback boundary

- A **targeted revise** = `mode==revise` + a `base_plan` + **not** `allow_broad_replan`. Such a revise
  never becomes an unrestricted from-scratch plan free to re-pick every clip. The only from-scratch
  replans allowed: initial creation, Explore (`mode==explore`), and a revise that **explicitly**
  authorizes broad redesign (`revision_context.allow_broad_replan == True`).
- **Preservation gate** (`_preservation_violation`): after the model is consulted and the plan is
  valid + feasible, the accepted plan's clip set (segment `asset_id`s, case-insensitive) is compared to
  the base. A timing/soft revise may not add or drop clips; a directive revise may only touch clips its
  directives name. A silent re-pick is rejected with a clear limitation — *"could not be applied without
  changing parts of your video you did not ask to change ... your current version was kept unchanged"* —
  and the user's existing version is preserved. Never fabricates success, never substitutes a different
  video.
- This increment enforces the **boundary + the check** (owner: do not build every repair algorithm
  now). Richer bounded preservation-repairs are a later increment.

## End-to-end provenance (iOS -> API -> SQS -> Lambda)

`revision_context` is a free-form dict on `EditPlanRequest`, passed unfiltered by the API and the worker
into engine inputs, so `duration_target_source` survives intact. The worker's `rev_diag` now logs
`dur_src` for live CloudWatch verification.

## Tests

- **Python (+9, suite 115 pass):** undershoot relaxed for `ai_recommended` timing revise (0 model
  calls, clips preserved, total shortened, no lift); `user_exact` keeps the strict lower bound (lift,
  clips preserved); initial-creation undershoot unchanged; preservation gate rejects a model clip
  re-pick (clear limitation) / allows a preserving revise; `allow_broad_replan` bypasses; provenance
  defaults to `user_exact`.
- **Swift (+5):** `editorialMode -> duration_target_source` wire mapping (custom/highlights/full/none)
  and no-clobber of a base-context value.

## Deploy

CodeBuild `story-rb-caseg-build` -> ECR -> App Runner `start-deployment` (API) + CDK worker-asset deploy;
health 200. Verify on device via `worker_plan_diag` `rev_diag.revision_path` + `rev_diag.dur_src`.

## Acceptance scenarios (device, owner STOP)

1. "Shorten each clip to ~5s" with inferred (Highlights/Full) duration -> `revision_path=deterministic_retime`,
   `model_calls=0`, `dur_src=ai_recommended`, same clips, total shortened (not lengthened).
2. Same with explicit custom duration -> clips preserved, total held near the exact length.
3. Remove one Moment, allow shorten. 4. Reorder Moments. 5. Replace only the opening.
6. Change soundtrack only. 7. Faster beat-aware cuts. 8. Unsupported color adjustment.
9. Unsupported visual effect. 10. Infeasible source range. 11. Mixed supported/unsupported.
12. Broad creative redesign (authorized). 13. Revision of an older selected version.
14. Recovery after app restart.
Per scenario verify: user-intent satisfaction, preservation of unrelated edits, duration-policy
behavior, renderer executability, no unintended replan, model-call count, latency, correct
`parentVersionId`, previous version unchanged.

## Retime correction — trim at normal speed (commit `5b2fcc0`), and 7-point verification (`bac6fe7`)

**Observed on device** (job `78350357`, retime fired correctly: clips kept, shortened, 0 model calls):
most clips played at ~1.8–2.0x with pitched-up native audio. **Root cause:** the first retime kept each
clip's full source span and shrank `output_duration`, so the renderer derived `speed = span/output` and
ran the footage fast. **Fix:** "shorten a clip to ~5s" now means *show ~5s of footage at normal speed* —
the retime **trims the source window** to `start + target` (preserving the planner's in-point), sets
`output_duration = trimmed span`, and keeps `speed = 1.0`. A clip already shorter than the target keeps
its whole window (never stretched). It never auto-increases playback speed or pitch-shifts audio.

**Verification (all confirmed in code + tests, 116 pass):**
1. Selected-version segment identities + order preserved — yes (clip set and order byte-identical).
2. Every revised segment `speed == 1.0` for this instruction — yes.
3. Native audio synchronized + normal pitch — yes (`output_duration == trimmed source span`, so playback
   is 1:1; `native_audio` policy unchanged).
4. Duration follows the user's request, not the old AI target — yes (undershoot floor relaxed for a
   timing-only `ai_recommended` revise; total shortens to the per-clip request).
5. Protected continuous performances — **limitation (see below):** no protected-performance signal exists
   in today's schema, so ordinary unprotected shots get the bounded start-trim; a clip already shorter
   than the target is not shortened.
6. Reliable AU timestamps / action anchors not cut off — **partial (see below).**
7. Validation failure never triggers unrestricted replanning — yes: a timing retime that cannot validate
   raises a clear limitation (`revision_path=deterministic_retime_infeasible`, `model_calls=0`, "your
   current version was kept unchanged"), never falling through to the model.

## Point-6 feasibility — can a bounded deterministic highlight-aware trim be built now?

**Finding: partially. Reliable timestamps exist; a quantitative highlight/action ranking does not.**
- `moments[].useful_segments` are **numeric `(start, end)` windows** (possibly several per Moment) — the
  planner already uses them, and they are reliable. A bounded, deterministic improvement is feasible
  **without any model**: snap the trimmed window to lie *inside a single `useful_segment`* (don't trim
  across a window boundary; prefer the longest/earliest usable window) instead of blindly from the clip's
  `source_start`.
- `moments[].events` carry only a **description string** — the planner does not read a per-event
  timestamp, so events cannot anchor a trim today.
- EditPlan/2 segments carry `narrative_role` (free text) and `music_alignment.anchor` — neither marks a
  **protected continuous performance**, so a performance cannot be detected deterministically yet.

**Decision (owner-directed):** keep the bounded start-trim for ordinary unprotected shots now; do NOT
build a multimodal highlight-selection model. Deferred as a future bounded increment: (a) snap-to-
useful-segment trimming, and (b) a protected-performance / minimum-duration signal so continuous
performances are not shortened below a floor.

## Remaining limitations / deferred

- **Protected continuous performances & highlight-aware trim** — no schema signal today (see point 6);
  bounded snap-to-useful-segment + protected-duration floor deferred.
## Phase 5 — unsupported-operation handling (commit `5e4fa34`, deployed)

**Audit:** an unsupported revise ("make it warmer", "add a glow", "reframe to square") has no hard
directive and no clip-length target, so it fell through to the model, which returns SOME re-cut plan —
a SILENT SUBSTITUTION of a different edit for the one asked for. MediaEngineV1's own scope (header
comment): trim, order, output duration, aspect-fit, cut, crossfade/fade, 0.5-2.0x speed — NO color,
filters, brightness/contrast/saturation, glow/vignette/blur, zoom/crop/reframe, stabilization,
text/overlay or background replacement.

**Smallest guard:** `_classify_unsupported_ops()` scores a revise's `soft_direction` against the renderer
capability vocabulary BEFORE any planning. `all_unsupported` -> keep the selected version and raise a
clear limitation (new `failure_category = unsupported_operation`, `model_calls = 0`, "your current
version was kept unchanged"); `mixed` (a supported edit + an unsupported effect) -> record
`partial_support_note` naming what cannot be applied and run the supported part; `supported`/empty ->
unchanged. Word-boundary, case-insensitive; no false positives on shorten/reorder/music/faster-cuts/
"more cinematic"; bare object nouns ("stabilize the clip") do not flip to mixed. Initial creation is
never gated. Worker maps it to its own `failure_category`; iOS `EditPlanJobFailure.unsupportedOperation`
+ an honest message (no fabricated success, no substitute video). +3 tests (118 pass).
- Richer bounded preservation-safe repairs (localized feasibility correction beyond relax-and-
  revalidate) deferred.
- The transition-vocabulary drift (backend {cut,crossfade,fade_in,fade_out,dip_to_black} vs iOS
  {cut,fade,dissolve}) documented elsewhere remains.
