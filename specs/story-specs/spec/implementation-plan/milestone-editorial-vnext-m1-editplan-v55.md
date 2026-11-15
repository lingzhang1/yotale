# Editorial vNext — M1: EditPlan 5.5 candidate (Highlights vs Full Story differentiation)

**Status: IMPLEMENTED on `feat/editorial-vnext-m1` (2026-11-15) — offline tests green; NOT merged, NOT deployed, NO live model
call, no beta/prod/dev config touched.** v5.5 is an isolated candidate: it is selected only by an owner-approved
`STORY_EDIT_PLAN_VERSION=5.5` override on the API *and* the worker; the default and the release manifest stay `5.3`.
Design baseline: [Phase A report](./milestone-editorial-vnext-phase-a-report.md). Owner decisions D1–D8 (2026-11-15) are
recorded there; this milestone implements D1, D6 and the M1 parts of D3, plus the D7 offline harness.

Quality is **not** claimed. Nothing here shows the candidate is better; that needs the matched rendered-video evaluation (§11).

## 1. What changed (files)

| File | Change |
|---|---|
| `prompts/edit_plan/5.5/system.md` | NEW isolated system prompt (5.3 body + three clause changes, §2). `5.3/` is byte-untouched (sha256 pinned in a test). |
| `packages/edit_planner/__init__.py` | `_v55_active()`, one-authority type routing (`_v55_type`), server-owned type-aware briefs (`_V55_BRIEFS`, `_effective_brief`), one per-type strategy block (`_v55_strategy`), sound defaults, deterministic budget hint (`compute_budget_hint`), v5.5 repair duration bullet, type-aware critique, `selection_diagnostics` (all versions). |
| `apps/api/app/worker.py` | whitelists `selection` into the job's persisted diagnostics (one line). |
| `apps/api/app/main.py` | comment only: the legacy `MM_CREATIVE_BRIEF` is ≤5.3; ≥5.5 the server brief is authoritative. |
| `scripts/editorial_eval.py` | NEW offline harness (§9). |
| tests | `test_edit_plan_v55.py` (34), `test_editorial_eval_harness.py` (7), `_v55_fixtures.py`, `fixtures/edit_plan_v53_golden.json`. |

Not touched: iOS (no Swift change; the iOS client still sends its brief string, which a ≥5.5 backend ignores when a type is present),
Duration Intelligence, AU frame selection/extraction, renderer, CDK, workflows, release manifest, any config.

## 2. Exact v5.5 system-prompt differences vs 5.3

(`diff` of the two files: 57 lines of 5.3 replaced by 43 of 5.5; 142 → 128 lines.) Everything else is 5.3 verbatim, including the
EXECUTABILITY invariants (valid range, output = span/speed, speed limits, transitions), NATIVE AUDIO, MUSIC ALIGNMENT and HARD RULES
(asserted equal by `test_55_keeps_executability_native_audio_and_hard_rules_verbatim`).

1. **Header comment** rewritten (the 5.3 one still said 5.2).
2. **`EDITORIAL MODE` bullet → `EDITORIAL TYPE` pointer.** Removes the shared "highlights = fewer, higher-value / full = broader" clause. The system prompt now says the
   user message's single TYPE STRATEGY block is the only authority for breadth, pacing and opening; the legacy `editorial_mode` hint
   applies only when no type is given. Invariants kept (preserve continuous actions, no clip quota, target stays the objective).
3. **`SIGNIFICANCE-WEIGHTED SCREEN TIME` + `CREATIVE FREEDOM OVER PACING` → one neutral paragraph.** Deleted: "favor BREADTH — more distinct shots,
   each shorter" and "visual variety is itself a reason to include a shot even when its action is ordinary" (a verified breadth bias for *both*
   types). Kept: significance weighting, no quota, no padding. Added: decide the shot list *before* writing segments so durations add to the target.
4. **`DURATION DISCIPLINE`**: now matches the runtime (target is a strong objective; land within ~10%; drop the weakest material rather than
   keep everything; a valid plan always ships; a deterministic fit trims long plans). Removed "±20% is a hard feasibility TOLERANCE".
5. **Invariants header + `TOTAL WITHIN TOLERANCE` bullet**: total length is explicitly *not* a rejection rule; "TOTAL NEAR TARGET ±10%".

## 3. Type-aware creative brief

