# Milestone C4A.2 — Capture Evidence transport experiment (gate report)

Status: **COMPLETE — stopped at gate. Do NOT begin C4B. No production camera code
touched. No Asset Understanding started. No dataset event-window annotation done.**
Date: 2026-10-05. Author: default (Kiro).

Experiment commissioned to test a reusable, **intent-independent temporal evidence
layer** that observes the camera stream *while recording* and emits a small ordered
`CaptureEvidence` set, versus the current approach of uniformly sampling frames
*after* recording. Hypothesis: live-observed, change-aware evidence selection gives
the Shot Validation model better temporal evidence than blind uniform sampling.

**Headline result: the hypothesis did NOT hold on this corpus.** CaptureEvidence
matched uniform-4 on aggregate user-state accuracy (0.721 == 0.721) but was **worse
on the single most safety-critical axis — contradiction detection (0.40 vs 0.80)** —
and introduced two **false GOT IT** verdicts on semantically contradicted footage.
Uniform-4 remains the recommended C4B transport. CaptureEvidence is **deferred**, not
adopted — with a specific, measured reason, and a clear future role for Asset
Understanding rather than immediate Shot Validation.

---

## 1. CaptureEvidenceV1 proposal (experimental; NOT frozen into core contracts)

An eval-only, intent-independent representation. **No** people/object labels, Story
intent, Beat, Shot purpose, importance, emotion, or event descriptions — only cheap
temporal structure.

```
CaptureEvidenceV1:
  generator_version      : str     # "capture_evidence/v1"
  duration_ms            : int
  observation_rate_fps   : float   # 3.0 baseline
  observed_frames        : int     # how many observations the forward pass made
  evidence_count         : int     # ~2..6 after prune
  evidence_points[]:
     timestamp_ms         : int
     role                 : start | before_change | change | after_change | end
     change_score         : float  # 0..1 normalized luma frame-change (causal)
     sharpness_score      : float  # 0..1 variance-of-Laplacian, clip-normalized
     frame_ref            : str    # ephemeral JPEG path (DERIVED/PRIVATE, not committed)
  selector_cpu_ms_forward / _total  # measured selector cost (offline incl. decode)
```

Deliberately **not** frozen: it is a transport/eval artifact, not a domain contract.
If ever persisted (see §Persistence), production stores the lightweight metadata
only — never necessarily the JPEG evidence frames.

Implemented: `evals/shot_validation/tools/capture_evidence.swift` (AVFoundation;
ffmpeg/pyav are unavailable in-sandbox). Runner:
`evals/run_capture_evidence_compare.py`.

## 2. Selector algorithm (deliberately simple; forward-only)

LIVE path and OFFLINE path feed ONE generator; this experiment drives the OFFLINE
path frame-by-frame exactly as the live path would.

1. **Observe forward** at ~3 fps. At observation time T, use ONLY data ≤ T (no
   future lookahead — enforced structurally: the pass is a single forward loop).
2. Per observation compute two **cheap** signals on a 160px grayscale thumbnail:
   normalized mean-absolute **luma change** vs the previous observation, and a
   **sharpness** proxy (variance of a 3×3 Laplacian).
3. Maintain a **bounded causal rolling buffer** (cap 12); when full, drop the
   lowest-change interior candidate. Track the running max-change observation.
4. **At stream completion**, prune to ~4–6 ordered points: always keep `start` +
   `end` anchors; add the dominant-change observation (`change`) and its causal
   `before_change` / `after_change` neighbors; fill toward 6 with the next
   strongest, temporally-separated changes; if the clip is too static, back-fill
   evenly-spaced points so at least 4 (when the clip is long enough).
5. **No** optical flow, object tracking, embeddings, Vision/ML semantic
   recognition, scene understanding, or event classification. This is not an AI
   engine; it is a cheap signal + a bounded heuristic.

## 3. Results — uniform-4 vs uniform-6 vs CaptureEvidence

Identical **Sonnet 4.6** (`us.anthropic.claude-sonnet-4-6`), identical prompt
(`prompts/shot_validation/v1`), identical fixtures (68), identical expected labels,
identical derivation. **204 live Bedrock calls.** Result file:
`evals/results/c4a2_capture_evidence_20261005T043200Z.json`.

| metric (OVERALL, n≈68) | uniform-4 | uniform-6 | CaptureEvidence |
|---|---|---|---|
| user-state accuracy | **0.721** | 0.687 | **0.721** |
| false-fulfillment | **0.176** | 0.224 | 0.191 |
| false-TRY-AGAIN | 0.0 | 0.0 | 0.0 |
| **contradiction detection** | **0.80** | 0.60 | **0.40** ⬇ |
| adversarial catch | **0.50** | 0.333 | 0.333 |
| alternative-success recog. | 0.20 | 0.30 | **0.40** |
| temporal accuracy | **0.818** | 0.714 | 0.727 |
| technical-failure accuracy | 0.312 | 0.333 | 0.375 |
| **contradiction leaked → fulfilled** (worst case) | **0** | 2 | **3** ⬇ |
| model p50 / p95 latency (s) | 4.09 / 5.75 | 4.47 / 5.78 | 4.51 / 5.37 |
| evidence/frames per clip | 4 | 6 (1 parse err) | mean 5.87 (2–6) |

