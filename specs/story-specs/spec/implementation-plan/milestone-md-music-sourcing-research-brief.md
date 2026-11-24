# Milestone M-d — Music Sourcing & Analysis: RESEARCH BRIEF (A-first, Epidemic Partner API)

**Status: RESEARCH / DESIGN ONLY — STOP for owner review.** No provider selected as final, no account or
credentials created, no license purchased, no vendor contacted, no catalog built, no audio/analysis/Edit-
Planner/Media-Engine implementation, nothing pushed automatically. All API capabilities below are quoted from
the **official Epidemic Sound Partner API docs** (`https://developers.epidemicsound.com/docs/`, read
2026-10-07); all pricing is **sales-gated → UNKNOWN**; marketing claims are kept distinct from enforceable
contract terms.

**Owner decision applied (M-d.1 revision):** preferred strategy flips **B→A** to **A-first (Epidemic Partner
API) with B (small Story-owned catalog) as the fallback.** We do NOT build a Story-owned catalog by default.

Pipeline this unblocks: **MusicPlan (frozen `music_plan/1`) → actual track → MusicAnalysis → Edit Planner →
rendered export.**

---

## 1. Verified Epidemic Partner API capabilities

Source: Introduction, Authentication, Music, Metadata, Report-usage, Safelisting guides. Base URL
`https://api.epidemicsound.com` (new `/v1`; `/v0` also on legacy `partner-content-api.epidemicsound.com`).
OpenAPI spec published at `https://partner-content-api.epidemicsound.com/docs/spec.json` (v0).

| Capability | Verified? | Detail |
|---|---|---|
| Free self-serve prototyping tier | **NO** | **"To use the Epidemic Sound API, you need a partnership agreement."** Credentials are provisioned only after an agreement; the dev portal is gated. My prior brief's "free prototyping tier" claim was WRONG — corrected here. |
| Partnership requirement | **YES** | Agreement first → technical team added to Developer Portal → credentials issued. |
| Authentication | **YES** | Three methods. **API Key (recommended)**: single long-lived `epidemic_live_…` bearer, backend-only, all requests proxied through our backend; per-user attribution via `x-partner-user-id` header. **Connect (OAuth2+PKCE)**: user logs in with their own ES account (for existing ES subscribers). **Partner Token (legacy)**: 2-step partner→user token. |
| Catalog access tiers | **YES** | Negotiated in the agreement: **Curated Collections** (100+ professionally curated themes) OR **Full Catalogue** (55,000+ tracks, 250k SFX). Full catalogue unlocks arbitrary search/filter. |
| Search / filtering | **YES** | `/v0/tracks/search` — semantic + keyword `term` (≤500 chars, "music for a calm beach scene"), filters: `mood`, `genre`, `bpmMin`/`bpmMax`, `vocalType`; `filterBehaviour=allOf|anyOf`; sort by Relevance/Date/Title/Popularity/BPM/Duration; facet counts. Browse `/v0/tracks` (≤100/page). |
| Track previews | **YES** | `/v0/tracks/{id}/stream` → **HLS (.m3u8)** manifest; iOS has native AVFoundation HLS support. |
| Audio downloads | **YES** | `/v0/.../download` → MP3 **Normal 128kbps** or **High 320kbps**; links expire (24h normal / 1h high). "When a user wants to add a track to their project for editing or export." |
| **Beat timing** | **YES** | `/v0/.../beats` (Beta) → `{time (s), value}` where **`value`=beat position in bar, 1 = downbeat**. Captures dynamic tempo changes, not just a static BPM. |
| **BPM** | **YES** | `bpm` in every track response (integer, never null). |
| **Waveform** | **YES** | `waveformUrl` → BBC audiowaveform JSON (~1600 min/max pairs, 8-bit). Docs: users read it for "build, drop etc." |
| **Musical sections** | **PARTIAL** | No explicit section/segmentation endpoint. **Highlights** `/v0/.../highlights` (AI "most popular section", trained on billions of YT streams) returns up to 5 windows (5–60s) as `from`/`to` ms + duration. **Find-Similar → similar sections** matches sections *across* tracks. Full intro/verse/chorus/outro labels are NOT provided → derive or analyse. |
| Energy information | **DERIVABLE** | No numeric energy-curve field. Waveform JSON (amplitude envelope) → coarse energy proxy; `highlights` marks the engaging region. |
| Vocal metadata | **YES** | `hasVocals` (bool), `vocalType` (`NONE`/`PRESENCE`/`LEAD`), server-side `vocalType=NONE` filter for instrumental-only, `/lyrics` endpoint (null for instrumentals), `isExplicit`. |
| Popular segments | **YES** | `highlights` endpoint (above). |
| Track licensing | **YES (tiered — see §3)** | Free-Tier personal license vs. ES-subscriber commercial license. |
| Export usage reporting | **YES** | `POST /v0/usage` (per-user, `x-partner-user-id`, platforms YOUTUBE/TIKTOK/INSTAGRAM/…/LOCAL) and `POST /v0/analytics/report` (bulk, ≤100 events, ≤50 trackIds each, ≤7 days old). Report on EXPORT/download-to-device; **do NOT report previews or our own editor downloads**. "Used for billing & analytics." |
| Safelisting | **YES (if enabled in agreement)** | `/v0/safelisting/licenses` CRUD, per-end-user (`X-Partner-User-Id`), per-asset (channel/video), platforms YouTube(video+channel)/IG/FB/TikTok/Twitch/Podcast/Website; channel licenses can carry `expiresAt` tied to subscription; expire-all on churn. Requires API-Key auth + safelisting enabled (else `400 "App is not configured for safelisting"`). |
| Rate limits | **PARTIAL** | Docs reference "per-user weekly rate limits" on **audio delivery** (download/stream/HLS) only; usage reporting is exempt. Exact numbers not public → agreement/portal. |
| Metadata extras | **YES** | `id`(UUID), `title`, artists, `moods`(46 taxonomy), `genres`(~500), `images`, `isrc`, `tierOption`, `isPreviewOnly` (⚠ unreliable on full-catalogue — "attempt the download regardless"). |

