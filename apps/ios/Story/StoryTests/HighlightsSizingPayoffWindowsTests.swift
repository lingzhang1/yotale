import XCTest
@testable import Story

// highlights_sizing/1 (client half): the compact AU payoff windows sent to the duration endpoint. The Highlights length is
// computed by the backend from these; the client only extracts them. Pure JSON tests, no SwiftUI host and no network.
final class HighlightsSizingPayoffWindowsTests: XCTestCase {

    private func au(_ candidates: [[String: JSONValue]]?) -> JSONValue {
        var root: [String: JSONValue] = ["observed": .object(["summary": .string("s")])]
        if let candidates {
            root["editorial"] = .object(["visual_candidates": .array(candidates.map { .object($0) })])
        }
        return .object(root)
    }

    private func vc(_ role: String, _ a: Double, _ b: Double) -> [String: JSONValue] {
        ["role": .string(role), "start_time": .number(a), "end_time": .number(b), "confidence": .number(0.9)]
    }

    func testOnlyPayoffWindowsAreExtracted() {
        let v = au([vc("payoff", 1, 4.5), vc("b_roll", 0, 8), vc("closing", 5, 6), vc("payoff", 10, 13)])
        XCTAssertEqual(EditPlanRequestBuilder.payoffWindowPairs(from: v),
                       .array([.array([.number(1), .number(4.5)]), .array([.number(10), .number(13)])]))
    }

    func testCandidatesWithoutPayoffGiveAnEmptyArrayNotNil() {
        XCTAssertEqual(EditPlanRequestBuilder.payoffWindowPairs(from: au([vc("b_roll", 0, 8)])), .array([]))
    }

    func testNoEditorialVisualCandidatesMeansNoEvidenceNil() {
        XCTAssertNil(EditPlanRequestBuilder.payoffWindowPairs(from: au(nil)))
        XCTAssertNil(EditPlanRequestBuilder.payoffWindowPairs(from: .null))
        XCTAssertNil(EditPlanRequestBuilder.payoffWindowPairs(
            from: .object(["editorial": .object(["narrative_candidates": .array([])])])))
    }

    func testInvalidWindowsAreDropped() {
        let bad: [String: JSONValue] = ["role": .string("payoff"), "start_time": .number(5), "end_time": .number(5)]
        let missing: [String: JSONValue] = ["role": .string("payoff"), "start_time": .number(1)]
        XCTAssertEqual(EditPlanRequestBuilder.payoffWindowPairs(from: au([bad, missing, vc("payoff", 2, 3)])),
                       .array([.array([.number(2), .number(3)])]))
    }

    func testFingerprintKeyChangesWithPayoffWindowsSoStaleRecommendationsAreNotReused() {
        func moment(_ windows: JSONValue) -> JSONValue {
            .object(["id": .string("A"), "duration_seconds": .number(12),
                     "useful_segments": .array([.array([.number(0), .number(10)])]), "payoff_windows": windows])
        }
        let a = DurationService.durationFingerprint(creativeIntent: .null, moments: [moment(.array([]))], requestedScope: nil)
        let b = DurationService.durationFingerprint(creativeIntent: .null,
                                                    moments: [moment(.array([.array([.number(1), .number(4)])]))], requestedScope: nil)
        XCTAssertNotEqual(a, b)
    }
}
