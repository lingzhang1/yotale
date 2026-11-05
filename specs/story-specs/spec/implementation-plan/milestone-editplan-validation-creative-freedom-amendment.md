# Milestone — EditPlan Validation & Creative Freedom: Hard/Soft Split + Best-Valid-Candidate Retention (AMENDMENT v1)

Status: **ARCHITECTURE / FREEZE GATE — awaiting owner approval. No implementation, nothing deployed, nothing pushed.**
Owner decision prompt: 2026-10-22 · Author: default (Kiro) · Method: code-grounded re-audit (direct file:line read this session) + deterministic feasibility proof of the recent failure.
Scope: the EditPlan planning/validation/repair path only (`packages/edit_planner/`, its worker call-site).
Builds on and is consistent with the three approved foundations:
`milestone-creative-revision-foundation-design.md`, `milestone-creative-editorial-freedom-architecture.md`,
`milestone-revision-editorial-continuity-amendment.md` (owner-approved 2026-10-21, commit `7c2c126`).
Frozen & UNTOUCHED by this amendment: `edit_plan/5.2` SYSTEM body, EditPlan/2 OUTPUT schema. All proposed
changes are request-only / routing-only / validator-predicate-only / diagnostics-only.
**Out of scope (owner floor, do NOT touch):** authentication, quotas, WAF, billing, R7 sync, production infra.

---

## Phase 0 — Audit of the frozen design + the recent failure

### 0.1 What is implemented today (file:line verified, `packages/edit_planner/__init__.py`)

The planning path is a single `RealEditPlannerEngine.generate()` with these stages:

1. **Unsupported-op preflight** (revise only) — deterministic classify; whole-instruction-unsupported ⇒ keep user version; mixed ⇒ note.
2. **Deterministic fast paths** (0 Bedrock) — timing-only retime (`apply_deterministic_retime`), pure structural directive revise (`apply_deterministic_revision`). Revise only.
3. **One Opus planning call** → `validate_plan` (the hard gate) → safe `normalize_plan` (rounding snaps only) → re-validate.
4. **Deterministic directive-placement repair** (`repair_directive_placement`, 0 Bedrock) — **only when `_errors_are_order_only(errs)` is true** (every error is an opening/ending/order placement violation).
5. **Bounded model repair** — up to `executability_repair_attempts` (worker uses **2**) Opus calls carrying the exact validator errors.
6. **Authoritative verdict** — still-invalid ⇒ `StructuredOutputError` → worker maps to `invalid_after_repair` → API returns 503 / device shows "Adjust instructions".
7. **Editorial-continuity gate (6a)** — revise only; graded `ok`/`noop`/`wholesale` (the 2026-10-21 amendment; keep).
8. **Critique→revision (6b)** — flag-gated, OFF by default.

`validate_plan` is the single deterministic hard gate; the model never self-certifies. This is correct and must stay.

### 0.2 Classification of every validation error into the four buckets

Enumerated from `validate_plan` + `_validate_directives` + `preflight_directives`, with the stable code from `worker._validator_error_codes`.