**Not inferred:** no section-label endpoint, no numeric energy curve, no downbeat endpoint *separate* from beats
(downbeat IS encoded in `beats.value==1`), no public pricing, no public rate-limit numbers, no free tier.

---

## 2. MusicAnalysis fields — provider-supplied vs. our analysis

Frozen `music_analysis/1` today: `{ bpm?, beats[], sections[] }`; `MusicSection {type,start,end}`.
Classification against verified Epidemic data:

| MusicAnalysis field | Classification | Basis |
|---|---|---|
| `duration_seconds` | **Provider supplies** | `length` (seconds) in every track response. |
| `bpm` | **Provider supplies** | `bpm` field. |
| `beats[]` | **Provider supplies** | `/beats` → per-beat `time`. |
| **downbeats** | **Provider supplies (derivable, trivially)** | `/beats` `value==1` ⇒ downbeat; filter the beats list. No separate model needed. |
| `sections[]` (boundaries) | **Requires our analysis OR partial-from-provider** | No section endpoint. `highlights` gives the key window; `waveform` gives envelope. Full labelled sections (intro/build/chorus/outro) need our own novelty/all-in-one analysis **if** the Edit Planner actually needs labelled segments beyond "the highlight". |
| `energy_curve` (coarse) | **Derivable from provider** | Downsample `waveformUrl` amplitude pairs → per-second/per-section coarse energy. No audio download or DSP needed (waveform is JSON). |
| `vocal_regions[]` | **Requires our analysis — IF needed** | Provider gives track-level `hasVocals`/`vocalType`/`lyrics`, NOT time-ranged vocal regions. Time-ranged ducking under native dialogue needs source-separation/VAD on the downloaded audio. **Justify before adding** (§4, §7). |
| `highlight_window` (NEW candidate) | **Provider supplies** | `highlights` `from`/`to`. Directly useful: "where in the track to anchor the payoff." Consider adding to `music_analysis/1` as provider-native. |
| intro/outro character, build/drop regions | **Not yet justified** | Partly from highlight+waveform; DEFER until a concrete Edit-Planner need appears. |

**Implication:** with Epidemic, Story needs **almost no bespoke audio analysis for MVP** — duration, BPM,
beats, downbeats, highlight, vocal class, and a coarse energy curve all come from provider metadata/waveform
JSON **without downloading or DSP-processing the audio**. The ONLY field that would require true audio analysis
is **time-ranged vocal_regions**, and only if the Edit Planner needs sub-track vocal ducking — see §4.

---

## 3. Licensing model (verified claims vs. terms needing contract confirmation)

**Verified from docs (marketing/doc-level, NOT the signed contract):**
- **User licensing is tiered and per-end-user:**
  - **Free Tier music** → each end user gets a **personal user license** allowing them to "post anywhere online."
  - **Users with an active paid ES subscription connected via ES Connect** → a **commercial user license**
    (monetization, advertising/promotion).
