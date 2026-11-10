import AVFoundation
import os

// CaptureStabilization — the ONE stabilization policy for every connection that records a movie file
// (ContinuousCameraController and the one-shot CameraCaptureController), plus the preview policy.
//
// Before this, no connection ever set `preferredVideoStabilizationMode`, and AVFoundation's default for apps
// linked after iOS 6 is `.off`, so every clip was recorded unstabilized.
//
// Recorded-video policy (explicit, ordered, first supported wins):
//   1. .cinematicExtended  — strong handheld/walking stabilization; Apple's recommended "stable video" mode.
//   2. .cinematic          — same family, slightly weaker, wider support.
//   3. .standard           — light stabilization, smallest crop, lowest latency.
//   4. .off                — nothing is supported on this device/format/camera.
//
// Deliberately NOT chosen:
//   • .cinematicExtendedEnhanced — an even narrower field of view than extended; would cost the wide
//     landscape framing (0.5×) travel Moments depend on. Revisit only if device tests show extended is
//     not enough.
//   • .lowLatency (iOS 26) — weaker stabilization; recording latency is not a constraint for Moments.
//   • .auto — opaque: we must know (and show) which mode was actually applied.
//
// Truthfulness: the REQUESTED mode is what we ask for; the ACTIVE mode is what the connection reports
// (`activeVideoStabilizationMode`, key-value observable, and `.off` whenever the requested mode is
// unavailable). The UI/diagnostics only ever report the active mode, never the request.
enum CaptureStabilization {
    /// Ordered preference for RECORDED video.
    static let recordingPreference: [AVCaptureVideoStabilizationMode] = [.cinematicExtended, .cinematic, .standard]

    /// The first mode in `preference` that `isSupported` accepts, or `.off`. Pure; testable without a camera.
    static func select(_ preference: [AVCaptureVideoStabilizationMode] = recordingPreference,
                       connectionSupportsStabilization: Bool,
                       isSupported: (AVCaptureVideoStabilizationMode) -> Bool) -> AVCaptureVideoStabilizationMode {
        guard connectionSupportsStabilization else { return .off }
        return preference.first(where: isSupported) ?? .off
    }

    /// Preview policy: `.previewOptimized` (low latency, low power) only when the active format supports it;
    /// otherwise leave the preview unstabilized. The preview never borrows the recording mode — a cinematic
    /// preview would lag the user's hand.
    static func selectPreview(connectionSupportsStabilization: Bool,
                              isSupported: (AVCaptureVideoStabilizationMode) -> Bool) -> AVCaptureVideoStabilizationMode {
        select([.previewOptimized], connectionSupportsStabilization: connectionSupportsStabilization,
               isSupported: isSupported)
    }

    /// Request the policy's mode on a movie-file connection for the device's CURRENT active format.
    /// Call after the input/output topology is committed and again after any input/format change.
    @discardableResult
    static func applyRecording(to connection: AVCaptureConnection?, device: AVCaptureDevice?) -> AVCaptureVideoStabilizationMode {
        guard let connection, let device else { return .off }
        let mode = select(connectionSupportsStabilization: connection.isVideoStabilizationSupported,
                          isSupported: { device.activeFormat.isVideoStabilizationModeSupported($0) })
        connection.preferredVideoStabilizationMode = mode
        log.notice("stabilization recording requested=\(name(mode), privacy: .public) format_supports=\(supportedNames(device), privacy: .public)")
        return mode
    }

    @discardableResult
    static func applyPreview(to connection: AVCaptureConnection?, device: AVCaptureDevice?) -> AVCaptureVideoStabilizationMode {
        guard let connection, let device else { return .off }
        let mode = selectPreview(connectionSupportsStabilization: connection.isVideoStabilizationSupported,
                                 isSupported: { device.activeFormat.isVideoStabilizationModeSupported($0) })
        connection.preferredVideoStabilizationMode = mode
        return mode
    }

    /// Short, stable names for logs and the DEBUG readout.
    static func name(_ mode: AVCaptureVideoStabilizationMode) -> String {
        switch mode {
        case .off: return "off"
        case .standard: return "standard"
        case .cinematic: return "cinematic"
        case .cinematicExtended: return "cinematicExtended"
        case .previewOptimized: return "previewOptimized"
        case .cinematicExtendedEnhanced: return "cinematicExtendedEnhanced"
        case .auto: return "auto"
        default: return "mode(\(mode.rawValue))"
        }
    }

    private static func supportedNames(_ device: AVCaptureDevice) -> String {
        let all: [AVCaptureVideoStabilizationMode] = [.standard, .cinematic, .cinematicExtended,
                                                      .cinematicExtendedEnhanced, .previewOptimized]
        return all.filter { device.activeFormat.isVideoStabilizationModeSupported($0) }.map(name).joined(separator: ",")
    }

    static let log = Logger(subsystem: "app.yotale", category: "camera")
}

/// What the recorded-video connection is actually doing (for diagnostics; never inferred from the request).
struct StabilizationStatus: Equatable {
    var requested: AVCaptureVideoStabilizationMode
    var active: AVCaptureVideoStabilizationMode

    var summary: String {
        requested == active
            ? "stab \(CaptureStabilization.name(active))"
            : "stab \(CaptureStabilization.name(active)) (asked \(CaptureStabilization.name(requested)))"
    }
}
