# Milestone M-d — MusicAnalysis Freeze + Production Edit Planner + Epidemic Adapter: FINAL REPORT

**Status: Batches 1–4 COMPLETE. Deployment-READY (feature-flagged adapter OFF by default); NOT deployed.
STOP before Media Engine.** No rendering, no commercial export, no production music exposed to users, no vendor
contact, no license purchased, nothing pushed. 199 backend tests pass. Secrets handled via AWS Secrets Manager
(`story-epidemic-key`) in-process — never printed/logged/committed/embedded in iOS.

Commits by batch: **1** `b58b0b1` · **2** `ec04768` · **3** `641eb36` · **4** `edbcc62` (below). Specs report
commit `f2f5d9b`. Unrelated untracked `milestone-e2c-phase1-reconciliation.md` preserved throughout.

---

## 1. MusicAnalysis/1 — FROZEN
`contracts/schemas/ai_contracts.py`: `MusicAnalysisV1Contract` + `HighlightWindow`. Fields:
`{ schema_version="music_analysis/1", duration_seconds (req, >0), bpm (nullable), tempo_reliable (bool),
beats[] (s), downbeats[]? (s), highlight_window?{start,end s}, energy_curve[]? (0..1 coarse), vocal_type? }`.
**Excluded** (as directed): labelled sections, time-ranged vocal_regions, numeric emotional intensity, fabricated
boundaries. Additive — the pre-existing `MusicAnalysisContract` (used by `MusicAssetContract.analysis`) is
untouched for consumer compatibility.

## 2. Schema generation
`contracts/schemas/music-analysis-v1.schema.json` generated via the registered generator; a drift-guard test
asserts the committed schema matches the Pydantic model and has no `sections`/`vocal_regions`.

## 3. Normalization rules (validated by contract tests + live data)
- **BPM:** `<=0 → null`; `tempo_reliable=true` only when bpm present AND in the 40–220 plausibility band. **A
  beat grid alone does NOT make a track beat-synchronizable** — the Epidemic ambient track returned bpm=0 and is
  correctly flagged non-reliable.
- **Beats/downbeats:** real seconds; downbeats = provider `value==1`; nonnegative, chronological, deduped,
  clamped to duration.
- **Highlights:** provider **milliseconds → seconds**; bounded to duration; candidate region, not a guaranteed
  climax.
- **Energy curve:** coarse **0..1 normalized amplitude envelope** from waveform JSON (bounded resolution, 16
  samples). Documented as **signal amplitude, not perceived emotion**.
- **Vocal type:** provider category preserved (NONE/PRESENCE/LEAD); no time-ranged detection.

## 4. Edit Planner engine
`packages/edit_planner/` — `RealEditPlannerEngine` (Opus 4.6 via the generic ModelGateway, frozen prompt
`prompts/edit_plan/2/system.md` registered verbatim from the validated `edit_plan/exp-v3` — no retuning) +
`MockEditPlannerEngine`. Owns segment selection, narrative ordering, source in/out, output duration, narrative
roles, optional music alignment, native-audio intent; server mints UUIDs onto the canonical `EditPlanV2Contract`.
Does NOT decode/render/mix/select-provider/fabricate. Music inputs are OPTIONAL (no-music planning supported).

## 5. Edit Planner API
`POST /v1/edit-plan` (existing auth/observability conventions, no new infra). Inputs: Story + Guide + Coverage +
MomentUnderstanding[] + MusicPlan + optional MusicAsset/MusicAnalysis. **200** → EditPlanV2; **503** → model/
validation failure (never fabricate; client keeps Story+Moments, retry); **422** → infeasible material + reason.

## 6. Deterministic validator (production hard gate)
Ported into `edit_planner.validate_plan`: Moment exists; source range valid + within duration + overlapping a
useful_segment; positive output; **source/output/speed physical consistency**; **transition feasibility**;
monotonic unique order; total within ±20% (skipped when feasible=false, which is the short best-effort plan);
no music_alignment anchor without MusicAnalysis; native_audio present; infeasible⇒reason. **The model never
self-certifies; an invalid plan never reaches the Media Engine** (raises → 503).

## 7. Regression results
Full backend suite **199 passed** (was 156 at M-c): +5 music_analysis/1 + 6 edit_plan/2 + 11 edit-planner engine/
endpoint + 13 music_provider + 1 testpaths widening. No regression in Creative Intent / Scene / Director / AU /
Coverage / Guide. Runtime engines for those milestones untouched.

## 8. Epidemic adapter
`packages/music_provider/` — `EpidemicClient` (search, metadata, preview HLS, beats, highlights, waveform, vocal,
download-link) using the **live-verified** response shapes; `to_music_analysis_v1` normalizer; `rank_candidates`
deterministic matcher. Key read from Secrets Manager in-process; robust to dict-shaped `moods`, missing
highlights, bpm=0, expiring URLs, auth(401/403)/rate-limit(429)/http errors.

## 9. Feature-flag safety
ALL Epidemic functionality is gated on `STORY_EPIDEMIC_MODE=prototyping`. Off by default → `EpidemicClient`
construction raises `EpidemicDisabledError`, and `POST /v1/music/candidates` returns **404** (invisible in normal
production — verified). **No sublicense/safelist/export path exists in code.** Key never in iOS.

## 10. Matching algorithm
Deterministic weighted score (NO extra LLM, embeddings, or vector DB): `0.5·mood_overlap + 0.3·vocal_compat +
0.2·duration_adequacy`. Vocal penalty rises when `audio_strategy.native_audio_priority` is important/selective
(prefer instrumental). **Does NOT prefer highest-BPM or "most dramatic"** (unit-tested: a loud 174-BPM epic loses
to a calm instrumental when the plan is calm). Returns ranked candidates with explainable per-factor scores.

