# Milestone Music — Design Reconciliation (DESIGN ONLY, not implemented)

**Status:** reconciliation only. No code, no model experiment run, no provider chosen, no Edit Planner
work. Grounded in the real current design: `02-core-story-schema.md` §6 (MusicDirection), §22 (MusicAsset),
§23 (MusicAnalysis); `ai_contracts.py` (`MusicDirectionContract`, `MusicAssetContract`,
`MusicAnalysisContract`, `MusicSection`, `MusicEnergy`, `MusicSectionType`); `09-edit-planner.md`;
`12-edit-flow.md`; and the frozen E2 intelligence (CreativeIntent, StoryGuide, StoryCoverage/2,
MomentUnderstanding).

## 1. Current Music design summary (what already exists)
The design ALREADY separates intelligence from asset — the owner's A/B split is the design's own intent:
- **`MusicDirection`** (02 §6, `MusicDirectionContract`): "how the soundtrack should FEEL — not the
  selected song." Fields: `summary`, `mood_tags[]`, `energy{low|medium|high|dynamic}`, `progression`
  (free-text, e.g. "quiet opening → gradual build → emotional climax"), `raw_user_description`. Spec:
  "Story may infer MusicDirection from CreativeIntent; the user can change it; exact selection happens
  later during Create My Story."
- **`MusicAsset`** (02 §22, `MusicAssetContract`): the actual track — `id`, `title`, `duration_seconds`,
  `mood_tags[]`, `source{story_catalog|user_import}`, `audioReference`, optional `analysis`. Spec: "MVP
  should primarily use a small licensing-safe Story music catalog."
- **`MusicAnalysis`** (02 §23, `MusicAnalysisContract`): `bpm`, `beats[]`, `sections[]` (each a
  `MusicSection{type,start_seconds,end_seconds}`) — the beat/section grid the editor syncs to.
- **EditPlan** (09): references `music_track_id` + a `beat_sync` flag. Edit Planner CONSUMES music, does
  not author it.
- A Story owns an optional `MusicDirection` (02 §6 ownership); `Create my Story` is the disabled future
  entry to selection + edit + render → Result.

## 2. Stale assumptions in the old Music design
1. **Pre-E2 intelligence.** MusicDirection was specified to derive from CreativeIntent ALONE — before
   StoryGuide and StoryCoverage/2 existed. The reconciliation must decide whether Music now also reads
   the Guide (intended narrative shape) and Coverage (what material actually exists).
2. **No energy-ARC / timed-section intelligence.** `progression` is a single free-text string. There is
   NO structured "0–12s quiet, 12–38s build, 38–52s momentum, 52–60s payoff" representation — which is
   exactly the owner's MusicPlan hypothesis and the thing the Edit Planner needs for pacing. The timed
   `MusicSection` grid today lives on `MusicAnalysis` (a property OF a chosen track), NOT on a Story-level
   plan — so the structure exists but is attached to the wrong layer for planning.
3. **Catalog hand-wave.** "a small licensing-safe Story music catalog" is asserted but no catalog,
   provider, licensing path, or `audioReference` storage/delivery is specified. Spotify/Apple/TikTok are
   explicitly deferred (02 "not now"). So track SOURCING is genuinely unresolved — correctly.
4. **Timing unspecified.** "selection happens later during Create My Story" is the only timing note; when
   the DIRECTION/PLAN is computed vs when the TRACK is chosen is not pinned.
5. **Beat-sync assumed.** `beat_sync: true` in the EditPlan example presumes real `bpm`/`beats` analysis
   of the chosen track exists — which requires either catalog-precomputed analysis or an analysis step.

## 3. Music responsibility (MVP recommendation)
Music owns the **soundtrack INTELLIGENCE** for a Story: what the music should DO (feel + energy arc +
structural moments), and — separately and later — WHICH concrete track realizes it. It does NOT own cut
timing, shot selection, or the final edit (that is Edit Planner), and it does NOT own rendering (Media
Engine). Keep the two layers the design already implies, and ADD the missing middle layer:

- **MusicDirection** (exists): feel/mood/energy — inferred from CreativeIntent (+ optionally Guide), user-editable.
- **MusicPlan** (NEW — the owner's hypothesis): the Story-level STRUCTURED soundtrack plan — energy arc +
  timed sections + build/payoff — computed close to Create-My-Story from CreativeIntent + StoryGuide +
  StoryCoverage/2 (+ scope/duration). This is the Edit-Planner-facing artifact.
- **MusicAsset + MusicAnalysis** (exist): the concrete licensed track + its beat/section grid, selected to
  MATCH the MusicPlan. Sourcing is a separate concern (§6/§12).

## 4. Music vs Edit Planner boundary (load-bearing)
Recommended responsibility split (matches the owner's hypothesis):
```
CreativeIntent + StoryGuide + StoryCoverage/2            -> MusicPlan        (Music intelligence)
CreativeIntent + StoryGuide + StoryCoverage/2
  + MomentUnderstanding[] + MusicPlan (+ chosen MusicAsset/Analysis) -> EditPlan  (Edit Planner)
```
- **MusicPlan tells the Edit Planner HOW the Story should breathe**: pacing targets, where the build is,
  where the climax/payoff lands, where to leave breathing room, how to end. It is an ADVISORY temporal
  shape, not cut points.
- **Edit Planner owns the actual cut**: shot order, per-clip in/out, durations, transitions, which Moments
  go where, and reconciling MusicPlan's intended arc against the ACTUAL available material (Coverage/2
  told it what exists). The Edit Planner may deviate from the MusicPlan when the footage demands it —
  MusicPlan is creative context, not a deterministic template (same principle as StoryGuide → Edit).
- **Music must NOT become the Edit Planner**: MusicPlan never names Moments, never sets clip boundaries,
  never emits an EditPlan. If a MusicPlan field would only make sense as an edit instruction, it belongs
  on EditPlan, not MusicPlan.

## 5. Music intelligence vs track-sourcing boundary
Two hard-separated concerns:
- **MUSIC INTELLIGENCE** (MusicDirection + MusicPlan): model-authored, text-only, no audio, no provider.
  Buildable on the existing gateway now, with zero new infrastructure. This is where MVP value is.
- **MUSIC CATALOG / LICENSING / DELIVERY** (MusicAsset + audioReference + MusicAnalysis): concrete audio
  files, licensing, storage, streaming, and beat/section analysis. Requires product + legal + infra
  decisions (a catalog, or user-import, or generation) that are NOT reconciliation's to invent. Keep
  these decoupled so the intelligence can be built and evaluated BEFORE a provider exists (MusicPlan can
  carry `track_selection_criteria` that a later selector matches against whatever catalog is chosen).

## 6. Proposed MINIMUM MusicPlan representation (every field names a consumer)
Not a frozen contract — the minimum with a REAL downstream consumer (Edit Planner), to be validated by a
small experiment (§15) before freezing.
```
MusicPlan
- schema_version
- story_id
- source_* provenance (creative_intent / story_guide / story_coverage versions)   [consumer: staleness]
- target_duration_seconds                                                          [consumer: Edit Planner pacing]
- character: { mood_tags[], energy }      (reuse MusicDirection vocabulary)         [consumer: track selection + Edit Planner tone]
- energy_arc: ordered sections[]                                                   [consumer: Edit Planner pacing/build]
    - label         e.g. "quiet opening", "gradual build", "breakthrough", "resolve"
    - start_fraction / end_fraction   (0..1 of target duration — scope-relative, NOT absolute seconds)
    - intensity     categorical {low|rising|high|falling}   (NO numeric score)
    - note          one short line of intent
- key_moments[] (optional)                                                         [consumer: Edit Planner climax/payoff placement]
    - kind {build|payoff|breath|ending}
    - at_fraction
    - note
- track_selection_criteria (optional): { mood_tags[], energy, structure_hint }     [consumer: future track selector against a catalog]
```
Design rules (carried from the frozen E2 philosophy): **fractions, not absolute cut times** (Edit Planner
owns real timing); **categorical intensity, no numeric scores**; **advisory, not a template**; **scope-
sensitive** (a short Story gets a tiny arc, a 2-min Story a richer one); every field above has a named
consumer or it is dropped. `energy_arc` sections are the structural concept the current design only has as
`MusicDirection.progression` free-text + `MusicAnalysis.sections` (track-bound) — MusicPlan is where a
Story-level structured arc belongs.

## 7. Generation timing / lifecycle (recommendation)
- **MusicDirection**: inferred cheaply at/near Story creation from CreativeIntent (the "Here's what I
  understood" screen already shows a Music line — "Emotional cinematic · gradual build"). User-editable.
  This is a light, early artifact.
- **MusicPlan**: generated **at / just before Create My Story**, NOT continuously during capture. Rationale
  (and the owner's own hypothesis): the plan is only meaningful once the Story's actual shape + material
  are known (StoryGuide gives intended shape, Coverage/2 gives what exists). Recomputing it on every
  Moment would be waste with no consumer until the user decides to create. One active MusicPlan per
  create-attempt; recompute if the user re-opens Create My Story after materially more capture.
- **MusicAsset selection + MusicAnalysis**: at Create My Story, after MusicPlan, matching the plan's
  `character` + `track_selection_criteria` against the catalog (when a catalog exists).

## 8. Recomputation policy
Do NOT continuously recompute MusicPlan while capturing (no evidence of value; no consumer until create).
Recompute only when the user (re-)enters Create My Story and the inputs changed (CreativeIntent / Guide /
Coverage source set). Same keep-last-valid / no-fabrication discipline as Coverage.

## 9. Figma Music reconciliation
| Figma state | intended semantics | current backend capability | missing | future dependency |
|---|---|---|---|---|
| "Here's what I understood" → MUSIC line ("Emotional cinematic · gradual build") | show inferred MusicDirection | `MusicDirectionContract` exists; NO endpoint/engine wired (shown as DISABLED "Not available yet" in the iOS wizard today) | a MusicDirection infer step (cheap, from CreativeIntent) | none (text-only) |
| MUSIC "Change →" affordance | user edits MusicDirection | contract supports it; no UI/endpoint | edit surface + persistence | none |
| Create My Story (currently DISABLED) | enter planning → selection → edit → render → Result | nothing wired (mock output only, Milestone A) | MusicPlan + track selection + Edit Planner + renderer | catalog/provider; Edit Planner; Media Engine |
| Result / soundtrack on the final video | the chosen track plays under the edit | none (mock) | real render with audio | MusicAsset delivery + Media Engine |
Do NOT treat the demo "Emotional cinematic · gradual build" string as production intelligence — it is Figma
mock copy; the real MusicDirection must be inferred from the Story's actual CreativeIntent.

## 10. Actual-track sourcing status / open questions
- MVP **names no provider** and no concrete catalog — only "a small licensing-safe Story music catalog"
  (aspirational). Spotify/Apple/TikTok/Instagram explicitly deferred.
- `source{story_catalog|user_import}` is defined; `user_import` is the only path that needs no licensing
  deal (user supplies their own audio) and could be an MVP fallback.
- **Open product decisions (owner):** (a) does MVP ship a tiny first-party licensed catalog, allow
  user-import only, or defer audio entirely and ship Music as INTELLIGENCE-ONLY (MusicPlan with no track
  under a silent/placeholder render)? (b) if a catalog: who licenses it, where stored (`audioReference`),
  precomputed `MusicAnalysis` or analyze-on-ingest? (c) music GENERATION is not assumed anywhere — confirm
  it stays out of scope.
- Recommendation: build + evaluate **Music intelligence (MusicPlan) first**, decoupled from any track, so
  the hardest value question is answered before any licensing/infra commitment.

## 11. Create-My-Story integration
Intended future flow (reconciled): Story sufficiently developed → **Create my Story** → (MusicDirection
already inferred) → **MusicPlan** generated from CreativeIntent + Guide + Coverage/2 → **track selection**
(MusicAsset, when a catalog exists) → **Edit Planner** (EditPlan from material + MusicPlan + track) →
**render** (Media Engine) → **Result**. Ownership: Music owns MusicDirection + MusicPlan + track-selection
CRITERIA; a selector/catalog owns the actual MusicAsset; Edit Planner owns EditPlan; Media Engine owns the
render. `Create my Story` stays disabled until at least MusicPlan + Edit Planner + a (possibly trivial)
render exist.

## 12. Infrastructure implications
- **MusicPlan intelligence: ZERO new infrastructure** — text-only, existing gateway + App Runner, same as
  Guide/Coverage. A `POST /v1/music-plan` mirrors the existing endpoints.
- **Track sourcing: real infrastructure** — audio storage/CDN, licensing, optional analysis pipeline
  (bpm/beats/sections). Deliberately out of MVP intelligence scope; do not provision during reconciliation.

## 13. Is a MusicPlan model experiment needed? YES (small, bounded)
MusicPlan is a NEW task (CreativeIntent + Guide + Coverage/2 → structured energy arc). Like the StoryGuide
experiment, we must see real cross-domain output before freezing the contract — specifically to check it
produces a USEFUL arc without over-specifying (not inventing fake precision, scope-sensitive, not an edit
plan). NOT a broad bake-off; first confirm the task shape, then compare the already-trusted models (Sonnet
4.6 vs Opus 4.6) on identical fixtures/prompt/schema, temperature 0.

## 14. Proposed fixture / evaluation plan (if run)
Reuse the E2-a fixture spirit: TMB cinematic journey · guitar learning progression · SF exploration ·
birthday/social · minimal solitude · energetic short Story. Human-review rubric (frozen before scoring):
CreativeIntent alignment · emotional-arc coherence · scope/duration sensitivity (8s ≠ 2min arc) ·
usefulness to Edit Planner (does the arc give pacing/build/payoff a planner can act on?) · NOT
over-specified (no fake per-second precision, no cut points) · cross-domain (guitar ≠ travel arc) ·
structured validity · latency · cost. Spend gate $20, same as prior experiments. Feed each fixture a real
StoryGuide + a representative Coverage/2 so MusicPlan is evaluated on the actual E2 inputs.

## 15. Open product decisions (for owner)
1. Music MVP scope: intelligence-only (MusicPlan, no audio) vs intelligence + a tiny catalog vs + user-import.
2. Track sourcing / licensing path (if any audio ships).
3. Does MusicDirection now read StoryGuide (recommended: yes, lightly) or stay CreativeIntent-only?
4. MusicPlan freeze gated on the §13 experiment — approve running it?

## 16. Recommended Music milestone sequence
- **M-a (reconciliation):** this doc → owner review.
- **M-b (MusicPlan intelligence):** define MusicPlan contract candidate → small cross-domain experiment
  (§13/§14) → model pick → freeze MusicPlan contract + prompt. No audio, no infra.
- **M-c (MusicDirection infer + wire the Figma MUSIC line):** cheap infer from CreativeIntent, show real
  direction on "Here's what I understood", user-editable. No audio.
- **M-d (track sourcing DECISION — owner/product):** choose catalog / user-import / defer. Only then any audio infra.
- **M-e:** Edit Planner reconciliation (consumes MusicPlan) — a SEPARATE milestone, not Music's.
Create My Story stays disabled until M-b + the Edit Planner milestone + a render exist.

## 17. Is the Music design ready to freeze? NO — but reconciliation is clear.
The intelligence/asset separation is sound and already in the contracts. The design is **ready to proceed
to M-b** (MusicPlan intelligence experiment) — but NOT ready to FREEZE because: (a) MusicPlan's exact shape
needs the §13 experiment, (b) track sourcing is a genuine open product/legal decision (§10/§15), and (c)
MusicDirection's input set (does it read the Guide?) needs an owner call. Recommend: approve M-b
(intelligence experiment, zero infra) and defer all track-sourcing/licensing to the M-d product decision.
STOP here — no Music implementation, no Edit Planner.
