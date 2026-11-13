import SwiftUI
import SwiftData
import UIKit
import CoreLocation

/// Pure, device-independent formatting for zoom-preset labels (unit-testable). ".5" for sub-1×,
/// integer for whole values ("1", "2"), one decimal otherwise ("1.5"). Kept free of AVFoundation so
/// it can be tested without a camera device (the preset DERIVATION needs real hardware and is a
/// device-acceptance concern, not a unit test).
enum CameraZoomFormat {
    static func label(_ z: Double) -> String {
        // Below 1× the label is tenths with a leading dot (.5, .6). A value that ROUNDS to ten tenths
        // (0.95..<1) is 1, never ".10" (seen on device while dragging through 1×).
        if z < 1 {
            let tenths = Int((z * 10).rounded())
            if tenths >= 10 { return "1" }
            return String(format: ".%d", max(tenths, 1))
        }
        if z == z.rounded() { return "\(Int(z))" }
        return String(format: "%.1f", z)
    }

    /// The live magnification shown on the ACTIVE zoom chip: "2.7×" style (one decimal + ×), "1×"/"2×"
    /// when sitting on/near an integer, ".5×" sub-1×. Separate from `label` (plain preset text).
    static func liveLabel(_ z: Double) -> String {
        if z < 1 && (z * 10).rounded() < 10 { return label(z) + "×" }
        if abs(z - z.rounded()) < 0.05 { return "\(Int(z.rounded()))×" }
        return String(format: "%.1f×", z)
    }

    /// Map an exposure-slider fraction (0 = bottom/min EV, 1 = top/max EV) to an EV value in `range`,
    /// and back. Pure so the Increment-2 exposure slider's math is unit-testable without a camera.
    static func exposureEV(fromFraction p: Float, range: ClosedRange<Float>) -> Float {
        let clampedP = min(max(p, 0), 1)
        return range.lowerBound + clampedP * (range.upperBound - range.lowerBound)
    }
    static func exposureFraction(fromEV ev: Float, range: ClosedRange<Float>) -> Float {
        let span = range.upperBound - range.lowerBound
        guard span > 0 else { return 0 }
        return min(max((ev - range.lowerBound) / span, 0), 1)
    }

    /// Thumb-dial zoom mapping (log-scaled, like the native camera dial so the low end is finer). A dial
    /// fraction (0 = min zoom, 1 = max zoom) maps to a user-× value, and back. Pure/unit-testable.
    static func dialZoom(fromFraction p: Double, range: ClosedRange<Double>) -> Double {
        let lo = max(0.0001, range.lowerBound), hi = max(lo, range.upperBound)
        let cp = min(max(p, 0), 1)
        let v = lo * pow(hi / lo, cp)
        return min(max(v, lo), hi)
    }
    static func dialFraction(fromZoom z: Double, range: ClosedRange<Double>) -> Double {
        let lo = max(0.0001, range.lowerBound), hi = max(lo, range.upperBound)
        guard hi > lo else { return 0 }
        let cz = min(max(z, lo), hi)
        return log(cz / lo) / log(hi / lo)
    }

    /// Build a GRADUAL preset ladder from the device's real optical anchors (e.g. [0.5, 1, 5]) by
    /// filling integer digital steps between 1× and the top anchor, so the user sees a smooth ramp
    /// (0.5, 1, 2, 3, 5) rather than a jarring 1→5 jump. Sub-1× anchors (0.5) are preserved exactly
    /// and never interpolated (we never imply an optical lens that isn't there). De-duped, sorted,
    /// clamped to `maxUserZoom`. Always returns at least [1.0].
    static func ladder(anchors rawAnchors: [Double], maxUserZoom: Double) -> [Double] {
        var anchors = rawAnchors
        if !anchors.contains(where: { abs($0 - 1.0) < 0.01 }) { anchors.append(1.0) }
        let topAnchor = anchors.max() ?? 1.0
        // A wide-only device (top optical anchor == 1×) still gets gradual DIGITAL steps up to a sane
        // cap (so there's a usable tele ramp); a device with optical tele fills up to that lens.
        let digitalCeiling = 3.0
        let top = min(max(topAnchor, digitalCeiling), maxUserZoom)
        var set = Set<Double>()
        // Keep every real anchor that fits (including sub-1× like 0.5 — never interpolated).
        for a in anchors where a <= maxUserZoom + 0.001 { set.insert(a) }
        // Fill integer steps from 2 up to `top` (digital zoom between/above optical lenses).
        if top >= 2 {
            var i = 2.0
            while i <= top + 0.001 { set.insert(i); i += 1 }
        }
        let cleaned = set.sorted().filter { $0 <= maxUserZoom + 0.001 }
        return cleaned.isEmpty ? [1.0] : cleaned
    }
}

