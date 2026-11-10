import Foundation

// EvidenceFrameMapper — DETERMINISTIC device-side port of packages/evidence_mapper (P1-F §7).
//
// Picks WHICH cached sampled frames a per-Video-Type contact sheet should contain. Same algorithm as the
// Python mapper (kept in lockstep): distinct-first round-robin across candidates (never confidence-collapse),
// representative-first context (region center, then setup/aftermath, peak last — ADVISORY), whole-Moment
// overview floor, uniform full-budget fallback when there are no candidates. Changes frame RELEVANCE, not
// count: returns a subset within the existing per-Moment budget. Candidate peaks/intervals are advisory;
// sampled timestamps are provenance only; the model `evidence` string is never consulted.

enum EvidenceVideoType {
    case highlights, fullStory

    /// Which selection rule (Highlights vs Full Story) this attempt's contact sheets use. The attempt's own
    /// resolved editorial type wins (Original = Story selection/default, Revise = base output's type,
    /// Explore = requested or parent type); only when the attempt carries none (legacy/unstamped base) do we
    /// fall back to the Story's legacy `editorialMode` seed, preserving prior behavior for that case.
    static func forAttempt(editorialType: String?, legacyStoryMode: String?) -> EvidenceVideoType {
        switch editorialType {
        case EditorialType.fullStory.rawValue: return .fullStory
        case EditorialType.highlights.rawValue: return .highlights
        default: return (legacyStoryMode?.lowercased() == "full") ? .fullStory : .highlights
        }
    }
}

struct EvidenceCandidate {
    let start: Double      // seconds
    let end: Double
    let peak: Double?
    let confidence: Double?
}

enum EvidenceFrameMapper {
    static let contextPadSeconds = 1.5

    /// Return chosen sampled-frame INDICES (ascending, de-duplicated, <= budget).
    static func selectFrames(videoType: EvidenceVideoType,
                             sampledFrameMs: [Int],
                             visualCandidates: [EvidenceCandidate],
                             narrativeCandidates: [EvidenceCandidate],
                             eventTimesS: [Double],
                             budget: Int) -> [Int] {
        let n = sampledFrameMs.count
        if n == 0 || budget <= 0 { return [] }
        if budget >= n { return Array(0..<n) }

        var cands = (videoType == .highlights) ? visualCandidates : narrativeCandidates
        if videoType == .fullStory {
            for t in eventTimesS { cands.append(EvidenceCandidate(start: t, end: t, peak: nil, confidence: nil)) }
        }

        // overview floor — full budget when no candidates (clean uniform), else ~half to leave room.
        let overviewK = cands.isEmpty ? budget : max(2, min(budget / 2 + 1, budget))
        var chosen: [Int] = overviewIndices(n: n, k: overviewK)

        // distinct-first round-robin over representative-first context lists.
        let ranked = rankCandidates(cands)
        let ctxLists = ranked.map { contextIndices(sampledFrameMs: sampledFrameMs, c: $0) }
        var cursors = [Int](repeating: 0, count: ctxLists.count)
        var progressed = true
        func count() -> Int { Set(chosen).count }
        while count() < budget && progressed {
            progressed = false
            for ci in ctxLists.indices {
                if count() >= budget { break }
                let ctx = ctxLists[ci]
                while cursors[ci] < ctx.count && chosen.contains(ctx[cursors[ci]]) { cursors[ci] += 1 }
                if cursors[ci] < ctx.count {
                    chosen.append(ctx[cursors[ci]]); cursors[ci] += 1; progressed = true
                }
            }
        }

        // top-up to full budget with uniform overview if candidates underfilled it.
        if count() < budget {
            for idx in overviewIndices(n: n, k: budget) {
                if !chosen.contains(idx) { chosen.append(idx) }
                if count() >= budget { break }
            }
        }

        var seen = Set<Int>(); var ordered: [Int] = []
        for idx in chosen where !seen.contains(idx) {
            seen.insert(idx); ordered.append(idx)
            if ordered.count >= budget { break }
        }
        return ordered.sorted()
    }

    // MARK: - helpers (mirror the Python mapper exactly)

    private static func nearestIndex(_ sampledFrameMs: [Int], _ tMs: Int) -> Int {
        var best = 0, bestD = Int.max
        for (i, t) in sampledFrameMs.enumerated() {
            let d = abs(t - tMs)
            if d < bestD { best = i; bestD = d }
        }
        return best
    }

    private static func overviewIndices(n: Int, k: Int) -> [Int] {
        if n <= 0 || k <= 0 { return [] }
        if k >= n { return Array(0..<n) }
        if k == 1 { return [0] }
        var out = Set<Int>()
        for i in 0..<k { out.insert(Int((Double(i) / Double(k - 1) * Double(n - 1)).rounded())) }
        return out.sorted()
    }

