import Foundation
import os
import Darwin

/// Create/render performance timeline (diagnostic only). Each stage emits one PUBLIC os_log line plus an
/// os_signpost interval, so the Xcode console and Instruments show the same stages.
///
/// Line format:  render-timing op=<8> t=<ms since op start> stage=<name> ms=<duration> <detail> mem=<MB> thermal=<0-3>
///   - `op` is the first 8 characters of the Create attempt's operation id, so every stage of one attempt
///     (including background work such as the cloud backup) can be correlated.
///   - `t` is the wall-clock END of the stage relative to the op start. Stages that overlap (e.g. concurrent
///     evidence fetches) must be read from `t`, not summed from `ms`.
/// Carries no user content: stage names, counts, byte sizes and timings only. No ids beyond the op prefix,
/// no URLs, tokens, prompts or media. Filter the console with `render-timing`.
enum RenderTiming {
    private static let log = Logger(subsystem: "ai.yotale.story", category: "timing")
    private static let signposter = OSSignposter(subsystem: "ai.yotale.story", category: "timing")

    private static let lock = NSLock()
    private static var _op: String = "-"
    private static var _opStart: CFAbsoluteTime = CFAbsoluteTimeGetCurrent()

    /// Start a new timeline (one Create attempt). Later stages report `t` relative to this moment.
    static func startOperation(_ operationId: String) {
        lock.lock(); defer { lock.unlock() }
        _op = String(operationId.prefix(8))
        _opStart = CFAbsoluteTimeGetCurrent()
    }

    private static func context() -> (String, Int) {
        lock.lock(); defer { lock.unlock() }
        return (_op, Int((CFAbsoluteTimeGetCurrent() - _opStart) * 1000))
    }

    /// Marks the start of a stage; call `end(_:)` on the returned value.
    struct Mark {
        let stage: String
        let start: CFAbsoluteTime
        let state: OSSignpostIntervalState
        func end(_ detail: String = "") {
            let ms = Int((CFAbsoluteTimeGetCurrent() - start) * 1000)
            RenderTiming.signposter.endInterval("stage", state)
            RenderTiming.emit(stage: stage, ms: ms, detail: detail)
        }
    }

    static func begin(_ stage: String) -> Mark {
        let id = signposter.makeSignpostID()
        let state = signposter.beginInterval("stage", id: id, "\(stage, privacy: .public)")
        return Mark(stage: stage, start: CFAbsoluteTimeGetCurrent(), state: state)
    }

    /// One line for a stage whose duration was measured elsewhere (or a point event with ms=0).
    static func emit(stage: String, ms: Int, detail: String = "") {
        let (op, t) = context()
        log.notice("render-timing op=\(op, privacy: .public) t=\(t) stage=\(stage, privacy: .public) ms=\(ms) \(detail, privacy: .public) mem=\(footprintMB()) thermal=\(ProcessInfo.processInfo.thermalState.rawValue)")
    }

    /// The app's current physical memory footprint in MB (what jetsam counts), or -1 if unavailable.
    static func footprintMB() -> Int {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return kr == KERN_SUCCESS ? Int(info.phys_footprint / 1_048_576) : -1
    }
}

/// Measures how long the MAIN THREAD fails to respond while a Create runs, and the peak memory footprint.
/// A background timer posts a no-op to the main queue every 50 ms and records how late it ran; a late block
/// means the main thread was busy (the UI could not respond). Diagnostic only; costs one tiny block per tick.
final class MainThreadStallProbe: @unchecked Sendable {
    private let queue = DispatchQueue(label: "ai.yotale.story.stall-probe", qos: .utility)
    private var timer: DispatchSourceTimer?
    private let lock = NSLock()
    private var maxStallMs = 0
    private var stallsOver250 = 0
    private var peakMB = 0
    private var inFlight = false

    func start() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: .milliseconds(50))
        t.setEventHandler { [weak self] in self?.tick() }
        timer = t
        t.resume()
    }

    private func tick() {
        let mb = RenderTiming.footprintMB()
        lock.lock()
        if mb > peakMB { peakMB = mb }
        if inFlight { lock.unlock(); return }      // previous ping not answered yet: still stalled
        inFlight = true
        lock.unlock()
        let sent = CFAbsoluteTimeGetCurrent()
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            let lag = Int((CFAbsoluteTimeGetCurrent() - sent) * 1000)
            self.lock.lock()
            if lag > self.maxStallMs { self.maxStallMs = lag }
            if lag > 250 { self.stallsOver250 += 1 }
            self.inFlight = false
            self.lock.unlock()
        }
    }

    /// Stop and return (longest main-thread stall ms, number of stalls > 250 ms, peak footprint MB).
    func stop() -> (maxStallMs: Int, stallsOver250: Int, peakMB: Int) {
        timer?.cancel(); timer = nil
        lock.lock(); defer { lock.unlock() }
        return (maxStallMs, stallsOver250, peakMB)
    }
}