// ContinuousCaptureModel — the @MainActor brain behind ContinuousCaptureView.
//
// Owns the single CaptureContext-driven persistence path (identical rules to
// SceneScanFlowView.persistMoment, reused here for continuous capture) plus the
// integrity guarantees that keep five fast recordings honest:
//
//   • One Moment per finished clip. Each adopt→create→enqueue runs on the main
//     actor; a `savingTokens` set + per-URL dedup guarantees a given temp URL is
//     persisted at most once even if a delegate callback is delivered twice.
//   • Saves are SERIALIZED through a simple in-order queue so a second recording
//     finishing fast cannot interleave with the first save and corrupt ordering
//     or produce duplicate links. AU + Photos copy are fired async AFTER the
//     Moment row is committed and never block the next recording.
//   • The recent-Moment thumbnail updates ONLY after a successful persist — never
//     on a failed or in-flight clip (no false success).
//   • A failed clip surfaces an honest alert and the temp file is cleaned up.
@MainActor
final class ContinuousCaptureModel: ObservableObject, ContinuousCameraControllerDelegate {
    @Published var isRecording = false
    @Published var isSaving = false
    @Published var showSaved = false
    @Published var recentThumbnail: UIImage?
    @Published var showError = false
    @Published var errorMessage: String?

    // AI Ideas (optional, user-initiated). The red record button stays live in
    // every AI state — scanning and inference NEVER block recording.
    //
    // Phase 1: generated ideas live in SESSION state (ideas/ideasOutput/ideaIndex) and SURVIVE
    // record/stop cycles. The on-screen presentation is separate: `aiState` drives the overlay,
    // and `ideasCollapsed` hides the full card (e.g. while recording) WITHOUT discarding the ideas,
    // so a small chip can reopen them with NO new inference.
    enum AIState: Equatable {
        case off                      // no AI UI, no ideas held
        case scanning                 // collecting scene frames from the live session
        case thinking                 // frames collected; Director is generating an idea
        case ideas                    // one or more shot ideas available (and shown)
        case failed(String)           // AI failed/throttled — recording still works
    }
    @Published var aiState: AIState = .off
    @Published var ideaIndex = 0                       // which cached idea is shown (preserved)
    @Published var ideasCollapsed = false              // full card hidden but ideas retained (chip reopens)
    @Published var recordingElapsed: TimeInterval = 0  // live REC timer (Phase 2)
    @Published var scanProgress: Double = 0            // 0→1 across the scan window (determinate bar)

    // MARK: - Phase 1A: optional Unsplash reference image for the CURRENT shot idea.
    //
    // The image NEVER blocks the idea card (owner §8): the text card shows immediately; the photo is
    // fetched asynchronously and only appears if a confident, grounded match is found. Guarantees:
    //   * At most ONE image per idea. `imagesByIdeaKey` memoizes the resolved result (DTO or a cached
    //     "no image") per (generation, ideaIndex) so SwiftUI re-renders and zoom changes never re-search.
    //   * Stale responses are dropped: a loader tagged with an older `aiGeneration`/index can never set
    //     `currentIdeaImage`, so a previous idea's photo can't appear on a new idea.
    //   * A dismissed/collapsed card is never reopened by a late image (we only publish into state; the
    //     card's visibility is driven solely by `aiState`/`ideasCollapsed`).
    /// The resolved reference image for the idea currently shown (nil = text-only / still loading).
    @Published var currentIdeaImage: SceneImageDTO?
    /// Memoized per-idea results so we fetch at most once per idea and never re-search on re-render/zoom.
    /// Key = "<generation>#<ideaIndex>"; value nil means "resolved: no image" (distinct from not-fetched).
    private var imagesByIdeaKey: [String: SceneImageDTO?] = [:]
    private let sceneImageService: SceneImageFetching = SceneImageService()

    // Phase 1B — reference VIDEO for the current idea (Pixabay), shown only in video mode. Same guarantees
    // as the image path (one per idea, memoized, stale-dropped). In image mode this stays nil and no video
    // request is made. The card prefers a video when present, else the image, else text.
    @Published var currentIdeaVideo: SceneVideoDTO?
    private var videosByIdeaKey: [String: SceneVideoDTO?] = [:]
    private let sceneVideoService: SceneVideoFetching = SceneVideoService()

