# AU Background Continuity and Honest Progress UX

Status: IMPLEMENTED on branch `feat/au-background-continuity` (off master `ce5fe6d`). NOT merged, NOT deployed, NOT device-tested. iOS-only; no backend, infra, prompt/model, quota or retention change.

## 1. Root cause (confirmed from beta logs, 2026-11-08)

- 51 `POST /v1/asset-understanding` requests, all 200; zero 429/5xx. Latency p50 15.6s, p90 18.7s.
- Requests arrive only in foreground bursts: 11-07 22:55 PT x22 (3.8 min), then a **689-minute gap**, then 11-08 10:28 PT x19 (3.0 min), matching the screenshot.
- The queue is healthy; it simply has no execution when iOS suspends the app. Before this change there was no `BGTask*`, no `UIBackgroundModes`, and no entitlement; the only `beginBackgroundTask` was Story creation. The UI line "N ready · M still being analyzed" came from MomentUnderstanding row presence only, so "waiting for the app to open" looked identical to "analyzing".

## 2. AU queue lifecycle map

Import (`StoryPhotosPicker`, videos only, max 100) -> `addExistingMedia` persists Moments + files in MediaStore -> `enqueueImportedVideos` writes PENDING `AssetUnderstandingJobModel` (idempotent per momentId; skips Moments already understood) -> `drain()` (triggers: app launch, scene active, sign-in, import sites, NEW: network regained, NEW: retry timer) -> per job: RUNNING saved -> `MomentFrameExtractor` (24 frames, device) -> sha256 -> `POST /v1/asset-understanding` (multipart frames, ephemeral, ai_sync class 20/min, server admission semaphore 4) -> `upsertUnderstanding` -> COMPLETE -> coalesced `UnderstandingSync.push`.

Persistence/recovery: launch `recoverOrphans()` resets RUNNING->PENDING. Photos/stills are not enqueued (out of scope). AU reads the LOCAL file; cloud backup is not needed for AU, and Auto Backup defaults OFF (`AutoBackupStore.isEnabled ?? false`), so imported media is cloud-restorable only if the account opted in. An AU result is pushed only for media already cloud-backed (existing P1-E behavior, unchanged).

Defects found in the audit and fixed:

| Defect | Fix |
| --- | --- |
| 401/403 mapped to `badStatus` (non-retryable): a token expired in the background burned 4 attempts and parked the job 24h | New `.unauthorized`; job returns to PENDING with marker `auth_required`, no attempt burned, drain stops |
| `authTokenProvider` is a captured snapshot refreshed only by foreground handlers | `sharedEnsureFreshToken` (-> `validAccessToken()`) runs before every paid request |
| Offline transport errors burned attempts | Offline = pause, marker `offline`, no attempt; drain refuses to start offline |
| Per-instance `draining` flag but every call site builds its own queue | Process-wide single-flight |
| Hydration-gated job could spin the loop 50x | Skipped once per drain |
| A job in backoff waited for the next app trigger | In-app retry timer (<= 15 min) |
| No resume on reconnect | `NetworkReachability.onBecameSatisfied` -> drain |
| Hard-parked (24h) jobs had no manual path | `retryParked()` + Retry button |

## 3. iOS background API assessment

Deployment target iOS 18.5; toolchain SDK 27.1. Every iOS 26 symbol is behind `#available(iOS 26.0, *)`.

| API | Fit | Decision |
| --- | --- | --- |
| `beginBackgroundTask` | ~30 s grace only, unsuited to a 10-30 min queue | Not used |
| `BGContinuedProcessingTask` (iOS 26) | User-initiated, visible system progress UI, user can cancel, runs the same sequential drain | **Used**, imports only |
| `BGProcessingTask` | System picks the time; no charging/idle window guaranteed; for maintenance | Not primary |
| Background `URLSession` | Moves file bytes; cannot run extract-frames -> POST sequentially | Not used for AU (Auto Backup upload is separate) |
| Silent push / server wake | Needs new infra, not guaranteed | Rejected |

Config: `Info.plist` gets only `BGTaskSchedulerPermittedIdentifiers = $(PRODUCT_BUNDLE_IDENTIFIER).au.import`. No `UIBackgroundModes` and no entitlements (GPU not requested). **Unverified on device:** whether iOS also demands a background mode for this identifier (`.notPermitted` on submit). The code treats any submit error as "foreground-only" and the UI never claims background continuation unless a system task is actually running.

## 4. Continued processing design (`AUContinuedProcessing`)

- Starts only from the 3 user-initiated import sites, never at launch; minimum batch of 3 Moments (a lone ~15 s clip is not worth system UI). Strategy `.queue`; one static identifier, one task at a time, registered once.
- It is a supervisor, not a second queue: it polls PERSISTED counts ~1/s to set `progress` (units = Moments), makes sure exactly one drain runs, and calls `setTaskCompleted(success:)` honestly. No timers or extrapolated fractions.
- Expiration/cancel: sets the stop gate (honored between jobs). The in-flight request is NOT cancelled, so there is no duplicate resend/bill; remaining jobs stay PENDING. Fails safe on suspension too (persisted state is authoritative).
- Ends early (reporting success only if complete) when waiting for network / sign-in / daily limit / manual retry; rides out ordinary backoff for at most 180 s; stops after two drain launches with no progress.
- Later imports join the running task (batch grows). Below iOS 26 or on Simulator everything degrades to the plain foreground drain.

