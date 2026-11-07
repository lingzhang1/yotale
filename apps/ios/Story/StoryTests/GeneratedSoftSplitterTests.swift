import XCTest
@testable import Story

// Device-test regression (2026-11-06): generated soft sentences ("Prefer shorter, punchier shots", "Make the cuts
// follow the music", the Mood phrase) were saved into the draft text and, on reopen, fed to the AI interpreter as
// if the user had typed them — which flagged one as "unsupported" and blocked Create. They must split back out.
final class GeneratedSoftSplitterTests: XCTestCase {

    private let generated = [
        "Prefer shorter, punchier shots",
        "Let the scenic shots breathe a little longer",
        "Make the cuts follow the music",
        "Keep the original audio from the clips",
        "Give it a cinematic feel",
    ]

    func test_exact_text_from_the_device_screenshot_leaves_no_user_text() {
        let saved = "Prefer shorter, punchier shots. Make the cuts follow the music. Give it a cinematic feel"
        let r = GeneratedSoftSplitter.split(saved, generated: generated)
        XCTAssertEqual(r.userText, "", "nothing the user typed => nothing reaches the interpreter")
        XCTAssertEqual(r.matched, ["Prefer shorter, punchier shots", "Make the cuts follow the music",
                                   "Give it a cinematic feel"])
    }

    func test_users_own_words_are_kept_and_come_first() {
        let saved = "Start with the mountain reveal. Make the cuts follow the music. Give it a cinematic feel"
        let r = GeneratedSoftSplitter.split(saved, generated: generated)
        XCTAssertEqual(r.userText, "Start with the mountain reveal")
        XCTAssertEqual(r.matched.count, 2)
    }

    func test_trailing_period_and_case_do_not_defeat_matching() {
        let r = GeneratedSoftSplitter.split("make the cuts follow the music.", generated: generated)
        XCTAssertEqual(r.userText, "")
        XCTAssertEqual(r.matched, ["Make the cuts follow the music"])
    }

    func test_a_similar_user_sentence_is_not_swallowed() {
        let saved = "Make the cuts follow the music of the waterfall"   // user's own, merely resembles a phrase
        let r = GeneratedSoftSplitter.split(saved, generated: generated)
        XCTAssertEqual(r.userText, saved)
        XCTAssertTrue(r.matched.isEmpty)
    }

    func test_empty_and_no_generated_text_are_unchanged() {
        XCTAssertEqual(GeneratedSoftSplitter.split("", generated: generated).userText, "")
        let r = GeneratedSoftSplitter.split("Opening on the sunrise, then the climb.", generated: generated)
        XCTAssertEqual(r.userText, "Opening on the sunrise, then the climb.")
        XCTAssertTrue(r.matched.isEmpty)
    }

    func test_split_is_idempotent() {
        let once = GeneratedSoftSplitter.split("Hello there. Give it a cinematic feel", generated: generated)
        let twice = GeneratedSoftSplitter.split(once.userText, generated: generated)
        XCTAssertEqual(once.userText, twice.userText)
        XCTAssertTrue(twice.matched.isEmpty)
    }
}
