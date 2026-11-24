import XCTest
import AVFoundation
@testable import Story

// P0 camera capture quality: stabilization policy, screen-awake ownership, zoom continuity + conversion.
// Pure logic only (no camera hardware): the AVFoundation-facing code delegates every decision to these types.

// MARK: - Stabilization policy

final class CaptureStabilizationPolicyTests: XCTestCase {
    private func pick(_ supported: Set<AVCaptureVideoStabilizationMode>, connection: Bool = true) -> AVCaptureVideoStabilizationMode {
        CaptureStabilization.select(connectionSupportsStabilization: connection, isSupported: { supported.contains($0) })
    }

    func testPrefersCinematicExtendedWhenSupported() {
        XCTAssertEqual(pick([.standard, .cinematic, .cinematicExtended, .cinematicExtendedEnhanced]), .cinematicExtended)
    }

    func testNeverPicksEnhancedEvenWhenItIsTheStrongestSupported() {
        // Enhanced narrows the field of view further; it is not in the default policy.
        XCTAssertEqual(pick([.cinematicExtendedEnhanced, .cinematic]), .cinematic)
        XCTAssertFalse(CaptureStabilization.recordingPreference.contains(.cinematicExtendedEnhanced))
    }

    func testFallsBackToCinematicThenStandard() {
        XCTAssertEqual(pick([.cinematic, .standard]), .cinematic)
        XCTAssertEqual(pick([.standard]), .standard)
    }

    func testOffWhenNothingSupported() {
        XCTAssertEqual(pick([]), .off)
        XCTAssertEqual(pick([.previewOptimized]), .off, "a preview-only mode is never used for the recorded file")
    }

    func testOffWhenConnectionDoesNotSupportStabilization() {
        XCTAssertEqual(pick([.cinematicExtended], connection: false), .off)
    }

    func testCameraSwitchReselectsForTheNewFormat() {
        // Back triple camera supports extended; a front camera format may only offer standard.
        XCTAssertEqual(pick([.standard, .cinematic, .cinematicExtended]), .cinematicExtended)
        XCTAssertEqual(pick([.standard]), .standard)
    }

    func testActiveFormatChangeReselects() {
        let fourK: Set<AVCaptureVideoStabilizationMode> = [.standard]
        let hd: Set<AVCaptureVideoStabilizationMode> = [.standard, .cinematic]
        XCTAssertEqual(pick(fourK), .standard)
        XCTAssertEqual(pick(hd), .cinematic)
    }

    func testPreviewUsesPreviewOptimizedOnlyWhenSupported() {
        XCTAssertEqual(CaptureStabilization.selectPreview(connectionSupportsStabilization: true,
                                                          isSupported: { $0 == .previewOptimized }), .previewOptimized)
        XCTAssertEqual(CaptureStabilization.selectPreview(connectionSupportsStabilization: true,
                                                          isSupported: { $0 == .cinematicExtended }), .off,
                       "the preview never borrows the recording mode")
        XCTAssertEqual(CaptureStabilization.selectPreview(connectionSupportsStabilization: false,
                                                          isSupported: { _ in true }), .off)
    }

    func testStatusReportsActiveModeNotTheRequest() {
        XCTAssertEqual(StabilizationStatus(requested: .cinematicExtended, active: .cinematicExtended).summary,
                       "stab cinematicExtended")
        XCTAssertEqual(StabilizationStatus(requested: .cinematicExtended, active: .off).summary,
                       "stab off (asked cinematicExtended)")
    }
}

// MARK: - Screen awake

@MainActor
final class ScreenAwakeTests: XCTestCase {
    private var writes: [Bool] = []
    private func make(active: Bool = true) -> ScreenAwake { ScreenAwake(apply: { [weak self] in self?.writes.append($0) }, appIsActive: active) }

    func testHoldDisablesIdleTimerAndReleaseRestoresIt() {
        let a = make()
        a.hold("camera")
        XCTAssertEqual(writes, [true])
        a.release("camera")
        XCTAssertEqual(writes, [true, false])
    }

    func testClaimsAreIdempotent() {
        let a = make()
        a.hold("camera"); a.hold("camera"); a.hold("camera")
        a.release("camera")
        XCTAssertFalse(a.isScreenHeldAwake, "repeated appear must not leak a counter")
        a.release("camera"); a.release("unknown")
        XCTAssertEqual(writes, [true, false])
    }

