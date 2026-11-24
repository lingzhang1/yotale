# Milestone R7 — Cloud-Aware Planner Eligibility & Explicit Moment Addition

Status: Phases 0–2 implemented (iOS); STOP at device acceptance. Phase 3 (explicit add-new-Moment during Revise) separately gated.
Date: 2026-10-20
Commit: `7757fe4` (iOS). No backend/worker change — the frozen Edit Planner/validator are byte-identical.

## Problem (P0)

The TMB Story has 14 Moments, but only 4 reached the Edit Planner. A directive naming a real
Moment ("end with Moment 2", id `9D36385A`) failed `directive_ref_ineligible` → `invalid_after_repair`.

Root cause (evidence): `RenderSupport.build()` built the planner `moments[]` from
`MomentResolver.resolve()`, which **hard-skips any Moment whose original file is not on disk**
(`fileExists`). On this device only 4 of the 14 TMB Moments had local bytes; the other 10 were
cloud-only (evicted / R7-restored shells) — including Moment 2, whose Asset Understanding **exists
server-side**. So a satisfiable, correctly-authored directive was blocked by a device-local byte gate
the planner never needed. `StoryCreationReadiness.evaluate` was already cloud-aware (`onDisk ||
restorable`); the request builder was not — the two disagreed.

Attribution: **B — pre-existing planner-input coupling exposed by R7 directive sync.** The Edit
Planner itself is unchanged; R7-C's cross-device directive sync made the cloud-only directive always
present, surfacing the latent local-byte eligibility coupling.

## Phase 0 — Contract audit

The planner `moments[]` payload is `{id, duration_seconds, useful_segments, summary, evidence}` and
needs **zero original bytes**:
- `duration_seconds` — `AssetModel.durationSeconds` (cloud metadata, carried in the synced Story doc).
- `useful_segments` / `summary` / `evidence` — the MomentUnderstanding JSON, hydrated from the server
  by `UnderstandingSync.restore` (metadata batch-get + content-sha reuse gate — **no bytes, no Bedrock**).

Original bytes are required only at **render** time, where R6 (`resolveEnsuringLocal`) already restores
them. "Removing fileExists is not automatically safe" (owner): confirmed — the render-time file gate is
kept; only the **planner-eligibility** gate is decoupled from local bytes.

## Phase 1 — Directive safeguard

Before Create/Revise submit, `restoreReferencedCloudOnlyMoments` now **hydrates server-side AU** for
every directive-referenced Moment missing a local AU (`UnderstandingSync.restore`, bounded to referenced
ids, no Bedrock), then best-effort pre-restores bytes. `directiveEligibility` is cloud-aware: a Moment is
eligible once it has AU + duration + a renderable source. A reference that genuinely cannot be satisfied
(no AU and not restorable, or bytes gone) is preserved and surfaced as an honest pending/recovery state —
never silently stripped, and a directive whose Moment is absent from `moments[]` is never submitted.

## Phase 2 — Cloud-aware eligibility (shared boundary)

New shared policy in `MomentResolver`:
- `plannerDuration(for:)` — local probe if on disk, else `AssetModel.durationSeconds`; 0 = unknown.
- `isRenderableSource(_:)` — bytes local **OR** cloud-verified + `cloudMediaId` (restorable via R6).

A Moment is **planner-eligible** iff: completed AU **AND** `plannerDuration > 0` **AND**
`isRenderableSource`. Applied in all four coupled builders — `build`, `usableNumberedMoments`
(Customize "Moment N" numbering), `momentsPayload` (Duration Planner), `directiveEligibility` — so they
agree with each other and with the planner. Local-only Moments behave exactly as before. A fully
cloud-only Story is plannable (the `noUsableMoments` guard now checks the planner set, not the local set).

Pre-render restore: after the plan completes, the Moments the plan **actually selected** have their
originals restored via R6 before the render resolver/validate — in both the fresh (`run`) and resume
(`renderResumedPlan`) paths. A Moment that cannot be restored is reported by `validate()` as an
unresolved asset (honest failure), never a silent skip.

## Phase 3 — Explicit Moment additions during Revise (separately gated)

This fix already lets a **revise reference any Story Moment with synced AU** (not just those in the base
plan), because the eligible set is the whole cloud-aware Story set. "Add Moment N / replace / remove" via
directives therefore resolves against the full set. A deterministic *add-new-segment* revision transform
(beyond reorder/prune) would touch `apply_deterministic_revision` semantics — if that is required it is a
versioned proposal (STOP gate), not implemented here.

## Boundary assessment

Strictly additive, iOS-only. No change to EditPlan/2 schema, frozen prompts, or `validate_plan` semantics.
Backend `apps/api/tests/test_edit_planner.py`: 125 passed (contract intact).

## Tests

`CloudAwareEligibilityTests` (in-memory SwiftData, no Bedrock/network): cloud-only Moment with AU is
eligible; a directive referencing a cloud-only Moment is eligible and in the payload; Device-A/Device-B
equivalent eligible sets; missing AU → honest exclusion (not invented); bytes-gone Moment with AU → not
eligible (cannot render); fully-cloud-only Story is plannable; Customize numbering includes cloud-only
Moments with `localAvailable=false`. Device Xcode build is the authoritative compile gate (sandbox blocks
the SwiftData macro plugin), so these run on device.

