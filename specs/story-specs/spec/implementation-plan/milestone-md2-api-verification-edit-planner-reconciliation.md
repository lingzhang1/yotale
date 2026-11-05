# Milestone M-d.2 — Epidemic API Access Verification + Edit Planner Reconciliation

**Status: RESEARCH / RECONCILIATION ONLY — STOP for owner review.** No account created, no legal terms
accepted, no credentials generated, no vendor contacted, no production Music/Edit-Planner/Media-Engine built,
nothing pushed automatically. Epidemic facts quoted from official pages read 2026-10-07 (business/developers,
tools/api, blog/free-api dated 2026-06-25, developer docs). The inquiry email in §3 is a DRAFT for owner review.

---

## Part 1 — Free-tier contradiction RESOLVED (supersedes M-d.1 §1)

**M-d.1 was wrong on this point and is corrected here.** The marketing pages
(`epidemicsound.com/business/developers`, `/tools/api/`) and the dated blog post `/blog/free-api/`
(**2026-06-25**) are the current, authoritative word; the developer-docs "partnership agreement required" line
describes **production/go-live** access, NOT prototyping. They reconcile cleanly as **two tiers**:

| Question | Verified answer (source) |
|---|---|
| Is self-service API signup available? | **YES.** "Self-serve sign-up, API key issued instantly… No contract, no credit card, and no waiting on a sales rep." (tools/api; blog) |
| Free tier available to new developers? | **YES.** "Head to Epidemic Sound for Developers, click 'Get free API key,' and fill in your details… instantly generate your API key." (blog) |
| Is the developer documentation outdated? | **No — it describes PRODUCTION access.** The docs' "you need a partnership agreement" is the go-live gate (safelisting, sublicensing, content tiers). The Free tier is a separate prototyping lane the docs under-describe. Both true. |
| Free tier includes real track search? | **YES.** "Full catalog access for prototyping and evaluation" — 55,000+ tracks, 250,000 SFX. (blog, tools/api) |
| Preview + download for experimentation? | **YES, bounded.** Full catalog for prototyping; **Free tier provides 50 downloads total** ("you won't lose access when you hit this limit, but you'll need to upgrade"). Preview (HLS) is not download-capped per the docs. (blog) |
| beats / highlights / waveform endpoints accessible? | **NOT STATED for Free tier specifically.** The docs describe them for API-Key auth generally; the Free tier issues an API key with "full catalog access." **Likely accessible but UNCONFIRMED → must be verified by a live call (§2), not asserted.** |
| Rate limits? | **Free tier: 50 downloads total** is the only published hard cap. The docs mention per-user weekly rate limits on audio delivery (numbers not public). Other Free-tier limits ("clear limits") not enumerated publicly. |
| Restrictions on experimental audio? | **Prototyping/evaluation ONLY. "You can't sublicense or go live… the music and sound effects are only licensed for paid tiers."** No safelisting, no sublicensing, no shipping to real users on Free. (blog) |
| Does production export still require a commercial agreement? | **YES.** Go-live needs a paid tier — **Scale** (startups/small businesses, needs-based pricing) or **Enterprise** (bespoke). "You can't safelist, sublicense, or go live with the Free tier." Prototyping carries over — "nothing to rebuild once you upgrade." (blog) |

**Experimental vs. production, cleanly separated:**
- **EXPERIMENTAL (Free tier):** instant self-serve key, full catalog, **≤50 downloads**, preview + metadata +
  (likely) beats/highlights/waveform, **for prototyping/evaluation only — may NOT ship to users or sublicense.**
  Enough to answer every technical question in §2 and to validate the MusicAnalysis-field mapping.
- **PRODUCTION (paid Scale/Enterprise):** required for real users, sublicensing, safelisting, export clearance,
  usage reporting at scale. **Pricing still UNKNOWN** (needs-based; the §3 inquiry asks for it).

**Signup path (owner action — do NOT create the account automatically):**
1. Go to **https://developers.epidemicsound.com/** → click **"Get free API key."**
2. Fill in developer/organization details; **no credit card.** An API key (`epidemic_live_…`) is issued instantly.
3. Hand the key to Story's backend **only** — store in **existing AWS Secrets Manager**, never in iOS, never
   committed to git.
