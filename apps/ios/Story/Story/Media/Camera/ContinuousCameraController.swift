import UIKit
import AVFoundation
import CoreImage

// ContinuousCameraController — the SHARED AVFoundation capture engine for
// Capture Anywhere (Figma MVP V0.2.2). Unlike the one-shot CameraCaptureView,
// this stays alive across many recordings: the owner (ContinuousCaptureView)
// drives start/stop and persists each finished clip as one independent Moment,
// then the camera remains ready for the next recording. No post-capture page.
//
// Integrity guards live HERE so every caller (Home standalone + in-Story) gets
// the same protection (one engine, one set of rules):
//   • Rapid taps / double callbacks — a strict state machine (.idle → .starting
//     → .recording → .stopping) rejects out-of-phase taps; the AV delegate
//     callback is dispatched exactly once per recording via a token.
//   • Backgrounding / interruptions — AVCaptureSession interruption + app
//     lifecycle notifications stop an in-flight recording cleanly (the partial
//     clip is still delivered so nothing silently vanishes).
//   • Storage/engine errors — a failed start or a delegate error surfaces as
//     .captureFailed; no false "saved" state is ever produced.
//   • Orphaned temp files — each recording writes to a uniquely-named temp
//     file; the controller tracks the active URL so a cancelled/failed clip
//     can be removed. Temp files live in the system temp dir and are reclaimed
//     by the OS; the controller deletes on explicit failure.
//
// The controller NEVER persists — it only produces (tempURL, duration) and
// lifecycle events. Persistence + Moment creation is the owner's job, so the
// single CaptureContext-driven persistence path is reused unchanged.

enum ContinuousCaptureEvent {
    case ready                       // session running, safe to record
    case recordingStarted
    case recordingFinished(URL, Double, Date, CaptureLocationService.LocationFix?)   // url, duration, capturedAt, location
    case captureFailed(String)       // human-readable, non-semantic
    case interrupted                 // session interrupted (phone call, etc.)
    case presetsReady([Double])      // device-derived zoom presets available (strip can render)
    case zoomChanged(Double)         // live USER-× zoom factor (pinch/preset) for the strip
    case aeafLockChanged(Bool)       // AE/AF lock engaged/released (Increment 2)
    case cameraPositionChanged(Bool) // true = front camera now active (Increment 2)
    case stabilizationChanged(StabilizationStatus)   // requested vs ACTIVE mode on the recorded-video connection
}

protocol ContinuousCameraControllerDelegate: AnyObject {
    func captureEvent(_ event: ContinuousCaptureEvent)
}

