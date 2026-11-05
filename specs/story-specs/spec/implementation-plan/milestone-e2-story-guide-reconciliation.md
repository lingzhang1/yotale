# Milestone E2 — Story Guide / Coverage / Idea Architecture Reconciliation

**Status:** DESIGN RECONCILIATION — for review. NOT implemented. No production code
changed. No UI polish. No Music. No Edit Planner.

**Date:** 2026-10-06 · **Author:** default · **Supersedes direction of:**
`milestone-e-story-coverage-reconciliation.md` (shipped Coverage single-layer design).

**Trigger:** physical-device dogfooding + direct review of the frozen Figma revealed
that the shipped Milestone-E implementation collapses TWO distinct concepts the Figma
separates — a *persistent, Moment-independent creative map* and a *per-recompute
mapping of real material onto that map* — into one `StoryCoverage` object that invents
its narrative dimensions from `CreativeIntent + Moments` on every recompute. This is the
root cause of (a) dimension-id drift, (b) the 70–85-word Story Idea that reconstructs the
whole arc, and (c) the long "Reading your Story…" state on a brand-new zero-Moment Story.

**Grounding sources read for this doc (not assumed):**
- Current contract — `contracts/schemas/ai_contracts.py` → `StoryCoverageContract`,
  `CoverageDimension`, `CoverageSufficiency`, `CoverageStoryIdea`, `NarrativeCoverage`,
  `SufficiencyStatus`.
- Current engine — `packages/story_coverage/__init__.py` (`RealStoryCoverageEngine`).
- Retired design — `02-core-story-schema.md` §7 `StoryBlueprint`, §8 `NarrativeNeed`.
- Frozen Figma — 9 stills + 8 extracted demo-mvp-2/3 frames (creation → feeling →
  "Here's what I understood" → "Here's what I'll look for" → ready Home → persistent
  Story Guide → Shot Idea/Director → Story Idea on Home → Story index).

---

## 0. The one-paragraph correction

The product must stop asking *"given the Moments I have, what's missing?"* and instead:
**(1)** understand the overall Story the user wants → a persistent **StoryGuide** (loose
long-horizon creative map, generated once from CreativeIntent, exists before any Moment);
**(2)** as real Moments arrive and Asset Understanding completes, **StoryCoverage** maps
the actual material onto the Guide's *stable* dimensions; **(3)** **StoryIdea** selects
ONE high-value opportunity from Guide×Coverage; **(4)** only on **Show Me** does Scene
Understanding + Director turn that opportunity into an executable, scene-specific Shot.
Guide is advisory, never a checklist; Coverage never fabricates; the Story is allowed to
become better/different than the initial Guide.

---

## 1. Current-vs-proposed architecture

### CURRENT (shipped Milestone E)
```
CreativeIntent ─┐
                ├─▶ StoryCoverage ─┬─▶ Story Guide UX
Moments[] ──────┘  (invents          └─▶ Story Idea UX
                   dimensions every
                   recompute)
```
- Problem: `StoryCoverage.dimensions[]` are regenerated each call → ids drift, labels
  wobble, nothing persistent for a new Story, and the Idea has to re-explain the arc
  because there is no stable map to point at.

### PROPOSED (Milestone E2)
```
CreativeIntent ─▶ StoryGuide (generated ONCE, persistent, stable dimension ids)
                        │
   StoryGuide + completed MomentUnderstanding[] + pending_count
                        └─▶ StoryCoverage (references Guide dimension ids; derived; recomputable)
                                   │
     CreativeIntent + StoryGuide + StoryCoverage
                                   └─▶ StoryIdea (ONE opportunity, or null)
                                              │
         StoryIdea (semantic) ──▶ Show Me ──▶ SceneUnderstanding ──▶ Director ──▶ executable Shot
```
- StoryGuide is the single authoritative persistent creative-map concept.
- Coverage no longer owns narrative definition — it owns *state against* the map.
- Idea is concise by construction: it names one Guide-relative opportunity, it does not
  rebuild the map.

---

## 2. StoryGuide responsibility (deliverable 2)

Answers: **"What kinds of moments / narrative qualities could make the Story the user
asked for compelling?"**

- Inputs: CreativeIntent, Story topic/context, requested duration/scope, style/feeling,
  user description + reference context where available.
- Does NOT require existing Moments. A new Story has a meaningful Guide before Moment #1.
- Output: `framing_summary` + a small set (typically 4–6, scope-sensitive) of
  Story-specific narrative **dimensions**, each with a purpose and a few example
  **capture_possibilities**.
- It is semantic, not a screenplay: no beats, no required shots, no chronology except
  where narrative meaning genuinely depends on it (e.g. "Opening"/"Arriving" are
  bookends, not a timeline).

## 3. StoryCoverage responsibility (deliverable 3)

Answers: **"Given THIS StoryGuide and the Moments actually understood so far, how is the
Story taking shape?"**

- Inputs: StoryGuide (dimensions + ids), completed MomentUnderstanding[], pending_count,
  CreativeIntent (for interpretation only).
