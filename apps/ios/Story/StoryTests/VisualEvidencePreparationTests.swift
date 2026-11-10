import XCTest
@testable import Story

// P1-F pre-beta — planning-time visual evidence for EVERY eligible Moment (local or cloud-only) under ONE shared
// payload budget. The three side effects (local file, cache fetch, R6 restore) are injected, so this exercises
// the real preparation + MultimodalVisualBudget + sheet builder + frame extractor with no network and no
// SwiftData. See VisualEvidencePreparation.swift for the A (cache) / B (restore + extract) / C (none) algorithm.
@MainActor
final class VisualEvidencePreparationTests: XCTestCase {

    // MARK: - fixtures

    private func ref(_ id: UUID = UUID(), dur: Double = 40, useful: Int = 1, events: [Double] = [],
                     type: EvidenceVideoType = .highlights,
                     visual: [EvidenceCandidate] = []) -> EvidenceMomentRef {
        EvidenceMomentRef(momentId: id, durationSeconds: dur, usefulSegmentCount: useful,
                          guidance: EditorialFrameGuidance(videoType: type, visual: visual, narrative: [], eventTimesS: events))
    }

    private func tinyFrames(_ n: Int = 6) -> [AUExtractedFrame] {
        (0..<n).map { AUExtractedFrame(jpeg: SyntheticMedia.tinyJPEG(gray: CGFloat($0) / CGFloat(n)), tMs: $0 * 1_000) }
    }

    private func ids(_ sheets: [MomentContactSheet]) -> Set<UUID> { Set(sheets.map { $0.momentId }) }

    // MARK: - A: cache hit works with NO local source and never restores (cloud-only, Test B)

