# Milestone E — Persistent Story Intelligence / Story Coverage (DESIGN RECONCILIATION)

> **Status: DESIGN RECONCILIATION — NOT implemented.** Repo-aware reconciliation of the pre-C1
> persistent-Story design against the system that actually exists after C1–C4 + Asset Understanding,
> plus a bounded-experiment plan to run before freezing. **Do NOT implement Story Coverage, do NOT
> modify Director, do NOT implement Edit Planner, do NOT touch canonical contracts** until this is
> reviewed and approved.
>
> Central question: **"What does this Story already have, what would genuinely improve it, and when
> should Story say nothing?"** Story Coverage is the first downstream consumer of real
> `MomentUnderstanding`.

---

## 1. Gap analysis — old persistent-Story design vs the actual current system

**What the OLD design (pre-C1, `02 §7-10`) specified**, and whether it survives contact with the
system that now exists:

| Old concept (`02 §7-10`) | Still correct? | Reconciliation |
|---|---|---|
| `StoryBlueprint { narrativeNeeds[] }` | **Partly.** The *idea* (a small set of narrative needs powering Guide/Idea) is right; the *name* "Blueprint" oversells it and the structure predates AU. | Keep the concept, rename/retire to a leaner `StoryCoverage`. Narrative needs are **derived + advisory**, not a stored authored structure. |
| `NarrativeNeed { label, purpose, exampleIdeas?, coverage? }` | **Yes, as a derived unit.** | Keep as a derived (not persisted-authoritative) element of coverage. `coverage ∈ {unknown, could_use_more, looking_good, strong}` already exists as the `NarrativeCoverage` enum in `ai_contracts.py`. |
| `StoryState { momentCount, narrativeCoverage: Record<need,coverage>, lastUpdatedAt }` | **Mostly.** This is genuinely "Story's current understanding of material collected" — exactly Coverage. | This becomes the heart of the new `StoryCoverage`. "Lightweight, no Story Graph" guidance still holds. |
| `StoryGuideIdea { title, description, worksBestWhen?, guidance? }` | **Yes**, but as reusable inspiration, distinct from a *contextual* Story Idea. | Keep as library inspiration; the contextual single "Story Idea" (§9) is a separate, intent+coverage-grounded output. |

**What materially CHANGED since the old design (why we must not auto-preserve it):**
- **AU now exists and is the real input.** The old design assumed Story would reason from raw Moments
  / Director history. It now reasons from structured `MomentUnderstanding` (observed + story_context).
  This is a stronger, cleaner input than the old design anticipated — coverage is now *derivable*, not
  something the user authors.
- **Director gained Concept→Beats→Shots + `DirectorState`/`BeatProgress`** (`05`), all scoped to a
  **CaptureSession**, not the persistent Story. Beats are explicitly "internal planning abstractions"
  (`05 §3-4`), with "don't make Beats a huge domain model yet" and an *open* "persistent-Story context
  depth" experiment. So the Director already produced the thing we must NOT confuse with persistent
  coverage.
- **`CreativeIntent` is now rich** (subject / desired_feeling / style_tags / emphasis /
  creative_constraints / pace / target_duration/format) — it already carries much of what the old
  "narrative needs" tried to express. Coverage must not duplicate it.
- **`StoryConcept.target_narrative_need_id`** and the `NarrativeCoverage` enum are already in the
  contracts — latent coverage hooks waiting for this milestone.

**Gap conclusion:** the old design is ~70% reusable as *intent* but must be re-derived as a **lean,
computed `StoryCoverage`** fed by AU, not a user-authored Blueprint and not a persistence of Director
beats.

---

## 2. Story Coverage responsibility (precise)

Story Coverage owns exactly: **"What does the collection of understood Moments mean for the Story?"**
Concretely it answers five questions and nothing else:
1. What useful material does this Story already contain? (strengths)
2. What narrative dimensions are strongly represented?
3. What is weak or absent?
4. Is anything genuinely worth suggesting next? (→ at most ONE Story Idea, §9)
5. **Is the Story already sufficient?** (→ ENOUGH, §7)

It does **NOT** own: observing raw media (AU) · scene-specific camera direction (Director) · final
edit selection/order (Edit Planner) · music · rendering.

Boundary table (preserve):

