# Milestone C4-Lite — Completion report (implementation)

Status: **C4L-A, C4L-B, C4L-C complete. STOPPED before C4-Lite close (C4L-D is the
user-run physical-iPhone gate). Asset Understanding NOT started.**
Date: 2026-10-05. No AI / no AWS / no Bedrock / no network added to the capture path.

## 1. Duration distribution + threshold

68-fixture scan (local, `integrity_signals`): min 0.47s · p05 2.03s · p10 3.63s · p25
6.53s · median 12.69s · max 154.13s. **Only two clips < 1.0s (both 0.47s); next clip 1.37s.**
**Adopted catastrophic floor = `minDurationSeconds = 0.8s`** — isolates the obviously-short
pair with margin to 1.37s, zero false rejection. Not gated on `target_duration_seconds`
(short-of-target is still a usable Moment). Full detail: `milestone-c4l-a-heuristic-adoption-report.md`.

## 2. Heuristic distributions (no-AI local signals)

| candidate | failure signal | legitimate signal | gap? |
|---|---|---|---|
| exposure (under) | mean_luma 31.7, p_dark 1.0 | low-light floor 82 | clean gap (but n=1 fail) |
| exposure (over) | mean_luma 142 | bright outdoor 148–155 | **NO gap** (fail darker than legit) |
| shake | luma_shift 0.13 | handheld up to 0.15 | **NO gap** |
| focus | sharpness 291.8 | legit 43–517 (motion-blur as low as 43) | **massive overlap** |

## 3. Checks adopted / rejected and why

- **ADOPTED (MUST):** `file_readable`, `duration` (0.8s floor). Robust, unambiguous, zero
  false-reject.
- **REJECTED:** overexposure (fail darker than legit outdoor), shake (legit handheld ≥ severe
  value), focus (fail mid-range; legit motion-blur far lower — the worst overlap).
- **NOT a default gate:** underexposure — clean gap but a single failure sample; offered as
  an optional conservative gate only, not shipped on by default. **Did not tune thresholds
  to force any check to ship.**

**C4-Lite MVP ships exactly `file_readable` + `duration`** — the anticipated
trustworthy-checks-only outcome. Shake/focus/exposure semantics are deferred to async Asset
Understanding.

## 4. False-reject evidence

No adopted check rejects any legitimate clip in the corpus: duration floor 0.8s < every
legitimate clip (min legit 1.37s); file_readable only fires on an unreadable/empty/
non-video file. The rejected heuristics were rejected *because* they would have false-rejected
legitimate low-light / handheld / motion-blur / bright-outdoor footage (§2).

## 5. Files changed

**story repo (iOS + eval tooling):**
- `apps/ios/Story/Story/Media/Camera/CaptureIntegrityChecker.swift` (NEW) — pure local
  checker; `CaptureIntegrityVerdict` (source of truth: `.save` / `.fail(issue)`);
  `CaptureIntegrityIssue` (physical reasons); `CaptureIntegrityConfig` (0.8s floor);
  frozen-`ValidationResult` adapter.
- `apps/ios/Story/StoryTests/CaptureIntegrityCheckerTests.swift` (NEW) — unit/boundary/
  adapter/no-semantic-claim tests.
- `apps/ios/Story/Story/Features/SceneScan/SceneScanFlowView.swift` (MOD) — `handleCapture`
  now runs the integrity gate; SAVE path (persist + "Moment added" + continue), FAIL sheet
  (physical reason + Try again / Keep anyway).
- `evals/shot_validation/tools/integrity_signals.swift` (NEW) — no-AI signal extractor (C4L-A).
- `evals/run_integrity_heuristics.py` (NEW) — adoption harness (C4L-A). Result
  `evals/results/c4l_a_heuristics.json` is gitignored (local).

**specs repo:** `milestone-c4l-a-heuristic-adoption-report.md` (NEW); earlier this turn the
C4-Lite spec reconciliation (`08`, `milestone-c4-shot-validation-design`, `05`,
`ui-capability-matrix`, `mvp-build-plan`, `13`) + `milestone-c4-lite-capture-integrity-design.md`.

**⚠️ Xcode project step (user):** the two new Swift files
(`CaptureIntegrityChecker.swift`, `CaptureIntegrityCheckerTests.swift`) must be added to
the `Story` app target and `StoryTests` target respectively in Xcode before they compile
(same manual step as `StoryContracts.swift`). I do not hand-edit the `.pbxproj`.

## 6. Tests