    // Camera controls (Package B Increment 1) — thin passthroughs to the shared controller. The
    // controller owns all device config (serialized + lock-guarded); the model only mirrors UI state.
    @Published var torchOn = false                     // reflects the torch button toggle
    @Published var currentUserZoom: Double = 1.0       // live magnification (pinch/preset); drives the strip
    /// Device-supported zoom presets, PUBLISHED by the controller via `.presetsReady` as soon as they
    /// are computed — so the strip renders on OPEN, not lazily on the first tap. [1.0] until ready.
    @Published var publishedZoomPresets: [Double] = [1.0]
    /// What the UI reads. Prefers the published copy; falls back to a live controller read.
    var zoomPresets: [Double] {
        publishedZoomPresets.count > 1 ? publishedZoomPresets : (controller?.zoomPresets ?? publishedZoomPresets)
    }
    /// Whether this device has a torch (UI hides the control when false).
    var hasTorch: Bool { controller?.hasTorch ?? false }

    /// Tap-to-focus at a view point (from the tap gesture). Also shows a brief focus reticle (UI state).
    func focusAndExpose(atViewPoint point: CGPoint) {
        noteInteraction()
        controller?.focusAndExpose(atViewPoint: point)
    }
    /// Snap to a zoom preset (preset button).
    func setZoomPreset(_ userZoom: Double) {
        noteInteraction()
        zoomDrag = nil
        setDisplayZoom(userZoom)
    }
    /// Continuous absolute zoom (displayed ×). The controller clamps it and is the authority; the readout
    /// shows the CLAMPED value immediately, and the device's report confirms it via .zoomChanged.
    func setDialZoom(_ userZoom: Double) {
        setDisplayZoom(userZoom)
    }
    private func setDisplayZoom(_ userZoom: Double) {
        guard let controller else { return }
        controller.setUserZoom(userZoom)
        currentUserZoom = controller.currentDisplayZoom
    }
    /// The device's continuous displayed zoom range (for the dial extents). [1,1] until ready.
    var userZoomRange: ClosedRange<Double> { controller?.userZoomRange ?? 1...1 }

    /// Thumb-dial drag. The FIRST update of a drag snapshots the controller's authoritative zoom and the
    /// finger offset at that moment; every update after is relative to that snapshot, so a drag continues
    /// from the current zoom (no jump to the dial minimum, no carry-over from a previous drag). The
    /// snapshot lives on this reference type, not in SwiftUI @State, so it is readable right after it is set.
    func dialDragChanged(move: Double) {
        guard let controller else { return }
        if zoomDrag == nil {
            noteInteraction()
            zoomDrag = ZoomDragSession(startZoom: controller.currentDisplayZoom, startMove: move,
                                       range: controller.userZoomRange)
        }
        guard let drag = zoomDrag else { return }
        setDisplayZoom(drag.zoom(forMove: move))
    }
    func dialDragEnded() {
        zoomDrag = nil
        noteInteraction()
    }
    /// Current drag snapshot (tests / diagnostics).
    private(set) var zoomDrag: ZoomDragSession?

    /// Continuous pinch zoom. `base` is captured at gesture start from the controller's authoritative zoom.
    func pinchZoom(scale: CGFloat, base: CGFloat) {
        noteInteraction()
        zoomDrag = nil   // a pinch takes over; the next dial drag re-snapshots from the pinched value
        controller?.applyPinchZoom(scale: scale, base: base)
        if let controller { currentUserZoom = controller.currentDisplayZoom }
    }

    // Screen awake (P0 camera): the capture screen keeps the display on while recording, and for a short
    // idle window while framing. Released on close; suspended automatically while backgrounded.
    private lazy var screenAwake = CaptureScreenAwake()
    func screenAppeared() { screenAwake.appear() }
    func screenDisappeared() {
        zoomDrag = nil
        screenAwake.disappear()
    }
    /// Any user action on the capture screen.
    func noteInteraction() { screenAwake.interaction() }

    /// The controller's current raw zoom factor (gesture start reads this).
    var currentRawZoom: CGFloat { controller?.currentZoomFactor ?? 1.0 }
    /// Toggle the torch.
    func toggleTorch() {
        torchOn.toggle()
        controller?.setTorch(torchOn)
    }

    // Increment 2 — front/rear, exposure bias, AE/AF lock.
    @Published var isFrontCamera = false
    @Published var isAEAFLocked = false
    @Published var exposureBias: Float = 0        // live EV bias (slider position)
    var hasFrontCamera: Bool { controller?.hasFrontCamera ?? false }
    var exposureBiasRange: ClosedRange<Float> { controller?.exposureBiasRange ?? 0...0 }

