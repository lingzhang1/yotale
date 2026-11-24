import XCTest
import SwiftData
@testable import Story

// AI Ideas latency: while the scan + Director are in flight, background queues start no new jobs, and the
// release re-drains them.
@MainActor
final class InteractiveAIHoldTests: XCTestCase {

    final class CountingAnalyzer: AUAnalyzing {
        var calls = 0
        func analyze(frames: [AUExtractedFrame], momentId: UUID, sourceCaptureId: UUID?,
                     captureContext: [String: Any]?, contentSha256: String?) async throws -> MomentUnderstandingDTO {
            calls += 1
            throw MomentFrameExtractorError.noFrames
        }
    }

    override func tearDown() async throws {
        InteractiveAIHold.onRelease = { }
        try await super.tearDown()
    }

    func test_begin_end_toggles_hold_and_fires_release_once() {
        var releases = 0
        InteractiveAIHold.onRelease = { releases += 1 }
        let a = InteractiveAIHold.begin()
        let b = InteractiveAIHold.begin()
        XCTAssertTrue(InteractiveAIHold.isHeld)
        InteractiveAIHold.end(a)
        XCTAssertTrue(InteractiveAIHold.isHeld, "still held while another holder is active")
        XCTAssertEqual(releases, 0)
        InteractiveAIHold.end(b)
        XCTAssertFalse(InteractiveAIHold.isHeld)
        XCTAssertEqual(releases, 1)
        InteractiveAIHold.end(b)        // double end is a no-op
        InteractiveAIHold.end(nil)
        XCTAssertEqual(releases, 1)
    }

    func test_au_drain_starts_nothing_while_held_and_runs_after_release() async throws {
        let container = try ModelContainer(
            for: StoryModel.self, MomentModel.self, StoryMomentLink.self, AssetModel.self,
                 GeneratedOutputModel.self, LocalIdentityModel.self,
                 MomentUnderstandingModel.self, AssetUnderstandingJobModel.self,
                 StoryCoverageModel.self, StoryGuideModel.self, StoryMusicDirectionModel.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true))
        let analyzer = CountingAnalyzer()
        let queue = AssetUnderstandingQueue(
            context: container.mainContext, service: analyzer,
            extractFrames: { _ in [AUExtractedFrame(jpeg: Data([0xFF]), tMs: 0)] },
            isAuthed: { true },
            fileExists: { _ in true })
        queue.enqueue(momentId: UUID(), relativeMediaPath: "media/x.mov", sourceCaptureId: nil, captureContext: nil)

        let hold = InteractiveAIHold.begin()
        await queue.drain()
        XCTAssertEqual(analyzer.calls, 0, "no AU request starts while AI Ideas is waiting")
        let job = try XCTUnwrap(try container.mainContext.fetch(FetchDescriptor<AssetUnderstandingJobModel>()).first)
        XCTAssertEqual(job.stateRaw, "pending")
        XCTAssertEqual(job.attempts, 0, "a held drain burns no attempt")

        InteractiveAIHold.end(hold)
        await queue.drain()
        XCTAssertEqual(analyzer.calls, 1, "the pending job runs once the hold ends")
    }
}
