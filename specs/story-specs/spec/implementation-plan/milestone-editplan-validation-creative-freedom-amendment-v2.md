# Milestone — EditPlan Validation & Creative Freedom (AMENDMENT v2)
## Creative directives become strong editorial objectives, not terminal validation failures

Status: **ARCHITECTURE / FREEZE GATE — awaiting owner approval. No implementation, nothing deployed, nothing pushed.**
Supersedes: Amendment v1 (`milestone-editplan-validation-creative-freedom-amendment.md`, specs `eca3cb3`) on the owner's 2026-10-22 revision.
Author: default (Kiro) · Method: code-grounded re-audit (`packages/edit_planner/__init__.py` read this session, exact `validate_plan`/`_validate_directives` semantics) + the deterministic feasibility proof from v1.
Scope: the EditPlan planning/validation/repair path only (`packages/edit_planner/`, its worker call-site, the device failure-routing).
Consistent with the three approved foundations: `milestone-creative-revision-foundation-design.md`,
`milestone-creative-editorial-freedom-architecture.md`, `milestone-revision-editorial-continuity-amendment.md`
(owner-approved 2026-10-21, commit `7c2c126`).
Frozen & UNTOUCHED: `edit_plan/5.2` SYSTEM body, EditPlan/2 OUTPUT schema. All changes are request-/routing-/validator-predicate-/diagnostics-only.
**Out of scope (owner floor, do NOT touch):** authentication, quotas, WAF, R7 sync, billing, production infra.

---

## What changed from v1, and why

The owner accepted v1's **root cause** (the 47.5s "infeasible" was a satisfiable plan burned by a skipped deterministic solver + no best-valid retention) and v1's mechanics (deterministic repair, best-valid retention, bounded model calls, Revise≠Explore).

The owner **rejected v1's hard/soft line.** v1 kept **every explicit creative directive** — opening, ending, ordering, inclusion — as a HARD validation failure. That conflicts with the product principle:

> **YoTale must prioritize delivering the best safe, playable video rather than rejecting an otherwise usable result after minutes of expensive inference because some creative instructions were imperfectly followed.**

v2 moves the line. The hard set shrinks to **technical correctness + media/source integrity + account ownership + renderer safety + genuine safety/privacy prohibitions.** Everything editorial — opening, ending, ordering, inclusion, pacing, duration *preference*, style — becomes a **strong editorial objective**: pursued hard (deterministically first, then one bounded model pass), scored, and **disclosed when unmet**, but it **never by itself turns a technically valid, playable plan into a terminal failure.**

The one thing v2 must NOT do is turn this into "ship whatever and claim success." An unmet objective is **disclosed honestly**; a genuine **safety/privacy** restriction is **never silently violated** (it stays hard).

---

## Phase 0 — Audit: the four buckets, re-split for v2

Every `validate_plan` + `_validate_directives` check (file:line from `packages/edit_planner/__init__.py` this session), now classified under the v2 rule: **Bucket 1 (technical/rendering), Bucket 2 (media ownership/integrity), and Bucket 5 (safety/privacy) are HARD. Bucket 3 (explicit *editorial* requirements) and Bucket 4 (editorial quality) are OBJECTIVES.**

