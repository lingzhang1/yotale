# Milestone E — Story Coverage fixture/model/representation EXPERIMENT (report)

Report-only, per the approved reconciliation (`milestone-e-story-coverage-reconciliation.md`). Nothing
implemented; no canonical contract / Director / Edit Planner / Music touched. Fixtures + runner:
`evals/story_coverage/` (commit `417252f`). Experiment spend **~$3.67** (projected $3.16; gate $20;
text-only, no image cost).

## Headline
- **Dimension strategy: HYBRID wins** (stable-id structure + intent-derived labels). Fixed fails
  cross-domain; derived fails stability + anti-checklist.
- **Model: Opus 4.6 wins** on the task's two *dangerous* error types — **0 false-sufficient, 0
  false-insufficient, 0 missed worthwhile ideas**. Its only weakness is the *safe* one (over-eager
  optional ideas), which is prompt-tunable.
- **Full recomputation confirmed** — coverage evolves coherently across H1→H2→H3 and correctly stops
  recommending already-captured material.
- **Story Coverage is READY TO FREEZE** on: Opus 4.6 + hybrid dimensions + full recompute + the
  minimum `story_coverage/1` contract below — with one prompt-restraint tightening before implementation.

---

## 1-3. Fixture set, provenance, human references
15 fixtures (`evals/story_coverage/fixtures.json`): A scenery-only · B broad · C redundant-scenery · D
strong_elsewhere · E contextless · F1/F2 one-exceptional (short vs rich intent) · G conflicting ·
H1/H2/H3 accumulation · I no-intervention · **J anti-checklist (quiet solitude)** · **K non-travel
(guitar practice)** · L pending-AU. **Provenance: 32 REAL moment-understandings** (verbatim from the
AU production-gate device-grade run), **11 synthetic** (controlled: redundant panoramas, guitar), **2
pending** (L). Human references pin *semantic* properties + forbidden properties + a sufficiency label
+ whether a Story Idea should exist (never exact prose), per §1.

## 4-5. Dimension-strategy result → HYBRID

Swept fixed / derived / hybrid on Sonnet across all 15 (45/45 valid). Decisive cases:

| criterion | fixed | derived | hybrid |
|---|---|---|---|
| **cross-domain (K guitar)** | ❌ locked to travel labels (environment/place, challenge/tension, resolution/ending) — meaningless for practice | ✅ guitar-relevant (Concentration, Struggle→Breakthrough, Visible Progress) | ✅ guitar-relevant + stable ids |
| **anti-checklist (J solitude)** | ✅ idea=null | ❌ emitted an idea ("The Figure Who Stopped") — drifted into suggesting | ✅ idea=null |
| **stability (H1→H3)** | n/a (no ids) | ❌ no stable identity across recomputes | ⚠️ core dims semantically stable; ids drift slightly (see §10) |
| **redundancy (C)** | ✅ | ✅ | ✅ (all three nailed "8 identical panoramas add no coverage") |

**Fixed** cannot generalize beyond travel (hard fail on K). **Derived** fits semantically but has no
stable structure and was the only strategy that broke the solitude anti-checklist. **Hybrid** is the
only strategy that satisfied intent-fit AND anti-checklist AND a stable-id structure. **Recommend
HYBRID**: `dimension { id (snake_case, best-effort stable), label (intent-derived), purpose, coverage,
note }`.

> Caveat (honest): hybrid ids are **best-effort, not guaranteed stable** across independent recomputes
> (H1 `human_scale_contrast` → H2 `human_landscape_scale` → H3 `human_vs_landscape_scale` — same
> meaning, drifting id). **Consequence for implementation: do NOT key persistent state on dimension id
> across recomputes; treat dimension identity as semantic/fuzzy.** The id is a within-result handle +
> a stability *hint*, not a durable primary key.

## 6. Sufficiency — confusion vs human reference (hybrid, n=15)

| model | correct | false-sufficient (DANGEROUS: suppresses help) | false-insufficient (DANGEROUS: homework) |
|---|---|---|---|
| Nova Pro | 10/15 | **3** (B, C, H1, H2 — over-declares enough) | 0 |
| Sonnet 4.6 | 10/15 | 1 | 0 |
| **Opus 4.6** | **11/15** | **0** | **0** |

