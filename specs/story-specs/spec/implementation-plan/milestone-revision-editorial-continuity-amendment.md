# Milestone — Revision Architecture Refinement: Creative Freedom with Editorial Continuity (AMENDMENT)

Status: **ARCHITECTURE / FREEZE GATE — awaiting owner approval. No implementation, nothing deployed, nothing pushed.**
Owner decision date: 2026-10-21 · Author: default (Kiro) · Method: code-grounded re-audit (direct file:line read this session).
Supersedes: the terminal-rejection preservation policy in
`milestone-p0-revision-constraint-priority-and-preservation.md` §"Preservation-safe fallback boundary".
Builds on the two approved foundations: `milestone-creative-revision-foundation-design.md`,
`milestone-creative-editorial-freedom-architecture.md`.
Frozen & UNTOUCHED by this amendment: `edit_plan/5.2` SYSTEM body, EditPlan/2 OUTPUT schema. All changes
request-only / routing-only / validator-predicate-only.

---

## Phase 0 — Reconciliation audit (code-grounded, this session)

Audited `packages/edit_planner/__init__.py`, `packages/edit_planner/deterministic_revision.py`, and the iOS
revision-context builders. Exact divergences from the approved foundation:

| # | Foundation says | Current code does | File:line |
|---|---|---|---|
| D1 | Revise injects the **exact base_plan** into the USER message so the model preserves it | `_revision_context_block` renders only `prior_edit_summaries` + directives. **`base_plan` is NEVER put in the USER message.** The model revises with no base to diff against. | `__init__.py:1070-1113` (comment at `:1510` wrongly claims it is injected) |
| D2 | "A technically valid revision should not be discarded solely because the clip set changed" (owner principle 5) | `_preservation_violation` converts **any** unauthorized clip add/remove into a **terminal `EditPlanInfeasibleError`** — the valid, rendered-feasible plan is thrown away and the old version kept | `__init__.py:540-579`, gate at `:1591-1600` |
| D3 | Deterministic editing is a **fast path, not a mandatory stage** | Correct today: retime (`:1450`) and structural (`:1489`) fast paths return early with 0 model calls; no AI pre/post stage wraps them. KEEP. | `__init__.py:1450-1503` |
| D4 | Revise must **not** seek diversity | Correct: Revise objective is "Apply the requested changes and PRESERVE unaffected edits where feasible" — it does NOT inherit Explore's "MEANINGFULLY DIFFERENT" text. But the objective is **thin** (no base plan, no "newer intent wins" framing). | `__init__.py:1098-1102` |
| D5 | `_preservation_violation` authorized-set should contain the directive-named ids | **Latent bug:** it iterates `rc["directives"]` as if it were a **list of dicts** (`for d in ... d.get("asset_id")`), but `directives` is a **dict of id-lists** (`opening`, `ending`, `must_include`, `exclude`, `order_*`). So `authorized` is **always empty** — even a legitimate exclude/add is flagged. (Carried from the prior P0 as "Part A".) | `__init__.py:566-571` |
| D6 | Newer user intent overrides conflicting inherited creative preferences (principle 3) | Partially present for duration (`duration_target_source`), absent as a general objective framing in the Revise block. | `__init__.py:530-537`, `:1098-1102` |
| D7 | Base video's actual plan/duration is the revise starting point, not stale Story targets | Fixed in the prior session (iOS `baseTargetSeconds`), confirmed live (job `467cbc43` ran at the base's ~152.5s, not a stale 16.5s). KEEP. | iOS `StoryResultView.baseTargetSeconds` |