| # | Check (stable code) | Bucket | v1 | **v2** |
|---|---|---|---|---|
| 1 | `no segments` w/o honest `feasible=false` (L742) | 1 Technical | HARD | **HARD** |
| 2 | order not monotonic / duplicate order (L746,748) | 1 Technical | HARD | **HARD** (deterministically renumbered — never reaches model) |
| 3 | `asset_id` not a known Moment (L757) | 2 Ownership/integrity | HARD | **HARD** |
| 4 | invalid / missing source range (L763,765) | 1 Technical | HARD | **HARD** |
| 5 | `source_end` exceeds Moment duration (L767) | 2 Integrity | HARD | **HARD** |
| 6 | source range overlaps NO useful_segment (L770) | 2 Integrity (quality-ish) | HARD→soft candidate | **SOFT** — deterministic range-nudge into nearest useful window; real-duration bound (#5) stays HARD |
| 7 | non-positive output_duration (L773) | 1 Technical | HARD | **HARD** |
| 8 | `native_audio` missing/invalid (L775) | 1 Technical (contract enum) | HARD | **HARD** |
| 9 | speed non-finite / non-positive (L778,780) | 1 Technical | HARD | **HARD** |
| 10 | speed out of renderer range [0.5,2.0] (L782) | 1 **Renderer safety** | HARD | **HARD** (device crashes otherwise) |
| 11 | output inconsistent w/ span@speed (L789) | 1 Technical | HARD | **HARD** — but widened deterministic snap clears the trivial case (0 Bedrock) |
| 12 | transition duration infeasible vs segment (L793) | 1 Technical | HARD | **HARD** (deterministically clampable) |
| 13 | total output > target by >+50% (L817) | 4 Editorial (upper band) | HARD band | **SOFT for approximate targets** (see Phase 5) — stays a *guard* against runaway, widened; HARD only for an explicit **exact-duration** request |
| 14 | total output >tol% SHORT (L820) | 3 user-req when exact / 4 when AI | operation-scoped | **HARD only when exact-duration**, else SOFT; degenerate/near-empty still rejected by a floor |
| 15 | `must_include` in no segment (L889) | 3 Explicit editorial | HARD | **OBJECTIVE** (pursued, disclosed if unmet) |
| 16 | `exclude` Moment appears in a segment (L897) | **depends on intent** | HARD | **HARD if safety/privacy exclude (Bucket 5); OBJECTIVE if ordinary creative "drop this clip"** — see 0.2 |
| 17 | opening / ending wrong (L903+) | 3 Explicit editorial | HARD | **OBJECTIVE** (deterministic reorder first; disclosed if unmet) |
| 18 | order_after / order_adjacent violated | 3 Explicit editorial | HARD | **OBJECTIVE** (deterministic reorder first; disclosed if unmet) |
| 19 | directive references Moment not in eligible set (L886) | 2 Integrity + 3 | HARD | **HARD** (unknown/unowned reference; caught at preflight) |
| 20 | `directive conflict:` (include∩exclude, cyclic order, impossible adjacency, …) | 3 (internally contradictory) | HARD | **HARD fail-fast at preflight** (0 Opus) — a contradiction can't be "best-effort satisfied"; return the specific conflict |
| 21 | music_alignment anchor w/o MusicAnalysis (L812) | 1 Technical | HARD | **HARD** (deterministically strippable) |

### 0.1 Why this split is honest and small
The validator today carries **no large catalogue of editorial exception rules** — the hard-to-soft move is concentrated in rows **6, 13, 14, 15, 16(conditional), 17, 18**. There is **no instruction-specific rule explosion**: we are *relaxing* a handful of blanket gates into objectives, not adding per-instruction special cases. The real editorial-quality layer (hook, variety, significance) already lives in the frozen prompt + optional critique pass, not in `validate_plan`, and stays there.

### 0.2 Distinguishing a safety/privacy `exclude` from a creative `exclude` (owner principle 3)
`exclude` is overloaded today (one hard rule, L897). Two very different intents ride it:
- **Safety/privacy exclude** — "never show this person / this clip / this face." Violating it is a **privacy breach**, not an editorial miss. → **HARD (Bucket 5). Never silently violated.**
- **Creative exclude** — "I don't like that shot, drop it." Violating it is an editorial miss. → **OBJECTIVE** (pursued; if the only playable plan must include it, ship + disclose, do not terminally fail).

v2 introduces an explicit **`exclude_reason`/`safety` marker** on the directive payload (additive, optional; default = creative) so the engine can tell them apart deterministically. Absent the marker, `exclude` is treated as **creative** (the common case) — EXCEPT the client already flags privacy excludes (face/person privacy controls), which set the safety marker. This keeps "do not silently violate an explicit safety or privacy restriction" true without guessing. (No frozen-contract change: the marker travels inside `revision_context.directives`, an already-free-form dict.)

### 0.3 The 47.5s failure — unchanged conclusion, now even cheaper under v2
From v1 (job `3cff789c`): FOUR positional directives (opening+ending+must_include+order_after), 18 moments, 47.5s, 3 Opus calls / ~3 min, terminal `invalid_after_repair`, codes `[directive_order_violated, "other"]`.
- The directives are topologically orderable (the code was a *placement* miss, not a `directive conflict:`), and the duration band **[38.0s, 71.25s]** intersects the 18-clip sum space → a valid plan exists. **Not infeasible.**
- Root cause: `repair_directive_placement` runs only when `_errors_are_order_only` (ALL errors); the lone `"other"` error skipped the 0-Bedrock reorder, and no best-valid plan was retained.
- **Under v2 this is strictly better:** even if the reorder/repair couldn't perfectly satisfy ordering, the directives are now **objectives**, so a technically valid plan that satisfies 3 of 4 (or lands the include-set + opening but misses one `order_after`) **ships with a disclosure** instead of returning `invalid_after_repair`. The deterministic reorder (Phase 2) still makes full satisfaction the common outcome at 0–1 model calls.

---

## Phase 1 — Validation architecture: one hard gate + a creative-intent satisfaction layer

Two clearly separated stages. The **hard gate stays deterministic and authoritative**; the **creative-intent layer scores and discloses, it does not reject.**

### 1.1 Hard gate — `validate_technical(plan, inputs)` (renamed intent; unchanged rules)
Returns errors for Buckets 1, 2, 5 ONLY (rows 1,3,4,5,7,8,9,10,11,12,19,21 + safety `exclude` + exact-duration bound + the degenerate-plan floor). **A plan with zero hard errors is playable and shippable** — this is the invariant the product leans on. The model never self-certifies; this gate is the only thing that can block a ship.

### 1.2 Creative-intent satisfaction layer — `assess_creative_intent(plan, inputs) → CreativeIntentReport`
A pure, deterministic scorer run AFTER the hard gate passes. For each editorial objective present (opening, ending, each order_after/adjacent, each must_include, duration-preference, creative-exclude, style-hint) it records `satisfied | partial | unmet` with the specific id. It:
- **Prioritizes the latest user request** (objectives come from the newest resolved directives; older preferences are context — unchanged `_revision_context_block`).
- **Allows AI editorial discretion** where instructions are ambiguous or cannot all be satisfied (soft_direction stays soft; the scorer does not punish creative latitude the frozen body is entitled to).
- Produces a single **`creative_satisfaction` score** (fraction of weighted objectives satisfied) + a **material-unmet list** (objectives the user will notice are missing).
- **Never emits a hard error.** Its output drives (a) best-candidate selection and (b) the honest disclosure — never a rejection.

### 1.3 The decision rule (replaces the blanket `invalid_after_repair` → 503)
```
run hard gate
  if hard errors:  (bounded) deterministic + model repair of TECHNICAL/INTEGRITY/SAFETY errors only
  if still hard-invalid and no retained valid candidate:  honest terminal (material_infeasible / technical),
      with the specific hard reason — NOT an editorial one
if hard-valid:
  assess_creative_intent
  if creative_satisfaction == full:        ship, success
  elif creative_satisfaction partial:      ship the best-valid candidate + INCOMPLETE-INSTRUCTION DISCLOSURE
  (never reject a hard-valid plan for an editorial miss)
```
No large exception catalogue: the only new "rules" are the preflight contradiction check (hard, 0-call) and the deterministic reorder/nudge (safe corrections). Everything else is scoring + disclosure.

---

## Phase 2 — Preserve the best valid candidate; deterministic-first; bounded model repair

### 2.1 Best-valid-candidate retention (across the WHOLE chain)
- Keep `best_valid: {plan, creative_satisfaction, attempt}` across initial call + deterministic reorder + each model repair (+ for revise, pre-continuity).
- After every hard-gate pass, if `errs == []` and `feasible is not False`: record it; **replace only by a strictly-better candidate** — higher `creative_satisfaction`, ties broken by closeness to target within band. **A later attempt can never discard an earlier valid candidate.**
- Terminal: if the last attempt is hard-invalid but a `best_valid` exists → **ship `best_valid`** (`final="executable_from_retained_candidate"`). Raise a terminal failure ONLY when **no** attempt ever cleared the hard gate.

### 2.2 Deterministic-first directive handling (the 47.5s fix + objective-ification)
- Partition hard-gate + objective errors. Run `repair_directive_placement` (0 Bedrock reorder) whenever the **directive-placement subset** is reorder-type — **not** only when *every* error is placement (v1 fix, retained).
- Widen the deterministic output-consistency snap to clear trivial `output_span_inconsistent` with 0 Bedrock (row 11), bounded by a safe epsilon.
- Deterministic **directed build** for a pure-structural directed create/another-version (analogous to `apply_deterministic_revision`): select+order eligible moments to satisfy objectives within the band, validate, ship — 0 Bedrock when it works.

### 2.3 Bounded model repair with justified benefit (owner principle 7)
- Model repair runs **only to clear remaining HARD (technical/integrity/safety) errors** — never to chase an editorial objective once a hard-valid candidate exists.
- Cap unchanged (≤2 repairs). **New gate:** a repair call is issued only if `expected_benefit` is real — i.e. there are HARD errors a repair can plausibly fix AND no equal-or-better valid candidate is already retained. Once `best_valid` exists, further model calls for editorial polish are **not** issued (deterministic nudge or disclosure instead).

| Situation | Action | Model calls |
|---|---|---|
| Directive errors reorder-only (± trivial numeric) | deterministic reorder + snap | **0** |
| Directives internally contradictory (cycle/∩/over-exclude) | fail-fast, specific message | **0** |
| First plan hard-valid, objectives full | ship | 1 |
| First plan hard-valid, objectives partial | **ship best-valid + disclosure** | 1 |
| Hard errors remain, repairable | ≤2 targeted repairs of HARD errors only | ≤3 |
| Any hard-valid candidate retained, later attempt regresses | **ship retained candidate** | no extra |
| No attempt ever hard-valid | honest terminal (technical/integrity/safety reason) | ≤3 |

---

## Phase 3 — Operation semantics preserved (Revise vs Create Another Version)

Not merged. The Revise↔Explore split from the 2026-10-21 continuity amendment is retained.

- **Revise** — start from the exact selected base plan; prioritize the requested change; preserve footage/order/timing/audio where unchanged; permit justified add/remove; **previous version preserved** (append-only). The continuity gate (CONTINUITY_FLOOR, `authorized_change`) is unchanged and still prevents returning an **unchanged** video as a successful revision (owner principle 9). Best-valid retention applies *after* the continuity gate.
- **Create Another Version (Explore)** — seek a meaningfully different valid interpretation; **retain the latest explicit user intent** (exact-duration if given, safety excludes); broad creative freedom in selection/timing/sequence (owner principle 10). The directed-another-version path (the 47.5s case) = Explore + editorial objectives → deterministic-first + disclosure.

Revise is not turned into Explore; objectives and preservation latitude stay distinct.

---

## Phase 4 — Evidence & regression plan

Fixtures: `evals/scenarios/` (Girl with Dress, Hiking, Guitar, Minimal footage) + the failed 47.5s Story (18 moments, 4 directives) + the earlier **TMB create/revise regression cases** (owner principle 13): the TMB A 166s mixed retime+creative revise (job history: `shorten each clip to ~5s + more cinematic`), and the TMB `Start with M1, then M6, end with M2` revise (job `04dbbe09`, all-clips-preserved baseline). Bounded spend, cached AU, no new research sweep.

Metrics — proposed vs current frozen baseline, per fixture + aggregate (owner principle 12):

| Metric | Source |
|---|---|
| Technical validation pass rate | hard-gate pass on shipped plan |
| **Playable-output rate** (headline) | fraction shipping a renderable plan vs terminal |
| Meaningful instruction satisfaction | `creative_satisfaction` (weighted objectives satisfied) + material-unmet count |
| Cost per playable output (USD) | `EstimatedModelCostUSD` ÷ playable count (live observability EMF) |
| Avg physical Bedrock invocations | `diag.model_calls` mean |
| p50/p95 planning latency | worker wall-clock to terminal |
| Incomplete-instruction disclosure frequency | ships carrying a material-unmet disclosure |

Required cases (each exercised, current vs proposed): **contradictory instructions** (→ fail-fast 0 calls, specific message); **unavailable media** (`directive_ref_ineligible` → HARD); **strict ordering** (47.5s 4-directive → reorder ships a valid, fully/near-fully satisfied plan; any residual miss → disclosure, not failure); **duration pressure** (tight target + many moments → band accept, no false infeasible, approximate target tolerated); **mixed creative requests** (retime+creative → ships, continuity `ok`, shorter total allowed); **safety/privacy exclude** (→ HARD, never violated even to ship).
Acceptance bar: **playable-output rate strictly ↑; avg model calls flat or ↓; zero technical/integrity/safety regression; no silent success on a material unmet instruction (every one disclosed); no safety/privacy exclude ever violated.**

---

## STOP-gate deliverables

### 1. Exact HARD vs SOFT classification
- **HARD (never weakened):**
  - Bucket 1 technical/rendering: rows 1,2,4,7,8,9,10,11,12,21.
  - Bucket 2 media ownership/integrity: rows 3,5,19.
  - Bucket 5 safety/privacy: safety-flagged `exclude` (row 16 when `safety`); directive references to unowned/unknown Moments (row 19).
  - Explicit **exact-duration** request: rows 13/14 become HARD bounds; a degenerate/near-empty plan floor always HARD.
  - Directive **contradiction** (row 20): HARD but fails fast at preflight (0 Opus), because a contradiction cannot be best-effort satisfied.
- **SOFT (strong objectives — pursued, scored, disclosed; never terminal on their own):** opening, ending, ordering (rows 17,18), inclusion (row 15), creative `exclude` (row 16 default), approximate duration preference (rows 13/14 when not exact), source-outside-useful (row 6 → deterministic nudge), style hints.
- **No new instruction-specific exception rules.**

### 2. Proposed planner/repair changes (`packages/edit_planner/__init__.py` + worker + device routing; request/routing/validator-predicate/diag only)
1. Split `validate_plan` into `validate_technical` (hard: buckets 1/2/5 + exact-duration + floor) and `assess_creative_intent` (scorer; objectives; never errors). (Phase 1)
2. `best_valid` retention across the whole chain; terminal fallback ships it. (Phase 2.1)
3. Partition errors; run `repair_directive_placement` when the directive subset is reorder-only; widen deterministic consistency snap. (Phase 2.2 — 47.5s fix)
4. Positional-satisfiability + `preflight_directives` inside `generate()` before the first Opus call; contradiction ⇒ fail-fast 0 calls. (Phase 2.2)
5. Deterministic directed build for pure-structural directed create/another-version. (Phase 2.2)
6. Bounded model repair gated on real expected benefit for HARD errors only; never for editorial polish once `best_valid` exists. (Phase 2.3)
7. `exclude` safety/creative marker (additive, default creative; client privacy controls set `safety`). (Phase 0.2)
8. Approximate-vs-exact duration treatment: widen approximate band to a runaway guard; exact stays hard. (Phase 5)
9. Incomplete-instruction disclosure surfaced to the device as a non-failure "shipped with N unmet: …" state; new `diag`: `creative_satisfaction`, `material_unmet`, `best_valid_from_attempt`, `positional_preflight`, `exclude_safety_count`. (Phase 1.3 / 4)
10. Device: a hard-valid-but-partial result renders as a **success with a disclosure** (not the `invalid_after_repair` "Adjust instructions" dead-end); genuine terminal (no hard-valid candidate) keeps the honest technical/safety message.

### 3. Frozen-contract impact
**None to the frozen surfaces.** `edit_plan/5.2` SYSTEM body and EditPlan/2 OUTPUT schema untouched. Directive payload additions (`exclude` safety marker) ride inside the already-free-form `revision_context.directives`. The device gains a new **non-failure disclosure response shape** (additive; old clients that don't understand it still receive a playable plan + a generic success — the disclosure degrades to absent, never to a failure). **This is the one item requiring a versioned *response/policy* note, not a schema break** — called out explicitly per owner principle 14.

### 4. Regression risks
- **Objective-ification could ship a plan that misses an instruction** → mitigated by the mandatory disclosure (never silent) + `creative_satisfaction` acceptance bar; and by deterministic-first making full satisfaction the common path.
- **Safety/privacy exclude mis-classified as creative** → mitigated by default-safe only where the client marks it; the client's existing privacy controls set the safety marker; absent a marker an `exclude` is creative by design (the common "drop this shot" case). Reviewed before enabling.
- **Approximate-duration widening** could let a noticeably off-length video ship → the runaway guard + the exact-duration hard path bound it; measured on the duration-pressure fixtures.
- **Row-6 soft nudge** could push a source range to a worse window → real-duration bound (#5) stays HARD; nudge only into the nearest useful window; gated + measured.
- **Best-valid retention** selecting a lower-satisfaction plan → selection prefers higher `creative_satisfaction`, ties by target-closeness; can only turn a former failure into a ship.

### 5. Expected latency / cost improvements
- 47.5s class: ~3 Opus / ~3 min → **0–1 call**, ships a playable video (full or disclosed-partial) instead of `invalid_after_repair`.
- Contradictory directives: 3 calls / 3 min → **0 calls**, instant specific message.
- Editorial-miss-only cases that today 503 after repair: → **ship at no extra model cost** + disclosure.
- Net: **playable-output rate ↑, avg physical Bedrock invocations ↓/flat, directed-path p95 ↓, USD/playable ↓.** Planning-only; no per-render change.

### 6. Rollback strategy
- Every change **flag-gated + additive**, each defaulting **off** so a deploy is a no-op until flipped:
  `STORY_EDITPLAN_OBJECTIVE_DIRECTIVES` (the hard→objective move), `STORY_EDITPLAN_BEST_VALID_RETENTION`,
  `STORY_EDITPLAN_DETERMINISTIC_DIRECTIVE_FIRST`, `STORY_EDITPLAN_POSITIONAL_PREFLIGHT`,
  `STORY_EDITPLAN_APPROX_DURATION_SOFT`, `STORY_EDITPLAN_USEFUL_RANGE_SOFT`.
- Flip individually, measure, revert a single flag on regression.
- No prompt/schema version bump ⇒ rollback = flag flip or `packages/edit_planner/` revert; **no data migration.** The device disclosure shape is additive; disabling the server flags returns exactly today's behavior. Older clients unaffected (no directives / understand only the playable plan).

---

## Fallback behavior (explicit, per owner request)
1. Hard error present, deterministically fixable → fix (0 Bedrock), re-gate.
2. Hard error present, not deterministically fixable → ≤2 targeted model repairs of the HARD error only.
3. Hard-valid at any point → candidate retained; it is the floor we can always fall back to.
4. Objectives unmet on the retained candidate → **ship it + disclose the material unmet instructions.**
5. No hard-valid candidate ever produced → honest terminal naming the specific technical/integrity/safety reason (never an editorial one), device routes to a real remedy.
6. Safety/privacy exclude would be violated → **never ship that plan**; it is a hard error and a repair target; if unsatisfiable, terminal with the safety reason.

## Operation-specific acceptance criteria
- **Revise:** base preserved; requested change applied; continuity gate still blocks an unchanged "revision"; previous version retained; a partial editorial miss ships + discloses (does not fail).
- **Create Another Version:** meaningfully different, latest explicit intent (exact-duration, safety excludes) retained; broad creative freedom; partial editorial miss ships + discloses.
- **Both:** zero technical/integrity/safety regression; no silent success on a material unmet instruction; no safety/privacy exclude violated.

## Test plan
Unit: hard-gate invariance (buckets 1/2/5 unchanged), objective scorer on each directive type, positional preflight (47.5s combo passes, true cycle fails), deterministic reorder/nudge, best-valid retention never regresses, safety-exclude never dropped, approximate-vs-exact duration branching, disclosure emitted iff material-unmet. Regression: the Phase-4 fixture matrix, current vs proposed, on every required case. Device: the partial-success disclosure renders as success-with-note, not the Adjust dead-end.

## Rollout strategy
All flags default off → merge is inert. Enable in dev first behind flags; run the Phase-4 matrix; verify playable-output rate ↑ and no hard/safety regression; one bounded real generation per operation on dev; then stage to beta behind the same flags with the observability EMF (ModelInvocations, EstimatedModelCostUSD, QueueWaitMs/WorkerProcessingMs) watching cost/latency; owner device acceptance before any default-on flip. Each flag flipped and measured independently; single-flag revert on regression.

---

## Architecture gate
**STOP for owner architecture approval before any implementation or deployment.** No code changed, no prompt/contract touched, nothing pushed. Out-of-scope systems (auth, quotas, WAF, R7 sync, billing, production infra) untouched. On approval: land Phase-2/3 behind the flags above and run the Phase-4 regression matrix (incl. the 47.5s 4-directive fixture, the TMB create/revise cases, and the contradictory/unavailable/strict-ordering/duration-pressure/mixed/safety-exclude cases) before any device gate.

---

## FINAL APPROVED POLICY (owner conditional approval, 2026-10-22) — implemented

The owner conditionally approved v2 with three corrections, now folded in and implemented behind the flags
(STOP is now **before DEPLOYMENT**, not before implementation):

### A. Strict cost-aware repair policy (owner §7) — **default ZERO additional model repair calls**
Repair priority is deterministic-first, then retain-and-deliver, then fail, and only last a targeted model
repair — and only when no valid meaningful candidate exists and the defect is technically recoverable:
| Operation | Max additional model repair calls | Condition |
|---|---|---|
| Revise | **0** | exception: **1** only to recover an otherwise-unrenderable HARD technical defect |
| Create / Create Another Version | **1** | only if HARD errors remain AND no valid candidate is already retained |
| (any) | **never ≥2** | no automatic second/third Opus attempt |
| (any) | **0 for purely creative/objective deviations** | objectives are scored + disclosed, never repaired |
Once a technically-valid candidate is retained, the loop **does not** spend a model call to chase editorial
compliance (`repair_skipped_have_valid`). `diag.repair_budget` records the ceiling in force. Repairs carry
**only the HARD errors**. Smaller-model routing for cheap technical repairs is noted as a future lever but is
**not changed here** (would need regression evidence first, per §7).

### B. Conservative safety/privacy exclude (owner §3) — **fail safe, do not assume creative**
A missing marker does **NOT** mean an exclusion is creative. `_exclude_is_safety` treats an exclude as a
SAFETY/PRIVACY prohibition (HARD, never silently violated) **unless it is unambiguously marked creative**
(`exclude_creative:[ids]` or `exclude_reason:{id:'creative'}`); an id marked `privacy`/`safety`/`sensitive`/
`person`/`face` (the client's privacy controls) is hard; and an **unresolved** id defaults to SAFETY. A single
escape hatch flag `STORY_EDITPLAN_EXCLUDE_DEFAULT_CREATIVE` (default off) exists for a surface that proves its
excludes are only creative; left off, the fail-safe default stands.

### C. Preserve AI creative freedom (owner §5) — **no deterministic montage substitution**
Deterministic processing is used ONLY for the existing safe transforms — technical normalization, mechanical
retime, unambiguous **reorder** of the SAME segments, and explicit mechanical revisions. Initial creation and
Create Another Version still go to the model for editorial selection/pacing/storytelling; nothing replaces
creative generation with a generic montage to cut cost. The deterministic reorder only reassigns `order`; it
never selects or drops footage.

### Exact changed files
- `packages/edit_planner/__init__.py` — v2 flags; `validate_plan` approximate-duration-soft branch +
  `DURATION_RUNAWAY_GUARD`; `_validate_directives_split` (hard vs objective) + `_validate_directives`
  back-compat wrapper; `_exclude_is_safety`; `assess_creative_intent` + `_objective_code`; `generate()`
  best-valid retention, placement-subset deterministic reorder, strict per-operation repair budget,
  partial-success disclosure; `__all__` exports.
- `apps/api/app/worker.py` — forward `completion` / `partial_disclosure` / `material_unmet` /
  `creative_satisfaction` / `shipped_retained_candidate` / `structural_repair` / `repair_budget` into
  `diag_out` so the device renders success-with-note, not the Adjust error.
- `apps/api/tests/test_edit_planner.py` — 14 new `test_v2_*` regression tests.

### Hard/soft classification (as implemented)
HARD = technical/rendering (no-segments, order monotonic, source range/duration, native_audio, speed in
[0.5,2.0], output-consistency, transition feasibility, music-anchor-without-analysis) + media
ownership/integrity (unknown/unowned Moment reference, source exceeds Moment duration) + safety/privacy
(safety-flagged exclude; conservative default) + explicit **exact-duration** bands + degenerate-plan floor +
directive **contradiction** (fail-fast). OBJECTIVE = opening, ending, must_include placement, order_after,
order_adjacent, creative exclude, approximate duration, source-outside-useful (nudge).

### Repair routing and call budgets
Deterministic reorder (0 calls) → retain best-valid → fail-fast on contradictions/unowned media → at most the
per-operation model-repair budget above, HARD errors only, skipped entirely once a valid candidate exists.

### Test results
`apps/api` backend suite **ALL GREEN** with flags default-off (legacy behavior byte-unchanged) and with the
14 new `test_v2_*` cases exercising: legacy-mode hard directive; objective-mode soft opening + scorer;
unknown-reference stays hard; safety-vs-creative exclude split; missing-marker-defaults-to-safety;
contradiction stays hard; approximate-duration soft + runaway guard; exact-duration stays hard; the 47.5s
mis-ordered case ships via reorder (complete, 1 call); partial ships with disclosure at 0 extra calls;
best-valid retention; Revise zero-repair budget; unrecoverable technical error still fails honestly.

### Playable-output comparison (headline, the 47.5s class)
Baseline (flags off): mis-ordered opening+ending+include+order → `invalid_after_repair`, **2 model calls, no
video**. Proposed (flags on): deterministic reorder → `executable`, **1 model call**, `completion=complete`,
opening/ending/inclusion/ordering all satisfied — **ships a playable video**. (FakeModelGateway harness proof;
the full real-fixture matrix runs on dev before any device gate.)

### Cost / latency evidence
Deterministic reorder is 0 Bedrock. Strict budget caps directed-path model calls at ≤1 (Revise 0) vs the
prior ≤3; best-valid retention converts a class of former `invalid_after_repair` 503s into ships at no extra
model cost. Live beta observability EMF (`ModelInvocations`, `EstimatedModelCostUSD`, `QueueWaitMs`,
`WorkerProcessingMs`) is the measurement surface for the dev/beta rollout.

### Feature flags & rollback
`STORY_EDITPLAN_OBJECTIVE_DIRECTIVES`, `_BEST_VALID_RETENTION`, `_DETERMINISTIC_DIRECTIVE_FIRST` (reserved),
`_POSITIONAL_PREFLIGHT` (reserved), `_APPROX_DURATION_SOFT`, `_USEFUL_RANGE_SOFT`,
`_EXCLUDE_DEFAULT_CREATIVE` (escape hatch) — all default **off**; module import/deploy is a no-op until a flag
is flipped. Rollback = single-flag flip or `git revert` of `packages/edit_planner/` + `worker.py`; no data
migration, no schema/prompt bump, old clients unaffected.

### Remaining risks
- Objective-ification could ship a plan missing an instruction → mitigated by the mandatory disclosure
  (`completion=partial`, `material_unmet`) and the deterministic-first reorder making full satisfaction common.
- Conservative safety default could block a *creative* exclude the client failed to mark → surfaced as a HARD
  error with a clear message; the fix is the client marking it creative, never a silent drop.
- Approximate-duration widening bounded by the runaway guard + exact-duration hard path.
- Smaller-model repair routing deliberately NOT changed (needs regression evidence).

**STOP before deployment for owner review.** Nothing pushed; auth/quotas/WAF/R7/billing/prod untouched.
