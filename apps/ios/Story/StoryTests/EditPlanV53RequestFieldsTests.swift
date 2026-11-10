import XCTest
@testable import Story

// P1-F pre-beta alignment — the EditPlan v5.3 request must carry the Rich AU editorial text for each Moment:
// editorial candidates, timestamped events and server-minted sampled_frame_ms (the backend reporting 5.3 is
// not enough if the client never sends them). The backend half (retention under v5.3, stripping under a 5.2
// rollback) is covered by apps/api/tests/test_edit_plan_v53.py.
final class EditPlanV53RequestFieldsTests: XCTestCase {

    private let rich = """
    {"schema_version":"moment_understanding/2","sampled_frame_ms":[0,1500,3000],
     "editorial":{
       "visual_candidates":[{"start_time":1.0,"end_time":2.0,"peak_time":1.5,"confidence":0.8,
                             "label":"reveal","evidence":"UNTRUSTED model-invented timing text"}],
       "narrative_candidates":[{"start_time":0.0,"end_time":3.0,"confidence":0.6}]},
     "observed":{"summary":"s","events":[{"start_time":1.0,"description":"face reveal"}]}}
    """

    private func arr(_ v: JSONValue?) -> [JSONValue]? { if case .array(let a)? = v { return a }; return nil }
    private func obj(_ v: JSONValue?) -> [String: JSONValue]? { if case .object(let o)? = v { return o }; return nil }

    func test_rich_au_fields_reach_the_planner_request() {
        let out = EditPlanRequestBuilder.editorialV53Fields(from: JSONValue.object(fromJSONString: rich))
        // sampled_frame_ms forwarded verbatim.
        XCTAssertEqual(arr(out["sampled_frame_ms"]), [.number(0), .number(1500), .number(3000)])
        // observed.events forwarded.
        XCTAssertEqual(arr(out["events"])?.count, 1)
        // editorial block forwarded with both candidate lists.
        let ed = obj(out["editorial"])
        XCTAssertEqual(arr(ed?["visual_candidates"])?.count, 1)
        XCTAssertEqual(arr(ed?["narrative_candidates"])?.count, 1)
        // Candidate context survives (peak is advisory but kept), the untrusted `evidence` string does not.
        let vc = obj(arr(ed?["visual_candidates"])?.first)
        XCTAssertEqual(vc?["peak_time"], .number(1.5))
        XCTAssertEqual(vc?["label"], .string("reveal"))
        XCTAssertNil(vc?["evidence"])
    }

    func test_older_record_forwards_nothing_and_fabricates_nothing() {
        let v1 = JSONValue.object(fromJSONString: #"{"schema_version":"moment_understanding/1","observed":{"summary":"s"}}"#)
        XCTAssertTrue(EditPlanRequestBuilder.editorialV53Fields(from: v1).isEmpty)
    }
}
