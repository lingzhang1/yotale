# C4L-A — Local heuristic adoption report (no AI)

Status: **C4L-A complete.** No architecture/product issue found → proceeding to C4L-B.
Date: 2026-10-05. All measurements local (AVFoundation), no AI/AWS/network.
Tool: `evals/shot_validation/tools/integrity_signals.swift`; harness
`evals/run_integrity_heuristics.py`; raw `evals/results/c4l_a_heuristics.json`.

Adoption bar (approved): a hard, interruptive gate ships ONLY with a **clear threshold
gap** and **zero/near-zero false rejection of legitimate footage**. Overlap → do NOT
ship; SAVE by default. Shipping only `file_readable` + `duration` is acceptable.

## 1. Duration distribution + threshold

68 fixtures: **min 0.47s · p05 2.03s · p10 3.63s · p25 6.53s · median 12.69s · max 154.13s.**

- Clips **< 1.0s: exactly two, both 0.47s** (the `*_too_short` controls).
- Next clip up is **1.37s**, then 2.03s — a clean gap between the catastrophic-short pair
  and everything else.

**Decision — ADOPT a catastrophic absolute duration floor at `ABS_FLOOR_S = 0.8s`.** It
isolates the two obviously-broken 0.47s clips with a wide margin to the next legitimate
clip (1.37s), so zero false rejection. **Do NOT gate on `target_duration_seconds`** — a
clip shorter than the Director's requested target is still a usable Moment; C4-Lite asks
only "is this obviously broken?", not "did it meet the requested length." The ~0.8–1.0s
hypothesis is confirmed at the low end; **0.8s** is chosen (strictly below 1.37s with
margin, strictly above 0.47s).

## 2. Exposure (`catastrophic_exposure`)

mean-luma of 8 sampled frames (0–255); `p_dark` = fraction < 35, `p_bright` = fraction > 225.

| group | mean_luma | p_dark | p_bright |
|---|---|---|---|
| **underexposed (fail)** T01_E | **31.7** | **1.00** | 0 |
| overexposed (fail) T01_F | 142.1 | 0 | 0 |
| legit low-light (S08 ×3) | 89–135 | 0 | 0 |
| legit bright outdoor (S03_B/S04_C/S06_G/S06_E) | 132–155 | 0 | 0 |
| clean (T01_A/H) | 82–114 | 0 | 0 |

- **Underexposure: clean gap** — fail mean_luma 31.7 (every frame p_dark) vs a legitimate
  low-light **floor of 82**. A gate like `mean_luma < 50 AND p_dark ≥ 0.8` separates with
  wide margin. **Candidate — but on n=1 failure sample.**
- **Overexposure: NO gap — REJECT.** The "overexposed" control (mean 142) is **darker than
  legitimate bright-outdoor footage** (148–155); `p_bright` is 0 for every clip including
  the fail. A mean-luma/p_bright overexposure gate would false-reject legitimate landscapes.

**Decision — do NOT ship overexposure.** Underexposure has a clean gap but **thin evidence
(1 failure clip)**; per "do not tune thresholds merely to make a check ship," I recommend
**NOT shipping it as a required MVP gate either**, and instead listing it as an
*optional, conservative* gate (`mean_luma < 50 AND p_dark ≥ 0.8`) the user may enable —
it cannot false-reject anything in the current corpus, but one sample is too thin to make
it a default interruption. **MVP default: no exposure gate.**

## 3. Shake (`catastrophic_shake`)

mean absolute inter-frame luma shift (0–1).

| group | luma_shift_mean | luma_shift_max |
|---|---|---|
| **severe shake (fail)** T01_D | **0.13** | 0.15 |
| legit moderate shake T01_C | 0.10 | 0.15 |
| legit handheld motion (S05_A/S06_D/S02_F) | 0.02–0.15 | 0.05–0.20 |

**NO gap — REJECT.** Legitimate handheld motion reaches **0.15**, *above* the severe-shake
clip's 0.13. A whole-frame luma-shift proxy cannot tell "unusable shake" from "legitimate
walking/handheld motion" — the exact confound the Stage-1 caution warned about. Separating
them would need real motion stabilization analysis (a CV subsystem), which is out of scope.
**Decision — do NOT ship shake. Leave to async Asset Understanding.**

## 4. Focus (`catastrophic_focus`)

variance-of-Laplacian sharpness proxy (higher = sharper).

| group | sharpness_median | sharpness_min |
|---|---|---|
| **out of focus (fail)** T01_G | **291.8** | 289.1 |
| clean (T01_A/H) | 215–385 | 211–357 |
| legit low-light (S08 ×3) | 234–333 | 212–324 |
| legit handheld motion | 43–517 | 7–288 |

**MASSIVE overlap — REJECT (worst of the three).** The out-of-focus clip's sharpness
(291.8) sits in the **middle** of the legitimate range; a legitimate handheld clip scores
as low as **43** (motion blur / low texture), far "blurrier" by this metric than the
genuinely out-of-focus clip. A variance-of-Laplacian gate would false-reject legitimate
soft/low-texture/motion-blur footage while *missing* the actual out-of-focus clip.
**Decision — do NOT ship focus.** This matches the GO/NO-GO finding that focus is genuinely
hard; it belongs to async Asset Understanding (semantic), not a local gate.

## 5. Adoption summary

| check | verdict | reason |
|---|---|---|
| `file_readable` | **ADOPT (MUST)** | unambiguous; broken/unreadable file is objectively unusable |
| `duration` (abs floor 0.8s) | **ADOPT (MUST)** | clean gap: fails 0.47s pair, next legit clip 1.37s |
| `catastrophic_exposure` (under) | **DO NOT SHIP as default** (optional, conservative) | clean gap but n=1 failure evidence — too thin to default-interrupt |
| `catastrophic_exposure` (over) | **REJECT** | fail darker than legit bright outdoor; no gap |
| `catastrophic_shake` | **REJECT** | legit handheld ≥ severe-shake value; no gap |
| `catastrophic_focus` | **REJECT** | fail mid-range; legit motion-blur far lower; massive overlap |

**C4-Lite MVP ships exactly `file_readable` + `duration`.** This is the "trustworthy
checks only" outcome anticipated in the brief. The two rejected categories (shake, focus)
and the deferred overexposure/underexposure semantics are handed to the future async Asset
Understanding, not forced into a local gate.

**Evidence limitation (stated honestly):** T01 provides one clip per failure category.
Duration (2 fail clips, wide gap) and the shake/focus REJECTs (legitimate clusters clearly
overlap/exceed, which n does not change) are robust conclusions. The underexposure
*candidate* rests on one failure clip, which is why it is not a default gate. If the user
later wants exposure as a gate, collect ≥3–5 catastrophic-exposure clips and re-run this
harness before adopting.

## 6. No architecture/product issue found → continue to C4L-B
The sweep confirms the C4-Lite shape: a tiny deterministic gate (file + duration), SAVE by
default, no CV subsystem. Proceeding to implement `CaptureIntegrityChecker` with exactly
these two checks.
