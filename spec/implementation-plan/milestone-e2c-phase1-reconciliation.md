# Milestone E2-c — Phase 1 Implementation Reconciliation (repo-aware delta)

**Status:** Phase 1 (inspection) complete — delta before substantial edits, per the owner's gate.
No production code changed yet. Frozen E2-a/E2-b semantics NOT reopened. One early finding escalated:
the **Phase-14 Director-contract gate is a real STOP** (existing contract cannot carry a selected
semantic opportunity) — reported below so it's visible before wiring, not discovered mid-edit.

Inspected: `apps/api/app/main.py` (routes + request models), `app/deps.py` (engine providers),
`packages/story_coverage/__init__.py` (Coverage/1 engine), `packages/story_director/__init__.py`
(Director initialize/next), `contracts/schemas/ai_contracts.py` (frozen StoryGuide/1 + StoryCoverage/2
+ internal types), the frozen prompts (`story_guide/v1`, `story_coverage/mapper-v1`,
`story_judgment/v2`), and the iOS Data/Contracts + StoryHome + StartStory + SceneScan file set.

---

## Backend delta

| area | CURRENT | TARGET | disposition |
|---|---|---|---|
| StoryGuide engine | none | `packages/story_guide/` RealStoryGuideEngine (Opus 4.6, prompt `story_guide/v1`, schema `story_guide/1`, server-mints canonical dim + possibility ids over model ordinals) | **ADD** |
| StoryGuide endpoint | none | `POST /v1/story-guide` (story_id + CreativeIntent + scope → StoryGuide/1; 503-on-fail, never fabricate) | **ADD** |
| Coverage engine | `RealStoryCoverageEngine` (Coverage/1: one call, CreativeIntent+MU→dimensions+suff+idea) | split: `RealStoryCoverageMapper` (Guide+MU→CoverageMapping) + `RealStoryJudgmentEngine` (evidence→StoryJudgment); compose → StoryCoverage/2 | **REPLACE** (keep /1 class for migration window only) |
| Evidence builder | none (Coverage/1 fed MU directly) | deterministic `build_judge_evidence()` (positive evidence + MaterialScopeEvidence from useful_segments + redundancy + pending; **NO Guide/states/candidates**) | **ADD** |
| Coverage endpoint | `POST /v1/story-coverage` (StoryCoverageRequest: intent+MU+pending→Coverage/1) | same path, body gains `story_guide` + returns Coverage/2 (Mapper→evidence→Judge→compose) | **CHANGE** |
| deps provider | `get_story_coverage_engine()` → Coverage/1 | add `get_story_guide_engine()`, `get_story_coverage_mapper()`, `get_story_judgment_engine()`; compose in the route | **ADD + CHANGE** |
| contracts | StoryGuide/1, StoryCoverage/2, CoverageMapping, StoryJudgment, MaterialScopeEvidence (all FROZEN E2-a/b, already in ai_contracts.py) | reuse verbatim | **REUSE** |
| prompts | mapper-v1, story_judgment/v2, story_guide/v1 (frozen) | reuse verbatim, do not tune | **REUSE** |
| store | `InMemoryStoryStore` | add a Guide slot keyed by story_id (dev; iOS SwiftData is source of truth) | **ADD** |

## iOS delta

