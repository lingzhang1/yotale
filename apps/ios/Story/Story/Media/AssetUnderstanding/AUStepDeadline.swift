import Foundation
import os

// AUStepDeadline — bounds the LOCAL, unbilled steps of one AU job (frame extraction, source hashing) so a step
// that never returns (seen on device: AVFoundation decode stalled after the app was backgrounded) can no longer
// hold the process-wide single-flight drain forever. The paid network request is NOT wrapped: URLSession's own
// request/resource timeouts bound it, and abandoning it early could resend and double-bill.
//
// The hung work is abandoned, not awaited: a TaskGroup would wait for its never-finishing child, so this races
// two unstructured tasks and resumes exactly once.

struct AUStepTimeout: Error, CustomStringConvertible {
    let step: String
    let seconds: TimeInterval
    var description: String { "step_timeout:\(step) after \(Int(seconds))s" }
}

enum AUStepDeadline {
    static func run<T: Sendable>(
        _ step: String,
        seconds: TimeInterval,
        _ work: @escaping @Sendable () async throws -> T
    ) async throws -> T {
        let once = OSAllocatedUnfairLock(initialState: false)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<T, Error>) in
            func finish(_ r: Result<T, Error>) {
                let first = once.withLock { done -> Bool in
                    if done { return false }
                    done = true
                    return true
                }
                if first { cont.resume(with: r) }
            }
            let worker = Task {
                do { finish(.success(try await work())) } catch { finish(.failure(error)) }
            }
            Task {
                try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                worker.cancel()   // cooperative; the extractor checks Task.isCancelled between frames
                finish(.failure(AUStepTimeout(step: step, seconds: seconds)))
            }
        }
    }
}

/// Privacy-safe AU diagnostics: step names, short moment id prefix, durations and app state only.
enum AULog {
    static let queue = Logger(subsystem: "app.yotale", category: "au-queue")
    static func short(_ id: UUID) -> String { String(id.uuidString.prefix(8)) }
}