| # | Validator check (code) | Bucket | Keep HARD, or make a quality SIGNAL? |
|---|---|---|---|
| 1 | `no segments` (and not an honest `feasible=false`) | **1 Technical** | HARD |
| 2 | `segment order not monotonic` / `duplicate order values` | **1 Technical** | HARD — but **deterministically repairable** (renumber), should never reach the model |
| 3 | `asset_id not a known Moment id` (`segment_unknown_asset`) | **2 Media ownership/integrity** | HARD |
| 4 | `invalid source range` / `missing source in/out` (`source_range_invalid`) | **1 Technical** | HARD |
| 5 | `source_end exceeds Moment duration` (`source_exceeds_duration`) | **2 Media integrity** | HARD |
| 6 | `source range overlaps NO useful_segment` (`source_outside_useful`) | **2 Media integrity** (quality-ish) | **HARD today; candidate SOFT** — see 0.5 |
| 7 | `non-positive output_duration` | **1 Technical** | HARD |
| 8 | `native_audio missing/invalid` | **1 Technical** | HARD (contract-required enum) |
| 9 | `speed non-finite / non-positive` | **1 Technical** | HARD |
| 10 | `speed out of renderer range [0.5,2.0]` (`speed_unrenderable`) | **1 Technical/rendering** | HARD (device crashes otherwise) |
| 11 | `output inconsistent with source span @ speed` (`output_span_inconsistent`) | **1 Technical** | HARD — but **deterministically repairable** (snap wider than the current snap window) |
| 12 | `transition duration infeasible vs segment` (`transition_infeasible`) | **1 Technical** | HARD — deterministically clampable |
| 13 | `total output > target by >+50%` (`duration_overshoot`) | **4 Editorial/quality** (upper bound) | HARD gate today; the +50% band is already generous — keep as a hard *band*, not an exact target |
| 14 | `total output >20% SHORT` (`duration_undershoot`) | **3 Explicit user req** when `user_exact`; **4 Editorial** when `ai_recommended` | Already operation-scoped (`_undershoot_tolerance_for`); keep |
| 15 | `must_include appears in no segment` (`directive_include_unplaced`) | **3 Explicit user req** | HARD |
| 16 | `exclude Moment appears in a segment` (`directive_exclude_violated`) | **3 Explicit user req** | HARD |
| 17 | `opening/ending wrong` (`directive_opening_unplaced` / `_ending_unplaced`) | **3 Explicit user req** | HARD — **deterministically repairable by reorder** |
| 18 | `order_after / order_adjacent violated` (`directive_order_violated`) | **3 Explicit user req** | HARD — **deterministically repairable by reorder** |
| 19 | `directive references Moment not in eligible set` (`directive_ref_ineligible`) | **2 Media integrity** + **3** | HARD (catch at preflight) |
| 20 | `directive conflict: …` (include∩exclude, excluded-but-ordered, cyclic order, impossible adjacency, opening/ending vs ordering) | **3 Explicit user req** (internally contradictory) | HARD — **catch at preflight, before any Opus call** |
| 21 | `music_alignment anchor set without MusicAnalysis` | **1 Technical** | HARD — deterministically strippable (anchor→none) |

**Buckets 1 & 2 (technical correctness, media ownership/integrity) must remain hard failures** — a plan that fails them is unrenderable or references footage the user does not own. **Bucket 3 (explicit user requirements)** must also stay hard (we never silently ignore a user instruction), but much of it is **deterministically satisfiable without the model** (17, 18, 20). **Bucket 4 (editorial/quality)** is where "do not reject a playable video for minor editorial deviations" applies — but note the current validator carries almost no pure bucket-4 rejections: the only soft-ish ones are the duration band (13/14), already generous and operation-scoped. The real editorial-quality layer the owner describes (hook, variety, significance) lives in the **prompt** and the **optional critique pass**, not in `validate_plan`.

**Conclusion of the classification:** the validator is already almost entirely hard-technical + hard-user-requirement, with no large collection of editorial exception rules to dismantle. The failure mode the owner is reacting to is **not** "the validator rejects playable videos for editorial nitpicks." It is: **a satisfiable hard-directive plan is burned through 3 Opus calls and still rejected because the cheap deterministic solver was skipped, and no earlier valid candidate was retained.** That is the precise thing to fix.

### 0.3 The recent failure (47.5s) — exact errors + feasibility proof

Authoritative diagnostics (`b0-p0sec-beta-acceptance-report.md` appendix, job `3cff789c`):
```
terminal            = invalid_after_repair
final_error_codes   = ["directive_order_violated", "other"]
directive_categories= ["ending", "must_include", "opening", "order_after"]  (FOUR hard directives)
usable_moment_count = 18
target_seconds      = 47.5
model_calls         = 3   (initial + 2 repairs),  ~3 min wall-clock
```

**The report concluded "no valid plan satisfies all four → honestly infeasible." That conclusion is not proven, and the deterministic analysis contradicts it:**

- The four directives are **opening + ending + must_include + order_after** — all **positional**. They are mutually consistent (the failure code was `directive_order_violated`, a *placement* miss — **not** a `directive conflict:` code, which is what an unsatisfiable combination emits). Placing `opening` first, `ending` last, `A after B`, and the include-set present is a **topological order over a tiny DAG on 18 nodes** — satisfiable for any non-cyclic, non-contradictory naming.
- The **duration** requirement is independent: the accept window at 47.5s is **[38.0s, 71.25s]** (−20% / +50%). Eighteen trimmable clips can sum to a total anywhere in that band (avg ~2.1–4.0s/clip, or fewer-but-longer). 
- The two requirement spaces **intersect** ⇒ **a technically valid, directive-satisfying candidate exists.** No mathematical infeasibility.