- **Safelisting** protects the end user's channel/video from platform copyright claims; **per-user, per-asset**;
  on churn you expire their licenses, and **content published while active stays protected**.
- Rights are **tied to the end user**, not blanket-granted to the platform — the licence a given exported video
  carries depends on that user's tier (Free vs. ES-subscriber-via-Connect).

**This resolves the M-b gating rule but changes the architecture:** Epidemic's model is **per-end-user sub-
licensing**, not "Story holds one platform license covering everyone." Two concrete consequences:
1. The **commercial** tier (monetize/advertise) appears to require the end user to be an **ES subscriber
   connected via Connect** — not automatic for an anonymous API-Key user. A pure API-Key integration grants the
   **Free-Tier personal** license ("post anywhere") — adequate for dogfooding and non-monetized sharing, but
   **the monetization/commercial path needs ES-Connect or an explicit contractual grant.** ← **owner/legal.**
2. **Safelisting must be enabled in the agreement** and driven per export to actually suppress claims.

**Terms that need the signed contract / written confirmation (do NOT treat the doc as the licence):**
- Exact scope of the Free-Tier "post anywhere" licence for **videos our users EXPORT and SHARE** (sync + master
  use embedded in a rendered MP4), worldwide.
- Whether Story's own backend-held API-Key integration **sublicenses to our end users** at the Free tier without
  each user holding an ES account, and the precise commercial-tier requirement.
- **Rights after termination / subscription lapse** — docs say safelisted content stays protected, but confirm
  already-rendered-and-exported videos remain cleared if Story's partnership ends.
- Per-export reporting obligations and any **minimums/commitments** in the commercial deal.
- **Pricing: NOT PUBLIC → UNKNOWN.** Partner pricing is sales-gated (likely per-MAU and/or rev-share). **No quote
  is fabricated.** Must come from Epidemic sales with owner authorization.

---

## 4. Caching & analysis restrictions (verified + open)

**Verified (Introduction → Caching policy, verbatim):**
> "Partners are **not permitted to cache collections or track metadata locally**. Always fetch data from the API
> to ensure your users see up-to-date content."

So Story **may NOT** persist a mirror of Epidemic's catalog, collections, or track metadata as a local store.
Curated collections are explicitly dynamic (e.g. "Trending on TikTok" refreshes daily).

**Open questions the public docs do NOT fully resolve — require WRITTEN confirmation (the Acceptable Use Policy
page was not machine-readable at research time):**
- May we **temporarily download audio for rendering** a user's video? (Download endpoint exists "for editing or
  export", links expire 1–24h — strongly implies yes for the render job, but confirm.)
- May we **analyze a downloaded track** (beat/section/energy) ourselves? (Likely unnecessary — provider supplies
  most — but confirm if we ever do time-ranged vocal analysis.)
- May we **store DERIVED analysis** (our own beat/section/energy JSON) tied to a track ID? The caching ban is
  worded as "collections or track **metadata**" — our *derived* MusicAnalysis is arguably not "their metadata",
  but this is the single most important open compliance question. **Mark REQUIRES WRITTEN CONFIRMATION.**
- May we **retain the audio during a render job**, and **retain the rendered video** containing the music after?
  (Rendered-video retention is the whole point of export + safelisting, so almost certainly yes, but confirm the
  audio-at-rest window.)