| System | Question it owns |
|---|---|
| Asset Understanding | "What exists in THIS Moment?" |
| **Story Coverage** | **"What does the collection of understood Moments MEAN for the Story?"** |
| Director | "Given the current scene, what should the user shoot NOW?" |
| Edit Planner | "Which material should the final output use, and in what order?" |

---

## 3. Director Beats vs persistent Story coverage — DECISION (§4, load-bearing)

**Decision: Director Beats are NOT persistent Story requirements. They are ephemeral, per-CaptureSession
planning abstractions and must not be lifted into a permanent Story checklist.**

Rationale, grounded in the repo: `05 §3-4` already states beats are "an internal planning abstraction,
not another thing users have to understand," scoped to one plan, with `BeatProgress`/`DirectorState`
living on the `CaptureSession` (`02 §14`, `ai_contracts.CaptureSessionContract`). A Director beat like
"show departure" exists to drive ONE scene's capture; it is not evidence that the persistent Story
schema needs a permanent required `departure` slot.

**The correct relationship:**
- **Director beats → (fulfilled captures) → Moments → AU → MomentUnderstanding → Story Coverage.**
  Beats influence coverage only *through the Moments they produced* and those Moments' understanding —
  never by being copied into the Story as requirements.
- Coverage's **narrative dimensions are derived from observed content + CreativeIntent**, NOT from the
  union of every beat any Director session ever planned. A beat that was planned but never captured
  leaves no trace in coverage (correctly — nothing was shot).
- This keeps ephemeral capture planning from ossifying into a rigid Story checklist (the §6 anti-goal).

---

## 4. Proposed MINIMUM persistent Story representation (`StoryCoverage`)

Every field names a consumer; nothing duplicates CreativeIntent / StoryPlan / MomentUnderstanding /
DirectorState. **Derived, recomputable, advisory.** Proposed shape (experimental — freeze only after §11):

```jsonc
{
  "schema_version": "story_coverage/1",
  "story_id": "uuid",
  "moment_count": 10,                 // understood Moments considered
  "pending_count": 2,                 // Moments with AU not yet complete (§14 honesty)
  "generated_at": "iso-8601",
  "source_understanding_ids": ["..."], // which MomentUnderstanding records this was computed from

  // Derived narrative dimensions — NOT authored, NOT a checklist, NOT shown as slots.
  "dimensions": [
    { "label": "environment / place", "coverage": "strong",
      "evidence_moment_ids": ["..."], "note": "many strong landscape Moments" },
    { "label": "human / companionship", "coverage": "could_use_more",
      "evidence_moment_ids": [], "note": "little human presence so far" }
    // coverage ∈ {unknown, could_use_more, looking_good, strong}  (existing enum)
  ],

  "strengths": ["string"],            // consumer: Story Guide ("what you have")
  "redundancies": ["string"],         // consumer: Idea/Guide — quantity != coverage (§C)
  "sufficiency": "insufficient | workable | sufficient",   // consumer: ENOUGH (§7)
  "story_idea": {                     // consumer: Story Idea surface. NULLABLE — §10 do-nothing.
    "title": "string", "description": "string", "rationale": "string"
  } | null
}
```

**Consumer map (every field earns its place):**
- `dimensions[].coverage` + `strengths` + `redundancies` → **Story Guide** (ordinary-language shape).
- `story_idea` → **Story Idea** surface (null = show nothing).
- `sufficiency` → the "you can Create My Story / ENOUGH" signal + future Director context.
- `pending_count` → honest uncertainty (§14).
- `source_understanding_ids` / `generated_at` → recompute invalidation + provenance.

**Retire / do not build:** a persisted `StoryBlueprint` authored structure; a persisted
`narrativeCoverage: Record<need,coverage>` keyed by stable need-ids (needs are derived per recompute,
not a stored registry); `BeatProgress` at Story level (that is Director/CaptureSession state). The old
`StoryState` collapses into this `StoryCoverage`. `StoryGuideIdea` library inspiration is a *separate,
later* concern — not required for this milestone.

> Open question for review: whether `dimensions` should be a **fixed small vocabulary** (environment /
> human / journey-progression / scale / difficulty / arrival-ending / detail) derived-and-scored, or a
> **free-derived** list per Story. The §11 experiment decides; my lean is a **small fixed advisory
> vocabulary** (stability across recomputes, §H) with free-text `note`.

---

