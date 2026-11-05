# M-d.5 — Epidemic MCP Provider (internal-testing) + energy_curve + Track-Adaptation experiment

Status: 🟢 built & deployed (MCP provider + energy_curve) · 🟡 design/experiment done, awaiting owner
listening verdict (track adaptation). **Internal testing only — not a production/commercial path.**

Date: 2026-10-11. App commits (local, NOT pushed): `ed69971` (MCP provider), `3f4186f` (energy_curve),
`7666a4d` (durable CDK IAM). Dev backend: App Runner `story-development-api`, acct 989088054552 us-east-1.

---

## 1. Why

The production music path (Partner REST API, `packages/music_provider.EpidemicClient`) uses a *prototyping*
key whose free tier returns **HTTP 402** on `/stream` (preview) and `/download` once the allowance is spent —
breaking music preview on device. The owner has a **Business-subscription Epidemic MCP** key for internal
testing. Goal: add the MCP as a SECOND, flag-selected provider that clears the 402 wall, **without** changing
the REST path (which remains the production provider) or any frozen contract.

## 2. What shipped

### 2a. MCP provider (additive) — `ed69971`
- New `packages/music_provider/mcp_client.py :: EpidemicMCPClient`, speaking the Epidemic **MCP Server (Beta)**
  — an Apollo/GraphQL endpoint at `https://www.epidemicsound.com/a/mcp-service/mcp`, JSON-RPC over SSE.
- Business key in Secrets Manager secret **`epidemic-mcp-api-key`** (`epidemic_…`), read in-process; never
  logged/committed/shipped to iOS.
- Selector `get_music_client()`: returns the MCP client when `STORY_MUSIC_PROVIDER=mcp`, else the REST client.
  Both still gated by `STORY_EPIDEMIC_MODE=prototyping`. Endpoints changed one line each (3 sites).
- Method parity with the REST client: `search`, `preview_url`, `download_link`, `metadata`, `beats`,
  `highlights` (+ `waveform_for_track`, below).

| Need | MCP mapping | Notes |
|---|---|---|
| search | `SearchRecordings` | id/title/duration(ms→s)/bpm/mood+vocal tags |
| preview | inline `audioFile.lqmp3Url` | ships in search result — **no extra call, no 402** |
| download | `DownloadRecording(FULL,MP3)` | signed `assetUrl` w/ `exp` |
| metadata | `SearchSimilarToRecording` | path `data.recording.similarRecordings.nodes[]` (flat recs) |
| beats / downbeats / highlights | — | **NOT available on MCP** → honestly empty, never fabricated |
| waveform | `audioFile.waveformUrl` | BBC-format JSON (see 2b) |

### 2b. energy_curve from waveformUrl — `3f4186f`
- `waveform_for_track(track_id)` fetches the cached `waveformUrl` (BBC JSON: `version 2, bits 8, data[]`
  signed int8, ~14 KB / 3202 samples) and feeds it through the **existing frozen `normalize_energy()`** to
  populate `MusicAnalysis/1.energy_curve` (16 coarse 0–1 buckets).
- Bounded + graceful: **8 s timeout, 1 MB cap**; returns `None` (→ empty energy_curve, no error, no invented
  value) on unknown/expired/forbidden/empty/malformed/oversize.
- REST `waveform_for_track` returns `None` → production energy_curve behavior unchanged.
- Waveform payload used transiently, **not persisted/mirrored** (Business MCP terms).

### 2c. Durable IAM — `7666a4d`
- CDK `infrastructure/cdk/lib/story-api-stack.ts` now grants the App Runner instance role
  `secretsmanager:GetSecretValue` on BOTH `story-epidemic-key-??????` and `epidemic-mcp-api-key-??????`
  (name-scoped, no wildcard). Closes prior drift (the REST grant was never in CDK; it had been applied
  out-of-band). Live role already carries both grants, so no effective drift; a future `cdk deploy` reconciles.

## 3. Verification
- Full backend suite **214 passed** (26 new music-provider tests across the three commits).
- Deployed to dev via CodeBuild → ECR → App Runner. Live `/v1/music/candidates` (cinematic/guitar/ambient):
  200, 3 playable previews each, **energy_curve 16 pts all 0–1**, beats/downbeats/highlight honestly empty
  (even at known bpm), graceful-None on dead waveform URL. Added latency ~59 ms (one waveform GET, top pick).
- Deploy gotchas: source.zip must include `buildspec.yml` (use `$ECR_URI`) AND `prompts/`; CodeBuild success
  ≠ deploy success (verify the endpoint). First MCP deploy 503'd until the IAM grant above was added.

## 4. Track-Adaptation experiment (design/eval only — NOT integrated)
`EditRecording(targetDurationMs, downloadAudioFormat) → PollEditRecordingJob → DownloadRecordingEdit`.
Ran 3 categories × 2 targets (15s/45s):

| | latency | polls | output |
|---|---|---|---|
| cinematic/guitar, 15s & 45s | 3.5–6.8 s | 1–2 | 0.68–1.9 MB MP3, completed w/ preview |
| **ambient "Path" 45s** | — | — | **`status=COMPLETED` but `edit=null` (NO output), reproducible ×2** |

- **Finding:** "COMPLETED" ≠ "produced a usable edit". Any integration MUST check `edit` is non-null and fall
  back to original-trimmed.
- **Architecture:** adaptation changes track STRUCTURE + DURATION → stale MusicAnalysis. Must re-run analysis
  on the adapted track. Proposed point = **after duration selection, before Edit Planner** (so MusicAnalysis
  reflects the adapted track), OR an optional post-plan soundtrack adjustment. NOT before duration (circular).
  No frozen-contract change needed for either.
- Owner-review audio set (original vs adapted 15s/45s, cinematic+guitar) delivered for listening. **Musical
  quality NOT yet judged** — awaiting owner verdict before any "adapted is better" claim.
- **MVP recommendation:** HOLD / likely not-in-MVP — technically working + low-latency, but has a reproducible
  silent-failure mode and adds analysis-recompute complexity; quality gain over trim/fade unproven.

## 5. Licensing
Business MCP = **authorized internal testing only**. It does **NOT** grant platform-wide commercial
sublicensing. Commercial export stays behind `STORY_MUSIC_COMMERCIAL_EXPORT` (OFF). Adapted-track downloads
carry the same restriction as originals.

## 6. Open items
- Not pushed (local commits only). `cdk deploy` not run (no effective drift).
- `/v1/music/analysis` for a directly-selected track (not from a prior search in-instance) has no cached
  waveformUrl → empty energy_curve there (candidates top-pick always has it). Acceptable, graceful.
- IAM fragility: a CDK re-synth without the `7666a4d` change would drop the MCP grant → MCP mode 503s.
