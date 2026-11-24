# Milestone C4-Lite — Capture Integrity (implementation-ready design)

> **Status: DESIGN — approved direction, NOT implemented. STOP after this doc; bring back
> for review before any implementation.** Supersedes inline semantic Shot Validation for
> the MVP (see `milestone-c4-go-no-go-audit.md`, decision **B: BUILD C4-LITE**).

## What C4-Lite is — and is NOT

C4-Lite is a **capture integrity checker**. After a clip is recorded it answers exactly
one narrow, local question: *is this file an obviously broken capture?* It is **not** a
Shot-success validator.

- ✅ It MAY make a **negative** claim ("this capture looks broken — try again") ONLY for a
  **high-confidence, obvious integrity failure**.
- ❌ It MUST NEVER claim: requested Shot fulfilled, Beat fulfilled, semantic success, or
  Story utility. Those words/ideas do not appear in any C4-Lite output.
- When integrity checks find no obvious failure, the product says **neutral** success
  language — **"Saved" / "Moment added"** — consistent with the frozen Figma/product
  language. It does **not** say "GOT IT" in the semantic sense.
- **No AI. No AWS. No Bedrock. No network dependency.** Pure on-device, local, synchronous.
- **Bias strongly toward ACCEPT/SAVE when uncertain.** A false "try again" on good footage
  is the worst C4-Lite outcome; obvious-failures-only, high confidence, or it saves.

The semantic responsibilities (`execution_match`, `shot_purpose`, `story_utility`,
Shot/Beat contribution, useful-elsewhere reasoning) move to the **future asynchronous
Asset Understanding** (see §10).

---

## 1. Exact local checks

All checks run on-device via AVFoundation + file I/O. Grouped by confidence tier.

### MUST (ship these)
| id | check | signal | source |
|---|---|---|---|
| `file_readable` | captured file exists, is non-empty, and opens as a decodable `AVAsset` with ≥1 video track | boolean | `FileManager` + `AVURLAsset` track load |
| `duration_floor` | clip duration ≥ a low absolute floor AND ≥ a fraction of the shot's target | seconds | `AVAsset.duration` vs `shot.target_duration_seconds` |

These two are robust, unambiguous, and have essentially zero false-reject risk on
legitimate footage. They are the entire guaranteed C4-Lite surface.

### EVALUATE BEFORE ADOPTING (each must EARN its place on T01 — see §8)
| id | candidate check | cheap local signal (no AI) | adopt only if… |
|---|---|---|---|
| `catastrophic_exposure` | severely under/over-exposed | mean luma of N sampled frames near floor/ceiling (e.g. <6 or >249 of 255) across *most* frames | separates T01_E/T01_F from clean + low-light legitimate footage with no meaningful false reject |
| `catastrophic_shake` | unusable camera instability | mean inter-frame luma-shift / simple global motion magnitude above a high threshold on sampled frames | separates T01_D (severe) from T01_C (moderate, legitimate) and legitimate handheld motion |
| `catastrophic_focus` | whole-frame out-of-focus | variance-of-Laplacian (sharpness proxy) far below clip-plausible range on sampled frames | separates T01_G from clean controls, legitimate motion blur, low-light, and intentionally-soft/non-subject areas |

**Do NOT adopt any EVALUATE check merely because the Sonnet model failed that category in
the C4A audit.** Each must independently prove on T01 that it catches the obvious failure
*without* meaningfully false-rejecting legitimate footage. If a simple heuristic cannot
cleanly separate, **do not ship it as a hard gate** — leave that category to the future
Asset Understanding, and let C4-Lite SAVE by default. (Per the standing Stage-1 caution:
avoid building a general CV subsystem.)

### Explicitly OUT of C4-Lite
Subject presence/identity, instruction-following, execution match, shot purpose, beat
fulfillment, story utility, alternative-success, "useful elsewhere" — all semantic, all
async Asset Understanding.

