# Milestone M-d.3 — API Validation + Edit Planner Experiment: REPORT

**Status: RESEARCH / EXPERIMENT ONLY — STOP for owner review.** No production Music/Edit-Planner/Media-Engine
built, no Epidemic plan selected or purchased, no vendor contacted, no account created, no infra added, nothing
pushed. Per owner M-d.3 decisions: no vendor inquiry; public plans + Partner-API FAQ are the licensing basis;
Epidemic preferred, Story-owned catalog fallback; free-API technical validation + Edit Planner experiment only.

Spend this milestone: **~$0.38** (10 Opus text calls; measured, under the $20 gate). Epidemic facts quoted from
official pages read 2026-10-07.

---

## 1. Epidemic official-source reconciliation (`/our-plans/`, `/docs/faq/`, `/docs/`)

Reconciled with M-d.1/M-d.2. Documented capabilities RECORDED (as the owner directed), kept distinct from
unverified terms:

- **Partner API supports music discovery + in-product use.** FAQ: users "discover, preview, and use music… directly
  inside your product," with AI tools to find/adapt/soundtrack. (confirms M-d.2 §1 search/preview/download)
- **Partner users do NOT need individual Epidemic accounts.** FAQ: "No. Your users do not need their own Epidemic
  Sound account… The partner holds the access." (resolves M-d.1's open "ES-subscriber-via-Connect?" doubt for the
  *partner-held* model — the partnership holds access, not each user.)
- **Commercial publishing is supported.** FAQ: "Epidemic Sound is built to give platforms and their users a safe,
  ready-to-publish music experience… without having to figure out rights, reporting, or separate clearances."
- **Generative-video + AI soundtracking are supported.** FAQ: "Many partners use Epidemic Sound as part of
  generative video workflows… automatically creating a soundtrack from a text/video prompt, then fitting the
  music to the pacing, feel, and structure of the video." (directly describes Story's MusicPlan→track→edit flow)
- **A creator Pro subscription ≠ Partner-API production licensing.** `/our-plans/`: the **Pro** plan gives a
  freelancer/business "full sublicensing rights" but is **per-subscriber, up to 3 channels/platform, with turnover
  caps** (contact Enterprise above USD 5M publisher / USD 10M corporation). That is the *creator* license, NOT the
  *Partner-API* production tier (Scale/Enterprise from the M-d.2 blog). **Do not conflate them.**

**Still UNKNOWN (not claimed):** exact Partner-API production pricing, per-MAU/per-export/rev-share basis,
derived-analysis caching permission, audio-retention-at-rest window, termination survival specifics. These remain
owner/legal items — and per this milestone's decision, **no inquiry was sent.** The M-d.2 draft inquiry stays on
file for when the owner chooses to send it.

---

## 2. Free API validation — CREDENTIAL-BLOCKED (live test not run)

**No `EPIDEMIC_*` credential is configured in this environment** (checked env + backend config; none present), and
I did not create an account or accept terms. So the **live API test was NOT run** — I will not assert endpoint
behavior I did not observe.

**Exact setup for the owner to unblock it (self-serve, free, no credit card — per M-d.2 §1):**
1. Go to **https://developers.epidemicsound.com/** → "Get free API key" → fill details → key issued instantly
   (`epidemic_live_…`).
2. Put the key in **existing AWS Secrets Manager** (same convention as the Bedrock path), exposed to the backend
   as e.g. `EPIDEMIC_API_KEY`. **Never paste it in chat; never commit it.**
3. Re-run the ready experiment harness (below), which reads the key from env and runs the bounded test.