## 5. MomentUnderstanding consumption rules

Coverage consumes the frozen split deliberately:

- **OBSERVED (`summary`, `subjects`, `events`, `temporal_order_note`, `useful_segments`)** → the
  factual basis for which narrative dimensions are present and how strongly. Dimension scoring reads
  observed content (e.g. human subjects present → "human/companionship" evidence; sustained
  landscape with no people → "environment" evidence). Observed stays request-independent.
- **STORY CONTEXT (`story_utility`, `requested_shot_contribution`, `requested_beat_contribution`)** →
  modulates weight, never replaces observed facts.

Required cases (all four handled):
- **Requested Shot fulfilled** → strengthens the dimension that Shot's purpose served (via the
  Moment's observed content), and raises `sufficiency` toward that dimension.
- **Requested Shot NOT fulfilled but `strong_elsewhere`** → **do NOT discard.** The Moment still
  contributes its *observed* content to whatever dimension it actually serves; `story_utility =
  strong_elsewhere` means "count this as real Story material elsewhere." (Fixture D.)
- **Contextless / Skip-Scan Moment** (no requested Shot/Beat; `requested_*` null) → coverage reasons
  purely from OBSERVED content. Coverage must never require a Director history. (Fixture E.)
- **Imported media / future contextless AU** → same as contextless: observed-only. Coverage must not
  depend on any Moment having a capture history. (Fixture E/§14.)

**Principle:** observed content is the floor every Moment contributes; story_context only adjusts
emphasis. A Moment is never worth zero to coverage just because it failed a requested Shot.

---

## 6. Coverage is NOT an obedience checklist (hard product rule)

Coverage represents **narrative opportunity and sufficiency**, never user obligation. Explicitly
forbidden in state and UX unless future evidence earns it: "3/7 required shots complete", "4 shots
remaining", required-shot counts, completion gates, progress bars over `NarrativeCoverage`. The user
can **always Create My Story with what they have** — coverage never blocks. Story Guide **helps**, it
does not assign homework. (This is why §4 keeps Director beats out of persistent coverage.)

---

## 7. Minimum-sufficient Story — ENOUGH is first-class

Carry the Director's minimum-sufficient philosophy up to Story level. `sufficiency` has three advisory
values:
- **insufficient** — too little understood material to tell any version of the intended Story.
- **workable** — a Story can be made; opportunities exist but are optional.
- **sufficient (ENOUGH)** — the Story already tells its intended thing; no suggestion is warranted.

Rules:
- One **exceptional** Moment may be `sufficient` for a small intended Story (CreativeIntent target
  duration/scope informs the bar). (Fixture F.)
- Two **complementary** Moments may already be `sufficient`. (Fixture B.)
- Ten **redundant** landscape clips do NOT raise coverage — quantity ≠ coverage; they inflate
  `redundancies`, not `dimensions`. (Fixture C.)
- A **missing category never auto-justifies interruption** — absence is only worth surfacing if it is
  (a) important to the CreativeIntent and (b) genuinely improvable. (Fixtures A, I.)

"Sufficient" is defined relative to **CreativeIntent** (scope/feeling/duration), not a template with
empty slots.

---

## 8. Story Guide (reconcile the Figma surface)

The frozen Figma Story Guide chapter names (Departure / On the Trail / Scale / …) and the
"✦ Story Idea — A moment together" card are **TMB DEMONSTRATION content**, confirmed in the capability
matrix note — they must NOT become generic production requirements. When this milestone ships, Story
Guide shows, in **ordinary language**, from real `StoryCoverage`:
- **what the Story already has** (1–3 `strengths`, plain language);
- **one or two meaningful weak areas** (`dimensions` with `could_use_more`/`unknown`) — gentle
  opportunity language, never a to-do;
- **an enough-material state** when `sufficiency = sufficient` ("Your Story already tells its story").

Avoid: raw AI metadata, scores, fake-precision percentages, rigid checklists, filmmaking jargon.
Story Guide communicates the Story's *evolving shape*, not a task list.

---

## 9. Story Idea (when to surface ONE)

A single Story Idea is surfaced only when it is: grounded in CreativeIntent; informed by what existing
Moments already contain; **complementary rather than redundant**; useful enough to justify an
interruption; and **high-level, not scene-specific**. Example: existing material = many mountain
panoramas → Idea = *"Capture a quiet human moment at the end of the day"*, NOT *"Take another wide
shot of the mountain."* (Fixture A.)