`_V55_BRIEFS` (server-owned): Highlights = visual hook, comparative selection, brisk pacing, selective; Full Story = meaningful narrative,
complete actions and context, natural sound, grounded progression, **no invented events, journey or dialogue**. Behavior:
- v5.5 + known `editorial_type` + the client sent a brief (multimodal run) → the server brief replaces the client text. An older iOS build
  sending the Highlights brief for Full Story therefore cannot reach the model (tested; `fx.LEGACY_BRIEF not in user message`).
- Presence of the client brief still gates the optional critique pass exactly as before; no client change is required.
- Type absent/unrecognized (e.g. legacy Revise base) → client brief and legacy mode line, unchanged. v5.3 → client brief, unchanged.
- Critique/revision prompts use the same effective brief; Full Story gets its own five questions (no "hook in 3 s").
Producers: iOS (`StoryMultimodalPlanning.creativeBrief`) and the dead backend constant `MM_CREATIVE_BRIEF` are legacy ≤5.3; the only brief
≥5.5 uses is `edit_planner._V55_BRIEFS`, so the two cannot conflict.

## 4. Legacy-instruction reconciliation (v5.5 path only)

With a known type, the user message contains exactly: brief → VERSION CONTEXT (if any) → visual evidence → one sound line → **one**
TYPE STRATEGY → advisory budget → INPUT. Removed from the v5.5 path: the legacy `EDITORIAL MODE =` line, the v5.3 `EDITORIAL TYPE =` directive,
the shared brief, and `editorial_mode` inside the INPUT JSON. Original, Revise and Explore keep their VERSION CONTEXT objectives; the strategy
states it guides new edits and that REVISE preserves the base edit and explicit directives always win.

## 5. Highlights strategy

Single block, six steps: survey all Moments (candidates, events, and above all the frames); **compare similar footage** (subject prominence,
expression, composition, colour/contrast, movement, scenic drama, payoff visible in the frames) and keep the strongest, a second only if it shows a
different action/place/emotion; **AU `peak_time`/confidence are not appeal; trust the frames when they disagree**; consider the most arresting visible payoff
as the **hook** and avoid arrival/town/packing/walking openers unless arresting (user opening directive wins); build contrast after the hook;
short purposeful shots starting at the action, longer when a payoff needs it ("a tendency, not a clip-length rule"); select, do not cover.
No Moment id is hardcoded anywhere (tested). The three red-jacket Moments are a fixture for prompt-shape tests only; no assertion names a winner.

## 6. Full Story strategy

Understand what happened from events/narrative candidates/Guide/Coverage; no invented dialogue; follow the thread the material supports with examples
explicitly "not a template"; **no invented departure/midpoint/return; village footage is not necessarily the start or end; `moments[]` order is import
order, not chronology** (measured τ −0.04); keep complete meaningful actions, context and original sound; select by meaning, not appeal alone; avoid repeats
that add nothing; no required arc. Chronology metadata itself is M3 (nothing in M1 references a field that does not exist).

## 7. Duration budget hint (deterministic, advisory)

`compute_budget_hint(inputs)`: target × type-typical shot length → suggested shot range, capped at two shots per Moment, plus material
characteristics (Moments, useful seconds, payoff windows for Highlights, narrative candidates for Full Story). Typical lengths: Highlights 3–5 s,
Full Story 5–9 s (tendencies, not quotas). Examples: 90 s Highlights → 18–30 shots; 155 s Full Story → 17–31; 16 s → 3–5; 5 Moments → capped to 10.
Rendered as `BUDGET (advisory, not a quota)`: decide shots first so the sum lands within ~10%; a payoff may run longer; a deterministic fit will trim a long
plan so aim at the target yourself. Skipped for Revise, for an unknown type, and with no target. The requested target (including Custom) is read
unchanged; the type never alters it (tested at 47 s). The fitter (`duration_fit.py`) is untouched.

## 8. Diagnostics (D3, deterministic, all versions)

`diagnostics.selection` (also persisted by the worker): effective type, prompt version, brief source, shot statistics and distinct Moments (final and pre-fit),
budget (target, pre-fit and delivered totals and overshoot %, hint), opening shot (with payoff flag), used list (≤80: 8-char ref, source range, output seconds,
payoff overlap, role), unused Moments that have a payoff window (≤40: ref, count, seconds, confidence, duration), sheet count and bytes, and a fit summary.
Computed from the plan, the request and AU only: no model, no rationale, no media, no prose, no full ids (asserted). Recorded for 5.3 too so baselines and
candidates are measured identically. Not recorded: per-sheet frame count/tier (device-side; M4).

