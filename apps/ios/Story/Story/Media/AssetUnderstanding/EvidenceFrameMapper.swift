import Foundation

// EvidenceFrameMapper — device port of packages/evidence_mapper, frame-selection policy v2 (evidence_select/2).
//
// ONE shared rule for Highlights and Full Story: the opening, the closing, every AU event and every visual
// candidate get visual evidence on the Moment's contact sheet; the editorial type only sets PRIORITY when the
// frame budget cannot hold everything. The frame count adapts to how much distinct evidence the Moment has
// (never below the previous duration rule, never above 9). Spec:
// docs/architecture/editorial-pipeline-v2/evidence-frame-selection-v2.md. The Python module is the reference;
// packages/evidence_mapper/fixtures/parity_v2.json pins identical outputs (EvidenceSelectionParityTests).
// Change all three together.
//
// Integer milliseconds throughout; rounding is half-away-from-zero and every sort has an explicit final tie-break,
// so the two implementations agree exactly. AU intervals and peak_time are ADVISORY (IMG_9091); sampled
// timestamps are provenance only; the model `evidence` string is never consulted.

enum EvidenceVideoType {
    case highlights, fullStory

    /// Which priority (Highlights vs Full Story) this attempt's contact sheets use. The attempt's own resolved
    /// editorial type wins (Original = Story selection/default, Revise = base output's type, Explore = requested or
    /// parent type); only when the attempt carries none (legacy/unstamped base) do we fall back to the Story's
    /// legacy `editorialMode` seed, preserving prior behavior for that case.
    static func forAttempt(editorialType: String?, legacyStoryMode: String?) -> EvidenceVideoType {
        switch editorialType {
        case EditorialType.fullStory.rawValue: return .fullStory
        case EditorialType.highlights.rawValue: return .highlights
        default: return (legacyStoryMode?.lowercased() == "full") ? .fullStory : .highlights
        }
    }
}

/// An AU interval: visual candidate, narrative candidate, or event. Seconds. `end <= start` is a point.
/// `peak` is advisory and only used as payoff context.
struct EvidenceCandidate: Equatable {
    let start: Double
    let end: Double
    let peak: Double?
    let confidence: Double?

    init(start: Double, end: Double, peak: Double?, confidence: Double?) {
        self.start = start; self.end = end; self.peak = peak; self.confidence = confidence
    }

    /// A point (no interval), e.g. an AU event persisted without `end_time`.
    static func point(_ t: Double) -> EvidenceCandidate {
        EvidenceCandidate(start: t, end: t, peak: nil, confidence: nil)
    }
}

/// The priority-ordered frame list for one Moment and its adaptive frame count.
struct FrameRanking: Equatable {
    /// Sampled-frame indices in priority order (<= maxFrames), or for `uniform` every index in time order.
    let ordered: [Int]
    let budget: Int
    let coreCount: Int
    let contextCount: Int
    /// No AU evidence at all: selection is the previous uniform overview.
    let uniform: Bool
}

/// Diagnostic only: how many AU intervals of each kind have a selected frame in their zone. Not semantic proof.
struct EvidenceCoverage: Equatable {
    var eventsCovered = 0, eventsTotal = 0
    var visualCovered = 0, visualTotal = 0
    var narrativeCovered = 0, narrativeTotal = 0
    var unrepresented: Int { (eventsTotal - eventsCovered) + (visualTotal - visualCovered) }
}

enum EvidenceFrameMapper {
    static let policyVersion = "evidence_select/2"
    static let minFrames = 4   // previous Tier-1 lower bound
    static let maxFrames = 9   // previous Tier-1 upper bound (and the sheet layout limit)

    // MARK: - ranking (the algorithm; mirrors evidence_mapper.rank_frames)

