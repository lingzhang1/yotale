# Milestone M-d (Part B) — Epidemic Partner API LIVE Validation: RESULTS

**Status: Part B COMPLETE — live-validated against the real API. RESEARCH/PROTOTYPING ONLY — STOP for owner.**
No production integration, no catalog mirror, no persisted provider metadata/audio, no export/sublicense, no
vendor contact. Free-tier prototyping only. One (1) download used (of the free-tier 50). The API key was read
from AWS Secrets Manager (`story-epidemic-key`) **in-process** and is **never printed, logged, committed, or
embedded** — the probe (`evals/edit_planner/epidemic_probe.py`) contains no key.

Account: AWS `989088054552` us-east-1. Probe run 2026-10-07. Redacted summary:
`evals/results/epidemic_probe.json` (gitignored — derived facts only, no key/audio/metadata mirror).

---

## 13. Credential readiness (no secret exposed)
The rotated key is in Secrets Manager as **`story-epidemic-key`**; the probe loads it with
`boto3.secretsmanager.get_secret_value` at runtime (supports a raw string or a single-field JSON secret) and
asserts the `epidemic_` prefix without printing the value. The originally-pasted key remains treated as burned
(the owner rotated it). **No key material appears in any artifact.**

## 14. Endpoints tested (all authenticated, real responses)
`GET /v0/tracks/search` (×5 queries), `GET /v0/tracks/metadata`, `GET /v0/tracks/{id}/beats`,
`GET /v0/tracks/{id}/highlights`, `GET /v0/tracks/{id}/stream` (HLS), the `waveformUrl` JSON fetch, and one
`GET /v0/tracks/{id}/download`. **Every call returned HTTP 200.** Base URL `https://api.epidemicsound.com`.

## 15. Search + metadata — CONFIRMED
- **Semantic search + filters work.** All 5 diverse intents (warm acoustic / cinematic build / energetic /
  sparse ambient / vocal-heavy) returned 5 results each at 200, with `term`, `vocalType` (NONE/LEAD), and
  `bpmMin` filters applied.
- **Metadata is complete per track:** `id, title, bpm, length, moods, genres, waveformUrl, hasVocals, vocalType,
  isrc` all present on the first result of every query. `length` = duration (seconds), `bpm` an integer.

## 16. Beats / downbeats / highlights / waveform — CONFIRMED
- **Beats:** `/beats` returns a list of `{time, value}`. **Downbeats are derivable** as `value==1`. Observed
  (track: n_beats → n_downbeats): warm acoustic 323→81, cinematic 242→61, energetic 516→129, ambient 592→148.
  Downbeat ratio ≈ 1/4 as expected (4/4 bars).
- **Highlights:** `/highlights?duration=15` returns `{"highlights": [{"from": 17000, "to": 32000, "duration":
  15}]}` — millisecond from/to for the AI-picked best window. Confirmed shape.
- **Waveform:** `waveformUrl` serves BBC-format JSON — **3202 data points, sample_rate 48000**, 8-bit amplitude
  pairs (observed min/max e.g. [-124,126], ambient [-92,91]). **A coarse energy_curve is derivable directly from
  this** (downsample the amplitude envelope) — no audio download, no DSP.
- **HLS stream:** `/stream` returns a playable manifest reference (200, manifest present) — usable for in-app
  preview via iOS AVFoundation.

## 17. Vocal classification — CONFIRMED
`hasVocals` (bool) + `vocalType` (NONE/PRESENCE/LEAD) present and filterable server-side (`vocalType=NONE`
returned instrumentals; the vocal-heavy query used `vocalType=LEAD`). Track-level only (no time-ranged vocal
regions from the provider).

## 18. Download / preview — CONFIRMED
One `/download?format=mp3&quality=normal` call: **200, download URL present, expiry present** (documented 24h
normal / 1h high). I did **not** fetch the audio bytes or persist them. HLS preview is separate (streaming, not a
download) and did not consume the download budget.