**Net finding.** The fast-path architecture (D3) and the Revise-vs-Explore objective separation (D4) are already
correct and must be preserved. The two real problems are: **(A)** the model-path Revise is under-specified — it
never receives the base plan to preserve (D1), and **(B)** preservation is enforced as a **blanket terminal
rejection** rather than an **objective** (D2), so a 5-minute valid revise is discarded over a soft clip-set delta
(observed: job `467cbc43` — "10 clips introduced" rejection on *"Start with Moment 1, shorten each clip to ~5s,
make it more cinematic"*). D5 is a latent bug that compounds B.

No broad historical re-investigation was done (owner instruction). This is the targeted reconcile only.

---

## Phase 1 — Revise vs Explore semantics (preserved, sharpened)

No merge of the two objectives. Concretely:

- **Revise** (`mode:"revise"`, has `base_plan`): the USER-message objective becomes (text-only, USER message,
  frozen system body untouched):
  > "Apply the user's latest requested changes to THIS existing edit (the base plan below). Preserve its
  > footage, order, timing, audio and creative decisions wherever they do not need to change. Make additional
  > editorial changes only when reasonably necessary to fulfil the request. Where an earlier creative preference
  > conflicts with the latest request, the latest request wins."

  And the **exact `base_plan` is injected** (D1 fix) so the model has something concrete to preserve and diff.
  Revise is never asked to diversify.
- **Explore** (`mode:"explore"`): the existing "MEANINGFULLY DIFFERENT yet valid" objective is unchanged.

Both remain append-only (new `GeneratedOutput`, previous versions preserved) — unchanged.

---

## Phase 2 — Deterministic vs AI execution (keep simple, no taxonomy)

Routing stays the current three-branch shape — **no new classifier, no keyword taxonomy**:

1. Pure structural (reorder/exclude/opening/ending/order) + no residual soft → `apply_deterministic_revision`,
   0 Bedrock, validate, render. (Exists, keep.)
2. Pure supported retime (no directives, parseable clip length) → `apply_deterministic_retime`, 0 Bedrock.
   (Exists, keep.)
3. Change-music-only → existing Change Music op, 0 Bedrock. (Exists, keep.)
4. Anything with residual creative intent deterministic editing cannot fulfil → **one** AI revision call with
   the exact base plan + the latest instruction + already-resolved structural directives as context. No second
   AI stage; no AI pre-pass before a deterministic edit; no AI post-pass after a successful deterministic edit.

The only change here is **D1**: branch 4 must actually carry the base plan (today it does not).

---

## Phase 3 — Newer intent precedence

Add the "latest request wins over conflicting inherited preference" framing to the Revise objective (Phase 1
text). Duration precedence already works via `duration_target_source` (keep). No per-example rules — the model
resolves ordinary creative ambiguity editorially; we do not add clarification round-trips.

---

## Phase 4 — Relax blanket preservation rejection (the core change)

**Technical validation stays mandatory and unchanged** — `validate_plan` continues to enforce: EditPlan/2
structure, known/authorized source-media ids, valid source ranges, renderer-feasible timing/speed/transitions,
native-audio policy, and any HARD directive predicate. A plan that fails `validate_plan` is still rejected. **We
do not weaken the validator.**

**Editorial continuity becomes an objective, not a terminal gate.** Replace the blanket
`_preservation_violation → EditPlanInfeasibleError` with a graded policy:

- Compute the base-vs-revised **clip-set delta** (added / removed / reordered / retimed) exactly as today — but
  use it as a **diagnostic signal**, not an automatic rejection.
- **Accept** a technically-valid revise that reasonably fulfils the latest request even when the clip set
  changed, provided:
  - every HARD directive is satisfied (validator predicates — unchanged), and
  - the change is not a **no-op** (principle: a directed revise that produced no effective change is an honest
    "couldn't apply that", never saved as success — keep this check), and
  - the change is not a **wholesale replacement** of an unrelated edit. Define a bounded **continuity floor**:
    the revised plan must retain a minimum fraction of the base clip set UNLESS the latest instruction's own
    semantics require otherwise (an explicit `exclude`, a shorter duration that drops clips, an explicit
    "focus on the best shots"). The floor is a single tunable (proposed: retain ≥ ~50% of base clips for a
    revise that carries no selection-changing instruction), surfaced in diagnostics — **not** a per-keyword
    rule and **not** a mode classifier.
- **Record** the delta in `rev_diag` (added/removed/reordered counts, continuity ratio) for the Phase-6 cost/
  quality metrics regardless of accept/reject.

**D5 fix (prerequisite):** correct `_preservation_violation`'s `authorized` extraction to read the directive
**dict** (`opening`, `ending`, `must_include`, `exclude`, `order_after`/`order_adjacent` pairs) instead of
iterating it as a list of dicts. This makes exclude/add-Moment revises work AND makes the continuity floor's
"instruction-authorized change" logic correct.

No Exact/Guided/Creative mode classification is introduced (owner).

---

## Phase 5 — Duration & pacing

Already aligned: base plan's actual duration is the starting point (D7, fixed + confirmed live); the undershoot
floor is relaxed for an `ai_recommended` timing revise so shorter clips/faster pacing may shorten the total;
`user_exact` duration is honored when feasible. **One addition:** do not add footage merely to hold an inherited
duration the user did not request — for a mixed retime+creative revise the AI path should be allowed to let the
total shorten rather than padding with new clips to hit the old length (this is what caused the
"10 clips introduced" rejection — the model padded to ~152.5s). This is covered by the Phase-4 continuity-floor
"instruction authorizes a shorter total" carve-out plus the existing relaxed undershoot.

---

## Phase 6 — Latency & cost (measurement, not new infra)

Extend `rev_diag` (already logged to CloudWatch) with, per revise: `revision_path`, `model_calls`,
`executability_repairs_used`, continuity ratio + added/removed/reordered counts, preservation outcome
(accepted / rejected-noop / rejected-wholesale), and wall-clock to playable. No billing system, no CloudWatch
dashboard build (out of scope) — these are fields on the existing diagnostic the worker already emits. The
governing rule: **never spend minutes producing a valid revision then discard it over a soft delta** (Phase 4),
and **never weaken technical validation to achieve that**.

---

## Exact changes (backend + iOS) — for approval, NOT yet implemented

**Backend (`packages/edit_planner`), request/routing/validator only:**
1. `_revision_context_block`: for `mode==revise`, inject the exact `base_plan` JSON and the Phase-1 objective
   (newer-intent-wins + preserve-unaffected). USER message only. (D1, D4, D6)
2. `_preservation_violation` → rename/repurpose to `_continuity_assessment`: returns a graded result
   (added/removed/reordered, continuity ratio, authorized set correctly built from the directive dict) instead
   of a single rejection string. (D5 + Phase 4)
3. `generate()` gate at `:1591`: replace the terminal raise with the Phase-4 accept/record/reject-only-on
   (no-op OR wholesale-below-floor-without-authorization) policy. Keep the no-op rejection and the
   never-substitute-a-different-video guarantee.
4. `rev_diag`: add the continuity + cost fields (Phase 6).
5. New deterministic predicate(s) already exist for HARD directives — unchanged.

**iOS:** none required for Phase 4 itself. The existing messages (`preservationViolation`,
`directivesUnsatisfiable`, `unsupportedOperation`) stay; a revise that is now ACCEPTED simply renders. Optional:
tune the `preservationViolation` copy to the narrower "couldn't apply without replacing your whole edit" case,
since blanket rejections become rare. No wire-schema change.

**Deterministic fast paths:** unchanged (D3). **Explore:** unchanged (D4). **EditPlan/2 schema & `edit_plan/5.2`
system body:** unchanged.

## Effect on Revise vs Explore, fast paths, Bedrock cost

- Revise vs Explore distinction is **preserved and sharpened** (Phase 1): different objectives, Revise carries
  the base plan, Explore keeps diversity.
- Fast paths are **unchanged** — a pure reorder/retime/change-music still costs **0 Bedrock calls**. Cost only
  changes for mixed structural+creative revises, which already take one AI call today; Phase 4 means that one
  call's valid output is now usually **accepted** instead of discarded — **strictly fewer wasted 5-minute
  runs**, not more calls.
- No second AI stage is introduced (owner).

## Frozen-contract / prompt changes

**None.** All new instruction text enters via the USER message (the proven `creative_brief`/`revision_context`
seam). The EditPlan/2 output schema and the `edit_plan/5.2` system body are untouched. No new wire request field
is required (the base_plan already travels in `revision_context`; this amendment only starts *using* it in the
USER message and changes server-side routing/validator logic).

---

## Architecture gate

This changes the previously frozen revision-**preservation policy** (terminal rejection → graded objective). Per
owner instruction: **STOP here for owner architecture approval before any implementation or deployment.** Once
approved, Phase 7 regression tests (reorder/retime 0-Bedrock; mixed uses AI; newer-intent-overrides; add/remove
when necessary; no wholesale replacement; Explore diversity intact; the 166s TMB
*"Start with Moment 1, shorten each clip to ~5s, make it more cinematic"* acceptance) run before the device gate.

---

## Implementation — Phases 1-6 + Phase 7 tests (owner-approved 2026-10-21) [committed, NOT deployed]

App commit `7c2c126` on `feat/r1-account-ownership-isolation`. Backend-only; `edit_plan/5.2` system body +
EditPlan/2 schema UNTOUCHED; no wire-field change. iOS unchanged.

**`packages/edit_planner/__init__.py`:**
- `_preservation_violation` → replaced by `_continuity_assessment` (graded dict verdict `ok`|`noop`|`wholesale`
  + continuity_ratio + added/removed/reordered) and `_directive_authorized_ids` (D5 fix — reads the directive
  DICT: opening/ending/must_include/exclude/order_after/order_adjacent, lowercased; the old code iterated it as
  a list of dicts so `authorized` was always empty). `CONTINUITY_FLOOR = 0.5`.
- `generate()` gate 6a: the terminal preservation raise is replaced by the graded gate — a valid revise is
  ACCEPTED even when the clip set changed; rejected ONLY on `noop` (no effective edit) or `wholesale`
  (continuity < floor AND the instruction authorized no selection change). `diag["continuity"]` is always
  recorded (Phase 6 signal).
- `_revision_context_block` revise branch (D1): injects the EXACT `base_plan` JSON + a "REVISE the existing
  edit / preserve unaffected / LATEST request wins / do not re-cut for novelty" objective into the USER
  message; Explore's `prior_edit_summaries` are no longer rendered for revise.
- Phase 5: new `_has_retime_intent` relaxes the AI-recommended undershoot floor for a retime/shorter revise
  EVEN WHEN a structural directive is also present (previously only a directive-free timing-only revise), so a
  mixed "open with Moment 1 + shorten each clip" revise may legitimately shorten the total instead of padding
  with new clips to hold the inherited duration. `_is_timing_only_revise` (gate for the 0-model deterministic
  retime fast path) is unchanged.

**`apps/api/tests/test_edit_planner.py`:** updated the re-pick test to the wholesale semantics; +7 Phase-7
tests (accept-within-floor, reject-noop, shorter-authorizes-drop, `_directive_authorized_ids` D5 unit,
base-plan-injected-for-revise, explore-block-unchanged, TMB mixed-retime acceptance).

**Verification:** `apps/api/tests` **360 pass** (was 355). The exact TMB instruction verified end-to-end against
the engine: `final=executable`, continuity `ok` ratio 1.0, opens with Moment 1, 85s → 30s (shorter allowed),
all clips preserved, ~5s each. Deterministic fast paths (reorder/retime/change-music 0-Bedrock) and Explore's
diversity objective unchanged (Phase-7 items 1, 2, 8, 9 covered by existing + new tests).

**STOP — awaiting owner approval to deploy** (CodeBuild → App Runner API + CDK worker) and device acceptance on
the real 166s TMB. Nothing pushed/deployed.

## Device acceptance (2026-10-21) — ACCEPTED

Owner rebuilt `feat/r1-account-ownership-isolation` and revised the 166s TMB with *"Start with Moment 1, shorten
each clip to ~5s, make the video more cinematic"*. Worker job `2773cb98` (backend live, API+worker dev):
`mode=revise`, `directive_keys=["opening"]`, **`opening_honored=true`** (seg0 = opening Moment), `model_calls=1`,
`first_pass_executable=true`, `repairs=0`, `revision_path=null` (AI path), `dur_src=ai_recommended` — **no
preservation_violation, no retime_reject**. The graded continuity gate ACCEPTED the shorter, Moment-1-opening,
all-clips-preserved revise instead of discarding it. Milestone COMPLETE + device-accepted. Not merged to master
(PR workflow); not a production deploy.