    static func rank(videoType: EvidenceVideoType, sampledFrameMs ms: [Int], events: [EvidenceCandidate],
                     visual: [EvidenceCandidate], narrative: [EvidenceCandidate]) -> FrameRanking {
        let n = ms.count
        if n == 0 { return FrameRanking(ordered: [], budget: 0, coreCount: 0, contextCount: 0, uniform: false) }
        let vis = byStart(visual), nar = byStart(narrative), evs = byStart(events)
        let floorFrames = durationFloor(Double(ms[n - 1]) / 1000.0)

        if vis.isEmpty && nar.isEmpty && evs.isEmpty {
            return FrameRanking(ordered: Array(0..<n), budget: min(floorFrames, n), coreCount: 0,
                                contextCount: 0, uniform: true)
        }

        let spacing = spacingMs(ms)
        let minGap = (3 * spacing) / 2
        let ctxGap = max(minGap, min(2 * minGap, 1500))
        var chosen: [Int] = []

        @discardableResult
        func add(_ i: Int) -> Bool {
            guard i >= 0, !chosen.contains(i), chosen.count < maxFrames else { return false }
            chosen.append(i); return true
        }
        func free() -> [Int] { (0..<n).filter { !chosen.contains($0) } }

        // 2) core coverage, in type priority order
        let core: [EvidenceCandidate] = videoType == .fullStory ? evs + nar + vis : vis + evs
        for c in core {
            let z = zone(c, spacing)
            if !covered(ms, z, chosen) { add(pickForZone(ms, z, chosen, minGap)) }
        }

        // 1) opening + closing context (a frame in the edge zone already serves); they lead the priority list
        let edge = min(2000, max(spacing, (ms[n - 1] * 15) / 100))
        let byTime = chosen.sorted { ms[$0] != ms[$1] ? ms[$0] < ms[$1] : $0 < $1 }
        let opening = byTime.first(where: { ms[$0] <= edge }) ?? 0
        let closing = byTime.reversed().first(where: { ms[$0] >= ms[n - 1] - edge }) ?? (n - 1)
        let lead = opening == closing ? [opening] : [opening, closing]
        chosen = Array((lead + chosen.filter { !lead.contains($0) }).prefix(maxFrames))
        let coreCount = chosen.count

        // 3) primary context
        func addContextNear(_ t: Int) {
            let i = nearest(ms, t, free())
            if i >= 0 && distToChosen(ms, i, chosen) >= ctxGap { add(i) }
        }
        func peakContext(_ cands: [EvidenceCandidate], aftermath: Bool) {
            for c in cands {
                let a = roundHalfAway(c.start * 1000)
                let b = roundHalfAway(c.end * 1000)
                if let pk = c.peak {
                    let p = roundHalfAway(pk * 1000)
                    if a - spacing <= p && p <= max(a, b) + spacing { addContextNear(p) }   // ungrounded: ignored
                }
                if aftermath && b - a >= 2 * spacing { addContextNear(zone(c, spacing).1) }
            }
        }
        func progressionContext(_ cands: [EvidenceCandidate]) {
            for c in cands {
                let z = zone(c, spacing)
                let inside = free().filter { z.0 <= ms[$0] && ms[$0] <= z.1 }
                guard var best = inside.first else { continue }
                for i in inside.dropFirst() {
                    let di = distToChosen(ms, i, chosen), db = distToChosen(ms, best, chosen)
                    if di > db { best = i }                       // ties keep the lower index
                }
                if distToChosen(ms, best, chosen) >= ctxGap { add(best) }
            }
        }
        if videoType == .fullStory { progressionContext(nar) } else { peakContext(vis, aftermath: true) }
        let contextCount = chosen.count - coreCount

        // 4) secondary (not counted in the budget)
        if videoType == .fullStory {
            peakContext(vis, aftermath: false)
        } else {
            for c in nar {
                let z = zone(c, spacing)
                if !covered(ms, z, chosen) { add(pickForZone(ms, z, chosen, minGap)) }
            }
        }

        // 5) gap fill up to maxFrames (prefix-stable whole-Moment coverage)
        while chosen.count < min(maxFrames, n) {
            let pts = chosen.sorted { ms[$0] != ms[$1] ? ms[$0] < ms[$1] : $0 < $1 }
            var bestGap = -1, bestMid = 0
            for k in 0..<(pts.count - 1) {
                let g = ms[pts[k + 1]] - ms[pts[k]]
                if g > bestGap { bestGap = g; bestMid = (ms[pts[k]] + ms[pts[k + 1]]) / 2 }
            }
            if !add(nearest(ms, bestMid, free())) { break }
        }

        let budget = min(max(floorFrames, coreCount + contextCount), maxFrames, n)
        return FrameRanking(ordered: chosen, budget: budget, coreCount: coreCount, contextCount: contextCount,
                            uniform: false)
    }