    func testOneOwnerCannotClearAnothersClaim() {
        let a = make()
        a.hold("create.view")
        a.hold("camera.preview.x")
        a.release("create.view")
        XCTAssertTrue(a.isScreenHeldAwake)
        a.release("camera.preview.x")
        XCTAssertFalse(a.isScreenHeldAwake)
    }

    func testBackgroundSuspendsAndForegroundRestores() {
        let a = make()
        a.hold("camera")
        a.setAppActive(false)
        XCTAssertFalse(a.isScreenHeldAwake, "never hold the display while backgrounded")
        XCTAssertTrue(a.isHeld("camera"), "the claim survives backgrounding")
        a.setAppActive(true)
        XCTAssertTrue(a.isScreenHeldAwake)
        XCTAssertEqual(writes, [true, false, true])
    }

    func testClaimTakenWhileBackgroundedAppliesOnlyOnForeground() {
        let a = make(active: false)
        a.hold("camera")
        XCTAssertEqual(writes, [])
        a.setAppActive(true)
        XCTAssertEqual(writes, [true])
    }
}

@MainActor
final class CaptureScreenAwakeTests: XCTestCase {
    private func make(idle: TimeInterval = 0.05) -> (ScreenAwake, CaptureScreenAwake) {
        let a = ScreenAwake(apply: { _ in })
        return (a, CaptureScreenAwake(awake: a, idleWindow: idle))
    }

    func testOpenHoldsAndCloseReleases() {
        let (a, c) = make(idle: 60)
        c.appear()
        XCTAssertTrue(a.isScreenHeldAwake)
        c.disappear()
        XCTAssertFalse(a.isScreenHeldAwake)
        XCTAssertTrue(a.activeClaims.isEmpty)
    }

    func testRecordingHoldsPastTheIdleWindow() async throws {
        let (a, c) = make()
        c.appear()
        c.recordingChanged(true)
        try await Task.sleep(nanoseconds: 200_000_000)
        XCTAssertFalse(c.holdsPreview, "idle window expired")
        XCTAssertTrue(c.holdsRecording)
        XCTAssertTrue(a.isScreenHeldAwake, "an active recording keeps the screen on")
    }

    func testStopRecordingRearmsPreviewThenIdleReleases() async throws {
        let (a, c) = make()
        c.appear()
        c.recordingChanged(true)
        c.recordingChanged(false)
        XCTAssertFalse(c.holdsRecording)
        XCTAssertTrue(c.holdsPreview)
        try await Task.sleep(nanoseconds: 200_000_000)
        XCTAssertFalse(a.isScreenHeldAwake, "normal auto-lock returns after the idle window")
    }

    func testInteractionExtendsTheIdleWindow() async throws {
        let (_, c) = make(idle: 0.15)
        c.appear()
        try await Task.sleep(nanoseconds: 100_000_000)
        c.interaction()
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertTrue(c.holdsPreview, "the interaction re-armed the window")
    }

    func testRapidInteractionsAreThrottledButStillExtend() async throws {
        let (_, c) = make(idle: 0.2)
        c.appear()
        for _ in 0..<100 { c.interaction() }   // a pinch burst
        XCTAssertTrue(c.holdsPreview)
        try await Task.sleep(nanoseconds: 120_000_000)
        c.interaction()                          // past the throttle (window/4): re-arms
        try await Task.sleep(nanoseconds: 120_000_000)
        XCTAssertTrue(c.holdsPreview, "the later interaction extended the window")
        try await Task.sleep(nanoseconds: 200_000_000)
        XCTAssertFalse(c.holdsPreview)
    }

    func testRepeatedAppearDisappearLeavesNoClaims() {
        let (a, c) = make(idle: 60)
        for _ in 0..<5 { c.appear(); c.appear(); c.disappear() }
        XCTAssertTrue(a.activeClaims.isEmpty)
    }

    func testUnexpectedInterruptionReleasesRecordingClaim() {
        let (_, c) = make(idle: 60)
        c.appear()
        c.recordingChanged(true)
        c.recordingChanged(false)   // .interrupted / .captureFailed path
        XCTAssertFalse(c.holdsRecording)
    }

    func testCloseDuringRecordingReleasesEverything() {
        let (a, c) = make(idle: 60)
        c.appear(); c.recordingChanged(true)
        c.disappear()
        XCTAssertTrue(a.activeClaims.isEmpty)
    }