## 11. Real API compatibility (Batch 4, prototyping)
Ran `evals/edit_planner/integration_md4.py` with real Epidemic metadata (ONE track/scenario, **no downloads**, no
persisted audio/metadata): search → rank → metadata/beats/highlights/waveform → normalize `music_analysis/1`. All
5 scenarios produced a usable MusicAnalysis; tempo'd tracks had reliable bpm + hundreds of beats + a highlight;
the **ambient pick returned bpm=0 → tempo_reliable=false** (handled correctly).

## 12. Integration scenario results — pipeline proven end to end
`MusicPlan → Epidemic search → deterministic rank → selected track → MusicAnalysis/1 → Edit Planner (Opus) →
EditPlan/2`, all 5 scenarios, **plans executable + re-validated clean**:
| scenario | track (real) | tempo_reliable | segs | out | anchors | native_audio |
|---|---|---|---|---|---|---|
| TMB | Venturing through Time | true | 8 | 60.0s | downbeat×3 | duck/mute mix |
| guitar | Light over Bad Lands | true | 3 | 41.0s | downbeat, highlight | duck,duck,**keep** |
| SF | Butterfly (Instrumental) | true | 8 | 45.0s | downbeat×3, highlight | mixed, 2×keep |
| solitude | Path | **false** | 3 | 17.5s | **all none** | **keep,keep,keep** |
| energetic | Bankteller | true | 3 | 12.0s | downbeat×2 | duck,**keep**,mute |
**Verified:** narrative ordering coherent; correct Moment/useful-segment selection; durations on target; music
alignment serves narrative; **native audio preserved** (guitar/skate keep); **no forced beats on ambient**
(solitude 0 anchors, driven by the real bpm=0 → tempo_reliable=false); no invented footage; deterministic
executability. **Rendered-video quality is NOT claimed** (no Media Engine).

## 13. Latency / cost
Edit Planner (Opus 4.6) p50 ~8–12s/plan. Integration run: 5 real Opus plans + ~20 Epidemic metadata calls + 0
downloads ≈ **well under $1**. Batches 1–3 experiments ≈ $0 (contract/tests) to ~$0.38. No infra cost.

## 14. Commits by batch
1 `b58b0b1` (music_analysis/1 freeze) · 2 `ec04768` (Edit Planner engine + /v1/edit-plan) · 3 `641eb36`
(Epidemic adapter + matcher + /v1/music/candidates) · 4 `edbcc62` (integration harness). Specs `f2f5d9b`.

## 15. Deployment status — READY, NOT DEPLOYED
Full suite green; app imports clean; `/v1/edit-plan` + `/v1/music/candidates` registered; the music adapter is
**OFF by default** (`/v1/music/candidates` → 404 without the flag). A safe backend deploy with the adapter
disabled is possible under existing policy (throwaway CodeBuild → ECR → App Runner, as prior milestones). Per the
stop gate + "do not auto-push", **I did NOT deploy** — `/v1/edit-plan` can be exercised on device only after a
redeploy you authorize. Free-tier music is NOT enabled for production users anywhere.

## 16. Unresolved production licensing requirements
Free tier = prototyping only (≤50 downloads, no sublicense/safelist/go-live). Production needs a paid **Scale/
Enterprise** tier (pricing UNKNOWN, no inquiry sent). Written confirmation still needed for: derived-analysis
caching vs. the no-cache policy; audio retention during/after render; commercial end-user sync scope; termination
survival. The M-d.2 draft inquiry remains on file.

## 17. Remaining iOS Music UX work (NOT started)
The frozen Figma track surfaces (`ScreenTMBMusic` suggested track + preview, `MusicPick` Change, Result "Change
music") are still disabled. Future flow: MusicDirection → suggested Epidemic track (from `/v1/music/candidates`) →
HLS preview → optional change → Create My Story. No music picker UI built (not approved this milestone).

## 18. Recommended next Media Engine milestone
Separate milestone: decode → cut/transition/crop/speed → **audio mix** (realize per-segment native_audio keep/
duck/mute + soundtrack ducking from MusicPlan.audio_strategy; snap cuts to MusicAnalysis times a segment's
`music_alignment.anchor` names) → render → export → on export: Epidemic usage-report + safelisting (needs the
paid tier). Consumes frozen `edit_plan/2` + `music_analysis/1`. No LLM.

## 19. Owner acceptance checklist
1. `music_analysis/1` frozen with the agreed field set (no sections/vocal_regions). ✅
2. `/v1/edit-plan` returns an executable EditPlan/2 for the 5 scenarios; 503 on failure, 422 on infeasible. ✅
3. Deterministic validator rejects invalid plans; model never self-certifies. ✅ (unit + integration)
4. Native audio preserved; no forced beats on ambient (real ambient track, bpm=0). ✅
5. Matcher is deterministic, explainable, not BPM-greedy. ✅
6. Epidemic adapter is PROTOTYPING_ONLY; `/v1/music/candidates` is 404 by default. ✅
7. Key only in Secrets Manager, never in code/logs/iOS. ✅
8. 199 backend tests pass; frozen prior milestones untouched. ✅
9. Nothing deployed/pushed; no license/vendor/export. ✅
Owner decisions to proceed: authorize a safe backend deploy (adapter off) to exercise `/v1/edit-plan` on device;
approve the iOS Music UX milestone; approve the Media Engine milestone; send the M-d.2 inquiry for production
Epidemic terms.

**STOP. No Media Engine, no rendering, no commercial Epidemic plan, no production exports, nothing pushed.**
