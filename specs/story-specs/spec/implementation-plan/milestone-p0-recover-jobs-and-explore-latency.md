# Milestone — P0 Recover Completed AI Jobs + Create-Another-Version Latency

Status: 🟡 implemented & unit-tested, awaiting owner iPhone device acceptance (STOP gate).
Scope: iOS only. No backend / prompt / EditPlan/2 changes. No public deployment. No AWS redesign.
App repo: `/Users/lingzhang/Workplace/story` (GitHub lingzhang1/story, `master`).

## Problem

A user's "Create Another Version" waited 10+ min and produced no new version. The backend was healthy; the
device silently discarded a completed plan.

## 1. Verified lifecycle root cause (Phase 0 — observed vs inferred)

Observed (from App Runner + DynamoDB + the Lambda worker log), job `39769fb1-1868-5f27-9c23-6e83c747f980`:

- Submitted 19:47:11 as `op=another_version`, `approach=visual_first`, **36 contact sheets**, `critique=true`,
  3.64 MB images. Exactly ONE `edit_plan_job_submitted`, `job_created=True` once → **no duplicate inference**
  (idempotency held).
- Worker invocation ran **167,431 ms** (RequestId `b618c659`) → `worker_outcome completed`.
- Plan persisted `status=completed`, `feasible=true`, **21 segments**, `plan.created_at=19:49:57Z`. Still
  retrievable live hours later (TTL `expires_at` ≈ 2026-10-17T01:47Z, ~6 h).
- Device polled the job at 19:47:11, 19:47:14, then a **6.5-minute gap**, one poll 19:53:44, then stopped —
  far short of the client's `maxSeconds=900`.
- `StoryBackend.longSession` is `URLSessionConfiguration.default` with `timeoutIntervalForResource = 300 s`.
- The coordinator's in-memory operation context (`operationType`, parent version, music, the plan) was NOT
  persisted; only a single mutable `story.planJobId`.

Inferred (high-confidence, consistent with all the above): during the long critique wait the app was
backgrounded; iOS suspended the foreground poll `Task` and tore down the socket past the 300 s resource
timeout; the plan completed while backgrounded; on return the poll was dead and the completed plan was never
fetched → silent no-version. Not the render `-11841` bug (that was on-device export); this is planning that
finished but was never consumed.

## 2. Pending-operation persistence design (Phase 1)

New SwiftData `@Model PendingOperationModel` — the durable source of truth for ONE unfinished operation per
Story (`apps/ios/Story/Story/Data/Persistence/Models.swift`, registered in `StoryApp` + test schema):

`storyId, operationId (idempotency key), jobId, operationType, baseVersionId, requestFingerprint,
phase (submitted|planning|plan_ready|rendering|saved|abandoned), jobStatus, failureCategory, planJSON
(the completed EditPlan/2 at plan_ready), musicSelectionRef, outputFormat, targetSeconds`.

Written BEFORE submit-dependent work and kept in sync at every pipeline transition. Minimal + additive
(optional/defaulted); existing SwiftData store migrates cleanly.

## 3. Recovery behavior (Phases 2–3)

Applies to ALL THREE generation operations — `original`, `another_version`, and `revision` (the mandate's
`edit_ai`; the live coordinator value is `"revision"`, the same operation). One shared lifecycle + one
recovery coordinator, keyed on the persisted `operationType`, not hardcoded to Explore.

`PendingOperationRecovery` (`apps/ios/Story/Story/Domain/Creation/PendingOperationRecovery.swift`) runs ONE
pass on `StoryApp` init (relaunch) and on `scenePhase == .active` (foreground) — mirroring the existing
`AssetUnderstandingQueue.recoverOrphans + drain`. It finds recoverable rows and resumes each via
`StoryCreationCoordinator.resumePendingOperation`:

- queued/running → resume polling the existing job (reuses `jobId` — **no re-submit**; the submitted request,
  incl. any revision directives, already lives in the server-side job), then validate + render + persist.
- plan_ready / completed-with-saved-plan → `renderResumedPlan` renders DIRECTLY from the saved plan (no poll,
  no inference) for every operation type; `operationType` + `parentVersionId` are carried onto the output.
- failed → the row is kept with its `failureCategory`; reopen surfaces the failure honestly.
- Music is re-resolved per op from `musicSelectionRef` **WITHOUT a fresh MusicPlan**: the plan was already
  planned music-aware, so recovery only needs the soundtrack file + decoded analysis (track-scoped
  `analysisBoth` + `downloadSoundtrack`, no `recommend()`) plus the persisted `soundtrackRole` /
  `nativeAudioPriority`. My Music resolves locally; nil renders no-music rather than block. This is what keeps
  `original` recovery from unnecessarily rerunning AU/Guide/Coverage (read from SwiftData, never re-invoked in
  `run()`) OR MusicPlan.