## 9. Offline evaluation harness (`scripts/editorial_eval.py`)

`render` (5.3 vs 5.5 prompts for one case, with a unified diff and token estimates), `metrics` (one job record → one row), `compare` (a table plus guards:
**an Explore is never silently compared with an Original**, differing targets/Moment counts are flagged, same-version pairs are labelled). Columns: type, operation,
target and source ("unrecorded" until M2/M4 record it), Moments, sheets, calls, pre-fit and delivered totals and overshoot, shot distribution, fit changes/drops,
payoff shots, opening-is-payoff, unused payoff Moments, validity, completion, tokens, estimated cost, job latency, builds. No network, model or private media;
inputs are local job/AU dumps you point at. Verified on the two real beta baseline jobs: it reproduces +76.2% pre-fit overshoot, 6.34 s pre-fit mean for Highlights
(24 shots, 23 distinct, opening not a payoff clip) and 5.75 s for the Full Story Explore. Mocked runs prove prompt construction only.

## 10. Runtime and rollback compatibility

- Default remains `5.3` in code, CDK and `release/release.json`; no config, gate or workflow changed. The candidate exists on disk and is inert.
- To run it (needs your approval, not done): set `planner.emergency_override: "5.5"` plus a matching `approved_overrides` entry in a reviewed PR (existing
  mechanism; CDK pins API and worker identically; the gate rejects an unapproved or mismatched override), deploy to **dev** first. Rollback = clear the
  override (back to 5.3), no data migration; prompts are per-request, pending jobs finish on the version their worker runs.
- Version resolution verified for numeric parsing: `5.5` resolves and `_v53_active`/`_v55_active` are both true; unknown versions fall back to 5.3; a
  non-numeric directory name (e.g. `5.3-cand`) never counts as ≥5.5.
- No permanent flag, no second engine, no extra mandatory model call (engine test asserts `model_calls == 1` for both types).

## 11. Verification (offline)

| Check | Result |
|---|---|
| v5.3 prompts byte-identical (user ×5 cases, repair, critique, revision) vs goldens generated from unmodified master | pass |
| `prompts/edit_plan/5.3/system.md` sha256 pinned | pass |
| New tests `test_edit_plan_v55.py` + `test_editorial_eval_harness.py` | 41 pass |
| Existing planner suites (`test_edit_plan_v53`, `test_edit_planner`, `test_edit_plan_duration_fit`) | pass, unmodified |
| Full CI backend suite `pytest packages contracts apps/api/tests` | **1163 passed** |
| CDK `jest` | **72 passed** (3 suites) |
| iOS | no Swift change in M1; Xcode tests not run (sandbox cannot build the app); owner's device build is the authority for any later iOS change |
| Pre-deploy release gate (`release_config_gate.py pre`, dev + beta, exactly the CI commands, clean committed tree at `54e8849`) | **ACCEPTED** for both (local; CI on the PR will re-run) |

Required cases from the brief covered: v5.3 unchanged; v5.5 Highlights/Full Story policies when selected; no conflicting legacy lines; Full Story never gets the
Highlights brief; user opening directive rendered and stated to win; Custom target preserved; Original/Revise/Explore routing preserved; directed Explore remains
Explore; one model call; no new terminal creative rejection (no validator change); source-range/duration arithmetic invariants verbatim; native-audio/music text
verbatim. Not asserted, deliberately: any aesthetic outcome or Moment id.

## 12. Not verified

Any quality effect; behavior of a real model under 5.5 (no live call made); latency/cost of 5.5 (the prompt is slightly different in size, not measured); rendered
videos; the release gate in CI (it passed locally); the iOS client (unchanged).

## 13. Remaining milestones and dependencies

M2 sizing (Duration Intelligence inputs; independent) → M3 chronology (backend gate + sanitize/repair projection first, then iOS emission; depends on M1's version gate) →
M4 Moment-ID aliases + remaining diagnostics (per-sheet tier/frames, target source) → M5 matched evaluation → M6 promotion. The M1 strategy's
Full Story chronology wording is intentionally absent until M3 lands.

## 14. Owner decisions needed

1. Merge M1 (CI green)? 2. Approve selecting 5.5 on **dev only** via the reviewed override for the initial live evaluation (4 jobs: baseline/candidate × Highlights/Full Story, all
Originals, same Story, same user direction and duration choices; no repeated regeneration). 3. Confirm the typical shot ranges (Highlights 3–5 s, Full Story 5–9 s) used for the hint.
