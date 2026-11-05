# Milestone R-b — Case G: Real AI EditPlan → First Rendered Story

**Status:** backend DEPLOYED + verified live; iOS Case G wired + parse-clean + XCTests authored.
**STOP at the physical-iPhone gate** (actual render + device round-trip not runnable in the build sandbox).
Nothing pushed. R-c / Creative Editing V2 / commercial Epidemic NOT begun.

Commits: app `0a1cb28` (iOS Case G wiring). Backend code was frozen in M-d (`ec04768`); this milestone
only CONTAINERIZED + DEPLOYED it — no backend source change.

---

## 1. Backend deployment target
- **Environment: `development`** (App Runner `story-development-api`, acct 989088054552, us-east-1,
  `https://ydmju5wdps.us-east-1.awsapprunner.com`). NOT production — no stop-and-report needed.
- Process (frozen pattern): zip repo source → S3 `story-codebuild-src-…/rb-caseg/` → throwaway CodeBuild
  project `story-rb-caseg-build` (privileged Linux, Docker) builds `apps/api/Dockerfile` and pushes
  `:latest` to the pre-existing ECR repo `story-development-api` → App Runner `start-deployment` pulls it.
  No new AWS infrastructure; CDK stack untouched.

## 2. Deployment verification (live, not build-only)
- `/health` → `{"status":"ok","service":"story-api","version":"0.1.0"}`.
- OpenAPI now registers **`/v1/edit-plan`** alongside creative-intent, scene-understanding, director/*,
  asset-understanding, story-guide, story-coverage/v2, music-direction. (`/v1/music/candidates` present but
  flag-gated → **404 at runtime**, Epidemic OFF.)
- **Real authenticated `POST /v1/edit-plan`** with safe synthetic data (3 moments, useful_segments, no music):
  HTTP 200 in ~6.7s, `schema_version=edit_plan/2`, `feasible=true`, 3 segments, total output **9.0s = target
  (0% error)**, every `asset_id` matches a request moment, every source range inside its useful_segment,
  **every `music_alignment.anchor=null`** (correct no-music). No fabricated IDs.
- `STORY_EPIDEMIC_MODE` left unset → `/v1/music/candidates` → 404. No provider credential reaches the device.

## 3. Backend regression
- **199 passed** (unchanged) both before deploy (gate) and after. Deployed image = tested tree.

## 4. iOS files changed (app `0a1cb28`)
- **NEW** `Data/Contracts/EditPlannerService.swift` — `POST /v1/edit-plan` client; 200→`EditPlanV2`,
  422→`.infeasible(reason)`, 503→`.unavailable`. No fabrication client-side.
- **NEW** `StoryTests/EditPlannerCaseGTests.swift` — 6 tests (shape/identity, no-music, AU exclusion,
  no-usable-moments error, EditPlanV2 decode).
- `Media/Render/RenderSupport.swift` — **`EditPlanRequestBuilder`**: builds the request from persisted Story
  data; the load-bearing identity mapping (below); no-music mode; excludes Moments without completed AU or a
  local file (never invents content).
- `Features/Debug/RenderTestHarnessView.swift` — real-plan toggle ENABLED; `renderRealPlan()` path; Case G
  diagnostics (model, plan latency, selected/excluded moments, segments, requested/planned/rendered duration,
  music mode, validation errors); local pre-check that every `asset_id` resolves before rendering.
- `Features/StoryHome/CreateStoryPreviewView.swift` — **reachable DEBUG entry point** ("Render Test (dev) ·
  Media Engine V1") inside the `aiDebug` diagnostics block, presenting the harness as a sheet. (R-b shipped the
  harness with NO entry point — this closes that gap.)

## 5. Real Edit Planner request path (Case G)
Existing Story → completed `MomentUnderstanding[]` + flattened CreativeIntent → `EditPlanRequestBuilder`
→ `POST /v1/edit-plan` (Opus 4.6, deterministic validator) → `EditPlanV2` → local asset-resolution pre-check
→ `MediaEngineV1.render` → MP4. Not a static plan labeled "AI".

## 6. MusicPlan availability → NO-MUSIC mode
**No production MusicPlan inference endpoint/engine exists** (only the frozen contract + a `no_music_planning`
test). Per the task, Case G uses the frozen planner's **supported no-music mode** — `music_plan` /
`music_asset_id` / `music_analysis` omitted; backend confirmed to accept this (live 200). No MusicPlan engine
built. No fixture substituted.

## 7. Local asset identity mapping (verified by test)
`MomentModel.id` == request `moments[].id` == `EditSegment.asset_id` (echoed by the planner) →
`MomentResolver.urlResolver` (keyed on `id.uuidString`) → `MediaStore` relative path → local file.
NOT confused with MomentUnderstanding/CaptureSession/filename. A Moment missing a local file OR completed AU is
**excluded** (reported as `excludedMomentIds`); a planned `asset_id` with no local file **blocks render** with a
clear diagnostic — never a silent skip.

## 8. Case G diagnostics (DEBUG-only)
Planner model, plan latency, moments selected/excluded, segment count, requested vs planned vs rendered
duration, output size, feasible, validation errors, music mode. No API keys, no raw private video, no personal
paths in any telemetry.

## 9. Tests run
- **VERIFIED HERE:** backend 199 pass; live `/v1/edit-plan` 200 with a valid EditPlan/2; all 5 changed/new
  Swift files `swiftc -parse` clean; 6 Case G XCTests authored (+ R-b's 8 engine tests).
- **REQUIRES XCODE/DEVICE:** the XCTest RUN; the on-device `/v1/edit-plan` round-trip from the app; the actual
  AVFoundation render/export/playback.

## 10. Known limitations
- No MP4 produced in-sandbox (AVFoundation export has no sandbox path) — first render is the device gate.
- Single-file `-parse` confirms syntax, not cross-file typecheck (Xcode).
- The 5 new Swift files must be in the Xcode project/target (same manual add as `StoryContracts.swift`), else
  they won't compile into the device build.
- No-music mode only (no production MusicPlan engine); music path deferred.

## 11. Deployment status
Dev backend LIVE with `/v1/edit-plan`; Epidemic OFF (404). No consumer-flow change (harness is `aiDebug`-only,
never Release). No production export path enabled.

## 12. Physical-iPhone acceptance checklist
Prereq: rebuild in Xcode with the 5 new files in the target; launch in **aiDebug** mode
(`-STORY_MODE aidebug` launch arg, or set UserDefaults `story_mode=aidebug`).
1. Open a Story with ≥3 analyzed video Moments → Create My Story preview → scroll to DEBUG →
   **"Render Test (dev) · Media Engine V1"**.
2. **Fixture first** (toggle OFF) → "Render Test Story" → plays? correct order/trims, no black frames? (Cases A–E).
3. **Case G** (toggle ON) → "Generate AI EditPlan + Render" → diagnostics show real Opus plan (model, latency,
   real Moment count, segments, planned duration) → plays?
4. Confirm segments reference REAL Moments; narrative order coherent; output duration ≈ planned (±0.3s).
5. Native audio behaves per plan (keep audible; duck lowered; mute silent).
6. Output survives app relaunch; Save to Photos / Share to Files work; source Moments intact.
7. **Case F** (failure): a Story whose Moment file is missing → clear error, no partial output, no silent skip.

## 13. Whether Case G is ready for owner acceptance
**Ready for device verification.** Backend deployed + live-proven; iOS wired end-to-end with a reachable entry
point, real-plan path, identity mapping, and diagnostics; parse-clean; tests authored. The only unverifiable-
here steps are the device render + the on-device round-trip — exactly the STOP gate.

## 14. Recommended next milestone (after device acceptance)
R-c: wire the renderer into the frozen Figma Create My Story → Result (replace the mock GeneratedOutput);
then production music (paid Epidemic tier); Creative Editing V2 separately (starts from the R-a Edit Evidence
stage). NOT begun.
