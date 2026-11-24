# Full Story Editorial Coverage — Guide Wiring + Mode-Aware Selection

Status: **Phase 1 wiring fix implemented + tested; A/B done; mode-semantics gap identified.
STOP for owner review before any prompt/mode freeze.**

## 1. The wiring defect & fix (Phase 1 — done, `fe4db68`)
`EditPlanRequestBuilder.build` sent `story_guide` and `story_coverage` as **empty
objects** (`.object([:])`), even though Edit Planner v5's prompt explicitly says to
"allocate time by narrative significance relative to the Guide and Coverage." Fixed by
loading the Story's persisted `StoryGuideModel` + `StoryCoverageModel` (same loaders the
music path uses) into the request; honest empty-object fallback when absent/not-yet-computed
(never fabricated or stale-forced). No frozen prompt/contract change — the request fields
already exist and v5 already reads them.

Tests (`EditPlannerCaseGTests`): `test_persisted_guide_and_coverage_reach_the_request`
(non-empty on the wire when persisted) and `test_absent_guide_and_coverage_fall_back_to_empty`
(honest empty when absent). Backend suite 224 pass.

## 2. A/B result (Phase 2 — live dev backend, identical footage/intent) — HONEST
24 moments, 105s target, cinematic-journey intent. Unique moments selected:

| summaries | A (empty guide/coverage) | B (populated guide/coverage) |
|---|---|---|
| rich | 13 | 13 |
| thin (device-like) | 17 | 15 |
| rich (repeat) | 15 | 15 |

**Wiring alone does NOT materially improve footage utilization.** B is equal to or slightly
below A, and the count swings 13-17 run-to-run (model non-determinism at temp 0). The guide/
coverage improves narrative *grounding and ordering* (correctness), but it is **not the lever**
for "only a few moments used." Per the owner's rule, B is **not** declared better for selecting
more clips — it doesn't.

(The earlier observed "36 eligible → 11 selected @ 105s" was a single real run; 11-17 at 105s
is ~6-10s/segment — a legitimate cinematic range, not a bug by itself.)

## 3. The real gap (Phase 3): editorial MODE never reaches the planner
`CustomizeYourStoryView.LengthChoice {highlights, full, custom}` is collapsed into a single
**`target_duration_seconds`** before anything leaves the device. The planner receives only a
duration — it **cannot distinguish** "Highlights: strongest + concise" from "Full Story: broad
representation" at the same duration. So the owner's product requirement (Highlights vs Full
Story being editorially different) is currently **unexpressible** to v5. This — not the guide
wiring — is the mechanism behind under-representation on Full Story.

## 4. Phase 6 recommendation
- **Keep the wiring fix** (`fe4db68`): it is a correctness fix (v5 should receive the evidence it asks for), low-risk, additive, no prompt change. But it does **not** close the utilization concern on its own — the A/B proves that.
- **The minimum change that addresses the owner's requirement is mode-aware planning:** pass the editorial objective (highlights | full | custom) to the planner as an additive request field, and a **narrowly versioned** v5→v5.1 prompt clause that reads it:
  - Highlights → strongest material, concision.
  - Full Story → represent more *distinct meaningful* parts where footage + duration support it; preserve essential continuous actions; avoid redundancy. (NOT a minimum clip count, NOT mandatory Guide completion.)
  - Custom → infer breadth from intent + material at the chosen duration.
- This is a **frozen-prompt change**, which the owner gated: **STOP here for approval** before authoring/freezing a v5.1 candidate. Phase 4 would then A/B v5 vs v5.1 at identical durations so mode effect is separable from duration.

## 5. Contract implications
- Phase 1: none (additive use of existing request fields).
- Mode-aware (proposed): one additive request field (`editorial_mode`) + a versioned v5.1 prompt. No EditPlan/2 output-schema change.

## 6. Device acceptance checklist (after a decision)
- Full Story on 20-25 moments represents visibly more distinct parts than Highlights at a comparable duration.
- Highlights stays tight/strong; no redundant near-duplicate clips.
- Continuous conversations/performances preserved.
- Duration accurate; native audio intact; plan executable.
- No forced inclusion of every moment or every Guide dimension.

## 7. Remaining risks
- A versioned mode prompt is model-mediated; "breadth" is a bias, not a guarantee.
- Synthetic A/B ≠ device proof; the real TMB/Guitar comparison needs on-device moment data (their files were lost earlier in testing; re-import needed) or a device render.
