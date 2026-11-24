# Milestone C3B — Real Director Experience: Completion Report

**Date:** 2026-10-02
**Stage:** C3B (put the evaluated Director in front of a user on a physical iPhone).
**Status:** Backend deployed + live-verified; iOS DIRECT slice built + parse-clean.
**Physical-iPhone acceptance gate (§12): PENDING — requires the user to run it on
device (an agent cannot operate the camera/hardware).** No Shot Validation (C4).

---

## 1. Files changed
**Backend**
- `apps/api/app/deps.py` — Director default corrected to `amazon.nova-pro-v1:0`
  (was a gated Anthropic id); config via `STORY_DIRECTOR_MODEL`.

**iOS** (`apps/ios/Story/Story`)
- `Data/Contracts/StoryDirectorService.swift` — NEW. JSON `POST /v1/director/initialize`,
  decode `DirectorOutputDTO`, recoverable 503, `CreativeIntentContractDTO(from: StoryModel)`.
- `Data/Contracts/StoryContracts.swift` — added `DirectorOutputDTO` envelope.
- `Features/SceneScan/SceneScanFlowView.swift` — REWRITTEN to the consumer flow.
- `Features/SceneScan/DirectorDebugPanel.swift` — NEW, DEBUG-only feedback capture.
- `Features/Capture/ShootMomentView.swift` — reduced to a thin launcher.
- `StoryTests/DirectorDTOTests.swift` — NEW (envelope decode + intent mapping).
- `.gitignore` — excludes device test media (local-first).

Commits: story `d164321` (C3B), `059fa7e` (C3A engine); story-specs `570813f` (C3A report).

## 2. Deployed endpoint(s)
`POST /v1/director/initialize` live on App Runner
`https://ydmju5wdps.us-east-1.awsapprunner.com` (acct 989088054552, us-east-1).
`/v1/director/next` is deployed too (used by the C4 loop later; C3B uses initialize).
Architecture preserved end to end: **DirectorEngine → ModelGateway → configured
Director model**. No provider fallback/routing built (per scope).

## 3. Final physical-iPhone flow (as implemented)
Creative Direction → CreativeIntent (real, C1) → Story → Shoot a Moment →
"Show me what's around you" → scan → "Looking at your scene…" (SceneUnderstanding,
C2) → "Finding the best way to capture this…" (Director) → **ONE** recommendation
(concept title + plain-language instruction + light subject/you/hold guidance) →
Open Camera (real capture) → Moment created → return to Story. Back/Cancel/Rescan
at each step. After capture = existing accepted-capture behavior (no validation).

## 4. Director model / prompt / schema version
Model `amazon.nova-pro-v1:0`; `prompt_version=story_director/v1`;
`schema_version=story_director.envelope/1`. Config-switchable to Claude Sonnet 4.5
via `STORY_DIRECTOR_MODEL` once the account's Anthropic use-case form is confirmed
(it is intermittently gated — a 503 "use case details not submitted" was observed
live, which is why Nova Pro is the default, not Claude).

## 5. Real Director latency
`/v1/director/initialize` on Nova Pro: ~2.8–4.9s (5 live calls). Acceptable for a
once-per-scan interactive step behind an explained "Finding the best way…" state.

## 6. Scan → recommendation total latency
Instrumented client-side (`scanToRecommendationMs`, shown in the DEBUG panel) =
SceneUnderstanding + Director. Director leg alone ~3–5s live; the full leg is
measured on-device during the acceptance run. Both legs show a labelled consumer
state, never an unexplained spinner.

## 7. Scenarios tested (live backend; device run pending)
Verified against the DEPLOYED endpoint:
- **A. TMB × home/backpack** → concept "Preparation for an 8-day TMB hike", rec
  "photo of the red backpack … symbolizing the start of the journey". Connects the
  ordinary room to the journey; no invented mountains; backpack is narrative, not
  product footage; executable. ✅
- **B. Same home × ordinary-day intent** → "A Day in the Life" — materially
  different concept from A on the same scene. Intent sensitivity. ✅
- **C. Weak scene (blank wall)** → "Cinematic and Moody in an Empty Room", minimal
  wide shot of the wall — did NOT hallucinate rich opportunities. ✅
- **D. Constrained hallway** → rec focuses on the narrow space + coats; respects
  limited operator space. ✅