`CaptureIntegrityCheckerTests` (XCTest, deterministic, offline):
- pure derivation truth table (save / unreadable-wins / too-short);
- duration boundaries (0.79 fail, 0.80 save, 1.37 save, lenient 1.0 save, custom floor);
- adapter mapping (save→usable/accept/[]; too_short→retake/[.tooShort]; unreadable→retake/
  **no borrowed semantic code**/[]);
- no-semantic-claim invariant (user reasons contain no shot/beat/purpose/story/fulfil words);
- verdict accessors.
Both new Swift files pass `swiftc -parse` (full macro typecheck is Xcode-only in the sandbox).
Run in Xcode after adding to targets: `⌘U` on `StoryTests`.

## 7. UX behavior

- **SAVE (default):** no validation screen, no spinner, no Continue button — a brief
  neutral **"Moment added"** capsule, then the flow dismisses to normal Story flow.
- **FAIL (obvious integrity only):** a medium sheet with the **physical** reason ("That one
  was too short to use." / "That one didn't record properly.") and **[Try again]** (discard
  held capture, reopen camera) / **[Keep anyway]** (persist the held capture as a Moment).
  Retake is optional. No "GOT IT", no semantic success language anywhere.
- **BeatProgress is NOT updated**; no semantic Director NEXT is invoked.

## 8. Performance

The gate is local and synchronous: a file-attributes read + one `AVURLAsset` duration/track
load — no frame sampling in the shipped checks (exposure/shake/focus were not adopted), no
network. Expected sub-10ms, no perceptible capture delay, works offline. (The C4L-A signal
extractor that DID sample frames was eval-only and is not on the capture path.)

## 9. Architecture deviations

None material. The checker is a standalone local type; no new endpoint
(`POST /v1/shot-validation` deliberately NOT built); the frozen `ValidationResult` contract
is unchanged (adapter only). One honest mapping choice: the frozen `ValidationIssue` enum has
no "unreadable file" code, so the adapter emits `usable:false/retake` with an **empty** issues
list rather than borrowing a semantic code — `CaptureIntegrityVerdict` remains the source of
truth.

## 10. Exact physical-iPhone checklist (C4L-D — user runs on device)

Camera requires a physical device (unavailable in Simulator; an agent cannot operate it).
Build to a real iPhone, open a Story → DIRECT scan → "Let's shoot", then:

1. **Normal capture** — record a normal ~4s clip → **"Moment added"** appears briefly, flow
   returns to Story; the Moment is present in Story Home. No "GOT IT"/semantic wording.
2. **Accidental very-short capture** — tap record then stop almost immediately (< 0.8s) →
   **FAIL "That one was too short to use."** with **[Try again] [Keep anyway]**. No Moment
   persisted yet.
3. **Adopted-heuristic failures** — N/A for shipped gates beyond duration (exposure/shake/
   focus were NOT adopted). Confirm a dark / shaky / slightly-soft but **otherwise valid**
   clip is **SAVED** (proves we did not ship an over-aggressive gate). (If the optional
   underexposure gate is later enabled, add: a near-black clip → FAIL "too dark".)
4. **Legitimate near-boundary footage (leniency)** — record a ~1.4s clip (just above floor)
   → **SAVED** (not rejected); record a legitimate low-light and a legitimate handheld-motion
   clip → both **SAVED**.
5. **Keep anyway** — on the step-2 FAIL, tap **Keep anyway** → the short clip persists as a
   Moment (user override), flow continues.
6. **Airplane mode** — enable airplane mode, repeat step 1 → capture + integrity + save still
   work end to end (no network dependency).
7. **Persistence / relaunch** — force-quit and relaunch → saved Moments (incl. the Keep-anyway
   one) are still present; Story status unchanged.
8. **C1–C3 regression** — scan → recommendation → shoot still works; Create My Story (mock)
   still works; Complete/Reopen still works; existing-media add still works. No regression.

## 11. Capability-matrix changes

`ui-capability-matrix.md` (done earlier this turn): the semantic **Shot Validation
(success/retry)** and **Validation-driven retry** rows are struck through and deferred to
async Asset Understanding; a new **Capture integrity check (C4-Lite)** row records the
local-only integrity gate reusing Screen8Validation for the FAIL surface, neutral
"Moment added" on SAVE, no semantic claim.

## 12. Explicitly deferred to Asset Understanding (NOT built)

execution_match, shot_purpose, story_utility, Shot/Beat contribution, BeatProgress
derivation, useful-elsewhere reasoning, the three-state semantic surface, and the Director
loop's consumption of a semantic validation result. All C4A research
(corpus/harness/prompt/4-axis model/model comparison/CaptureEvidence/GO-NO-GO audit) is
preserved as inputs for that work — nothing deleted or repurposed.

**STOP. C4L-D is yours to run on the device. Asset Understanding not started.**
