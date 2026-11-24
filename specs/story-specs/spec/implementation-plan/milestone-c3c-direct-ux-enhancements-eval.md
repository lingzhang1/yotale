# DIRECT UX enhancements — evaluation report (Skip Scan + 3 alternatives)

Status: **evaluation PASSED → implementing both features.** Production Director model
`us.anthropic.claude-opus-4-5-20251101-v1:0`, production prompt + frozen contracts + guards.
Subset: 5 representative fixtures × {scanned, null} × {single, candidates} = 20 live calls/run.
Runner `evals/run_direct_ux_enhancements.py`; result `evals/results/direct_ux_enhancements.json`.

## Prompt changes made (smallest sufficient)

Two additive clauses in `prompts/story_director/v1/system.md`, no behavior change to the
scanned path:
1. **SKIP-SCAN / NO SCENE** — when `scene_understanding` is null, still produce an
   actionable `capture_shot` grounded ONLY in intent + the user; environment-agnostic;
   MUST NOT invent surroundings; MUST NOT choose `rescan_scene` just because scene is null.
2. **One-beat/one-shot cap for null scene** — with no scene there is nothing to justify
   several beats; emit exactly one beat + one shot for the slot (anti-over-planning).

## Findings (final run, after both clauses)

| dimension | result |
|---|---|
| **Null-scene actionable** | 10/10 null runs → `capture_shot` (was 10/10 `rescan_scene` before fix) |
| **No environment fabrication** | 0 true surroundings-fabrications. One substring hit ("look up as if seeing the mountains ahead *in your mind*") is an INTENT-derived MENTAL image, not a claim that surroundings exist, and directs no environment-dependent action — judged acceptable; the tripwire is a blunt substring match |
| **No over-planning** | null scene = **beats 1 / shots 1** everywhere (was 3–4 beats before the cap). Candidate requests did NOT inflate plan beats/shots vs the single run |
| **Candidate diversity** | `candidates` uniq instructions = 3/3 on essentially every candidate run (one 2/3 earlier, 3/3 after); no paraphrases of #1 |
| **Candidate count** | up to 3; candidates[0] == primary decision |
| **Scanned not regressed** | scanned stays 1/1 or 2/2 beats/shots; genuinely irrelevant scanned scene still `rescan_scene` (single); recommendation #1 unchanged in character |
| **Safety** | all runs pass `_safety_guard` + `_integrity_guard`; 0 unsafe hits |
| **Structured validity** | 20/20 valid against the (additive) candidates envelope; ids minted normally |
| **Latency** | candidate call p50 ≈ 17s vs single ≈ 12s (one-time +~5s for 3 candidates). `Try another idea` is then **instant** (local cycle, NO new call) |
| **Token/cost** | candidate call ~1.5–1.9× single output tokens (one extra pass worth of alternatives); one call per recommendation slot, not per Try-another-idea |

## Architecture decision (smallest change; no canonical contract change)

- `candidates[]` is added to the **Director engine RESPONSE envelope only** (`DirectorOutput`),
  as an array of the frozen `DirectorDecision` shape. It is **ephemeral session/UI data**,
  NOT persisted into `StoryPlan` and NOT a canonical contract change. `candidates[0]` mirrors
  `decision`. `plan.beats` / `plan.shots` stay minimal — the over-planning guardrail holds.
- `scene_understanding` becomes **optional/nullable** through the request path
  (endpoint + engine). No canonical contract is modified: a null scene is simply "no scene
  object provided", which the frozen contracts already allow at the request boundary.
- **No `StoryPlan` change, no new persisted beat/shot, no Beat/Shot contract change.** The
  selected candidate maps into the existing Shot capture path unchanged (it IS a Shot).

Evaluation passed on every required dimension → proceeding to implement server + iOS.