## 2. Thresholds / derivation strategy

Thresholds are **constants in a single config struct**, not model outputs, so they are
inspectable and tunable from the T01 evaluation (§8). Proposed starting points (to be
*confirmed/replaced* by the T01 sweep before shipping — not asserted as final):

- `duration_floor`: `max(ABS_FLOOR_S, target * MIN_FRACTION)` with `ABS_FLOOR_S ≈ 1.0s`
  (a clip under ~1s cannot be a usable Moment) and `MIN_FRACTION ≈ 0.5` (lenient; the old
  semantic design used 0.7 — C4-Lite is more lenient because it is integrity-only).
- EVALUATE checks: each gets a **single high-confidence threshold** chosen on T01 to sit
  comfortably between the obvious-failure cluster and the legitimate cluster, with margin.
  If no such gap exists for a check, that check is **not adopted**.

Derivation is a pure function (mirrors the C4A derivation pattern — testable, model-free):

```
integrity_verdict(file, duration, [sampled signals]) ->
    FAIL(issue)   iff a MUST check fails, OR an ADOPTED EVALUATE check fires with high confidence
    SAVE          otherwise   (default; uncertainty -> SAVE)
```

Only ONE issue is surfaced to the user (the first/most-severe), as a plain sentence.

## 3. Conservative failure semantics

- A FAIL is asserted **only** on a MUST failure or an adopted high-confidence EVALUATE
  failure. Everything else is SAVE.
- FAIL maps to the **existing frozen `ValidationResult`** (02 §20) with **no change to the
  contract**: `{ usable: false, recommendation: "retake", issues: [<code>] }`. SAVE maps to
  `{ usable: true, recommendation: "accept", issues: [] }`. `ValidationResult` already
  carries **no** beat/purpose/story signal by design — a perfect fit for integrity-only.
- `ValidationIssue` codes used by C4-Lite come from the **frozen enum** (02 §20):
  `too_short`, `severe_shake`, `severe_underexposure`, `severe_overexposure`. **C4-Lite does
  NOT use** `subject_missing` or `instruction_not_followed` (both semantic) and does **NOT**
  require the C4 additions (`out_of_focus`/`wrong_subject`/`unusable_motion`) **unless** the
  focus check earns adoption in §8 — in which case add ONLY `out_of_focus`, nothing else.
  **No `skip_beat`.** No material redesign of `ValidationResult`.
- The verdict is **advisory**: retake is always optional; the user may keep/continue
  regardless (preserves the frozen "retake is optional" product rule).

## 4. Moment adoption lifecycle (integrity-only)

```
record clip -> transient CaptureAsset (local temp file)
      -> C4-Lite integrity_verdict
          SAVE  -> persist as a Moment  (status active; NO semantic claim attached)
          FAIL  -> NOT auto-adopted; offer "Try again" (retake replaces temp) OR
                    "Keep anyway" (user override -> persist as Moment)
```

- SAVE persists the Moment with the existing capture→persist path (unchanged from C3/07),
  tagged `shot_id` + `story_project_id`, **without** any beat-fulfillment or shot-success
  flag. Semantic adoption (does this Moment fulfill the requested Shot/Beat, is it useful
  elsewhere) is **deferred to async Asset Understanding** and is not decided at capture.
- FAIL does not pollute Moments: the broken temp capture is not promoted unless the user
  explicitly overrides ("Keep anyway"). Retake replaces the transient temp file (frozen 07
  behavior).
- **Beat progress does NOT update at capture time** (no inline semantic judgment exists to
  drive it). Coverage/beat state becomes a function of settled Asset Understanding later.

## 5. UX states / copy (neutral; no semantic success language)

Reuses the frozen Screen8Validation surface, re-labeled to integrity semantics. **Two
states** (not three — the semantic KEEP + ONE MORE state is gone with the semantic model):