    /// Flip front/rear (UI gates this out of recording). Resets zoom to 1× on the new camera.
    func switchCamera() {
        guard !isRecording else { return }
        noteInteraction()
        zoomDrag = nil
        controller?.switchCamera()
    }
    /// Manual exposure bias from the slider.
    func setExposureBias(_ ev: Float) {
        exposureBias = ev
        controller?.setExposureBias(ev)
    }
    /// Long-press AE/AF lock toggle.
    func toggleAEAFLock() {
        controller?.setAEAFLock(!isAEAFLocked)
    }

    private(set) var ideas: [DirectorDecisionDTO] = []
    private(set) var ideasOutput: DirectorOutputDTO?   // for concept/shot lookups
    private var recordingTimer: Timer?
    private var recordingStartedAt: Date?
    // Monotonic token: every scan/record transition bumps it so a stale Director response
    // from a cancelled or superseded scan can NEVER replace newer ideas or reopen an overlay.
    private var aiGeneration = 0

    weak var controller: ContinuousCameraController?

    private var context: ModelContext?
    private var captureContext: CaptureContext?
    private let captureSessionId = UUID()
    private let sceneService = SceneUnderstandingService()
    private let directorService = StoryDirectorService()

    // Dedup + serialization state.
    private var inFlightURLs = Set<String>()      // temp URLs currently being persisted
    private var persistedURLs = Set<String>()     // temp URLs already persisted (double-callback guard)

    // Guide/Idea seed: the specific opportunity the user tapped Shoot/Reshoot on (Story Guide
    // possibility or Story Idea Show-me). When present, the camera shows THIS idea IMMEDIATELY on
    // open — NO network call, NO scan — because the possibility already carries its own label +
    // purpose text (loaded on the Story screen). The idea card renders straight from this text, so
    // Reshoot lands on the continuous camera already showing that exact guide idea with zero latency.
    // nil for plain "Shoot a moment" (no seed; the pill shows "Get an AI shot idea").
    private var seededIdea: SeededIdea?
    private var seedConsumed = false

    /// An instant, network-free idea rendered directly from the tapped guide possibility / Story Idea.
    struct SeededIdea: Equatable {
        let title: String        // the possibility/idea label — the card headline
        let body: String         // its semantic purpose — the card instruction line
        let seconds: Int?        // optional target duration (seeds carry none today)
    }

