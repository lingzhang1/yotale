import XCTest
@testable import Story

// Director DTO decoding tests (Milestone C3B §11).
//
// Proves the Swift DirectorOutputDTO decodes the canonical backend envelope
// from POST /v1/director/initialize, that shot->beat references survive, and
// that a StoryModel maps back to the CreativeIntent wire contract the Director
// expects. No network — fixed JSON, same shape the backend emits.
final class DirectorDTOTests: XCTestCase {

    private let envelope = """
    {
      "concept": {"id":"11111111-1111-1111-1111-111111111111","title":"Preparation","summary":"The journey begins at home."},
      "plan": {
        "id":"22222222-2222-2222-2222-222222222222",
        "concept_id":"11111111-1111-1111-1111-111111111111",
        "beats":[{"id":"b_prep","purpose":"Show preparation."}],
        "shots":[{"id":"33333333-3333-3333-3333-333333333333","order":1,"beat_id":"b_prep",
                  "purpose":"Capture the packed bag.","instruction":"Film the backpack by the door.",
                  "camera_motion":"static","subject_action":"none","target_duration_seconds":3}]
      },
      "director_state": {"current_beat_id":"b_prep","beat_progress":[]},
      "decision": {"action":"capture_shot",
                   "shot":{"id":"33333333-3333-3333-3333-333333333333","order":1,"beat_id":"b_prep",
                           "purpose":"Capture the packed bag.","instruction":"Film the backpack by the door."}}
    }
    """.data(using: .utf8)!

    func testDecodesDirectorEnvelope() throws {
        let out = try StoryContractCoding.decoder().decode(DirectorOutputDTO.self, from: envelope)
        XCTAssertEqual(out.concept.title, "Preparation")
        XCTAssertEqual(out.plan.beats.count, 1)
        XCTAssertEqual(out.plan.shots.count, 1)
        // referential integrity survives the wire: shot -> real beat
        XCTAssertEqual(out.plan.shots[0].beatId, out.plan.beats[0].id)
        XCTAssertEqual(out.decision.action, .captureShot)
        // capture_shot carries a shot with a user-facing instruction
        XCTAssertEqual(out.decision.shot?.instruction, "Film the backpack by the door.")
        XCTAssertEqual(out.plan.shots[0].targetDurationSeconds, 3)
        // envelope/1 shape (no reference map) still decodes; no photo query => text-only card
        XCTAssertTrue(out.shotReferenceQueries.isEmpty)
        XCTAssertNil(out.referenceQuery(for: out.plan.shots[0].id))
    }

    // MARK: - Phase 1A: shot_reference_queries (story_director.envelope/2)

    private func envelopeWithMap(_ mapJSON: String) -> Data {
        var s = String(data: envelope, encoding: .utf8)!
        let end = s.lastIndex(of: "}")!
        s.replaceSubrange(end...end, with: ", \"shot_reference_queries\": \(mapJSON) }")
        return s.data(using: .utf8)!
    }

    func testDecodesReferenceQueryAndLooksUpByShotUUID() throws {
        let data = envelopeWithMap(#"{"33333333-3333-3333-3333-333333333333": "close up backpack by door"}"#)
        let out = try StoryContractCoding.decoder().decode(DirectorOutputDTO.self, from: data)
        // Swift UUID.uuidString is UPPERCASE; the server key is lowercase — lookup must still hit.
        let shotId = try XCTUnwrap(out.decision.shot?.id)
        XCTAssertEqual(out.referenceQuery(for: shotId), "close up backpack by door")
    }

    func testReferenceQueryForUnknownShotIsNil() throws {
        let data = envelopeWithMap(#"{"44444444-4444-4444-4444-444444444444": "wide shot room"}"#)
        let out = try StoryContractCoding.decoder().decode(DirectorOutputDTO.self, from: data)
        XCTAssertNil(out.referenceQuery(for: out.plan.shots[0].id),
                     "another idea's query must never be shown on this idea")
    }

    func testMalformedReferenceMapNeverFailsDirectorDecode() throws {
        let data = envelopeWithMap(#"["not", "a", "map"]"#)
        let out = try StoryContractCoding.decoder().decode(DirectorOutputDTO.self, from: data)
        XCTAssertEqual(out.concept.title, "Preparation")
        XCTAssertTrue(out.shotReferenceQueries.isEmpty)
    }

    func testBlankReferenceQueryIsTreatedAsNone() throws {
        let data = envelopeWithMap(#"{"33333333-3333-3333-3333-333333333333": "   "}"#)
        let out = try StoryContractCoding.decoder().decode(DirectorOutputDTO.self, from: data)
        XCTAssertNil(out.referenceQuery(for: out.plan.shots[0].id))
    }

    func testCreativeIntentMapsFromStory() throws {
        let story = StoryModel(
            title: "TMB", intentRawText: "8 days hiking in TMB",
            intentTheme: "adventure", intentTone: "peaceful",
            intentSummary: "8-day Tour du Mont Blanc hike")
        story.intentDesiredFeeling = ["peaceful", "adventurous"]
        story.intentEmphasis = ["journey"]
        story.intentPace = "slow"
        story.intentTargetDurationSeconds = 60

        let ci = CreativeIntentContractDTO(from: story)
        XCTAssertEqual(ci.summary, "8-day Tour du Mont Blanc hike")
        XCTAssertEqual(ci.desiredFeeling, ["peaceful", "adventurous"])
        XCTAssertEqual(ci.emphasis, ["journey"])
        XCTAssertEqual(ci.pace, .slow)
        XCTAssertEqual(ci.targetDurationSeconds, 60)
    }
}
