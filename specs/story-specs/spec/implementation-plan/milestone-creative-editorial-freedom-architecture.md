# Creative Editorial Freedom & User-Directed Editing — Architecture Study

Status: **Design study + bounded A/B complete. STOP at the owner architecture/freeze gate.**
No production default change, no prompt freeze. `5.2-exp` is an experiment-only prompt (NOT
default); dev backend reverted to `5.1`. Nothing pushed.

Owner principle: **AI has creative freedom by default; the user has final editorial authority.**
NO fixed style templates (Dynamic/Cinematic/Natural) as the core architecture.

## 1. Artistic-constraint audit (Phase 1)
In v5/v5.1, the clause that unnecessarily constrains creative judgment is
**SIGNIFICANCE-WEIGHTED SCREEN TIME**, specifically "Prefer fewer well-chosen Moments held long
enough to read over many equally short clips." This is a **long-hold bias** that, measured earlier,
FIGHTS breadth at generous durations (Girl-with-Dress 100s used only ~9-16 of 36 genuinely-distinct
moments). It is an **artistic** preference, not a technical necessity.

Must-KEEP technical invariants (NOT touched): EXECUTABILITY INVARIANTS (source-range validity,
output=span/speed, ±20% total, transitions), DURATION DISCIPLINE (target authoritative, no pad),
native-audio policy, source-grounding ("never invent footage"), and continuous-performance
preservation. These are the floor; freedom lives above them.

## 2. Human reference (Phase 2)
Owner's ~60s / 20+-clip human edit of Girl with Dress was not available as a file to measure, so
this is reported as a limitation; the real footage ground truth (two outfits, red bag, ~10
locations, 4-6s human-cut pace) stands in as the target. Guitar Practice is the counterexample: a
continuous performance that must keep one long hold. Neither is made a template.

## 3. User-instruction taxonomy (Phase 3) — additive request object, NO EditPlan/2 change
Proposed `user_directives` on the edit-plan REQUEST (optional; absent = full AI freedom):
| directive | type | meaning |
|---|---|---|
| `must_include: [moment_id]` | HARD | these Moments must appear |
| `exclude: [moment_id]` | HARD | never use these |
| `include_all: bool` | HARD | use every usable Moment (subject to duration feasibility) |
| `opening: moment_id` / `ending: moment_id` | HARD | first/last Moment |
| `order: [moment_id]` | HARD (partial) | relative order of the named Moments |
| `locked: [{moment_id, source_start, source_end}]` | HARD | preserve these exact segments |
| `target_duration_seconds` | HARD | already exists in CreativeIntent |
| `music_only: bool` | HARD | re-soundtrack only, reuse visual edit (already shipped as Change Music) |
| `preferences: free text` | SOFT | flexible creative steering ("start energetic", "more of the green dress") |
References resolve against ALL source Moments (including omitted footage); thumbnail selection maps
directly to `moment_id`, natural language maps to soft `preferences` + resolved ids. Hard vs soft is
explicit: hard = validated/enforced; soft = steering the AI retains freedom over.

## 4. Constraint validators (Phase 4) — deterministic, around existing EditPlan/2
Add checks (client or backend, post-plan, pre-render) that each HARD directive is satisfied:
must-include present; excluded absent; include-all coverage (modulo feasibility); opening/ending
Moment correct; required partial order respected; locked segments present with exact ranges; plus
the EXISTING source-range/duration/native-audio invariants. On conflict (e.g. must_include + a
duration too short to fit) → report the specific conflict + smallest resolution (drop the lowest-
priority soft item, or surface "these can't all fit in Ns"); NEVER silently drop a user requirement.

## 5. Creative-planning A/B (Phase 5) — v5.1 vs 5.2-exp (freedom candidate)
`5.2-exp` = v5.1 verbatim with the one significance clause rebalanced to **creative freedom over
pacing** (no long-hold bias; favor breadth when footage is distinct + intent is variety/journey;
favor continuous holds when the footage centers on a performance/payoff). Confirmed live
(`prompt_version=edit_plan/5.2-exp`). Identical footage/intent/duration/mode/evidence.

