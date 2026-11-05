import SwiftUI
import AVKit
import AVFoundation

// ReferenceVideoPlayer — Phase 1B shared player for a stock-video reference (Pixabay), used by both the
// Shooting Idea "See framing" sheet and the Story Guide hero. Owner §8 requirements:
//   * Native AVFoundation/AVKit, no third-party SDK.
//   * Streams the PREVIEW MP4 directly from cdn.pixabay.com (embedding allowed); no full-res download.
//   * Poster shown until the user starts playback; playback is USER-INITIATED.
//   * MUTED by default — never activates the mic or changes the shared audio session (camera recording
//     must be unaffected). We only set the player instance muted; we do NOT touch AVAudioSession.
//   * Preserves aspect ratio (.resizeAspect), no cropping of the subject.
//   * Loops ONLY while visible and playing; pauses on disappear / background; clean teardown (no leaks).
//   * Respects Reduce Motion: with it on, we do not auto-loop — one play-through, then show replay.
//   * At most ONE instance is mounted per screen by construction (callers show a single sheet / hero).
//
// The poster is loaded through the backend (Pixabay forbids image hotlinking); the MP4 is streamed direct.
struct ReferenceVideoPlayer: View {
    let video: SceneVideoDTO
    /// Loads the compliant poster image data via the backend (nil when unavailable -> neutral placeholder).
    let loadPoster: () async -> Data?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    @State private var player: AVPlayer?
    @State private var isPlaying = false
    @State private var posterImage: UIImage?
    @State private var failed = false
    @State private var loopObserver: NSObjectProtocol?

    private var aspect: CGFloat { video.aspect }

    var body: some View {
        ZStack {
            Color.black.opacity(0.9)
            if let player, isPlaying {
                VideoPlayer(player: player)
                    .aspectRatio(aspect, contentMode: .fit)
                    .accessibilityLabel("Example video, muted")
            } else {
                posterLayer
            }
        }
        .aspectRatio(aspect, contentMode: .fit)
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .task { if posterImage == nil { posterImage = (await loadPoster()).flatMap(UIImage.init(data:)) } }
        .onDisappear(perform: teardown)
        .onChange(of: scenePhase) { _, phase in if phase != .active { pause() } }
    }

    // Poster + Play button (user-initiated playback). On failure, a neutral placeholder — never a wrong clip.
    private var posterLayer: some View {
        ZStack {
            if let posterImage {
                Image(uiImage: posterImage).resizable().scaledToFit()
            } else {
                Color.white.opacity(0.06)
                    .overlay(Image(systemName: failed ? "video.slash" : "film")
                        .font(.system(size: 28)).foregroundStyle(.white.opacity(0.35)))
            }
            if !failed {
                Button(action: play) {
                    Image(systemName: "play.circle.fill")
                        .font(.system(size: 54))
                        .foregroundStyle(.white.opacity(0.92))
                        .shadow(radius: 6)
                }
                .accessibilityLabel(isPlaying ? "Replay example video" : "Play example video")
                .accessibilityIdentifier("reference-video-play")
            }
        }
    }

    private func play() {
        guard let url = URL(string: video.previewURL) else { failed = true; return }
        let p = player ?? AVPlayer(url: url)
        p.isMuted = true                       // never unmute: example playback must stay silent
        player = p
        // Loop only when motion is allowed; otherwise a single play-through (Reduce Motion).
        if loopObserver == nil, !reduceMotion, let item = p.currentItem {
            loopObserver = NotificationCenter.default.addObserver(
                forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { _ in
                    p.seek(to: .zero); p.play()
                }
        }
        p.seek(to: .zero)
        p.play()
        isPlaying = true
    }

    private func pause() {
        player?.pause()
        isPlaying = false
    }

    private func teardown() {
        player?.pause()
        if let obs = loopObserver { NotificationCenter.default.removeObserver(obs); loopObserver = nil }
        player = nil
        isPlaying = false
    }
}