> I did NOT sign up or accept any terms. Account creation + accepting the Free-tier terms is the owner's to do.

---

## Part 2 — Conditional API experiment (BLOCKED pending owner-provided key)

**No credentials are available in this session, and I will not create an account.** So the live experiment is
**not run this turn.** When the owner provides a Free-tier `epidemic_live_…` key (via Secrets Manager, never
pasted into chat/git), the bounded experiment is ready to run. Spec:

**Tracks:** ~3–5 diverse, spanning the frozen MusicDirection/MusicPlan space — e.g. warm acoustic (guitar),
cinematic gradual build (TMB), energetic short-form, sparse ambient, vocal-heavy — chosen via `/v0/tracks/search`.

**Calls to make (and the MusicAnalysis field each resolves):**
| Call | Field validated | Expectation to confirm (not assert) |
|---|---|---|
| `GET /v0/tracks/search?term=…&vocalType=…&bpmMin/Max` | query feasibility | semantic + filter search returns candidates |
| `GET /v0/tracks/metadata?trackId=…` | `duration` (`length`), `bpm`, `hasVocals`, `vocalType` | present, non-null |
| `GET /v0/tracks/{id}/stream` (HLS) | preview | `.m3u8` plays on iOS AVFoundation |
| `GET /v0/tracks/{id}/beats` | `beats[]` + **downbeats** (`value==1`) | per-beat time + bar position present |
| `GET /v0/tracks/{id}/highlights` | `highlight_window` | from/to ms for the key section |
| `GET …/waveformUrl` JSON | `energy_curve` (derived) | amplitude envelope downsamples to coarse energy |
| vocal class (`vocalType`/`hasVocals`/`lyrics`) | `vocal_type` | track-level vocal classification |
| `download` (counts against the **50** cap) | asset retrieval | MP3 link + expiry; use SPARINGLY in the experiment |

**Compliance guards during the experiment (do not violate the terms even in prototyping):**
- **Do NOT persist copyrighted source audio** beyond the transient test, and **do NOT build a local mirror of
  Epidemic catalog/track metadata** (the no-cache policy). Store only our own derived numbers for the writeup.
- Treat **downloads as scarce (≤50)** — prefer metadata/beats/highlights/waveform (which likely don't consume
  the download budget) and download only the 3–5 chosen tracks once.
- The result is an **evaluation artifact**, never shipped — Free tier forbids go-live.

**If access stays unavailable:** this is a **soft blocker only for the live confirmation**; design proceeds on
the documented capabilities (M-d.1 §1 + this doc). The field-mapping in M-d.1 §2 stands as the design
hypothesis to be confirmed by the experiment, not blocked by its absence.

---

## Part 3 — Commercial inquiry (DRAFT for owner — NOT sent)

> **DO NOT SEND automatically.** This is a draft for the owner to review, edit, and send from their own address.
> No vendor has been contacted. Send target: Epidemic Sound partnerships (via the "Contact sales"/Scale upgrade
> path at `developers.epidemicsound.com` or `epidemicsound.com/business/developers`).

**Subject:** API partnership inquiry — Story (early-stage AI iPhone video storytelling app)

Hi Epidemic Sound team,

We're evaluating the Epidemic Sound API for **Story**, an early-stage, AI-powered iPhone app for personal video
storytelling. Story helps a user capture Moments, analyzes their footage, generates a musical plan for the piece,
matches it to a real track, assembles an edited video, and lets the user export and share it to social platforms.
We've prototyped against the Free tier and want to understand the path to production.

Could you clarify the following for a startup-stage integration?

1. **Startup / early-stage pricing** — what the **Scale** tier looks like for a pre-revenue early-stage app.
2. **Pricing basis** — is it MAU, per-export, revenue share, or a minimum commitment? Which applies at low volume?
3. **End-user sync rights** — the personal vs. commercial end-user synchronization license for music embedded in
   a user's exported video, and what distinguishes them.
