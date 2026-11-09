import Foundation
import SwiftData
import UIKit

// AssetUnderstandingQueue — the FROZEN persistent on-device AU job queue
// (06-asset-understanding.md §6-7, §9-10).
//
// State machine (persisted, survives app termination):
//     enqueue ──▶ PENDING ──(eligible)──▶ RUNNING ──success──▶ COMPLETE
//                    ▲                        │
//                    └──── failure / interruption (incl. the server's own
//                          single retry already spent) ───┘  (+ backoff)
//
// Invariants:
//  - Moment creation NEVER blocks on AU: enqueue only writes a PENDING job row.
//  - Opportunistic + resumable: drain() runs on app-active / network-available /
//    next launch. No assumption of unlimited background execution.
//  - Orphan recovery: any RUNNING job found at launch (app was killed mid-run)
//    is reset to PENDING.
//  - Idempotent: one job and one MomentUnderstanding per momentId (upsert); a
//    resumed/duplicate run never creates a second understanding row (§9).
//  - No model fallback / routing: a server 503 (its own one retry already spent)
//    sends the job back to PENDING with bounded exponential backoff.
@MainActor
final class AssetUnderstandingQueue {
    private let context: ModelContext
    private let service: AUAnalyzing
    private let extractFrames: (URL) async throws -> [AUExtractedFrame]
    /// Injectable media-presence check (defaults to the real MediaStore). A seam so tests don't depend on the
    /// device filesystem: the `run()` guard that DROPS a job when its media file is gone otherwise reads the
    /// real disk, making a fake "media/x.mov" job order/filesystem-dependent (the pre-existing
    /// AuthGatingTests flake). Same injection pattern as `extractFrames`/`isAuthed`.
    private let fileExists: (String) -> Bool
    /// Whether an authenticated session exists. Asset Understanding is a PAID cloud call, so draining is
    /// DEFERRED until this returns true (Increment 4, Phase 4): the Moment and its PENDING job are preserved;
    /// no model call is made while signed out. On sign-in the app calls `drain()` and the existing idempotent
    /// upsert + orphan recovery resume each pending job exactly once under the authenticated account. Injected
    /// (not an AuthStore import) to keep the queue pure/testable; defaults to the shared predicate below so all
    /// existing construction sites defer correctly without plumbing an AuthStore through each.
    private let isAuthed: () -> Bool

    /// Shared auth predicate, set once by AuthStore (same seam pattern as `StoryBackend.authTokenProvider`).
    /// Defaults to `false` — fail SAFE: until AuthStore wires it, paid AU does not run unauthenticated. The app
    /// sets it on launch before the first drain, and in dev optional-auth AuthStore reports signed-in state
    /// honestly (a restored session = true).
    nonisolated(unsafe) static var sharedIsAuthed: () -> Bool = { false }

    /// P1-E (AU durability): fired ONCE after a drain batch that completed at least one understanding, so a
    /// result produced MID-SESSION is pushed to the account store without waiting for the next foreground /
    /// sign-in (the previous push cadence). Wired by StoryApp to a coalesced, idempotent
    /// `UnderstandingSync.shared.push(...)`; default no-op so the queue stays pure/testable and construction
    /// sites that never set it (incl. unit tests) do nothing. Same static-seam pattern as `sharedIsAuthed` /
    /// `MediaUploadQueue.sharedAutoEnroll`. The push itself is cheap + idempotent (PUT), and already skips any
    /// understanding whose media is not yet cloud-backed — so a Moment whose sha is not ready is simply retried
    /// by the upload-complete hook later, never lost.
    nonisolated(unsafe) static var sharedPushUnderstanding: () -> Void = { }

    /// Ensures the bearer token the NEXT request will carry is fresh (refreshing it when it is inside the expiry
    /// margin). `StoryBackend.authTokenProvider` is a captured SNAPSHOT that only foreground handlers refresh, so
    /// a drain running while the app is backgrounded for an hour would otherwise send an expired token. Wired by
    /// StoryApp to `AuthStore.validAccessToken() != nil`; default true so tests/unwired sites are unchanged.
    nonisolated(unsafe) static var sharedEnsureFreshToken: () async -> Bool = { true }
    /// Whether the network path is currently usable (wired to NetworkReachability). Default true.
    nonisolated(unsafe) static var sharedIsOnline: () -> Bool = { true }