    func test_all_cache_hit_cloud_only_story_builds_every_sheet_without_any_restore() async {
        let refs = (0..<5).map { _ in ref() }
        var restoreCalls = 0
        let r = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in nil },
            fetchCachedFrames: { _ in self.tinyFrames() },
            restoreSources: { _ in restoreCalls += 1; return ([:], []) })
        XCTAssertEqual(restoreCalls, 0, "a cache hit must not restore the original for planning")
        XCTAssertEqual(ids(r.sheets), Set(refs.map { $0.momentId }))
        XCTAssertEqual(r.cacheHitCount, 5)
        XCTAssertEqual(r.cacheMissCount, 0)
        XCTAssertTrue(r.restoreUnavailableIds.isEmpty)
        XCTAssertTrue(r.sheetMissReasons.isEmpty)
    }

    func test_every_eligible_moment_gets_a_cache_lookup_even_when_its_source_is_not_local() async {
        let refs = (0..<4).map { _ in ref() }
        var looked = Set<UUID>()
        _ = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in nil },
            fetchCachedFrames: { m in looked.insert(m.momentId); return nil },
            restoreSources: { _ in ([:], []) })
        XCTAssertEqual(looked, Set(refs.map { $0.momentId }))
    }

    // MARK: - B: cache miss -> local source, or R6 restore of the cloud-only source, then extract (Test C)

    func test_all_cache_miss_local_story_extracts_without_restore() async throws {
        let video = try await SyntheticMedia.makeVideo(seconds: 10)
        defer { try? FileManager.default.removeItem(at: video) }
        let refs = (0..<3).map { _ in ref(dur: 10) }
        var restoreCalls = 0
        let r = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in video },
            fetchCachedFrames: { _ in nil },
            restoreSources: { _ in restoreCalls += 1; return ([:], []) })
        XCTAssertEqual(restoreCalls, 0)
        XCTAssertEqual(ids(r.sheets), Set(refs.map { $0.momentId }))
        XCTAssertEqual(r.cacheMissCount, 3)
    }

    func test_cache_miss_cloud_only_source_is_restored_then_extracted() async throws {
        let video = try await SyntheticMedia.makeVideo(seconds: 10)
        defer { try? FileManager.default.removeItem(at: video) }
        let refs = (0..<3).map { _ in ref(dur: 10) }
        var restoredIds: [UUID] = []
        let r = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in nil },
            fetchCachedFrames: { _ in nil },
            restoreSources: { want in
                restoredIds = want
                return (Dictionary(uniqueKeysWithValues: want.map { ($0, video) }), [])
            })
        XCTAssertEqual(Set(restoredIds), Set(refs.map { $0.momentId }))
        XCTAssertEqual(ids(r.sheets), Set(refs.map { $0.momentId }), "a cloud-restorable Moment must not become text-only")
        XCTAssertEqual(r.restoredCount, 3)
    }

    // MARK: - C: genuinely unavailable -> truthful, no fabricated sheet

    func test_unrestorable_source_gets_no_sheet_and_is_reported_not_fabricated() async throws {
        let video = try await SyntheticMedia.makeVideo(seconds: 10)
        defer { try? FileManager.default.removeItem(at: video) }
        let good = ref(dur: 10), gone = ref(dur: 10)
        let r = await VisualEvidencePreparation.prepare(
            moments: [good, gone], localURL: { _ in nil },
            fetchCachedFrames: { _ in nil },
            restoreSources: { _ in ([good.momentId: video], [gone.momentId]) })
        XCTAssertEqual(ids(r.sheets), [good.momentId])
        XCTAssertEqual(r.restoreUnavailableIds, [gone.momentId.uuidString.lowercased()])
        XCTAssertEqual(r.eligibleCount, 2)
        XCTAssertEqual(r.restoredCount, 1)
    }

    // MARK: - D: mixed Story, one shared budget, all eligible Moments accounted for

    func test_mixed_story_restores_only_cache_misses_that_are_not_local_and_accounts_for_everyone() async throws {
        let video = try await SyntheticMedia.makeVideo(seconds: 10)
        defer { try? FileManager.default.removeItem(at: video) }
        let hitA = ref(dur: 10), hitB = ref(dur: 10)        // cached, source cloud-only
        let localMiss = ref(dur: 10)                          // no cache, already local
        let restoredMiss = ref(dur: 10)                       // no cache, cloud-only, restorable
        let unavailable = ref(dur: 10)                        // no cache, cloud-only, not restorable
        let all = [hitA, hitB, localMiss, restoredMiss, unavailable]
        let hits: Set<UUID> = [hitA.momentId, hitB.momentId]
        var asked: [UUID] = []
        let r = await VisualEvidencePreparation.prepare(
            moments: all,
            localURL: { $0 == localMiss.momentId ? video : nil },
            fetchCachedFrames: { hits.contains($0.momentId) ? self.tinyFrames() : nil },
            restoreSources: { want in
                asked = want
                return ([restoredMiss.momentId: video], [unavailable.momentId])
            })
        XCTAssertEqual(Set(asked), [restoredMiss.momentId, unavailable.momentId],
                       "restore only the cache misses that are not local: never a cache hit, never a local Moment")
        XCTAssertEqual(ids(r.sheets), [hitA.momentId, hitB.momentId, localMiss.momentId, restoredMiss.momentId])
        XCTAssertEqual(r.restoreUnavailableIds, [unavailable.momentId.uuidString.lowercased()])
        XCTAssertEqual(r.eligibleCount, 5)
        XCTAssertEqual(r.cacheHitCount, 2)
        XCTAssertEqual(r.cacheMissCount, 3)
        // Every eligible Moment is either sheeted, reported with a miss reason, or reported unrestorable.
        let accounted = ids(r.sheets)
            .union(r.sheetMissReasons.keys.compactMap { UUID(uuidString: $0) })
            .union(r.restoreUnavailableIds.compactMap { UUID(uuidString: $0) })
        XCTAssertEqual(accounted, Set(all.map { $0.momentId }))
        // One budget pass: a single tier label for the whole payload.
        XCTAssertFalse(r.budget.selectedTier.isEmpty)
    }

    // MARK: - editorial type reaches the cache fetch (Original / Revise / Explore resolve it upstream)

    func test_attempt_editorial_type_is_what_the_cache_fetch_receives() async {
        for type in [EvidenceVideoType.highlights, .fullStory] {
            var seen: [EvidenceVideoType] = []
            _ = await VisualEvidencePreparation.prepare(
                moments: [ref(type: type), ref(type: type)], localURL: { _ in nil },
                fetchCachedFrames: { m in seen.append(m.guidance.videoType); return nil },
                restoreSources: { _ in ([:], []) })
            XCTAssertEqual(seen, [type, type])
        }
    }

    func test_guided_and_uniform_counts_follow_candidate_availability() async {
        let withCand = ref(visual: [EvidenceCandidate(start: 5, end: 8, peak: nil, confidence: 0.8)])
        let none = ref()
        let r = await VisualEvidencePreparation.prepare(
            moments: [withCand, none], localURL: { _ in nil },
            fetchCachedFrames: { _ in self.tinyFrames(9) }, restoreSources: { _ in ([:], []) })
        XCTAssertEqual(r.guidedCount, 1)
        XCTAssertEqual(r.uniformCount, 1)
        XCTAssertEqual(r.sheets.count, 2)
    }

    // MARK: - shared payload budget: no cache exemption, large Story, honest degradation

    func test_wire_bytes_count_the_multipart_framing_per_sheet() async {
        let r = await VisualEvidencePreparation.prepare(
            moments: [ref(), ref(), ref()], localURL: { _ in nil },
            fetchCachedFrames: { _ in self.tinyFrames() }, restoreSources: { _ in ([:], []) })
        let raw = r.sheets.reduce(0) { $0 + $1.jpeg.count }
        XCTAssertEqual(r.wireBytes, raw + 3 * VisualBudgetLimits().perSheetOverheadBytes)
    }

    /// Runs `count` cache-hit Moments of noisy (poorly compressible) frames, first unconstrained to prove the
    /// premise that the payload is over `ceiling`, then under `ceiling` to prove the existing ladder brings the
    /// SAME cached frames under it without dropping a Moment.
    private func assertLargeCachedStoryIsDegradedNotDropped(count: Int, ceiling: Int,
                                                            file: StaticString = #file, line: UInt = #line) async {
        let frames = (0..<9).map { AUExtractedFrame(jpeg: SyntheticMedia.noiseJPEG(seed: UInt64($0 + 1)), tMs: $0 * 4_000) }
        let refs = (0..<count).map { _ in ref(dur: 72) }   // Tier-1 = 9 frames per Moment

        var huge = VisualBudgetLimits()
        huge.maxTotalImageBytes = Int.max / 2; huge.maxSheetBytes = Int.max / 2
        let natural = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in nil }, fetchCachedFrames: { _ in frames },
            restoreSources: { _ in ([:], []) }, limits: huge)
        XCTAssertGreaterThan(natural.wireBytes, ceiling,
                             "premise: unconstrained payload must exceed the ceiling, got \(natural.wireBytes)", file: file, line: line)

        var limits = VisualBudgetLimits()
        limits.maxTotalImageBytes = ceiling
        let r = await VisualEvidencePreparation.prepare(
            moments: refs, localURL: { _ in nil }, fetchCachedFrames: { _ in frames },
            restoreSources: { _ in ([:], []) }, limits: limits)
        XCTAssertLessThanOrEqual(r.wireBytes, ceiling, file: file, line: line)
        XCTAssertLessThan(r.wireBytes, natural.wireBytes, file: file, line: line)
        XCTAssertEqual(r.sheets.count, count, "degradation must come from the ladder, not from dropping Moments", file: file, line: line)
        XCTAssertTrue(r.sheetMissReasons.isEmpty, file: file, line: line)
        XCTAssertNotEqual(r.budget.selectedTier, "tier1", file: file, line: line)
        XCTAssertFalse(r.budget.appliedSteps.isEmpty, file: file, line: line)
        for s in r.sheets { XCTAssertLessThanOrEqual(s.jpeg.count, limits.maxSheetBytes, file: file, line: line) }
    }

    func test_35_moment_cached_story_over_the_ceiling_is_downscaled_without_losing_a_moment() async {
        // 35 synthetic noise sheets are ~11.5 MB (real sheets are ~100 KB), so the ceiling is scaled to 8 MB to
        // put this Story over it. The mechanism under test is identical to the 16 MB case below.
        await assertLargeCachedStoryIsDegradedNotDropped(count: 35, ceiling: 8 * 1024 * 1024)
    }

    func test_cached_story_over_the_real_16MB_ceiling_is_downscaled_without_losing_a_moment() async {
        await assertLargeCachedStoryIsDegradedNotDropped(count: 60, ceiling: VisualBudgetLimits().maxTotalImageBytes)
    }

    func test_unavoidable_overflow_reduces_coverage_with_a_reason_for_every_dropped_moment() async throws {
        let video = try await SyntheticMedia.makeVideo(seconds: 10)
        defer { try? FileManager.default.removeItem(at: video) }
        let cachedRefs = (0..<4).map { _ in ref(dur: 10) }
        let extractedRefs = (0..<4).map { _ in ref(dur: 10) }
        let all = cachedRefs + extractedRefs
        let cachedIds = Set(cachedRefs.map { $0.momentId })
        // Probe one sheet's size, then allow only ~3 sheets in total across BOTH sources.
        let probe = await VisualEvidencePreparation.prepare(
            moments: [cachedRefs[0]], localURL: { _ in nil }, fetchCachedFrames: { _ in self.tinyFrames(9) },
            restoreSources: { _ in ([:], []) })
        var tight = VisualBudgetLimits()
        tight.maxTotalImageBytes = probe.wireBytes * 3 + 64
        let r = await VisualEvidencePreparation.prepare(
            moments: all,
            localURL: { cachedIds.contains($0) ? nil : video },
            fetchCachedFrames: { cachedIds.contains($0.momentId) ? self.tinyFrames(9) : nil },
            restoreSources: { _ in ([:], []) }, limits: tight)
        XCTAssertLessThanOrEqual(r.wireBytes, tight.maxTotalImageBytes, "cache hits must obey the same ceiling")
        XCTAssertLessThan(r.sheets.count, all.count)
        // Every Moment is either sheeted or carries a recorded reason: nothing is silently lost.
        let reasoned = Set(r.sheetMissReasons.keys.compactMap { UUID(uuidString: $0) })
        XCTAssertEqual(ids(r.sheets).union(reasoned), Set(all.map { $0.momentId }))
        XCTAssertTrue(ids(r.sheets).isDisjoint(with: reasoned))
        for reason in r.sheetMissReasons.values {
            XCTAssertTrue(reason == .budgetCoverageDropped || reason == .oversizeDropped, "\(reason)")
        }
    }

    // MARK: - eventCount audit: known AU events now reach the existing richness ranking

    func test_known_au_events_reach_the_budget_ranking() async {
        let eventRich = ref(useful: 1, events: [1, 2, 3, 4, 5])
        let eventPoor = ref(useful: 1, events: [])
        var capped = VisualBudgetLimits()
        capped.maxSheets = 1            // forces the coverage-reduction step, which keeps the richest first
        let r = await VisualEvidencePreparation.prepare(
            moments: [eventPoor, eventRich], localURL: { _ in nil },
            fetchCachedFrames: { _ in self.tinyFrames() }, restoreSources: { _ in ([:], []) }, limits: capped)
        XCTAssertEqual(ids(r.sheets), [eventRich.momentId])
        XCTAssertEqual(r.sheetMissReasons[eventPoor.momentId.uuidString.lowercased()], .budgetCoverageDropped)
    }
}