**Why it failed anyway (root cause):** the final errors were `["directive_order_violated", "other"]`. The deterministic `repair_directive_placement` (which would have reordered the SAME segments to satisfy opening/ending/order with **0 model calls**) only runs when **`_errors_are_order_only(errs)` is true** — i.e. *every* error is a placement error. The lone `"other"` error (an unrelated numeric/duration nit) disqualified the deterministic reorder, so the engine fell to Opus repair, which kept mis-ordering the segments. **A solvable ordering problem was handed to a stochastic model instead of the deterministic solver that exists two functions away, and when the model missed, a valid candidate was never reconstructed.**

This is the load-bearing Phase-0 result: **do not route this class to "create a shorter Story / adjust instructions." It is a planning/repair-orchestration defect, exactly as the owner suspected.** (Consistent with the stored lesson: a model-declared/flow-declared infeasibility must be corroborated against deterministic evidence before routing the user to a remedy.)

### 0.4 Where "infeasible" is claimed vs proven today

- `preflight_directives` DOES prove two real infeasibilities cheaply (before any Opus call): internal directive contradictions, and over-exclusion leaving < 2 moments. Keep. **But it is only wired into `/v1/interpret-revision`** (main.py:838) — the NL-interpretation step. It does **not** run inside `generate()` on the directed-create/another-version path, so a contradictory or over-constrained directed request still spends Opus calls before failing.
- There is **no joint positional-feasibility check** (can opening+ending+order+include be topologically ordered at all) and **no deterministic directed-build attempt** before the model is trusted to honor directives.

### 0.5 The one genuinely-soft candidate in buckets 1–2

Check #6 (`source range overlaps NO useful_segment`) is the single validator rule that is a **quality judgement masquerading as a hard gate**: a source range slightly outside the AU-tagged "useful" window is still *renderable* (the footage exists; AU's useful_segments are coherent regions, not frame-precise in/out points — see the stored AU lesson). Today it is HARD. Candidate: downgrade to a **repair-preferred signal** (nudge the range into the nearest useful window deterministically; only hard-fail if the range is outside the Moment's real duration, which is check #5 and stays HARD). This is the **only** validator rule this amendment proposes moving from hard to soft, and it is bucket-2-adjacent, so it is proposed **conservatively** (see Phase 1).

---

## Phase 1 — Proposed validation architecture (hard gate + creative-intent layer)

**Mandatory technical & integrity validation is preserved unchanged.** `validate_plan` keeps every bucket-1 and bucket-2 rule as a hard failure (rows 1,3,4,5,7,8,9,10,11,12,19,21), and every explicit-user-requirement rule (rows 15–18,20) stays hard. We do **not** weaken the validator and we do **not** add a collection of instruction-specific exception rules.

The "creative-intent satisfaction layer" the owner asks for is defined as a **thin routing + repair discipline around the existing gate**, not a second validator:

1. **Latest user request is prioritized** — already the Revise objective (`_revision_context_block`, newer-intent-wins) and `duration_target_source`. No change needed; this amendment only ensures the *directed* path actually reaches a directive-satisfying plan.
2. **Older compatible preferences are context** — unchanged (inherited directives follow the selected lineage; the system body carries creative-pacing freedom per the Editorial Freedom architecture).
3. **AI editorial judgement where instructions are ambiguous** — unchanged; soft_direction stays soft, the frozen body keeps creative freedom.
4. **Deterministic corrections where safe** — **expanded** (Phase 2): the deterministic reorder must run whenever the *directive* errors are order-only even if unrelated numeric errors coexist (fix them separately), and the output-consistency snap window is widened to cover trivially-fixable `output_span_inconsistent`.
5. **Do not auto-reject a playable video for minor editorial deviations** — codified as the **best-valid-candidate retention** policy (Phase 2): if any attempt produced a `validate_plan`-passing plan, that plan is shippable; we never discard it to chase an exact editorial target.
6. **Do not silently claim success when a critical explicit instruction was ignored** — preserved and strengthened: an unmet HARD directive (bucket 3) remains a hard failure (never silently accepted); and when we ship a retained valid candidate that could not satisfy a *soft* ask, we attach an **incomplete-instruction disclosure** (Phase 4 metric) rather than claiming full success.