Uniform-4 is the best or tied-best on every metric that governs safety
(false-fulfillment, contradiction detection, contradiction-leak, temporal), at the
lowest latency and lowest token cost (4 frames). More frames did not help: uniform-6
was *worse* across the board and threw a parse error. **CaptureEvidence did not earn
its complexity.**

## 4. ≤10s DIRECT-like band — PRIMARY (n=28)

| metric (≤10s) | uniform-4 | uniform-6 | CaptureEvidence |
|---|---|---|---|
| user-state accuracy | **0.607** | 0.556 | 0.643 |
| false-fulfillment | 0.25 | 0.222 | **0.107** |
| temporal accuracy | **0.60** | 0.25 | **0.60** |
| alternative-success | 0.0 | 0.0 | 0.0 |
| technical accuracy | 0.385 | 0.417 | **0.462** |

On the primary band CaptureEvidence has one genuine edge — **lower false-fulfillment
(0.107 vs 0.25)** and slightly higher user-state/technical accuracy — but it does
**not** improve temporal accuracy (tied at 0.60), which was the entire point of a
temporal evidence layer. The ≤10s band is also where overall accuracy is *weakest*
for every arm (0.56–0.64), confirming short DIRECT-like clips are the hard case and
the current validator (any transport) is not yet production-ready there. 10–30s is
much stronger (0.79–0.82); >30s is small-n and inconclusive.

## 5. Failure cases — where CaptureEvidence performed WORSE (the decisive finding)

The requested "report any cases where CaptureEvidence performs worse because visual
change was unrelated to semantic importance." Both regressions are exactly that:

| fixture | expected | uniform-4 | CaptureEvidence | why |
|---|---|---|---|---|
| `A03_backpack_but_arrival_not_departure` | keep+one_more (contradicted→unfulfilled) | ✅ contradicted / unfulfilled | ❌ **matched / fulfilled → GOT IT** | change-peak frames showed backpack handling that *looks* like the requested action; the arrival-vs-departure ORDER was lost |
| `S03_D_reverse_reveal__take2` | keep+one_more (contradicted→unfulfilled) | ✅ contradicted / unfulfilled | ❌ **deviated / fulfilled → GOT IT** | reveal direction is reversed; concentrating frames on the pan's change moment dropped the directional context that proves it's backwards |
| `S02_G_contradictory_action` | (contradiction) | partial | **fulfilled** (worse) | same mechanism: motion present at change-peak, contradiction direction lost |

Root cause, stated plainly: **the selector keys on visual-change magnitude, which is
not the same as temporal-semantic importance.** For "departure vs arrival", "walk
toward vs away", and "reveal direction", the discriminating evidence is the *ordered
relationship across the whole clip*, not the single moment of greatest pixel change.
By spending its evidence budget near the change peak, CaptureEvidence can present
frames that superficially satisfy the request while discarding the ordering that
reveals the contradiction — producing a **false GOT IT**, the worst error class in
this product. Uniform spacing, by construction, preserves the global temporal
skeleton and caught these.

The one case CaptureEvidence "won" (`T01_B_too_short`, 0.47s → only 2 evidence
points → TRY AGAIN) is **already handled by the approved deterministic duration
gate**, so it is not an independent advantage.

## 6. CPU / memory / runtime estimate

**Measured (offline, Mac, incl. AVFoundation decode):** selector p50 **682 ms**,
mean 887 ms, max 6.0 s (the 154 s / 214 MB clip). This cost is **dominated by video
decode**, not by the selection math — the luma-diff + 3×3 Laplacian on a 160px
thumbnail is sub-millisecond per frame.

**Expected on iPhone, LIVE path:** the decode cost **disappears** — a live
`AVCaptureSession` already delivers decoded `CMSampleBuffer`s. The real on-device
cost is: downscale to ~160px + two cheap passes at **3 fps** (not 30 fps), i.e. ~3
operations/second over a few thousand pixels, plus a bounded buffer of ≤12 small
thumbnails (a few hundred KB resident). This is comfortably runnable **beside
`AVCaptureMovieFileOutput`** without storing every observed frame: only the ~4–6
selected frames are ever JPEG-encoded, and only at stream end. Memory and CPU are
negligible; the architecture is feasible. **Feasibility was never the blocker —
quality was.**

## 7. Is live evidence extraction worth implementing (for Shot Validation)?