Explicitly NOT an indefinite background loop and NOT reliant on background `URLSession`/`beginBackgroundTask`:
active polling stops when the app is suspended and a fresh pass resumes it on the next `.active`.

Exactly-once output: on successful `persist()` the pipeline deletes every pending row for the Story
(`finalizePending`), so no later foreground/reopen can re-render the plan into a duplicate version.

## 4. Duplicate-job protections (Phase 5)

- Process-global `activeStories` claim in `beginRun`/`resumePendingOperation`: a second coordinator (another
  view, or the recovery driver) cannot run/resume the same Story concurrently → no two renders of one plan.
- Released atomically in the run/resume `defer` with `isCreating`, closing the observe-then-release race.
- Three operation classes kept distinct: **resume** (reuse `operationId`), **transport-retry** (reuse
  `operationId`), **deliberate new version** (NEW `operationId`). A deliberate Create Another Version /
  Revise first `abandonPendingOperations` for the Story, so there is never more than one non-terminal op.
- `hasRecoverablePendingOperation(storyId:)` lets the UI offer resume instead of silently re-creating.

## 5. Create Another Version routing changes (Phase 4)

`StoryMultimodalPlanning.critiqueExploreEnabled` (default **OFF**; env `STORY_CRITIQUE_EXPLORE`).
For `operationType == "another_version"` the critique pass is now **conditional, not automatic** → ONE
multimodal planning call as the default. Preserved: bounded multimodal contact sheets, prior-version
context + diversity, mandatory deterministic validation, the worker's bounded repair. NOT changed: images are
kept (no text-only downgrade), frozen prompts + EditPlan/2 untouched. The original create and NL revision keep
their existing critique behavior.

## 6. Before / after latency + model-call count

| | Model calls | Planning latency |
|---|---|---|
| Before — Explore `critique=true`, 36 sheets (job `39769fb1`, measured) | 3 (1 plan + 2 critique/revision) | **167.4 s** (worker `b618c659`) |
| After — Explore one-call, critique OFF (default) | **1** | ~⅓ (projection; the 2 Opus-with-36-sheet critique calls removed) — exact device number at acceptance |

The backend's own contract notes critique_revision "costs 2 extra model calls", so the 3→1 reduction is
structural. Images, validation and repair are unchanged, so editorial quality is expected to hold; Phase 6
measures one-call vs critique on hiking + Girl with Dress footage.

## 7. Device acceptance (owner Phase 6 — the STOP gate)

Not yet run. On iPhone: start Create Another Version → background during planning → wait for backend
completion → reopen → recover the completed plan with NO new inference → render + save → verify
`parentVersionId`, prior versions intact; force-quit during planning and after plan retrieval and recover;
repeated foreground = no duplicate render; Try Again reuses operation identity; backend expiry/failure
surfaced; original creation + NL revision recovery still work. Also compare one-call vs critique-enabled
Explore (model calls, latency, editorial quality).

## 8. Files

- `apps/ios/Story/Story/Data/Persistence/Models.swift` — `PendingOperationModel`.
- `apps/ios/Story/Story/App/StoryApp.swift` — schema + launch/foreground recovery.
- `apps/ios/Story/Story/Domain/Creation/PendingOperationRecovery.swift` — recovery driver (new).
- `apps/ios/Story/Story/Domain/Creation/StoryCreationCoordinator.swift` — durable transitions, resume path,
  single-flight claim, Phase-5 abandon.
- `apps/ios/Story/Story/Domain/Creation/StoryMultimodalPlanning.swift` — `critiqueExploreEnabled`.
- `apps/ios/Story/StoryTests/StoryCreationCoordinatorTests.swift` — recovery + duplicate-protection tests.

## 9. Remaining risks

- Cold-relaunch render-resume re-resolves a provider soundtrack over the network (track-scoped analysis +
  download, NO MusicPlan); if that fails the resume renders no-music (video still recovered) — honest
  degradation, surfaced via beacon.
- A queued/running resume re-reads persisted AU/Guide from SwiftData to rebuild the request, but when
  `story.planJobId` is set that rebuilt request is NOT submitted — only the existing job is polled — so the
  revision directives baked into the server-side job are preserved and no inference repeats. The deterministic
  feasibility preflight re-runs (cheap, no model call).
- `swiftc -parse` clean on all touched files; the SwiftData `@Model` macro is sandbox-blocked, so the device
  Xcode build is the authoritative compile gate (owner acceptance).
