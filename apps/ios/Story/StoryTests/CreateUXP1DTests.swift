import XCTest
@testable import Story

// P1-D §14 — offline tests for the PURE Create-UX decision logic: Video Type seeding (Highlights default,
// historical custom != Full Story), the independent Recommended/Custom duration seed, and the
// (flag-free) standard editorial behavior. The full on-device matrix (type switch updates the estimate,
// chip insertion, More Options expand/collapse, Revise inherit, Explore switch, async submit/resume) runs
// via StoryCreationCoordinatorTests + ⌘U; these cover the deterministic units without a SwiftUI host.
final class CreateUXP1DTests: XCTestCase {

    typealias V = CustomizeYourStoryView

    // MARK: - Video Type seeding (§4 / §12) — option B: ALWAYS opens Highlights

    func testUnselectedOriginalSeedsHighlights() {
        XCTAssertEqual(V.seedVideoType(editorialMode: nil), .highlights)
        XCTAssertEqual(V.seedVideoType(editorialMode: ""), .highlights)
    }

    func testSeedAlwaysHighlightsRegardlessOfPersistedMode() {
        // Owner decision (option B): the sheet always opens on Highlights — a prior Full Story generation does
        // NOT pre-select Full Story on re-open; the user opts into Full Story per attempt.
        XCTAssertEqual(V.seedVideoType(editorialMode: "full"), .highlights)
        XCTAssertEqual(V.seedVideoType(editorialMode: "highlights"), .highlights)
        XCTAssertEqual(V.seedVideoType(editorialMode: "custom"), .highlights)   // custom is a duration fact
        XCTAssertEqual(V.seedVideoType(editorialMode: "visual_first"), .highlights) // old approach is NOT a type
    }

    // MARK: - Duration is INDEPENDENT of type (§8)

    func testHistoricalCustomSeedsCustomDuration() {
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "custom", explicitTarget: 45), .custom)
    }

    func testExplicitTargetSeedsCustomDuration() {
        // A prior explicit target (non-nil) opens the duration control as Custom...
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 30), .custom)
    }

    func testNoExplicitTargetSeedsRecommended() {
        // ...while no explicit target (a fresh/recommended selection) opens as Recommended.
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: nil), .recommended)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "full", explicitTarget: nil), .recommended)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: nil, explicitTarget: nil), .recommended)
    }

    // MARK: - "always 50s" regression (dev device test 2026-11-11, TMB Hiking, 25 Moments)

    func testPriorRecommendedTargetReopensAsRecommended() {
        // A previous Recommended pick persisted 50s (= the Highlights point). Reopening must stay Recommended so
        // choosing Full Story submits its own point (90s) instead of the stale 50s Custom value.
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 50,
                                            recommendedPoints: [50, 90]), .recommended)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "full", explicitTarget: 90,
                                            recommendedPoints: [50, 90]), .recommended)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "full", explicitTarget: 90.4,
                                            recommendedPoints: [50, 89.6]), .recommended)   // ±1s rounding
    }

    func testPriorTypedTargetStillReopensAsCustom() {
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 32,
                                            recommendedPoints: [50, 90]), .custom)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "custom", explicitTarget: 50,
                                            recommendedPoints: [50, 90]), .custom)        // historical custom wins
    }

    func testCustomFloorIsNotTiedToMomentCount() {
        // The duration planner's band floor is 2s per Moment (25 Moments -> 50s). 16s and 32s must be accepted.
        XCTAssertEqual(V.customFloor(bandFloor: 50), V.minCustomSeconds)
        XCTAssertLessThanOrEqual(V.customFloor(bandFloor: 50), 16)
        XCTAssertEqual(V.customFloor(bandFloor: 4), 4)          // very little footage -> its own floor
        XCTAssertEqual(V.customFloor(bandFloor: 1), 3)          // never below 3s
        XCTAssertEqual(V.customFloor(bandFloor: nil), V.minCustomSeconds)
    }

    func testCustomSecondsTextParsesEveryKeystroke() {
        XCTAssertEqual(V.parseSeconds("16"), 16)
        XCTAssertEqual(V.parseSeconds("3"), 3)
        XCTAssertEqual(V.parseSeconds(" 32s"), 32)
        XCTAssertNil(V.parseSeconds(""))
        XCTAssertNil(V.parseSeconds("abc"))
    }

    func testVideoTypeWireValuesMatchContract() {
        XCTAssertEqual(V.VideoType.highlights.wire, "highlights")
        XCTAssertEqual(V.VideoType.full.wire, "full")
    }
}
