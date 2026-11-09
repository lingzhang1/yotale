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

/// Durable AU diagnostics: the last 80 events (local time, privacy-safe) in UserDefaults, so the reason a
/// background run ended survives suspension, a detached debugger and relaunch. Printed at launch as AU_DIAG lines
/// and shown on Story Home in DEBUG builds. Also mirrored to the unified log.
enum AUDiag {
    private static let key = "au.diag.v1"
    private static let limit = 80
    private static let lock = NSLock()
    private static let fmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; return f
    }()

    static func record(_ line: String) {
        AULog.queue.notice("\(line, privacy: .public)")
        lock.lock(); defer { lock.unlock() }
        var lines = UserDefaults.standard.stringArray(forKey: key) ?? []
        lines.append("\(fmt.string(from: Date())) \(line)")
        if lines.count > limit { lines.removeFirst(lines.count - limit) }
        UserDefaults.standard.set(lines, forKey: key)
    }

    static func lines() -> [String] {
        lock.lock(); defer { lock.unlock() }
        return UserDefaults.standard.stringArray(forKey: key) ?? []
    }

    static func printAtLaunch() {
        for l in lines().suffix(40) { print("AU_DIAG \(l)") }
    }
}
