import XCTest
import SwiftUI
@testable import Story

// Color(hex: String) parsing for the Unsplash dominant-color placeholder on the Shooting Idea card
// (moved here from the removed ShotReferenceQueryTests).
final class ColorHexTests: XCTestCase {
    func testColorHexParsing() {
        XCTAssertNotNil(Color(hex: "#c0a080"))
        XCTAssertNotNil(Color(hex: "c0a080"))
        XCTAssertNil(Color(hex: "#fff"), "3-digit shorthand not supported -> nil (safe fallback)")
        XCTAssertNil(Color(hex: "not-a-color"))
        XCTAssertNil(Color(hex: ""))
    }
}
