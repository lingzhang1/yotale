# Milestone — P0 Fix: EditPlan Renderer Capability Validation (speed 0.5x–2.0x)

Status: IMPLEMENTED (backend + tests), awaiting device acceptance. STOP before prompt freeze.
Owner-approved: 2026-10-14. Code-grounded; no public push/deploy.

## 1. Root cause confirmation

The on-device render failure *"The plan can't be rendered: segment 0 speed 4.0 out of
range [0.5, 2.0]"* is a **contract gap between the planner and the renderer**, not a
transient bug:

- The EditPlan/2 schema only requires `"speed": {"exclusiveMinimum": 0}` — any positive
  number is schema-valid.
- The deterministic `validate_plan` gate (the production executability check) validated
  source ranges, output-duration consistency (`output == span/speed`), ordering, and audio,
  but **never bounded the speed value itself**. So a plan with `speed: 4.0` passed every
  server check as "executable".
- `MediaEngineV1` (the on-device renderer) supports playback only in **0.5x–2.0x**
  (`apps/ios/.../Media/Render/MediaEngineV1.swift` SCOPE line). `StoryCreationCoordinator`'s
  renderability check rejects anything outside that window and surfaces the exact error seen.

Hiking triggers it more than other fixtures because its long walking/landscape clips invite
the model to compress with aggressive speed-up to hit the target duration. At temperature 0.0
the same inputs reproduce the same 4.0x plan, so "Try again" with an identical request repeats
it (and the async idempotency path may return the cached plan).

## 2. Validator changes (Phase 1 — deterministic reject, NOT clamp)

`packages/edit_planner/__init__.py`:

- New exported constants `RENDERER_SPEED_MIN = 0.5`, `RENDERER_SPEED_MAX = 2.0`, documented as
  the renderer capability and kept in sync with the iOS check.
- `validate_plan` now evaluates each segment's speed in order:
  1. non-finite / non-numeric (`inf`, `nan`, junk) → `"segN: speed must be a finite number ..."`
  2. `<= 0` → existing `"segN: non-positive speed ..."`
  3. outside `[0.5, 2.0]` → `"segN: speed S out of renderer-supported range [0.5, 2.0]"`
  4. else the existing output-consistency check.
- `_segment_timeline` now resolves speed via `_coerce_speed`: an **absent** speed defaults to
  1.0 (the schema default); a **present** speed is validated AS GIVEN (so 4.0 is rejected, not
  normalized); non-numeric junk becomes `NaN` so the finite gate rejects it cleanly instead of
  raising deep in arithmetic.
- **Reject, not clamp** (owner directive). A mathematically valid speed is not necessarily an
  editorially valid one; the plan is routed to bounded repair so the planner picks a real
  alternative. No source range or output duration is silently modified. `normalize_plan` is
  unchanged and still only snaps the redundant `output_duration_seconds` within a tiny window —
  it never touches speed or source ranges, so it cannot mask an out-of-range speed.
- Because every path (normal, multimodal, critique, revision, model-fallback) runs its output
  through `validate_plan` before the plan is accepted, the gate applies uniformly to all of them.

## 3. Repair behavior (Phase 2 — bounded, honest failure)

The existing bounded repair path is reused (no new engine, no new retry loop):

- `RealEditPlannerEngine.generate` already does: generate → normalize → validate → (if invalid)
  ONE model-repair turn carrying the exact validator errors → re-normalize → re-validate → if
  still invalid, raise `StructuredOutputError` (honest planning failure, never ships an invalid
  plan). Repairs are bounded by `executability_repair_attempts` (default 1).
- `_build_repair` prompt amended with a **RENDERER SPEED** rule: when a segment uses an
  unsupported speed, PREFER to shorten the source range and let the cut carry the pacing rather
  than merely clamping the number; keep speed within 0.5x–2.0x; use speed only as a last resort.
- The repaired plan is re-validated by the deterministic gate (authoritative; the model never
  self-certifies). Target duration, source grounding, native-audio policy and hard directives
  are preserved by the existing repair-prompt invariants.
- The critique→revision pass already adopts a revision ONLY if it also passes `validate_plan`,
  so a revision that reintroduces an invalid speed is rejected and the original valid plan is
  retained.

## 4. Renderer capability audit (Phase 4)

Backend `validate_plan` vs iOS `StoryCreationCoordinator.validate(plan:...)` / `MediaEngineV1`:

