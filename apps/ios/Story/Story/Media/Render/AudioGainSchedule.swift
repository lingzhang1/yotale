import AVFoundation

/// One audio track's gain changes, built so they can NEVER overlap.
///
/// AVFoundation throws an Objective-C exception (`-[AVScheduledAudioParameters _setRamp:]`, an uncatchable
/// SIGABRT) when a volume point or ramp lands inside another ramp on the same track. On beta (2026-11-12) a
/// 0.79 s final shot put the soundtrack's segment-start volume point inside the 1 s end fade, so every render —
/// and every relaunch that resumed it — crashed. Instead of hoping the callers' times never collide, every change
/// is offered here with a priority; a change that would overlap one already accepted is skipped, and the
/// survivors are applied in time order. Times are quantised to the CMTime ticks AVFoundation will see, so the
/// overlap check is exact. Ramps may touch end-to-start; a point may not sit on a ramp (ends included).
struct AudioGainSchedule {
    static let timescale: CMTimeScale = 600

    enum Change: Equatable {
        case point(at: Int64, volume: Float)                          // ticks
        case ramp(start: Int64, end: Int64, from: Float, to: Float)   // ticks, end > start

        var start: Int64 {
            switch self {
            case .point(let t, _): return t
            case .ramp(let s, _, _, _): return s
            }
        }
        var end: Int64 {
            switch self {
            case .point(let t, _): return t
            case .ramp(_, let e, _, _): return e
            }
        }
    }

    static func ticks(_ seconds: Double) -> Int64? {
        guard seconds.isFinite else { return nil }
        return Int64((max(0, seconds) * Double(timescale)).rounded())
    }

    private(set) var accepted: [Change] = []

    private func collides(_ c: Change) -> Bool {
        accepted.contains { a in
            switch (a, c) {
            case (.point(let t1, _), .point(let t2, _)):
                return t1 == t2
            case (.ramp(let s, let e, _, _), .point(let t, _)), (.point(let t, _), .ramp(let s, let e, _, _)):
                return t >= s && t <= e
            case (.ramp(let s1, let e1, _, _), .ramp(let s2, let e2, _, _)):
                return s1 < e2 && s2 < e1
            }
        }
    }

    /// Offer a volume point at `seconds`; returns whether it was kept.
    @discardableResult
    mutating func point(_ volume: Float, at seconds: Double) -> Bool {
        guard let t = Self.ticks(seconds) else { return false }
        return offer(.point(at: t, volume: volume))
    }

    /// Offer a ramp over [start, end] seconds; an empty or backwards ramp is skipped.
    @discardableResult
    mutating func ramp(from: Float, to: Float, start: Double, end: Double) -> Bool {
        guard let s = Self.ticks(start), let e = Self.ticks(end), e > s else { return false }
        return offer(.ramp(start: s, end: e, from: from, to: to))
    }

    /// Offer a level point; if it falls on an accepted ramp, move it to one tick after that ramp ends (once),
    /// but never to or past `limit` seconds (the end fade's start). A point that cannot be placed is skipped.
    @discardableResult
    mutating func pointOrAfterRamp(_ volume: Float, at seconds: Double, before limit: Double? = nil) -> Bool {
        guard let t = Self.ticks(seconds) else { return false }
        let cap = limit.flatMap(Self.ticks) ?? Int64.max
        guard t < cap else { return false }
        if offer(.point(at: t, volume: volume)) { return true }
        let covering = accepted.compactMap { c -> Int64? in
            if case .ramp(let s, let e, _, _) = c, t >= s, t <= e { return e }
            return nil
        }
        guard let after = covering.max(), after + 1 < cap else { return false }
        return offer(.point(at: after + 1, volume: volume))
    }

    private mutating func offer(_ c: Change) -> Bool {
        guard !collides(c) else { return false }
        accepted.append(c)
        return true
    }

    /// The accepted changes in time order.
    var ordered: [Change] { accepted.sorted { ($0.start, $0.end) < ($1.start, $1.end) } }

    /// Apply the accepted changes to `p`, in time order.
    func apply(to p: AVMutableAudioMixInputParameters) {
        let ts = Self.timescale
        for c in ordered {
            switch c {
            case .point(let t, let v):
                p.setVolume(v, at: CMTime(value: t, timescale: ts))
            case .ramp(let s, let e, let f, let to):
                p.setVolumeRamp(fromStartVolume: f, toEndVolume: to,
                                timeRange: CMTimeRange(start: CMTime(value: s, timescale: ts),
                                                       end: CMTime(value: e, timescale: ts)))
            }
        }
    }
}
