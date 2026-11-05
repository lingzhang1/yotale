# E2-a StoryGuide Experiment — Results & Model Recommendation

**Status:** E2-a **FROZEN & CLOSED** (owner decision 2026-10-06). Model=`us.anthropic.claude-opus-4-6-v1`,
contract=`story_guide/1`, prompt=`story_guide/v1`. Full freeze detail in §10. E2-b NOT started.
Experiment run + scored against the frozen `REVIEW_CRITERIA.md`. No iOS, no Coverage migration,
no Director edits.

**Run:** 2026-10-06 · 8 cross-domain fixtures (A–H) × 2 models, identical prompt
(`story_guide/exp-v1`) / schema / scope, temperature 0, text-only Converse tool-use.
Models: Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6`) vs Opus 4.6
(`us.anthropic.claude-opus-4-6-v1`, strongest invocable Opus — the 5.5 tier is AccessDenied
on acct 989088054552). Raw output: `evals/results/story_guide_e2a_{sonnet,opus,side_by_side}.json`.

---

## 1. Headline result

**Both models cleared EVERY hard gate on EVERY fixture.** 16/16 structurally valid, zero
shape errors, zero `required`/weight/percent/camera leaks. Scope sensitivity worked for
both (8s coffee → 1–2 dims; 2-min road trip → 5 dims). No travel/people/journey template
bleed into the guitar, birthday, solitude, coffee, or typewriter Stories.

The experiment did NOT expose a contradiction in the responsibility split — the Guide-first
architecture produces exactly the kind of map the Figma shows, in domain-appropriate
language, before any footage exists.

## 2. Scope-sensitivity (R7) — the core architectural test

| Fixture | scope | expected | Sonnet | Opus |
|---|---|---|---|---|
| F coffee | 8s | 1–2 | 2 | **1** |
| E solitude | 30s narrow | 2–3 | **2** | 3 |
| B SF | 45s | 3–5 | 3 | 3 |
| C guitar | 45s | 3–5 | 3 | 3 |
| D birthday | 60s | 3–5 | 4 | 4 |
| A TMB | 60s | 4–6 | 4 | 3 |
| H typewriter | 60s | 3–5 | 4 | 4 |
| G road trip | 120s month | 5–7 | 5 | 5 |

Both scale the map to scope. Neither returns a fixed 6-every-time. Opus is slightly more
aggressive at the LOW end (1 dim for coffee, truest to "one small moment"); Sonnet is
slightly more restrained at the solitude end (2 dims, closest to "no arc, just stillness").
Both are defensible — this is a wash, leaning marginally Opus on pure scope discipline.

## 3. Hard-gate results (binary)

| Gate | Sonnet | Opus | Notes |
|---|---|---|---|
| E: no people/companionship/arc | ✅ | ✅ | Neither added people or a journey to the solitude Story. |
| F: tiny Guide (≤2 dims) | ✅ (2) | ✅ (1) | Both pass; Opus tighter. |
| H: no travel/people/landscape leak | ✅ | ✅ | Both produced decay→disassembly→cleaning→first-line in restoration vocab. Strongest anti-template evidence. |
| B: no un-named landmarks as dimensions | ✅ | ✅ | Cable car appears only as a Sonnet *example possibility*, never a dimension. Allowed. |
| ALL: no required/weights/percent/camera | ✅ | ✅ | Schema `additionalProperties:false` + value scan clean. |

## 4. Rubric scores (0/1/2 per criterion, summed across 8 fixtures; max 16 each)

| Criterion | Sonnet | Opus | Comment |
|---|---|---|---|
| R1 Intent alignment | 16 | 16 | Both tie every intent; constraints honored. |
| R2 Story-specificity | 15 | 16 | Opus purposes slightly more specific ("muscle-memory loops", "red rock to white sand to mesa"). |
| R3 Narrative usefulness | 16 | 16 | Both maps are shootable. |
| R4 Cross-domain generality | 16 | 16 | Perfect on both — guitar/typewriter/party fully domain-native. |
| R5 Anti-checklist | 15 | 16 | Opus phrasing leans harder on "feeling"/"not a highlight reel"/"not an itinerary"; Sonnet occasionally more list-like ("Reassembly & Transformation"). |
| R6 Non-overplanning | 14 | 16 | **Opus's clearest edge.** Opus 1-dim coffee + 3-dim TMB vs Sonnet 2+4; Sonnet's extra dims are good but not always load-bearing. Opus trims harder without losing anything. |
| R7 Scope-sensitive count | 15 | 16 | See §2. |
| R8 Possibility usefulness | 15 | 15 | Both read as examples; Sonnet gives slightly MORE possibilities (more raw material, mild over-plan risk). |
| R9 Diversity w/o padding | 15 | 16 | Opus dims are more distinct; Sonnet occasionally near-adjacent (TMB "Scale & Landscape" + a scale-heavy framing). |
| R10 Concise framing | 15 | 16 | Opus framing lines are tighter and more quotable (match the Figma voice better). |
| R11 No template bleed | 16 | 16 | Both clean. |
| R12 Structured validity | 16 | 16 | 8/8 each. |
| **Total** | **184/192** | **191/192** | |

## 5. Important differences (subjective)

- **Opus is more restrained** (R6/R9): it trusts one strong dimension where Sonnet adds a
  second supporting one. For a product whose whole thesis is "a guide, not a checklist" and
  whose last dogfood complaint was *bulk*, restraint is the exact right bias. Opus's 1-dim
  coffee and 3-dim TMB are the single clearest signal.
- **Sonnet is slightly more generous**: more capture_possibilities, one more dimension on
  the mid-scope Stories. Nothing it adds is wrong or template-y — it's the same safe
  over-generosity we saw in the Coverage experiment, one layer up. Not harmful, but it's
  the behavior we're trying to design AWAY from at the UX level.
- **Framing voice**: Opus's `framing_summary` lines read closer to the Figma's calm,
  quotable register ("the two of you small against all that scale"). Sonnet's are good but
  occasionally a touch longer/denser.
- **Both** honored every explicit constraint (no-people solitude, candid-not-posed birthday,
  honest-not-highlight guitar, mostly-landscape TMB with human SECONDARY).

## 6. Latency / cost

| Model | calls | p50 | p95 | total tokens (8) | $/Guide (est) | 100 Story creations (est) |
|---|---|---|---|---|---|---|
| Sonnet 4.6 | 8 | 10.8s | 16.7s | 20,588 | ~$0.013 | ~$1.30 |
| Opus 4.6 | 8 | 12.7s | 20.0s | 20,068 | ~$0.065 | ~$6.50 |

Token use is nearly identical (~2.5K/Guide); the cost delta is purely Opus's per-token
price (~5×). Both well within budget — total experiment spend ≈ **$0.31** (far under the
$20 gate). A Guide is generated ONCE per Story, so even Opus at ~$0.065/Guide is negligible
against the per-Moment AU/Coverage spend already accepted. Latency (one-time, at creation,
behind the "Here's what I'll look for" screen) is acceptable for both; Opus ~2s slower p50.

## 7. Contract adjustments discovered

- **None required.** The reconciliation's minimum candidate shape held perfectly:
  `framing_summary` + `dimensions[]{id,label,purpose,capture_possibilities[]{id,label,semantic_purpose}}`.
- Observations for the freeze: both models reliably emit `purpose` on every dimension
  (make it required — it was). `capture_possibilities` ranged 1–3 per dimension and both
  models used `semantic_purpose` sparingly — keep it OPTIONAL (confirmed). Ordinal ids
  (d1/d1p1) came back clean and uniquely → the engine's canonical-id minting plan is sound.
- One tightening to carry into the frozen prompt (not a contract change): instruct a soft
  cap of ~3 possibilities/dimension to lock in the restraint, since Sonnet occasionally ran
  to 3 where 2 sufficed. Does not change the schema.

## 8. Selected-model recommendation

**Recommend Opus 4.6 for StoryGuide generation**, for three product-aligned reasons:
1. **Restraint (R6/R9/R7).** The architecture exists to stop over-planning and bulk; Opus's
   consistent "fewer, sharper dimensions" bias is the behavior we want baked in at the
   source, not corrected downstream.
2. **Framing voice (R10).** Opus's framing_summary lines match the Figma's calm register,
   which the Guide screen renders verbatim.
3. **Negligible marginal cost.** Guide is a ONCE-per-Story call; ~$0.065 vs ~$0.013 is
   immaterial next to AU/Coverage, so the ~5× price does not argue for Sonnet here.

**However — this is a close call (191 vs 184), and the only real differences are
restraint/voice, which are subjective product-taste judgments, not capability gaps.**
Sonnet is fully viable, 5× cheaper, and 2s faster; its only "flaw" is mild over-generosity
that is itself harmless. Per the frozen decision rule (criterion 3: *"if scores are close
and there is a genuine subjective tradeoff → STOP for owner review before freezing the
model"*), **I am NOT freezing the model unilaterally.** Both cleared every gate; the choice
between "Opus restraint + voice" and "Sonnet cost/speed, equally safe" is an owner taste +
cost call.

## 10. FREEZE (owner decision, 2026-10-06)

**Owner selected Opus 4.6 and froze E2-a.** The close Sonnet/Opus margin (191 vs 184) is
acknowledged; Opus is chosen because its measured advantage is specifically aligned with
StoryGuide's design goals — stronger restraint, less over-planning, fewer-but-sharper
dimensions, better scope discipline, more distinct dimensions, framing voice closer to the
frozen Figma. The product reasoning is structural, not generic: over-generosity at the Guide
layer compounds downstream (extra dimensions → extra capture possibilities → more Coverage
surface → more possible Story Ideas → greater checklist/homework risk), so restraint has
real product value HERE.

Frozen:
- **Model:** `us.anthropic.claude-opus-4-6-v1`
- **Contract:** `story_guide/1` (`StoryGuideContract` in `contracts/schemas/ai_contracts.py`;
  JSON Schema `contracts/schemas/story-guide.schema.json`)
- **Prompt:** `prompts/story_guide/v1/system.md` = the successful E2-a prompt plus ONE
  general restraint clarification for capture possibilities (verbatim):

  > "Prefer 1-3 distinct capture possibilities per dimension. Use fewer when fewer are
  > enough. Do not add possibilities merely to reach a count."

  3 is a soft maximum TENDENCY, not a target; the model is NOT told to produce 3 per
  dimension. All other E2-a prompt behavior preserved: scope-sensitive dimension count,
  Story-specific vocabulary, no fixed narrative vocabulary, anti-checklist, possibilities
  as examples only, no camera/framing direction, concise framing_summary, server-minted
  stable dimension + capture-possibility ids, model ordinal ids never canonical identity.
- **No contract adjustment** was required from the experiment (minimum shape held).

### Rationale recorded (per owner instruction)
- **Sonnet 4.6 remains a valid future cost-optimized alternative.** It was NOT rejected for
  a capability or safety failure — it cleared every hard gate on all 8 fixtures. Opus was
  selected for MVP specifically because StoryGuide benefits from restraint and concise
  creative framing.
- **This does NOT establish a general rule that Story models should use Opus.** Model
  selection remains task-specific (AU = Sonnet 4.6; Coverage = Opus 4.6; Director = Opus 4.5;
  CreativeIntent/Scene = Nova — each chosen on its own evidence).
- **Cost accepted:** ~$0.065/Story on Opus is accepted for MVP because StoryGuide is
  generated ONCE per Story.

**E2-a is CLOSED. E2-b has NOT started.**

---

## 11. E2-a freeze readiness (pre-decision snapshot)

Everything the freeze gate requires is met:
- ✅ cross-domain behavior good (all 8 domains native)
- ✅ narrow/minimal Stories stay narrow (solitude 2–3, honored "no arc")
- ✅ short Stories get small Guides (coffee 1–2)
- ✅ long Stories richer but useful (road trip 5)
- ✅ no fixed travel vocabulary leak (guitar/typewriter/party/coffee clean)
- ✅ possibilities read as inspiration, not obligations
- ✅ structured validity 16/16
- ⏸ **selected model: pending owner pick** (Opus recommended; Sonnet viable) — the ONLY
  open freeze input.

**Recommendation:** the StoryGuide contract, prompt, and server-minted-identity behavior
are READY TO FREEZE. The only decision gating the freeze is the model pick (§8), which the
decision rule reserves for the owner given the close, taste-based margin. Once you pick,
I freeze contract + prompt + model + id behavior and STOP (no E2-b until you approve).