    /// PROCESS-WIDE single-flight. Every call site builds its own queue instance, so a per-instance flag could not
    /// stop two drains (e.g. scene-active + a background continued-processing task) from analyzing the same job
    /// twice — which would double-bill. All drains share this one flag.
    private static var drainInFlight = false
    private static var drainStartedAt: Date?
    /// Moments a user just imported: picked before older backlog (still oldest-first within each group).
    static var priorityMomentIds = Set<UUID>()
    /// Jobs being worked on right now (up to `maxWorkers`), with how many REAL steps are done
    /// (0 = started, 1 = frames extracted, 2 = hashed, request in flight since `requestStartedAt`).
    static var inFlight: [UUID: AUInFlight] = [:]
    /// Smoothed duration of recent successful AU requests; feeds the ESTIMATED in-request progress only.
    static var typicalRequestSeconds: TimeInterval = 20
    /// At most this many jobs at once. A second worker runs ONLY while `parallelWorkersEnabled` (set by the
    /// iOS continued-processing supervisor while its system task runs); otherwise the queue stays sequential.
    /// Two concurrent requests stay under the server's per-user ai_sync limit (20/min, shared with other AI calls).
    static let maxWorkers = 2
    static var parallelWorkersEnabled = false
    /// Moment ids a worker has picked but not yet marked RUNNING (the token refresh awaits in between), so two
    /// workers can never pick, and bill, the same job.
    private static var claimed = Set<UUID>()
    /// The drain currently running, so the supervisor can add the second worker mid-drain.
    private static var currentRun: DrainRun?
    /// Upper bound for one LOCAL step (frame extraction or source hash) of one clip. Normal is a few seconds.
    static let localStepDeadline: TimeInterval = 90
    /// "fg" / "bg" / "inactive" for diagnostics (UIApplication state; main actor).
    static func backgroundState() -> String {
        switch UIApplication.shared.applicationState {
        case .active: return "fg"
        case .background: return "bg"
        case .inactive: return "inactive"
        @unknown default: return "unknown"
        }
    }
    /// True while any drain in this process is processing jobs (live fact for the status UI / supervisor).
    static var isDraining: Bool { drainInFlight }
    /// Thread-safe stop request set by a system expiration / cancel. Checked between jobs by EVERY drain (never
    /// cancels an in-flight billed request). Cleared on foreground and at the start of a user-initiated import.
    static let stopGate = AUStopGate()
    private static var retryTask: Task<Void, Never>?
    /// Longest in-app retry timer; farther-out jobs wait for the next trigger (foreground / network / import).
    static let retryTimerCeiling: TimeInterval = 15 * 60

    private let framePolicy = MomentFrameExtractor.framePolicy
    private let promptVersion = "au_prompt/2"
    private let schemaVersion = "moment_understanding/2"

    // Bounded exponential backoff: 5s, 20s, 80s, ... capped at 10 min.
    private let baseBackoff: TimeInterval = 5
    private let maxBackoff: TimeInterval = 600

    init(
        context: ModelContext,
        service: AUAnalyzing = AssetUnderstandingService(),
        extractFrames: @escaping (URL) async throws -> [AUExtractedFrame] = { try await MomentFrameExtractor.extract(from: $0) },
        isAuthed: @escaping () -> Bool = { AssetUnderstandingQueue.sharedIsAuthed() },
        fileExists: @escaping (String) -> Bool = { MediaStore.shared.fileExists(relativePath: $0) }
    ) {
        self.context = context
        self.service = service
        self.extractFrames = extractFrames
        self.isAuthed = isAuthed
        self.fileExists = fileExists
    }

    // MARK: - Enqueue (called AFTER the Moment is persisted; never blocks it)

