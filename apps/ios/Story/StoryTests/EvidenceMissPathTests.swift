import XCTest
import AVFoundation
import UIKit
@testable import Story

// P1-F pre-beta alignment — cache-MISS frame selection must use the same AU editorial mapper as the cache-HIT
// path, and the attempt's own editorial type must pick the rule. Pure logic + one synthetic-video pipeline
// test (AVFoundation only): no network, no SwiftData, no device media, no model calls.
final class EvidenceMissPathTests: XCTestCase {

    // MARK: - helpers

    /// Frames shaped exactly like MomentFrameExtractor output: N evenly spaced timestamps, inclusive of both ends.
    private func extracted(_ n: Int = 24, dur: Double = 35.3) -> [AUExtractedFrame] {
        let step = (dur * 1000) / Double(n - 1)
        return (0..<n).map { AUExtractedFrame(jpeg: Data([UInt8($0)]), tMs: Int(($0 == 0 ? 0 : Double($0) * step).rounded())) }
    }

    private func ms(_ frames: [AUExtractedFrame]) -> [Int] { frames.map { $0.tMs } }

    private let img9091Visual = [EvidenceCandidate(start: 12, end: 18, peak: 12.5, confidence: 0.86)]

    // MARK: - uniform fallback (Test C): nothing fabricated, behavior unchanged

    func test_miss_without_guidance_is_the_unchanged_even_subsample() {
        let f = extracted()
        let out = EvidenceFrameMapper.selectExtracted(f, guidance: nil, count: 8)
        XCTAssertEqual(ms(out), ms(MomentContactSheetBuilder.evenlySubsample(f, count: 8)))
    }

