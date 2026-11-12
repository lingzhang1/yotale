import XCTest
@testable import Story

// Lost-reply recovery for async EditPlan jobs (dev 2026-11-12: one dropped 202 left the Creating screen
// spinning ~5 min and the finished plan was never collected or resumable).
final class EditPlanJobSubmitRecoveryTests: XCTestCase {

    func test_jobSession_failsFastInsteadOfWaiting() {
        let c = StoryBackend.jobSession.configuration
        XCTAssertLessThanOrEqual(c.timeoutIntervalForRequest, 30)
        XCTAssertLessThanOrEqual(c.timeoutIntervalForResource, 120)
        XCTAssertFalse(c.waitsForConnectivity, "a lost reply must surface as an error the same-op retry handles")
    }

    func test_pendingSubmitStore_roundTripsExactBytesAndRemoves() {
        let op = "op-\(UUID().uuidString)"
        let bytes = Data((0..<4096).map { UInt8($0 % 251) })
        PendingJobSubmitStore.save(PreparedJobSubmit(body: bytes, boundary: "story.job.X"), operationId: op)
        XCTAssertTrue(PendingJobSubmitStore.exists(operationId: op))
        let back = PendingJobSubmitStore.load(operationId: op)
        XCTAssertEqual(back?.body, bytes)
        XCTAssertEqual(back?.boundary, "story.job.X")
        PendingJobSubmitStore.remove(operationId: op)
        XCTAssertFalse(PendingJobSubmitStore.exists(operationId: op))
        XCTAssertNil(PendingJobSubmitStore.load(operationId: op))
    }

    func test_preparedSubmit_carriesOperationIdAndEveryField() throws {
        let req = EditPlanRequestDTO(storyId: UUID(), creativeIntentId: UUID(),
                                     creativeIntent: .object(["target_duration_seconds": .number(90)]),
                                     storyGuide: .object([:]), storyCoverage: .object([:]), moments: [],
                                     outputFormat: "vertical")
        let p = try XCTUnwrap(EditPlanJobClient().prepareSubmit(
            req, operationId: "op-abc", owner: "dev", approach: .visualFirst, sheets: [], creativeBrief: "brief",
            critiqueRevision: false, evidenceAccounting: ["eligible": 25], buildProvenance: ["commit_sha": "x"]))
        let text = String(decoding: p.body, as: UTF8.self)
        for needle in ["name=\"operation_id\"", "op-abc", "name=\"body\"", "name=\"sheet_order\"",
                       "name=\"creative_brief\"", "name=\"evidence_accounting\"", "name=\"build_provenance\"",
                       "--\(p.boundary)--"] {
            XCTAssertTrue(text.contains(needle), "missing \(needle)")
        }
    }

    func test_customizeVideoTypeResolvesToTheAttemptType() {
        // StoryCreatingView passes this as createAnotherVersion(requestedEditorialType:) after Customize.
        XCTAssertEqual(ResolvedEditorial.fromLegacy("full").type, .fullStory)
        XCTAssertEqual(ResolvedEditorial.fromLegacy("highlights").type, .highlights)
        XCTAssertNil(ResolvedEditorial.fromLegacy("custom").type, "legacy custom keeps the parent's type")
    }
}
