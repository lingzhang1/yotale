import XCTest
@testable import Story

// Focused tests for AudioSessionCoordinator — the serialized, off-main owner of AVAudioSession config.
// These validate the CONTRACT that keeps the main actor unblocked and avoids redundant activation. They do
// not assert on real hardware audio routing (not available/deterministic in a unit test); they assert the
// coordinator's own observable behavior: off-main execution, idempotent redundancy, and error-preserving
// result shape.
final class AudioSessionCoordinatorTests: XCTestCase {

    // apply() must run its (potentially blocking) work OFF the main thread, so a @MainActor caller is never
    // blocked. The actor's executor is not the main thread, so the work reports beganOnMainThread=false.
    func test_apply_runs_off_main_thread() async {
        let r = await AudioSessionCoordinator.shared.apply(.deactivate)
        XCTAssertFalse(r.beganOnMainThread, "audio-session work must not begin on the main thread")
    }

    // A repeated identical playback intent is a no-op (redundant=true, no system call), so switching UI that
    // re-requests the same category does not thrash activation.
    func test_repeated_playback_intent_is_redundant_noop() async {
        let coord = AudioSessionCoordinator.shared
        await coord.invalidate()
        _ = await coord.apply(.playbackDefault)           // first application
        let second = await coord.apply(.playbackDefault)  // identical -> redundant
        XCTAssertTrue(second.redundant, "a repeated identical playback intent should be a redundant no-op")
        XCTAssertEqual(second.elapsedMs, 0, "a redundant no-op makes no system call")
    }

    // invalidate() clears the idempotency memory so the next apply re-asserts (used when capture may have
    // changed the session underneath us) — the following identical intent is NOT treated as redundant.
    func test_invalidate_forces_reassert() async {
        let coord = AudioSessionCoordinator.shared
        await coord.invalidate()
        _ = await coord.apply(.playbackDefault)
        await coord.invalidate()
        let after = await coord.apply(.playbackDefault)
        XCTAssertFalse(after.redundant, "after invalidate, an identical intent must re-assert (not redundant)")
    }

    // deactivate is never treated as redundant (we always honor an explicit release), and the result shape is
    // well-formed (a Sendable value the @MainActor caller can act on).
    func test_deactivate_is_not_redundant_and_returns_result() async {
        let r = await AudioSessionCoordinator.shared.apply(.deactivate)
        XCTAssertFalse(r.redundant, "deactivate is always honored, never a redundant no-op")
        XCTAssertFalse(r.beganOnMainThread)
    }

    // Serialization: many concurrent applies from different tasks all complete without data races or hangs
    // (the actor serializes them). This guards against the preview/result/capture race the fix prevents.
    func test_concurrent_applies_all_complete_serialized() async {
        let coord = AudioSessionCoordinator.shared
        await coord.invalidate()
        await withTaskGroup(of: Bool.self) { group in
            for i in 0..<12 {
                group.addTask {
                    let intent: AudioSessionIntent = (i % 2 == 0) ? .playbackDefault : .deactivate
                    let r = await coord.apply(intent)
                    return !r.beganOnMainThread   // every op ran off-main
                }
            }
            var count = 0
            for await ok in group { XCTAssertTrue(ok); count += 1 }
            XCTAssertEqual(count, 12, "all concurrent audio-session operations complete")
        }
    }
}
