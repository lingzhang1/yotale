import Foundation

// CameraZoomScale — the ONE conversion between the hardware zoom (`AVCaptureDevice.videoZoomFactor`, "raw")
// and the zoom the user sees ("display", the familiar .5× / 1× / 2× labels). Pure; no AVFoundation.
//
// On a virtual multi-lens back camera, raw 1.0 is the WIDEST lens (the ultra-wide), which the system Camera
// app labels 0.5×. Apple publishes the ratio as `displayVideoZoomFactorMultiplier` (iOS 18+): display = raw ×
// multiplier (0.5 on ultra-wide virtual devices, 1.0 on a plain wide or front camera). Every chip, the dial,
// the readout, pinch and the initial zoom go through this type, so they cannot disagree.
struct CameraZoomScale: Equatable {
    /// display = raw × multiplier.
    let multiplier: Double
    let minRaw: Double
    let maxRaw: Double

    init(multiplier: Double, minRaw: Double, maxRaw: Double) {
        self.multiplier = multiplier > 0 && multiplier.isFinite ? multiplier : 1
        self.minRaw = max(0.0001, minRaw)
        self.maxRaw = max(self.minRaw, maxRaw)
    }

    /// The multiplier to use: the system's own value when it is valid, else the long-standing heuristic
    /// (ultra-wide present => 0.5, otherwise 1.0).
    static func resolvedMultiplier(system: Double?, hasUltraWide: Bool) -> Double {
        if let s = system, s.isFinite, s > 0 { return s }
        return hasUltraWide ? 0.5 : 1.0
    }

    func display(fromRaw raw: Double) -> Double { raw * multiplier }

    /// Raw factor for a displayed zoom, clamped to the device's available range.
    func raw(fromDisplay display: Double) -> Double { clampRaw(display / multiplier) }

    func clampRaw(_ raw: Double) -> Double { min(max(raw, minRaw), maxRaw) }

    /// The displayed range the hardware can actually reach.
    var displayRange: ClosedRange<Double> { display(fromRaw: minRaw)...display(fromRaw: maxRaw) }

    /// Raw factor to open the camera at: displayed 1× when the device can reach it, otherwise the nearest
    /// reachable value (which the UI then shows as-is, never as a false "1×").
    var initialRaw: Double { raw(fromDisplay: 1.0) }

    /// Pinch: the gesture's cumulative scale applied to the raw zoom captured at gesture start, clamped.
    func pinchRaw(base: Double, scale: Double) -> Double { clampRaw(base * scale) }

    /// Optical anchors in DISPLAY terms: the widest lens when it is below 1×, 1×, and each lens switch-over
    /// above 1× (rounded to the familiar integer label). Never invents a lens.
    func opticalAnchors(switchOverRaw: [Double]) -> [Double] {
        var anchors: [Double] = []
        let widest = display(fromRaw: minRaw)
        if widest < 0.99 { anchors.append((widest * 10).rounded() / 10) }
        anchors.append(1.0)
        for f in switchOverRaw {
            let d = display(fromRaw: f)
            if d > 1.01 { anchors.append(d.rounded()) }
        }
        return anchors
    }
}

// ZoomDragSession — the thumb-dial drag on the zoom strip. The START zoom is captured ONCE when the drag begins
// (from the controller's authoritative zoom, never from SwiftUI view state) together with the finger offset at
// that moment, and every later update is relative to that snapshot. So a drag can never begin from the dial's
// minimum (the old bug read a just-written @State back in the same callback and got its stale 0 => 0.5×).
struct ZoomDragSession: Equatable {
    /// Finger travel (points) that spans the whole log-scaled range.
    static let pointsForFullRange = 220.0

    let startFraction: Double
    let startMove: Double
    let range: ClosedRange<Double>

    /// `move` = horizontal minus vertical translation (right/up zooms in), in points.
    init(startZoom: Double, startMove: Double, range: ClosedRange<Double>) {
        self.range = range
        self.startMove = startMove
        self.startFraction = CameraZoomFormat.dialFraction(fromZoom: startZoom, range: range)
    }

    /// Displayed zoom for the current finger position. Exactly the start zoom (clamped) when the finger has
    /// not moved since the snapshot.
    func zoom(forMove move: Double) -> Double {
        let frac = startFraction + (move - startMove) / Self.pointsForFullRange
        return CameraZoomFormat.dialZoom(fromFraction: frac, range: range)
    }

    /// Combined drag translation used by the strip (either axis drives the dial).
    static func move(width: Double, height: Double) -> Double { width - height }
}