```
record stops
   ↓  (local, synchronous — target < ~0.5s, no spinner needed; no network)
┌────────────────────────────┬──────────────────────────────────────┐
│  SAVE (default)            │  FAIL (high-confidence integrity only) │
│  ✓ "Saved."  / "Moment     │  ↺ "That one didn't record well —      │
│     added."                │     let's try again."                  │
│  → continue                │  reason (plain, integrity only):       │
│                            │   "too short" / "too dark" / "too      │
│                            │    bright" / "too shaky" [/ "out of    │
│                            │    focus" if adopted]                  │
│                            │  [Try again]   [Keep anyway]           │
└────────────────────────────┴──────────────────────────────────────┘
```

Copy rules: SAVE copy is **neutral** ("Saved" / "Moment added") — never "GOT IT", never
"we got the shot", never any claim the requested moment/beat was captured. FAIL copy names
only the **physical** problem, never a semantic one ("too dark", not "this doesn't show the
departure"). Final wording tracks the frozen Figma/product language.

## 6. Local architecture

```
Capture (07, AVCaptureMovieFileOutput) -> temp file
        ↓
CaptureIntegrityChecker (NEW, local, sync, no network)
  ├─ file_readable        (FileManager + AVURLAsset track load)
  ├─ duration_floor       (AVAsset.duration)
  └─ [adopted EVALUATE]   (AVAssetImageGenerator: sample K frames @ small size;
                           mean-luma / luma-shift / variance-of-Laplacian — the same
                           cheap primitives proven in the C4A sampler/CaptureEvidence tools)
        ↓ pure function
IntegrityVerdict { save|fail, issue? }  ->  ValidationResult (frozen contract, unchanged)
        ↓
SAVE -> Moment persist (existing path)   |   FAIL -> retake/keep-anyway UX
```

- A single `CaptureIntegrityChecker` type (Swift, device) + a pure
  `integrity_verdict(...)` function. No engine process, no gateway, no boto3, no HTTP.
- Frame sampling reuses the already-proven cheap primitives (AVFoundation decode + luma /
  Laplacian) from `evals/shot_validation/tools/` — but runs **on-device at capture**, not
  in the eval harness. K is small (e.g. 3–5 frames) and only computed for adopted checks.
- Backend: **no new endpoint.** The old planned `POST /v1/shot-validation` is **not built**.
  C4-Lite is entirely client-side; `ValidationResult` is produced locally. (If a server
  record of integrity verdicts is ever wanted, it rides the existing persistence path — not
  a semantic validation service.)

## 7. Tests

- **Pure-function unit tests** for `integrity_verdict`: exhaustive over
  {MUST-pass/fail} × {each adopted EVALUATE pass/fail} × {uncertain → SAVE}, asserting
  SAVE-by-default and that FAIL fires only on the defined conditions. (Mirrors the C4A
  `test_derivation.py` style — model-free, fast.)
- **Threshold/config tests**: `duration_floor` boundary cases (just under/over floor and
  target fraction).
- **No-semantic-claim test**: assert C4-Lite output never contains beat/shot/story fields
  and SAVE copy is from the neutral set only.
- **T01 corpus harness test** (§8): the heuristic-evaluation runner is itself a committed,
  repeatable test that re-asserts each adopted check's catch-rate and false-reject bar.
- **Device integration** (manual, §9): the physical-iPhone acceptance gate.

## 8. T01 heuristic-evaluation plan (gates adoption of every EVALUATE check)

Goal: decide — **empirically, before shipping** — which EVALUATE checks earn a hard gate.

- **Dataset:** the T01 technical-controls set (private corpus) + a legitimate-footage
  control set drawn from the semantic scenarios (clean, moderate-shake, low-light,
  motion-blur, intentionally-soft/non-subject). Specifically compare each candidate against:
  - `catastrophic_focus` → T01_G_out_of_focus **vs** clean controls, legitimate motion
    blur, low-light footage, intentionally-soft/non-subject areas.
  - `catastrophic_shake` → T01_D_severe_shake **vs** T01_C_moderate_shake + legitimate
    handheld.
  - `catastrophic_exposure` → T01_E/T01_F **vs** clean + legitimate low-light.
- **Procedure:** a local, no-AI runner samples K frames per clip, computes the candidate
  signal, and reports the signal distribution for failure-cluster vs legitimate-cluster.
- **Adoption bar:** adopt a check as a hard gate **only** if there is a clear threshold gap
  that catches the obvious failures with **zero or near-zero** false rejection of
  legitimate footage. If the clusters overlap, **do NOT adopt** — SAVE by default and leave
  that category to Asset Understanding.
- **Output:** a short adoption report (which checks adopted, chosen thresholds, measured
  false-reject rate) committed alongside the implementation. Duration + file-readable are
  pre-adopted (MUST); they still get boundary tests.

## 9. Physical-iPhone acceptance gate (close C4-Lite)

Demonstrate on a real device (an agent cannot operate the camera — this is a user/manual
gate):

1. Normal good capture → **"Saved" / "Moment added"**, Moment persists, flow continues. No
   semantic claim shown.
2. Deliberately too-short capture → **FAIL "too short" → Try again**; retake replaces temp;
   no broken Moment persisted.
3. (If adopted) deliberately dark / shaky / out-of-focus capture → correct high-confidence
   FAIL with the right plain reason; **"Keep anyway" override** persists if the user insists.
4. Legitimate handheld / low-light / soft-background capture → **SAVE** (NOT false-rejected)
   — the leniency bar holds on real footage.
5. No "GOT IT"/semantic-success wording appears anywhere; SAVE copy is neutral.
6. Entirely offline (airplane mode) → C4-Lite still works (no network dependency).
7. Relaunch/persistence correct; C1–C3 behavior remains green; capture latency unchanged
   (local check adds no perceptible delay, no spinner).

## 10. What explicitly moved to Asset Understanding (async)

These are **removed from the capture hot path** and become the future asynchronous Asset
Understanding design (NOT built now):

- `execution_match` (matched / deviated / absent / contradicted)
- `shot_purpose` (fulfilled / partial / unfulfilled / alternative_fulfilled)
- `story_utility` (none / useful_elsewhere / strong_elsewhere)
- Shot/Beat contribution and **BeatProgress** derivation
- "useful-elsewhere" reasoning and semantic Moment adoption
- the three-state GOT IT / KEEP + ONE MORE / TRY AGAIN surface
- the Director loop's consumption of a semantic validation result (future Director consumes
  **settled** Asset/Moment Understanding + Story coverage, not an inline guess — §05
  supersession note)

**Preserved as research inputs for that work (do NOT delete):** the C4A corpus
(`evals/assets/private_local/`), harness + runner, versioned prompt, 4-axis
`ShotValidationJudgment` model + derivation (`packages/shot_validation/`), the four-model
comparison (`milestone-c4a-shot-validation-eval-report.md`), the CaptureEvidence experiment
(`milestone-c4a2-capture-evidence-report.md` — re-evaluate for offline temporal indexing
there), and the GO/NO-GO audit (`milestone-c4-go-no-go-audit.md`).

---

## Open items for review (bring back before implementing)

1. Confirm `ABS_FLOOR_S` (~1.0s) and `MIN_FRACTION` (~0.5) for `duration_floor`, or set from
   a quick T01/scenario duration scan.
2. Approve the §8 adoption bar (zero/near-zero false-reject) and whether to run the T01
   heuristic sweep as part of C4-Lite implementation or as a pre-step.
3. Confirm the neutral SAVE copy ("Saved" vs "Moment added") against the frozen Figma.
4. Confirm the two-state surface (SAVE / FAIL) reuses Screen8Validation acceptably, or
   whether SAVE should be silent (no screen) with only FAIL interrupting.

**STOP. No implementation. No Asset Understanding. Awaiting review of this design.**
