import Foundation

// VisualEvidencePreparation — planning-time contact-sheet preparation for EVERY eligible Moment (P1-F pre-beta).
//
// Eligibility is cloud-aware (completed AU + positive duration + a renderable source that may be local OR
// cloud-restorable), so a Moment whose original was safely evicted from the device still gets visual evidence.
// Per eligible Moment, in order:
//   A. CACHE   — fetch the authorized AU evidence package and use the original accepted AU frames. This needs NO
//                source video, so it works while the original is cloud-only, and it never triggers a restore.
//   B. MISS    — use the local source if present; otherwise restore it through the existing R6 resolver
//                (restoring ONLY cache misses, never a cache hit), then extract frames.
//   C. NONE    — the source genuinely cannot be obtained: the Moment gets no sheet (truthful diagnostics, listed
//                in `restoreUnavailableIds`), exactly as before. Nothing is fabricated.
// Both A and B select frames with the same editorial mapper (EditorialFrameGuidance), and every resulting sheet
// goes through ONE `MultimodalVisualBudget` pass: same tier ladder, same per-sheet and total ceilings, same
// degradation, same miss-reason accounting. There is no cache-specific exemption.
//
// Pure of SwiftData and of the network: the caller injects the three side effects as closures, which keeps the
// whole algorithm unit-testable. Render-time restoration is a separate step and is not touched here.

/// One eligible Moment as planning-time evidence preparation sees it.
struct EvidenceMomentRef {
    let momentId: UUID
    /// Planner duration (fresh local probe when on disk, else the persisted/cloud metadata). > 0 for eligible.
    let durationSeconds: Double
    let usefulSegmentCount: Int
    let guidance: EditorialFrameGuidance
}

struct EvidencePreparationResult {
    let sheets: [MomentContactSheet]
    /// Lowercased Moment id -> why an eligible Moment that reached the budget did NOT get a sheet.
    let sheetMissReasons: [String: SheetMissReason]
    /// Lowercased ids of cache-miss Moments whose source could not be restored (stage C).
    let restoreUnavailableIds: [String]
    let budget: VisualBudgetResult
    // Counts for privacy-safe diagnostics (never ids or content).
    let eligibleCount: Int
    let cacheHitCount: Int
    let cacheMissCount: Int
    let restoredCount: Int
    let guidedCount: Int
    let uniformCount: Int
    /// What the attached sheets cost on the wire (raw JPEG + multipart framing), i.e. the number the ceiling used.
    let wireBytes: Int
}

enum VisualEvidencePreparation {

    @MainActor
    static func prepare(
        moments: [EvidenceMomentRef],
        localURL: (UUID) -> URL?,
        fetchCachedFrames: (EvidenceMomentRef) async -> [AUExtractedFrame]?,
        restoreSources: ([UUID]) async -> (restored: [UUID: URL], unavailable: [UUID]),
        limits: VisualBudgetLimits = VisualBudgetLimits()
    ) async -> EvidencePreparationResult {

        // A. cache lookup for EVERY eligible Moment, local or not.
        var cached: [UUID: [AUExtractedFrame]] = [:]
        var misses: [EvidenceMomentRef] = []
        for m in moments {
            if let frames = await fetchCachedFrames(m), !frames.isEmpty { cached[m.momentId] = frames }
            else { misses.append(m) }
        }

        // B. misses: local source if present, otherwise restore (misses only).
        var sourceURL: [UUID: URL] = [:]
        var needRestore: [UUID] = []
        for m in misses {
            if let url = localURL(m.momentId) { sourceURL[m.momentId] = url } else { needRestore.append(m.momentId) }
        }
        var unavailable: [UUID] = []
        if !needRestore.isEmpty {
            let r = await restoreSources(needRestore)
            for (id, url) in r.restored { sourceURL[id] = url }
            unavailable = r.unavailable
        }

        // One input per Moment that has frames or a source, in the caller's (stable) order.
        var inputs: [VisualBudgetInput] = []
        for m in moments {
            if let frames = cached[m.momentId] {
                inputs.append(VisualBudgetInput(
                    momentId: m.momentId, url: nil, durationSeconds: m.durationSeconds,
                    usefulSegmentCount: m.usefulSegmentCount, eventCount: m.guidance.eventTimesS.count,
                    guidance: m.guidance, cachedFrames: frames))
            } else if let url = sourceURL[m.momentId] {
                inputs.append(VisualBudgetInput(
                    momentId: m.momentId, url: url, durationSeconds: m.durationSeconds,
                    usefulSegmentCount: m.usefulSegmentCount, eventCount: m.guidance.eventTimesS.count,
                    guidance: m.guidance))
            }
        }

        // Shared budget: cache hits and extracted sheets compete under the same ceilings.
        let budget = await MultimodalVisualBudget.build(inputs, limits: limits)

        let guided = moments.filter { $0.guidance.hasCandidates }.count
        return EvidencePreparationResult(
            sheets: budget.sheets,
            sheetMissReasons: budget.sheetMissReasons,
            restoreUnavailableIds: unavailable.map { $0.uuidString.lowercased() },
            budget: budget,
            eligibleCount: moments.count,
            cacheHitCount: cached.count,
            cacheMissCount: misses.count,
            restoredCount: needRestore.count - unavailable.count,
            guidedCount: guided,
            uniformCount: moments.count - guided,
            wireBytes: MultimodalVisualBudget.wireBytes(budget.sheets, limits: limits))
    }
}