Sufficiency is correctly **relative to CreativeIntent + scope**, proven by F1 vs F2: the SAME single
Moment → `sufficient` for an 8s single-shot intent (F1) but `insufficient` for a rich 120s whole-trek
intent (F2). Sonnet and Opus both got the F1/F2 split right; **Nova got F2 wrong** (called the
one-Moment rich story "workable", a mild false-not-insufficient). No model derived sufficiency from
Moment count. **Opus is the only model with zero of BOTH dangerous errors.**

## 7. Story Idea usefulness (human review)
Opus's ideas on genuine-gap fixtures were strong, high-level, non-redundant, and emitted **no camera
direction** (no §7 hard-fail across any model/fixture):
- A (all scenery) → *"a moment of stillness at a summit/pass"* — human, not more scenery. ✅
- F2 (rich intent, 1 clip) → *"The crew in the crucible — your group during a hard stretch."* ✅
- G (landscape clips, intimacy intent) → *"show your partner as someone you love, not just someone you
  hike with."* — nails the intent mismatch. ✅
- K (guitar) → *"Then vs. Now — play the same riff from a later session."* — perfectly in-domain
  progress idea. ✅
Human-review questions (would it improve THIS story / is it missing / matches intent / helpful not
annoying / high-level enough for Director): Opus passed on all gap fixtures.

## 8. No-intervention accuracy
idea-exists match vs human ref: Nova 9/15, Sonnet 9/15, **Opus 10/15**. Error *shape* matters:
- Nova: 3 unnecessary + **3 missed** worthwhile ideas (misses are bad — a real opportunity goes
  unsurfaced).
- Opus: **5 unnecessary, 0 missed.** Its unnecessary ideas (B, H2, H3, I, J) were all **on-theme,
  high-level, optional** (it labeled those Stories `workable`, not `sufficient`, so it offered an
  *opportunity*, not homework) — e.g. J solitude → *"a moment of stillness on the ridge"* (on-theme for
  solitude, NOT a companionship/difficulty demand). These are **restraint-calibration gaps, not
  §7 hard-fails.** Opus never missed a real opportunity, which is the costlier error.

**Decision on the sufficiency↔idea link:** the experiment does NOT support hard-coding `idea=null` when
`sufficient`. Opus kept them loosely coupled (sometimes workable+idea, sometimes workable+null) and
got the dangerous cases right. Keep them **separate outputs**, nudge restraint via prompt, do not
make the relationship deterministic.

## 9. Pending-AU (fixture L)
All three models handled L correctly: computed coverage from the 2 understood Moments, did **not**
invent content for the 2 pending Moments, and treated them as unknown-not-absent. `pending_count` must
be passed in and surfaced. Observed tendency: models still emitted an idea under uncertainty — so the
restraint prompt should say *high pending_count tempers Story-Idea confidence* (none hallucinated a gap
FROM the pending media, which was the key failure to avoid).

## 10. Full-recompute stability (H1→H2→H3, Opus hybrid) — CONFIRMED
Coverage **evolved, did not reset**: core dimensions (human-scale, progression) persisted with stable
meaning across all three; the newest Moment never dominated. Crucially the **Story Idea tracked gap
closure**: H1 suggested companionship/reflective (gap) → H2 (companionship now covered by m3) shifted
to effort → **H3 correctly went NULL** once difficulty (m4) filled the last gap. **The model never
re-recommended already-captured material** — the central recompute-stability win. Only wobble: id
string drift (§4 caveat) and one H3 sufficiency call (Opus `workable` vs human `sufficient`) — the safe
direction. **Full recomputation is confirmed for MVP; no event-sourcing needed.**

