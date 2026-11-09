import XCTest
@testable import Story

// Pure tests: the persisted-state -> honest-status mapper and the failure classifier. No SwiftData, no network.
final class AUQueueStatusTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private func id() -> UUID { UUID() }

    private func snap(_ jobs: [AUJobFacts], moments: [UUID]? = nil, online: Bool = true, draining: Bool = false) -> AUQueueSnapshot {
        AUQueueStatusMapper.snapshot(moments: moments ?? jobs.map(\.momentId), understood: [], jobs: jobs,
                                     isOnline: online, isDraining: draining, now: now)
    }

    func testAllCompleteIsCompleteAndSilent() {
        let a = AUJobFacts(momentId: id(), state: .complete), b = AUJobFacts(momentId: id(), state: .complete)
        let s = snap([a, b])
        XCTAssertEqual(s.state, .complete)
        XCTAssertNil(AUQueueStatusMapper.line(s))
    }

    func testNoJobsIsIdle() {
        XCTAssertEqual(snap([], moments: [id()]).state, .idle)   // stills / no job: nothing to say
    }

    func testRunningIsAnalyzingWithRealCounts() {
        let s = snap([AUJobFacts(momentId: id(), state: .complete),
                      AUJobFacts(momentId: id(), state: .running),
                      AUJobFacts(momentId: id(), state: .pending)])
        XCTAssertEqual(s.state, .analyzing)
        XCTAssertEqual(AUQueueStatusMapper.line(s), "Analyzing — 1 of 3 done")
        XCTAssertEqual(AUQueueStatusMapper.line(s, continuesInBackground: true),
                       "Analyzing — 1 of 3 done · continues in the background")
    }

    func testEligibleButNotDrainingMeansWaitingForAppOpen() {
        let s = snap([AUJobFacts(momentId: id(), state: .pending, nextEligibleAt: now.addingTimeInterval(-5))])
        XCTAssertEqual(s.state, .waitingToContinue)
        XCTAssertTrue(AUQueueStatusMapper.line(s)!.contains("continues when YoTale is open"))
        XCTAssertEqual(snap([AUJobFacts(momentId: id(), state: .pending)], draining: true).state, .analyzing)
    }

    func testOfflineWinsOverEligible() {
        let s = snap([AUJobFacts(momentId: id(), state: .pending)], online: false)
        XCTAssertEqual(s.state, .waitingForNetwork)
    }

    func testOfflineMarkerClearsOnceOnline() {
        // A stale "offline" marker must not keep saying "waiting for network" after the path is back.
        let j = AUJobFacts(momentId: id(), state: .pending, lastError: AUMarker.offline)
        XCTAssertEqual(snap([j], online: true).state, .waitingToContinue)
    }

    func testAuthMarkerMeansSignIn() {
        let j = AUJobFacts(momentId: id(), state: .pending, lastError: AUMarker.authRequired)
        XCTAssertEqual(snap([j]).state, .waitingToSignIn)
    }

    func testQuotaIsUsageLimitUntilBoundary() {
        let j = AUJobFacts(momentId: id(), state: .pending, attempts: 0,
                           nextEligibleAt: now.addingTimeInterval(3 * 3600),
                           lastError: "quota_exhausted:daily (deferred to next day)")
        XCTAssertEqual(snap([j]).state, .usageLimit)
    }

    func testBackoffIsRetryingSoon() {
        let j = AUJobFacts(momentId: id(), state: .pending, attempts: 1, nextEligibleAt: now.addingTimeInterval(20))
        XCTAssertEqual(snap([j]).state, .retryingSoon)
    }

    func testExhaustedHardErrorsNeedRetryAndOfferIt() {
        let j = AUJobFacts(momentId: id(), state: .pending, attempts: 4, nextEligibleAt: now.addingTimeInterval(24 * 3600))
        let s = snap([j])
        XCTAssertEqual(s.state, .retryRequired)
        XCTAssertTrue(AUQueueStatusMapper.offersRetry(s))
        XCTAssertEqual(AUQueueStatusMapper.line(s), "1 moment couldn't be analyzed")
    }

    func testParkedJobIsNoteWhileOtherWorkContinues() {
        let parked = AUJobFacts(momentId: id(), state: .pending, attempts: 4, nextEligibleAt: now.addingTimeInterval(24 * 3600))
        let running = AUJobFacts(momentId: id(), state: .running)
        let s = snap([parked, running])
        XCTAssertEqual(s.state, .analyzing)
        XCTAssertEqual(s.parkedForRetry, 1)
        XCTAssertTrue(AUQueueStatusMapper.line(s)!.hasSuffix("1 need a retry"))
    }

    func testQuotaParkWithManyAttemptsIsNotRetryRequired() {
        let j = AUJobFacts(momentId: id(), state: .pending, attempts: 9,
                           nextEligibleAt: now.addingTimeInterval(20 * 3600), lastError: "quota_exhausted:x (deferred to next day)")
        XCTAssertFalse(AUQueueStatusMapper.isParkedForRetry(j, now: now))
    }

    func testDuplicateMomentIdsCountOnce() {
        let m = id()
        let s = snap([AUJobFacts(momentId: m, state: .complete)], moments: [m, m])
        XCTAssertEqual(s.total, 1)
    }

    func testUnrelatedJobsIgnored() {
        let mine = AUJobFacts(momentId: id(), state: .complete)
        let other = AUJobFacts(momentId: id(), state: .pending)
        XCTAssertEqual(snap([mine, other], moments: [mine.momentId]).state, .complete)
    }

    func testMapperConstantsMatchQueue() {
        XCTAssertEqual(AUQueueStatusMapper.hardAttempts, AssetUnderstandingQueue.maxHardAttempts)
        XCTAssertLessThan(AUQueueStatusMapper.hardParkHorizon, AssetUnderstandingQueue.hardErrorParkInterval)
    }

    // MARK: classification

    func testClassification() {
        let on = true, off = false
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.unauthorized(401), isOnline: on), .authPause)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.quotaExhausted(scope: "d"), isOnline: on), .quotaPark)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.rateLimited(retryAfter: 3), isOnline: on), .rateLimited(retryAfter: 3))
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.unavailableRetryable, isOnline: on), .transientRetry)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.badStatus(400), isOnline: on), .hardError)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.transport(URLError(.timedOut)), isOnline: on), .transientRetry)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.transport(URLError(.notConnectedToInternet)), isOnline: off), .offlinePause)
        XCTAssertEqual(AUDisposition.classify(AssetUnderstandingServiceError.transport(URLError(.cancelled)), isOnline: on), .cancelled)
        XCTAssertEqual(AUDisposition.classify(CancellationError(), isOnline: on), .cancelled)
    }

    func testUnauthorizedIsRetryableNotHard() {
        XCTAssertTrue(AssetUnderstandingServiceError.unauthorized(401).isRetryable)
    }
}
