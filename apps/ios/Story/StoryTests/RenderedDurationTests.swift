import AVFoundation
import XCTest
@testable import Story

// Duration reliability — the device renders exactly the planned length. The backend EditPlan/2 contract drops
// transitions (straight cuts), so the rendered file must equal the SUM of segment output durations; the
// backend's deterministic duration fit relies on this. Covers a fitted-plan shape: several Moments, a second
// (non-overlapping) re-cut of one Moment, and a non-1x speed. Also pins the dissolve overlap arithmetic for
// iOS-authored transitions. Synthetic silent videos; composition timeline AND the exported file are checked.
@MainActor
final class RenderedDurationTests: XCTestCase {

    private var videos: [URL] = []

    override func tearDown() {
        for v in videos { try? FileManager.default.removeItem(at: v) }
        videos = []
        super.tearDown()
    }

    private func plan(_ segs: [EditSegmentV2], target: Double) -> EditPlanV2 {
        EditPlanV2(schemaVersion: "edit_plan/2", targetDurationSeconds: target, outputFormat: "vertical",
                   musicAssetId: nil, feasible: true, segments: segs)
    }

    private func seg(_ order: Int, _ id: String, _ a: Double, _ b: Double, speed: Double = 1.0,
                     transition: Transition? = nil) -> EditSegmentV2 {
        EditSegmentV2(order: order, assetId: id, sourceStartSeconds: a, sourceEndSeconds: b,
                      outputDurationSeconds: (b - a) / speed, speed: speed, nativeAudio: "keep",
                      musicAlignment: nil, transition: transition)
    }

    private func inputs(_ p: EditPlanV2, _ urls: [String: URL]) -> MediaEngineInputs {
        MediaEngineInputs(plan: p, resolveMomentURL: { urls[$0] }, soundtrackURL: nil, musicAnalysis: nil,
                          soundtrackRole: "supportive", nativeAudioPriority: "selective")
    }

    private func makeSources() async throws -> [String: URL] {
        var urls: [String: URL] = [:]
        for id in ["m-a", "m-b", "m-c"] {
            let u = try await SyntheticMedia.makeVideo(seconds: 10)
            videos.append(u); urls[id] = u
        }
        return urls
    }

    func test_straight_cut_plan_composition_equals_segment_sum() async throws {
        let urls = try await makeSources()
        let (p, expected) = fittedShapePlan()
        let built = try MediaEngineV1().buildComposition(inputs(p, urls))
        XCTAssertEqual(built.totalDuration.seconds, expected, accuracy: 0.05)
    }

    func test_straight_cut_plan_exported_file_equals_segment_sum() async throws {
        let urls = try await makeSources()
        let (p, expected) = fittedShapePlan()
        let result: RenderResult
        do {
            result = try await MediaEngineV1().render(inputs(p, urls))
        } catch MediaEngineError.exportFailed(let why) {
            // AVAssetExportSession is not reliably available on the simulator (the existing engine tests treat
            // actual export as a device gate); the composition test above still pins the timeline length.
            throw XCTSkip("export unavailable in this environment: \(why)")
        }
        defer { try? FileManager.default.removeItem(at: result.url) }
        let fileDuration = try await AVURLAsset(url: result.url).load(.duration).seconds
        XCTAssertEqual(result.durationSeconds, expected, accuracy: 0.15)
        XCTAssertEqual(fileDuration, expected, accuracy: 0.15)
    }

    private func fittedShapePlan() -> (EditPlanV2, Double) {
        let segs = [seg(0, "m-a", 2.0, 6.5), seg(1, "m-b", 1.0, 7.0, speed: 1.5),
                    seg(2, "m-a", 7.0, 9.5), seg(3, "m-c", 0.5, 4.0)]
        return (plan(segs, target: 14), segs.reduce(0) { $0 + $1.outputDurationSeconds })   // 4.5+4+2.5+3.5
    }

    func test_ios_dissolve_overlap_shortens_the_timeline_by_its_duration() async throws {
        let urls = try await makeSources()
        let segs = [seg(0, "m-a", 0, 4), seg(1, "m-b", 0, 4, transition: Transition(type: "dissolve", durationSeconds: 0.5)),
                    seg(2, "m-c", 0, 4)]
        let built = try MediaEngineV1().buildComposition(inputs(plan(segs, target: 12), urls))
        XCTAssertEqual(built.totalDuration.seconds, 12.0 - 0.5, accuracy: 0.05)
    }
}
