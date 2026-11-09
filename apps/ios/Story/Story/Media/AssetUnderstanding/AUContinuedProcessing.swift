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
    private static let log = Logger(subsystem: "app.yotale", category: "au-continued")

    /// True ONLY while a system task is really running for this work — drives the "continues in the background"
    /// copy. Never claimed otherwise.
    private(set) static var isRunning = false
    private static var registered = false
    private static var submitted = false

    /// Replaces `Task { await queue.drain() }` at the user-initiated import sites. Always drains in the foreground
    /// right away; additionally asks the system to keep going if the user leaves.
    static func startAfterImport(queue: AssetUnderstandingQueue, context: ModelContext) {
        AssetUnderstandingQueue.stopGate.clear()
        Task { await queue.drain() }
        guard #available(iOS 26.0, *) else { return }
        let unfinished = AssetUnderstandingQueue.unfinishedMomentIds(context: context)
        guard unfinished.count >= minimumBatch else { return }
        submitIfNeeded(context: context, batchCount: unfinished.count)
    }

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
            guard ok else { log.error("register failed"); return }
            registered = true
        }
        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier,
            title: "Analyzing your Moments",
            subtitle: "\(batchCount) Moments"
        )
        request.strategy = .queue
        do {
            try BGTaskScheduler.shared.submit(request)
            submitted = true
        } catch {
            // Unavailable (Simulator) / NotPermitted / TooManyPendingTaskRequests: foreground-only, no harm done.
            log.notice("continued processing unavailable: \(String(describing: error), privacy: .public)")
        }
    }

    // MARK: - Supervisor

    @available(iOS 26.0, *)
    private static func supervise(_ box: TaskBox, context: ModelContext) async {
        let task = box.task
        submitted = false
        isRunning = true
        let finished = OSAllocatedUnfairLock(initialState: false)
        func complete(_ success: Bool) {
            let already = finished.withLock { v -> Bool in let o = v; v = true; return o }
            guard !already else { return }
            isRunning = false
            task.setTaskCompleted(success: success)
        }
        // Expiration/cancel: stop starting NEW jobs. The in-flight request is left to finish or be torn down by
        // suspension; it is never cancelled mid-flight (that would resend and double-bill on the next drain).
        task.expirationHandler = {
            AssetUnderstandingQueue.stopGate.set()
            Task { @MainActor in complete(false) }
        }

        let queue = AssetUnderstandingQueue(context: context)
        var batch = AssetUnderstandingQueue.unfinishedMomentIds(context: context)
        var doneAtLastLaunch = -1
        var fruitlessLaunches = 0
        var backoffSince: Date?
        let backoffPatience: TimeInterval = 180   // ride out a short 503/429 blip, never an endless one

        while !AssetUnderstandingQueue.stopGate.isSet, !finished.withLock({ $0 }) {
            batch.formUnion(AssetUnderstandingQueue.unfinishedMomentIds(context: context))   // later imports join
            let snap = AssetUnderstandingQueue.snapshot(context: context, momentIds: batch)
            task.progress.totalUnitCount = Int64(snap.total)
            task.progress.completedUnitCount = Int64(snap.done)
            task.updateTitle("Analyzing your Moments", subtitle: "\(snap.done) of \(snap.total) done")

            // Done, or waiting on something only the user / the clock / the network can supply.
            switch snap.state {
            case .idle, .complete, .waitingForNetwork, .waitingToSignIn, .usageLimit, .retryRequired:
                complete(snap.state == .complete || snap.state == .idle)
                return
            case .analyzing, .waitingToContinue, .retryingSoon:
                break
            }

            if snap.state == .retryingSoon {
                // Jobs are in ordinary backoff; the queue's own retry timer re-drains them. Just wait (bounded).
                let since = backoffSince ?? Date(); backoffSince = since
                if Date().timeIntervalSince(since) > backoffPatience { break }
            } else {
                backoffSince = nil
            }
            if !AssetUnderstandingQueue.isDraining, snap.state != .retryingSoon {
                // Launching another drain that made no progress since the previous launch, twice in a row, means
                // the rest is backing off / failing: stop instead of spinning. Jobs stay PENDING for the next
                // foreground / reconnect / retry timer.
                if snap.done == doneAtLastLaunch { fruitlessLaunches += 1 } else { fruitlessLaunches = 0 }
                if fruitlessLaunches >= 2 { break }
                doneAtLastLaunch = snap.done
                Task { @MainActor in await queue.drain() }
            }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        complete(false)
    }
}

/// BGTask is not Sendable; the supervisor hops straight onto the main actor, so a box is enough.
@available(iOS 26.0, *)
private final class TaskBox: @unchecked Sendable {
    let task: BGContinuedProcessingTask
    init(_ t: BGContinuedProcessingTask) { task = t }
}