    /// Enqueue an AU job for a freshly-persisted Moment. Idempotent: if a job
    /// already exists for this momentId, it is left as-is (no duplicate).
    func enqueue(
        momentId: UUID,
        relativeMediaPath: String,
        sourceCaptureId: UUID?,
        captureContext: [String: Any]?
    ) {
        if existingJob(for: momentId) != nil { return }
        // R7-C fix: a Moment that ALREADY has a completed understanding must NOT be re-analyzed — this is the
        // case after an R6 restore (the downloaded original is byte-identical, SHA256-verified, to what was
        // understood before). Re-enqueuing here is what flooded the queue with duplicate AU + coverage work.
        if hasCompletedUnderstanding(momentId: momentId) { return }
        var ctxJSON: String?
        if let captureContext,
           let d = try? JSONSerialization.data(withJSONObject: captureContext) {
            ctxJSON = String(data: d, encoding: .utf8)
        }
        let job = AssetUnderstandingJobModel(
            momentId: momentId,
            relativeMediaPath: relativeMediaPath,
            sourceCaptureId: sourceCaptureId,
            captureContextJSON: ctxJSON,
            framePolicy: framePolicy,
            promptVersion: promptVersion,
            schemaVersion: schemaVersion
        )
        context.insert(job)
        try? context.save()
    }

    // MARK: - Launch recovery

    /// Reset orphaned RUNNING jobs (app was killed mid-analysis) back to PENDING.
    /// Call once at launch before the first drain.
    func recoverOrphans() {
        let running = (try? context.fetch(
            FetchDescriptor<AssetUnderstandingJobModel>(
                predicate: #Predicate { $0.stateRaw == "running" }
            )
        )) ?? []
        for job in running {
            job.state = .pending
            job.updatedAt = .now
        }
        if !running.isEmpty { try? context.save() }
    }

    // MARK: - Drain (opportunistic)

    /// Process eligible PENDING jobs one at a time. Safe to call repeatedly
    /// (app-active tick, network-available, next launch). Re-entrancy guarded.
    ///
    /// DEFERRED while signed out: Asset Understanding is a paid cloud call, so a signed-out drain is a silent
    /// no-op — pending jobs are left untouched (not failed, no backoff burned) and resume on the next drain
    /// after sign-in. This is the "defer background AI until an authenticated session exists" boundary; there
    /// is NO sign-in prompt here (background work waits silently).
    func drain(maxJobs: Int = 50, shouldContinue: @escaping () -> Bool = { true }) async {
        if Self.drainInFlight {
            let held = Self.drainStartedAt.map { Int(Date().timeIntervalSince($0)) } ?? -1
            AULog.queue.notice("au drain skip=in_flight held_s=\(held)")
            if held > 120 { AUDiag.record("drain skip in_flight held_s=\(held)") }
            return
        }
        guard isAuthed() else { AULog.queue.notice("au drain skip=signed_out"); return }   // defer silently until authenticated
        guard Self.sharedIsOnline() else { AULog.queue.notice("au drain skip=offline"); return }   // resume on reconnect
        Self.drainInFlight = true
        Self.drainStartedAt = Date()
        AUDiag.record("drain begin app=\(Self.backgroundState())")
        defer {
            Self.drainInFlight = false
            Self.drainStartedAt = nil
            AUDiag.record("drain end app=\(Self.backgroundState())")
        }

        let r = DrainRun(maxJobs: maxJobs, shouldContinue: shouldContinue)
        r.spawnSecond = { [unowned self] in
            r.secondActive = true
            AUDiag.record("drain second worker on app=\(Self.backgroundState())")
            r.secondTasks.append(Task { @MainActor in await self.worker(1, r) })
        }
        Self.currentRun = r
        await worker(0, r)
        while let t = r.secondTasks.popLast() { await t.value }   // never end the drain under a running job
        Self.currentRun = nil
        let completedAny = r.completedAny
        // P1-E (AU durability): a result produced in THIS session is pushed now (coalesced: one push for the
        // whole batch, not one per Moment) instead of waiting for the next foreground/sign-in. No-op until
        // StoryApp wires the seam; idempotent PUT; media-not-yet-backed understandings are retried by the
        // upload-complete hook, never lost.
        if completedAny { Self.sharedPushUnderstanding() }
        scheduleRetryIfNeeded()
    }