Net: the "creative-intent layer" is a **disclosure + routing contract**, not new validation surface. This respects "avoid a large collection of instruction-specific exception rules."

---

## Phase 2 — Preserve the best valid candidate + bounded retry/stopping policy

The core behavioral change. Today each repair **overwrites** `plan`; if repair N regresses, the valid plan from repair N−1 is lost, and the final verdict reflects only the last (possibly worse) attempt.

### 2.1 Best-valid-candidate retention

- Maintain `best_valid: dict | None` across the whole `generate()` attempt chain (initial call, deterministic reorder, each model repair, and — for revise — before the continuity gate).
- After every `validate_plan`, if `errs == []` **and** `feasible is not False`, record the plan as `best_valid` (first valid wins; a later valid plan may replace it only if it is *also* valid and strictly preferred by a cheap deterministic score — e.g. closer to target within the accept band — never a worse one).
- **Terminal rule:** if the final attempt is invalid but `best_valid` is not None, **ship `best_valid`** (it already passed the hard gate) instead of raising `invalid_after_repair`. Record `final="executable_from_retained_candidate"` + which attempt produced it.
- Only raise `invalid_after_repair` when **no** attempt in the chain ever produced a hard-valid plan.

This directly answers "if a later repair fails creative validation, do not discard an earlier valid plan," and "avoid additional expensive model calls when acceptance of an existing valid candidate is preferable."

### 2.2 Deterministic-first directive repair (the 47.5s fix)

- Change the gate on `repair_directive_placement` from `_errors_are_order_only(errs)` (every error must be placement) to: **run it whenever the DIRECTIVE subset of errors is placement-only**, regardless of coexisting numeric errors. Partition errors: `directive_placement_errs` vs `other_errs`. If `directive_placement_errs` is non-empty and all of them are reorder-type, apply the reorder first (0 Bedrock), re-validate; this clears the ordering errors deterministically and leaves only the (usually trivial) numeric errors for one targeted model/deterministic pass.
- Widen the deterministic normalization to snap `output_span_inconsistent` where the fix is unambiguous (declared output vs `span/speed`) beyond the current tiny rounding window, bounded so it never changes the source range the model chose by more than a safe epsilon — turning a common `"other"` error into a 0-Bedrock fix rather than a repair-call trigger.

### 2.3 Joint directive-feasibility preflight inside generate()

- Before the first Opus call on any request carrying `directives`, run the existing `preflight_directives` (today only on the interpret endpoint) **plus** a new **positional-satisfiability check**: can opening/ending/order_after/order_adjacent/must_include be topologically ordered over the eligible set at all? If NOT (a true contradiction/cycle) ⇒ fail **fast** with the specific conflict (0 Opus calls) and a precise "these constraints can't all hold — loosen X" message. If YES ⇒ proceed. This converts the genuinely-infeasible case into an instant, cheap, specific answer, and guarantees the expensive path is only spent on *satisfiable* requests.
- **Attempt a fully-deterministic directed build** for a directed *create/another-version* when the request is pure-structural over a known candidate pool (analogous to `apply_deterministic_revision`, which today only runs for revise with a base_plan): if the directives can be satisfied by selecting+ordering eligible moments within the duration band with 0 Bedrock, ship it. Fall through to the model only for genuinely creative selection.

### 2.4 Bounded retry + stopping policy (explicit)

| Situation | Action | Model calls |
|---|---|---|
| Directive errors are reorder-only (± trivial numeric) | deterministic reorder + deterministic snap | **0** |
| Joint directives unsatisfiable (cycle/contradiction/over-exclusion) | fail fast, specific message | **0** |
| First plan hard-valid | ship | 1 |
| First plan invalid, repairable | ≤ 2 targeted repairs (unchanged cap), each carrying exact errors | ≤ 3 total |
| Any attempt produced a hard-valid plan, later attempt regresses | **ship the retained best-valid candidate** | no extra |
| No attempt ever hard-valid | `invalid_after_repair` (honest), with the specific unmet hard errors | ≤ 3 total |

