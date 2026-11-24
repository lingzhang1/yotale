import UIKit

// ScreenAwake — the ONE owner of `UIApplication.isIdleTimerDisabled`.
//
// Before this, three places wrote the global Boolean directly (Create view, Create coordinator) and the camera
// wrote nothing, so the phone auto-locked mid-recording and `appResignActive` cut the clip short. Separate
// writers also clear each other: Create ending would re-enable auto-lock while another screen still needs it.
//
// Model: named, idempotent claims. `hold(key)` adds a claim (holding the same key twice is still one claim, so
// repeated `onAppear` cannot leak); `release(key)` removes it (releasing an unknown key is a no-op). The idle
// timer is disabled exactly while at least one claim exists AND the app is in the foreground: on background
// the claims are kept but suspended (the display is never held awake in the background), and they apply again
// on foreground return. Nothing here grants background execution.
@MainActor
final class ScreenAwake {
    static let shared = ScreenAwake(apply: { UIApplication.shared.isIdleTimerDisabled = $0 },
                                    appIsActive: UIApplication.shared.applicationState != .background,
                                    observeLifecycle: true)

    private let apply: (Bool) -> Void
    private var claims = Set<String>()
    private var appIsActive: Bool
    /// What was last written. iOS starts with auto-lock ON (false), so nothing is written until a change.
    private var applied = false
    private var observers: [NSObjectProtocol] = []

    /// `apply` sets the real idle-timer flag; tests inject a recorder.
    init(apply: @escaping (Bool) -> Void, appIsActive: Bool = true, observeLifecycle: Bool = false) {
        self.apply = apply
        self.appIsActive = appIsActive
        if observeLifecycle {
            let nc = NotificationCenter.default
            observers.append(nc.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil,
                                            queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.setAppActive(false) }
            })
            observers.append(nc.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil,
                                            queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.setAppActive(true) }
            })
        }
    }

    /// Claim "keep the screen on" under `key` (idempotent).
    func hold(_ key: String) {
        claims.insert(key)
        update()
    }

    /// Drop the claim under `key` (idempotent; never touches other keys).
    func release(_ key: String) {
        claims.remove(key)
        update()
    }

    func isHeld(_ key: String) -> Bool { claims.contains(key) }
    var activeClaims: Set<String> { claims }
    /// Whether the idle timer is currently disabled by this owner.
    var isScreenHeldAwake: Bool { applied }

    /// Lifecycle input (wired to background/foreground notifications on the shared instance).
    func setAppActive(_ active: Bool) {
        appIsActive = active
        update()
    }

    private func update() {
        let want = appIsActive && !claims.isEmpty
        guard applied != want else { return }
        applied = want
        apply(want)
    }
}

// CaptureScreenAwake — the camera screen's use of ScreenAwake.
//
//  • While RECORDING: always held (an auto-lock would end the clip).
//  • While the capture screen is open but idle: held for `idleWindow` after the last interaction (opening the
//    camera, zoom, focus, record/stop, idea actions), so framing a shot is not interrupted by auto-lock, but a
//    camera left open on a table does not burn the display forever. After the window, normal auto-lock applies.
//  • On close: both claims released.
// Keys include an instance id, so two capture screens can never release each other's claim.
@MainActor
final class CaptureScreenAwake {
    nonisolated static let defaultIdleWindow: TimeInterval = 120

    private let awake: ScreenAwake
    private let idleWindow: TimeInterval
    private let sleep: (TimeInterval) async -> Void
    private let previewKey: String
    private let recordingKey: String
    private var idleTask: Task<Void, Never>?
    private var recording = false
    private var visible = false
    private var lastArmed: Date?
    private let now: () -> Date

    /// `awake` defaults to the shared owner (resolved here, on the main actor).
    init(awake: ScreenAwake? = nil,
         idleWindow: TimeInterval = CaptureScreenAwake.defaultIdleWindow,
         sleep: @escaping (TimeInterval) async -> Void = { try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000)) },
         now: @escaping () -> Date = Date.init) {
        self.awake = awake ?? .shared
        self.now = now
        self.idleWindow = idleWindow
        self.sleep = sleep
        let id = UUID().uuidString.prefix(8)
        previewKey = "camera.preview.\(id)"
        recordingKey = "camera.recording.\(id)"
    }

    func appear() {
        visible = true
        interaction()
    }

    /// Any user action on the capture screen re-arms the idle window.
    func interaction() {
        guard visible else { return }
        // Continuous gestures (pinch fires ~60×/s) re-arm at most every quarter window (≤ 1 s).
        let t = now()
        if awake.isHeld(previewKey), let last = lastArmed, t.timeIntervalSince(last) < min(1, idleWindow / 4) { return }
        lastArmed = t
        awake.hold(previewKey)
        idleTask?.cancel()
        let window = idleWindow
        idleTask = Task { [weak self] in
            await self?.sleep(window)
            guard !Task.isCancelled else { return }
            self?.idleExpired()
        }
    }

    func recordingChanged(_ isRecording: Bool) {
        recording = isRecording
        if isRecording {
            awake.hold(recordingKey)
        } else {
            awake.release(recordingKey)
            interaction()   // stopping is an interaction: keep the preview awake for the next shot
        }
    }

    func disappear() {
        visible = false
        idleTask?.cancel()
        idleTask = nil
        lastArmed = nil
        recording = false
        awake.release(previewKey)
        awake.release(recordingKey)
    }

    private func idleExpired() {
        idleTask = nil
        lastArmed = nil
        awake.release(previewKey)   // the recording claim (if any) is untouched
    }

    var holdsPreview: Bool { awake.isHeld(previewKey) }
    var holdsRecording: Bool { awake.isHeld(recordingKey) }
}
