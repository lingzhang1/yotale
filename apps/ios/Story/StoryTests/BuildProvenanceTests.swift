import XCTest
@testable import Story

// Build provenance sent with every EditPlan job: the contact-sheet SELECTION policy is recorded separately from
// the AU frame EXTRACTION policy, so an A/B can identify exactly which sheet mapper ran.
final class BuildProvenanceTests: XCTestCase {

    func test_selection_policy_is_reported_and_distinct_from_extraction_frame_policy() {
        let p = BuildProvenance.current(requestedApproach: "visual_first", multimodalEnabled: true,
                                        extractionPolicy: MomentFrameExtractor.extractionPolicy)
        let d = p.asRequestDictionary()
        XCTAssertEqual(d["selection_policy"] as? String, EvidenceFrameMapper.policyVersion)
        XCTAssertEqual(d["selection_policy"] as? String, "evidence_select/2")
        XCTAssertEqual(d["frame_policy"] as? String, MomentFrameExtractor.framePolicy)
        XCTAssertNotEqual(d["selection_policy"] as? String, d["frame_policy"] as? String)
    }

    func test_commit_sha_is_never_an_unresolved_build_token() {
        let sha = BuildProvenance.current(requestedApproach: "storytelling", multimodalEnabled: false,
                                          extractionPolicy: "x").commitSHA
        XCTAssertFalse(sha.isEmpty)
        XCTAssertFalse(sha.hasPrefix("$("), "an unstamped build must report 'unknown', not a raw token")
    }
}