    func testTwoCaptureScreensDoNotReleaseEachOther() {
        let a = ScreenAwake(apply: { _ in })
        let c1 = CaptureScreenAwake(awake: a, idleWindow: 60)
        let c2 = CaptureScreenAwake(awake: a, idleWindow: 60)
        c1.appear(); c2.appear()
        c1.disappear()
        XCTAssertTrue(a.isScreenHeldAwake)
        c2.disappear()
        XCTAssertFalse(a.isScreenHeldAwake)
    }
}

// MARK: - Zoom conversion + gestures

final class CameraZoomScaleTests: XCTestCase {
    // Triple/dual-wide virtual device: raw 1.0 = ultra-wide (0.5×), raw 2.0 = wide (1×).
    private let ultraWide = CameraZoomScale(multiplier: 0.5, minRaw: 1, maxRaw: 30)
    // Wide-only or front camera.
    private let wideOnly = CameraZoomScale(multiplier: 1, minRaw: 1, maxRaw: 10)

    func testVirtualDeviceConversion() {
        XCTAssertEqual(ultraWide.display(fromRaw: 1), 0.5)
        XCTAssertEqual(ultraWide.display(fromRaw: 2), 1)
        XCTAssertEqual(ultraWide.raw(fromDisplay: 1), 2)
        XCTAssertEqual(ultraWide.raw(fromDisplay: 0.5), 1)
        XCTAssertEqual(ultraWide.displayRange, 0.5...15)
    }

    func testOpensAtDisplayedOneX() {
        XCTAssertEqual(ultraWide.initialRaw, 2, "not raw 1.0, which is the ultra-wide")
        XCTAssertEqual(wideOnly.initialRaw, 1)
    }

    func testOneXUnreachableFallsBackToNearestAndDisplaysIt() {
        let teleOnly = CameraZoomScale(multiplier: 1, minRaw: 1.5, maxRaw: 6)
        XCTAssertEqual(teleOnly.initialRaw, 1.5)
        XCTAssertEqual(teleOnly.display(fromRaw: teleOnly.initialRaw), 1.5, "shown as 1.5×, never as a false 1×")
    }

    func testNoUltraWideDeviceHasNoSubOneZoom() {
        XCTAssertEqual(wideOnly.displayRange.lowerBound, 1)
        XCTAssertEqual(wideOnly.raw(fromDisplay: 0.5), 1, "0.5× clamps to the widest real lens")
        XCTAssertFalse(wideOnly.opticalAnchors(switchOverRaw: []).contains(0.5))
    }

    func testClampingAtBothEnds() {
        XCTAssertEqual(ultraWide.raw(fromDisplay: 0.1), 1)
        XCTAssertEqual(ultraWide.raw(fromDisplay: 99), 30)
        XCTAssertEqual(ultraWide.pinchRaw(base: 2, scale: 100), 30)
        XCTAssertEqual(ultraWide.pinchRaw(base: 2, scale: 0.01), 1)
    }

    func testMultiplierPrefersSystemValueAndFallsBack() {
        XCTAssertEqual(CameraZoomScale.resolvedMultiplier(system: 0.5, hasUltraWide: false), 0.5)
        XCTAssertEqual(CameraZoomScale.resolvedMultiplier(system: nil, hasUltraWide: true), 0.5)
        XCTAssertEqual(CameraZoomScale.resolvedMultiplier(system: 0, hasUltraWide: false), 1)
        XCTAssertEqual(CameraZoomScale.resolvedMultiplier(system: .nan, hasUltraWide: true), 0.5)
    }

    func testOpticalAnchorsFromSwitchOvers() {
        // iPhone Pro: switch-overs at raw 2 (wide) and 10 (5× tele).
        XCTAssertEqual(ultraWide.opticalAnchors(switchOverRaw: [2, 10]), [0.5, 1, 5])
        XCTAssertEqual(CameraZoomFormat.ladder(anchors: ultraWide.opticalAnchors(switchOverRaw: [2, 10]),
                                               maxUserZoom: ultraWide.displayRange.upperBound),
                       [0.5, 1, 2, 3, 4, 5])
    }
}

final class ZoomDragSessionTests: XCTestCase {
    private let range = 0.5...15.0
    // The strip's DragGesture fires its first update only after 10 pt of travel.
    private let firstMove = 10.0