| Dimension | iOS renderer (authoritative) | Backend validator | Status |
|---|---|---|---|
| **Playback speed** | reject if `s < 0.5 || s > 2.0` | **now rejects outside [0.5,2.0] + non-finite** | **FIXED (this change)** |
| Source range validity | `end > start`, `start >= 0` | `0 <= start < end`, `end <= duration+0.05`, overlaps a useful_segment | backend STRICTER (good) |
| Source material available | `output*speed <= clip + 0.05` | `source_end <= duration+0.05` (per-seg) | equivalent intent; backend bounds source_end, iOS bounds consumed span — both prevent over-read |
| Min segment duration | `output > 0` | `output > 0` | MATCH |
| Transition types | `{cut, fade, dissolve}` | schema enum `TRANSITION` (verify set); duration `>=0`, `<= segment` | **MISMATCH TO DOCUMENT** — enum sets must be reconciled (see below) |
| Transition duration | not re-checked beyond type | `>= 0` and `<= segment output` | backend STRICTER (good) |
| Crop / aspect ratio | engine fits aspect/crop downstream; no plan field | not in EditPlan/2 | N/A — no plan-level field, not a mismatch |
| Native audio | `{keep, duck, mute}` | schema enum `NATIVE` + required | MATCH |
| Music source & duration | soundtrack cut/looped downstream to fit | planner carries `music_asset_id`/alignment only; music fit is downstream | N/A at plan level |
| Whole-plan duration | `outputSum <= sourceSum + 0.1` | asymmetric target band (−20% / +50%) | different purpose: iOS = physical source feasibility, backend = editorial length; both bind |
| Segment count | none explicit | none explicit (token-cap escalation only) | MATCH (no hard cap) |

**Immediate blocker fixed now:** playback speed (the confirmed crash).

**Documented, NOT fixed in this P0 (not an immediate render blocker):**
- *Transition vocabulary drift.* The iOS renderer accepts `{cut, fade, dissolve}`. The backend
  schema's `TRANSITION` enum and the validator's crossfade-family names
  (`crossfade, fade_in, fade_out, dip_to_black`) should be reconciled against the renderer's
  accepted set so the planner cannot emit a transition the renderer silently ignores or rejects.
  This has not produced a device failure (the renderer tolerates/degrades unknown transitions to
  a cut), so per the owner's "document other mismatches separately unless immediate blockers"
  it is logged here for a follow-up, not changed in this P0.

No renderer redesign; scope limited to the confirmed speed mismatch.

## 5. Test results (Phase 5)

`apps/api/tests/test_edit_planner.py` — all 12 required cases + supporting, full api suite green
(135 passed):

1. speed=0.5 accepted ✔
2. speed=1.0 accepted ✔
3. speed=2.0 accepted ✔
4. speed=0.49 rejected ✔ (`out of renderer-supported range`)
5. speed=4.0 rejected ✔ (exact hiking case, message cites `[0.5, 2.0]`)
6. non-finite speed rejected ✔ (`inf`, `nan`, and non-numeric `"fast"`)
7. invalid speed triggers bounded repair ✔ (exact error reaches repair prompt; 1 attempt)
8. repaired plan passes full validation ✔ (round-tripped contract → zero errors)
9. repair preserves target duration ✔ (total within accept band)
10. repair does not violate hard directives ✔ (preserved via repair-prompt invariants; covered)
11. critique/revision cannot reintroduce invalid speed ✔ (revision rejected, original retained)
12. existing valid plans remain unchanged ✔ (absent-speed default 1.0 still valid)

## 6. Device results (Phase 6)

PENDING owner device acceptance. Reproduce the hiking scenario and verify: backend catches the
invalid plan; repair produces a valid plan; no segment exceeds 2.0x; total duration valid; iPhone
renders successfully; music and native audio correct; no editorial degradation. **Requires the
backend change deployed to the dev App Runner** (dev only — the device sends plans the live
validator must gate).

## 7. Versioned prompt recommendation (Phase 3)

Candidate `prompts/edit_plan/5.3-cand/` = frozen `5.2` byte-for-byte PLUS a single added
invariant (`RENDERER SPEED LIMIT`: supported speed 0.5x–2.0x; achieve faster pacing primarily via
shot selection and cut timing; do not propose time-lapse/speed-ramp). `diff` against 5.2 shows
exactly the 5 added lines — frozen 5.2 is unchanged and NOT wired as the live `PROMPT_VERSION`.

Recommendation: the deterministic validator + repair already prevent the crash with the frozen
prompt. The prompt amendment reduces repair churn by stopping the model from proposing unsupported
speeds in the first place. Run a bounded comparison (reuse cached hiking evidence, no new A/B
sweep) before requesting prompt-freeze approval. **STOP before freezing a new prompt version.**

## Files

- `packages/edit_planner/__init__.py` — constants, `_coerce_speed`, `validate_plan` speed gate, `_build_repair` rule.
- `apps/api/tests/test_edit_planner.py` — +20 tests (all 12 required cases).
- `prompts/edit_plan/5.3-cand/system.md` — versioned candidate (proposal only).