**The bounded test is written and ready** (`evals/edit_planner/` has the plan-side; a thin Epidemic probe would
call `/v0/tracks/search`, `/metadata`, `/stream`(HLS), `/beats`, `/highlights`, `waveformUrl`, vocal fields on
3–5 tracks, ≤5 downloads). It validates documented behavior against reality and fills the "live-confirm" column of
§3. **Blocked only on the key; everything else proceeded.** Free-tier guardrails honored by design: no catalog/
metadata mirror, downloads ≤50 (we'd use ≤5), prototyping-only, nothing shipped.

---

## 3. Available MusicAnalysis fields (documented; live-confirm pending the key)

Unchanged from M-d.2 §2, restated as the design basis the §6 experiment used (CONTROLLED analysis, not a real
track):

| Field | Source | Status |
|---|---|---|
| duration, bpm, beats, **downbeats** (`beats.value==1`), highlight window, vocal class | Epidemic provider (documented) | to live-confirm |
| energy_curve (coarse) | derived from waveform JSON (no DSP, no download) | to live-confirm |
| time-ranged vocal_regions | our own analysis (separation/VAD) | only if sub-track ducking needed (deferred) |
| sections (labelled intro/build/peak/outro) | partial: `highlights`+waveform; full labels = our analysis | the §6 experiment used synthetic sections to test whether the planner even uses them |

---

## 4. Updated Edit Planner design

`spec/implementation-plan/09-edit-planner.md` was rewritten E2-aware this milestone (banner-superseded old body
preserved for history). Summary:
- **Inputs (current):** CreativeIntent, StoryGuide/1, StoryCoverage/2, MomentUnderstanding[] (observed +
  `useful_segments`, NOT old `AssetUnderstanding`/`usable_ranges`), MusicDirection, MusicPlan/1, MusicAsset,
  MusicAnalysis.
- **Edit Planner OWNS:** choose useful Moment segments (from `useful_segments`); narrative progression grounded in
  Guide/Coverage (anti-template); segment ordering; source in/out; target output duration (±20%); musical
  alignment to real MusicAnalysis **within** MusicPlan intent; **per-segment native-audio preservation INTENT**.
- **Media Engine OWNS:** decode, cut, transitions, **actual audio mixing** (ducking/fades), render, export.
- **Hard boundary preserved** (the one valid decision from the old spec): AI/engine PLANS, Media Engine EXECUTES;
  never ask an LLM to "edit the video"; no sample-level mix curves from the model.

---

## 5. Proposed EditPlan/2 contract (experimental — NOT frozen)

Full proposal in `milestone-md3-editplan2-contract.md`. Shape validated by the experiment:
```
EditPlanContract (edit_plan/2) =
  id, story_id (ADD), creative_intent_id, target_duration_seconds, output_format,
  music_asset_id?, music_plan_id? (ADD), music_analysis_ref? (ADD),
  segments[]: order, asset_id(=Moment id), source_start_seconds?, source_end_seconds?,
              output_duration_seconds, crop?, speed?, transition?{type,duration_seconds?},
              narrative_role?, native_audio{keep|duck|mute} (ADD),
              music_alignment?{anchor: beat|downbeat|highlight|none, note?} (ADD, SEGMENT-LEVEL)
```

### Fields to KEEP / ADD / DROP (deliverable 14)
- **KEEP** (frozen EditPlanContract): id, creative_intent_id, target_duration_seconds, output_format,
  music_asset_id, segments{order, asset_id, source_start/end, output_duration, crop, speed, transition,
  narrative_role}. All exercised and useful.
- **ADD:** `story_id` (the plan belongs to a Story, not just an intent); `music_plan_id` + `music_analysis_ref`
  (provenance + the structure the plan aligned to); **`native_audio` per segment** (load-bearing — the planner used
  it correctly to protect the guitar performance / skate landing / solitude room tone); **`music_alignment` per
  segment** (see §6).
- **DROP / do NOT add:** a **global `beat_sync` boolean** (see §6 — it would be redundant and lossy); per-segment
  mix curves (Media Engine); explicit payoff marker (the `highlight` anchor already carries it); multi-track audio
  (downstream).

---

## 6. Beat-alignment representation — RECOMMENDATION: **segment-level `music_alignment.anchor`, default `none`**

**Evaluated the four options the owner listed, against the experiment:**
- **Global edit-level bool (`beat_sync`)** — REJECTED. The experiment shows alignment is **per-segment and
  heterogeneous**: in TMB Arm B, five cuts anchored `downbeat` and one segment anchored `highlight`; a single bool
  cannot express "this cut lands on a downbeat, that one on the highlight, the rest free." It is also redundant
  with the per-segment anchor and invites the "more cuts on beats = better" fallacy.
- **Transition-boundary** — the anchor conceptually lives at a segment's start cut, so representing it ON the
  segment (its leading boundary) is equivalent and simpler than a separate transition object. Folded into the
  segment.
- **Derived by Media Engine from cut times** — insufficient ALONE: the Media Engine can detect that a cut happens
  to fall near a beat, but it cannot know the planner's INTENT ("this payoff is meant to land on the highlight").
  Intent must be explicit; the Engine then realizes it precisely.
- **► Segment-level `music_alignment{anchor, note?}` with `anchor` default `none`** — CHOSEN. Expresses intent
  exactly where it applies, stays absent/`none` when alignment is irrelevant (minimal/ambient), and the Media
  Engine does the exact snapping. Every anchor names a consumer (the Engine's cut placement). **No redundant
  global state.**

**And the key finding behind the warning:** real structure **helped where there is an arc** (TMB payoff on the
`highlight`, skate landing anchored, guitar performance on the `highlight`), but on **minimal_solitude Arm B** the
planner anchored two held stillness shots to `downbeat` on a 60-bpm ambient pad and even flipped one segment from
`keep`→`duck` — **spurious alignment that serves no narrative.** This confirms the owner's rule: *music sync must
serve the narrative, not the reverse.* The design response: anchors default `none`, and the planner prompt
explicitly says alignment is optional and narrative-first (already in the experiment prompt; carry into production).

---

## 7. Fixture inventory

`evals/edit_planner/fixtures.json` — 5 scenarios (`build_fixtures.py` regenerates):
1. **tmb_cinematic_60s** — 3 Moments, **REAL MomentUnderstanding** (backpack/departure from
   `story_coverage/real_moment_understanding.json`), target 60s.
2. **guitar_progression** — 3 Moments incl. a 34s real-performance Moment (native audio = payoff), target 40s.
3. **sf_exploration** — 4 Moments (cable car / fog / food / street), vignette, target 45s.
4. **minimal_solitude** — 2 held calm Moments, target 18s (anti-template test).
5. **energetic_shortform** — 2 Moments (roll-up + trick), target 12s (one-burst test).
Each carries CreativeIntent + StoryGuide + StoryCoverage + MusicPlan/1 + a **CONTROLLED** MusicAnalysis
(synthetic beats/downbeats/highlight/sections — NOT a real track, clearly labelled in `_meta`).

---

## 8. Human-review criteria (frozen BEFORE model output)

Defined in this report before running (the harness run came after). For each scenario a human judges, pass/discuss:
narrative coherence; correct Moment selection (nothing load-bearing dropped); useful-segment selection (cuts land
in meaningful ranges); temporal ordering; duration feasibility (±20%); pacing vs. energy_arc; music-structure
alignment (payoff near real highlight where it helps); **native-audio preservation** (guitar/birthday/skate keep
their own audio); non-redundancy; **anti-template** (reflects THIS Story, not a stock montage); executable-contract
validity. **Not scored by resemblance to one human timeline — multiple valid edits exist.**

---

## 9. Opus planning results (model `us.anthropic.claude-opus-4-6-v1`, temp 0)

10/10 plans generated; **10/10 passed deterministic validation.** Latency p50 ~11s (range 4.9–21.7s).
| Scenario | Arm | segs | out | native_audio | anchors |
|---|---|---|---|---|---|
| tmb_cinematic_60s | A | 8 | 58.0s | duck×6, mute×2 | all none |
| tmb_cinematic_60s | B | 8 | 60.0s | duck×5, mute×3 | downbeat×6, highlight, none |
| guitar_progression | A | 3 | 39.0s | duck, duck, **keep** | none |
| guitar_progression | B | 4 | **48.0s** | duck, duck, keep, keep | downbeat×2, **highlight**, none |
| sf_exploration | A | 7 | 44.0s | mixed | none |
| sf_exploration | B | 6 | 45.0s | mixed | mixed |
| minimal_solitude | A | 2 | 18.0s | **keep, keep** | none |
| minimal_solitude | B | 2 | 18.0s | keep, **duck** | **downbeat, downbeat** |
| energetic_shortform | A | 3 | 12.0s | duck, duck, **keep** | none |
| energetic_shortform | B | 3 | 12.0s | duck, **keep**, mute | downbeat, downbeat, **highlight** |

Qualitatively (human read of the plans): narrative ordering is coherent and grounded (TMB = pack→prep→threshold→
walk→landscape→final; guitar = grind→cleaner→full performance; solitude = two held shots, no manufactured arc —
anti-template HELD). Moment/segment selection is sensible and stays inside `useful_segments`.

---

## 10. MusicPlan-only (A) vs MusicPlan+MusicAnalysis (B) — does real structure help?

**Yes, where the Story has an arc; and it can HURT a minimal Story if applied blindly.**
- **Helps:** TMB-B put the landscape reveal on the real `highlight` and major cuts on `downbeat`; guitar-B
  anchored the performance to the `highlight`; skate-B anchored the landing/replay to `downbeat`/`highlight`.
  These are exactly the payoff/major-cut/ending improvements the task asked about — alignment that **serves** the
  narrative beat.
- **Neutral/risky:** sf-B barely changed (a vignette has no single payoff — correct). **minimal_solitude-B
  over-aligned** (downbeat anchors on 60-bpm stillness; one keep→duck flip) — a real instance of "more beats ≠
  better." **Duration inflation:** guitar-B grew to 48s (edge of +20%) by splitting the performance to fill
  structure — a mild tendency to pad to the track rather than to the Story.
- **Verdict:** MusicAnalysis is **worth carrying** (payoff/major-cut placement genuinely improve), but the planner
  must treat alignment as **optional and narrative-first** (anchor default `none`), and duration must stay pinned
  to the Story's target, not the track's length. Both are design constraints, not reasons to drop the field.

---

## 11. Native-audio findings

**First-class and correct across the board** — the single most load-bearing new field:
- Guitar **performance = `keep`** in BOTH arms (the real payoff survives; music recedes) — the M-b native-audio
  promise realized.
- Skate **landing = `keep`** (board clack punches through); solitude room tone = `keep` (A).
- Prep/transition footage = `duck`/`mute`; nothing important is drowned.
- One nit: solitude-B flipped a `keep`→`duck` under beat-alignment pressure — reinforces that alignment must not
  override native-audio priority. The prompt already orders native-audio above alignment; keep that ordering in
  production.
`native_audio{keep|duck|mute}` per segment is **confirmed necessary and sufficient** for MVP (exact ducking/fade
curves are Media-Engine, driven by this intent).

---

## 12. Deterministic executability results

A standalone validator (NOT model self-certification) checks: all asset_ids exist as Moments; source in/out within
Moment duration AND overlapping a `useful_segment`; positive output durations; monotonic unique ordering; total
within ±20% of target; `native_audio` present; alignment anchors only set when MusicAnalysis is present. **All 10
generated plans passed.** The validator has an **8/8 self-test** (`test_validator.py`) exercising invented-Moment,
out-of-bounds, outside-useful, duration-off, bad-order, missing-native-audio, and anchor-without-analysis. This is
the production executability gate (model NEVER self-certifies).

---

## 13. Model validity / latency / cost

- **Validity:** 10/10 schema-valid + 10/10 deterministically executable, 0 repairs observed.
- **Latency:** p50 ~11s, max 21.7s (TMB-B, 8 segments). Acceptable for a Create-My-Story-time call; a pre-beta
  latency item like Director.
- **Cost:** **~$0.38 total** for 10 calls (Opus 4.6, text-only ~2.5k in / ~1k out each). Per-plan ~$0.04.
- **Model:** reused the existing `us.anthropic.claude-opus-4-6-v1` via the generic ModelGateway. **No bake-off;
  no frozen Director/Guide/Coverage/AU/MusicPlan prompt touched** — only the experimental `edit_plan/exp-v2`
  prompt.

---

## 14. Contract fields to keep/drop
See §5. KEEP all current EditPlanContract fields; ADD story_id, music_plan_id, music_analysis_ref, per-segment
native_audio, per-segment music_alignment; DROP/avoid a global beat_sync bool, model-authored mix curves, explicit
payoff marker, multi-track audio.

---

## 15. Is EditPlan/2 ready to freeze? — **ALMOST; freeze after ONE small confirmation**

The shape held across 5 diverse scenarios with 100% executable validity and correct native-audio behavior, so the
**structure is sound**. Two items to resolve BEFORE freezing (both small, both design — not model):
1. **Duration discipline:** add an explicit prompt + validator rule that total output tracks the **Story target**,
   not the track length (guitar-B drifted to the +20% edge). Trivial.
2. **Alignment restraint:** confirm (with the owner, or a 1-line prompt tweak like MusicPlan's restraint clause)
   that anchors stay `none` unless they serve a beat — the solitude-B over-alignment is the only quality miss.
Recommend: apply those two tweaks, re-run the 5 scenarios once (~$0.38), then **freeze `edit_plan/2`.** Not frozen
unilaterally — owner approves the two tweaks.

---

## 16. Recommended next milestone / sequence
1. **(owner, unblocks live confirm)** sign up for the free Epidemic key → run the ready §2 probe → fill the
   live-confirm column (does `/beats`/`/highlights`/`waveform` behave as documented?).
2. **(design, parallel)** apply the §15 duration + restraint tweaks → re-run → **freeze EditPlan/2.**
3. **(implementation, AFTER freeze + owner go)** build the Edit Planner engine against frozen `edit_plan/2`
   (generic ModelGateway, Opus 4.6, prompt `edit_plan/1`, the deterministic validator as the hard gate, 503 on
   failure — never fabricate), + `/v1/edit-plan` endpoint. Still NO rendering.
4. **(separate later milestone)** Media Engine — decode/cut/transition/**mix**/render/export + Epidemic
   download-for-render + usage-report + safelisting (needs the production tier).
5. Track sourcing (real MusicAsset + real MusicAnalysis) rides on the Epidemic go-live decision (M-d.1/.2).

**Blockers requiring owner action:** (i) free Epidemic key to run the live API confirm (self-serve, $0);
(ii) approve the §15 EditPlan/2 tweaks → freeze; (iii) when ready, send the M-d.2 inquiry for production pricing/
terms. All independent; design continues meanwhile.

**STOP for owner review. No production Edit Planner/Media Engine, no Epidemic plan selected/purchased, no vendor
contacted, no infra, nothing pushed.**
