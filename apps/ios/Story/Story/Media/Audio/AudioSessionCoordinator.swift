import Foundation
import AVFoundation

// AudioSessionCoordinator — the single, serialized owner of AVAudioSession configuration + activation.
//
// WHY (P0, owner 2026-11-02): `AVAudioSession.setActive(true)` / `setCategory(...)` are SYNCHRONOUS system
// calls that can block for hundreds of ms. They were being invoked directly inside @MainActor SwiftUI view
// callbacks (music preview, result playback) — Apple's own warning: "AVAudioSession_iOS.mm:978 This method
// can lead to UI unresponsiveness if called on the main thread." A blocked main actor also starves other
// main-actor-scheduled async work (the Create submission `await` was observed never to enter while these ran).
//
// This coordinator moves every potentially-blocking audio-session operation off the main actor onto a single
// serialized executor (the actor), so:
//   - the main actor is never blocked waiting on a synchronous session call;
//   - concurrent preview / result-playback / capture configurations cannot race (actor serialization);
//   - callers `await` a quick hand-off and get the result back on the main actor for UI updates.
//
// It is deliberately MINIMAL: configure+activate, deactivate, and an idempotent guard to avoid redundant
// activation. It does not manage players, routes, or interruptions — those stay with their existing owners.
// Errors are PRESERVED and returned (never silently swallowed) so callers can surface honest state.

/// A compact, Sendable description of a desired audio-session configuration.
enum AudioSessionIntent: Equatable, Sendable {
    /// Media playback (music preview, result video). Routes to the speaker.
    case playback(mode: AVAudioSession.Mode)
    /// Fully deactivate playback and notify others (so capture / other apps resume).
    case deactivate

    static var playbackDefault: AudioSessionIntent { .playback(mode: .default) }
    static var moviePlayback: AudioSessionIntent { .playback(mode: .moviePlayback) }
}

/// Outcome of an audio-session operation, carried back to the caller (main actor) for honest UI state.
struct AudioSessionResult: Sendable {
    let succeeded: Bool
    let error: String?          // description of the thrown error, if any (never a raw secret/PII)
    let elapsedMs: Int
    let beganOnMainThread: Bool // diagnostic: whether the WORK began on the main thread (should be false)
    let redundant: Bool         // true when the intent matched the already-applied state (no system call made)
}

/// Serialized, off-main owner of AVAudioSession configuration. `actor` isolation guarantees the synchronous
/// session calls run on the actor's executor (never the main actor) and are serialized against each other.
actor AudioSessionCoordinator {
    static let shared = AudioSessionCoordinator()

    private var lastApplied: AudioSessionIntent?

    /// Apply an audio-session intent. Potentially-blocking system calls run HERE (off the main actor), so the
    /// caller's `await` returns control to the main actor without the main thread ever blocking on the system
    /// call. Idempotent: a repeated identical intent is a no-op (avoids redundant activation). Errors are
    /// captured and returned, never thrown into the UI (callers decide how to surface them).
    @discardableResult
    func apply(_ intent: AudioSessionIntent) async -> AudioSessionResult {
        let start = DispatchTime.now()
        let onMain = Thread.isMainThread   // expected false on the actor's executor; a diagnostic, not a gate
        if intent == lastApplied, case .playback = intent {
            return AudioSessionResult(succeeded: true, error: nil, elapsedMs: 0,
                                      beganOnMainThread: onMain, redundant: true)
        }
        let session = AVAudioSession.sharedInstance()
        var thrown: Error?
        do {
            switch intent {
            case .playback(let mode):
                try session.setCategory(.playback, mode: mode)
                try session.setActive(true)
            case .deactivate:
                try session.setActive(false, options: [.notifyOthersOnDeactivation])
            }
            lastApplied = intent
        } catch {
            thrown = error
            // A failed deactivate/activate should not leave a stale "applied" belief.
            if case .deactivate = intent { lastApplied = nil }
        }
        let elapsedMs = Int(Double(DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000.0)
        return AudioSessionResult(succeeded: thrown == nil,
                                  error: thrown.map { String(describing: $0).prefix(160).description },
                                  elapsedMs: elapsedMs, beganOnMainThread: onMain, redundant: false)
    }

    /// Reset the idempotency memory. Call when an external owner (capture / AVCaptureSession) may have changed
    /// the session underneath us, so the next `apply` always re-asserts rather than trusting a stale belief.
    func invalidate() { lastApplied = nil }
}