**Preserve the two-layer split:**
- **Story Idea** → long-horizon opportunity (Coverage output; high-level).
- **Show Me / DIRECT** → current SceneUnderstanding → Director → an executable, scene-specific shot.

Story Idea becomes scene-specific ONLY when the user invokes Show Me. Coverage never emits camera
direction.

---

## 10. Do-nothing behavior — a FIRST-CLASS output

`story_idea = null` is a legitimate, correct intelligence result, not a failure. Idea generation is
**not mandatory on every coverage update.** Valid reasons for no intervention: the Story already has
enough (`sufficient`); a new Moment did not materially change coverage; the remaining weakness is
unimportant or not improvable; information is too uncertain (high `pending_count`). (Fixtures F, I, and
the §11 no-intervention cases.) **Do not** build notification-frequency / engagement machinery now —
just preserve `no recommendation` as a real result the model is allowed (and expected) to choose.

---

## 11. Bounded Story-level evaluation fixture set (compose, don't collect)

Build a SMALL controlled set from **existing real `MomentUnderstanding` outputs** (we now have 18+ from
the AU gate + device runs) plus **carefully controlled synthetic structured MomentUnderstanding** where
a case needs it. Each fixture = {CreativeIntent, [MomentUnderstanding...], expected coverage behavior}.
Cases (minimum):

| id | composition | expected |
|---|---|---|
| **A scenery-only** | many strong environment Moments | recognize strong environment; surface a human/emotional *opportunity*; do NOT ask for more scenery |
| **B broad coverage** | scenery + departure + progression + difficulty | broad coverage; possibly `sufficient` / no suggestion |
| **C redundant scenery** | many near-identical mountain panoramas | recognize redundancy; quantity ≠ coverage; do NOT raise the environment dimension past one strong |
| **D strong_elsewhere** | Moment failed its requested Shot, AU says strong_elsewhere | retain its broader narrative value; count it toward the dimension it actually serves |
| **E contextless** | no requested Shot/Beat | reason from observed content alone; no Director history required |
| **F one exceptional** | a single outstanding Moment, small intended Story | may conclude `sufficient`; do NOT manufacture requirements |
| **G conflicting** | individually-good Moments that don't match CreativeIntent | recognize mismatch WITHOUT discarding factual AU; honest "doesn't yet match what you asked for" |
| **H long persistent** | several diverse Moments accumulated over time | coverage updates coherently; adding the newest Moment does not reset reasoning (stability) |
| **I no-intervention** | explicitly constructed enough/unimportant-gap cases | correct result = NO Story Idea |

Expected behaviors are human-reviewed ground truth (same discipline as the AU gate).

---

## 12. Model experiment (rubric first; run only if needed)

This is a NEW reasoning task — do not assume Opus (Director) or Sonnet (AU). **Define the rubric +
fixtures first, then run a SMALL comparison only if the design needs it.** No broad bake-off. Likely
candidates: Sonnet 4.6, Opus 4.x, possibly one other available reasoner. Rubric (score each arm):
coverage correctness · redundancy awareness · minimum-sufficient behavior · Story Idea usefulness
(human-reviewed) · no-intervention correctness · intent alignment · **stability when one Moment is
added** (§H) · hallucinated Story requirements (count) · latency · cost · structured-output
reliability. Decision prefers task-measured quality, like the AU gate.

---

## 13. Incremental vs full recomputation — DECISION

**For MVP: full recomputation from all current `MomentUnderstanding` records whenever coverage is
needed** (on Moment add/AU complete, and on Story Home open). Reasons: Moment counts are small (tens),
each MomentUnderstanding is already a compact structured summary (not raw media), full recompute avoids
stale accumulated reasoning and the §H "newest Moment resets everything" failure, and it is far simpler
than event-sourced incremental state. Estimate: ~N compact summaries into one reasoning call; even 30
Moments is a modest prompt. **Do NOT build event-sourced/incrementally-mutated Story intelligence**
unless measured Moment counts or latency later prove full recompute insufficient. (Revisit only on
evidence.)

---

## 14. Pending / failed AU — honest uncertainty

