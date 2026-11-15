import Foundation

// AUQueueStatus — honest, PERSISTED-STATE-DRIVEN status for Asset Understanding (AU), plus the pure failure
// classification the queue uses. No SwiftData, no SwiftUI, no network: plain values in, plain values out, so it
// is unit-testable and cannot drift from what the queue actually stored.
//
// WHY THIS EXISTS (beta, 2026-11-08): after a hike import the Story showed "10 ready · 19 still being analyzed"
// indefinitely. That line was derived only from "does a MomentUnderstanding row exist", so it could not tell
// "running", "waiting for the app to be opened", "waiting for network", "daily limit reached" and "failed, needs a
// retry" apart — every one of them read as perpetual analysis. This maps the queue's own persisted job rows
// (state / attempts / nextEligibleAt / lastError) plus two LIVE facts (is the network up, is a drain running
// right now) to one of a small set of states with one honest sentence each. There is deliberately NO timer or
// optimistic percentage anywhere in here.

// MARK: - Persisted markers (written to AssetUnderstandingJobModel.lastError; no @Model change)

enum AUMarker {
    /// The server rejected our token (401/403). The job is NOT failed — it waits for a fresh token / sign-in.
    static let authRequired = "auth_required"
    /// A transport failure while the device had no network path. Not a failure of the work.
    static let offline = "offline"
    /// An allowance is spent (daily gens / monthly USD / global breaker) — see the queue's quota branch.
    static let quotaPrefix = "quota_exhausted"
}

// MARK: - Failure classification (pure)

/// What the queue should DO with a failed AU attempt. Only the first three never touch the retry budget:
/// none of them is a failure of the work itself.
enum AUDisposition: Equatable {
    /// Token rejected (401/403): pause the drain and wait for a refresh/sign-in. Never burns an attempt, so a
    /// token that expired in the background cannot walk a healthy job toward the 24-hour hard-error park.
    case authPause
    /// Transport failure while offline: pause the drain; resume when the network returns. Never burns an attempt.
    case offlinePause
    /// The attempt was cancelled (system expiration / user cancel / task cancellation). Never burns an attempt.
    case cancelled
    /// A spent allowance — parked until the next UTC day by the queue (existing behavior).
    case quotaPark
    /// Temporary per-user rate cap (existing behavior: honor Retry-After, jitter).
    case rateLimited(retryAfter: Int?)
    /// 503 / transport while ONLINE / unknown error — bounded exponential backoff (existing behavior).
    case transientRetry
    /// Bad status / undecodable body — bounded by attempts, then parked far out (existing behavior).
    case hardError

    static func classify(_ error: Error, isOnline: Bool) -> AUDisposition {
        if Self.isCancellation(error) { return .cancelled }
        guard let au = error as? AssetUnderstandingServiceError else {
            // A non-AU error (e.g. frame extraction): previously treated as transient. Offline is not its fault.
            return isOnline ? .transientRetry : .offlinePause
        }
        switch au {
        case .unauthorized:
            return .authPause
        case .quotaExhausted:
            return .quotaPark
        case .rateLimited(let ra):
            return .rateLimited(retryAfter: ra)
        case .transport(let inner):
            if Self.isCancellation(inner) { return .cancelled }
            return isOnline ? .transientRetry : .offlinePause
        case .unavailableRetryable:
            return .transientRetry
        case .badStatus, .decoding:
            return .hardError
        }
    }

    private static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let u = error as? URLError, u.code == .cancelled { return true }
        return (error as NSError).domain == NSURLErrorDomain && (error as NSError).code == NSURLErrorCancelled
    }
}

// MARK: - Plain facts about one job

/// A job as the status mapper sees it. Built from the persisted `AssetUnderstandingJobModel` by the caller.
struct AUJobFacts: Equatable {
    var momentId: UUID
    var state: AUJobState
    var attempts: Int
    var nextEligibleAt: Date
    var lastError: String?

    init(momentId: UUID, state: AUJobState, attempts: Int = 0, nextEligibleAt: Date = .distantPast, lastError: String? = nil) {
        self.momentId = momentId; self.state = state; self.attempts = attempts
        self.nextEligibleAt = nextEligibleAt; self.lastError = lastError
    }
}