| area | CURRENT | TARGET | disposition |
|---|---|---|---|
| StoryContracts.swift | Coverage/1 DTO (`StoryCoverageDTO` w/ `dimensions[]`), Director DTOs | add `StoryGuideDTO`/`StoryGuideDimensionDTO`/`CapturePossibilityDTO`; add `StoryCoverageV2DTO` (`dimension_coverage[]`, `story_idea` + `target_story_guide_dimension_id`); retire /1 DTO as active | **ADD + REPLACE** |
| Models.swift | `StoryCoverageModel` (one per Story, Coverage/1 JSON) | add `StoryGuideModel` (one active per Story, Guide JSON, canonical ids); repoint `StoryCoverageModel` to Coverage/2 JSON | **ADD + CHANGE** |
| StoryGuideService | none | `POST /v1/story-guide` client | **ADD** |
| StoryCoverageService | JSON POST → Coverage/1 | send persisted Guide too; decode Coverage/2 | **CHANGE** |
| StoryCoverageEngine.swift | on-device orchestrator (compact MU request, fingerprint staleness, keep-last-valid) — **this lifecycle logic is REUSED largely intact** | add Guide fingerprint to staleness; send Guide in request; decode V2; add "Guide shows immediately, no Mapper/Judge call when zero understood MU" rule | **REUSE core + CHANGE** |
| StoryCoverageViews.swift | Coverage/1 Guide/Idea mapper | persistent Guide (dimensions+purposes+possibilities w/ [x]/Shoot/Reshoot from `represented_possibility_ids`) + Coverage/2 state tags + concise Idea card | **REPLACE** |
| StoryHomeView.swift | shows cached Coverage/1, recompute on appear/after-capture | render persistent Guide pre-Moment + Coverage/2 overlay; both Director entry points | **CHANGE** |
| StartStory wizard (`CreativeDirectionView`) | intent → Story Home | after intent resolves → generate Guide → "Here's what I'll look for" screen (real Guide) → Story Home | **ADD screen + CHANGE** |
| StoryApp.swift container | registers StoryCoverageModel | + StoryGuideModel | **CHANGE** |
| SceneScanFlowView | Show Me → scan → Director (no opportunity carried) | carry selected_opportunity (Idea or Guide possibility) into Director — **GATED on Phase 14** | **CHANGE (gated)** |

---

## PHASE 14 FINDING — Director contract GATE (reporting before any edit, per owner)

**The existing Director contract CANNOT faithfully carry a selected semantic opportunity. A minimal
additive change is required.** Evidence from the actual code:

- `DirectorInitializeRequest` (`apps/api/app/main.py`) fields: `creative_intent`, `scene_understanding`,
  `capture_constraints` — nothing for "WHAT kind of moment the user chose to pursue."
- `StoryDirectorEngine.initialize(creative_intent, scene_understanding, capture_constraints)` and
  `build_initialize_request()` serialize exactly `{operation, creative_intent, scene_understanding,
  capture_constraints}` to the model. The prompt grounds its ONE recommendation in intent + scene; it
  has no notion of a pre-selected Story-level opportunity.
- iOS `SceneScanFlowView` enters `initialize` with intent + scene only.

**Could an existing field carry it?** `capture_constraints` is a free dict, so a Story Idea could be
*smuggled* in there — but that is semantically wrong (it is not a constraint, and the prompt treats
constraints as limits, not as the creative target). Overloading it would corrupt the Director's
reasoning. **So this is a genuine contract gap, exactly as the owner anticipated.**

**Minimum additive change (owner pre-approved IN PRINCIPLE; reporting the exact shape before editing):**
```
DirectorInitializeRequest / build_initialize_request content:
  + selected_opportunity: {                      # optional; null = today's behavior unchanged
       story_guide_dimension_id: str | null,     # owning Guide dimension when applicable
       label: str,                               # e.g. "A moment together" / "Boots moving through terrain"
       purpose: str,                             # the dimension purpose / idea description (semantic WHAT)
       capture_possibility_label: str | null,    # when entered from a Guide possibility
    } | null
```
Plus ONE prompt clause: "When `selected_opportunity` is present, treat it as the HIGH-LEVEL narrative
goal the user chose; decide HOW to realize THAT in the current scene. It is not a literal shot."
Director design/behavior otherwise unchanged — no redesign, beats stay ephemeral.

**This is NOT yet authorized to implement.** Per the owner's Phase-14 rule I STOP at the handoff-wiring
step (Phases 12/13/14) and need explicit go on this exact `selected_opportunity` shape before touching
the canonical Director contract. **Phases 2–11, 15–18 (Guide engine/endpoint, Mapper/Judge/evidence,
Coverage/2 composition + lifecycle, Guide/Idea UX display, persistence, migration, tests, production
gate) do NOT depend on the Director change and can proceed now.** Only the two Director *entry-point
wirings* (Guide-possibility Shoot, Story-Idea Show-Me handoff) wait on this gate.

---

## No canonical-contract contradiction found (other than the known Director gap)
StoryGuide/1 + StoryCoverage/2 + the internal types are internally consistent with the frozen prompts
and the existing MomentUnderstanding/CreativeIntent shapes. The iOS Coverage lifecycle (fingerprint
staleness, keep-last-valid, full recompute) maps directly onto Coverage/2 with a Guide-fingerprint
addition. Proceeding with Phase 2 (backend StoryGuide engine).
