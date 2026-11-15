import Foundation
import SwiftData
import BackgroundTasks
import os

// AUContinuedProcessing — lets Asset Understanding keep going for a while after the user backgrounds YoTale
// FOLLOWING A USER-INITIATED IMPORT (iOS 26+ BGContinuedProcessingTask). It is a SUPERVISOR around the existing
// queue, not a second queue:
//
//  - Queue ownership stays with AssetUnderstandingQueue (persisted jobs, backoff, quota, auth, single-flight).
//    The supervisor never analyzes anything itself; it only makes sure a drain is running and reports REAL
//    progress (Moments completed of Moments in the batch, read from the persisted rows ~1/s). No timers feed the
//    progress value and nothing is extrapolated.
//  - Only user-initiated imports start it. It is never used to auto-resume the queue at launch (Apple: system or
//    maintenance work may be cancelled), and a lone short clip does not justify system UI (minimumBatch).
//  - Nothing is guaranteed: the system may refuse (`submit` throws), delay (strategy .queue), or expire the task.
//    On expiration/cancel we set the queue's stop gate (honored BETWEEN jobs; the in-flight billed request is
//    never cancelled, so there is no duplicate resend), report success:false, and the remaining jobs simply stay
//    PENDING for the next foreground / reconnect / retry.
//  - One static identifier, one active task at a time; handlers cannot be unregistered so we register once.
//  - Below iOS 26 (deployment target is 18.5) or on a Simulator everything degrades to the plain foreground drain.
@MainActor
enum AUContinuedProcessing {
    /// Must match Info.plist `BGTaskSchedulerPermittedIdentifiers` ($(PRODUCT_BUNDLE_IDENTIFIER).au.import).
    static var identifier: String { (Bundle.main.bundleIdentifier ?? "app.yotale") + ".au.import" }
    /// Smallest import that earns a system-visible task (≈15 s of analysis per clip).
    static let minimumBatch = 3
    nonisolated private static let log = Logger(subsystem: "app.yotale", category: "au-continued")

    /// True ONLY while a system task is really running for this work — drives the "continues in the background"
    /// copy. Never claimed otherwise.
    private(set) static var isRunning = false
    private static var registered = false
    private static var submitted = false

    /// Replaces `Task { await queue.drain() }` at the user-initiated import sites. Always drains in the foreground
    /// right away; additionally asks the system to keep going if the user leaves.
    ///
    /// `momentIds` = the Moments THIS user action is about (the import, or nil for a Retry of everything). They
    /// run first (ahead of older library backlog) and they alone define the task's progress and success, so an
    /// unrelated stuck Moment elsewhere can neither inflate "X of Y" nor turn a finished import into "failed".
    static func startAfterImport(queue: AssetUnderstandingQueue, context: ModelContext, momentIds: Set<UUID>? = nil) {
        AssetUnderstandingQueue.stopGate.clear()
        let unfinished = AssetUnderstandingQueue.unfinishedMomentIds(context: context)
        let scope = momentIds.map { $0.intersection(unfinished) } ?? unfinished
        if !isRunning && !submitted { taskBatch.removeAll() }   // a refused/finished task's batch is stale
        AssetUnderstandingQueue.priorityMomentIds.formUnion(scope)
        taskBatch.formUnion(scope)   // a running task picks these up on its next tick
        Task { await queue.drain() }
        guard #available(iOS 26.0, *) else { return }
        guard taskBatch.count >= minimumBatch else { return }
        submitIfNeeded(context: context, batchCount: taskBatch.count)
    }

    /// Moments the current/pending system task reports on. Grows with later imports; cleared when it ends.
    private static var taskBatch = Set<UUID>()