The retry **cap is unchanged** (still 2 repairs); the change is that retries can now only *improve on or fall back to* a retained valid plan — they can no longer destroy one. Expected effect: **strictly fewer wasted ≥3-call/≥3-min runs**, not more calls.

---

## Phase 3 — Preserve operation semantics (Revise vs Create Another Version)

**No merge of the two operations.** This amendment does not touch the Revise↔Explore objective split already sharpened in the 2026-10-21 continuity amendment.

- **Revise** (`mode:"revise"`, has `base_plan`): starts from the exact selected base plan (D1 fix already landed `7c2c126`), preserves footage/order/timing/audio where not changed, applies the latest change, permits justified add/remove, previous version preserved (append-only). Best-valid retention (Phase 2.1) applies **after** the continuity gate, so a valid revise that the continuity gate ACCEPTS is the retained candidate; the continuity `noop`/`wholesale` rejections are unchanged.
- **Create Another Version** (`mode:"explore"`): seeks a meaningfully different valid interpretation, retains the latest explicit requirements (duration, hard directives), permits creative flexibility in selection/timing/sequence. The Explore diversity objective is unchanged. Best-valid retention applies to Explore too (a valid alternative is never discarded to chase more novelty).
- The directed "another version with Customize directives" path (the 47.5s case) is **Explore + hard directives** — it gets the Phase-2.2/2.3 deterministic-first treatment, so a satisfiable directed alternative is produced deterministically or by one honest model pass, and retained.

Revise is **not** turned into Explore; the two keep distinct objectives and distinct preservation latitude.

---

## Phase 4 — Evidence & regression plan

Reuse existing real fixtures (`evals/scenarios/`: Girl with Dress, Hiking, Guitar, Minimal footage) + the recent failed Story (18 moments, 47.5s, the 4 directives). **Bounded spend**, cached AU evidence, no new research sweep.

Metrics (proposed vs the current frozen baseline), per fixture + aggregate:

| Metric | How measured |
|---|---|
| Technical validation pass rate | `validate_plan` pass on the shipped plan |
| Creative-intent satisfaction | HARD-directive satisfaction (deterministic) + soft-intent human read |
| Playable-output rate | fraction of requests that ship a renderable plan (vs `invalid_after_repair`) — **the headline metric this amendment moves** |
| Avg physical Bedrock invocations | `diag.model_calls` mean |
| p50/p95 planning latency | worker wall-clock to terminal |
| Estimated USD / playable output | `EstimatedModelCostUSD` ÷ playable count (reuses the observability EMF already live) |
| Incomplete-instruction disclosure frequency | count of ships that carried a soft-intent-unmet disclosure |

Required regression cases (must each be exercised): **contradictory instructions** (include∩exclude, cyclic order → fail-fast 0 calls, specific message), **unavailable media** (directive_ref_ineligible → hard fail), **strict ordering** (the 47.5s 4-directive case → deterministic reorder ships a valid plan), **duration pressure** (tight target + many moments → band accept, no false infeasible), **mixed creative requests** (retime + creative → shorter total allowed, continuity `ok`). Acceptance bar: **playable-output rate strictly increases, avg model calls does not increase, no technical/integrity regression, no silent success on an unmet HARD directive.**

---

## STOP gate — versioned architecture amendment deliverables

### 1. Exact hard vs soft validation rules
- **HARD (unchanged, never weakened):** buckets 1 (technical/rendering: rows 1,2,4,7,8,9,10,11,12,21), 2 (media ownership/integrity: rows 3,5,19), and 3 (explicit user requirements: rows 15,16,17,18,20). Duration band (13/14) stays a hard *band* (−20%/+50%), operation-scoped as today.
- **SOFT (quality signals, not auto-reject):** the real editorial-quality layer (hook/variety/significance) stays where it already is — the frozen prompt body + the optional critique pass — **not** in `validate_plan`. The *only* validator rule proposed to move hard→soft is **row 6** (`source range overlaps NO useful_segment`) → a deterministic repair-preferred nudge, with row 5 (real-duration bound) remaining HARD. This single move is conservative and reversible.
- **No new instruction-specific exception rules.**