- Evaluates the Guide's existing dimensions (by stable id) — it does NOT invent a new set
  each recompute. This is the direct fix for the id-drift problem.
- Derived, recomputable, advisory. On failure it raises → caller keeps last valid cache.

## 4. StoryIdea responsibility (deliverable 4)

Answers: **"Given the Guide and current Coverage, what ONE additional opportunity would
add the most value right now?"** — or `null`.

- One opportunity, high-level, narrative, complementary, optional, scene-independent.
- Does NOT reconstruct the arc. The responsibility split (not truncation) is what keeps
  it to the Figma's ~2-sentence shape: *"A moment together — You have beautiful
  landscapes. A moment together could add some warmth."*
- `story_idea = null` remains first-class correct (sufficient Story, or no grounded
  worthwhile opportunity).

---

## 5. StoryIdea ↔ Director boundary (deliverable 5)

| | StoryIdea | Director |
|---|---|---|
| Question | WHAT kind of moment adds value to the overall Story? | GIVEN what's around you now, HOW to capture it? |
| Scope | scene-INDEPENDENT | scene-SPECIFIC |
| Contains | narrative opportunity, no framing/camera | framing, action, duration, scene-aware shot |
| Lifetime | persists on Story Home until superseded | ephemeral per CaptureSession |

Same StoryIdea *"A moment together"* → at a viewpoint Director yields *"Hold on your
friend looking over the valley, then let them turn toward you"*; at a hut *"Capture your
friend taking off their boots while you both rest"*; at dinner *"a natural interaction
across the table."* The Idea is constant; Director adapts it to the scene.

