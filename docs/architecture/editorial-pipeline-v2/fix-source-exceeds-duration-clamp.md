# Fix: never-block `source_exceeds_duration` (deterministic source-range clamp)

Status: **IMPLEMENTED (2026-11-02), PR pending** — backend-only, offline-tested. Not yet deployed.

## Symptom (owner-reported, beta)
A revise ("Start with Moment 3, followed by 7, 9, 11", Highlights, Custom 32s) repeatedly failed with the
client screen *"Your instruction couldn't be applied to this footage — it may exclude too much or conflict."*
Removing the per-clip "each clip less than 5 seconds" phrase did **not** fix it.

## Root cause (traced from live worker logs)
The failing job's `worker_validation_diag`:
```
terminal: invalid_after_repair
final_error_codes: ["source_exceeds_duration"]
directive_categories: ["must_include", "opening", "order_adjacent"]   # NOTE: no `exclude`
target_seconds: 32, usable_moment_count: 12
```
Two findings:
1. **Not an exclusive-membership problem.** The interpreter (`revision_interpret/2`) correctly treated the
   named Moments as `must_include` + ordering, with **no `exclude`** — the other 8 Moments stayed eligible.
   So "only use these 4" was never the constraint; the "4 clips can't fill 32s" theory was wrong.
2. **The real error is per-segment** (`edit_planner/__init__.py` validator, ~L839):
   `if source_end > moment_duration + 0.05 -> "source_end exceeds Moment duration"`. Reaching for ~32s, the
   model wrote a segment whose `source_end` ran past that clip's real length. The single model-repair attempt
   didn't fix it → terminal `invalid_after_repair`, surfaced to the user as the misleading generic copy.

Duration is already advisory/non-blocking (owner 2026-10-25) and the interpreter was already correct, so the
only broken link was this mechanical overshoot being treated as a hard, model-repair-only failure.

## Fix
`normalize_plan` (the deterministic pre-validation pass) now **clamps** any `source_end_seconds` that exceeds
the clip's real `duration_seconds` down to that duration, re-deriving `output_duration` from the clamped span
at the unchanged speed. It only ever REMOVES footage that does not exist — always safe and fully renderable —
so `source_exceeds_duration` can no longer reach the validator or fail a generation.

Contrast with the speed-range gate, which is deliberately a REJECT (not a clamp) because changing speed changes
editorial intent. Trimming a nonexistent source tail does not change intent; it is the never-block-correct move.

A shorter total is fine — target duration is advisory. The result is the best valid, playable video rather than
a hard failure.

## Scope
- `packages/edit_planner/__init__.py` — clamp in `normalize_plan` (runs before `validate_plan` on every path).
- `apps/api/tests/test_edit_planner.py` — test: an over-long `source_end` normalizes to a valid passing plan;
  a within-bounds range is untouched.
- Backend-only; no contract/schema change; no iOS change. Full API suite green.

## Still open (separate, lower priority)
- The iOS error copy still blames the instruction for any `invalid_after_repair` with hard directives; once the
  clamp ships, `source_exceeds_duration` no longer triggers it, but other `invalid_after_repair` causes could.
  An honest, cause-specific message is a follow-up UX fix.
