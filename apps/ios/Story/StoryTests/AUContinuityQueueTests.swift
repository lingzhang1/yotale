import XCTest
import SwiftData
@testable import Story

// Queue-level reliability tests for background continuity: auth pause, offline pause, cancel, stop gate,
// single-flight, retryParked, snapshot from persisted rows. Fake analyzer; no network.
@MainActor
final class AUContinuityQueueTests: XCTestCase {
    private var container: ModelContainer!
    private var ctx: ModelContext { container.mainContext }

    override func setUp() async throws {
        container = try ModelContainer(
            for: StoryModel.self, MomentModel.self, AssetModel.self,
                 GeneratedOutputModel.self, LocalIdentityModel.self,
                 MomentUnderstandingModel.self, AssetUnderstandingJobModel.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true))
        AssetUnderstandingQueue.stopGate.clear()
        AssetUnderstandingQueue.sharedIsOnline = { true }
        AssetUnderstandingQueue.sharedEnsureFreshToken = { true }
    }

    override func tearDown() async throws {
        AssetUnderstandingQueue.stopGate.clear()
        AssetUnderstandingQueue.sharedIsOnline = { true }
        AssetUnderstandingQueue.sharedEnsureFreshToken = { true }
    }

    private final class Fake: AUAnalyzing {
        var errors: [Error?] = []     // consumed per call; nil = success
        var calls = 0
        var onCall: (() -> Void)?
        func analyze(frames: [AUExtractedFrame], momentId: UUID, sourceCaptureId: UUID?,
                     captureContext: [String: Any]?, contentSha256: String?) async throws -> MomentUnderstandingDTO {
            calls += 1
            onCall?()
            if !errors.isEmpty, let e = errors.removeFirst() { throw e }
            return MomentUnderstandingDTO(
                momentId: momentId, sourceCaptureId: sourceCaptureId,
                schemaVersion: "moment_understanding/1", framePolicy: "au_frames/1",
                promptVersion: "au_prompt/1", modelId: "fake", nFrames: frames.count,
                observed: MomentObservedDTO(summary: "s", subjects: [], events: [], temporalOrderNote: "", usefulSegments: []),
                storyContext: MomentStoryContextDTO(storyUtility: "useful_elsewhere", requestedShotContribution: nil, requestedBeatContribution: nil),
                createdAt: nil)
        }
    }

    private func queue(_ f: Fake) -> AssetUnderstandingQueue {
        AssetUnderstandingQueue(context: ctx, service: f,
                                extractFrames: { _ in [AUExtractedFrame(jpeg: Data([0xFF, 0xD8]), tMs: 0)] },
                                isAuthed: { true })
    }
    private func add(_ q: AssetUnderstandingQueue, _ n: Int) -> [UUID] {
        (0..<n).map { _ in
            let m = UUID()
            q.enqueue(momentId: m, relativeMediaPath: "test/\(m).mov", sourceCaptureId: nil, captureContext: nil)
            return m
        }
    }
    private func jobs() -> [AssetUnderstandingJobModel] { (try? ctx.fetch(FetchDescriptor<AssetUnderstandingJobModel>())) ?? [] }

    func testThirtyMomentsAllCompleteExactlyOnce() async {
        let f = Fake(); let q = queue(f); _ = add(q, 30)
        await q.drain()
        XCTAssertEqual(f.calls, 30)
        XCTAssertTrue(jobs().allSatisfy { $0.state == .complete })
        XCTAssertEqual((try? ctx.fetch(FetchDescriptor<MomentUnderstandingModel>()))?.count, 30)
        XCTAssertEqual(AssetUnderstandingQueue.snapshot(context: ctx).state, .complete)
    }

    func testUnauthorizedPausesWithoutBurningAttempts() async {
        let f = Fake(); f.errors = [AssetUnderstandingServiceError.unauthorized(401)]
        let q = queue(f); _ = add(q, 3)
        await q.drain()
        XCTAssertEqual(f.calls, 1, "drain must stop at the first 401")
        let pending = jobs().filter { $0.state == .pending }
        XCTAssertEqual(pending.count, 3)
        XCTAssertTrue(pending.allSatisfy { $0.attempts == 0 })
        XCTAssertEqual(pending.filter { $0.lastError == AUMarker.authRequired }.count, 1)
        await q.drain()   // token fixed (fake succeeds now)
        XCTAssertTrue(jobs().allSatisfy { $0.state == .complete })
    }

    func testStaleTokenIsRefreshedBeforeRequestAndFailureParksWithoutCall() async {
        let f = Fake()
        AssetUnderstandingQueue.sharedEnsureFreshToken = { false }
        let q = queue(f); _ = add(q, 2)
        await q.drain()
        XCTAssertEqual(f.calls, 0, "no paid request without a fresh token")
        XCTAssertTrue(jobs().allSatisfy { $0.state == .pending && $0.attempts == 0 })
    }

    func testOfflineAtStartLeavesJobsUntouched() async {
        let f = Fake(); AssetUnderstandingQueue.sharedIsOnline = { false }
        let q = queue(f); _ = add(q, 2)
        await q.drain()
        XCTAssertEqual(f.calls, 0)
        XCTAssertTrue(jobs().allSatisfy { $0.state == .pending && $0.attempts == 0 })
        XCTAssertEqual(AssetUnderstandingQueue.snapshot(context: ctx).state, .waitingForNetwork)
    }

    func testNetworkLostMidDrainPausesWithoutBurningAttempt() async {
        let f = Fake(); f.errors = [nil, AssetUnderstandingServiceError.transport(URLError(.notConnectedToInternet))]
        f.onCall = { if f.calls == 2 { AssetUnderstandingQueue.sharedIsOnline = { false } } }
        let q = queue(f); _ = add(q, 4)
        await q.drain()
        XCTAssertEqual(f.calls, 2)
        XCTAssertEqual(jobs().filter { $0.state == .complete }.count, 1)
        XCTAssertTrue(jobs().allSatisfy { $0.attempts == 0 })
        AssetUnderstandingQueue.sharedIsOnline = { true }
        await q.drain()
        XCTAssertTrue(jobs().allSatisfy { $0.state == .complete })
        XCTAssertEqual(f.calls, 2 + 3)   // the interrupted one + the 2 untouched; completed one never re-sent
    }

    func testCancelledAttemptReturnsToPendingNoAttempt() async {
        let f = Fake(); f.errors = [CancellationError()]
        let q = queue(f); _ = add(q, 2)
        await q.drain()
        XCTAssertEqual(f.calls, 1)
        XCTAssertTrue(jobs().allSatisfy { $0.state == .pending && $0.attempts == 0 })
    }

    func testStopGateStopsBetweenJobsAndNeverCancelsInFlight() async {
        let f = Fake()
        f.onCall = { if f.calls == 2 { AssetUnderstandingQueue.stopGate.set() } }   // "expiration" during job 2
        let q = queue(f); _ = add(q, 5)
        await q.drain()
        XCTAssertEqual(f.calls, 2)
        XCTAssertEqual(jobs().filter { $0.state == .complete }.count, 2, "in-flight job finishes; no resend")
        XCTAssertEqual(jobs().filter { $0.state == .pending }.count, 3)
        AssetUnderstandingQueue.stopGate.clear()
        await q.drain()
        XCTAssertEqual(f.calls, 5, "each Moment analyzed exactly once overall")
    }

    func testSingleFlightAcrossInstances() async {
        let f = Fake(); let q1 = queue(f); let q2 = queue(f); _ = add(q1, 4)
        async let a: Void = q1.drain()
        async let b: Void = q2.drain()
        _ = await (a, b)
        XCTAssertEqual(f.calls, 4, "two concurrent drains must not analyze any Moment twice")
        XCTAssertFalse(AssetUnderstandingQueue.isDraining)
    }

    func testRetryParkedResetsOnlyExhaustedHardErrors() async {
        let f = Fake(); let q = queue(f); let ids = add(q, 2)
        let parked = jobs().first { $0.momentId == ids[0] }!
        parked.attempts = 4; parked.nextEligibleAt = Date().addingTimeInterval(24 * 3600); parked.lastError = "x"
        let backoff = jobs().first { $0.momentId == ids[1] }!
        backoff.attempts = 1; backoff.nextEligibleAt = Date().addingTimeInterval(30)
        XCTAssertEqual(q.retryParked(), 1)
        XCTAssertEqual(parked.attempts, 0)
        XCTAssertEqual(backoff.attempts, 1)
    }

    func testSnapshotReadsPersistedRowsAcrossRestart() async {
        let f = Fake(); f.errors = [nil, AssetUnderstandingServiceError.unavailableRetryable]
        let q = queue(f); _ = add(q, 3)
        await q.drain()
        // "Restart": a brand-new queue instance over the same store sees the same honest picture.
        let s = AssetUnderstandingQueue.snapshot(context: ctx)
        XCTAssertEqual(s.done, 2)   // job 2 is backing off, 1 and 3 completed
        XCTAssertEqual(s.total, 3)
        XCTAssertEqual(s.state, .retryingSoon)
    }
}