    /// Add the second worker to the running drain if parallel work is allowed and it is not already running.
    /// Called by worker 0 between jobs and by the supervisor every tick, so it starts while worker 0 is still
    /// waiting on a long request, not only after it.
    static func kickParallel() {
        guard maxWorkers > 1, parallelWorkersEnabled, let r = currentRun, !r.secondActive, !r.stopped else { return }
        r.spawnSecond?()
    }

    /// One worker of a drain. Worker 0 is the existing sequential loop; worker 1 runs only while parallel work
    /// is enabled and stops picking new jobs as soon as it is not (its current job always finishes).
    private func worker(_ index: Int, _ r: DrainRun) async {
        defer { if index > 0 { r.secondActive = false } }
        while !r.stopped, r.processed < r.maxJobs, r.shouldContinue(), !Self.stopGate.isSet, !Task.isCancelled {
            if index == 0 { Self.kickParallel() }
            if index > 0, !Self.parallelWorkersEnabled { break }
            guard let job = nextEligibleJob(excluding: r.skipped) else { break }
            // R7-F: do NOT analyze a Moment while its Story's cloud state is still hydrating — a restore may
            // be about to supply a reusable understanding (restore first, regenerate only if missing).
            // Skipped for THIS drain only (it never spins on the same job).
            if CloudHydrationGate.shared.isHydrating(momentId: job.momentId) { r.skipped.insert(job.momentId); continue }
            Self.claimed.insert(job.momentId)
            defer { Self.claimed.remove(job.momentId) }
            // Token freshness BEFORE the paid request (the snapshot provider is stale after a long background).
            guard await Self.sharedEnsureFreshToken() else {
                AULog.queue.notice("au job=\(AULog.short(job.momentId), privacy: .public) token=unavailable -> auth_required")
                markAuthRequired(job); r.stopped = true; break
            }
            r.processed += 1
            let before = job.stateRaw
            let outcome = await run(job)
            if before != "complete" && job.stateRaw == "complete" { r.completedAny = true }
            if outcome == .stop { r.stopped = true; break }   // auth / offline / cancel / local timeout: both stop
        }
    }

    /// Reset jobs that exhausted their bounded retries (parked ~24h out) so a user-initiated Retry runs them now.
    /// Returns how many were reset. Does not drain; the caller does.
    @discardableResult
    func retryParked() -> Int {
        let now = Date()
        let pending = (try? context.fetch(FetchDescriptor<AssetUnderstandingJobModel>(
            predicate: #Predicate { $0.stateRaw == "pending" }
        ))) ?? []
        var n = 0
        for job in pending where AUQueueStatusMapper.isParkedForRetry(Self.facts(job), now: now) {
            job.attempts = 0
            job.nextEligibleAt = now
            job.lastError = nil
            job.updatedAt = now
            n += 1
        }
        if n > 0 { try? context.save() }
        return n
    }

