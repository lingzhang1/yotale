import XCTest
@testable import Story

/// A run that stopped progressing must not block a new Create for its Story (dev 2026-11-27).
final class StaleCreateClaimTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func test_active_recent_run_keeps_the_story() {
        XCTAssertTrue(StoryCreationCoordinator.claimIsLive(
            holderIsCreating: true, holderLastActivity: now.addingTimeInterval(-60), now: now))
    }

    func test_run_without_progress_for_ten_minutes_is_stale() {
        let idle = StoryCreationCoordinator.staleRunAfter
        XCTAssertFalse(StoryCreationCoordinator.claimIsLive(
            holderIsCreating: true, holderLastActivity: now.addingTimeInterval(-idle), now: now))
        XCTAssertFalse(StoryCreationCoordinator.claimIsLive(
            holderIsCreating: true, holderLastActivity: now.addingTimeInterval(-8 * 3600), now: now))
    }

    func test_finished_run_never_holds_the_story() {
        XCTAssertFalse(StoryCreationCoordinator.claimIsLive(
            holderIsCreating: false, holderLastActivity: now, now: now))
    }

    func test_stale_window_is_ten_minutes() {
        XCTAssertEqual(StoryCreationCoordinator.staleRunAfter, 600)
    }
}
