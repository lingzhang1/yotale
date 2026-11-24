import Foundation

// StoryGuideFeatures — reference-media mode for Shooting Ideas / Story Guide cards.
//
// P1-G0: Guide v2 (AI shooting script) and Scene Images are STANDARD product behavior. Their former switches
// (STORY_GUIDE_V2 / STORY_SCENE_IMAGES env + UserDefaults overrides) were removed; the only thing left here is
// the PARKED reference-VIDEO mode, whose backend capability stays disabled (STORY_REFERENCE_MEDIA_MODE=image).
enum StoryGuideFeatures {

    // MARK: - Reference-media mode (Phase 1B): image (Unsplash) | video (Pixabay)

    /// ONE shared switch for BOTH surfaces (Shooting Idea + Story Guide). `image` keeps the Unsplash behavior and
    /// makes ZERO video requests; `video` (PARKED — owner 2026-11-06) shows a Pixabay reference video with
    /// image/text fallback. Resolution: env var -> UserDefaults -> compiled default. Defaults SAFELY to `image`
    /// when missing or invalid, so a half-provisioned backend never breaks the card.
    enum ReferenceMediaMode: String { case image, video }

    static var referenceMediaMode: ReferenceMediaMode {
        if let env = ProcessInfo.processInfo.environment[referenceMediaKey],
           let m = ReferenceMediaMode(rawValue: env.lowercased()) { return m }
        if let raw = UserDefaults.standard.string(forKey: referenceMediaKey),
           let m = ReferenceMediaMode(rawValue: raw.lowercased()) { return m }
        return _referenceMediaDefault
    }
    /// True when the app should request/show reference VIDEOS (parked; image mode never does).
    static var referenceVideoEnabled: Bool { referenceMediaMode == .video }

    static let referenceMediaKey = "STORY_REFERENCE_MEDIA_MODE"
    static func setReferenceMediaOverride(_ mode: ReferenceMediaMode) {
        UserDefaults.standard.set(mode.rawValue, forKey: referenceMediaKey)
    }
    private static let _referenceMediaDefault = ReferenceMediaMode.image   // owner §4: safe default is image
}