**Architecture rule adopted:** **do NOT build anything that assumes we may cache Epidemic catalog/metadata or
persist their audio.** Design for **fetch-at-use** (search → preview via HLS → download for the render job →
report usage → discard source audio), and treat **derived MusicAnalysis persistence as conditional** on written
confirmation. If confirmation is denied, we recompute per render (cheap, since it's provider metadata) rather
than caching.

---

## 5. Smallest useful prototype (NO production functionality)

Goal: prove `MusicPlan → Epidemic search → candidates → preview → select → retrieve → MusicAnalysis → Edit-
Planner handoff` end to end, backend-only, with throwaway data.

```
MusicPlan (music_plan/1, already produced)
  └─ build an Epidemic search query from character.mood_tags + energy + target_duration + vocalType
       (energy→BPM band; native_audio_priority=important → vocalType=NONE)
  └─ GET /v0/tracks/search → candidate tracks (+ facet counts)
  └─ for top N: HLS preview URL (user) + /beats + highlights + waveformUrl
  └─ user (or auto) selects one
  └─ GET /download (render job only) + assemble MusicAnalysis from provider fields
       {duration=length, bpm, beats, downbeats=beats.value==1, highlight, energy_curve=waveform-derived,
        vocal_type}
  └─ emit MusicAsset{source="epidemic", id, …, analysis} → hand to Edit Planner (stub)
```

**Account/credentials needed (do NOT create without owner authorization):** a **partnership agreement** (there is
NO free tier), then Developer-Portal access → an **API Key** (`epidemic_live_…`). Content tier: request **Full
Catalogue** for search; **Curated Collections** suffices for a mood-driven first cut. Safelisting + commercial
tier are separate agreement line-items.

**Credential handling:** API Key is **backend-only** (`Authorization: Bearer`), stored in the **existing AWS
Secrets Manager**, injected into the App Runner service env. **NEVER embed the key in iOS.** iOS calls Story's
backend; the backend proxies to Epidemic (API-Key auth mandates this proxy model). Per-user attribution via
`x-partner-user-id` using Story's stable anonymised user id.

**If API access is unavailable (no agreement yet):** fall back to a **small local analysis experiment** (§7) on
legally-usable tracks to validate our own MusicAnalysis gap-fill — no commercial purchases, no new infra.

---

## 6. Epidemic (A) vs. Story-owned catalog (B)

| Axis | A — Epidemic Partner API | B — Story-owned catalog (fallback) |
|---|---|---|
| Integration complexity | Moderate: backend proxy, auth, search→download→report, safelisting, fetch-at-use (no caching) | Low: own files in S3, offline analysis, in-process match |
| Catalog breadth | **55,000+ tracks**, curated collections, semantic search | ~30–100 curated tracks |
| Musical quality | High, professionally curated | High but narrow |
| **Licensing certainty** | Model is clear (per-user, tiered) but **commercial-tier scope + pricing UNKNOWN → needs contract** | Must verify each track's end-user-export rights; **perpetual/buyout preferred** so lapse doesn't orphan videos |
| Production cost | **UNKNOWN** (per-MAU/rev-share, sales-gated); likely per-export reporting | One-time per-track + S3; **$0 per export** |
| Analysis requirements | **Minimal** — provider supplies duration/BPM/beats/downbeats/highlight/vocal class; waveform→energy | We analyse each track once offline (librosa/etc.) |
| Maintenance | Provider owns catalog freshness; we own the integration + compliance (no-cache) | We own curation, metadata, licence tracking |
| Scalability | Scales to large catalogs; cost scales with users/exports | Flat; breadth-limited |
| Time to working MVP | Longer (agreement + contract gating before any key) | **Fast** (no third party; start immediately) |

**Neither is "cheaper" without verified terms** — B is cheaper *per export* but breadth-limited; A's cost is
unknown until the quote. B remains the **fallback** precisely because it is unblocked today while A is contract-
gated.

---

## 7. Revised MusicAnalysis experiment

Because Epidemic supplies most signals, the experiment **shrinks** and **re-targets** to the real gaps:
1. **Do NOT re-implement** beat/BPM/downbeat/vocal-class/highlight — validate the **provider's** values instead
   (sanity-check beats/highlights against a handful of tracks once we have API access).
2. **Remaining gaps to test:**
   - **Labelled sections** beyond `highlights` — only if the Edit Planner needs intro/build/chorus/outro labels.
     Evaluate: is `highlights` + beats + energy-from-waveform *enough* for good cuts, or do we need our own
     segmentation? **Default hypothesis: highlights+beats+waveform is enough for MVP; defer section labelling.**
   - **Time-ranged `vocal_regions`** — only if native-audio ducking needs sub-track vocal timing. Test a
     separation/VAD pass on a few downloaded tracks; weigh against just using `vocalType` + `audio_strategy`
     at the track level.
3. **If NO API access yet:** run the small **local** fallback on legally-usable tracks (a few CC0/owned) covering
   warm-acoustic, cinematic-build, energetic-short, sparse-ambient, emotional-instrumental, vocal-heavy, clear-
   sections, weak-beat — librosa baseline + (optionally) an all-in-one segmenter + a separation model for vocals.
   Score beat/section/energy/vocal usefulness, latency, compute. **No commercial purchases, no new infra.**
4. **Human review** decides whether the selected track actually improves the Story — not F-scores. Freeze
   `music_analysis/1` only after this.

**Proposed minimum `music_analysis/1` (revised, provider-aligned):**
`{ duration_seconds, bpm, beats[], downbeats[]?, highlight_window?{from,to}, sections[]? (type,start,end),
energy_curve[]? (coarse, waveform-derived), vocal_type?, vocal_regions[]? }` — everything optional except
duration+bpm+beats (all provider-native). Add a field only when an Edit-Planner decision needs it.

---

## 8. MusicPlan → track matching (unchanged architecture, provider-fed)

```
MusicPlan (music_plan/1)
  -> Epidemic search query     (character.mood_tags→mood/term, energy→bpmMin/Max, target_duration,
                                audio_strategy.native_audio_priority→vocalType)
  -> candidate tracks + facets
  -> structural score          (energy_arc vs beats/highlight/energy_curve; build/payoff vs highlight window)
  -> vocal/native guard         (native_audio_priority=important|dialogue -> prefer vocalType=NONE)
  -> ranked -> top MusicAsset{source="epidemic"} + its (provider-derived) MusicAnalysis
```
**Still deterministic, rule-based — NO embeddings, vector DB, or extra LLM.** Epidemic's own semantic `term`
search does the heavy lifting on the query side; our weighted score ranks the returned candidates and applies the
native-audio vocal penalty. Fully testable with recorded fixtures (store sample API responses as test data, not
as a live cache).

---

## 9. Native audio stays first-class (preserve M-b)
`audio_strategy.{soundtrack_role, native_audio_priority}` drives both the search (→ `vocalType=NONE` when native
priority is important) and downstream mix intent. Guitar/birthday/TMB/dialogue cases unchanged: MusicAnalysis
(provider-fed) **informs** ducking/placement; it does NOT perform fades/ducking — that's Edit Planner / audio-mix.
`vocalType`/`hasVocals` at track level is enough to AVOID vocal-vs-speech conflicts for MVP; time-ranged
`vocal_regions` is only needed for sub-track ducking (deferred, §7).

---

## 10. Edit Planner boundary (final interface — unchanged)
- **MusicPlan** — desired musical shape (fractions, categorical). Owns intent.
- **MusicAsset** — the chosen real track (now possibly `source="epidemic"`, carrying the Epidemic track UUID +
  expiring download handle, NOT cached metadata).
- **MusicAnalysis** — observed track structure (real seconds/beats/sections/highlight), provider-fed where
  possible. Owns facts, no decisions.
- **MomentUnderstanding** — what each captured Moment contains.
- **Edit Planner** — OWNS footage selection, clip ordering, exact cut times, beat alignment, music-segment
  selection, soundtrack placement, native-audio preservation, transitions. Reconciles MusicPlan intent **within**
  MusicAnalysis's real structure (land the payoff at the real `highlight`/climax, not mechanically at 0.75).
- **Media Engine** — rendering only; also the component that holds the Epidemic audio transiently during render
  and triggers usage-report + safelisting on export.
None of these move into MusicPlan.

---

## 11. Infrastructure implications (existing AWS sufficient; no changes authorized)
Existing: App Runner + ECR + S3 (temporary media) + Secrets Manager. For Epidemic (A): **no new infra** — the
backend proxies search/preview/download, stores the API key in **existing Secrets Manager**, and the render job
pulls audio transiently (expiring links) into **existing S3 temporary-media** scratch, discarding after render.
**No local catalog store** (caching is prohibited anyway). Usage-report + safelisting are outbound HTTPS calls.
For the fallback (B): analyse-once-offline + S3, also no new infra. **No S3/CDN/queue/worker changes are
authorized during M-d research.**

---

## 12. Figma Music UX implications
Frozen Figma already has the future track surface (`ScreenTMBMusic` recommended tracks + preview, `MusicPick`
pick+Change, Result-screen "Change music"). With Epidemic the minimal future flow becomes concrete:
`MusicDirection → suggested Epidemic track (from §8 matching) → HLS preview → optional Change → Create My Story`.
The **music choice need not be finalised during creation** — a strong default from matching, previewable/
changeable before or after the first rendered preview, fits "generated at/just-before Create My Story." Preserve
the lightweight M-c MusicDirection UX; **do not build a music editor.** The disabled "Choose a track" section is
exactly where the Epidemic suggested-track + preview lands when A is approved.

---

## 13. Risks & unresolved questions
1. **Commercial-tier licence scope + PRICING (sales-gated → UNKNOWN).** The single biggest open item; blocks a
   final A decision. (§3)
2. **Derived-MusicAnalysis persistence vs. the no-cache policy** — REQUIRES WRITTEN CONFIRMATION. (§4)
3. **Audio retention during/after render** — confirm the allowed window. (§4)
4. **Free-Tier vs. ES-Connect commercial** — does monetized/advertised export require each user to be an ES
   subscriber via Connect, or does the partnership grant it? (§3)
5. **Rate limits** (per-user weekly on audio delivery) — numbers not public; confirm they fit expected export
   volume. (§1)
6. **Safelisting enablement** must be in the agreement; video-safelisting is YouTube-only (channel-safelisting on
   IG/TikTok/etc.). (§1 Safelisting)
7. **Termination survival** of already-exported videos. (§3)
8. **AUP page** was not machine-readable at research time — several §4 answers live there; read it with the agreement.

---

## 14. Decision gate — recommendation: **B (technically suitable, commercial terms UNKNOWN)**

Per the owner's gate options:
- **A (proceed to integration design)** — NOT yet: commercial terms/pricing are unverified.
- **► B (technically suitable, commercial UNKNOWN → prepare owner decision / vendor inquiry, no production
  integration)** — **THIS.** Epidemic is **technically an excellent fit**: real search, HLS preview, MP3 download,
  beats+downbeats, highlights, waveform, vocal metadata, usage reporting, and per-user safelisting cover the
  pipeline, and it **nearly eliminates our own audio-analysis burden**. But there is **no free tier**, pricing is
  **sales-gated**, and the **commercial-tier/sublicensing + no-cache-of-derived-analysis** terms need the signed
  contract. So: **prepare the owner decision + a vendor-inquiry checklist; do not integrate production yet.**
- **C (Epidemic cannot meet critical requirements → Story-owned catalog)** — not warranted; Epidemic meets the
  technical requirements. B(catalog) stays the **fallback** only if the commercial terms prove unviable.
- **D (insufficient evidence → one bounded experiment)** — the one bounded experiment that *would* add evidence
  needs **API access**, which needs the agreement. Until then, run the §7 **local** fallback experiment only if
  the owner wants to de-risk our MusicAnalysis gap-fill independently.

**Recommended MVP strategy:** **A-first (Epidemic Partner API)** conditional on (a) a commercial quote the owner
accepts and (b) written confirmation of the §4 caching/analysis/retention and §3 export-licence terms;
**fallback B** (small Story-owned catalog, unblocked today) if those terms are unviable or the timeline can't wait.

---

## 15. Exact next implementation gate (when owner approves)
1. **Owner authorizes a vendor inquiry to Epidemic** (pricing + the §13 term confirmations). *No contact without
   this authorization.*
2. On acceptable terms: owner authorizes **a partnership agreement + API-Key provisioning** → key into existing
   Secrets Manager.
3. Build the **backend Epidemic proxy** (search/preview/download/report/safelisting) — the smallest §5 prototype
   first, behind a feature flag, no iOS key exposure.
4. Validate provider beats/highlights on a few tracks; decide the §7 remaining gaps (sections? vocal_regions?);
   **freeze `music_analysis/1`.**
5. Build the deterministic matcher (§8) with recorded-response fixtures.
6. Wire the suggested-track + HLS preview into the (currently disabled) Figma track surface.
7. Hand `MusicAsset{source="epidemic"} + MusicAnalysis` to the Edit Planner milestone (separate).
*If the owner chooses the fallback B instead:* acquire ~30–100 export-licensed tracks → offline analysis → same
matcher → same Figma wiring.

---

## 16. Decisions requiring owner approval
- **Authorize a vendor inquiry to Epidemic** for pricing + the §13 licensing/caching/retention confirmations
  (nothing is contacted without this).
- **A-first vs. fallback-B** given that A is contract-gated and B is unblocked today (timeline call).
- Whether to run the §7 **local** MusicAnalysis experiment now to de-risk independently of Epidemic access
  (needs a small legally-usable track set — no commercial purchases).
- Which optional `music_analysis/1` fields (sections / vocal_regions / highlight_window / energy_curve) are in
  scope to freeze.
- **user-import (Strategy C)** remains a disclaimered secondary path, never the default — confirm if it ships in
  MVP at all.

**STOP for owner review. No provider chosen as final, no account/credentials, no license bought, no vendor
contacted, no catalog/analysis/infra/Edit-Planner built, nothing pushed.**