## 14. Hallucinated-requirement analysis
**Zero generic-template requirements across all models on the anti-checklist fixtures.** K (guitar)
never got travel dimensions from any model under hybrid; J (solitude) was never pushed toward
companionship/difficulty as a *requirement* (Opus's J idea was on-theme stillness). The hybrid
strategy + the "coverage is not a checklist" system rule held. This was the biggest risk and it did
not materialize.

## 11-12 / 15. Model metrics + cost (hybrid, n=15; ESTIMATE us-east-1 on-demand 2026-10-05)

| model | suff ✓ | idea-match | false-suff | false-insuff | missed-idea | unnec-idea | p50 | valid | $/recompute (5/20/50 moments) |
|---|---|---|---|---|---|---|---|---|---|
| Nova Pro | 10/15 | 9/15 | 3 | 0 | 3 | 3 | **3.3s** | 15/15 | **$0.004 / $0.008 / $0.016** |
| Sonnet 4.6 | 10/15 | 9/15 | 1 | 0 | 3 | 3 | 26s | 15/15 | $0.030 / $0.045 / $0.074 |
| **Opus 4.6** | **11/15** | **10/15** | **0** | **0** | **0** | 5 | 28s | 15/15 | $0.133 / $0.208 / $0.356 |

Structured-output validity **45/45 every arm** (tool-use path). Cost is **trivial for a text-only
once-per-recompute call** even on Opus ($0.21 at 20 Moments). Latency (28s) is irrelevant — coverage is
background, not interactive.

## 16. Selected model → **Opus 4.6**, hybrid dimensions
Opus is the only model making **neither** dangerous error (false-sufficient suppresses help;
false-insufficient = homework) and **never missing a worthwhile idea**. Its over-eagerness to suggest
is the *safe* failure and is a prompt-restraint tuning problem, not a reasoning deficit. At ~$0.21 per
20-Moment recompute (background, infrequent), cost does not argue against it. This mirrors the
Director choice philosophy: the most intelligence-sensitive reasoning task gets the strongest reasoner;
unlike AU (per-Moment, high volume, Sonnet), Coverage is **once per Story recompute**, so Opus's cost
is immaterial. **Nova is rejected** (3 false-sufficient + 3 missed ideas — it both silences help and
misses opportunities). **Sonnet is the fallback** if Opus cost/latency ever matters.

> One prompt change before implementation: tighten restraint so a `workable` Story with no *materially
> valuable* gap yields `story_idea = null` more often (addresses Opus's 5 unnecessary-but-safe ideas).
> This is a prompt tweak, re-scored against these same fixtures — not a model or design change.

## 17. Proposed minimum `StoryCoverage` contract (every field earns its place)
```jsonc
{
  "schema_version": "story_coverage/1",
  "story_id": "uuid",
  "moment_count": 10,            // understood Moments considered — consumer: Guide ("what you have")
  "pending_count": 2,            // §9 honest uncertainty — consumer: Guide + idea-restraint
  "generated_at": "iso-8601",
  "source_understanding_ids": ["..."],   // recompute invalidation + provenance

  "dimensions": [                // HYBRID (§4). NOT a checklist, NOT shown as slots.
    { "id": "human_scale",       // best-effort stable; NOT a durable key (ids drift, §4 caveat)
      "label": "Human vs. Landscape Scale",   // intent-derived
      "purpose": "contrast the small figure against the vast terrain",
      "coverage": "strong",      // enum {unknown, could_use_more, looking_good, strong}
      "note": "..." } ],
  "strengths": ["string"],       // consumer: Story Guide
  "redundancies": ["string"],    // consumer: Guide/Idea — quantity != coverage (validated, fixture C)
  "sufficiency": "insufficient | workable | sufficient",   // separate scored output (§6)
  "sufficiency_reason": "string",
  "story_idea": {                // NULLABLE — null is first-class/correct (§8/§10)
    "title": "string", "description": "string", "rationale": "string" } | null
}
```
**Dropped / not added:** numeric scores or percentages (the experiment showed categorical `coverage` +
`sufficiency` are sufficient — no consumer needed numbers); Story-level `BeatProgress` (Director state);
a persisted authored Blueprint; a stable need-id registry (dimension ids are fuzzy, §4). `strengths`,
`redundancies`, `sufficiency_reason` each earned their place in the fixtures (Guide copy, redundancy
display, and auditability of the sufficiency call respectively).

## 18. Full-recompute decision → CONFIRMED
MVP: full recomputation from all current MomentUnderstanding + pending_count on each coverage need
(Moment add / AU complete / Story Home open). §10 proved it evolves coherently without reset; token
cost is trivial. **Do NOT build incremental/event-sourced Story intelligence.**

## 19. Figma / UX implications
Confirmed: `StoryCoverage` cleanly drives **Story Guide** (`strengths` + weak `dimensions` +
enough-state, ordinary language) and **Story Idea** (`story_idea` or hidden when null). TMB chapter
names stay demo. The capability-matrix rows ("Story Guide / arc", "Story Idea passive suggestion") can
flip to real when this milestone implements. Show Me stays the Director path (Coverage feeds the
long-horizon Idea; Show Me the scene-specific shot). No product redesign.

## 20. Ready to freeze?
**YES.** The representation question (hybrid), the model (Opus 4.6), the recompute strategy (full), the
contract (`story_coverage/1` above), and the hard product behaviors (not-a-checklist, ENOUGH, nullable
idea, strong_elsewhere retention, contextless/pending honesty) are all resolved and evidenced on real +
controlled fixtures. **One pre-implementation action**: apply the restraint prompt tweak (§16) and
re-score against these fixtures to pull Opus's unnecessary-idea rate down, then freeze. Every future
dogfood failure becomes a fixture here (§18 of the reconciliation).

## STOP
Experiment complete. No implementation, no Director change, no Edit Planner, no Music, no
canonical-contract change. Next on approval: freeze `story_coverage/1` (with the restraint prompt
tweak) and implement Story Coverage as a single Opus recompute call consuming MomentUnderstanding.

---

## FINAL DECISION (2026-10-06) — FREEZE THE ORIGINAL PRE-RESTRAINT OPUS PROMPT

The Phase-0 restraint tweak was run (Opus-only, hybrid, same frozen fixtures) and **FAILED the gate**:

| criterion | required | before (original) | after (restraint) |
|---|---|---|---|
| false-sufficient | 0 | **0** | 1 (A) ❌ |
| false-insufficient | 0 | **0** | 0 |
| missed worthwhile idea | 0 | **0** | 1 (A) ❌ |
| unnecessary ideas ↓ | yes | 5 | 2 ✅ |
| anti-checklist no regression | yes | J=null | J=idea ❌ |
| structured validity | intact | 15/15 | 15/15 |

Trading 3 fewer *safe optional* ideas (5→2) cost **1 false-sufficient + 1 missed worthwhile idea + 1
anti-checklist regression** — exactly the dangerous errors the gate protects. On fixture A the restraint
pressure made Opus *both* over-declare "sufficient" AND drop a genuinely worthwhile human-moment idea.
Per the owner rule ("if restraint causes missed ideas or sufficiency regression: STOP, do not stack
tweaks"), the restraint line is abandoned. **The ORIGINAL prompt is frozen** — it is the only
configuration with 0 false-sufficient, 0 false-insufficient, 0 missed worthwhile ideas, no harmful
template behavior, 15/15 validity. The restraint run is retained as regression/rationale evidence
(`evals/results/story_coverage_models_restraint.json`).

The 5 extra ideas are accepted for MVP as **SAFE OPTIONAL OVER-SUGGESTION** (on-theme, high-level,
optional, non-camera-specific, on `workable` Stories, not completion gates) — not reasoning failures.

### MVP Story Coverage error priority (most important to avoid, first)
1. **false-sufficient** (prematurely silences useful guidance)
2. **missed materially-worthwhile Story Idea** (a real opportunity goes unsurfaced)
3. **false-insufficient / homework behavior** (turns Story into a checklist)
4. **template/checklist requirement** (generic needs the intent never asked for)
5. **safe optional over-suggestion** (on-theme optional idea on a workable Story)

Do NOT optimize #5 at the expense of #1–#4. Suggestion frequency/presentation is a *separate* future
concern, revisited in dogfood — not Coverage reasoning.

### Reasoning vs intervention (architectural distinction, recorded)
Story Coverage answers **"Is there a useful Story opportunity?"** The product may *later* separately
answer **"Should we surface it right now?"** For MVP there is **no separate intervention-policy system**:
no idea confidence scores, no frequency limits, no timers, no notification policy, no deterministic
suppression thresholds. **Optional Figma presentation (hide the card when null) is sufficient restraint
for MVP.** The frozen Coverage prompt is the ORIGINAL (no restraint clause).

---

## PRODUCTION-PATH GATE (2026-10-06) — implementation vs experiment baseline

Ran the ACTUAL production engine (`RealStoryCoverageEngine` + real `BedrockModelGateway` tool-use,
Opus 4.6, `story_coverage/v1` original prompt) over the frozen 15 fixtures.

| metric | experiment baseline (1 run, plain-Converse) | production (tool-use), run 1 / run 2 |
|---|---|---|
| structured validity | 15/15 | 14/15 / **15/15** (one transient null-sufficiency, caught on repair) |
| false-insufficient | 0 | 1 / **0** (H1 — run variance) |
| false-sufficient | 0 | 1 / 1 (**fixture A only**) |
| missed worthwhile idea | 0 | 1 / 1 (**fixture A only**) |
| unnecessary (safe) ideas | 5 | 2 / 2 |
| p50 latency | ~28s | ~26s |

**Diagnosis of the A divergence (gate rule: STOP + diagnose before deploy).** Fixture A
(all-scenery, intent = "the beauty and scale of the TMB") is **genuinely boundary-ambiguous**: across
3 production calls the engine returned sufficient+idea, sufficient+null, workable+null. The intent
literally asks for *beauty and scale*, which strong scenery arguably already satisfies — so the model
legitimately wobbles across the sufficient/workable line, and the human reference ("workable + suggest
a human moment") is itself a defensible-but-disputable grader call. This is **fixture-boundary variance
on one ambiguous case, not a stable regression of the frozen reasoning**: production matches the
experiment on the 13 unambiguous fixtures, false-insufficient is 0, and the experiment's single run
simply sampled A's "workable+idea" outcome. Hardening applied (general, not fixture-tuning): Coverage
in-call structured repair raised 1→2 (removes the transient null-sufficiency). **Open judgment call for
the owner:** whether A's boundary wobble counts as a "material regression" that should block deploy, or
is accepted as a known-ambiguous fixture (recorded here, kept as a regression fixture, revisited in
dogfood). Everything else matches baseline.

---

## Phase 1 (post-freeze) — Fixture A classified semantic-envelope; production gate PASSED (2026-10-06)

Owner decision (2026-10-06): **Fixture A is a KNOWN-AMBIGUOUS semantic-boundary
fixture, NOT a material production regression.** A's CreativeIntent is explicitly
"the beauty and scale of the TMB" over strong scenery material, so both
`workable + optional complementary idea` and `sufficient + null` are semantically
defensible; repeated production runs (sufficient+idea / sufficient+null /
workable+null) confirmed a genuine narrative judgment boundary, not a stable model
failure. The frozen prompt/model/schema/engine were NOT changed — this was a
HARNESS-ONLY classification change.

**Harness change (minimal):** every fixture now carries an explicit `eval_mode`
(`strict` | `semantic_envelope`). 14 fixtures are `strict` (exact human-reference
expectations). A is `semantic_envelope` with an acceptable set
{sufficiency ∈ workable|sufficient; story_idea ∈ null|one optional complementary},
a forbidden set (insufficient / "scenery missing" / request-more-scenery /
mandatory-companionship / template / camera-direction / intent-contradiction), and
a `decision_note` recording the original human reference, the observed variance,
why ambiguity was accepted, and the owner date. The original human_reference is
preserved verbatim; history is not rewritten.

**Production gate re-run (Opus 4.6, original prompt, hybrid, model/prompt/schema/engine UNCHANGED):**

| group | metric | result |
|---|---|---|
| STRICT (n=13 valid) | false-sufficient | **0** |
| STRICT | false-insufficient | **0** |
| STRICT | missed worthwhile idea | **0** |
| STRICT | unnecessary (safe-optional) ideas | 3 (accepted MVP class #5) |
| SEMANTIC-ENVELOPE (A) | within envelope | **1/1** (sufficient + null) |
| all | structured validity | 14/15 (B transient null-sufficiency → designed-safe 503/keep-cache) |
| all | p50 latency | ~24 s |

No previously-strict fixture showed meaningful semantic variance into a dangerous
direction (J/C/K produced on-theme, non-forbidden ideas; J's "unnecessary" idea
stays entirely within solitude — zero forbidden hits). **Gate PASSED.** No further
fixture was auto-classified ambiguous; future ambiguity classification requires
explicit owner review.

### Error priority (frozen for MVP)
1. false-sufficient (silences useful help) — avoid most
2. missed materially-worthwhile Story Idea
3. false-insufficient / homework behavior
4. template/checklist requirement
5. safe optional over-suggestion (tunable later, do NOT optimize at the expense of 1–4)

### Reasoning vs intervention (architectural note)
Story Coverage answers "is there a useful opportunity?". A future, separate layer
may answer "should we surface it right now?". MVP builds NO intervention-policy
system (no idea confidence scores, frequency limits, timers, notification policy,
or deterministic suppression thresholds) — optional Figma presentation is
sufficient restraint.