- **E. Outdoor park, energetic** → "Energetic Day Out", uses lawn/trees/path +
  open-space movement. Scene sensitivity. ✅

## 8. Representative Director outputs
A: beats {preparation, anticipation}, rec = backpack-as-start-of-journey.
B: concept "A Day in the Life", 3 beats/3 shots.
C: 2 beats, wide shot of the plain wall.
D: 2 beats, hallway/coats within the narrow space.
E: 2 beats / 3 shots, park energy with path movement.

## 9. User-facing UX implemented
One strong recommendation (concept title + instruction). Plain-language guidance
rows (Subject / You / Hold ~Ns) with `camera_motion` translated out of jargon
("static" → "hold still", "pan" → "slowly turn the phone"). No raw CreativeIntent,
SceneUnderstanding, environment tags, operator_space, motion/composition
opportunities, beats, DirectorState, or JSON in the consumer path — all behind
`#if DEBUG`. Consumer sees Story's conclusion, not its pipeline.

## 10. UX problems discovered
- The pre-C3B scene-observations debug screen overlapped the Dynamic Island (seen
  in the 10-02 recording). Resolved implicitly: that screen is no longer the
  consumer path; the new recommendation screen is a safe-area-respecting ScrollView.
- Open on-device: confirm the recommendation reads well at a glance and the
  guidance rows aren't redundant with the instruction — a device-run observation.

## 11. Director failures discovered
None at the behavior level across the 5 live scenarios. One infrastructure failure
found + fixed: the first deploy defaulted to the gated Anthropic model → 503; fixed
to Nova Pro. The 503 path is correct (recoverable, no fabrication) and is unit-tested.

## 12. Regression fixtures added
C3A's 8 fixtures remain. No NEW regression fixture added yet — the live scenarios
all passed, and fixtures should come from REAL device failures (§9/§14), captured
via the DEBUG feedback panel during the acceptance run. Conversion path is ready
(panel writes the exact fixture shape).

## 13. Debug feedback mechanism status
Implemented (`DirectorDebugPanel`, DEBUG only). Good / Bad direction with Bad
classification (generic / doesn't use scene / doesn't match intent / hard to shoot
/ physically infeasible / unsafe / confusing / other). Writes a self-contained JSON
case (CreativeIntent, SceneUnderstanding, Director output, model, prompt_version,
schema_version, failure label, beat/shot counts, latency) to
`Documents/director_feedback/`. Does NOT retain scene frames.

## 14. Beat/Shot count observations (§10)
Live counts: A 2/2, B 3/3, C 2/2, D 2/2, E 2/3. No runaway; the C3A "too many beats
on vague intent" tendency did not recur meaningfully (B, the vaguest intent, was the
highest at 3/3). Not patching on a handful of examples — the DEBUG panel surfaces
beat/shot counts so the device run can confirm whether requested capture ever feels
excessive before any general prompt change.

## 15. Test results
Backend: 98 pytest pass (Director engine + endpoint incl. 503 + body validation;
C1/C2 unaffected). iOS: `swiftc -parse` clean on all changed files; `DirectorDTOTests`
added (envelope decode, shot→beat integrity, intent mapping). Full iOS XCTest run
happens in Xcode on device/simulator during acceptance.

## 16. Architecture deviations
None. Contracts and the Concept→Beats→Shots + DirectorDecision model are unchanged.
`DirectorOutput` is an engine/transport envelope composed from the frozen contracts,
not a new contract. The Xcode project is filesystem-synchronized (Xcode 16), so new
Swift files are auto-included — the earlier C1 "add StoryContracts.swift to Xcode"
open item was never actually required.

## 17. Recommendation for C4
Proceed to C4 (real Shot Validation + validation-driven Director loop) only after the
§12 device gate passes. C4 wires `/v1/director/next` (already deployed) with real
`ValidationResult` from captured video, drives BeatProgress, and exercises
retry_shot/capture_shot/create_now adaptively. Keep the DEBUG feedback panel running
through C4 to grow the eval corpus from real captures.

---

## Physical-device acceptance (§12) — PENDING, needs the user
Steps 1–6 (create Story, real CreativeIntent, scan, real SceneUnderstanding, Director
runs on real intent+scene) are verified via the live backend. Steps 7–13 (one useful
recommendation understood without filmmaking expertise → camera → record → Moment →
survives relaunch, across several real scenes) require running the build on a physical
iPhone. The build is ready; the device run is the user's.
