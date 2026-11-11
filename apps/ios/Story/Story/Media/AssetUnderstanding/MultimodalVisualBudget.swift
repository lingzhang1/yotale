import Foundation
import AVFoundation

// MultimodalVisualBudget — MVP ADAPTIVE VISUAL-EVIDENCE PREFLIGHT.
//
// Goal: PRESERVE multimodal visual reasoning whenever possible instead of silently dropping to text-only
// because the image payload would exceed provider limits. Before the planning request is sent, this computes
// a deterministic visual budget and builds contact sheets that fit the request-size ceiling — WITHOUT a model
// call, WITHOUT fabricating evidence, and WITHOUT ever dropping a source Moment from planning (A1 text is kept
// for every eligible Moment; only VISUAL coverage is reduced).
//
// Adaptation ladder (deterministic, cheapest-degradation first), applied until the payload fits:
//   1. Resize oversized sheets      (smaller cell side)
//   2. Compress JPEGs               (lower quality floor)
//   3. Remove redundant frames      (fewer frames per Moment)
//   4. Reduce frames per Moment      (toward the minimum)
//   5. Reduce whole-Moment visual coverage  (sheets only for the highest-value Moments; the rest go text-only)
//
// Frame allocation uses evidence ALREADY available (AU useful_segments count, events, clip duration) to spend
// the frame budget where footage is richest — no extra model pass. Moment IDs and timestamps are stable.

struct VisualBudgetLimits {
    /// Server backstop is 20 MB total / 1 MB per sheet (apps/api _MM_EDIT_MAX_*). The device aims BELOW that so
    /// the server never has to reject — leaving headroom for the JSON body + transport framing.
    var maxTotalImageBytes: Int = 16 * 1024 * 1024     // 16 MB device target (< 20 MB server ceiling)
    var maxSheetBytes: Int = 900 * 1024                // 900 KB/sheet device target (< 1 MB server ceiling)
    var maxSheets: Int = 120
    /// Multipart framing per attached sheet (boundary line + Content-Disposition + Content-Type headers).
    /// Counted against the total ceiling so the budget is enforced on what is actually put on the wire, not
    /// only on the raw JPEG bytes. The server counts raw sheet bytes (20 MB); the device target (16 MB) leaves
    /// the remaining headroom for the JSON request part.
    var perSheetOverheadBytes: Int = 512
    /// Degradation floors — never go below these before falling back to text-only for a Moment.
    var minCellSide: CGFloat = 200
    var minJpegQuality: CGFloat = 0.45
    var minFramesPerMoment: Int = 3
}

struct VisualBudgetInput {
    let momentId: UUID
    /// Local source video. nil when this Moment's frames come from `cachedFrames` (cloud-only source that is
    /// deliberately NOT restored for planning) — a Moment needs one or the other.
    let url: URL?
    let durationSeconds: Double
    let usefulSegmentCount: Int     // from AU observed.useful_segments (richness signal)
    let eventCount: Int             // from AU observed.events (richness signal)
    /// AU guidance for FRAME SELECTION (events + candidates + this attempt's type). nil => uniform coverage.
    /// The same guidance ranks cached and extracted frames, and decides the Moment's adaptive frame count.
    var guidance: EditorialFrameGuidance? = nil
    /// Every frame of a valid cached AU evidence package (time order). When set, the sheet is built from these —
    /// no video, no extraction — under the SAME ranking, tier ladder and byte budget (no cache exemption).
    var cachedFrames: [AUExtractedFrame]? = nil
    /// Frames already ranked (e.g. a cache hit ranked as soon as it arrived, so only the frames a sheet can use
    /// are held). Takes precedence over `cachedFrames` and `url`.
    var ranked: RankedFrames? = nil
}

/// What the preflight decided and produced, plus diagnostics (never includes image bytes/content).
struct VisualBudgetResult {
    let sheets: [MomentContactSheet]       // sheets that fit; order matches `sheetOrder`
    let sheetOrder: [UUID]                 // Moment ids, one per sheet, in sheets[] order
    let momentsWithImages: Int
    let momentsTextOnly: Int               // Moments planned with A1 text only (visual coverage reduced)
    let totalImageBytes: Int
    let selectedTier: String               // human-readable tier label for diagnostics
    let appliedSteps: [String]             // which ladder steps were applied
    /// P0 evidence accounting: for every INPUT Moment that did NOT get a sheet, WHY (low-cardinality reason).
    /// Keyed by lowercased Moment UUID. A Moment with a sheet is absent from this map. Never includes bytes.
    let sheetMissReasons: [String: SheetMissReason]
}