    /// The k-frame selection in time order: the first k of the priority list, or for a uniform Moment an even
    /// subsample of its uniform overview.
    static func select(_ r: FrameRanking, count k: Int) -> [Int] {
        let k = max(0, k)
        if r.uniform { return overviewIndices(n: r.ordered.count, k: k).map { r.ordered[$0] }.sorted() }
        return Array(r.ordered.prefix(k)).sorted()
    }

    /// The previous Tier-1 frame count, kept as the lower bound: max(4, min(9, round(duration / 8))).
    static func durationFloor(_ durationS: Double) -> Int {
        max(minFrames, min(maxFrames, roundHalfAway(durationS / 8.0)))
    }

    static func coverage(sampledFrameMs ms: [Int], selected: [Int], events: [EvidenceCandidate],
                         visual: [EvidenceCandidate], narrative: [EvidenceCandidate]) -> EvidenceCoverage {
        let spacing = spacingMs(ms)
        func count(_ cs: [EvidenceCandidate]) -> Int { cs.filter { covered(ms, zone($0, spacing), selected) }.count }
        return EvidenceCoverage(eventsCovered: count(events), eventsTotal: events.count,
                                visualCovered: count(visual), visualTotal: visual.count,
                                narrativeCovered: count(narrative), narrativeTotal: narrative.count)
    }

    /// Back-compatible entry point (ascending indices). With `budget` nil the adaptive budget is used; otherwise
    /// the first `budget` frames of the same priority list.
    static func selectFrames(videoType: EvidenceVideoType, sampledFrameMs: [Int],
                             visualCandidates: [EvidenceCandidate], narrativeCandidates: [EvidenceCandidate],
                             eventTimesS: [Double] = [], events: [EvidenceCandidate]? = nil,
                             budget: Int?) -> [Int] {
        let evs = events ?? eventTimesS.map { EvidenceCandidate.point($0) }
        let r = rank(videoType: videoType, sampledFrameMs: sampledFrameMs, events: evs,
                     visual: visualCandidates, narrative: narrativeCandidates)
        if r.ordered.isEmpty { return [] }
        let k = budget ?? r.budget
        if k <= 0 { return [] }
        if k >= sampledFrameMs.count { return Array(0..<sampledFrameMs.count) }
        return select(r, count: k)
    }

    // MARK: - helpers (each mirrors the Python helper of the same name)

    static func roundHalfAway(_ x: Double) -> Int {
        x >= 0 ? Int((x + 0.5).rounded(.down)) : -Int((-x + 0.5).rounded(.down))
    }

    static func spacingMs(_ ms: [Int]) -> Int {
        guard ms.count >= 2 else { return 1000 }
        let gaps = (1..<ms.count).map { ms[$0] - ms[$0 - 1] }.sorted()
        return max(1, gaps[(gaps.count - 1) / 2])
    }

    static func zone(_ c: EvidenceCandidate, _ spacing: Int) -> (Int, Int) {
        let a = roundHalfAway(c.start * 1000)
        let b = max(a, roundHalfAway(c.end * 1000))
        if b - a < 2 * spacing {
            let mid = (a + b) / 2, half = max(spacing, (b - a) / 2)
            return (mid - half, mid + half)
        }
        let q = (b - a) / 4
        return (a + q, b - q)
    }

    private static func nearest(_ ms: [Int], _ t: Int, _ pool: [Int]) -> Int {
        var best = -1, bestD = Int.max
        for i in pool {
            let d = abs(ms[i] - t)
            if d < bestD { best = i; bestD = d }
        }
        return best
    }