    func configure(context: ModelContext, captureContext: CaptureContext,
                   seedOpportunity: SelectedOpportunityDTO? = nil) {
        self.context = context
        self.captureContext = captureContext
        if let opp = seedOpportunity, !seedConsumed {
            // Build the idea card from text we ALREADY have — no Director call, no spinner.
            let title = opp.label.trimmingCharacters(in: .whitespacesAndNewlines)
            let body = (opp.purpose ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !title.isEmpty { self.seededIdea = SeededIdea(title: title, body: body, seconds: nil) }
        }
    }

    /// Show the seeded guide idea as the DEFAULT in-camera idea, instantly, once, on first appear.
    /// Pure local state change — no network, so the card appears the moment Reshoot opens the camera.
    func seedGuideIdeaIfNeeded() {
        guard !seedConsumed, seededIdea != nil else { return }
        seedConsumed = true
        aiState = .ideas
        loadReferenceMediaForCurrentIdea()   // optional photo/video for the seeded guide idea (non-blocking)
    }

    func toggleRecording() {
        noteInteraction()
        controller?.toggleRecording()
    }

    /// Whether we hold a shot idea that can be reopened without a new scan (drives the chip):
    /// either live cached Director ideas OR an instant seeded guide idea.
    var hasCachedIdeas: Bool { !ideas.isEmpty || seededIdea != nil }

    /// AI Ideas — user-initiated. If ideas are already cached and merely collapsed, REOPEN them
    /// (no inference). Otherwise start a fresh scene scan on the LIVE session (does not stop any
    /// in-progress recording), then run the Director.
    func getAIShotIdeaTapped() {
        noteInteraction()
        if hasCachedIdeas {
            reopenIdeas()
            return
        }
        guard aiState == .off || isFailed else { return }
        startScan()
    }

    /// Reopen the cached ideas overlay WITHOUT running new inference (Phase 1: the upper-right chip).
    func reopenIdeas() {
        guard hasCachedIdeas else { return }
        ideasCollapsed = false
        aiState = .ideas
    }

    /// "Rescan" — EXPLICIT fresh scene evidence + new Director call. The only path that replaces
    /// cached ideas, so old ideas are never silently presented as a newly-scanned scene (Phase 1).
    func scanAgain() { startScan() }

    /// "Next idea" — advance through the already-available cached ideas (no new call).
    func nextIdea() {
        guard !ideas.isEmpty else { return }
        ideaIndex = (ideaIndex + 1) % ideas.count
        loadReferenceMediaForCurrentIdea()   // load/reuse this idea's media; clears the previous one
    }

    /// Dismiss the overlay. If ideas are cached, this COLLAPSES (keeps them for the chip); if a
    /// scan/think is in flight it cancels and clears. Never discards cached ideas.
    func dismissIdeas() {
        if hasCachedIdeas {
            ideasCollapsed = true
            aiState = .off
            return
        }
        aiGeneration &+= 1               // invalidate any in-flight scan/Director response
        controller?.cancelScan()
        aiState = .off
    }

    /// Cancel an in-flight AI request (scanning/thinking) explicitly — clears nothing cached.
    func cancelAIRequest() {
        aiGeneration &+= 1
        controller?.cancelScan()
        aiState = hasCachedIdeas ? .off : .off
        if hasCachedIdeas { ideasCollapsed = true }
    }

    private var isFailed: Bool { if case .failed = aiState { return true } else { return false } }

    // MARK: - Current idea accessors (for the overlay)
    //
    // A SEEDED idea (from a Guide Reshoot / Story Idea) renders instantly from local text and takes
    // precedence until the user Rescans — then live Director `ideas` replace it (seed cleared).

    var currentIdeaTitle: String {
        if let s = seededIdea, ideas.isEmpty { return s.title }
        return ideasOutput?.concept.title ?? L10n.t("Shot idea")
    }
    var currentIdeaBody: String {
        if let s = seededIdea, ideas.isEmpty { return s.body }
        guard ideaIndex < ideas.count else { return "" }
        return ideas[ideaIndex].shot?.instruction ?? ideasOutput?.concept.summary ?? ""
    }
    var currentIdeaSeconds: Int? {
        if seededIdea != nil, ideas.isEmpty { return seededIdea?.seconds }
        guard ideaIndex < ideas.count else { return nil }
        if let d = ideas[ideaIndex].shot?.targetDurationSeconds, d > 0 { return Int(d.rounded()) }
        return nil
    }
    var ideaCount: Int { ideas.count }

    // MARK: - Phase 1A reference-image loading (non-blocking, one per idea)

    /// A stable key for the idea currently shown, scoped to the live generation so a Rescan (new
    /// generation) never reuses a prior idea's memoized image.
    private var currentIdeaKey: String { "\(aiGeneration)#\(ideaIndex)" }

    /// The generic stock-photo query for the CURRENT idea (nil => text-only, no search).
    /// Source: the Director's own per-shot `visual_reference_query` (story_director/v2), written in the
    /// SAME call that produced the idea (no extra inference) and sanitized server-side; the
    /// /v1/scene-image proxy re-sanitizes it again. There is deliberately NO client-side keyword
    /// fallback: device testing showed keyword heuristics pick background nouns ("city lights" ->
    /// street) and an irrelevant photo is worse than none (owner §6). A seeded guide idea carries no
    /// Director shot, so it stays text-only.
    private func currentReferenceQuery() -> String? {
        if seededIdea != nil, ideas.isEmpty { return nil }
        guard ideaIndex < ideas.count, let shotId = ideas[ideaIndex].shot?.id else { return nil }
        return ideasOutput?.referenceQuery(for: shotId)
    }

    /// Load (or reuse) the reference image for the CURRENTLY shown idea. Idempotent per idea; safe to
    /// call on every "idea shown" transition. Does NOT block the card. A stale generation/index result
    /// is dropped and never published. Called after the idea text is already on screen.
    func loadReferenceImageForCurrentIdea() {
        let key = currentIdeaKey
        // Already resolved for this idea (incl. a cached "no image")? Publish memoized, no network.
        if let memo = imagesByIdeaKey[key] {
            currentIdeaImage = memo
            return
        }
        // Not fetched yet: clear any previous idea's image immediately so it can't linger on this idea.
        currentIdeaImage = nil
        guard let query = currentReferenceQuery() else {
            imagesByIdeaKey[key] = nil      // no grounded signal -> resolved "no image" (never a placeholder)
            return
        }
        let gen = aiGeneration
        let idx = ideaIndex
        Task { [weak self] in
            guard let self else { return }
            let dto = await self.sceneImageService.fetch(query: query)
            await MainActor.run {
                // Drop a stale response: the shown idea moved on (Rescan / Next idea / dismiss).
                guard gen == self.aiGeneration, idx == self.ideaIndex else { return }
                self.imagesByIdeaKey["\(gen)#\(idx)"] = dto
                self.currentIdeaImage = dto
            }
        }
    }

    /// Fire the Unsplash download-tracking endpoint when the user actually USES a reference (opens the
    /// expanded "See framing" view), per Unsplash's rule — never on mere display. Best-effort.
    func trackReferenceUsed() {
        guard let loc = currentIdeaImage?.downloadLocation, !loc.isEmpty else { return }
        Task { [weak self] in await self?.sceneImageService.track(downloadLocation: loc) }
    }

    // MARK: - Phase 1B reference-video loading (video mode only; mirrors the image path)

    /// The shot's generic framing/camera-motion/instruction text, used by the backend ONLY to classify the
    /// requested camera technique (no PII, no new model call). nil for a seeded guide idea (no Director shot).
    private func currentTechniqueText() -> String? {
        guard ideaIndex < ideas.count, let shot = ideas[ideaIndex].shot else { return nil }
        return [shot.framing, shot.cameraMotion, shot.instruction].compactMap { $0 }
            .joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Load (or reuse) the reference VIDEO for the current idea. No-op in image mode. Same memoize +
    /// stale-drop guarantees as the image loader; the card shows video text immediately and the poster/clip
    /// appear only if a confident match is found, else it falls back to the image path.
    func loadReferenceVideoForCurrentIdea() {
        guard StoryGuideFeatures.referenceVideoEnabled else { currentIdeaVideo = nil; return }
        let key = currentIdeaKey
        if let memo = videosByIdeaKey[key] { currentIdeaVideo = memo; return }
        currentIdeaVideo = nil
        guard let query = currentReferenceQuery() else { videosByIdeaKey[key] = nil; return }
        let technique = currentTechniqueText()
        let gen = aiGeneration
        let idx = ideaIndex
        Task { [weak self] in
            guard let self else { return }
            let dto = await self.sceneVideoService.fetch(query: query, technique: technique)
            await MainActor.run {
                guard gen == self.aiGeneration, idx == self.ideaIndex else { return }   // drop stale
                self.videosByIdeaKey["\(gen)#\(idx)"] = dto
                self.currentIdeaVideo = dto
            }
        }
    }

    /// Load the reference MEDIA for the current idea per the active mode: in video mode, fetch the video
    /// (and still fetch the image as the fallback); in image mode, image only. One call per "idea shown".
    func loadReferenceMediaForCurrentIdea() {
        loadReferenceImageForCurrentIdea()      // always: the image is the video's fallback
        if StoryGuideFeatures.referenceVideoEnabled { loadReferenceVideoForCurrentIdea() }
    }

    /// Load the current idea video's poster BYTES via the backend (Pixabay forbids image hotlinking).
    /// Returns nil -> the player shows a neutral placeholder. Best-effort, never throws.
    func loadIdeaVideoPoster() async -> Data? {
        guard let video = currentIdeaVideo, !video.posterURL.isEmpty else { return nil }
        let url = sceneVideoService.posterRequestURL()
        guard let body = sceneVideoService.posterBody(for: video.posterURL) else { return nil }
        var req = URLRequest(url: url)
        StoryBackend.authorize(&req)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 6
        req.httpBody = body
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200, !data.isEmpty else { return nil }
        return data
    }

    /// A compact one-line reminder of the active idea, for the minimized recording state.
    var currentIdeaReminder: String? {
        if let s = seededIdea, ideas.isEmpty { return s.title.isEmpty ? nil : s.title }
        guard hasCachedIdeas else { return nil }
        let t = currentIdeaTitle
        return t.isEmpty ? nil : t
    }

    private func startScan() {
        aiGeneration &+= 1
        let gen = aiGeneration
        ideas = []; ideasOutput = nil; ideaIndex = 0
        seededIdea = nil            // Rescan replaces the seeded guide idea with live, scene-specific ideas
        currentIdeaImage = nil      // drop any shown photo; new generation key means no stale reuse
        currentIdeaVideo = nil      // Phase 1B: drop any shown video too
        scanProgress = 0
        aiState = .scanning
        guard let controller else { aiState = .failed(L10n.t("Camera unavailable.")); return }
        controller.startScan(progress: { [weak self] p in
            Task { @MainActor in
                guard let self, gen == self.aiGeneration, self.aiState == .scanning else { return }
                self.scanProgress = p
            }
        }, completion: { [weak self] frames in
            Task { @MainActor in
                guard let self, gen == self.aiGeneration else { return }  // superseded/cancelled
                // Frames are in; the Director is now thinking.
                self.aiState = .thinking
                await self.runDirector(frames: frames, generation: gen)
            }
        })
    }

    /// "Done" — end the scan early and use the frames collected so far (proactive end, Phase 3).
    func finishScanNow() {
        guard aiState == .scanning else { return }
        controller?.finishScanNow()
    }

    /// The scan window length (seconds), for labeling the progress UI.
    var scanWindowSeconds: Double { controller?.scanWindowSeconds ?? 4.0 }

    private func runDirector(frames: [UIImage], generation gen: Int) async {
        guard gen == aiGeneration else { return }                 // stale — drop silently
        guard let captureContext else { aiState = .off; return }
        guard !frames.isEmpty else {
            if gen == aiGeneration { aiState = .failed(L10n.t("Couldn't read the scene. Try again.")) }
            return
        }
        do {
            let selected = SceneFrameProcessor.select(from: frames, max: 5)
            let su = try await sceneService.analyze(
                frames: selected, captureSessionId: captureSessionId,
                mode: "shoot_moment", storyId: captureContext.associatedStory?.id)
            let out = try await directorService.initialize(
                creativeIntent: captureContext.directorIntent(),
                sceneUnderstanding: su,
                targetDurationSeconds: captureContext.targetDurationSeconds,
                selectedOpportunity: nil)
            // The user may have started recording or dismissed while we were thinking — if so,
            // this response is stale and must NOT reopen an overlay (Phase 2).
            guard gen == aiGeneration else { return }
            let candidates = out.candidates.isEmpty ? [out.decision] : out.candidates
            let shots = candidates.filter { $0.action == .captureShot || $0.action == .retryShot }
            if shots.isEmpty {
                aiState = .failed(L10n.t("No strong shot here. Try moving or scanning again."))
            } else {
                ideas = shots
                ideasOutput = out
                ideaIndex = 0
                ideasCollapsed = false
                aiState = .ideas
                loadReferenceMediaForCurrentIdea()   // async photo/video for idea 0; never blocks the card
            }
        } catch {
            // AI failure / quota exhaustion must NOT disable recording — just report, if still current.
            guard gen == aiGeneration else { return }
            aiState = .failed(L10n.t("AI ideas are unavailable right now."))
        }
    }

    // MARK: - ContinuousCameraControllerDelegate

    nonisolated func captureEvent(_ event: ContinuousCaptureEvent) {
        Task { @MainActor in self.handle(event) }
    }

    private func handle(_ event: ContinuousCaptureEvent) {
        switch event {
        case .ready:
            break
        case .recordingStarted:
            isRecording = true
            screenAwake.recordingChanged(true)
            // Phase 1+2: starting a recording cancels any IN-FLIGHT scan/inference (bump the
            // generation so a late Director response can't replace newer ideas or reopen the
            // overlay), and COLLAPSES the full idea card — but PRESERVES cached ideas + the
            // selected index so they can be reopened after recording with no new scan.
            aiGeneration &+= 1
            controller?.cancelScan()
            if aiState == .scanning || aiState == .thinking {
                // No cached result from this in-flight request — just hide the request UI.
                aiState = hasCachedIdeas ? .off : .off
                if hasCachedIdeas { ideasCollapsed = true }
            } else if aiState == .ideas {
                ideasCollapsed = true          // keep ideas, hide the card
                aiState = .off
            } else {
                aiState = .off
            }
            startRecordingTimer()
        case .recordingFinished(let url, let duration, let capturedAt, let fix):
            isRecording = false
            screenAwake.recordingChanged(false)
            stopRecordingTimer()
            persist(tempURL: url, duration: duration, capturedAt: capturedAt, location: fix)
        case .captureFailed(let message):
            isRecording = false
            screenAwake.recordingChanged(false)
            stopRecordingTimer()
            errorMessage = message
            showError = true
        case .interrupted:
            isRecording = false
            screenAwake.recordingChanged(false)
            stopRecordingTimer()
        case .presetsReady(let presets):
            // The strip now renders from the model's OWN published copy (not a lazy controller read),
            // so it appears on OPEN instead of only after the first tap forces a re-render.
            publishedZoomPresets = presets
        case .zoomChanged(let userZoom):
            // Live magnification from pinch, dial or a chip. The controller's authoritative target wins over a
            // report that arrives late from an earlier request (fast drags), so the readout never steps back.
            currentUserZoom = controller?.currentDisplayZoom ?? userZoom
        case .aeafLockChanged(let locked):
            isAEAFLocked = locked
        case .stabilizationChanged:
            break   // the active mode is logged by the controller (category "camera"); no on-screen readout
        case .cameraPositionChanged(let front):
            isFrontCamera = front
            // A swap opens the new camera at displayed 1× (or its nearest reachable zoom); the controller
            // reports the actual value via .zoomChanged. Any in-progress dial drag ends with the old camera.
            zoomDrag = nil
            if front { torchOn = false }
            exposureBias = 0
        }
    }

    // MARK: - Recording timer (live REC elapsed, Phase 2)

    private func startRecordingTimer() {
        recordingStartedAt = Date()
        recordingElapsed = 0
        recordingTimer?.invalidate()
        recordingTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let start = self.recordingStartedAt else { return }
                self.recordingElapsed = Date().timeIntervalSince(start)
            }
        }
    }