    func testFirstDragFromOneXDoesNotJumpToMinimum() {
        let d = ZoomDragSession(startZoom: 1, startMove: firstMove, range: range)
        XCTAssertEqual(d.zoom(forMove: firstMove), 1, accuracy: 1e-9, "no jump on the first update")
        XCTAssertGreaterThan(d.zoom(forMove: firstMove + 5), 1)
        XCTAssertLessThan(d.zoom(forMove: firstMove - 5), 1)
    }

    func testDragFromHalfAndFromTwo() {
        XCTAssertEqual(ZoomDragSession(startZoom: 0.5, startMove: 0, range: range).zoom(forMove: 0), 0.5, accuracy: 1e-9)
        XCTAssertEqual(ZoomDragSession(startZoom: 2, startMove: -10, range: range).zoom(forMove: -10), 2, accuracy: 1e-9)
    }

    func testConsecutiveDragsContinueFromTheLastZoom() {
        let first = ZoomDragSession(startZoom: 1, startMove: firstMove, range: range)
        let ended = first.zoom(forMove: firstMove + 60)
        let second = ZoomDragSession(startZoom: ended, startMove: -firstMove, range: range)
        XCTAssertEqual(second.zoom(forMove: -firstMove), ended, accuracy: 1e-9)
    }

    func testDirectionReversalReturnsToStart() {
        let d = ZoomDragSession(startZoom: 2, startMove: 0, range: range)
        XCTAssertGreaterThan(d.zoom(forMove: 80), 2)
        XCTAssertEqual(d.zoom(forMove: 0), 2, accuracy: 1e-9)
        XCTAssertLessThan(d.zoom(forMove: -40), 2)
    }

    func testClampsAtMinAndMax() {
        let d = ZoomDragSession(startZoom: 1, startMove: 0, range: range)
        XCTAssertEqual(d.zoom(forMove: -10_000), 0.5, accuracy: 1e-9)
        XCTAssertEqual(d.zoom(forMove: 10_000), 15, accuracy: 1e-9)
    }

    func testFullTravelSpansTheRange() {
        let d = ZoomDragSession(startZoom: 0.5, startMove: 0, range: range)
        XCTAssertEqual(d.zoom(forMove: ZoomDragSession.pointsForFullRange), 15, accuracy: 1e-6)
    }

    func testFrontCameraRange() {
        let front = 1.0...10.0
        let d = ZoomDragSession(startZoom: 1, startMove: firstMove, range: front)
        XCTAssertEqual(d.zoom(forMove: firstMove), 1, accuracy: 1e-9)
        XCTAssertEqual(d.zoom(forMove: -500), 1, accuracy: 1e-9)
    }

    func testLocalSpaceLayoutShiftExplainsTheDeviceJump() {
        // Documents the device bug the GLOBAL drag coordinate space fixes: the strip grows 44 pt when the dial
        // opens; in LOCAL coordinates that reads as +44 pt downward travel, which from 1× lands on ~0.5×.
        let d = ZoomDragSession(startZoom: 1, startMove: firstMove, range: range)
        let phantom = ZoomDragSession.move(width: firstMove, height: 44)
        XCTAssertLessThan(d.zoom(forMove: phantom), 0.52)
        XCTAssertEqual(d.zoom(forMove: ZoomDragSession.move(width: firstMove, height: 0)), 1, accuracy: 1e-9)
    }

    func testMoveCombinesBothAxes() {
        XCTAssertEqual(ZoomDragSession.move(width: 30, height: -10), 40, "right and up both zoom in")
    }
}

final class ZoomLabelBelowOneTests: XCTestCase {
    func testNoTenTenthsLabel() {
        XCTAssertEqual(CameraZoomFormat.label(0.96), "1")
        XCTAssertEqual(CameraZoomFormat.label(0.99), "1")
        XCTAssertEqual(CameraZoomFormat.liveLabel(0.97), "1×")
        XCTAssertNotEqual(CameraZoomFormat.liveLabel(0.95), ".10×")
    }

    func testSubOneLabelsUnchanged() {
        XCTAssertEqual(CameraZoomFormat.label(0.5), ".5")
        XCTAssertEqual(CameraZoomFormat.label(0.6), ".6")
        XCTAssertEqual(CameraZoomFormat.label(0.94), ".9")
        XCTAssertEqual(CameraZoomFormat.liveLabel(0.7), ".7×")
    }
}