    /// A job in ordinary backoff would otherwise wait for the next app trigger. While the app is alive, wake once
    /// when the soonest backoff ends (bounded to 15 min). Never for auth/offline/quota/parked jobs — those wait
    /// for their own signal (sign-in / reconnect / next day / manual retry).
    private func scheduleRetryIfNeeded() {
        Self.retryTask?.cancel(); Self.retryTask = nil
        let now = Date()
        let pending = (try? context.fetch(FetchDescriptor<AssetUnderstandingJobModel>(
            predicate: #Predicate { $0.stateRaw == "pending" && $0.nextEligibleAt > now }
        ))) ?? []
        let waits = pending.compactMap { j -> TimeInterval? in
            let err = j.lastError ?? ""
            if err.hasPrefix(AUMarker.quotaPrefix) || err.hasPrefix(AUMarker.authRequired) || err.hasPrefix(AUMarker.offline) { return nil }
            let w = j.nextEligibleAt.timeIntervalSince(now)
            return w <= Self.retryTimerCeiling ? w : nil
        }
        guard let soonest = waits.min() else { return }
        Self.retryTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64((soonest + 0.5) * 1_000_000_000))
            guard !Task.isCancelled, let self else { return }
            await self.drain()
        }
    }

    private func markAuthRequired(_ job: AssetUnderstandingJobModel) {
        job.state = .pending
        job.lastError = AUMarker.authRequired
        job.updatedAt = .now
        try? context.save()
    }

    static let recentWindow: TimeInterval = 12 * 3600

    /// Moment ids of every job not yet complete (pending or running).
    static func unfinishedMomentIds(context: ModelContext) -> Set<UUID> {
        let all = (try? context.fetch(FetchDescriptor<AssetUnderstandingJobModel>())) ?? []
        return Set(all.filter { $0.state != .complete }.map(\.momentId))
    }

    static func facts(_ j: AssetUnderstandingJobModel) -> AUJobFacts {
        AUJobFacts(momentId: j.momentId, state: j.state, attempts: j.attempts,
                   nextEligibleAt: j.nextEligibleAt, lastError: j.lastError)
    }

    /// Status for the UI, built ONLY from persisted job rows + two live facts.
    static func snapshot(context: ModelContext, momentIds: Set<UUID>? = nil) -> AUQueueSnapshot {
        let all = (try? context.fetch(FetchDescriptor<AssetUnderstandingJobModel>())) ?? []
        let scoped: [AssetUnderstandingJobModel]
        if let momentIds {
            scoped = all.filter { momentIds.contains($0.momentId) }
        } else {
            // Unfinished work plus what finished recently, so "X of Y" reads as the current batch and an old
            // library never inflates it.
            let since = Date().addingTimeInterval(-recentWindow)
            scoped = all.filter { $0.state != .complete || $0.updatedAt >= since }
        }
        let facts = scoped.map(facts)
        return AUQueueStatusMapper.snapshot(moments: facts.map(\.momentId), understood: [], jobs: facts,
                                            isOnline: sharedIsOnline(), isDraining: drainInFlight)
    }

    // MARK: - One job

    private enum RunOutcome { case `continue`, stop }

    @discardableResult
    private func run(_ job: AssetUnderstandingJobModel) async -> RunOutcome {
        job.state = .running
        job.updatedAt = .now
        try? context.save()

        let url = MediaStore.shared.absoluteURL(for: job.relativeMediaPath)
        // If the media file is gone (Moment deleted), drop the job — no retry. Uses the injectable seam so a
        // test is not coupled to the device filesystem.
        if !fileExists(job.relativeMediaPath),
           job.relativeMediaPath.hasPrefix("media/") {
            Self.inFlight[job.momentId] = nil
            context.delete(job)
            try? context.save()
            return .continue
        }

        let tag = AULog.short(job.momentId)
        let started = Date()
        Self.inFlight[job.momentId] = AUInFlight(stage: 0, requestStartedAt: nil)
        func ms() -> Int { Int(Date().timeIntervalSince(started) * 1000) }
        do {
            AULog.queue.notice("au job=\(tag, privacy: .public) step=extract begin bg=\(Self.backgroundState(), privacy: .public)")
            let extract = extractFrames
            let frames = try await AUStepDeadline.run("extract", seconds: Self.localStepDeadline) { try await extract(url) }
            AULog.queue.notice("au job=\(tag, privacy: .public) step=extract ok frames=\(frames.count) ms=\(ms())")
            Self.inFlight[job.momentId] = AUInFlight(stage: 1, requestStartedAt: nil)
            var ctx: [String: Any]?
            if let j = job.captureContextJSON, let d = j.data(using: .utf8) {
                ctx = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
            }
            // P1-F (R1): compute the SOURCE file sha256 (full-file) off the main thread for the SAME file the
            // frames were just extracted from (so sha + frames refer to one file version). Best-effort — a
            // hash failure (missing/replaced file, read error) simply yields nil and AU proceeds WITHOUT an
            // evidence claim (caching unavailable this run; never blocks AU). Reuses the streaming upload hasher.
            let contentSha: String? = try await AUStepDeadline.run("hash", seconds: Self.localStepDeadline) {
                await Self.hashSource(url: url)
            }
            let requestStarted = Date()
            Self.inFlight[job.momentId] = AUInFlight(stage: 2, requestStartedAt: requestStarted)
            AUDiag.record("job \(tag) request begin app=\(Self.backgroundState()) prio=\(Self.priorityMomentIds.contains(job.momentId))")
            let dto = try await service.analyze(
                frames: frames,
                momentId: job.momentId,
                sourceCaptureId: job.sourceCaptureId,
                captureContext: ctx,
                contentSha256: contentSha
            )
            Self.inFlight[job.momentId] = nil
            Self.typicalRequestSeconds = AUTaskProgress.smoothed(Self.typicalRequestSeconds,
                                                                 Date().timeIntervalSince(requestStarted))
            AUDiag.record("job \(tag) ok ms=\(ms()) app=\(Self.backgroundState())")
            Self.priorityMomentIds.remove(job.momentId)
            try upsertUnderstanding(dto)
            job.state = .complete
            job.lastError = nil
            job.updatedAt = .now
            try? context.save()
            // Transient derived frames are released here (never persisted).
            return .continue
        } catch {
            Self.inFlight[job.momentId] = nil
            AUDiag.record("job \(tag) FAILED ms=\(ms()) app=\(Self.backgroundState()) error=\(String(describing: error).prefix(160))")
            if let timeout = error as? AUStepTimeout {
                // A LOCAL step (no paid request yet) never returned. Not a failure of the Moment: back to
                // PENDING, no attempt burned, and stop this drain so the single-flight lock is released and the
                // next foreground / reconnect / supervisor round starts fresh.
                job.state = .pending
                job.lastError = timeout.description
                job.updatedAt = .now
                try? context.save()
                return .stop
            }
            // Classify the failure to decide RETRY vs STOP (pre-beta AU-429 hardening). All state uses the
            // EXISTING persisted fields (attempts / nextEligibleAt / lastError / state) so the SwiftData
            // @Model shape is UNCHANGED (no migration; honors the FROZEN model + device-build gate).
            let disposition = AUDisposition.classify(error, isOnline: Self.sharedIsOnline())
            switch disposition {
            case .authPause:
                // Token rejected: not a failure of the work. Back to PENDING, no attempt burned, stop the drain.
                markAuthRequired(job)
                return .stop
            case .offlinePause:
                job.state = .pending
                job.lastError = AUMarker.offline
                job.updatedAt = .now
                try? context.save()
                return .stop
            case .cancelled:
                // System expiration / user cancel: put it back untouched (the interrupted request is retried
                // later; idempotent upsert guarantees one understanding per Moment).
                job.state = .pending
                job.updatedAt = .now
                try? context.save()
                return .stop
            default:
                break
            }
            job.lastError = String(describing: error).prefix(300).description
            let auErr = error as? AssetUnderstandingServiceError

            if case let .quotaExhausted(scope)? = auErr {
                // An ALLOWANCE is spent (daily gens / monthly USD / global breaker). Retrying now cannot
                // succeed — the cap clears when the PERIOD rolls over. Park the job PENDING but ineligible
                // until the next UTC-day boundary (the daily cap's reset; monthly/global clear later, re-checked
                // cheaply once a day). Do NOT burn an attempt — this is not a failure of the work, and we must
                // not let an exhausted cap push the job toward a hard-error ceiling.
                job.state = .pending
                job.nextEligibleAt = Self.nextUtcDayBoundary(after: Date())
                job.lastError = "quota_exhausted:\(scope) (deferred to next day)"
                job.updatedAt = .now
                try? context.save()
                return .continue
            }

            if case let .rateLimited(retryAfter)? = auErr {
                // TEMPORARY per-user rate cap (ai_sync 20/min window). Retryable: wait at least the server's
                // Retry-After, but never less than our own exponential backoff, plus jitter to avoid a
                // thundering-herd re-fire of a bulk import all coming eligible at the same instant. We reuse
                // the EXISTING `attempts` counter for the backoff curve (no new @Model field -> no migration);
                // a rate limit advancing `attempts` only lengthens its own backoff, which is the desired
                // self-throttling under sustained 429s and still clears to COMPLETE on the first 200.
                job.attempts += 1
                let serverWait = TimeInterval(max(0, retryAfter ?? 0))
                let base = max(serverWait, backoff(for: job.attempts))
                job.state = .pending
                job.nextEligibleAt = Date().addingTimeInterval(Self.withJitter(base))
                job.updatedAt = .now
                try? context.save()
                return .continue
            }

            // Transient (503 / transport) OR a hard error (badStatus / decoding). Transient errors are
            // retryable with bounded exponential backoff + jitter. A hard error is NOT expected to clear by
            // retrying; bound it by attempts so the queue stops hammering it (parks far out once the ceiling
            // is reached) while still surviving a restart (state persists).
            job.attempts += 1
            let retryable = disposition != .hardError   // unknown (non-AU) error -> treat as transient
            if !retryable && job.attempts >= Self.maxHardAttempts {
                // Permanent-looking failure that exhausted its bounded attempts: park far out (no terminal
                // state exists in the FROZEN model, so a distant nextEligibleAt is the no-migration stop).
                job.state = .pending
                job.nextEligibleAt = Date().addingTimeInterval(Self.hardErrorParkInterval)
            } else {
                job.state = .pending
                job.nextEligibleAt = Date().addingTimeInterval(Self.withJitter(backoff(for: job.attempts)))
            }
            job.updatedAt = .now
            try? context.save()
            return .continue
        }
    }

    // MARK: - Idempotent upsert of the understanding (§9)

    private func upsertUnderstanding(_ dto: MomentUnderstandingDTO) throws {
        let json = String(data: try StoryContractCoding.encoder().encode(dto), encoding: .utf8) ?? "{}"
        let momentId = dto.momentId
        if let existing = (try? context.fetch(
            FetchDescriptor<MomentUnderstandingModel>(
                predicate: #Predicate { $0.momentId == momentId }
            )
        ))?.first {
            existing.sourceCaptureId = dto.sourceCaptureId
            existing.schemaVersion = dto.schemaVersion
            existing.framePolicy = dto.framePolicy
            existing.promptVersion = dto.promptVersion
            existing.modelId = dto.modelId
            existing.nFrames = dto.nFrames
            existing.understandingJSON = json
            existing.updatedAt = .now
        } else {
            context.insert(MomentUnderstandingModel(
                momentId: dto.momentId,
                sourceCaptureId: dto.sourceCaptureId,
                schemaVersion: dto.schemaVersion,
                framePolicy: dto.framePolicy,
                promptVersion: dto.promptVersion,
                modelId: dto.modelId,
                nFrames: dto.nFrames,
                understandingJSON: json
            ))
        }
    }

    // MARK: - Queries

    private func existingJob(for momentId: UUID) -> AssetUnderstandingJobModel? {
        (try? context.fetch(
            FetchDescriptor<AssetUnderstandingJobModel>(
                predicate: #Predicate { $0.momentId == momentId }
            )
        ))?.first
    }

    /// True if a completed MomentUnderstanding already exists for this Moment — used to avoid re-analyzing a
    /// Moment whose original was merely RESTORED (R6). A restored original is the SAME verified bytes, so its
    /// understanding is still valid; re-running AU (and the coverage it invalidates) is pure waste.
    private func hasCompletedUnderstanding(momentId: UUID) -> Bool {
        // v2-aware (06v2 §9): a Moment with a CURRENT-version understanding is not
        // re-analyzed (R7-restore no-reanalysis guarantee holds for v2 records). A stale
        // v1 record does NOT block — it stays usable but the Moment is eligible for lazy
        // v2 enrichment when next used. Bulk re-analysis is never triggered here.
        let current = schemaVersion
        return ((try? context.fetch(
            FetchDescriptor<MomentUnderstandingModel>(
                predicate: #Predicate { $0.momentId == momentId && $0.schemaVersion == current }
            )
        ))?.first) != nil
    }

    private func nextEligibleJob(excluding skipped: Set<UUID> = []) -> AssetUnderstandingJobModel? {
        let now = Date()
        var desc = FetchDescriptor<AssetUnderstandingJobModel>(
            predicate: #Predicate { $0.stateRaw == "pending" && $0.nextEligibleAt <= now },
            sortBy: [SortDescriptor(\.createdAt, order: .forward)]
        )
        let eligible = ((try? context.fetch(desc)) ?? []).filter {
            !skipped.contains($0.momentId) && !Self.claimed.contains($0.momentId)
        }
        let prio = Self.priorityMomentIds
        return eligible.first { prio.contains($0.momentId) } ?? eligible.first
    }

    private func backoff(for attempts: Int) -> TimeInterval {
        let exp = baseBackoff * pow(4.0, Double(max(0, attempts - 1)))
        return min(exp, maxBackoff)
    }

    // MARK: - AU-429 retry policy helpers (pre-beta hardening; no @Model change)

    /// Hard (non-retryable) errors — a bad status or an undecodable body — are not expected to clear by
    /// retrying. Bound them so the queue stops hammering after a few attempts, then parks the job far out.
    static let maxHardAttempts = 4
    /// Where a hard error parks once its bounded attempts are spent (effectively "stop, but survive a restart
    /// and allow a much-later re-check" — there is no terminal-fail state in the FROZEN model to migrate to).
    static let hardErrorParkInterval: TimeInterval = 24 * 60 * 60

    /// Full-jitter on a backoff interval: a uniform random in [base/2, base]. Prevents a bulk import whose
    /// jobs all fail a rate-limit window at once from coming eligible on the same instant and re-bursting.
    static func withJitter(_ base: TimeInterval) -> TimeInterval {
        guard base > 0 else { return 0 }
        return base / 2 + Double.random(in: 0...(base / 2))
    }

    /// The next 00:00:00 UTC boundary strictly after `date`. A quota-exhausted job defers to here because the
    /// per-user DAILY generation allowance resets on the UTC day; monthly/global caps clear later but a daily
    /// re-check is a cheap, bounded way to resume without spinning.
    static func nextUtcDayBoundary(after date: Date) -> Date {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let start = cal.startOfDay(for: date)
        return cal.date(byAdding: .day, value: 1, to: start) ?? date.addingTimeInterval(24 * 60 * 60)
    }

    /// P1-F (R1): full-file sha256 of the source clip, computed OFF the main actor on a background task so the
    /// AU drain (which is @MainActor) never blocks the UI hashing a large video. Best-effort: any failure
    /// (missing/replaced file, read error) returns nil and AU proceeds without an evidence claim. Reuses the
    /// streaming upload hasher (never loads the whole file into memory) so there is no second hashing subsystem.
    nonisolated private static func hashSource(url: URL) async -> String? {
        await Task.detached(priority: .utility) {
            try? MediaUploadService.sha256Hex(fileURL: url)
        }.value
    }
}

/// Shared state of one drain across its workers (main actor only).
@MainActor
final class DrainRun {
    let maxJobs: Int
    let shouldContinue: () -> Bool
    var processed = 0
    var completedAny = false
    var skipped = Set<UUID>()
    var stopped = false
    var secondActive = false
    var secondTasks: [Task<Void, Never>] = []
    var spawnSecond: (() -> Void)?
    init(maxJobs: Int, shouldContinue: @escaping () -> Bool) {
        self.maxJobs = maxJobs
        self.shouldContinue = shouldContinue
    }
}

struct AUInFlight {
    var stage: Int
    var requestStartedAt: Date?
}

/// A tiny lock-protected flag (the expiration handler runs on an arbitrary queue).
final class AUStopGate: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var isSet: Bool { lock.lock(); defer { lock.unlock() }; return value }
    func set() { lock.lock(); value = true; lock.unlock() }
    func clear() { lock.lock(); value = false; lock.unlock() }
}