    private static func contextIndices(sampledFrameMs: [Int], c: EvidenceCandidate) -> [Int] {
        let padMs = Int(contextPadSeconds * 1000)
        let mid = (c.start + c.end) / 2.0
        var targets = [Int(mid * 1000), Int(c.start * 1000) - padMs, Int(c.end * 1000) + padMs]
        if let peak = c.peak { targets.append(Int(peak * 1000)) }   // advisory — never first/alone
        var out: [Int] = []
        for t in targets {
            let idx = nearestIndex(sampledFrameMs, t)
            if !out.contains(idx) { out.append(idx) }
        }
        return out
    }

    private static func rankCandidates(_ cands: [EvidenceCandidate]) -> [EvidenceCandidate] {
        // earlier start first (stable temporal axis); confidence only a weak tiebreak. NOT confidence-sorted.
        cands.sorted { a, b in
            let sa = (a.start * 1000).rounded() / 1000, sb = (b.start * 1000).rounded() / 1000
            if sa != sb { return sa < sb }
            return (a.confidence ?? 0) > (b.confidence ?? 0)
        }
    }
}

// MARK: - Editorial guidance (shared by the cache-hit AND cache-miss paths)

/// The AU editorial information that steers frame SELECTION for one Moment: the attempt's video type plus the
/// Moment's visual/narrative candidates and event times (all ADVISORY, parsed from its local
/// MomentUnderstanding). The cache-hit path feeds it to the mapper over the cached AU timestamps; the
/// cache-miss path feeds the SAME value to the SAME mapper over the freshly extracted timestamps, so both
/// paths select frames by the same editorial rule (P1-F pre-beta alignment).
struct EditorialFrameGuidance {
    let videoType: EvidenceVideoType
    let visual: [EvidenceCandidate]
    let narrative: [EvidenceCandidate]
    let eventTimesS: [Double]

    /// True when the mapper would have at least one candidate for this video type. Mirrors the mapper's own
    /// candidate selection (Highlights = visual; Full Story = narrative + events). When false there is no
    /// editorial signal, so callers keep the plain uniform-coverage selection — nothing is fabricated.
    var hasCandidates: Bool {
        switch videoType {
        case .highlights: return !visual.isEmpty
        case .fullStory: return !narrative.isEmpty || !eventTimesS.isEmpty
        }
    }
}

extension EvidenceFrameMapper {
    /// Cache-MISS selection: choose which of the freshly extracted frames go on the sheet. With editorial
    /// candidates, runs the existing mapper over the ACTUAL extracted timestamps (the source pixels may differ
    /// from AU's accepted JPEGs, but the choice is still guided by the Moment's editorial information). With
    /// no guidance or no candidates, falls back to the existing even subsample (uniform coverage, unchanged).
    static func selectExtracted(_ frames: [AUExtractedFrame], guidance: EditorialFrameGuidance?,
                                count: Int) -> [AUExtractedFrame] {
        guard let g = guidance, g.hasCandidates, count > 0, !frames.isEmpty else {
            return MomentContactSheetBuilder.evenlySubsample(frames, count: count)
        }
        let idx = selectFrames(videoType: g.videoType, sampledFrameMs: frames.map { $0.tMs },
                               visualCandidates: g.visual, narrativeCandidates: g.narrative,
                               eventTimesS: g.eventTimesS, budget: count)
        let picked = idx.compactMap { $0 < frames.count ? frames[$0] : nil }
        return picked.isEmpty ? MomentContactSheetBuilder.evenlySubsample(frames, count: count) : picked
    }
}

// MARK: - Cache-hit retrieval

enum AUEvidenceCacheHit {
    /// Attempt a cache hit for one Moment: fetch the authorized evidence package (identity, source SHA,
    /// extraction version and blob integrity are validated server-side at retrieval and again by the service),
    /// unpack the ORIGINAL accepted AU frames, and let the editorial mapper pick the Tier-1 subset. Returns the
    /// selected frames (ascending `tMs`) or nil on ANY miss/validation/transport failure so the caller falls
    /// back to restore + extract. It deliberately does NOT build a contact sheet: the frames join the shared
    /// `MultimodalVisualBudget` like every other source, so a cache hit has no payload-budget exemption. It
    /// needs no local video, so it works for a cloud-only/evicted source.
    static func fetchSelectedFrames(momentId: UUID,
                                    guidance: EditorialFrameGuidance,
                                    budget: ContactSheetBudget,
                                    service: AUEvidenceService = AUEvidenceService()) async -> [AUExtractedFrame]? {
        do {
            let (manifest, download) = try await service.fetchManifest(momentId: momentId)
            let packed = try await service.downloadPacked(download, manifest: manifest)
            let allFrames = try service.unpackFrames(packed, manifest: manifest)
            let picked = EvidenceFrameMapper.selectFrames(
                videoType: guidance.videoType, sampledFrameMs: manifest.sampledFrameMs,
                visualCandidates: guidance.visual, narrativeCandidates: guidance.narrative,
                eventTimesS: guidance.eventTimesS, budget: budget.framesPerMoment)
            let selected = picked.compactMap { i in i < allFrames.count ? allFrames[i] : nil }
            return selected.isEmpty ? nil : selected
        } catch {
            return nil   // any miss/integrity/transport failure -> caller uses the restore/extract fallback
        }
    }
}