4. **End-user accounts** — do our users need individual Epidemic Sound subscriptions, or does our partnership
   cover them (and if so, under which tier)?
5. **Worldwide export + monetization** — are exports cleared worldwide across YouTube / TikTok / Instagram, and is
   user monetization covered?
6. **Rights after termination** — if our partnership ends, do already-exported user videos remain cleared?
7. **Temporary audio storage** — may we download a track transiently to render a user's video on our backend, then
   discard the source audio?
8. **Derived MusicAnalysis caching** — your docs state partners may not cache collections or track metadata. May we
   persist our **own derived analysis** (beat/section/energy timings tied to a track ID) to avoid recomputation,
   and if not, what's permitted?
9. **Safelisting & reporting** — how safelisting and usage reporting work for a mobile app whose users export to
   multiple platforms, and what's enabled at the Scale tier.
10. **Production API access & catalog tiers** — Curated Collections vs. Full Catalogue at Scale, and any
    rate limits we should design around.

We're happy to share more about our architecture and expected volumes. Thanks very much.

[Owner name], Story

---

## Part 4 — Edit Planner reconciliation

### 4.1 Current state and stale assumptions

Two artifacts exist and **disagree with each other and with the frozen contract set**:

**(a) `spec/implementation-plan/09-edit-planner.md`** — badly **pre-E2 / pre-M-b / pre-M-c STALE**:
- Consumes `CreativeIntent` + `AssetUnderstanding[]` with `usable_ranges` and a `StoryPlan`. **AssetUnderstanding
  was superseded by `MomentUnderstanding` in Milestone D** (observed/story_context split; `useful_segments`, not
  `usable_ranges`).
- No knowledge of **StoryGuide/1, StoryCoverage/2, MusicDirection, MusicPlan/1, MusicAsset, MusicAnalysis** — all
  frozen since. Music is a bare `music_track_id` + `beat_sync` bool; there is no MusicPlan intent, no MusicAnalysis
  structure, and **no native-audio handling at all** (contradicts the M-b first-class native-audio decision).
- Flat `creative_intent.desired_duration` / `desired_duration ±20%` — CreativeIntent was restructured in M-c
  (`target_duration` lives there; MusicPlan carries `target_duration_seconds`).
- DIRECT vs EDIT framing predates the current Story model (Moments + CaptureSessions + Create-My-Story).

**(b) frozen `EditPlanContract` in `contracts/schemas/ai_contracts.py`** — newer and typed, but **also pre-E2 on
the music/native-audio seam**:
- `EditPlanContract{ id, creative_intent_id, target_duration_seconds, output_format, music_asset_id?, segments[] }`;
  `EditSegmentContract{ order, asset_id, source_start/end_seconds?, output_duration_seconds, crop?, speed?,
  transition?, narrative_role? }`; `CropInstruction`, `TransitionInstruction{type,duration}`.
- **Gaps vs. the frozen inputs:** references only `creative_intent_id` (no `story_id`, no `music_plan_id`, no
  `story_guide`/`coverage` provenance); music is only `music_asset_id` (no link to the chosen `MusicAnalysis`, no
  beat-sync anchor, no section/highlight anchoring); **no native-audio field** (soundtrack vs. captured-audio mix
  intent is absent, contradicting M-b `audio_strategy`); `narrative_role` is a free string (not tied to a
  StoryGuide dimension or MusicPlan energy region); `asset_id` is a bare UUID (not explicitly a Moment id).

**Verdict:** the typed contract is the better base, but **both need an E2-aware reconciliation.** `09` should be
rewritten (or banner-superseded) to consume the current contract set; the contract needs a small additive
**EditPlan/2** to carry the music/native-audio seam. **Not frozen here — this doc proposes; owner approves.**

### 4.2 Responsibilities (reaffirmed, E2-aware)

**Edit Planner (planning — AI/engine, no pixels):**
- Select useful **Moment segments** from `MomentUnderstanding.observed.useful_segments` (NOT old `usable_ranges`).
- Construct narrative progression grounded in **StoryGuide/1 dimensions** + **StoryCoverage/2** (what the Story
  means / already has), honoring the MVP anti-checklist stance (ENOUGH is first-class; never force a template).