**No, not now.** It does not beat uniform-4 on the metrics that matter and it
*regresses* contradiction detection — the exact temporal-semantic distinction it was
meant to help. Spending engineering on a live camera-stream observer, a new
generator, and a (non-frozen) CaptureEvidence representation is not justified by any
measured Shot Validation gain.

## 8. Part of C4, or deferred?

**Defer out of C4.** C4B should ship with **uniform-4 ordered frames + the
deterministic duration gate**, the already-recommended frontier. CaptureEvidence
stays an experiment on disk (tool + runner committed; evidence frames private). No
C4 milestone depends on it.

## 9. Implications for future Asset Understanding

This is where CaptureEvidence has a real future. Asset Understanding operates
**offline, over the whole clip, without a specific requested Shot** — so (a) the
contradiction-detection regression (which came from *purpose-conditioned* judgment on
too-few frames) does not apply, and (b) an intent-independent, change-aware set of
temporal anchors is a sensible, cheap pre-pass to seed a heavier understanding model.
The **intent-independence property is proven** (see §Intent-independence) — the same
physical clip yields byte-identical evidence regardless of context — which is exactly
the reusability Asset Understanding wants. **Recommendation: carry CaptureEvidenceV1
forward as an Asset-Understanding input candidate, re-evaluate it there, and do NOT
couple it to Shot Validation.**

## 10. Recommendation for C4B transport

**Ship C4B on uniform-4 ordered, timestamped frames + deterministic duration gate.**
Do not build the live CaptureEvidence observer for C4. Do not build native-video
transport (per the standing instruction; this experiment did not change that). Keep
CaptureEvidence as a deferred, Asset-Understanding-facing experiment.

---

## Intent-independence test (REQUIRED) — PASSED

For both shared-source / different-purpose pairs the CaptureEvidence output is
**byte-identical** (same roles, same timestamps), regardless of requested Shot/Beat:

```
A05_motion_but_wrong_motion   vs  S02_G_contradictory_action
  both: start@0  before_change@5667  change@6667  after_change@7667  change@11667  end@14266   → identical ✅
A01_hiking_but_not_difficulty vs  A06_beautiful_but_wrong_beat
  both: start@0  change@6667  change@13000  change@33667  change@36667  end@38867            → identical ✅
```

Only the downstream semantic judgment differs — the selector carries no intent, as
designed.

## Persistence (experiment posture)

- Raw videos remain **private/local** (`evals/assets/private_local/videos/`,
  directory-ignored). Evidence/sampled frames are **derived/private**
  (`evals/assets/private_local/frames/`, directory-ignored). **Neither is
  committed.** Verified: nothing under `private_local/` can be staged.
- Committed from this experiment: the selector tool, the comparison runner, and
  this report. No media, no frames, no result JSON (result JSONs are gitignored and
  kept local for inspection).
- **Production recommendation:** persist lightweight `CaptureEvidence` *metadata*
  only (timestamps/roles/scores), **not** the JPEG evidence frames. The original
  local Moment stays authoritative; frames can be regenerated from it later if Asset
  Understanding needs them.

## Architecture (two equivalent entry paths — designed, not built)

```
LIVE:    AVCaptureSession CMSampleBuffer stream ─┐
                                                 ├─▶ CaptureEvidenceGenerator ─▶ CaptureEvidenceV1
OFFLINE: existing local video (AVAsset)        ─┘   (forward-only, ~3fps, bounded buffer)
```

The OFFLINE path is implemented (this experiment). The LIVE production interface is
**not** implemented — deferred with the rest of CaptureEvidence. Both paths would
share the identical forward selection logic, so the offline eval result transfers.

## Native video — not expanded (as instructed)

Native-video transport was **not** touched. This experiment answered the prior
question first (does CaptureEvidence beat frame sampling? — no), so there is no basis
to expand into native video here.

---

## Gate summary

| # | deliverable | result |
|---|---|---|
| 1 | CaptureEvidenceV1 proposal | §1 — eval-only, intent-independent, not frozen |
| 2 | selector algorithm | §2 — forward-only, ~3fps, bounded buffer, cheap signals |
| 3 | uniform-4 / uniform-6 / CaptureEvidence results | §3 — uniform-4 best/tied on all safety metrics |
| 4 | ≤10s results prominent | §4 — hard band for all arms; CaptureEvidence no temporal gain |
| 5 | failure cases | §5 — 2 false GOT IT from change≠importance (contradiction) |
| 6 | CPU/memory/runtime | §6 — feasible on-device; decode-dominated offline, cheap live |
| 7 | worth implementing (Shot Validation)? | §7 — **No** |
| 8 | part of C4 or deferred? | §8 — **Deferred out of C4** |
| 9 | Asset Understanding implications | §9 — **carry forward there**, re-evaluate |
| 10 | C4B transport recommendation | §10 — **uniform-4 + duration gate** |

**STOP. Awaiting approval before C4B.**
