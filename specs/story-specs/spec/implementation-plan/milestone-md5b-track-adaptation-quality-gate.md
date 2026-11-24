# M-d.5b — Track-Adaptation Final Quality Gate (measurements + A/B/C listening baselines)

Status: 🟡 experiment/eval complete — **awaiting owner listening verdict**. Internal-testing only.
Date: 2026-10-11. No code change; no frozen-contract change. Builds on
[M-d.5](./milestone-md5-epidemic-mcp-provider.md).

## 1. Objective duration measurements (afinfo, decoded audio — not byte-estimated)

| Clip | Requested | **Actual** | Overshoot | Ending |
|---|---|---|---|---|
| cinematic adapted 15s | 15.0 | **18.384 s** | +3.38 s (+22%) | natural ring-out (tail RMS 0.002) |
| cinematic adapted 45s | 45.0 | **48.120 s** | +3.12 s | natural ring-out |
| guitar adapted 15s | 15.0 | **16.896 s** | +1.90 s | natural ring-out |
| guitar adapted 45s | 45.0 | **46.944 s** | +1.94 s | natural ring-out |

**Cause of overshoot (investigated, not assumed):** NOT silence padding (trailing silence 0.03–0.32 s) and
NOT metadata error — the extra time is a **musical tail**: the adapter lands past the requested target on a
phrase boundary and lets the final note decay (tail-1.5s RMS ≈ 0.002 vs full-track ≈ 0.04–0.18). So
`EditRecording(targetDurationMs=N)` means "≈N, rounded UP to a musical ending," not exact N. This matters for
the Edit Planner, which assumes a known soundtrack duration — the adapted duration must be MEASURED and fed
back, never assumed equal to the request.

## 2. Fair A/B/C listening baselines (delivered to owner)
Per track × {15s, 45s}:
- **A** — original trimmed + 0.4 s fade to EXACT target. Objective tell: tail-1.5s RMS stays HIGH
  (0.08–0.15) → music still at full energy at the cut → a **mid-phrase hard stop masked by a fade**.
- **B** — adapted as-is (actual duration above). Natural start + resolved ending.
- **C** — adapted then constrained to EXACT target with a fade. Re-trimming RE-CUTS the adapter's natural
  ending, so C partially loses B's advantage (tail RMS rises again).
Loudness roughly matched (same ballpark RMS); true LUFS normalization not done (no ffmpeg in env) — flagged.
Files: `adapt_review/{A_,C_}*.wav` (A/C) + `*_ADAPTED_*.mp3` (B). Scratch, not committed.

## 3. Quality read (OBJECTIVE only — musical verdict is the owner's)
- A ends mid-phrase (fade masks a non-ending). B ends naturally. C trades B's ending to hit exact N.
- For **guitar**: the Story's **native performance audio** may matter more than any soundtrack treatment;
  adaptation vs trim may be moot if native audio takes priority (per MusicPlan `native_audio_priority`).
- Not claiming adapted is better — that requires listening.

## 4. Reliability
- `EditRecording`+poll latency 3.5–6.8 s, 1–2 polls.
- **`COMPLETED` with `edit=null` = unusable** (no output). Characterized precisely: ambient "Path" fails ONLY
  at tgt=45s; 15/30/60s succeed. So it is a **target-specific** edge case, not a track-wide failure, and the
  adapter mislabels it COMPLETED instead of FAILED. Any integration MUST treat null-edit as failure and FALL
  BACK to original-trim (baseline A).

## 5. Recommendation → **OPTIONAL adaptation (not default, not deferred)**, pending owner listening
- Default adaptation: NO — overshoot + the null-edit edge case make it unsafe as the only path.
- Defer entirely: too strong — it demonstrably produces better endings than a hard trim in most cases.
- **Optional**: adapt when it returns a usable edit; otherwise fall back to original-trim; always MEASURE the
  returned duration and feed the real value to the Edit Planner. Integration point unchanged from M-d.5:
  after duration selection, before Edit Planner (so MusicAnalysis reflects the adapted track).
- Owner listening gate still open before any "better" claim or production go.

## 6. Constraints honored
Business MCP internal-testing only (no commercial sublicense). No production music-selection/render change.
No frozen-contract change. Creative Editing V2 not started.