    private static func distToChosen(_ ms: [Int], _ i: Int, _ chosen: [Int]) -> Int {
        chosen.map { abs(ms[i] - ms[$0]) }.min() ?? 1_000_000_000_000
    }

    private static func covered(_ ms: [Int], _ z: (Int, Int), _ chosen: [Int]) -> Bool {
        chosen.contains { z.0 <= ms[$0] && ms[$0] <= z.1 }
    }

    private static func pickForZone(_ ms: [Int], _ z: (Int, Int), _ chosen: [Int], _ minGap: Int) -> Int {
        let centre = (z.0 + z.1) / 2
        let inside = (0..<ms.count).filter { z.0 <= ms[$0] && ms[$0] <= z.1 && !chosen.contains($0) }
        let distinct = inside.filter { distToChosen(ms, $0, chosen) >= minGap }
        if !distinct.isEmpty { return nearest(ms, centre, distinct) }
        if !inside.isEmpty { return nearest(ms, centre, inside) }
        let free = (0..<ms.count).filter { !chosen.contains($0) }
        return free.isEmpty ? -1 : nearest(ms, centre, free)
    }

    private static func byStart(_ cands: [EvidenceCandidate]) -> [EvidenceCandidate] {
        cands.enumerated().sorted { x, y in
            let sx = roundHalfAway(x.element.start * 1000), sy = roundHalfAway(y.element.start * 1000)
            if sx != sy { return sx < sy }
            let cx = x.element.confidence ?? 0, cy = y.element.confidence ?? 0
            if cx != cy { return cx > cy }
            return x.offset < y.offset
        }.map { $0.element }
    }

    static func overviewIndices(n: Int, k: Int) -> [Int] {
        if n <= 0 || k <= 0 { return [] }
        if k >= n { return Array(0..<n) }
        if k == 1 { return [0] }
        var out = Set<Int>()
        for i in 0..<k { out.insert(roundHalfAway(Double(i) / Double(k - 1) * Double(n - 1))) }
        return out.sorted()
    }
}

// MARK: - Editorial guidance (shared by the cache-hit AND cache-miss paths)

/// The AU information that steers frame selection for one Moment: the attempt's video type plus the Moment's
/// events and visual/narrative candidates (all ADVISORY, parsed from its local MomentUnderstanding). Cached AU
/// frames and freshly extracted frames go through the SAME ranking with the SAME guidance.
struct EditorialFrameGuidance {
    let videoType: EvidenceVideoType
    let visual: [EvidenceCandidate]
    let narrative: [EvidenceCandidate]
    let events: [EvidenceCandidate]

    init(videoType: EvidenceVideoType, visual: [EvidenceCandidate], narrative: [EvidenceCandidate],
         events: [EvidenceCandidate]) {
        self.videoType = videoType; self.visual = visual; self.narrative = narrative; self.events = events
    }

    /// Point events (start times only).
    init(videoType: EvidenceVideoType, visual: [EvidenceCandidate], narrative: [EvidenceCandidate],
         eventTimesS: [Double]) {
        self.init(videoType: videoType, visual: visual, narrative: narrative,
                  events: eventTimesS.map { EvidenceCandidate.point($0) })
    }

    var eventTimesS: [Double] { events.map { $0.start } }

    /// True when the Moment has ANY AU evidence (events or candidates). Without it selection is the previous
    /// uniform overview — nothing is fabricated.
    var hasCandidates: Bool { !visual.isEmpty || !narrative.isEmpty || !events.isEmpty }
}

/// Frames ranked for one Moment: the priority-ordered frames actually held (<= 9, or every frame for a uniform
/// Moment) and the adaptive frame count. `frames(count:)` gives the time-ordered selection for any payload tier.
struct RankedFrames {
    let ordered: [AUExtractedFrame]
    let ranking: FrameRanking
    var preferred: Int { ranking.budget }