## Deployment & acceptance

**iOS-only — no backend/worker redeploy.** Rebuild the app on device, then using the TMB Story:
- Confirm planner-eligible set includes all 14 Moments when their AU/duration are valid.
- Confirm "end with Moment 2" no longer fails due to device-local availability.
- Confirm the rendered video uses the requested Moment (R6 restores its bytes before render).
- Confirm normal-speed/native-audio behavior is preserved.

## Remaining limitations

- A referenced Moment with no synced AU still blocks honestly until AU hydrates (expected).
- Deterministic *add-new-segment* revision (vs reorder/prune) is Phase 3, gated.

## Addendum — the real cause of "9 clips you did not ask to remove were dropped"

After the cloud-aware fix landed, the same TMB revise ("Start with Moment 1, then Moment 6, end with
Moment 2") failed with a NEW error. Worker diag `7928e215`: `usable_moment_count: 14` (the regression
IS fixed — all Moments reach the planner), `terminal: preservation_violation`, `repairs_used: 0`,
`final_error_codes: []`. The plan was structurally valid but dropped 9 base clips.

Root cause (NOT a policy question): the revise ran at **target 16.5s** while the base video is **85s**.
`StoryResultView.startRevise` passed no `targetSeconds`, so `EditPlanRequestBuilder.build()` fell back
to `story.intentTargetDurationSeconds` — a stale 16.5s left from earlier testing (the live doc now shows
it null, but at failure time it was 16.5). Honoring opening+adjacency+ending at 16.5s forced the planner
to keep only a few clips and drop ~9; the preservation backstop then **correctly** rejected the silent
loss. The backstop was right; the target was wrong.

Fix (commit `b3084be`, iOS-only): `startRevise` derives the revise target from the base executable plan's
`target_duration_seconds` (authoritative), falling back to the rendered `durationSeconds`, and passes it
to `reviseVersion`. A revise edits the existing ~85s video; it never invents a new length. At 85s every
base clip fits, so a reorder-only directive applies without dropping anything. Tests:
`StoryResultFlowTests.test_baseTargetSeconds_*`.

Note (latent, separate): `_preservation_violation` builds its `authorized` id set from object keys
(`asset_id`/`id`/`moment_id`/`target_id`) but the directive payload is a dict of id-lists
(`opening`/`ending`/`must_include`/`exclude`/`order_*`), so `authorized` is always empty. It did not
affect this case (the target fix removes the drops entirely) and touching it is a frozen revision-policy
change — a separate versioned proposal if a directive-named clip ever legitimately needs to move/drop at
a correct target.

## Addendum 2 — revision routing (avoid unnecessary AI replanning) + failure-message separation

After the revise-target fix, the same TMB revise ran at 87.5s (correct) but still dropped 2 clips →
preservation violation. Phase 0 proof (no Bedrock): `apply_deterministic_revision` on a faithful 85s
14-clip TMB base plan with the directive (opening=M1, M6 immediately after M1, ending=M2) places the
order correctly, **drops 0 / adds 0 clips**, and passes the full validator (total 85.0s). So the
deterministic path fully satisfies the instruction — the model path was the problem.

Root cause: the deterministic revision fast path runs only when `soft_direction` is empty, but a revise
sent the instruction text as BOTH structured directives AND `soft_direction`, so the path was skipped and
the model re-planned (dropping 2 clips).

Phase 1 fix (commit `95244dc`, iOS): `InterpretationCoordinator.residualSoftDirection` subtracts the exact
parsed directive spans (non-naive — not keyword matching) and returns the creative leftover, empty when the
instruction is fully structural. The deterministic `.ok` branch emits that residual instead of the raw
text, and `ReviseStorySheet` passes `outcome.softDirection` (not the raw instruction) to the coordinator.
So a pure-structural revise sends empty `soft_direction` → the engine's deterministic reorder runs and
preserves every clip. Verified standalone: "Start with Moment 1, then Moment 6, end with Moment 2" →
residual `''`; "…make it more cinematic" → residual kept; "exclude Moment 4" → `''`. The raw text stays in
the sheet for display/history.

Phase 2 fix (commit `95244dc`, backend + iOS): a preservation violation no longer wears the
material-infeasibility "can't fill the target" prefix. `worker.py` re-categorizes `material_infeasible`
with `last_diagnostics.final == "preservation_violation"` to a distinct `preservation_violation` category
(mirrors the existing `unsupported_operation` promotion). iOS adds `EditPlanJobFailure.preservationViolation`
and a distinct `StoryCreationError.preservationViolation` message ("altered clips you didn't ask to change,
so your current version was kept. Try naming the Moments to keep or move, or use Create Another Version"),
and routes it to Adjust Instructions, not a plain retry. Worker redeployed (Lambda LastModified
2026-10-21T05:34Z). Tests: `InterpretationPipelineTests` residual cases; backend `test_edit_planner.py`
(125) and `test_edit_plan_jobs_api.py` green.

No frozen EditPlan/2, prompt, or validator-semantics change. The `_preservation_violation` authorized-id
extraction remains a separate latent bug (not needed for this case).
