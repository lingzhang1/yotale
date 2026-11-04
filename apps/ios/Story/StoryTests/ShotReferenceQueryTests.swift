import XCTest
import SwiftUI
@testable import Story

// Phase 1A — ShotReferenceQuery: deterministic, generic stock-photo query builder for the live-camera
// Shooting Idea card. These tests prove the MATCHING MATRIX (owner §10) and the grounding safeguards:
//   * Composition/subject signals produce a short, GENERIC, composition-first phrase.
//   * An abstract idea with no reliable visual signal returns nil => text-only (never a placeholder).
//   * The query NEVER contains the raw instruction paragraph, URLs, emails, or personal data.
// Pure logic — no network, no model, CI-safe.
final class ShotReferenceQueryTests: XCTestCase {

    private func shot(framing: String? = nil, cameraMotion: String? = nil,
                      subjectAction: String? = nil, instruction: String = "") -> ShotContractDTO {
        ShotContractDTO(id: UUID(), order: 0, instruction: instruction, beatId: nil, purpose: nil,
                        targetDurationSeconds: 4, framing: framing, cameraMotion: cameraMotion,
                        subjectAction: subjectAction, exampleAssetId: nil)
    }

    // MARK: - Matching matrix

    func testOfficeDesk_closeUpWorkspace() throws {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "close-up", subjectAction: "typing on a laptop keyboard",
                       instruction: "Frame your desk and hands."),
            conceptTitle: "A Quiet Moment at Work", conceptSummary: "A calm desk scene")
        let qq = try XCTUnwrap(q).lowercased()
        XCTAssertTrue(qq.contains("close up"), "should lead with composition: \(qq)")
        XCTAssertTrue(qq.contains("workspace") || qq.contains("keyboard"), "subject category: \(qq)")
    }

    func testOfficeAisle_symmetricalLeadingLines() {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "symmetrical corridor", instruction: "Shoot straight down the office aisle."),
            conceptTitle: "Down the Aisle", conceptSummary: "An office corridor")
        let qq = (q ?? "").lowercased()
        XCTAssertTrue(qq.contains("symmetrical") || qq.contains("leading lines"), "composition: \(qq)")
    }

    func testMountainLandscape_wideScenic() {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "wide establishing", subjectAction: "mountain reveal"),
            conceptTitle: "The Summit Reveal", conceptSummary: "A scenic mountain vista")
        let qq = (q ?? "").lowercased()
        XCTAssertTrue(qq.contains("wide") || qq.contains("landscape"), "composition: \(qq)")
        XCTAssertTrue(qq.contains("mountain"), "subject: \(qq)")
    }

    func testCityStreetWalking_backView() {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "back view", subjectAction: "person walking away",
                       instruction: "Follow them down the street."),
            conceptTitle: "A Walk Through the City", conceptSummary: "Someone walking a city street")
        let qq = (q ?? "").lowercased()
        XCTAssertTrue(qq.contains("back view") || qq.contains("walking"), "walking subject: \(qq)")
    }

    func testFoodPreparation_handsDetail() {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "close-up", subjectAction: "chopping vegetables",
                       instruction: "Capture the cooking hands."),
            conceptTitle: "Preparing Dinner", conceptSummary: "Hands cooking in the kitchen")
        let qq = (q ?? "").lowercased()
        XCTAssertTrue(qq.contains("food preparation") || qq.contains("hands") || qq.contains("close up"),
                      "food/hands: \(qq)")
    }

    func testHumanInteraction_portraitOrFace() {
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "portrait", subjectAction: "two people talking and smiling"),
            conceptTitle: "A Shared Laugh", conceptSummary: "Friends in conversation")
        XCTAssertNotNil(q, "a clear portrait/subject idea should produce a query")
        XCTAssertTrue((q ?? "").lowercased().contains("portrait"), "composition: \(q ?? "")")
    }

    // MARK: - Abstract / no-match -> nil (text-only, never a placeholder)

    func testAbstractIdea_noReliableSignal_returnsNil() {
        // No composition, no subject vocabulary hit — only a vague mood/environment.
        let q = ShotReferenceQuery.build(
            shot: shot(instruction: "Capture the feeling of the moment."),
            conceptTitle: "Something Meaningful", conceptSummary: "A feeling worth remembering")
        XCTAssertNil(q, "an abstract idea with no grounded visual signal must omit the image")
    }

    func testEnvironmentOnly_isTooWeak_returnsNil() {
        // "office" alone is a weak-only token — not enough to return a RELEVANT photo.
        let q = ShotReferenceQuery.build(shot: shot(instruction: "At the office."),
                                         conceptTitle: "At the Office", conceptSummary: "")
        XCTAssertNil(q, "environment-only signal is too weak; conservative matching omits it")
    }

    // MARK: - Grounding safeguards: never leak the raw paragraph / personal data

    func testQueryIsGenericAndBounded_noRawParagraph() throws {
        let longInstruction = "Move closer to Sarah's desk by the window and film her hands on the laptop " +
            "keyboard for about four seconds, keeping her face out of frame — see https://example.com"
        let q = ShotReferenceQuery.build(
            shot: shot(framing: "close-up", subjectAction: "typing", instruction: longInstruction),
            conceptTitle: "A Quiet Moment at Work", conceptSummary: "")
        let qq = try XCTUnwrap(q)
        XCTAssertLessThanOrEqual(qq.count, 120, "bounded phrase, not the paragraph")
        XCTAssertFalse(qq.lowercased().contains("sarah"), "must not leak a personal name")
        XCTAssertFalse(qq.contains("http"), "must not leak a URL")
        XCTAssertFalse(qq.contains("@"), "must not leak an email")
        XCTAssertFalse(qq.contains("four seconds"), "must not echo the raw instruction text")
    }

    func testDeterministic_sameInputsSameOutput() {
        let a = ShotReferenceQuery.build(shot: shot(framing: "close-up", subjectAction: "keyboard"),
                                         conceptTitle: "Work", conceptSummary: "desk")
        let b = ShotReferenceQuery.build(shot: shot(framing: "close-up", subjectAction: "keyboard"),
                                         conceptTitle: "Work", conceptSummary: "desk")
        XCTAssertEqual(a, b, "builder must be pure/deterministic")
    }

    func testNilShot_usesTitleOnly_forSeededGuideIdea() {
        // A seeded guide idea has no Director shot; a generic title should still yield a query when it
        // carries a real subject/composition word, else nil.
        let q = ShotReferenceQuery.build(shot: nil, conceptTitle: "Hiking the Mountain Trail",
                                         conceptSummary: nil)
        XCTAssertNotNil(q)
        XCTAssertTrue((q ?? "").lowercased().contains("mountain") || (q ?? "").lowercased().contains("walking"),
                      "title-derived subject: \(q ?? "")")
    }

    // MARK: - Color(hex:) parsing for the dominant-color placeholder

    func testColorHexParsing() {
        XCTAssertNotNil(Color(hex: "#c0a080"))
        XCTAssertNotNil(Color(hex: "c0a080"))
        XCTAssertNil(Color(hex: "#fff"), "3-digit shorthand not supported -> nil (safe fallback)")
        XCTAssertNil(Color(hex: "not-a-color"))
        XCTAssertNil(Color(hex: ""))
    }
}