- Order clips; determine **cut boundaries** (source in/out + output duration per segment).
- Align footage to **real musical structure** from the chosen track's **MusicAnalysis** (beats/downbeats for cut
  cadence, `highlight`/sections for payoff placement) **within** the **MusicPlan/1** intended shape
  (`energy_arc`, `character`) — reconcile intent to real structure, never mechanically.
- **Preserve important native audio** per **MusicPlan.audio_strategy** (`soundtrack_role`,
  `native_audio_priority`): emit *intent* ("this segment keeps its own audio; music recedes"), not a mix.
- Produce an executable **EditPlan** (typed JSON). Fail only if no usable material exists.

**Media Engine (rendering — execution, pixels + samples):**
- Decode assets; apply cuts/transitions/crop/speed; **mix audio** (actual ducking/fades from the plan's intent);
  render the final video; export; (post-M-d) trigger usage-report + safelisting on export.

**Hard boundary (unchanged):** AI/engine produces the plan; the Media Engine executes it. **Never ask an LLM to
"edit the video."** Exact fades/ducking/mix automation are Media-Engine, driven by EditPlan *intent*, not authored
sample-by-sample by the planner.

### 4.3 Proposed minimum **EditPlan/2** (additive; owner-gated, NOT frozen)

Extend the frozen `EditPlanContract` minimally so it carries the E2/music seam — every new field names a consumer:

```
EditPlanContract (edit_plan/2)
  id, story_id (ADD), creative_intent_id, target_duration_seconds, output_format
  music_asset_id?            (the chosen real track — Epidemic UUID or story_catalog id)
  music_plan_id? (ADD)       (provenance: which MusicPlan shaped this)
  music_analysis_ref? (ADD)  (the track's observed structure the plan aligned to; by value or handle,
                              NOT a cached mirror of provider metadata)
  beat_sync? (ADD, bool/enum) (whether cuts were aligned to beats/downbeats)
  segments[]:
    order, asset_id (= Moment id), source_start/end_seconds?, output_duration_seconds,
    crop?, speed?, transition?,
    narrative_role?           (KEEP free-text for MVP; may later reference a StoryGuide dimension id)
    native_audio (ADD, enum)  (keep | duck | mute — per-segment realization of audio_strategy;
                              intent only, NOT a mix curve)
  created_at
```
Deferred (add only on a proven planner need): per-segment music-section anchor, explicit payoff marker, transition
easing curves, multi-track audio. **Freeze EditPlan/2 only after the §5 planning experiment confirms the fields a
good plan actually uses.**

---

## Part 5 — Planning-quality experiment (recommended, smallest form)

**Is an experiment needed before implementing?** **Yes — a small one.** The open architectural questions are not
answerable from contracts alone: (a) can one model produce a *coherent* narrative-ordered plan from real
MomentUnderstanding without a montage template? (b) does aligning to MusicAnalysis beats/highlight measurably
improve pacing, or is it cosmetic? (c) does `audio_strategy`→per-segment `native_audio` survive contact with real
Moments (guitar payoff, birthday singing)? (d) is ±duration feasibility achievable from `useful_segments`?

**Smallest experiment that answers them (NOT a broad model bake-off):**
- **5 scenarios**, reusing existing real fixtures where possible: TMB 60s cinematic journey; guitar-learning
  progression **with real performance audio**; SF exploration; minimal solitude; energetic short-form.
- Inputs per scenario: existing **MomentUnderstanding** fixtures + a **MusicPlan/1** fixture + a (synthetic or
  Free-tier-derived) **MusicAnalysis** (beats/highlight/duration). No real catalog needed if MusicAnalysis is
  stubbed from the §2 experiment or hand-authored.
- **ONE strong model** (reuse the Director/Coverage choice, Opus 4.6) — **no bake-off**; only add a second model
  if the first fails a hard gate.
- **Human-reference expectations defined BEFORE running** (freeze a REVIEW_CRITERIA like E2-a):
  narrative coherence; Moment selection (right segments, nothing load-bearing dropped); useful-segment boundaries
  (cuts land on meaningful sub-ranges); pacing (cadence vs. energy_arc); music alignment (payoff near the real
  highlight, cuts near beats/downbeats where intended); **native-audio preservation** (guitar/birthday keep their
  own audio; music recedes); duration feasibility (within ±20% of target); **no generic montage template**
  (anti-checklist — the plan reflects THIS Story, not a stock structure).
- **Human review decides** whether the plan would make a good video — not a numeric score. Freeze **EditPlan/2**
  only after this. **Do not run automatically; owner-gated.**

---

## Part 6 — Report summary (deliverables)

1. **Free-tier status:** RESOLVED — self-serve instant free key EXISTS (full catalog, no credit card, **≤50
   downloads**, prototyping/evaluation ONLY, no sublicense/safelist/go-live). Supersedes M-d.1 §1. Production =
   paid **Scale**/**Enterprise**, pricing UNKNOWN.
2. **Official signup path:** `https://developers.epidemicsound.com/` → "Get free API key" → details → instant key.
   Owner action; I did not sign up.
3. **API test feasibility:** experiment fully specified (§2), **blocked only on an owner-provided key**; design
   proceeds regardless.
4. **Available MusicAnalysis fields (documented, to be live-confirmed):** duration, bpm, beats, **downbeats**
   (`beats.value==1`), highlight window, vocal class direct; **energy_curve derivable** from waveform JSON; only
   **time-ranged vocal_regions** needs our own analysis (deferred).
5. **Commercial inquiry draft:** §3, ready for owner to send; **not sent.**
6. **Remaining licensing questions:** derived-analysis caching vs. no-cache policy; audio-retention-during-render;
   Free-vs-commercial end-user license scope; termination survival; Scale pricing basis — all in the §3 inquiry.
7. **Edit Planner gap analysis:** `09-edit-planner.md` is pre-E2 STALE (AssetUnderstanding/usable_ranges/flat
   duration/bare music_track_id/no native audio); frozen `EditPlanContract` is better but lacks the music/native-
   audio seam. §4.1.
8. **Minimum EditPlan contract proposal:** **EditPlan/2** (additive: story_id, music_plan_id, music_analysis_ref,
   beat_sync, per-segment `native_audio` keep/duck/mute). §4.3. NOT frozen.
9. **Edit Planner vs Media Engine boundary:** planning (segment/narrative/cut/alignment/native-audio INTENT) vs
   rendering (decode/cut/transition/MIX/render/export). §4.2.
10. **Evaluation fixtures:** 5 scenarios (TMB/guitar+real-audio/SF/solitude/energetic) from existing
    MomentUnderstanding + MusicPlan fixtures. §5.
11. **Model experiment:** ONE model (Opus 4.6), human-reference rubric frozen first, no bake-off. §5.
12. **Recommended next implementation sequence:** (a) owner signs up for the Free key → run §2 live confirm;
    (b) owner reviews/sends §3 inquiry → get Scale pricing + term confirmations; (c) in parallel, rewrite/supersede
    `09-edit-planner.md` E2-aware + run the §5 planning experiment → freeze EditPlan/2; (d) only then implement the
    Edit Planner engine against frozen EditPlan/2; (e) Media Engine is a separate later milestone.
13. **Cost implications:** Free tier = **$0** (≤50 downloads). §5 experiment = a handful of Opus text calls
    (~single-digit dollars, like prior experiments). Production Epidemic = UNKNOWN (Scale, needs-based). No infra.
14. **Blockers requiring owner action:** (i) sign up for the Free API key (self-serve, no cost) to unblock §2;
    (ii) review + send the §3 inquiry to get production pricing/terms; (iii) approve rewriting `09` + running the
    §5 planning experiment. All non-blocking to each other; design continues meanwhile.

**STOP for owner review. No account/credentials, no vendor contacted, no production Music/Edit-Planner/Media
built, no terms accepted, nothing pushed.**
