import Foundation

/// While the user is waiting on AI Ideas (scene scan upload + Director), background network work must not
/// compete for the uplink. Beta 2026-11-23: the 576 KB scan took 20.2 s to arrive while an AU upload was in
/// flight, against a 7.5 s model call.
///
/// A hold stops the AU queue, the media upload queue and the generated-output backup queue from STARTING new
/// jobs. A job already in flight always finishes (never cancels a billed AU request or a part upload). When
/// the last hold ends, `onRelease` re-drains the queues. Every hold expires on its own after
/// `maxHoldSeconds`, so a caller that never ends its hold cannot stall background work.
@MainActor
enum InteractiveAIHold {
    static let maxHoldSeconds: TimeInterval = 90

    /// Set once by StoryApp to re-drain the background queues. Default no-op (tests / before setup).
    static var onRelease: @MainActor () -> Void = { }

    private static var holders: [UUID: Task<Void, Never>] = [:]

    static var isHeld: Bool { !holders.isEmpty }

    /// Start a hold. Returns its token; pass it to `end`.
    static func begin() -> UUID {
        let id = UUID()
        holders[id] = Task { @MainActor in
            try? await Task.sleep(nanoseconds: UInt64(maxHoldSeconds * 1_000_000_000))
            guard !Task.isCancelled else { return }
            end(id)
        }
        return id
    }

    /// End a hold. Safe to call twice or with nil. Re-drains the queues when the last hold ends.
    static func end(_ id: UUID?) {
        guard let id, let expiry = holders.removeValue(forKey: id) else { return }
        expiry.cancel()
        if holders.isEmpty { onRelease() }
    }
}