Coverage must not block ordinary Story use and must not treat an unanalyzed Moment as empty.
- **All understood** → full coverage.
- **Some AU pending/retryable** → compute coverage from the understood subset; set `pending_count > 0`;
  Story Guide may say "still looking at N recent moments." A pending Moment is **unknown**, not absent.
- **Contextless/imported not yet analyzed** → same: counted as pending, not zero.
- Coverage never waits on AU to let the user Create My Story. Represent uncertainty (`pending_count`,
  `unknown` dimensions) rather than guessing.

---

## 15. Relationship to Director (future boundary only — do NOT modify Director now)

Eventually Coverage may hand Director a **compact structured Story context**: what the Story already
has (strengths/dimensions), what opportunity would add value, and whether `sufficient`. It must **never
pass the entire raw Moment library** to Director. This milestone only *defines* that boundary; Director
is untouched. (This also finally answers `05`'s open "persistent-Story context depth" experiment:
Coverage is that compact context.)

---

## 16. Relationship to Edit Planner (boundary only — do NOT implement)

Coverage may provide **narrative context** to the Edit Planner, but the Edit Planner still makes global
material-selection + ordering from `CreativeIntent` + `MomentUnderstanding` + `useful_segments` + Music
+ output constraints (`09`). **Coverage must not pre-select the final cut** — it describes narrative
shape/sufficiency, not which seconds to use. `useful_segments` remain the Edit Planner's input, not
Coverage's output.

---

## 17. Figma / UX reconciliation

Surfaces that can become REAL when this milestone implements (flip the capability-matrix rows):
- **Story Guide** (`ScreenStoryBlueprint` / `ScreenTMB Guide`) → driven by `StoryCoverage.strengths` +
  weak `dimensions` + enough-state. TMB chapter names stay demo; real copy is derived.
- **Story Idea passive suggestion** (`ScreenTMB "✦ Story Idea"`) → `StoryCoverage.story_idea` (or
  hidden when null, §10). TMB "A moment together" stays demo.
- **Show Me** stays the Director path (unchanged) — Coverage feeds the *long-horizon* Idea, Show Me
  feeds the *scene-specific* shot.
- **Story Home** "Story Idea / Story Guide — not available yet" placeholders become live.
Preserve Figma fidelity; any behavior beyond the frozen UI is a documented REAL_SYSTEM_EXTENSION, not a
redesign.

---

## 18. Evaluation & regression format

A persistent-Story fixture = `{creative_intent, moment_understandings[], expected_coverage}` (JSON),
scored by a Coverage judge + human review for Story Idea usefulness. Every future dogfood failure
becomes a regression fixture: redundant Story Idea · unnecessary suggestion · wrong coverage · failure
to recognize enough material · suggestion conflicting with intent · ignoring `strong_elsewhere`
material · treating pending AU as empty. Human review stays required for Idea usefulness (same as AU).

---

## Deliverables summary (as requested)
1. **Gap analysis** — §1 (old `02 §7-10` ~70% reusable as intent; must re-derive as lean computed
   `StoryCoverage` fed by AU, not an authored Blueprint, not persisted Director beats).
2. **Precise Coverage responsibility** — §2 (the five questions; the four-system boundary table).
3. **Director Beat vs persistent coverage decision** — §3 (beats are ephemeral per-session; influence
   coverage only through the Moments they produced, never copied as requirements).
4. **Minimum persistent representation** — §4 (`story_coverage/1`: dimensions[]+coverage, strengths,
   redundancies, sufficiency, nullable story_idea, pending_count; retire Blueprint/StoryState/
   Story-level BeatProgress).
5. **MomentUnderstanding consumption rules** — §5 (observed = floor every Moment contributes;
   story_context modulates; strong_elsewhere retained; contextless/imported = observed-only).
6. **Sufficiency / ENOUGH** — §7; **Guide** — §8; **Idea** — §9; **do-nothing** — §10; **fixtures** —
   §11; **model rubric** — §12; **full-recompute decision** — §13; **pending-AU** — §14; **Director /
   Edit boundaries** — §15/§16; **Figma reconciliation** — §17; **eval format** — §18.

## STOP
Design reconciliation only. Next step (on approval): build the §11 fixtures from real
MomentUnderstanding + run the §12 bounded model comparison, then freeze the `StoryCoverage` design.
No implementation, no Director change, no Edit Planner, no canonical-contract change until approved.