enum MultimodalVisualBudget {

    /// Build the largest visual payload that fits the limits, degrading deterministically. Returns the sheets
    /// to attach + the id order; Moments without a sheet are still planned (text-only A1) by the caller.
    static func build(_ inputs: [VisualBudgetInput],
                      limits: VisualBudgetLimits = VisualBudgetLimits()) async -> VisualBudgetResult {
        var applied: [String] = []

        // Rank Moments by visual richness so, if we must reduce COVERAGE (step 5), the richest keep images.
        let ranked = inputs.sorted { lhs, rhs in
            let l = richness(lhs), r = richness(rhs)
            if l != r { return l > r }
            return lhs.momentId.uuidString < rhs.momentId.uuidString   // stable tiebreak
        }

        // Tier knobs we will walk through (steps 1-4). Each tuple = (cell, quality, frameScale, label).
        // frameScale multiplies each Moment's adaptive frame count (then clamped to minFramesPerMoment).
        let tiers: [(cell: CGFloat, q: CGFloat, fscale: Double, label: String)] = [
            (320, 0.70, 1.00, "tier1"),
            (300, 0.65, 1.00, "tier1-resized"),
            (280, 0.58, 0.80, "tier1-compressed"),
            (240, 0.52, 0.60, "tier1-fewer-frames"),
            (limits.minCellSide, limits.minJpegQuality, 0.0, "tier1-min"),   // fscale 0 => minFramesPerMoment
        ]

        // Produce and rank every Moment's frames ONCE (cached frames as-is, local video extracted once); every
        // tier below selects from that same ranking, so cached and extracted frames follow one rule.
        let (frameSets, prepMisses) = await rankedFrames(for: ranked)

        // Try each tier at FULL coverage; if even the smallest tier overflows, reduce coverage (step 5).
        for (ti, tier) in tiers.enumerated() {
            let (sheets, misses) = buildSheets(ranked, frameSets, prepMisses, tier: tier, limits: limits)
            let total = wireBytes(sheets, limits: limits)
            if ti >= 1 && !applied.contains("resize") { applied.append("resize") }
            if ti >= 2 && !applied.contains("compress") { applied.append("compress") }
            if ti >= 3 && !applied.contains("reduce-frames") { applied.append("reduce-frames") }
            if total <= limits.maxTotalImageBytes && sheets.count <= limits.maxSheets {
                return VisualBudgetResult(
                    sheets: sheets, sheetOrder: sheets.map { $0.momentId },
                    momentsWithImages: sheets.count, momentsTextOnly: inputs.count - sheets.count,
                    totalImageBytes: sheets.reduce(0) { $0 + $1.jpeg.count }, selectedTier: tier.label,
                    appliedSteps: applied, sheetMissReasons: misses)
            }
        }

        // Step 5: smallest tier still overflows -> reduce COVERAGE. Keep the richest Moments' sheets until the
        // byte budget is hit; the rest plan text-only. A1 text still covers every Moment (caller's job).
        applied.append("reduce-coverage")
        let smallest = tiers.last!
        let (allSheets, smallestMisses) = buildSheets(ranked, frameSets, prepMisses, tier: smallest, limits: limits)
        var kept: [MomentContactSheet] = []
        var running = 0
        var misses = smallestMisses
        for s in allSheets {   // allSheets is in richness order (ranked)
            if running + s.jpeg.count + limits.perSheetOverheadBytes > limits.maxTotalImageBytes
                || kept.count >= limits.maxSheets {
                misses[s.momentId.uuidString.lowercased()] = .budgetCoverageDropped   // sized but cut by budget
                continue
            }
            kept.append(s); running += s.jpeg.count + limits.perSheetOverheadBytes
        }
        return VisualBudgetResult(
            sheets: kept, sheetOrder: kept.map { $0.momentId },
            momentsWithImages: kept.count, momentsTextOnly: inputs.count - kept.count,
            totalImageBytes: kept.reduce(0) { $0 + $1.jpeg.count }, selectedTier: smallest.label + "+partial-coverage",
            appliedSteps: applied, sheetMissReasons: misses)
    }

