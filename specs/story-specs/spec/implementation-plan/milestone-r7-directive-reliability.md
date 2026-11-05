# Milestone R7 — Directive Reliability & Persisted-Instruction UX (P0)

Status: implemented + backend-deployed (dev) + automated-test verified; **awaiting device acceptance**.
Commits (app repo): planner `669ad89` (Part A+C), Customize `4c860b0` (Part B). Worker deployed to dev
(Lambda LastModified 2026-10-21T01:45Z). No frozen EditPlan/2 or prompt change.

## Attribution (accepted)
The Edit Planner implementation (`packages/edit_planner/__init__.py`) is **byte-identical** between the
pre-R7 baseline (`9c81f17`, parent of R7-A) and HEAD — confirmed by `git diff`. R7-C added cross-device
directive SYNC (`StoryDocCodec` encodes `creative_directives_json`; `StorySyncCoordinator.apply` restores it),
which, combined with the pre-existing `composeRevisionContext` folding persisted directives into every
original create, means a once-typed opening+adjacency directive now rides along on every create/revise.
The directive is **satisfiable** (a conforming plan passes the real `validate_plan`), so the failure is a
**pre-existing planner weakness** (model mis-orders a satisfiable opening/adjacency; model-repair doesn't
reliably fix it → `invalid_after_repair`) **exposed by R7-changed inputs**. Classification: **B**.

## Part A — deterministic structural directive repair (additive)
`repair_directive_placement(plan, inputs)` reorders ONLY `segment.order` to satisfy opening/ending/
order_adjacent/order_after, preserving asset_id, source ranges, output_duration, speed, transition,
native_audio and music_alignment (carried with the segment). No add/drop/reselect. Wired into the engine
repair loop AFTER the first `validate_plan`: when the errors are order-only (`_errors_are_order_only`), it
reorders and re-runs the FULL validator with NO model call; membership/duration/speed/source errors fall
through to the model-repair loop unchanged. Returns None (keeps the existing failure path) when the
constraints are unsatisfiable by reorder (opening/ending absent, cyclic order). No frozen-contract change.

## Part B — persisted-directive visibility in Customize
Customize now renders a **SAVED INSTRUCTIONS** summary by stable Moment number (opening/adjacency/order/
include/exclude), distinct from the new free-text input, with an explicit **Clear**. On submit the kept
saved directives are folded back (new typed text wins per slot); Clear drops them. Never silently retains a
cleared directive, never silently drops a kept one. Stable numbering → Device A/B show equivalent directives.

## Part C — editorial_mode / target consistency
`editorial_mode="full"` with `target=16.5s` is VALID: `full` is an advisory prompt bias ("broader
representation **where footage and duration support it**") with NO hard coverage/clip-count constraint; the
target stays authoritative. Restored correctly from R7. **No mapping defect; no change made.**

## Tests
edit_planner suite **125 passed**, incl. +7 structural-repair tests (opening-only, opening+adjacency,
transition/music-alignment preserved, opening-absent→None, cyclic→None, membership-not-order-only, end-to-end
engine repair with no model-repair call). iOS: `savedDirectiveLines` renders all active directive kinds.

## Device acceptance checklist
1. TMB create/revise with the existing opening+adjacency directive now SUCCEEDS (structural repair reorders).
2. Customize shows the SAVED INSTRUCTIONS summary for that directive; Clear removes it from the next request.
3. A genuinely infeasible/contradictory directive still fails honestly.
4. Segment order in the delivered plan honors opening + adjacency.
5. Capture one `worker_validation_diag` only if a failure occurs (should not, for the satisfiable TMB case).

## Known limitations
- Customize's "Create" always runs one NL interpretation call even with empty new text (pre-existing).
- The real live `worker_validation_diag` for the TMB case has not yet been captured (every prior failure
  pre-dated the crash fix or was client-blocked); device acceptance will confirm success (0 failures expected).