## 19. MusicAnalysis field mapping — LIVE-CONFIRMED
| MusicAnalysis field | Classification | Live evidence |
|---|---|---|
| duration_seconds | **provider-supplied** | `length` present on every track |
| bpm | **provider-supplied** (⚠ unreliable for ambient) | integer bpm; **ambient track returned bpm=0** (no stable tempo) |
| beats[] | **provider-supplied** | `/beats` `{time,value}`, hundreds per track |
| downbeats[] | **provider-derived** (`value==1`) | ~1/4 of beats, no extra model needed |
| highlight_window | **provider-supplied** | `/highlights` from/to ms |
| energy_curve (coarse) | **derived from provider** | waveform JSON amplitude envelope (3202 pts) |
| vocal_type | **provider-supplied** | `vocalType` NONE/PRESENCE/LEAD + `hasVocals` |
| sections (labelled) | **our analysis if needed** | no section-label endpoint; highlight+waveform may suffice |
| time-ranged vocal_regions | **our analysis if needed** | provider is track-level only; deferred |
**Finding:** for a tempo'd track Epidemic supplies essentially the whole MVP MusicAnalysis. **For ambient tracks
`bpm=0` and the beat grid is unreliable** — the waveform-derived energy_curve + highlight are the trustworthy
signals there (matches the M-d.3 experiment's "don't beat-align ambient" lesson). Every mapped field has an
Edit-Planner consumer (EditPlan/2 `music_analysis_ref`).

## 20. Remaining provider limitations (observed/documented)
- **No local caching** of collections/track metadata (fetch-at-use) — unchanged.
- **bpm/beat grid unreliable for ambient** (bpm=0, grid-filled beats) — treat tempo as optional per track.
- No section-label endpoint; no time-ranged vocal regions (track-level only).
- **Free tier is prototyping-only** (≤50 downloads, no sublicense/safelist/go-live); production = paid Scale/
  Enterprise, **pricing still UNKNOWN** (no inquiry sent).
- Derived-analysis caching + audio-retention windows remain written-confirmation items for the paid agreement.

## 21. Recommended minimum provider adapter (design; NOT implemented)
```
MusicPlan (music_plan/1)
  -> Epidemic /v0/tracks/search   (character.mood_tags -> term/mood; energy -> bpmMin/Max;
                                    audio_strategy.native_audio_priority=important -> vocalType=NONE)
  -> rank candidates              (deterministic: mood/energy/duration fit + vocal penalty; NO embeddings/LLM)
  -> selected MusicAsset{source="epidemic", id=UUID, download handle (expiring)}
  -> MusicAnalysis                (duration=length, bpm (if>0), beats, downbeats=value==1, highlight,
                                    energy_curve=waveform-derived, vocal_type); recompute per use (no mirror)
```
Backend-only: key in Secrets Manager (`story-epidemic-key`), injected into App Runner env; iOS calls Story's
backend which proxies to Epidemic. No new infra. Build only after owner go — this remains research.

## 22. Is MusicAnalysis ready to freeze? — **YES, now live-confirmed (pending the owner's optional-field call)**
The provider path is validated end-to-end. Recommended **`music_analysis/1`** minimum:
`{ duration_seconds, bpm?(nullable — ambient=0→null), beats[], downbeats[]?, highlight_window?{from,to},
energy_curve[]?(coarse, waveform-derived), vocal_type? }`; sections[] and time-ranged vocal_regions DEFERRED
(our-analysis, add only on a proven Edit-Planner need). **Freeze decision is the owner's** (which optional fields
are in scope); the technical basis is no longer blocked.

## Next
- Owner picks the `music_analysis/1` optional fields → freeze (mirrors the EditPlan/2 freeze pattern).
- Build the backend Epidemic adapter (§21) behind a flag, prototyping-tier, when approved.
- Production go-live (sublicense/safelist/usage-report) still needs a paid tier + the M-d.2 inquiry — separate
  owner decision; pricing UNKNOWN.

**STOP for owner review. No production integration, no mirror, no license, no vendor contact, nothing pushed.**