    /// What the attached sheets cost on the wire: raw JPEG bytes plus per-part multipart framing. This is the
    /// number every ceiling check uses, for cached and extracted sheets alike.
    static func wireBytes(_ sheets: [MomentContactSheet], limits: VisualBudgetLimits = VisualBudgetLimits()) -> Int {
        sheets.reduce(0) { $0 + $1.jpeg.count + limits.perSheetOverheadBytes }
    }

    /// Rank each input's frames once. A Moment whose frames cannot be obtained gets a miss reason instead (it is
    /// still planned from its AU text; nothing is fabricated).
    private static func rankedFrames(for inputs: [VisualBudgetInput])
        async -> ([UUID: RankedFrames], [String: SheetMissReason]) {
        var out: [UUID: RankedFrames] = [:]
        var misses: [String: SheetMissReason] = [:]
        for inp in inputs {
            let key = inp.momentId.uuidString.lowercased()
            if let r = inp.ranked, !r.ordered.isEmpty { out[inp.momentId] = r; continue }
            if let cached = inp.cachedFrames, !cached.isEmpty {
                out[inp.momentId] = EvidenceFrameMapper.rank(cached, guidance: inp.guidance); continue
            }
            guard let url = inp.url else { misses[key] = .extractionError; continue }   // no frames, no source
            do {
                let all = try await MomentFrameExtractor.extract(from: url)
                if all.isEmpty { misses[key] = .extractionEmpty; continue }
                out[inp.momentId] = EvidenceFrameMapper.rank(all, guidance: inp.guidance)
            } catch let e as MomentFrameExtractorError {
                misses[key] = (e == .noFrames) ? .extractionEmpty : .extractionError
            } catch {
                misses[key] = .extractionError
            }
        }
        return (out, misses)
    }

    /// Frames for one Moment at a tier: its adaptive count scaled by the tier, never below the floor.
    static func framesAtTier(preferred: Int, fscale: Double, limits: VisualBudgetLimits) -> Int {
        fscale <= 0 ? limits.minFramesPerMoment
                    : max(limits.minFramesPerMoment, Int((Double(preferred) * fscale).rounded()))
    }

    /// Build one sheet per ranked input at the given tier, skipping any sheet that still exceeds the per-sheet
    /// cap after this tier's compression (that Moment degrades to text-only rather than busting the per-sheet
    /// limit). Returns the sheets AND a per-Moment miss-reason map (lowercased id -> reason) for every input
    /// that did NOT get a sheet, so the caller can account for every lost sheet precisely.
    private static func buildSheets(_ inputs: [VisualBudgetInput], _ frameSets: [UUID: RankedFrames],
                                    _ prepMisses: [String: SheetMissReason],
                                    tier: (cell: CGFloat, q: CGFloat, fscale: Double, label: String),
                                    limits: VisualBudgetLimits)
        -> (sheets: [MomentContactSheet], misses: [String: SheetMissReason]) {
        var out: [MomentContactSheet] = []
        var misses = prepMisses
        for inp in inputs {
            let key = inp.momentId.uuidString.lowercased()
            guard let r = frameSets[inp.momentId] else { continue }   // miss reason already recorded
            let count = framesAtTier(preferred: r.preferred, fscale: tier.fscale, limits: limits)
            let picked = r.frames(count: count)
            var budget = ContactSheetBudget(framesPerMoment: max(1, picked.count))
            budget.cellLongestSide = tier.cell
            budget.jpegQuality = tier.q
            do {
                let sheet = try MomentContactSheetBuilder.buildFromFrames(
                    momentId: inp.momentId, frames: picked, durationSeconds: inp.durationSeconds, budget: budget)
                if sheet.jpeg.count <= limits.maxSheetBytes {
                    out.append(sheet)
                    misses.removeValue(forKey: key)
                } else {
                    misses[key] = .oversizeDropped   // too big even at this tier -> text-only for this Moment
                }
            } catch let e as ContactSheetError {
                misses[key] = (e == .noFrames) ? .extractionEmpty : .extractionError
            } catch {
                misses[key] = .extractionError   // any other failure -> text-only (never fabricate)
            }
        }
        return (out, misses)
    }

    /// Visual richness heuristic from evidence ALREADY on hand (no model call): more useful segments / events
    /// / longer footage => more worth spending frames on. Pure, deterministic.
    private static func richness(_ i: VisualBudgetInput) -> Double {
        Double(i.usefulSegmentCount) * 2.0 + Double(i.eventCount) * 1.0 + min(i.durationSeconds / 30.0, 3.0)
    }
}
