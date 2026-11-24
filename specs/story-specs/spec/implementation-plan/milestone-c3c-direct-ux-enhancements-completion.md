# Milestone C3C — DIRECT UX enhancements (completion report)

Status: **Implemented (Skip Scan + ephemeral alternatives). Server tests green; iOS parses
clean. STOPPED for the physical-iPhone gate. Asset Understanding NOT started. C4-Lite
untouched. DIRECT lifecycle not redesigned.**
Date: 2026-10-05. Eval: `milestone-c3c-direct-ux-enhancements-eval.md` (PASSED).

## What shipped

### 1. Skip Scan (intent-only DIRECT)
- Intro screen gains a secondary **Skip Scan** action under primary **Start Scan** (Cancel
  stays). Tapping it calls the Director with **`scene_understanding = null`** (the request
  omits the field) — no Scene Understanding call, no fabricated SceneUnderstanding object.
- Prompt gains a **SKIP-SCAN / NO SCENE** clause: with a null scene the Director must still
  return an actionable `capture_shot` grounded ONLY in intent + the user, environment-
  agnostic, inventing no surroundings, and must NOT `rescan_scene`; plus a **one-beat/one-
  shot cap** so a null scene cannot over-plan.

### 2. Ephemeral alternatives (one call, show one)
- ONE Director call now also returns up to **3 ranked `candidates`** (alternative
  decisions) in the engine response envelope. `candidates[0] == decision`. The UI shows
  **only candidate #1**; **Try another idea** advances #1→#2→#3 **instantly, locally — no
  new Director call, no thinking state, no rescan**; the button hides on the last candidate
  (no endless loop). **Let's shoot** opens the camera for the currently displayed candidate.
- **Anti-over-planning (enforced):** `candidates` are ephemeral response/UI data, NOT
  persisted into StoryPlan, NOT additional required captures. `plan.beats`/`plan.shots`
  stay minimal; a server guard rejects output where candidates[0] ≠ primary decision, and
  the safety guard scans every candidate shot.

## Architecture (smallest change; no canonical contract change)

- **Engine envelope only:** `DirectorOutput.candidates: list[DirectorDecision]` (default
  `[]`). `scene_understanding` made **optional/nullable** through the engine + the
  `/v1/director/initialize` request model. **No `StoryPlan`/`Shot`/`Beat`/`DirectorDecision`
  canonical contract was modified** — a null scene is simply "no scene provided", and
  candidates reuse the existing frozen `DirectorDecision` shape. The selected candidate IS a
  Shot and maps into the existing capture path unchanged.

## Files changed

**story repo — server:**
- `packages/story_director/__init__.py` — `DirectorOutput.candidates`; nullable scene in
  `initialize`/Protocol/`build_initialize_request` + Skip-Scan request marker; candidate id
  minting; integrity guard (candidates[0]==primary, candidate shot→beat, no plan inflation);
  safety guard extended over candidate shots; `_CANDIDATES_INSTRUCTION`.
- `prompts/story_director/v1/system.md` — SKIP-SCAN / NO SCENE clause (+ one-beat/one-shot
  cap). Additive; scanned-scene behavior unchanged.
- `apps/api/app/main.py` — `DirectorInitializeRequest.scene_understanding: dict | None`.
- `apps/api/tests/test_story_director_engine.py` — +5 tests (null scene; candidates minted +
  no plan inflation; zero-candidates ok; candidates[0] mirror; unsafe candidate rejected).

**story repo — iOS:**
- `Data/Contracts/StoryContracts.swift` — `DirectorOutputDTO.candidates` (decode-optional,
  defaults []).
- `Data/Contracts/StoryDirectorService.swift` — `sceneUnderstanding` optional; body omits it
  on Skip Scan.
- `Features/SceneScan/SceneScanFlowView.swift` — Skip Scan button; nullable scene through
  FlowState/runDirector; `candidateIndex`; recommendation view shows current candidate;
  Try another idea (local cycle, hidden on last); Let's shoot uses current candidate; DEBUG
  scene panel guarded to non-null scene.

**story repo — eval:** `evals/run_direct_ux_enhancements.py` (null-scene + candidates eval).

**specs repo:** `milestone-c3c-direct-ux-enhancements-eval.md`, this report, and
`ui-capability-matrix.md` (Skip scan + Try another idea → IMPLEMENTED (C3C)).

## Tests

- Server: full `apps/api/tests` suite green (58), incl. the 5 new Director tests. Pure/fake-
  gateway — no network.
- iOS: all modified/new files pass `swiftc -parse` (full typecheck is Xcode-only in sandbox).
- Eval (live Opus, 5 fixtures × scanned/null × single/candidates): null-scene 10/10
  actionable `capture_shot`, 0 environment fabrications, no over-planning (null = 1 beat/1
  shot), candidate uniqueness 3/3, scanned unchanged, 100% structured validity.

## Performance

- The ONE Director call that produces candidates costs ~+5s vs a single recommendation
  (p50 ≈17s vs ≈12s) — a one-time cost at recommendation time. **Try another idea is
  instant** (local index change). No extra network, no per-cycle model call.

## Architecture deviations

None beyond the additive envelope field + nullable scene. No canonical contract change (so
no STOP-and-explain was triggered). No new endpoint.

## Physical-iPhone acceptance checklist (user runs on device)

Build to a real iPhone, open a Story → DIRECT:

1. **Start Scan** still works exactly as before (scan → recommendation → shoot).
2. **Skip Scan** (new secondary button) bypasses the scan and reaches a Director
   recommendation.
3. Skip-Scan recommendation does **not** invent visible surroundings (no "the window / your
   backpack / the trail" — it talks about you/your intent, e.g. "Capture yourself getting
   ready to begin").
4. A normal **scanned** recommendation remains scene-specific (mentions real scene elements).
5. Recommendation **#1 quality** has not regressed vs today.
6. **Try another idea** switches instantly — **no** second ~10s thinking state, no rescan.
7. **#2** is meaningfully different from #1 (different action/angle, not a reword).
8. **#3** is meaningfully different from #1/#2; after #3 the **Try another idea** button is
   gone (no endless loop).
9. **Only one** recommendation is visible at a time.
10. **Let's shoot** uses the **currently displayed** recommendation (shoot while #2 is shown
    → you're capturing #2's idea).
11. Capturing an alternative creates **exactly one** Moment; no extra required Moments/Beats
    appear in the Story (Story Home moment count increases by one).
12. **Rescan** and other existing actions still work.
13. **C4-Lite** still works (normal capture → "Moment added"; too-short → Try again / Keep
    anyway).
14. Existing **C1–C3** behavior remains green (scan, recommendation, shoot, Create My Story
    mock, Complete/Reopen, existing-media add).

(Camera needs a physical device; server unit tests + eval already cover the backend logic.)

**STOP. Awaiting the device gate. Asset Understanding not started.**