**Two Director entry points confirmed in the Figma (demo-mvp-2/3):**
1. **Story Idea card** → Show Me → Director (the "A moment together" path).
2. **Guide capture-possibility** with a `Shoot →` affordance ("Boots moving through
   terrain → Shoot") → Director directly, producing a Shot Idea **tagged by its owning
   Guide dimension** ("STORY GUIDE · OPENING — The Gear by the Door", "STORY GUIDE ·
   JOURNEY — Step by Step", each carrying `N sec · <purpose>`).

Both paths hand Director a *semantic opportunity + its owning Guide-dimension purpose*,
never a framing instruction. **Minimum Director-contract question is deferred to §29.**

## 6. Guide dimension vs capture-possibility semantics (deliverable 6)

- **Dimension** = a narrative purpose for THIS Story (e.g. Scale — "Make the mountains
  feel enormous"). Stable id, label, purpose.
- **capture_possibility** = an *example way* that purpose could be expressed (e.g. "person
  beneath huge mountains", "wide landscape, person entering frame"). These are
  ILLUSTRATIONS, never requirements. Internally they must NOT be called `required`,
  `shot`, or `task`. Sufficiency is NEVER "how many possibilities are checked."
- A single excellent Moment may satisfy a dimension's *purpose* even if no listed
  possibility was followed literally (see §7 flexible matching).

## 7. Flexible matching — purpose over obedience (deliverable 6 cont.)

Coverage matches real Moments to the **purpose** of a dimension, not to literal
capture-possibility text. Example: dimension "Departure" (examples: packing / leaving
hotel / first mountain reveal); the user instead captures *"puts on backpack and walks
onto trail"* → Coverage may legitimately mark Departure `strong`. Reuse the C4 Shot
Validation lesson: **purpose fulfillment > instruction obedience.** This is the single
most important anti-checklist guarantee in the design.

## 8. Director Beat relationship (deliverable 7)

Preserved boundary — do NOT merge:
- **StoryGuideDimension** = long-horizon, persistent, semantic Story opportunity.
- **Director Beat** = short-lived, per-CaptureSession plan for turning ONE selected
  opportunity into an executable capture in the current scene.

Director Beats are NOT persisted into StoryGuide, and StoryGuide dimensions do NOT
replace Director Beats. They operate at different time horizons and are produced by
different engines. (This matches the retired 02 §7 note that Blueprint "is not an
itinerary / timeline / day-by-day tasks.")

## 9. Stable identity decision (deliverable 8)

- **StoryGuide owns stable, Story-local dimension identity.** Guide dimension ids are
  **server/domain-minted** after Guide generation (same discipline already used for
  Director Beat/Shot ids and the Milestone-B id-minting lesson: never trust
  model-generated ids/labels as identity).
- Each capture_possibility also gets a server-minted stable id (so the UX
  checkmark/Shoot/Reshoot affordance and evidence mapping can reference it).
- **StoryCoverage references `story_guide_dimension_id`** (and optionally
  `capture_possibility_id`) — it does not carry its own dimension identity and does not
  invent replacement dimensions during ordinary recompute.
- Model-supplied label strings are display text only, never keys.

**Unmapped material:** if Coverage finds genuinely strong material that maps to NO Guide
dimension, it must PRESERVE that value rather than discard it. Decision in §18 + §22:
represent via a small `unexpected_strengths[]` only if a consumer needs structured access;
otherwise the existing free-text `strengths[]` already carries it. Recommendation: start
with `strengths[]` (free text) and add `unexpected_strengths[]` ONLY when Edit Planner or
Idea selection needs it machine-readable — do not expand the contract speculatively.

---

## 9b. Sufficiency semantics under the Guide (deliverable 9)

Keep the validated enum: `insufficient | workable | sufficient`. Reconcile its meaning
against CreativeIntent + StoryGuide + actual coverage:

- Sufficiency is NOT "all Guide dimensions covered" and NOT "all possibilities checked."
- It answers: *"Can a Story meeting the user's intent and requested scope be made from the
  currently understood material?"*
- Therefore: one excellent Moment may be sufficient for a tiny Story; several Guide
  dimensions may stay unexplored while the Story is still sufficient; ten redundant
  Moments do NOT create sufficiency; a dimension at `could_use_more` does NOT by itself
  make the Story insufficient.
- Preserve validated sensitivity to: target duration, intended scope, CreativeIntent,
  complementarity, redundancy, pending-AU uncertainty. (Unchanged from Milestone E —
  only the dimension *source* changes, not the sufficiency reasoning.)

## 10. Unexpected / serendipitous material (deliverable 10)

The Guide must not blind the Story to good material outside the plan (unexpected storm,
funny interaction, wildlife, a conversation, a local event). AU may mark such material
`strong_elsewhere` / describe it in `observed`.

- Coverage MUST preserve its narrative value even when it maps to no Guide dimension.
- The Story is allowed to become better/different than the initial Guide.
- MVP: do NOT auto-regenerate the Guide. Minimum representation so unexpected strong
  material stays visible to Coverage, Idea, and future Edit Planner:
  - **MVP default:** carry it in Coverage `strengths[]` (free text) — zero new fields.
  - **If a consumer needs it structured:** add `unexpected_strengths[]` (small objects
    `{note, evidence_moment_ids[]}`). Flag as the single candidate contract addition;
    decide at implementation when the Idea-selection prompt or Edit Planner actually reads
    it. Do not add speculatively.

## 11. Old StoryBlueprint reconciliation (deliverable 11)

The retired `02 §7 StoryBlueprint` / `§8 NarrativeNeed` design is **the direct ancestor of
StoryGuide** — the new work largely RECOVERS it rather than inventing something new:

| Retired concept | Disposition | New owner |
|---|---|---|
| `StoryBlueprint{ id, storyId, narrativeNeeds[], generatedAt, updatedAt }` | **RECOVER as StoryGuide** (persistent per-Story creative map) | `StoryGuide` |
| `NarrativeNeed{ id, label, purpose, exampleIdeas?, coverage? }` | **BECOMES StoryGuideDimension** (`id,label,purpose,capture_possibilities[]`) | `StoryGuide.dimensions[]` |
| `NarrativeNeed.exampleIdeas` (shot-like) | **BECOMES capture_possibilities** (examples, not shots) | `StoryGuideDimension.capture_possibilities[]` |
| `NarrativeNeed.coverage` (NarrativeCoverage enum, advisory, never a bar) | **MOVE off the Guide; it is per-recompute STATE** | `StoryCoverage.dimension_coverage[].state` |
| `NarrativeCoverage = unknown\|could_use_more\|looking_good\|strong` | **KEEP** (already implemented enum) | reused by Coverage |

**Net:** StoryGuide replaces the useful persistent part of StoryBlueprint; NarrativeNeed
→ StoryGuideDimension; the advisory `coverage` field was always *state*, so it belongs on
Coverage, keyed by the Guide dimension id. We end with ONE persistent creative-map concept
(StoryGuide), no duplicate long-horizon representation. The retired `StoryBlueprint` name
can be formally retired in favour of `StoryGuide` in 02-core-story-schema.md (doc-only;
no shipped code uses `StoryBlueprint`).

## 12. Current StoryCoverage field-by-field migration (deliverable 12)

Current `StoryCoverageContract` (shipped `story_coverage/1`):

| Current field | KEEP / MOVE / CHANGE / DROP | New owner / shape |
|---|---|---|
| `schema_version` | CHANGE (bump) | `StoryCoverage` → `story_coverage/2` |
| `story_id` | KEEP | Coverage |
| `moment_count` | KEEP | Coverage |
| `pending_count` | KEEP | Coverage |
| `source_understanding_ids[]` | KEEP | Coverage (provenance/staleness) |
| `generated_at` | KEEP | Coverage |
| `dimensions[]{id,label,purpose,coverage,note,evidence_moment_ids}` | **SPLIT** | **narrative def (id,label,purpose,examples) → `StoryGuide.dimensions[]`**; **state (coverage,note,evidence) → `StoryCoverage.dimension_coverage[]` keyed by `story_guide_dimension_id`** |
| `strengths[]` | KEEP | Coverage (now also carries unexpected material per §10) |
| `redundancies[]` | KEEP | Coverage |
| `sufficiency{status,reason}` | KEEP | Coverage (reasoning unchanged, §9b) |
| `story_idea{title,description,rationale}\|null` | KEEP + extend | Coverage; add optional `target_story_guide_dimension_id?` |
| — (new) | ADD | `story_guide_id` / `story_guide_version` on Coverage (which Guide it was computed against) |
| — (new, conditional) | ADD IF NEEDED (§10) | `unexpected_strengths[]` |

Nothing is thrown away: narrative definition relocates to the Guide (gaining stable ids),
all derived state stays on Coverage (now referencing those ids).

---

## 13. Proposed minimum StoryGuide contract (deliverable 13)

Minimum shape — every field names a consumer; no completion %, no `required` flags, no
numeric weights, no fixed vocabulary, no camera direction.

```python
class CapturePossibility(_Strict):           # EXAMPLE expression, NOT a required shot
    id: str                                  # server-minted, stable (consumer: UX affordance + evidence map)
    label: str                               # "person beneath huge mountains" (consumer: Guide UX row)
    semantic_purpose: str | None = None      # what it expresses (consumer: Director handoff, flexible match)

class StoryGuideDimension(_Strict):
    id: str                                  # server-minted, STABLE Story-local identity (consumer: Coverage ref)
    label: str                               # "Scale" (consumer: Guide UX section header)
    purpose: str                             # "Make the mountains feel enormous" (consumer: UX + Coverage matching + Director)
    capture_possibilities: list[CapturePossibility] = []   # 0..small; examples only

class StoryGuideContract(_Strict):
    schema_version: str = "story_guide/1"
    story_id: UUID
    generated_at: datetime
    source_creative_intent_version: str | None = None      # provenance (consumer: staleness/§28)
    framing_summary: str                     # "For this Story: one strong opening, movement through
                                             # the landscape, the scale of it all — and one big moment."
                                             # (consumer: Guide UX top line — matches Figma)
    dimensions: list[StoryGuideDimension]    # typically 4–6, scope-sensitive (§24 fixtures test this)
```

Notes:
- `framing_summary` is exactly the Figma's *"A guide, not a checklist…"* companion line
  ("For this Story: …"). It is Guide-owned, generated once.
- Dimension count is scope-sensitive, NOT fixed at 6 (an 8-second Story gets a tiny Guide;
  see §24 "very short Story" + "long/rich Story" fixtures).
- `capture_possibilities` may be empty for a dimension whose purpose needs no examples.

## 14. Proposed revised StoryCoverage contract after split (deliverable 14)

```python
class DimensionCoverage(_Strict):            # STATE of one Guide dimension (not its definition)
    story_guide_dimension_id: str            # FK → StoryGuide dimension (stable)
    state: NarrativeCoverage                 # unknown | could_use_more | looking_good | strong (REUSED enum)
    note: str | None = None
    evidence_moment_ids: list[UUID] = []
    represented_possibility_ids: list[str] = []   # which capture_possibilities the real material satisfies
                                                  # (consumer: UX checkmarks) — PURPOSE match, not literal

class StoryCoverageContract(_Strict):        # story_coverage/2
    schema_version: str = "story_coverage/2"
    story_id: UUID
    story_guide_id: str                      # which Guide this maps onto
    story_guide_version: str                 # Guide schema/version it was computed against (§28)
    moment_count: int
    pending_count: int
    source_understanding_ids: list[UUID] = []
    generated_at: datetime

    dimension_coverage: list[DimensionCoverage] = []   # one per Guide dimension (by id) — NOT invented here
    strengths: list[str] = []                # includes unexpected material (free text) per §10
    redundancies: list[str] = []
    # unexpected_strengths: list[UnexpectedStrength] = []   # ADD ONLY IF a consumer needs it structured (§10/§18)

    sufficiency: CoverageSufficiency         # {status, reason} — unchanged reasoning (§9b)
    story_idea: CoverageStoryIdea | None = None   # + target_story_guide_dimension_id? (below)
```

`CoverageStoryIdea` gains one optional field:
```python
class CoverageStoryIdea(_Strict):
    title: str
    description: str                         # SHORT (§15) — ~1–2 sentences, not an arc
    rationale: str | None = None
    target_story_guide_dimension_id: str | None = None   # which Guide dimension this opportunity serves
                                                          # (consumer: Director handoff §29, UX tag-back)
```

Do not freeze this blindly — §25 (regression migration) must pass before freeze.

## 15. Story Guide generation + Coverage recompute lifecycle (deliverables 15 + 16)

```
Story creation:  CreativeIntent completes ─▶ generate StoryGuide ONCE ─▶ persist.
Moment captured/imported: AU runs independently (unchanged).
AU completion:   mark StoryCoverage STALE (Guide untouched).
Coverage:        full recompute from StoryGuide + completed MomentUnderstanding[] + pending_count.
                 Persist/cache latest valid Coverage.
Story Home open: StoryGuide displays IMMEDIATELY (no model call — it is persisted).
                 Coverage overlays current state when available; if stale, show last valid
                 Coverage + recompute in background; if current, NO model call.
```
Rules: do NOT regenerate the Guide on every Moment. Do NOT call Opus over zero understood
Moments merely to produce guidance — the Guide has its OWN generation path at Story
creation, so a brand-new zero-Moment Story shows a real Guide and NO Coverage spinner.
**This directly eliminates the dogfood "Reading your Story…" dead state (§16).**

## 16. New-Story behavior (deliverable — product improvement)

Today: new Story, zero completed AU → Coverage has nothing to reason over → long "Reading
your Story…". Under E2: Story creation → CreativeIntent → **StoryGuide**, so meaningful
guidance exists before Moment #1. Coverage may legitimately be
`{moments:0, pending:0, dimension_coverage: all unknown}` and that is fine — the Guide
still renders. The Figma "ready to begin" Home (still #5: *"Your Story is ready to begin /
Your moments will appear here"* + full Story Guide with "A guide, not a checklist") is
exactly this state and is now BACKED BY REAL DATA, not a placeholder.

## 17. Pending AU (deliverable — preserve)

Unchanged good behavior: pending media is UNKNOWN, not absent. Guide is unaffected by AU
pending state. Coverage reasons only from COMPLETED MomentUnderstanding + records
`pending_count`. Never mark a dimension missing solely because relevant Moments are still
pending. Keep calm language: *"Still looking at N more moments — your guide will fill in
as they're ready."* No percentages/progress machinery.

---

## 18. Story Idea selection under the new architecture (deliverable — reconcile §13 of brief)

Selected from the relationship CreativeIntent + StoryGuide + StoryCoverage. NOT "pick the
weakest dimension" — a weak dimension may not matter enough to interrupt. Selection
considers: importance to CreativeIntent, current Story shape, redundancy, complementarity,
whether it would materially add something, pending uncertainty, and whether the Story is
already sufficient. `story_idea = null` stays first-class. FORBIDDEN: numeric opportunity
scores, progress %, deterministic weakest-dimension selection, completion quotas. The
selected Idea SHOULD set `target_story_guide_dimension_id` when it serves a specific Guide
dimension (enables the Figma dimension tag-back + Director handoff), but may be null for a
cross-cutting opportunity.

## 19. Failure / retry behavior (deliverable 17)

Each layer fails independently; **no layer fabricates another layer's output.**

- **StoryGuide generation failure:** Story creation must NOT lose the user's
  CreativeIntent. Enter a neutral "Guide pending" state and allow retry (manual or
  opportunistic). Do NOT fabricate a generic Guide. (CreativeIntent is already persisted
  independently today — Guide failure is recoverable.)
- **Coverage failure:** preserve the previous valid cached Coverage (existing
  `CoverageUnavailableError` → keep-cache path, unchanged). Guide remains available.
- **AU pending/failure:** Guide remains available; Coverage stays honest about the
  understood subset + pending_count.

## 20. Persistence / versioning (deliverable 18)

Version: StoryGuide schema, StoryGuide prompt, StoryGuide model, Coverage schema, Coverage
prompt/model, source CreativeIntent version, source MomentUnderstanding ids. MVP: ONE
active Guide version per Story. A future Guide regeneration MUST create a NEW Guide version
(not silently mutate the semantic meaning old Coverage was computed against) — Coverage
records `story_guide_version` so a stale Coverage can be detected when the Guide changes.
Do NOT build historical Guide browsing now.

iOS/backend persistence:
- Backend: `InMemoryStoryStore` already in-memory (dev); add a Guide slot keyed by
  story_id. iOS SwiftData remains source of truth — add a `StoryGuideModel` (one current
  Guide per Story, wire JSON) alongside the existing `StoryCoverageModel`.
- Guide is written once at creation; Coverage upserts on recompute (existing pattern).

## 21. StoryGuide model selection plan (deliverable 19)

Do NOT assume Opus just because Coverage uses it. Guide generation is a NEW task
(CreativeIntent → long-horizon creative map). Define a rubric BEFORE picking a model:
CreativeIntent alignment · Story-specificity · narrative usefulness · cross-domain
generality · anti-checklist behavior · non-overplanning · diversity of useful
opportunities · concise human-readable framing · avoidance of generic travel templates ·
structured validity · latency · cost.

Bounded candidate comparison only (Sonnet vs Opus likely; Nova only if a real
cost/behavior reason emerges — not automatically). **No broad bake-off.** Run the §24
fixtures through each candidate, human-review, pick the cheapest that clears the rubric.
(Hypothesis: Guide generation is more "creative framing" than "careful judgment", so
Sonnet may suffice and be cheaper/faster — must be measured, not assumed.)

## 22. Cross-domain StoryGuide fixture plan (deliverable 20)

Small cross-domain set, human-reviewed, BEFORE freezing the Guide. Minimum fixtures +
expected shape (dimensions illustrative, must derive from intent, NOT hard-coded):

| Fixture | Intent gist | Expected Guide (not a required list) |
|---|---|---|
| TMB / multi-day hiking | cinematic scenic journey, natural human presence | journey/scale/human/effort/arrival in Story-specific language |
| San Francisco exploration | city character | city character/scale/street life/details/people/progression — NO hard-coded landmarks the user didn't name |
| Guitar practice | focus/process | focus/process/struggle/progress/performance — NO travel dims |
| Birthday / social event | gathering & reactions | anticipation/gathering/reactions/relationships/celebration/closing |
| Minimal solitude Story | intentionally narrow | respects narrow scope; MUST NOT manufacture people/companionship/challenge |
| Very short Story (~8s) | tiny | SMALL Guide — NOT six dimensions |
| Long / rich Story | large scope | richer Guide appropriate to duration — tests scope sensitivity |

Pass criteria (human review): intent-grounded, Story-specific vocabulary, no generic
travel template bleed, no required-shot framing, scope-appropriate dimension count,
concise `framing_summary`, structured validity.

## 23. Coverage regression migration plan (deliverable 21)

Do NOT discard the existing Coverage regression suite (15 fixtures incl. semantic-envelope
A). Map each forward: express the OLD fixture's `CreativeIntent + Moments` as
`StoryGuide (generated from that intent) + MomentUnderstanding[]` → run new split engine →
score. Behaviors that MUST survive (STOP before implementation if any regresses
materially):
- false-sufficient protection · false-insufficient protection · no-checklist behavior ·
  `strong_elsewhere` retention · contextless-Moment handling · pending-AU honesty ·
  redundancy awareness · H1/H2/H3 stability (now expected to IMPROVE — stable Guide ids) ·
  nullable Story Idea · semantic-envelope fixture A within its approved envelope.

Hypothesis: the split should REDUCE dimension instability (H1/H2/H3) because dimensions no
longer regenerate per recompute — a measurable predicted improvement, to be confirmed.

---

## 24. Director handoff impact (deliverable 22)

Minimum future handoff: `StoryIdea` (or a Guide capture-possibility) → Director init /
current-recommendation context. Director should receive: CreativeIntent, the selected
semantic opportunity (`target_story_guide_dimension_id` + that dimension's `purpose` +
the Idea's title/description, OR the chosen `capture_possibility` + its dimension purpose),
current SceneUnderstanding, and compact Story/coverage context only if needed. Do NOT send
the entire StoryGuide or Moment library unless evaluation proves it necessary. Director's
job stays local execution.

**Open contract question (flag, do NOT implement):** does the existing Director
init/recommendation contract already accept "a high-level narrative opportunity + its
purpose"? Needs a read of `05-story-director.md` + the Director request contract. Two
possible outcomes:
- (a) Director already takes a free-text intent/opportunity string → NO contract change,
  wire the Idea/possibility purpose into it.
- (b) Director only takes SceneUnderstanding + CreativeIntent → MINIMUM change is adding an
  optional `selected_opportunity {dimension_id?, purpose, label}` field to the Director
  request. This is the single flagged possible contract change — **requires approval
  before implementation; not done here.**

## 25. Edit Planner boundary (deliverable 23)

Future Edit Planner consumes: CreativeIntent, StoryGuide (intended narrative shape),
StoryCoverage (how actual material maps to that shape), MomentUnderstanding/useful_segments,
MusicPlan, output constraints. Neither Guide nor Coverage pre-selects the final cut — Edit
Planner is free to omit Guide dimensions, emphasize unexpected strong material (hence §10
must keep that material visible), reorder, compress, and adapt to music/footage. **Guide is
creative context, not a deterministic edit template.** No Edit Planner work in this
milestone — boundary recorded only.

## 26. Figma screen/state ownership map (deliverables 24 + 31)

| Figma screen/state | Owning domain object | Real backend capability | Current status | Required migration | Content |
|---|---|---|---|---|---|
| "Tell me about this experience" (text input) | CreativeIntent (raw_text) | /v1/creative-intent | SHIPPED | none | real |
| "How should this Story feel?" (feeling/reference/describe) | CreativeIntent (feeling/style/reference) | /v1/creative-intent | SHIPPED | none | real |
| "Here's what I understood" (title, duration, tags, music, quote) | CreativeIntent (resolved) | /v1/creative-intent | SHIPPED | none | real |
| **"Here's what I'll look for" (6 dimensions, "can change as your trip unfolds")** | **StoryGuide** | **/v1/story-guide (NEW)** | **NOT IMPLEMENTED** | **build Guide engine+endpoint+iOS** | demo-only today → real |
| New Story Home "ready to begin / moments appear here" + Guide block | StoryGuide (+ empty Coverage) | Guide persisted; Coverage optional | PARTIAL (Coverage-only today) | render persisted Guide pre-Moment | demo-only → real |
| **Persistent Story Guide (dimension state tags + ✓/Shoot/Reshoot possibilities)** | **StoryGuide (def) + StoryCoverage (state)** | **Guide + Coverage/2** | **PARTIAL** (Coverage invents dims) | **split; state tags ← dimension_coverage; ✓ ← represented_possibility_ids** | partly real, needs split |
| Story Idea card ("A moment together / Show me →") | StoryCoverage.story_idea | Coverage | SHIPPED (too bulky) | shorten via split (§15), add dim tag-back | real |
| Shot Idea / Director ("STORY GUIDE · OPENING — The Gear by the Door", N sec · purpose) | Director output (Shot) tagged by Guide dimension | Director | SHIPPED (Director) | pass owning-dimension purpose into Director (§24) | real |
| Story index (Continue / Create now / Start a Story / Your Stories) | Story list | store | SHIPPED | none | real |

**"Content" column key:** real = backed by live data; demo-only = Figma mock not yet
backed; the "Here's what I'll look for" + persistent-Guide checkmark/Reshoot affordances
are the demo-only screens that E2 must make real.

**Figma checkmark/Shoot/Reshoot mapping (deliverable 14 of brief, §14 UX):**
- A capture_possibility shows **✓ + "Reshoot"** when a Moment's PURPOSE-match satisfies it
  (`id ∈ dimension_coverage.represented_possibility_ids`). "Reshoot" = optional improve,
  NOT an incomplete requirement.
- A capture_possibility shows **dashed ○ + "Shoot"** when not yet represented — an
  INVITATION, never an unmet requirement. Unchecked possibilities MUST NOT read as
  incomplete.
- Dimension-level tag maps `NarrativeCoverage`: `strong`→"You've got this covered",
  `looking_good`→"Looking strong", `could_use_more`→"Could use more", `unknown`→ no tag
  (or neutral). NO numeric %, NO "N/M".
- Do NOT fake literal completion to reproduce the screenshot — purpose fulfillment, not
  example matching, drives the ✓ (§7).

---

## 27. Backend migration scope (deliverable 25)

- **NEW** `packages/story_guide/` engine: CreativeIntent → `StoryGuideContract`, via
  generic ModelGateway, own versioned prompt `story_guide/v1`, server-minted stable
  dimension + possibility ids (reuse Milestone-B id-minting discipline), structured
  validation. Model TBD by §21 rubric.
- **NEW** contract `StoryGuideContract` (+ `StoryGuideDimension`, `CapturePossibility`) in
  `ai_contracts.py` + `story-guide.schema.json` + `generate_schema.py` registration.
- **CHANGE** `StoryCoverageContract` → `story_coverage/2`: `dimensions[]` →
  `dimension_coverage[]` (FK to Guide dim id), add `story_guide_id/version`, extend
  `story_idea` with `target_story_guide_dimension_id?`. Keep `strengths/redundancies/
  sufficiency`.
- **CHANGE** `packages/story_coverage/`: engine now takes StoryGuide as input, evaluates
  existing dimensions by id (stops inventing), remaps `represented_possibility_ids` by
  purpose-match, drops the per-recompute dimension minting. Prompt → `story_coverage/v2`
  (references the Guide's dimensions instead of deriving its own).
- **NEW** endpoint `POST /v1/story-guide` (JSON: CreativeIntent + scope → StoryGuide).
  **CHANGE** `POST /v1/story-coverage` request to accept the StoryGuide alongside MUs.
- Store: add Guide slot in `InMemoryStoryStore` keyed by story_id.
- Tests: Guide contract/engine/endpoint; Coverage/2 contract+engine; migrated regression
  suite (§23); the §24 Guide fixtures.

## 28. iOS migration scope (deliverable 26)

- **NEW** `StoryGuideDTO` (+ dimension/possibility) in `StoryContracts.swift`, mirroring
  the contract; **NEW** `StoryGuideModel` SwiftData (one current Guide per Story, wire
  JSON) in `Models.swift`; register in `StoryApp.swift` ModelContainer.
- **NEW** `StoryGuideService` (POST /v1/story-guide) + generation at Story creation (after
  CreativeIntent resolves), persist Guide.
- **CHANGE** `StoryCoverageDTO` → coverage/2 (`dimension_coverage[]` keyed by Guide dim id;
  idea gains `targetStoryGuideDimensionId`); **CHANGE** `StoryCoverageService` request to
  send the persisted Guide; **CHANGE** `StoryCoverageEngine` lifecycle: Guide shows
  immediately (no model call), Coverage overlays/recomputes on staleness.
- **CHANGE** `StoryHomeView` + `StoryCoverageViews.swift`: render the persistent Guide
  (dimensions, purposes, capture-possibilities with ✓/Shoot/Reshoot, dimension state
  tags) + the shortened Idea card; wire BOTH Director entry points (Idea → Show Me; a
  possibility's Shoot → Director) into the existing `SceneScanFlowView`.
- **NEW** "Here's what I'll look for" creation screen (post-CreativeIntent, pre-Start
  Story) rendering Guide v1 — matches Figma still #4.
- iOS tests: Guide decode; coverage/2 decode; dimension-coverage keyed by stable id;
  Guide renders pre-Moment; ✓ ← purpose match; Shot Idea tagged by dimension.

## 29. What existing implementation can be REUSED unchanged (deliverable 27)

- `NarrativeCoverage` + `SufficiencyStatus` + `CoverageSufficiency` enums/objects.
- `CoverageStoryIdea` (one optional additive field only).
- `strengths[]` / `redundancies[]` / `sufficiency` reasoning (§9b — only the dimension
  SOURCE changes, not sufficiency logic).
- The generic ModelGateway tool-use path, provenance minting, `CoverageUnavailableError`
  keep-cache failure path, compact-input discipline (no raw media/frames/Director history).
- The Milestone-E regression HARNESS (strict vs semantic-envelope scoring, fixture A
  envelope, decision-note machinery) — reused for the migrated suite (§23).
- iOS SwiftData JSON-in-model convention, AU queue/background-recompute pattern,
  `SceneScanFlowView` Director entry (both new entry points reuse it — no Director
  redesign, pending §24 contract read).

## 30. What must be DEPRECATED / REPLACED (deliverable 28)

- `StoryCoverageContract.dimensions[]` (per-recompute, drifting) → REPLACED by
  `StoryGuide.dimensions[]` (persistent) + `StoryCoverage.dimension_coverage[]` (state).
- `story_coverage/1` schema + `story_coverage/v1` prompt → superseded by `/2` (prompt no
  longer derives dimensions; it maps onto a supplied Guide). Keep `/1` fixtures as frozen
  history (do not rewrite history — Milestone-E rule).
- The notion that Coverage is the primary creative-reasoning entry → replaced by Guide-first.
- Retired `02 §7 StoryBlueprint` naming → formally folded into `StoryGuide` in the schema
  doc (doc-only; no shipped code references `StoryBlueprint`).
- Nothing SHIPPED is deleted destructively; the Milestone-E Coverage code is migrated in
  place (contract bump + engine change), not thrown away.

## 31. Risks / open decisions (deliverable 29)

1. **Director contract (§24):** may need one optional `selected_opportunity` field —
   flagged, needs `05-story-director.md` read + approval before any change.
2. **`unexpected_strengths[]` (§10/§18):** add as a structured field, or keep in free-text
   `strengths[]`? Decide when the Idea-selection prompt / Edit Planner actually reads it —
   recommend free-text for MVP.
3. **Guide model (§21):** unproven that Opus is needed; Sonnet may suffice (cheaper/faster)
   — requires the bounded §24 comparison, not assumption.
4. **Guide stability vs evolution:** MVP = generate once, never auto-evolve. Risk: a Story
   that materially changes direction (scenic hike → storm/struggle saga) keeps a stale
   Guide. Mitigated by §10 (unexpected material stays visible to Coverage/Idea/Edit) +
   §20 (future Guide v2 is a new version). Accept for MVP; record as future capability.
5. **Fixture-forward mapping (§23):** old fixtures were authored for intent+Moments; some
   expected behaviors may shift once a real Guide mediates. The STOP gate (any material
   regression) protects this, but expect some fixture re-expression effort.
6. **Scope creep:** E2 touches creation flow, Home, Guide, Coverage, Idea, two Director
   entry points — larger than Milestone E. Sequence to de-risk (§32).

## 32. Recommendation on readiness to freeze (deliverable 30)

**The architecture is READY TO FREEZE in principle** — it is a clean recovery of the
already-designed-and-retired StoryBlueprint/NarrativeNeed split, it resolves the three
observed dogfood problems (id drift, bulky Idea, empty-Story spinner) by *responsibility
separation* rather than new mechanism, and it preserves every validated Milestone-E
behavior (sufficiency reasoning, nullable Idea, pending honesty, keep-cache, anti-checklist,
semantic-envelope A).

**Two things gate the freeze of the CONTRACTS (not the architecture):**
1. The §24 cross-domain Guide fixture experiment + §21 model pick (we must see a real Guide
   per domain before we freeze `StoryGuideContract`).
2. The §23 Coverage regression migration passing (confirm the split does not regress the
   dangerous-error rates; H1/H2/H3 predicted to improve).

**Recommended sequence (for approval, not yet executed):**
- **E2-a:** build `StoryGuide` contract + engine + `/v1/story-guide`, run §24 fixtures +
  §21 model comparison, human-review → freeze `StoryGuideContract`.
- **E2-b:** split `StoryCoverage` → `/2` referencing Guide ids, migrate the regression
  suite (§23), STOP-gate on dangerous-error parity.
- **E2-c:** iOS (Guide persistence + creation "what I'll look for" screen + persistent
  Guide UX + shortened Idea + both Director entry points), §24 Director contract read →
  flag/approve any change.
- **E2-d:** deploy, device gate (new checklist), report.

Do NOT begin E2-a until this reconciliation is reviewed and the sequence approved. No
Music. No Edit Planner.

---

### Appendix — Figma evidence index (frames read for this doc)
Stills (in-message): creation input · feeling · "Here's what I understood" · "Here's what
I'll look for" (Departure/On the Trail/Scale/The People in It/Effort/Arriving + "This can
change as your trip unfolds") · ready-Home · persistent Guide (Opening ✓✓✓ "You've got
this covered"; Journey ✓✓○ "Looking strong"; Scale ✓○ "Looking strong"; Human moments ○○
"Could use more") · Shot Idea "The View From Here" · Story Idea "A moment together" · index.
Demo frames (demo-mvp-2/3): persistent Guide scroll · Shot Idea "STORY GUIDE · OPENING —
The Gear by the Door" (6 sec · Establishes the departure) · "STORY GUIDE · JOURNEY — Step
by Step" (5 sec · The texture of the trail) · GO/Got-it capture confirmation. These confirm
Shot Ideas are tagged by owning Guide dimension and reachable from a Guide capture-possibility.