// MARK: - Snapshot + mapper

struct AUQueueSnapshot: Equatable {
    enum State: Equatable {
        /// No analyzable Moments here (nothing to say).
        case idle
        /// Every analyzable Moment has an understanding.
        case complete
        /// A job is running now, or an eligible job is being drained right now.
        case analyzing
        /// A transient failure is backing off; the queue will try again on its own shortly.
        case retryingSoon
        /// Eligible work exists but nothing is draining — it continues the next time YoTale is open.
        case waitingToContinue
        case waitingForNetwork
        case waitingToSignIn
        /// An allowance is spent; resumes at the next UTC day.
        case usageLimit
        /// Only jobs that exhausted their bounded retries remain — needs a manual retry.
        case retryRequired
    }

    var total: Int
    var done: Int
    var state: State
    /// Jobs that exhausted their bounded retries (shown as an extra note when other work is still moving).
    var parkedForRetry: Int

    var remaining: Int { max(0, total - done) }
}

enum AUQueueStatusMapper {
    /// A pending job whose next attempt is farther out than this AND that spent its bounded attempts is "parked
    /// for retry" (the queue parks a hard error for 24h). Anything sooner is ordinary backoff.
    static let hardParkHorizon: TimeInterval = 6 * 3600
    /// Mirrors AssetUnderstandingQueue.maxHardAttempts (kept literal so this file stays dependency-free; a test
    /// asserts the two agree).
    static let hardAttempts = 4

    static func isParkedForRetry(_ j: AUJobFacts, now: Date) -> Bool {
        guard j.state == .pending, j.attempts >= hardAttempts else { return false }
        if (j.lastError ?? "").hasPrefix(AUMarker.quotaPrefix) { return false }   // quota has its own state
        return j.nextEligibleAt.timeIntervalSince(now) > hardParkHorizon
    }

    /// - Parameters:
    ///   - moments: the Moment ids to report on, in any order (duplicates ignored).
    ///   - understood: ids that already have a completed MomentUnderstanding.
    ///   - jobs: the persisted AU job facts (any Moments; unrelated ones are ignored).
    ///   - isOnline: the live network path (NOT persisted — a fact about right now).
    ///   - isDraining: whether a drain is processing jobs right now (live).
    static func snapshot(moments: [UUID], understood: Set<UUID>, jobs: [AUJobFacts],
                         isOnline: Bool, isDraining: Bool, now: Date = Date()) -> AUQueueSnapshot {
        var seen = Set<UUID>()
        let ids = moments.filter { seen.insert($0).inserted }
        var byId: [UUID: AUJobFacts] = [:]
        for j in jobs where byId[j.momentId] == nil { byId[j.momentId] = j }

        var total = 0, done = 0
        var remaining: [AUJobFacts] = []
        for id in ids {
            if understood.contains(id) { total += 1; done += 1; continue }
            guard let job = byId[id] else { continue }        // no job and no understanding: not analyzable (stills)
            total += 1
            if job.state == .complete { done += 1 } else { remaining.append(job) }
        }
        if remaining.isEmpty {
            return AUQueueSnapshot(total: total, done: done, state: total == 0 ? .idle : .complete, parkedForRetry: 0)
        }

        var parked = 0
        var present = Set<Category>()
        for j in remaining {
            if isParkedForRetry(j, now: now) { parked += 1; continue }
            present.insert(category(of: j, isOnline: isOnline, isDraining: isDraining, now: now))
        }
        let order: [Category] = [.analyzing, .network, .signIn, .waiting, .retrying, .limit]
        let state: AUQueueSnapshot.State
        if let first = order.first(where: { present.contains($0) }) {
            switch first {
            case .analyzing: state = .analyzing
            case .network:   state = .waitingForNetwork
            case .signIn:    state = .waitingToSignIn
            case .waiting:   state = .waitingToContinue
            case .retrying:  state = .retryingSoon
            case .limit:     state = .usageLimit
            }
        } else {
            state = .retryRequired                              // only parked-for-retry jobs remain
        }
        return AUQueueSnapshot(total: total, done: done, state: state, parkedForRetry: parked)
    }

