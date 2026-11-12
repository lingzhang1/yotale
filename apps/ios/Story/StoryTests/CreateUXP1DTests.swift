import XCTest
@testable import Story

// P1-D §14 — offline tests for the PURE Create-UX decision logic: Video Type seeding (Highlights default,
// historical custom != Full Story), the independent Recommended/Custom duration seed, and the default-ON
// EditorialTypeFlag with override precedence. The full on-device matrix (type switch updates the estimate,
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

    func testSavedRecommendedPickReopensRecommendedEvenWhenTodaysPointsDiffer() {
        // beta 2026-11-12: a 67.5 s Recommended pick, today's points 53/95 — must NOT reopen as Custom 67.5 s.
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 67.5,
                                            recommendedPoints: [53, 95], savedChoice: "recommended"), .recommended)
    }

    func testSavedCustomPickReopensCustomEvenWhenItMatchesAPoint() {
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 53,
                                            recommendedPoints: [53, 95], savedChoice: "custom"), .custom)
    }

    func testNoSavedChoiceFallsBackToPointMatchingForOlderStories() {
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 53.4,
                                            recommendedPoints: [53, 95], savedChoice: nil), .recommended)
        XCTAssertEqual(V.seedDurationChoice(editorialMode: "highlights", explicitTarget: 67.5,
                                            recommendedPoints: [53, 95], savedChoice: "garbage"), .custom)
    }

    func testDurationChoiceWireRoundTrips() {
        for c in [V.DurationChoice.recommended, .custom] { XCTAssertEqual(V.DurationChoice(rawValue: c.wire), c) }
    }

    // MARK: - Duration recommendation cache key = footage only

    private func moment(_ id: String, _ dur: Double, summary: String = "a", segmentEnd: Double = 10) -> JSONValue {
        .object(["id": .string(id), "duration_seconds": .number(dur),
                 "useful_segments": .array([.array([.number(0), .number(segmentEnd)])]), "summary": .string(summary)])
    }

    private func fp(target: Double?, type: String = "highlights", _ moments: [JSONValue]) -> String {
        DurationService.durationFingerprint(
            creativeIntent: .object(["target_duration_seconds": target.map { .number($0) } ?? .null,
                                     "editorial_mode": .string(type), "theme": .string("trip")]),
            moments: moments, requestedScope: nil)
    }

    func testRecommendationKeyIgnoresTheChosenTargetAndType() {
        let ms = [moment("A", 12), moment("B", 30)]
        XCTAssertEqual(fp(target: nil, ms), fp(target: 67.5, ms))
        XCTAssertEqual(fp(target: 53, ms), fp(target: 90, type: "full", ms))
    }

    func testRecommendationKeyChangesWhenFootageChanges() {
        let base = fp(target: nil, [moment("A", 12), moment("B", 30)])
        XCTAssertNotEqual(base, fp(target: nil, [moment("A", 12)]))                          // Moment removed
        XCTAssertNotEqual(base, fp(target: nil, [moment("A", 12), moment("B", 30), moment("C", 5)]))  // added
        XCTAssertNotEqual(base, fp(target: nil, [moment("A", 12), moment("B", 31)]))         // duration
        XCTAssertNotEqual(base, fp(target: nil, [moment("A", 12), moment("B", 30, summary: "b")]))   // AU
        XCTAssertNotEqual(base, fp(target: nil, [moment("A", 12), moment("B", 30, segmentEnd: 8)]))   // AU
    }

    func testRecommendationKeyToleratesMillisecondDurationNoise() {
        XCTAssertEqual(fp(target: nil, [moment("A", 12.001)]), fp(target: nil, [moment("A", 11.998)]))
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

    // MARK: - EditorialTypeFlag default-ON + override precedence (§11)

    func testFlagDefaultsOnWithNoOverride() {
        // No env override possible in-test; clear any UserDefaults override -> baseline must be ON.
        EditorialTypeFlag.setOverride(nil)
        XCTAssertTrue(EditorialTypeFlag.enabled, "P1-D: Editing v2 is the product default")
    }

    func testUserDefaultsOverrideForcesOff() {
        EditorialTypeFlag.setOverride(false)
        XCTAssertFalse(EditorialTypeFlag.enabled, "an explicit override must win over the default")
        EditorialTypeFlag.setOverride(nil)   // restore baseline; a cleared override must not persist
        XCTAssertTrue(EditorialTypeFlag.enabled)
    }

    func testOverrideCanBeClearedToAvoidStaleContamination() {
        EditorialTypeFlag.setOverride(true)
        EditorialTypeFlag.setOverride(nil)   // §11: a stale dev toggle must be clearable, not sticky
        XCTAssertNil(UserDefaults.standard.object(forKey: EditorialTypeFlag.key))
        XCTAssertTrue(EditorialTypeFlag.enabled)
    }
}