| fixture | v5.1 | 5.2-exp |
|---|---|---|
| Girl-with-Dress 100s full | ~9-16 unique | **22 unique**, 4-6s shots (broad, varied) |
| Guitar 45s (continuous) | 6/6 | **6/6, incl. a 25s continuous hold** |
| Solitude 30s | 3/3 | 3/3 (long calm holds) |
| Redundant 30s | 12/12 | 12/12 (near-dup padding — residual) |

**Both edit types emerge from the material, not a template:** a 22-shot fashion edit AND a 6-shot
performance edit, from the same planner. This is the owner's principle realized.

## 6. Quality (Phase 6)
- Shot-duration distribution: Girl 4-6s (varied, appropriate), Guitar 3-25s (one long payoff), Solitude 7-12s (patient) — all material-driven, not uniform.
- Visual variety + meaningful coverage: Girl now spans both outfits + many locations.
- Continuous-action preservation: Guitar's performance kept as one 25s hold. ✅
- Native-audio / duration / executability: all feasible, invariants unchanged.
- NOT optimizing raw count or randomness; redundant control still pads (separate dedup concern).

## 7. Architecture recommendation (Phase 7)
**Smallest reliable creative architecture = (1) ONE creative Edit Planner with richer context +
creative-pacing freedom  +  (3) a deterministic constraint validator around existing EditPlan/2 for
user directives.** NOT fixed style templates; NOT a creative→revision two-stage pass (unneeded — one
planner already produces both edit types); NOT a full timeline editor.
- The freedom amendment (5.2-exp) is the planner half.
- `user_directives` (additive request object) + the Phase-4 validators are the authority half.
- EditPlan/2 output contract, native-audio policy, and executability invariants all unchanged.

## 8. Contract implications
EditPlan/2 OUTPUT: no change. REQUEST: one additive optional `user_directives` object (back-compat;
absent = today's behavior). Prompt: the 5.2-exp pacing-freedom amendment, versioned, owner-gated.

## 9. Cost & latency
A/B + fixtures: a handful of edit-plan calls (~15-22s each), well under the $20 gate. No per-render
latency change (same single Opus call).

## 10. Recommended next implementation milestone (owner decision)
1. **Freeze the creative-freedom prompt** (promote 5.2-exp → a real versioned v5.2) after a device render confirms the Girl-with-Dress breadth + Guitar long-hold both hold on real footage.
2. **Then** implement `user_directives` (request object) + the deterministic validators — this is the "user has final authority" half, and the foundation for the Figma feedback/revision UX and future Natural-Language Refinement.
Residual (separate, owner-scoped-out): near-duplicate padding under Full → an optional dedup heuristic later.

STOP for owner approval before freezing the prompt or building the directives layer.

## Addendum — hiking fixture (5th real dataset)
Added `evals/scenarios/hiking` (40 files; ~39 unique clips + one genuine duplicate IMG_4469 2.MOV;
durations 1.6-95s). Two treks (Iceland Laugavegur + Alps TMB), highly distinct: volcanic rhyolite
terrain, fog, a river crossing (continuous), a hut-café moment (intimate), Mont-Blanc vistas,
glaciers, lakes, a summit jump. Visual ground truth confirmed via extracted frames.

A/B at 100s Full (same methodology; prompt_version confirmed each arm):
| | v5.1 | 5.2-exp (freedom) |
|---|---|---|
| hiking (39 moments) | **20/39** (11 Iceland / 9 Alps) | **24/39** (13 / 11), 3.5-5s shots |

Consistent with Girl-with-Dress (9-16 → 22): the freedom candidate broadens distinct coverage and
balances across both trips. Note v5.1 already did better here (20) than on the fashion set, because
hiking summaries describe inherently more distinct scenes (fog/river/café/glacier) — more for the
planner to differentiate even before the freedom amendment. Full 5-fixture read: freedom helps most
where footage is distinct and the intent is breadth/journey (fashion, hiking), is neutral/correct on
performance (Guitar 6/6, 25s hold) and minimal (Solitude 3/3), and does not fix genuine-duplicate
padding (redundant control). No change to the architecture recommendation.
