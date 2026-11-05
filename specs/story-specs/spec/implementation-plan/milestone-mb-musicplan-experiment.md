# Milestone M-b — MusicPlan Intelligence Experiment — Results

**Status:** experiment complete, scored against the frozen `REVIEW_CRITERIA.md`. Intelligence/contract
only — no production Music, no catalog, no provider, no audio infra, no Edit Planner. Recommendation +
freeze-readiness below. Raw: `evals/results/music_plan_mb.json`.

**Run:** 2026-10-07 · 6 cross-domain fixtures × {Sonnet 4.6, Opus 4.6} × {Arm A = Guide only, Arm B =
+Coverage/2} = 24 calls, temperature 0, text-only tool-use. 24/24 structurally valid.

## 1. Experimental MusicPlan contract (as tested)
`character{mood_tags[], energy}` + `energy_arc[]{label, start_fraction, end_fraction, intensity
(low|rising|high|falling), note}` + `key_moments[]?{kind(build|payoff|breath|ending), at_fraction, note}`
+ `track_selection_criteria?{mood_tags[], energy, structure_hint}` + `audio_strategy{soundtrack_role
(continuous|supportive|sparse), native_audio_priority(low|selective|important), guidance}`. Fractions 0..1,
categorical intensity, no numeric scores, no cut times, no Moment/clip ids, no transitions.