    private func stopRecordingTimer() {
        recordingTimer?.invalidate()
        recordingTimer = nil
        recordingStartedAt = nil
        recordingElapsed = 0
    }

    /// mm:ss elapsed string for the REC indicator.
    var recordingTimeString: String {
        let total = Int(recordingElapsed)
        return String(format: "%02d:%02d", total / 60, total % 60)
    }

    // MARK: - Persistence (ONE path, serialized, deduped)

    private func persist(tempURL: URL, duration: Double,
                         capturedAt: Date? = nil,
                         location: CaptureLocationService.LocationFix? = nil) {
        let key = tempURL.path
        // Double-callback / rapid-tap dedup: never persist the same temp URL twice.
        guard !persistedURLs.contains(key), !inFlightURLs.contains(key) else {
            try? FileManager.default.removeItem(at: tempURL)
            return
        }
        guard let context, let captureContext else {
            try? FileManager.default.removeItem(at: tempURL)
            return
        }
        inFlightURLs.insert(key)
        isSaving = true

        let useCases = StoryUseCases(repository: StoryRepository(context: context))
        do {
            // Finalize media on disk FIRST — if adoption fails, nothing is claimed.
            let relativePath = try MediaStore.shared.adoptCapturedFile(tempURL: tempURL)

            // ONE persistence path; context picks the association (Increment 1 rules).
            let moment: MomentModel
            if let story = captureContext.associatedStory {
                moment = try useCases.shootMoment(for: story, relativePath: relativePath,
                                                  durationSeconds: duration)
            } else {
                moment = try useCases.shootStandaloneMoment(relativePath: relativePath,
                                                            durationSeconds: duration)
            }

            persistedURLs.insert(key)
            inFlightURLs.remove(key)

            // Camera Metadata P0: stamp the TRUE capture time + the trustworthy location fix (or leave nil
            // = unknown) onto the asset. Additive fields; nothing else about the Moment changes. Saved with
            // the context on the next save (the use case already inserted the asset).
            if let asset = moment.asset {
                asset.capturedAt = capturedAt
                if let fix = location {
                    asset.latitude = fix.latitude
                    asset.longitude = fix.longitude
                    asset.locationAccuracyMeters = fix.horizontalAccuracyMeters
                }
                try? context.save()
            }

            // AU enqueue — AFTER the Moment is committed; never blocks the next
            // recording. Contextless here (no requested shot/beat in continuous mode).
            let auQueue = AssetUnderstandingQueue(context: context)
            auQueue.enqueue(momentId: moment.id, relativeMediaPath: relativePath,
                            sourceCaptureId: captureSessionId, captureContext: nil)
            Task.detached { await auQueue.drain() }

            // R4-A.1: if the active account has Auto Backup ON, auto-enroll this new Moment for cloud backup
            // (fire-and-forget; no-op when OFF/signed out). NEVER blocks capture.
            MediaUploadQueue.sharedAutoEnroll(moment)

            // Add-only Photos copy — fire-and-forget, degrades silently. Carries the capture date + a
            // trustworthy location so the user's own Photos copy is correctly dated and placed.
            let adoptedURL = MediaStore.shared.absoluteURL(for: relativePath)
            let clLocation = location.map {
                CLLocation(coordinate: CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude),
                           altitude: 0, horizontalAccuracy: $0.horizontalAccuracyMeters,
                           verticalAccuracy: -1, timestamp: $0.timestamp)
            }
            PhotosSaver.saveVideoCopy(at: adoptedURL, creationDate: capturedAt, location: clLocation) { _ in }

            // Subtle save feedback + recent thumbnail AFTER success only.
            isSaving = !inFlightURLs.isEmpty
            flashSaved()
            Task { await updateRecentThumbnail(for: moment) }

        } catch {
            inFlightURLs.remove(key)
            isSaving = !inFlightURLs.isEmpty
            try? FileManager.default.removeItem(at: tempURL)
            errorMessage = L10n.t("That clip couldn't be saved. Please try again.")
            showError = true
        }
    }

    private func flashSaved() {
        withAnimation { showSaved = true }
        Task {
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            await MainActor.run { withAnimation { self.showSaved = false } }
        }
    }

    private func updateRecentThumbnail(for moment: MomentModel) async {
        if let img = await MomentThumbnailCache.shared.thumbnail(for: moment) {
            await MainActor.run { self.recentThumbnail = img }
        }
    }
}