    func test_miss_with_guidance_but_no_candidates_is_uniform_coverage() {
        let f = extracted()
        // Highlights uses visual candidates only: narrative-only guidance carries no signal for this type.
        let g = EditorialFrameGuidance(videoType: .highlights, visual: [],
                                       narrative: [EvidenceCandidate(start: 5, end: 9, peak: nil, confidence: 0.5)],
                                       eventTimesS: [3])
        XCTAssertFalse(g.hasCandidates)
        let out = EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 8)
        XCTAssertEqual(ms(out), ms(MomentContactSheetBuilder.evenlySubsample(f, count: 8)))
    }

    func test_hasCandidates_follows_the_video_type() {
        let v = [EvidenceCandidate(start: 1, end: 2, peak: nil, confidence: nil)]
        XCTAssertTrue(EditorialFrameGuidance(videoType: .highlights, visual: v, narrative: [], eventTimesS: []).hasCandidates)
        XCTAssertFalse(EditorialFrameGuidance(videoType: .fullStory, visual: v, narrative: [], eventTimesS: []).hasCandidates)
        XCTAssertTrue(EditorialFrameGuidance(videoType: .fullStory, visual: [], narrative: [], eventTimesS: [4]).hasCandidates)
        XCTAssertTrue(EditorialFrameGuidance(videoType: .fullStory, visual: [], narrative: v, eventTimesS: []).hasCandidates)
    }

    // MARK: - candidate-aligned selection on a miss (Test B) + IMG_9091 regression (Test D)

    func test_miss_with_candidates_uses_the_mapper_over_extracted_timestamps() {
        let f = extracted()
        let g = EditorialFrameGuidance(videoType: .highlights, visual: img9091Visual, narrative: [], eventTimesS: [])
        let out = EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 8)
        // Identical to running the mapper directly over those timestamps: one rule, two paths.
        let direct = EvidenceFrameMapper.selectFrames(
            videoType: .highlights, sampledFrameMs: ms(f), visualCandidates: img9091Visual,
            narrativeCandidates: [], eventTimesS: [], budget: 8).map { f[$0] }
        XCTAssertEqual(ms(out), ms(direct))
        XCTAssertLessThanOrEqual(out.count, 8)
        XCTAssertEqual(ms(out), ms(out).sorted())
    }

    func test_miss_img9091_keeps_context_around_the_true_reveal() {
        let f = extracted(24, dur: 35.3)
        let g = EditorialFrameGuidance(videoType: .highlights, visual: img9091Visual, narrative: [], eventTimesS: [])
        let guided = ms(EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 8))
        let uniform = ms(MomentContactSheetBuilder.evenlySubsample(f, count: 8))
        let reveal = 16_620
        // Context on both sides of the real reveal (peak is advisory and mis-estimated early at 12.5s).
        XCTAssertTrue(guided.contains { abs($0 - reveal) <= 1_600 }, "\(guided)")
        XCTAssertTrue(guided.contains { $0 < reveal }, "need a frame before the reveal: \(guided)")
        XCTAssertTrue(guided.contains { $0 > reveal }, "need a frame after the reveal: \(guided)")
        // Whole-Moment visibility is preserved (opening + closing).
        XCTAssertEqual(guided.first, f.first?.tMs)
        XCTAssertEqual(guided.last, f.last?.tMs)
        // The candidate's region centre is represented (representative-first), plus setup/aftermath context.
        XCTAssertTrue(guided.contains { $0 >= 12_000 && $0 <= 18_000 }, "\(guided)")
        _ = uniform
    }

    func test_miss_guidance_lands_a_frame_in_a_candidate_window_that_uniform_sampling_skips() {
        // 60s Moment, 24 extracted frames, budget 6: uniform picks land at ~0/13/23/36/47/60s and none falls in
        // the 40..44s candidate; the mapper's region-centre context frame does. (IMG_9091's own 35.3s timeline
        // happens to be bracketed by uniform too, so it cannot demonstrate the difference.)
        let f = extracted(24, dur: 60)
        let g = EditorialFrameGuidance(videoType: .highlights,
                                       visual: [EvidenceCandidate(start: 40, end: 44, peak: nil, confidence: 0.9)],
                                       narrative: [], eventTimesS: [])
        let inWindow: (Int) -> Bool = { $0 >= 40_000 && $0 <= 44_000 }
        let uniform = ms(MomentContactSheetBuilder.evenlySubsample(f, count: 6))
        let guided = ms(EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 6))
        XCTAssertFalse(uniform.contains(where: inWindow), "premise: uniform skips the window: \(uniform)")
        XCTAssertTrue(guided.contains(where: inWindow), "guided must reach the window: \(guided)")
        XCTAssertEqual(guided.first, 0)                      // whole-Moment visibility kept
        XCTAssertEqual(guided.last, f.last?.tMs)
        XCTAssertLessThanOrEqual(guided.count, 6)
    }

    func test_miss_highlights_and_full_story_choose_different_frames() {
        let f = extracted()
        let vis = [EvidenceCandidate(start: 3, end: 6, peak: 4.5, confidence: 0.9)]
        let nar = [EvidenceCandidate(start: 28, end: 33, peak: nil, confidence: 0.6)]
        let h = ms(EvidenceFrameMapper.selectExtracted(
            f, guidance: EditorialFrameGuidance(videoType: .highlights, visual: vis, narrative: nar, eventTimesS: []), count: 6))
        let s = ms(EvidenceFrameMapper.selectExtracted(
            f, guidance: EditorialFrameGuidance(videoType: .fullStory, visual: vis, narrative: nar, eventTimesS: [20]), count: 6))
        XCTAssertNotEqual(h, s)
    }

    func test_miss_selection_never_exceeds_budget_or_frame_count() {
        let f = extracted(5, dur: 4)
        let g = EditorialFrameGuidance(videoType: .highlights, visual: img9091Visual, narrative: [], eventTimesS: [])
        XCTAssertEqual(EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 9).count, 5)   // budget > frames
        XCTAssertLessThanOrEqual(EvidenceFrameMapper.selectExtracted(f, guidance: g, count: 3).count, 3)
        XCTAssertTrue(EvidenceFrameMapper.selectExtracted([], guidance: g, count: 4).isEmpty)
    }

    // MARK: - attempt editorial type picks the rule (Original / Revise / Explore)

    func test_evidenceVideoType_follows_the_attempt_not_the_legacy_story_seed() {
        // Explore switching type / Revise inheriting base type: the attempt value wins over the Story seed.
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: "full_story", legacyStoryMode: "highlights"), .fullStory)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: "highlights", legacyStoryMode: "full"), .highlights)
        // Original create resolves the Story selection into the attempt type, so it agrees with the seed.
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: "full_story", legacyStoryMode: "full"), .fullStory)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: "highlights", legacyStoryMode: nil), .highlights)
    }

    func test_evidenceVideoType_falls_back_to_the_legacy_seed_only_when_the_attempt_has_no_type() {
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: nil, legacyStoryMode: "full"), .fullStory)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: nil, legacyStoryMode: "FULL"), .fullStory)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: nil, legacyStoryMode: "custom"), .highlights)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: nil, legacyStoryMode: nil), .highlights)
        XCTAssertEqual(EvidenceVideoType.forAttempt(editorialType: "bogus", legacyStoryMode: "full"), .fullStory)
    }

    // MARK: - the guidance reaches the budget builder unchanged

    func test_visual_budget_input_defaults_to_no_guidance_and_carries_it_when_given() {
        let url = URL(fileURLWithPath: "/dev/null")
        let id = UUID()
        let plain = VisualBudgetInput(momentId: id, url: url, durationSeconds: 5, usefulSegmentCount: 1, eventCount: 0)
        XCTAssertNil(plain.guidance)
        let g = EditorialFrameGuidance(videoType: .fullStory, visual: [], narrative: [], eventTimesS: [2])
        let guided = VisualBudgetInput(momentId: id, url: url, durationSeconds: 5, usefulSegmentCount: 1,
                                       eventCount: 0, guidance: g)
        XCTAssertEqual(guided.guidance?.videoType, .fullStory)
        XCTAssertEqual(guided.guidance?.eventTimesS, [2])
    }

    // MARK: - end to end on a real (synthetic) video: restore/extract fallback + mapper + tiled sheet

    /// Writes a small H.264 video whose frame at second s is a flat colour keyed to s. Enough for the REAL
    /// MomentFrameExtractor + MomentContactSheetBuilder pipeline; contains no personal media.
    private func makeVideo(seconds: Int, fps: Int32 = 10) async throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("p1f-miss-\(UUID().uuidString).mp4")
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let settings: [String: Any] = [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 320, AVVideoHeightKey: 240]
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                                          kCVPixelBufferWidthKey as String: 320, kCVPixelBufferHeightKey as String: 240])
        writer.add(input)
        XCTAssertTrue(writer.startWriting())
        writer.startSession(atSourceTime: .zero)
        for i in 0..<(seconds * Int(fps)) {
            while !input.isReadyForMoreMediaData { try await Task.sleep(nanoseconds: 2_000_000) }
            var pb: CVPixelBuffer?
            CVPixelBufferCreate(nil, 320, 240, kCVPixelFormatType_32BGRA, nil, &pb)
            guard let buf = pb else { continue }
            CVPixelBufferLockBaseAddress(buf, [])
            if let base = CVPixelBufferGetBaseAddress(buf) {
                memset(base, Int32((i / Int(fps)) * 20 % 250), CVPixelBufferGetDataSize(buf))
            }
            CVPixelBufferUnlockBaseAddress(buf, [])
            adaptor.append(buf, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: fps))
        }
        input.markAsFinished()
        await writer.finishWriting()
        XCTAssertEqual(writer.status, .completed)
        return url
    }

    func test_pipeline_extract_then_select_is_candidate_guided_and_still_yields_a_sheet() async throws {
        let url = try await makeVideo(seconds: 12)
        defer { try? FileManager.default.removeItem(at: url) }
        let frames = try await MomentFrameExtractor.extract(from: url)
        XCTAssertGreaterThan(frames.count, 8)

        // Candidate near the end; guided selection must reach it, blind uniform at budget 4 need not.
        let g = EditorialFrameGuidance(videoType: .highlights,
                                       visual: [EvidenceCandidate(start: 8, end: 9.5, peak: 8.7, confidence: 0.9)],
                                       narrative: [], eventTimesS: [])
        let guided = EvidenceFrameMapper.selectExtracted(frames, guidance: g, count: 4)
        XCTAssertTrue(guided.contains { $0.tMs >= 8_000 && $0.tMs <= 9_500 + 1_500 },
                      "guided \(guided.map { $0.tMs })")
        XCTAssertLessThanOrEqual(guided.count, 4)

        // The real builder produces a sheet for both guided and unguided inputs (no Moment is dropped).
        var budget = ContactSheetBudget.tier1(forDuration: 12); budget.framesPerMoment = 4
        let id = UUID()
        let sheetGuided = try await MomentContactSheetBuilder.build(
            momentId: id, url: url, durationSeconds: 12, budget: budget, guidance: g)
        let sheetPlain = try await MomentContactSheetBuilder.build(
            momentId: id, url: url, durationSeconds: 12, budget: budget)
        XCTAssertEqual(sheetGuided.momentId, id)
        XCTAssertFalse(sheetGuided.jpeg.isEmpty)
        XCTAssertFalse(sheetPlain.jpeg.isEmpty)
        XCTAssertLessThanOrEqual(sheetGuided.frameCount, 4)
    }

    func test_budget_preflight_accepts_guided_inputs_and_returns_a_sheet() async throws {
        let url = try await makeVideo(seconds: 8)
        defer { try? FileManager.default.removeItem(at: url) }
        let id = UUID()
        let g = EditorialFrameGuidance(videoType: .highlights,
                                       visual: [EvidenceCandidate(start: 5, end: 6.5, peak: nil, confidence: 0.8)],
                                       narrative: [], eventTimesS: [])
        let res = await MultimodalVisualBudget.build([
            VisualBudgetInput(momentId: id, url: url, durationSeconds: 8, usefulSegmentCount: 1, eventCount: 0, guidance: g)
        ])
        XCTAssertEqual(res.sheets.count, 1)
        XCTAssertEqual(res.sheetOrder, [id])
        XCTAssertEqual(res.momentsTextOnly, 0)
        XCTAssertTrue(res.sheetMissReasons.isEmpty)
    }
}