## 2. Fixtures
A TMB cinematic journey (Coverage = storm/struggle) · B guitar (NATIVE-AUDIO-DOMINANT #7) · C SF
exploration · D birthday (singing/laughter native audio) · E minimal solitude · F energetic 8s skate.
Each carries real CreativeIntent + MusicDirection + a frozen StoryGuide + a representative Coverage/2.

## 3. Human-review criteria — frozen before scoring (`REVIEW_CRITERIA.md`).

## 4–5. Sonnet & Opus outputs (summary)
Both models: 24/24 valid, scope-sensitive, native-audio-aware. Scope was excellent on BOTH — E solitude →
**1 region "Held stillness [low]"** (no build), F skate → **1 region "[high]"**, A/B/D → 3, C → 2–3. No
model over-sectioned anywhere; neither invented a quiet→build→climax where it didn't belong.

## 6. Rubric comparison (both clear every hard gate → both eligible)
| criterion | Sonnet | Opus | note |
|---|---|---|---|
| R1 intent / R2 guide align | good | good | both on-intent, no 1:1 guide→section mapping |
| R4 arc coherence | good | good | — |
| R5 scope sensitivity | **2** | **2** | both nail E=1, F=1, rich=3 (tie, excellent) |
| R6 cross-domain | good | good | guitar≠travel, skate≠cinematic, no vocab leak |
| R7 planner usefulness | good | good | arc + audio_strategy are actionable |
| R8 restraint | good | **slightly better** | Opus guitar/B ends on `falling` ("the song takes over" → score recedes) — a cleaner arc semantic than Sonnet's `high` |
| R9 native audio | **2** | **2** | both supportive/sparse+important on B/D; both say music recedes for the song/singing |
| R10 anti-template | good | good | A Arm-B grit, E stable, C groove-not-climax |
| R11 validity | 24/24 | 24/24 | — |

**Difference is marginal.** The one qualitative edge: Opus's guitar Arm-B arc ends on `intensity: falling`
("the song takes over") — a more honest "soundtrack recedes at the payoff" shape than Sonnet's `high`
there. Everything else is a tie.

## 7. Coverage A/B ablation — KEEP Coverage (evidenced)
Arm B produced MEANINGFULLY better/different plans where Coverage should matter:
- **A TMB:** Arm A = generic "cinematic/emotional/expansive" scenic swell. **Arm B → moods gain
  "gritty/vast", notes name "storm drama, physical effort", "grit earns its place here, not just
  grandeur"** — the plan correctly became a come-through-it story, matching the storm/struggle Coverage.
  This is exactly the intended-arc-vs-actual-material correction.
- **B guitar:** Arm A = `supportive`; **Arm B (Sonnet) → `sparse`** because Coverage flagged a strong real
  song take — the plan pulled the soundtrack further back for it. Correct responsiveness.
- Coverage never caused music to "compensate" for weak dimensions (no fabricated sections). It added
  signal, not noise. **→ StoryCoverage/2 is a production MusicPlan input.**

## 8. Native-audio findings — the audio_strategy block EARNS its place
On B (guitar) and D (birthday) both models set `soundtrack_role: supportive/sparse` + `native_audio_priority:
important` + concrete guidance ("step back so the real guitar lands", "music should nearly vanish under the
Happy Birthday singing"). On F (skate, no meaningful native audio) → `continuous`. This is real, actionable
Story-level info a soundtrack-less or music-first editor would get wrong. **Keep audio_strategy** — it is the
most clearly load-bearing NEW field. (soundtrack_role + native_audio_priority both drive planner behavior;
`guidance` is a human/debug line — keep it OPTIONAL.)

## 9. key_moments — DROP (evidenced)
The emitted `key_moments` are **redundant with `energy_arc`**: TMB `payoff@0.75` = the "Emotional peak"
region; birthday `ending@0.95` = inferable from the last region; `build@0.25` = the "rising" region's start.
The only sometimes-additive one is `breath`, and it was inconsistent (Sonnet emits it, Opus often doesn't) —
and a `breath` is inferable from an intensity drop in the arc. **No concrete Edit-Planner decision requires
key_moments that `energy_arc` + `audio_strategy` cannot already express.** → drop it from the frozen contract.

## 10. Field-by-field Planner-consumer analysis (what could Edit Planner do differently?)
| field | planner uses it to… | verdict |
|---|---|---|
| `character.mood_tags/energy` | set overall tonal target + hand the track selector a brief | **KEEP** |
| `energy_arc[].label` | human-readable region id (debug / future UI) | keep (cheap) |
| `energy_arc[].start/end_fraction` | map pacing regions onto the timeline (where to breathe vs drive) | **KEEP** |
| `energy_arc[].intensity` | decide cut rhythm per region (slow holds in `low`, quicker in `high`, settle on `falling`) | **KEEP** |
| `energy_arc[].note` | tie-breaker intent when a region is ambiguous | keep OPTIONAL |
| `key_moments` | — nothing the arc can't express — | **DROP** |
| `track_selection_criteria` | future track selector against a catalog (M-d) | keep OPTIONAL (no consumer until M-d, but zero cost and the natural handoff) |
| `audio_strategy.soundtrack_role` | decide whether to lay continuous music vs duck/leave gaps | **KEEP** |
| `audio_strategy.native_audio_priority` | decide whether native audio can own moments | **KEEP** |
| `audio_strategy.guidance` | human/debug prose | keep OPTIONAL |

## 11. MusicDirection / MusicPlan ownership — REFERENCE, don't duplicate (recommendation)
`character` in MusicPlan overlaps `MusicDirection` (mood/energy). To avoid two sources of truth: MusicPlan
should REFERENCE MusicDirection as its character source rather than re-author it — i.e. MusicPlan owns the
STRUCTURED TEMPORAL plan (energy_arc + audio_strategy), and carries character only as a resolved SNAPSHOT of
the MusicDirection it was computed against (for provenance / standalone use by the selector), not as a
competing authority. Mood/energy/progression authority stays with MusicDirection (user-editable). **Do NOT
modify canonical MusicDirection now** — this is a freeze-time note for M-c.

## 12. Final recommended MINIMUM MusicPlan shape (freeze candidate)
```
MusicPlan
- schema_version, story_id, provenance{creative_intent/story_guide/story_coverage/music_direction versions}
- target_duration_seconds
- character { mood_tags[], energy }            # resolved snapshot of MusicDirection (referenced, not owned)
- energy_arc[] { label, start_fraction, end_fraction, intensity(low|rising|high|falling), note? }   # SMALL, scope-sensitive
- audio_strategy { soundtrack_role(continuous|supportive|sparse), native_audio_priority(low|selective|important), guidance? }
- track_selection_criteria? { mood_tags[], energy, structure_hint }   # handoff to the future selector (M-d)
```
**DROPPED vs the candidate:** `key_moments[]` (redundant with energy_arc — §9).

## 13. Selected-model recommendation
Both cleared every hard gate; the margin is marginal (Opus's `falling`-at-payoff on guitar is the only
qualitative edge). This mirrors E2-a. Per the frozen rule (close + subjective → owner review), I recommend
**Opus 4.6 for consistency with the Coverage/Guide stack and its slightly cleaner recede-at-payoff arc**, but
**Sonnet 4.6 is fully viable and ~5× cheaper** — a defensible cost-optimized choice given how close they are.
**I am NOT picking unilaterally** — this is an owner taste/cost call like E2-a.

## 14. Latency / cost
24 calls, p50 7.3s, p95 10.1s. Tokens: Sonnet 33.3K total, Opus 32.8K (≈1.4K/plan). $/plan: Sonnet ≈ $0.009,
Opus ≈ $0.045. Per 100 Stories (ONE MusicPlan each, at Create-My-Story): Sonnet ≈ $0.90, Opus ≈ $4.50. Total
experiment spend ≈ **$0.9**. Well under the $20 gate.

## 15. Rejected fields / alternatives
- `key_moments[]` — dropped (redundant with energy_arc).
- Numeric energy scores — never introduced (categorical intensity only).
- One-section-per-Guide-dimension — explicitly avoided; no model did it.
- Absolute seconds / cut points / Moment ids / transitions — forbidden, none appeared.

## 16. Open questions (owner)
1. Model pick: Opus (consistency + edge) vs Sonnet (5× cheaper, equally gate-clean)?
2. MusicDirection input: confirm it reads CreativeIntent + StoryGuide.framing_summary (owner decision #2,
   already approved) — M-c will wire the cheap infer.
3. `track_selection_criteria` has no consumer until M-d — keep it in the frozen shape as the handoff, or
   add it at M-d? (Recommend keep: zero cost, natural seam.)

## 17. Is M-b ready to freeze? YES — with the owner model pick.
All freeze-gate conditions met: strong cross-domain behavior, short Stories get tiny plans (E/F = 1 region),
rich Stories richer (3), plans useful to a future Edit Planner, no generic cinematic arc dominates, native
audio handled correctly (B/D recede), no fake cut precision, no Moment/clip leakage, **Coverage input
decision evidenced (KEEP)**, **key_moments decision evidenced (DROP)**, contract minimized. The only open
input is the model pick (§13), reserved for the owner given the close margin. On your pick I freeze the
MusicPlan contract + prompt + model and STOP.


---

## 18. OWNER DECISION — M-b FROZEN & CLOSED (2026-10-07)

Everything above §18 is the experiment as run; it is preserved UNCHANGED. This section records the owner's
freeze decision and where the frozen artifacts live.

**Model (frozen):** `us.anthropic.claude-opus-4-6-v1`. Task-specific selection — chosen for slightly better
soundtrack *restraint* and native-audio payoff behavior (the guitar Arm-B arc ending on `intensity: falling`
so the real performance takes over), and for consistency with the Opus-backed Coverage/Guide stack. Sonnet
4.6 remains a valid future cost-optimized alternative (~5× cheaper, equally gate-clean). **No additional
model comparison or prompt tuning is authorized.**

**Frozen prompt:** `music_plan/1` — `prompts/music_plan/v1/system.md` (app repo). Frozen VERBATIM from the
validated experiment SYSTEM (`music_plan/exp-v1` in `evals/music_plan/run_experiment.py`); decoding
temperature 0, structured tool-use, 2 repair attempts. The body still *mentions* `key_moments` (as the
validated text did) but the frozen CONTRACT no longer exposes that field, so it cannot be emitted — the
contract is the enforcement point. Prompt text left unchanged to freeze exact validated behavior.

**Frozen contract:** `music_plan/1` — Pydantic `MusicPlanContract` in `contracts/schemas/ai_contracts.py`;
canonical JSON Schema generated to `contracts/schemas/music-plan.schema.json` via `contracts/generate_schema.py`
(registered in `AI_CONTRACTS`). A sync test (`test_music_plan_schema_dropped_key_moments_and_in_sync`) guards
against schema/model drift.

**Kept fields (each has a downstream consumer):**
- `schema_version`, `story_id`, `target_duration_seconds`, `provenance` — envelope / server-minted.
- `character { mood_tags[], energy }` — resolved MusicDirection snapshot (provenance + seeds track selection).
- `energy_arc[] { label, start_fraction, end_fraction, intensity(low|rising|high|falling), note? }` —
  scope-sensitive, approximate normalized regions, categorical intensity.
- `audio_strategy { soundtrack_role(continuous|supportive|sparse), native_audio_priority(low|selective|important), guidance? }`
  — first-class native audio.
- `track_selection_criteria? { mood_tags[], energy, structure_hint }` — optional handoff to the future track
  selector (M-d). Kept per §16.3: zero cost, natural seam.

**Dropped:** `key_moments[]` (ablated — redundant with `energy_arc` + `audio_strategy`). Also never present:
numeric energy scores, absolute seconds / cut points, Moment/clip ids, transitions, per-shot instructions,
one-section-per-Guide-dimension.

**Coverage/2 input — KEPT.** Ablation-evidenced: Arm B meaningfully improved plans (TMB → grit/resolve matching
the storm Coverage; guitar supportive→sparse once the real song take is known). Production MusicPlan consumes
`CreativeIntent + MusicDirection + StoryGuide + StoryCoverage/2 + target_duration`.

**MusicDirection ownership.** MusicDirection stays AUTHORITATIVE for mood/energy/progression and user musical
preferences. MusicPlan.character is a RESOLVED snapshot carried for provenance only — no competing source of
truth.

**Timing/recompute (unchanged).** Generated at / immediately before Create My Story. NOT recomputed
continuously during capture.

**Track sourcing — DEFERRED to M-d.** No provider, no catalog, no licensing assumption, no audio
infrastructure. `track_selection_criteria` is the only forward seam and selects nothing.

**Verification.** 149 contract + backend tests pass (incl. 8 new MusicPlan tests: round-trip, categorical
intensity, normalized fractions, optional track-selection, native-audio vocabularies, absence of key_moments,
no Moment/cut leakage, schema-sync). This freezes the CONTRACT; model-output quality was NOT re-verified
(no live inference rerun) — the §4–10 experiment results stand as the quality evidence.

**Deferred follow-up (NOT this task):** the Swift `MusicPlanDTO` in `apps/ios/.../Data/Contracts/StoryContracts.swift`
is consumer-side and belongs to M-c / Edit Planner wiring, so it is intentionally not added here.

**STATUS: M-b CLOSED.** M-c (MusicDirection infer + Figma MUSIC line), M-d (track sourcing), and the Edit
Planner have NOT started.