### 2. Proposed planner/repair changes (`packages/edit_planner/__init__.py` + worker, request/routing/validator/diag only)
1. Add `best_valid` retention across the attempt chain; terminal fallback ships it (`executable_from_retained_candidate`). (Phase 2.1)
2. Partition validator errors into directive-placement vs other; run `repair_directive_placement` whenever the *directive* subset is reorder-only (not only when *all* errors are). (Phase 2.2 — the 47.5s fix)
3. Widen deterministic output-consistency snap to clear trivial `output_span_inconsistent` with 0 Bedrock. (Phase 2.2)
4. Run `preflight_directives` + a new positional-satisfiability (topological) check inside `generate()` before the first Opus call on any directive-carrying request; unsatisfiable ⇒ fail-fast with the specific conflict, 0 calls. (Phase 2.3)
5. Deterministic directed-build attempt for pure-structural directed create/another-version. (Phase 2.3)
6. Row-6 downgrade to a deterministic range-nudge (optional, gated). (Phase 1/0.5)
7. `diag` additions: `best_valid_from_attempt`, `positional_preflight`, `incomplete_instruction_disclosure`. (Phase 4)

### 3. Frozen-contract impact
**None.** `edit_plan/5.2` SYSTEM body and the EditPlan/2 OUTPUT schema are untouched. No new wire request field (directives already travel in `revision_context`). All changes are server-side routing/validator/diagnostic logic + one conservative hard→soft validator reclassification. Back-compat: absent directives ⇒ behavior byte-for-byte today's (plus best-valid retention, which can only turn a former failure into a ship, never the reverse).

### 4. Regression risks
- **Row-6 downgrade** could let a plan whose source range sits just outside a useful window reach render; mitigated by keeping the real-duration bound (row 5) HARD and nudging into the nearest useful window deterministically. Gated + reversible; measure visual quality on the fixtures before defaulting on.
- **Best-valid retention** could ship a plan that satisfies the hard gate but misses a *soft* editorial ask; mitigated by the incomplete-instruction disclosure (never a silent success) and by the fact that the retained plan is, by definition, playable — the owner's stated priority.
- **Positional preflight** must not false-positive (reject a satisfiable combo); it is a pure topological check with the same semantics as `_validate_directives`, unit-tested against the 47.5s combo (must pass) and a true cycle (must fail).
- **Deterministic directed build** must never *invent* footage or violate the useful/duration bounds — it reuses `validate_plan` as the authoritative check before shipping, exactly like `apply_deterministic_revision`.

### 5. Expected latency / cost improvements
- The 47.5s class (satisfiable directives mis-ordered by the model): **~3 Opus calls / ~3 min → 1 call or 0** (deterministic reorder), and it **ships a playable video instead of `invalid_after_repair`**.
- Genuinely-contradictory directives: **3 calls / 3 min → 0 calls, instant specific message.**
- General repair regressions: no extra calls; best-valid retention converts a subset of today's `invalid_after_repair` 503s into ships at **no additional model cost**.
- Net: **playable-output rate ↑, avg physical Bedrock invocations ↓ or flat, p95 latency ↓ on the directed path, USD/playable ↓.** No per-render latency change (planning only).

### 6. Rollback strategy
- Every change is **flag-gated and additive** behind request-independent server flags (e.g. `STORY_EDITPLAN_BEST_VALID_RETENTION`, `STORY_EDITPLAN_DETERMINISTIC_DIRECTIVE_FIRST`, `STORY_EDITPLAN_POSITIONAL_PREFLIGHT`, `STORY_EDITPLAN_USEFUL_RANGE_SOFT`), each defaulting **off** so a deploy is a no-op until flipped; flip individually, measure, revert a single flag on regression.
- No contract/schema/prompt version bump ⇒ rollback is a flag flip or a code revert of `packages/edit_planner/`; **no data migration, no client change** (older clients already send no directives and are unaffected). The frozen `edit_plan/5.2` default path is reachable throughout.

---

## Architecture gate

**STOP here for owner architecture approval before any implementation or deployment.** No code changed, no prompt/contract touched, nothing pushed. Out-of-scope systems (auth, quotas, WAF, billing, R7 sync, production infra) untouched. On approval, Phase-2/3 changes land behind the flags above with the Phase-4 regression suite (including the 47.5s 4-directive fixture and the contradictory/unavailable/strict-ordering/duration-pressure/mixed cases) run before any device gate.