final class ContinuousCameraController: UIViewController, AVCaptureFileOutputRecordingDelegate,
                                        AVCaptureVideoDataOutputSampleBufferDelegate {
    weak var delegate: ContinuousCameraControllerDelegate?

    // Strict phase machine — the single source of truth for "can I tap now?".
    private enum Phase { case idle, starting, recording, stopping }
    private var phase: Phase = .idle

    private let session = AVCaptureSession()
    private let movieOutput = AVCaptureMovieFileOutput()
    private var previewLayer: AVCaptureVideoPreviewLayer?

    // Package B Increment 1 — camera controls (ADDITIVE; the recording engine is unchanged).
    // The back-camera device + its input are retained so focus/exposure/zoom/torch can be
    // configured on it. All device configuration is serialized on `sessionQueue` and wrapped in
    // lockForConfiguration, so it can never interleave with the recording state machine on main.
    private let sessionQueue = DispatchQueue(label: "com.story.continuous.session")
    private var videoDevice: AVCaptureDevice?
    private var videoDeviceInput: AVCaptureDeviceInput?

    // Increment 2 — front/rear switching. The CURRENT camera position; a swap rebuilds only the video
    // input inside begin/commitConfiguration (audio + outputs stay), gated out of .recording by the UI.
    private(set) var cameraPosition: AVCaptureDevice.Position = .back
    /// Whether a front camera exists (UI hides the flip button otherwise).
    var hasFrontCamera: Bool {
        AVCaptureDevice.DiscoverySession(
            deviceTypes: [.builtInWideAngleCamera, .builtInTrueDepthCamera],
            mediaType: .video, position: .front).devices.isEmpty == false
    }
    // Increment 2 — AE/AF lock. When locked, a scene change does NOT re-meter/refocus until unlocked.
    private(set) var isAELocked = false

    /// Device-supported zoom presets (e.g. 0.5×, 1×, 2×) derived from the ACTUAL virtual-device
    /// switch-over factors — NEVER a hardcoded lens list, so an SE with no ultra-wide/tele shows
    /// only [1×, 2×(digital)]. `1.0` is always present (the base wide). Published for the UI.
    private(set) var zoomPresets: [Double] = [1.0]
    /// The single conversion between hardware and displayed zoom for the ACTIVE camera (see CameraZoomScale).
    private(set) var zoomScale = CameraZoomScale(multiplier: 1, minRaw: 1, maxRaw: 1)
    /// AUTHORITATIVE zoom (raw `videoZoomFactor`), main-thread only. Updated synchronously whenever a zoom is
    /// REQUESTED (chip, dial, pinch, open, camera switch), before the device lock on `sessionQueue` applies it,
    /// so a gesture that starts right after a request reads the value the camera is moving to, not a stale one.
    private(set) var targetRawZoom: CGFloat = 1
    /// Stabilization actually in effect on the recorded-video connection (KVO on activeVideoStabilizationMode).
    private(set) var stabilizationStatus = StabilizationStatus(requested: .off, active: .off)
    private var stabilizationObservation: NSKeyValueObservation?
    /// Whether this device has a torch (UI hides the control when false).
    var hasTorch: Bool { videoDevice?.hasTorch ?? false }

    // Orientation (Increment 1 verify/fix): keep the movie-file + preview connections rotated to
    // match the physical device so portrait/landscape clips are recorded upright. iOS 17+ uses
    // RotationCoordinator (the Apple-recommended path); older iOS falls back to interface
    // orientation. Held as Any to avoid a hard availability type on the stored property.
    private var rotationCoordinator: Any?
    private var rotationObservations: [NSKeyValueObservation] = []

    // Scene-scan frame grabbing — a SECOND output on the SAME session so an AI
    // scan can collect frames WITHOUT a separate camera session and WITHOUT
    // interrupting an in-flight recording (Figma: "you can keep recording").
    private let videoDataOutput = AVCaptureVideoDataOutput()
    private let scanQueue = DispatchQueue(label: "com.story.continuous.scan")
    private let ciContext = CIContext()
    private var scanning = false
    private var scanStart: CMTime?
    private var lastKeptPTS: CMTime?
    private var scanFrames: [UIImage] = []
    private var scanCompletion: (([UIImage]) -> Void)?
    private var scanProgress: ((Double) -> Void)?     // 0→1 over the scan window (for the UI progress bar)
    private let scanDuration: Double = 4.0
    private let scanFrameInterval: Double = 0.35

    // The temp URL of the active recording + a token to ensure the AV finish
    // callback is honored exactly once (guards against double delegate calls).
    private var activeTempURL: URL?
    private var activeToken: UUID?
    private var recordingStart: Date?

    /// Whether a recording is currently in progress (owner reads this to render
    /// the record vs stop button and to gate overlay actions).
    var isRecording: Bool { phase == .recording }

    // MARK: - Lifecycle

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureSession()
        observeLifecycle()
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        startSession()
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        // If we are leaving mid-recording, stop cleanly so the partial clip is
        // delivered rather than lost (the owner decides whether to keep it).
        if phase == .recording { movieOutput.stopRecording() }
        if session.isRunning { session.stopRunning() }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    private func startSession() {
        Task.detached { [session] in
            if !session.isRunning { session.startRunning() }
            await MainActor.run { [weak self] in
                guard let self else { return }
                if self.phase == .idle { self.delegate?.captureEvent(.ready) }
            }
        }
    }

    // MARK: - Session configuration

    private func configureSession() {
        session.beginConfiguration()
        session.sessionPreset = .high

        // Prefer a VIRTUAL multi-camera device (triple/dual/dual-wide) when present: it exposes the
        // real optical lenses as zoom-factor switch-over points, so pinch + presets cross 0.5×/2×
        // optically where the hardware has them, and fall back to pure wide on an SE. This is NOT a
        // hardcoded lens list — unavailable lenses simply never appear.
        let device = Self.bestCamera(position: .back)
        if let camera = device,
           let videoInput = try? AVCaptureDeviceInput(device: camera),
           session.canAddInput(videoInput) {
            session.addInput(videoInput)
            self.videoDevice = camera
            self.videoDeviceInput = videoInput
        }
        if let mic = AVCaptureDevice.default(for: .audio),
           let audioInput = try? AVCaptureDeviceInput(device: mic),
           session.canAddInput(audioInput) {
            session.addInput(audioInput)
        }
        if session.canAddOutput(movieOutput) {
            session.addOutput(movieOutput)
        }
        // Second output on the SAME session for AI scan frame grabbing. Frames are
        // collected in memory only during an explicit scan; the delegate ignores
        // buffers unless `scanning` is true, so there is no steady-state cost.
        videoDataOutput.alwaysDiscardsLateVideoFrames = true
        videoDataOutput.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ]
        videoDataOutput.setSampleBufferDelegate(self, queue: scanQueue)
        if session.canAddOutput(videoDataOutput) {
            session.addOutput(videoDataOutput)
        }
        session.commitConfiguration()

        // Compute the zoom conversion + device-supported presets from the ACTUAL hardware (no fake lenses).
        if let camera = device {
            self.zoomScale = Self.zoomScale(for: camera)
            self.zoomPresets = Self.zoomPresets(for: camera, scale: zoomScale)
        }
        // Publish presets to the owner immediately so the zoom strip renders on OPEN (not lazily on
        // first tap). Dispatched to main because the delegate drives @Published UI state.
        let presets = self.zoomPresets
        DispatchQueue.main.async { [weak self] in self?.delegate?.captureEvent(.presetsReady(presets)) }

        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        preview.frame = view.bounds
        view.layer.addSublayer(preview)
        self.previewLayer = preview

        // Orientation verify/fix: observe + apply rotation to preview + movie connections.
        configureRotationCoordinator()

        // Stabilization (recorded file + preview) for the active format, then open at displayed 1×.
        applyStabilization()
        applyInitialZoom()
    }

    // MARK: - Stabilization

    /// Request the policy's mode on the MOVIE connection and `.previewOptimized` on the preview connection,
    /// for the CURRENT device/format. Re-run after every input/format change (camera switch). The recorded
    /// file and the preview are separate connections: neither setting affects the other.
    private func applyStabilization() {
        let movieConnection = movieOutput.connection(with: .video)
        let requested = CaptureStabilization.applyRecording(to: movieConnection, device: videoDevice)
        CaptureStabilization.applyPreview(to: previewLayer?.connection, device: videoDevice)
        stabilizationObservation = movieConnection?.observe(\.activeVideoStabilizationMode, options: [.initial, .new]) { [weak self] c, _ in
            let status = StabilizationStatus(requested: requested, active: c.activeVideoStabilizationMode)
            DispatchQueue.main.async {
                guard let self else { return }
                self.stabilizationStatus = status
                CaptureStabilization.log.notice("stabilization recording active=\(CaptureStabilization.name(status.active), privacy: .public) requested=\(CaptureStabilization.name(status.requested), privacy: .public)")
                self.delegate?.captureEvent(.stabilizationChanged(status))
            }
        }
    }

    // MARK: - Zoom (one conversion, one authoritative value)

    /// Open at displayed 1× when reachable (raw 2.0 on an ultra-wide virtual device, raw 1.0 elsewhere). Without
    /// this the virtual device opens at raw 1.0 — the ULTRA-WIDE — while the UI assumed 1×.
    private func applyInitialZoom() {
        let raw = CGFloat(zoomScale.initialRaw)
        targetRawZoom = raw
        let scale = zoomScale
        configureDevice { [weak self] device in
            let applied = Self.liveClamped(raw, device)
            device.videoZoomFactor = applied
            self?.reportZoom(raw: applied, scale: scale)
        }
        CaptureStabilization.log.notice("zoom open raw=\(Double(raw)) display=\(scale.display(fromRaw: Double(raw))) multiplier=\(scale.multiplier) range=\(scale.minRaw)...\(scale.maxRaw)")
    }

    /// Build the movie-file location metadata (ISO-6709) from a trustworthy fix, or [] when unknown.
    /// Coordinates only — no place name is ever synthesized. Used as `AVCaptureMovieFileOutput.metadata`.
    static func locationMetadata(for fix: CaptureLocationService.LocationFix?) -> [AVMetadataItem] {
        guard let fix else { return [] }
        // ISO-6709: "+DD.dddd+DDD.dddd/" (lat, lon, trailing slash). Positive = N/E.
        let iso = String(format: "%+09.5f%+010.5f/", fix.latitude, fix.longitude)
        let item = AVMutableMetadataItem()
        item.identifier = .commonIdentifierLocation
        item.keySpace = .common
        item.key = AVMetadataKey.commonKeyLocation as NSString
        item.value = iso as NSString
        return [item]
    }

    // MARK: - Device selection & capability detection (per-device, never assumed)

    /// The best video device at a POSITION: a virtual multi-camera (triple → dual → dual-wide) when
    /// present so optical lenses are reachable via zoom, else the plain wide angle. Front typically has
    /// only wide (+ TrueDepth). Never fabricates lenses.
    private static func bestCamera(position: AVCaptureDevice.Position) -> AVCaptureDevice? {
        let preferred: [AVCaptureDevice.DeviceType] = [
            .builtInTripleCamera, .builtInDualWideCamera, .builtInDualCamera,
            .builtInWideAngleCamera, .builtInTrueDepthCamera
        ]
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: preferred, mediaType: .video, position: position)
        for type in preferred {
            if let d = discovery.devices.first(where: { $0.deviceType == type }) { return d }
        }
        return AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position)
    }

    /// The device's zoom conversion: the system's `displayVideoZoomFactorMultiplier` (iOS 18+) when valid,
    /// else the ultra-wide heuristic; and the device's available raw range.
    static func zoomScale(for device: AVCaptureDevice) -> CameraZoomScale {
        let hasUltraWide = device.constituentDevices.contains { $0.deviceType == .builtInUltraWideCamera }
        var system: Double?
        if #available(iOS 18.0, *) { system = Double(device.displayVideoZoomFactorMultiplier) }
        return CameraZoomScale(
            multiplier: CameraZoomScale.resolvedMultiplier(system: system, hasUltraWide: hasUltraWide),
            minRaw: Double(device.minAvailableVideoZoomFactor),
            maxRaw: Double(device.maxAvailableVideoZoomFactor))
    }

    /// Zoom presets in DISPLAY terms, derived from the device's real `virtualDeviceSwitchOverVideoZoomFactors`
    /// through `CameraZoomScale` (ultra-wide gives 0.5×, each tele switch-over e.g. 5×). The optical anchors are
    /// filled with integer digital steps by `CameraZoomFormat.ladder`, clamped to what the device can reach.
    private static func zoomPresets(for device: AVCaptureDevice, scale: CameraZoomScale) -> [Double] {
        let switchOvers = device.virtualDeviceSwitchOverVideoZoomFactors.map { $0.doubleValue }
        let anchors = scale.opticalAnchors(switchOverRaw: switchOvers)
        return CameraZoomFormat.ladder(anchors: anchors, maxUserZoom: scale.displayRange.upperBound)
    }

    /// Final guard at the device boundary: the AVAILABLE range can change while running (e.g. thermal limits),
    /// and setting `videoZoomFactor` outside it raises. Called inside lockForConfiguration on `sessionQueue`.
    private static func liveClamped(_ raw: CGFloat, _ device: AVCaptureDevice) -> CGFloat {
        min(max(raw, device.minAvailableVideoZoomFactor), device.maxAvailableVideoZoomFactor)
    }

    /// Report a zoom (DISPLAY terms) to the owner on the main actor (drives chips, readout and dial).
    private func reportZoom(raw: CGFloat, scale: CameraZoomScale) {
        let display = scale.display(fromRaw: Double(raw))
        DispatchQueue.main.async { [weak self] in self?.delegate?.captureEvent(.zoomChanged(display)) }
    }

    // MARK: - Interruption / backgrounding guards

    private func observeLifecycle() {
        let nc = NotificationCenter.default
        nc.addObserver(self, selector: #selector(sessionInterrupted),
                       name: .AVCaptureSessionWasInterrupted, object: session)
        nc.addObserver(self, selector: #selector(appResignActive),
                       name: UIApplication.willResignActiveNotification, object: nil)
    }

    @objc private func sessionInterrupted() {
        if phase == .recording {
            // Deliver the partial clip then report the interruption so the owner
            // can show an honest state (never a false success).
            movieOutput.stopRecording()
        }
        delegate?.captureEvent(.interrupted)
    }

    @objc private func appResignActive() {
        // Backgrounding mid-recording: finalize what we have rather than drop it.
        if phase == .recording { movieOutput.stopRecording() }
    }

    // MARK: - Record / stop (driven by the owner's red button)

    /// Toggle entry point used by the owner's single record/stop button.
    func toggleRecording() {
        switch phase {
        case .idle:      beginRecording()
        case .recording: endRecording()
        case .starting, .stopping: break    // in-flight — reject the tap (rapid-tap guard)
        }
    }

    private func beginRecording() {
        guard phase == .idle, session.isRunning else { return }
        phase = .starting
        let token = UUID()
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("cap-\(token.uuidString)")
            .appendingPathExtension("mov")
        activeTempURL = tempURL
        activeToken = token
        recordingStart = Date()
        // Camera Metadata P0: embed a trustworthy capture-time GPS fix into the .mov itself (ISO-6709
        // common metadata) so the original file carries location where available. nil fix → no location
        // metadata (honest "unknown"), never fabricated. This does not touch the recording engine/path.
        movieOutput.metadata = Self.locationMetadata(for: CaptureLocationService.shared.fix(at: Date()))
        movieOutput.startRecording(to: tempURL, recordingDelegate: self)
        // AVCaptureMovieFileOutput confirms the actual start via
        // didStartRecordingTo; flip to .recording there so the button can't be
        // tapped to "stop" a recording that has not physically begun.
    }

    private func endRecording() {
        guard phase == .recording else { return }
        phase = .stopping
        movieOutput.stopRecording()
    }

    // MARK: - AVCaptureFileOutputRecordingDelegate

    func fileOutput(_ output: AVCaptureFileOutput,
                    didStartRecordingTo fileURL: URL,
                    from connections: [AVCaptureConnection]) {
        // Physical start confirmed.
        DispatchQueue.main.async { [weak self] in
            guard let self, self.phase == .starting else { return }
            self.phase = .recording
            self.delegate?.captureEvent(.recordingStarted)
        }
    }

    func fileOutput(_ output: AVCaptureFileOutput,
                    didFinishRecordingTo outputFileURL: URL,
                    from connections: [AVCaptureConnection],
                    error: Error?) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            // Exactly-once: ignore a callback that does not correspond to the
            // active recording (double-callback guard).
            guard self.activeToken != nil, self.phase == .stopping || self.phase == .recording
            else { return }
            self.phase = .idle
            self.activeToken = nil
            let started = self.recordingStart ?? Date()
            self.recordingStart = nil

            if let error = error as NSError? {
                // AVErrorRecordingSuccessfullyFinished means the stop was clean
                // despite a non-nil error (e.g. interruption) — treat the clip as
                // valid. maximumDurationReached is likewise a clean finish.
                let successfullyFinished =
                    (error.userInfo[AVErrorRecordingSuccessfullyFinishedKey] as? Bool) == true
                let recoverable = error.code == AVError.Code.maximumDurationReached.rawValue
                if !successfullyFinished && !recoverable {
                    self.cleanupTempFile()
                    self.delegate?.captureEvent(.captureFailed(self.friendly(error)))
                    return
                }
            }

            // Validate the file actually exists before claiming a clip.
            guard FileManager.default.fileExists(atPath: outputFileURL.path) else {
                self.cleanupTempFile()
                self.delegate?.captureEvent(.captureFailed("The recording could not be saved."))
                return
            }
            let asset = AVURLAsset(url: outputFileURL)
            let dur = CMTimeGetSeconds(asset.duration)
            let duration = (dur.isFinite && dur > 0) ? dur : Date().timeIntervalSince(started)
            self.activeTempURL = nil   // ownership handed to the owner for adoption
            // Location tagging (optional, non-blocking): read the trustworthy fix for the capture instant,
            // or nil ("unknown"). `started` is the true capture time. Never blocks, never fabricates.
            let fix = CaptureLocationService.shared.fix(at: started)
            self.delegate?.captureEvent(.recordingFinished(outputFileURL, duration, started, fix))
        }
    }

    // MARK: - Scene scan (AI Ideas) — concurrent with recording

    /// Collect ~scanDuration seconds of throttled frames from the live session and
    /// deliver them to `completion`. Does NOT touch recording — the user can keep
    /// recording during a scan. Calling again while scanning restarts the window.
    func startScan(completion: @escaping ([UIImage]) -> Void) {
        scanQueue.async { [weak self] in
            guard let self else { return }
            self.scanFrames.removeAll()
            self.scanStart = nil
            self.lastKeptPTS = nil
            self.scanCompletion = completion
            self.scanning = true
        }
    }

    /// Collect ~scanDuration seconds of throttled frames from the live session and
    /// deliver them to `completion`. Does NOT touch recording — the user can keep
    /// recording during a scan. Calling again while scanning restarts the window.
    /// `progress` is fired 0→1 across the scan window so the UI can show a determinate bar.
    func startScan(progress: ((Double) -> Void)? = nil, completion: @escaping ([UIImage]) -> Void) {
        scanQueue.async { [weak self] in
            guard let self else { return }
            self.scanFrames.removeAll()
            self.scanStart = nil
            self.lastKeptPTS = nil
            self.scanCompletion = completion
            self.scanProgress = progress
            self.scanning = true
        }
    }

    /// The fixed scan window length (seconds), so the owner can label/scale the progress UI.
    var scanWindowSeconds: Double { scanDuration }

    /// Proactively END the current scan NOW and deliver whatever frames were collected
    /// (user tapped "Done" before the window elapsed). Safe if ≥1 frame; otherwise reports empty.
    func finishScanNow() {
        scanQueue.async { [weak self] in self?.finishScan() }
    }

    /// Abort an in-flight scan without delivering frames (user tapped Cancel scan).
    func cancelScan() {
        scanQueue.async { [weak self] in
            guard let self else { return }
            self.scanning = false
            self.scanFrames.removeAll()
            self.scanStart = nil
            self.lastKeptPTS = nil
            self.scanCompletion = nil
            self.scanProgress = nil
        }
    }

    private func finishScan() {
        // Called on scanQueue.
        guard scanning else { return }
        scanning = false
        let frames = scanFrames
        let completion = scanCompletion
        scanFrames.removeAll()
        scanStart = nil
        lastKeptPTS = nil
        scanCompletion = nil
        scanProgress = nil
        DispatchQueue.main.async { completion?(frames) }
    }

    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard scanning else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        if scanStart == nil { scanStart = pts }
        if let last = lastKeptPTS {
            let delta = CMTimeGetSeconds(CMTimeSubtract(pts, last))
            if delta < scanFrameInterval { return }
        }
        lastKeptPTS = pts
        if let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) {
            let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
            if let cg = ciContext.createCGImage(ciImage, from: ciImage.extent) {
                scanFrames.append(UIImage(cgImage: cg))
            }
        }
        if let start = scanStart {
            let elapsed = CMTimeGetSeconds(CMTimeSubtract(pts, start))
            let p = max(0, min(1, elapsed / scanDuration))
            if let cb = scanProgress { DispatchQueue.main.async { cb(p) } }
            if elapsed >= scanDuration { finishScan() }
        }
    }

    // MARK: - Camera controls (Package B Increment 1) — all ADDITIVE, serialized, lock-guarded.
    //
    // Every device mutation runs on `sessionQueue` inside lockForConfiguration/unlockForConfiguration,
    // so it is atomic and never races the recording state machine (which lives on main). None of these
    // touch the session topology (no begin/commitConfiguration, no input/output changes), so an
    // in-flight recording and a live AI scan are unaffected — zoom/focus/exposure/torch all adjust the
    // SAME running device both outputs already read from.

    private func configureDevice(_ body: @escaping (AVCaptureDevice) -> Void) {
        guard let device = videoDevice else { return }
        sessionQueue.async {
            do {
                try device.lockForConfiguration()
                body(device)
                device.unlockForConfiguration()
            } catch {
                // A transient lock failure must never crash or corrupt recording — ignore and keep going.
            }
        }
    }

    /// Set zoom by DISPLAYED value (chip tap or dial). Clamped to the device range. Main thread.
    func setUserZoom(_ displayZoom: Double) {
        setRawZoom(CGFloat(zoomScale.raw(fromDisplay: displayZoom)))
    }

    /// Continuous pinch zoom. `scale` is the gesture's cumulative scale applied to the raw zoom captured at
    /// gesture start (`base`, read from `currentZoomFactor`). Works during recording (device-level, no
    /// topology change). Clamped to the device's real min/max. Main thread.
    func applyPinchZoom(scale: CGFloat, base: CGFloat) {
        setRawZoom(CGFloat(zoomScale.pinchRaw(base: Double(base), scale: Double(scale))))
    }

    /// The one writer of zoom: update the authoritative target now, apply it on the session queue.
    private func setRawZoom(_ raw: CGFloat) {
        targetRawZoom = raw
        let scale = zoomScale
        configureDevice { [weak self] device in
            let applied = Self.liveClamped(raw, device)
            device.videoZoomFactor = applied
            self?.reportZoom(raw: applied, scale: scale)
        }
    }

    /// The authoritative raw zoom (gesture start reads this as its base).
    var currentZoomFactor: CGFloat { targetRawZoom }

    /// The authoritative zoom in DISPLAY terms (the dial snapshots this when a drag begins).
    var currentDisplayZoom: Double { zoomScale.display(fromRaw: Double(targetRawZoom)) }

    /// The displayed zoom range the active camera can reach (dial extents).
    var userZoomRange: ClosedRange<Double> { zoomScale.displayRange }

    /// Tap-to-focus + expose at a preview point (0..1 device coords from the preview layer). A tap also
    /// CLEARS any AE/AF lock and resumes continuous tracking — the native behavior (tap to re-meter).
    func focusAndExpose(atDevicePoint point: CGPoint) {
        configureDevice { [weak self] device in
            if device.isFocusPointOfInterestSupported {
                device.focusPointOfInterest = point
                if device.isFocusModeSupported(.autoFocus) { device.focusMode = .autoFocus }
            }
            if device.isExposurePointOfInterestSupported {
                device.exposurePointOfInterest = point
                if device.isExposureModeSupported(.autoExpose) { device.exposureMode = .autoExpose }
            }
            // Resume continuous tracking after a tap so the scene stays correctly focused/exposed as it
            // moves — this also lifts an AE/AF lock (tap overrides lock, like the native camera).
            if device.isFocusModeSupported(.continuousAutoFocus) { device.focusMode = .continuousAutoFocus }
            if device.isExposureModeSupported(.continuousAutoExposure) { device.exposureMode = .continuousAutoExposure }
            if let self, self.isAELocked {
                self.isAELocked = false
                DispatchQueue.main.async { self.delegate?.captureEvent(.aeafLockChanged(false)) }
            }
        }
    }

    /// Convert a view-space tap into the device point-of-interest via the preview layer (handles
    /// resizeAspectFill cropping + mirroring correctly).
    func focusAndExpose(atViewPoint viewPoint: CGPoint) {
        guard let preview = previewLayer else { return }
        let devicePoint = preview.captureDevicePointConverted(fromLayerPoint: viewPoint)
        focusAndExpose(atDevicePoint: devicePoint)
    }

    /// Toggle the torch where present. No-op (and UI-hidden) on devices without one. Torch is a
    /// device property, independent of recording — safe to toggle mid-record.
    func setTorch(_ on: Bool) {
        configureDevice { device in
            guard device.hasTorch, device.isTorchModeSupported(on ? .on : .off) else { return }
            if on {
                try? device.setTorchModeOn(level: AVCaptureDevice.maxAvailableTorchLevel)
            } else {
                device.torchMode = .off
            }
        }
    }

    // MARK: - Increment 2 controls — front/rear swap, exposure bias, AE/AF lock

    /// Flip between back and front cameras. Rebuilds ONLY the video input inside begin/commitConfiguration
    /// (audio input + movie/data outputs are untouched), then re-applies presets, orientation and zoom.
    /// REFUSED while recording — the UI gates the button out of .recording, and this is a second guard
    /// (a mid-clip input swap would corrupt the movie file). Runs on the session queue.
    func switchCamera() {
        guard phase != .recording, phase != .stopping else { return }
        sessionQueue.async { [weak self] in
            guard let self else { return }
            let target: AVCaptureDevice.Position = (self.cameraPosition == .back) ? .front : .back
            guard let newDevice = Self.bestCamera(position: target),
                  let newInput = try? AVCaptureDeviceInput(device: newDevice) else { return }
            self.session.beginConfiguration()
            if let old = self.videoDeviceInput { self.session.removeInput(old) }
            if self.session.canAddInput(newInput) {
                self.session.addInput(newInput)
                self.videoDevice = newDevice
                self.videoDeviceInput = newInput
                self.cameraPosition = target
            } else if let old = self.videoDeviceInput {
                // Revert if the new input cannot be added (keep a working session).
                self.session.addInput(old)
            }
            self.session.commitConfiguration()

            // Re-derive the zoom conversion + presets for the NEW device and open it at displayed 1× (or the
            // nearest reachable value), then re-apply orientation and stabilization: the new input has a new
            // active format, so the old mode choice no longer applies.
            let scale = Self.zoomScale(for: newDevice)
            let presets = Self.zoomPresets(for: newDevice, scale: scale)
            let raw = CGFloat(scale.initialRaw)
            try? newDevice.lockForConfiguration()
            newDevice.videoZoomFactor = Self.liveClamped(raw, newDevice)
            newDevice.unlockForConfiguration()
            self.isAELocked = false
            let pos = self.cameraPosition
            DispatchQueue.main.async {
                self.zoomScale = scale
                self.zoomPresets = presets
                self.targetRawZoom = raw
                self.delegate?.captureEvent(.presetsReady(presets))
                self.delegate?.captureEvent(.zoomChanged(scale.display(fromRaw: Double(raw))))
                self.delegate?.captureEvent(.aeafLockChanged(false))
                self.delegate?.captureEvent(.cameraPositionChanged(pos == .front))
                self.applyRotationForCurrentAPI()
                self.applyStabilization()
            }
        }
    }

    /// Manual exposure bias in EV (e.g. −2…+2). Clamped to the device's real min/max target bias.
    /// Independent of recording. Does NOT engage the AE/AF lock — it biases the running auto-exposure.
    func setExposureBias(_ ev: Float) {
        configureDevice { device in
            let clamped = max(device.minExposureTargetBias, min(ev, device.maxExposureTargetBias))
            device.setExposureTargetBias(clamped, completionHandler: nil)
        }
    }

    /// The device's supported exposure-bias range (UI uses it to size the slider). Defaults to 0…0.
    var exposureBiasRange: ClosedRange<Float> {
        guard let d = videoDevice else { return 0...0 }
        return d.minExposureTargetBias...d.maxExposureTargetBias
    }

    /// Lock / unlock Auto-Exposure AND Auto-Focus at their current values (long-press AE/AF lock). While
    /// locked a scene change does NOT re-meter/refocus; a tap-to-focus clears the lock. Safe mid-record.
    func setAEAFLock(_ locked: Bool) {
        configureDevice { [weak self] device in
            if locked {
                if device.isExposureModeSupported(.locked) { device.exposureMode = .locked }
                if device.isFocusModeSupported(.locked) { device.focusMode = .locked }
            } else {
                if device.isExposureModeSupported(.continuousAutoExposure) { device.exposureMode = .continuousAutoExposure }
                if device.isFocusModeSupported(.continuousAutoFocus) { device.focusMode = .continuousAutoFocus }
            }
            self?.isAELocked = locked
            DispatchQueue.main.async { self?.delegate?.captureEvent(.aeafLockChanged(locked)) }
        }
    }

    // MARK: - Orientation (Increment 1 verify/fix)
    //
    // The ORIGINAL engine never set any connection orientation, so a clip's upright-ness relied on
    // the sensor default — a confirmed defect for landscape capture. Fix: keep both the PREVIEW and
    // the MOVIE-FILE output connections rotated to match the physical device. iOS 17+ uses
    // AVCaptureDevice.RotationCoordinator (Apple-recommended, accounts for the device + the preview
    // layer); older iOS falls back to the interface orientation. The angle is NOT changed while a
    // recording is in flight — a mid-clip rotation would corrupt the file — so a recording keeps the
    // angle it started at and the next recording picks up the current one.

    /// Install rotation observation. Called once after `configureSession()`.
    private func configureRotationCoordinator() {
        if #available(iOS 17.0, *) {
            guard let device = videoDevice else { return }
            let coordinator = AVCaptureDevice.RotationCoordinator(device: device, previewLayer: previewLayer)
            self.rotationCoordinator = coordinator
            applyRotation()
            // Observe both angles; re-apply on change (but never mid-recording).
            rotationObservations = [
                coordinator.observe(\.videoRotationAngleForHorizonLevelPreview, options: [.new]) { [weak self] _, _ in
                    DispatchQueue.main.async { self?.applyRotation() }
                },
                coordinator.observe(\.videoRotationAngleForHorizonLevelCapture, options: [.new]) { [weak self] _, _ in
                    DispatchQueue.main.async { self?.applyRotation() }
                }
            ]
        } else {
            // Pre-17 fallback: apply once from the interface orientation and on device rotation.
            applyLegacyRotation()
            NotificationCenter.default.addObserver(
                self, selector: #selector(applyLegacyRotation),
                name: UIDevice.orientationDidChangeNotification, object: nil)
        }
    }

    /// iOS 17+ — push the coordinator's horizon-level angles onto the preview + movie connections.
    @available(iOS 17.0, *)
    private func applyRotation() {
        guard let coordinator = rotationCoordinator as? AVCaptureDevice.RotationCoordinator else { return }
        if let pc = previewLayer?.connection, pc.isVideoRotationAngleSupported(coordinator.videoRotationAngleForHorizonLevelPreview) {
            pc.videoRotationAngle = coordinator.videoRotationAngleForHorizonLevelPreview
        }
        // Do not re-rotate the movie connection while recording — the clip keeps its start angle.
        guard phase != .recording, phase != .stopping else { return }
        let captureAngle = coordinator.videoRotationAngleForHorizonLevelCapture
        if let mc = movieOutput.connection(with: .video), mc.isVideoRotationAngleSupported(captureAngle) {
            mc.videoRotationAngle = captureAngle
        }
    }

    /// Pre-iOS-17 — map the interface orientation to a rotation angle on both connections.
    @objc private func applyLegacyRotation() {
        let angle: CGFloat
        switch UIDevice.current.orientation {
        case .landscapeLeft: angle = 0      // home button right
        case .landscapeRight: angle = 180
        case .portraitUpsideDown: angle = 270
        default: angle = 90                 // portrait
        }
        if let pc = previewLayer?.connection, pc.isVideoRotationAngleSupported(angle) {
            pc.videoRotationAngle = angle
        }
        guard phase != .recording, phase != .stopping else { return }
        if let mc = movieOutput.connection(with: .video), mc.isVideoRotationAngleSupported(angle) {
            mc.videoRotationAngle = angle
        }
    }

    /// Version-agnostic rotation apply (used after a camera swap / on demand).
    private func applyRotationForCurrentAPI() {
        if #available(iOS 17.0, *) {
            // Rebuild the coordinator for the CURRENT device — a front/rear swap changes the device, and
            // the old coordinator would report the wrong device's angles (orientation-hardening).
            if let device = videoDevice {
                rotationObservations.removeAll()
                let coordinator = AVCaptureDevice.RotationCoordinator(device: device, previewLayer: previewLayer)
                self.rotationCoordinator = coordinator
                rotationObservations = [
                    coordinator.observe(\.videoRotationAngleForHorizonLevelPreview, options: [.new]) { [weak self] _, _ in
                        DispatchQueue.main.async { self?.applyRotation() }
                    },
                    coordinator.observe(\.videoRotationAngleForHorizonLevelCapture, options: [.new]) { [weak self] _, _ in
                        DispatchQueue.main.async { self?.applyRotation() }
                    }
                ]
            }
            applyRotation()
        } else {
            applyLegacyRotation()
        }
    }

    // MARK: - Helpers

    /// Remove the active temp file (used when a recording failed and will not be adopted).
    func cleanupTempFile() {
        if let url = activeTempURL { try? FileManager.default.removeItem(at: url) }
        activeTempURL = nil
    }

    private func friendly(_ error: NSError) -> String {
        if error.code == AVError.Code.diskFull.rawValue { return "Your device is out of storage." }
        return "The recording stopped unexpectedly."
    }

    deinit { NotificationCenter.default.removeObserver(self) }
}