## 5. Honest status UX (`AUProgressStatusView`)

State from `AUQueueStatusMapper` (pure; persisted rows + live network/draining facts): Analyzing X of Y; retrying shortly; X of Y analyzed · continues when YoTale is open; waiting for network; sign in to continue; paused, daily limit reached; "N moments couldn't be analyzed" + Retry. "Preparing media" stays in the import banner; "Uploading" belongs to the separate backup pipeline and is not conflated. The screen is never kept awake and Story browsing is never blocked.

## 6. Verification status

| Layer | Result |
| --- | --- |
| Implemented | Everything above |
| Python suite | `apps/api/tests` all pass (no backend change) |
| Simulated (standalone, this sandbox) | `AUQueueStatusTests` (17 cases: mapper, classifier, constants) compiled with `swiftc` against the real `AUQueueStatus.swift` and run: ALL PASS |
| Compile-checked | Full `xcodebuild` for iOS Simulator: no diagnostics in the changed files other than the sandbox's known SwiftData/Observation macro-plugin failure (`swift-plugin-server`), which cascades. This is NOT a build pass |
| Written, not run | `AUContinuityQueueTests` (30 Moments exactly-once, 401 pause, stale token, offline at start / mid-drain, cancel, stop gate, cross-instance single-flight, retryParked, snapshot after restart). Needs the owner's Xcode Cmd-U |
| Device-tested | Nothing |
| Deployed | Nothing |

### Physical-device checklist

1. Import 30 clips, background immediately: system progress UI appears, no `.notPermitted`; reopen: counts match persisted truth.
2. Lock the phone; return after 10 min.
3. Airplane mode mid-run, then restore: status shows waiting for network, resumes on reconnect, no attempts burned.
4. Cancel from the system UI and let it expire: remaining jobs stay PENDING, resume on next open, no Moment analyzed twice (compare `asset_understanding_resolved` count to Moment count in beta logs).
5. Force-quit mid-run: queued request is cancelled by the system; reopening resumes; at most the single in-flight clip repeats.
6. Token expiry: wait >60 min backgrounded, confirm no 401 loop and no 24h park.
7. Repeated fg/bg; photo + video concurrent imports; quota/retryable errors.
8. Check the ~15 s per-clip progress granularity does not trigger a stall expiry (the one real risk of `progress` advancing only per Moment).
9. Simulator: confirm graceful foreground-only fallback.

## 7. Cost/battery estimate

~15 s per clip, ~4 clips/min sequential (server cap 20/min and admission 4 are never approached). 30 clips ~ 8 min of CPU frame extraction + network. No extra inference calls are made for progress; progress reads local SwiftData rows once per second.

## 8. Limitations

Not guaranteed (system may refuse, delay, or expire); user can cancel; a queued request is dropped if the app is removed from the app switcher; force-quit during an in-flight billed request can repeat that single request; photos are not importable/analyzable; Auto Backup off by default; foreground expiration also stops foreground drain until the next scene-active; iOS 18.5-25 only get honest foreground status.

## 9. Device findings and mitigations (2026-11-09)

Device runs on iOS 27.0.1 (beta backend), read from the on-device `AUDiag` event log (tap the Story Home status line in Debug builds):

| Finding | Fix |
|---|---|
| A local step that never returned held the process-wide single-flight drain, so later drains were no-ops ("1 of 39" frozen) | Frame extraction and hashing bounded at 90 s; timeout returns the job to pending, no attempt burned (`09b8924`) |
| The task's batch included 31 older library Moments; the import ran last ("0 of 6") | Imported Moments run first and alone define the task's progress and success (`41aed66`) |
| System expired the task ~30 s after backgrounding with progress stuck at 0, while one 50 s request was in flight | Count the in-flight job (`cc5f13e`); then the two mitigations below |

Owner-approved mitigations for long requests (model latency on beta rose from ~15 s to 24-49 s):

1. **Estimated progress while waiting on the server.** The system task's progress is real for every step the app can observe (frames extracted, hashed, response returned). Only the wait on the server response is estimated: `AUTaskProgress` rises toward 95% of the Moment using the smoothed recent request duration, never reaches it, and the remainder arrives only with the real response. The value never moves backwards. Story Home's "X of Y done" stays persisted-state only.
2. **Two analyses at once, only while the background task runs.** `AssetUnderstandingQueue.maxWorkers = 2`; the second worker is enabled by the supervisor for the life of the system task and is otherwise off, so foreground behavior is unchanged (one at a time). A claimed set prevents two workers from picking the same job across the token-refresh await; auth, offline, cancel and local-timeout stops end both workers; the in-flight request is never cancelled.

Rate-limit check: the backend's `ai_sync` throttle (`apps/api/app/throttle.py`) is per user (`story_user_id`) and per class, default 20 per fixed one-minute window, and the class is shared with the other synchronous AI routes (creative-intent, story-guide, story-guide-v2, story-coverage, director, music-plan, duration-recommendation and others). Epidemic music and scene-image calls are a separate `music_provider` class. Two concurrent AU requests at observed latencies (15-50 s) are about 2-8 per minute. A 429 takes the existing `rateLimited` path (Retry-After plus backoff, no completed work resent).