    private enum Category: Hashable { case analyzing, network, signIn, waiting, retrying, limit }

    private static func category(of j: AUJobFacts, isOnline: Bool, isDraining: Bool, now: Date) -> Category {
        let err = j.lastError ?? ""
        if j.state == .running { return .analyzing }
        if err.hasPrefix(AUMarker.quotaPrefix), j.nextEligibleAt > now { return .limit }
        if err.hasPrefix(AUMarker.authRequired) { return .signIn }
        if !isOnline { return .network }                          // the live path, not a stale marker
        if j.nextEligibleAt <= now { return isDraining ? .analyzing : .waiting }
        return .retrying                                         // future nextEligibleAt, ordinary backoff
    }

    // MARK: - Copy

    /// One honest sentence for the Story Home status line, or nil when there is nothing to say.
    /// `continuesInBackground` is true ONLY while a system background task is actually running for this work —
    /// it is never claimed otherwise (the system does not guarantee completion).
    static func line(_ s: AUQueueSnapshot, continuesInBackground: Bool = false) -> String? {
        let progress = L10n.t("\(s.done) of \(s.total)")
        var out: String
        switch s.state {
        case .idle, .complete:
            return nil
        case .analyzing:
            out = L10n.t("Analyzing — \(progress) done")
            if continuesInBackground { out += L10n.t(" · continues in the background") }
        case .retryingSoon:
            out = L10n.t("\(progress) analyzed · retrying shortly")
        case .waitingToContinue:
            out = L10n.t("\(progress) analyzed · continues when YoTale is open")
        case .waitingForNetwork:
            out = L10n.t("\(progress) analyzed · waiting for network")
        case .waitingToSignIn:
            out = L10n.t("\(progress) analyzed · sign in to continue")
        case .usageLimit:
            out = L10n.t("\(progress) analyzed · paused, daily limit reached — resumes tomorrow")
        case .retryRequired:
            let n = max(1, s.parkedForRetry)
            return L10n.t("\(n) moments couldn't be analyzed")
        }
        if s.parkedForRetry > 0 { out += L10n.t(" · \(s.parkedForRetry) need a retry") }
        return out
    }

    /// Whether the status line should offer a Retry action (some job exhausted its bounded retries).
    static func offersRetry(_ s: AUQueueSnapshot) -> Bool { s.parkedForRetry > 0 || s.state == .retryRequired }
}


// MARK: - Background task progress (iOS continued processing)

/// Progress units for ONE Moment in the system background task. Steps the app can observe are REAL (frames
/// extracted, source hashed, analysis returned). The wait on the server's analysis is the one part the app
/// cannot observe, so while a request is in flight the value is ESTIMATED from recent request durations: it
/// rises toward, and never reaches, the request ceiling, and the jump to 100% happens only when the server
/// actually answers. Used ONLY for the system task's progress (the system expires a task whose progress stops
/// moving); Story Home's "X of Y done" stays strictly persisted-state.
enum AUTaskProgress {
    static let unitsPerMoment = 1000
    static let afterExtract = 100
    static let afterHash = 150
    /// The estimate never passes this; the remaining units arrive only with the real response.
    static let requestCeiling = 950

    static func units(stage: Int, requestElapsed: TimeInterval?, typicalRequest: TimeInterval) -> Int {
        switch stage {
        case ..<1: return 0
        case 1: return afterExtract
        default:
            guard let t = requestElapsed, t > 0 else { return afterHash }
            let tau = max(1, typicalRequest)
            let span = Double(requestCeiling - afterHash)
            let est = span * (1 - exp(-t / tau))
            return min(requestCeiling - 1, afterHash + Int(est))
        }
    }

    /// Exponential smoothing of real request durations, clamped to a sane band.
    static func smoothed(_ previous: TimeInterval, _ sample: TimeInterval) -> TimeInterval {
        min(90, max(8, previous * 0.7 + sample * 0.3))
    }
}