    func frames(count k: Int) -> [AUExtractedFrame] {
        let k = max(0, k)
        if ranking.uniform {
            return EvidenceFrameMapper.overviewIndices(n: ordered.count, k: k).map { ordered[$0] }
        }
        return Array(ordered.prefix(k)).sorted { $0.tMs < $1.tMs }
    }
}

extension EvidenceFrameMapper {
    /// Rank a Moment's frames (cached AU frames or freshly extracted ones — the same rule either way). Keeps only
    /// the frames a sheet can use, so holding many Moments' frames for the payload ladder stays small.
    static func rank(_ frames: [AUExtractedFrame], guidance: EditorialFrameGuidance?) -> RankedFrames {
        let sorted = frames.sorted { $0.tMs < $1.tMs }
        let g = guidance
        let r = rank(videoType: g?.videoType ?? .highlights, sampledFrameMs: sorted.map { $0.tMs },
                     events: g?.events ?? [], visual: g?.visual ?? [], narrative: g?.narrative ?? [])
        let held = r.ordered.map { sorted[$0] }
        // Re-index the held ranking so RankedFrames.ordered[i] corresponds to ranking.ordered position i.
        let local = FrameRanking(ordered: Array(0..<held.count), budget: r.budget, coreCount: r.coreCount,
                                 contextCount: r.contextCount, uniform: r.uniform)
        return RankedFrames(ordered: held, ranking: local)
    }

    /// Coverage of a submitted sheet given only its frame timestamps. Zones use the au_frames/1 spacing
    /// (24 frames across the Moment), matching how the frames were sampled. Diagnostic counts only.
    static func coverage(selectedMs: [Int], durationSeconds: Double, events: [EvidenceCandidate],
                         visual: [EvidenceCandidate], narrative: [EvidenceCandidate]) -> EvidenceCoverage {
        let n = MomentFrameExtractor.frameCount
        let spacing = max(1, roundHalfAway(durationSeconds * 1000 / Double(n - 1)))
        let synthetic = (0..<n).map { roundHalfAway(Double($0 * spacing)) }   // only `spacing` is used for zones
        var c = coverage(sampledFrameMs: synthetic, selected: [], events: events, visual: visual,
                         narrative: narrative)
        func count(_ cs: [EvidenceCandidate]) -> Int {
            cs.filter { cand in
                let z = zone(cand, spacing)
                return selectedMs.contains { z.0 <= $0 && $0 <= z.1 }
            }.count
        }
        c.eventsCovered = count(events); c.visualCovered = count(visual); c.narrativeCovered = count(narrative)
        return c
    }

    /// The time-ordered selection of `count` frames from `frames` under `guidance` (the adaptive count when nil).
    static func selectExtracted(_ frames: [AUExtractedFrame], guidance: EditorialFrameGuidance?,
                                count: Int? = nil) -> [AUExtractedFrame] {
        guard !frames.isEmpty else { return [] }
        let r = rank(frames, guidance: guidance)
        return r.frames(count: count ?? r.preferred)
    }
}

// MARK: - Cache-hit retrieval

enum AUEvidenceCacheHit {
    /// Attempt a cache hit for one Moment: fetch the authorized evidence package (identity, source SHA,
    /// extraction version and blob integrity are validated server-side at retrieval and again by the service)
    /// and unpack the ORIGINAL accepted AU frames, in time order. Returns nil on ANY miss/validation/transport
    /// failure so the caller falls back to restore + extract. Selection happens in the shared ranking, and the
    /// sheet is built under the shared payload budget — a cache hit has no exemption. Needs no local video.
    static func fetchFrames(momentId: UUID,
                            service: AUEvidenceService = AUEvidenceService()) async -> [AUExtractedFrame]? {
        do {
            let (manifest, download) = try await service.fetchManifest(momentId: momentId)
            let packed = try await service.downloadPacked(download, manifest: manifest)
            let frames = try service.unpackFrames(packed, manifest: manifest)
            return frames.isEmpty ? nil : frames.sorted { $0.tMs < $1.tMs }
        } catch {
            return nil   // any miss/integrity/transport failure -> caller uses the restore/extract fallback
        }
    }
}