    @available(iOS 26.0, *)
    private static func submitIfNeeded(context: ModelContext, batchCount: Int) {
        guard !submitted, !isRunning else { return }   // one task; a running one already picks up new jobs
        if !registered {
            // Dynamic registration immediately before submit is the documented pattern for continued tasks.
            let ok = BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { task in
                guard let task = task as? BGContinuedProcessingTask else {
                    task.setTaskCompleted(success: false)
                    return
                }
                let box = TaskBox(task)
                Task { @MainActor in await supervise(box, context: context) }
            }
            guard ok else { AUDiag.record("bgtask register failed"); return }
            registered = true
        }
        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier,
            title: L10n.t("Analyzing your Moments"),
            subtitle: L10n.t("\(batchCount) Moments")
        )
        request.strategy = .queue
        do {
            try BGTaskScheduler.shared.submit(request)
            submitted = true
            AUDiag.record("bgtask submitted batch=\(batchCount) app=\(AssetUnderstandingQueue.backgroundState())")
        } catch {
            // Unavailable (Simulator) / NotPermitted / TooManyPendingTaskRequests: foreground-only, no harm done.
            AUDiag.record("bgtask submit refused: \(String(describing: error).prefix(160))")
        }
    }

    // MARK: - Supervisor

    @available(iOS 26.0, *)
    private static func supervise(_ box: TaskBox, context: ModelContext) async {
        let task = box.task
        submitted = false
        isRunning = true
        AssetUnderstandingQueue.parallelWorkersEnabled = true   // two analyses at once while the task runs
        AUDiag.record("bgtask started app=\(AssetUnderstandingQueue.backgroundState())")
        let finished = OSAllocatedUnfairLock(initialState: false)
        func complete(_ success: Bool, _ reason: String) {
            let already = finished.withLock { v -> Bool in let o = v; v = true; return o }
            guard !already else { return }
            isRunning = false
            AssetUnderstandingQueue.parallelWorkersEnabled = false   // back to one at a time
            taskBatch.removeAll()
            AUDiag.record("bgtask completed success=\(success) reason=\(reason)")
            task.setTaskCompleted(success: success)
        }
        // Expiration/cancel: stop starting NEW jobs. The in-flight request is left to finish or be torn down by
        // suspension; it is never cancelled mid-flight (that would resend and double-bill on the next drain).
        task.expirationHandler = {
            AUDiag.record("bgtask EXPIRED (system expiry or user cancel)")
            AssetUnderstandingQueue.stopGate.set()
            Task { @MainActor in complete(false, "expiration_handler") }
        }

        let queue = AssetUnderstandingQueue(context: context)
        var doneAtLastLaunch = -1
        var fruitlessLaunches = 0
        var backoffSince: Date?
        var lastState: AUQueueSnapshot.State?
        var lastApp = ""
        var stopReason = "stop_gate (expired/cancelled)"
        var highWater: Int64 = 0   // the system progress value never moves backwards (e.g. a job re-queued)
        let backoffPatience: TimeInterval = 180   // ride out a short 503/429 blip, never an endless one

        while !AssetUnderstandingQueue.stopGate.isSet, !finished.withLock({ $0 }) {
            // The job already in flight when the task started is real work this task carries out: count it, so
            // progress is not stuck at 0 while it finishes (device: expired 30 s after backgrounding at 0/6 while
            // an older backlog job, outside the batch, was mid-request).
            for id in AssetUnderstandingQueue.inFlight.keys where !taskBatch.contains(id) {
                taskBatch.insert(id)
                AUDiag.record("supervisor adopted in-flight job \(AULog.short(id))")
            }
            AssetUnderstandingQueue.kickParallel()
            let snap = AssetUnderstandingQueue.snapshot(context: context, momentIds: taskBatch)   // later imports join
            // Per-step progress: real for the steps the app observes, ESTIMATED only while waiting on the server
            // (AUTaskProgress). The system expires a task whose progress stops moving; a single 30-50 s request
            // with no movement was enough to get it expired on device.
            let now = Date()
            let typical = AssetUnderstandingQueue.typicalRequestSeconds
            var units = snap.done * AUTaskProgress.unitsPerMoment
            for (id, f) in AssetUnderstandingQueue.inFlight where taskBatch.contains(id) {
                units += AUTaskProgress.units(stage: f.stage,
                                              requestElapsed: f.requestStartedAt.map { now.timeIntervalSince($0) },
                                              typicalRequest: typical)
            }
            let totalUnits = Int64(snap.total * AUTaskProgress.unitsPerMoment)
            highWater = min(totalUnits, max(highWater, Int64(units)))
            task.progress.totalUnitCount = totalUnits
            task.progress.completedUnitCount = highWater
            task.updateTitle(L10n.t("Analyzing your Moments"), subtitle: L10n.t("\(snap.done) of \(snap.total) done"))

            // Done, or waiting on something only the user / the clock / the network can supply.
            let app = AssetUnderstandingQueue.backgroundState()
            if snap.state != lastState || app != lastApp {
                AUDiag.record("supervisor state=\(snap.state) done=\(snap.done)/\(snap.total) draining=\(AssetUnderstandingQueue.isDraining) app=\(app)")
                lastState = snap.state
                lastApp = app
            }
            switch snap.state {
            case .idle, .complete, .waitingForNetwork, .waitingToSignIn, .usageLimit, .retryRequired:
                complete(snap.state == .complete || snap.state == .idle, "end_state=\(snap.state) done=\(snap.done)/\(snap.total)")
                return
            case .analyzing, .waitingToContinue, .retryingSoon:
                break
            }

            if snap.state == .retryingSoon {
                // Jobs are in ordinary backoff; the queue's own retry timer re-drains them. Just wait (bounded).
                let since = backoffSince ?? Date(); backoffSince = since
                if Date().timeIntervalSince(since) > backoffPatience { stopReason = "backoff_patience done=\(snap.done)"; break }
            } else {
                backoffSince = nil
            }
            if !AssetUnderstandingQueue.isDraining, snap.state != .retryingSoon {
                // Launching another drain that made no progress since the previous launch, twice in a row, means
                // the rest is backing off / failing: stop instead of spinning. Jobs stay PENDING for the next
                // foreground / reconnect / retry timer.
                if snap.done == doneAtLastLaunch { fruitlessLaunches += 1 } else { fruitlessLaunches = 0 }
                if fruitlessLaunches >= 2 { stopReason = "no_progress done=\(snap.done)"; break }
                doneAtLastLaunch = snap.done
                Task { @MainActor in await queue.drain() }
            }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        complete(false, stopReason)
    }
}

/// BGTask is not Sendable; the supervisor hops straight onto the main actor, so a box is enough.
@available(iOS 26.0, *)
private final class TaskBox: @unchecked Sendable {
    let task: BGContinuedProcessingTask
    init(_ t: BGContinuedProcessingTask) { task = t }
}
