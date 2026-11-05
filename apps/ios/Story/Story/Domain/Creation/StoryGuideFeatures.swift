import Foundation

// StoryGuideFeatures — iOS feature flags for the AI Shooting Script (story_guide/2) + visual reference
// images (Unsplash via the backend proxy). Mirrors the StoryMultimodalPlanning idiom: an env var (Xcode
// scheme / launch) OR a persisted UserDefaults override, else a compiled default. Both default OFF until
// the owner's device acceptance + Production provider approval (no deploy/beta from this milestone).
//
// Two SEPARATE flags by owner requirement: Guide v2 can ship WITHOUT images (text-only cards), and images
// never gate Guide generation or the UI. guideV2Enabled controls the shooting-script contract/UI;
// sceneImagesEnabled controls whether the client ever calls /v1/scene-image at all.
enum StoryGuideFeatures {

    // MARK: - Guide v2 (AI shooting script)

    /// When ON, Story creation + Story Home use the story_guide/2 scene-based shooting script (service,
    /// coordinator, scene-card UI). When OFF, the frozen story_guide/1 creative-map path is used unchanged.
    static var guideV2Enabled: Bool {
        if ProcessInfo.processInfo.environment["STORY_GUIDE_V2"] == "0" { return false }
        if ProcessInfo.processInfo.environment["STORY_GUIDE_V2"] == "1" { return true }
        if UserDefaults.standard.object(forKey: guideV2Key) != nil {
            return UserDefaults.standard.bool(forKey: guideV2Key)
        }
        return _guideV2Default
    }
    static let guideV2Key = "STORY_GUIDE_V2"
    static func setGuideV2Override(_ on: Bool) { UserDefaults.standard.set(on, forKey: guideV2Key) }
    // v2 (shooting script) is now the ONLY generation path (owner 2026-10-24: v1 generation removed; v1
    // persisted guides still RENDER as a legacy fallback). Defaults ON; the env "0" / UserDefaults override
    // remain as a debug kill-switch only.
    private static let _guideV2Default = true

    // MARK: - Scene reference images (Unsplash via backend proxy)

    /// When ON, scene cards lazily request ONE reference image per scene from the backend proxy
    /// (/v1/scene-image). When OFF (default), cards render text-only and the client makes ZERO image
    /// requests — so a missing provider key / un-rolled-out backend costs nothing. Independent of guideV2.
    static var sceneImagesEnabled: Bool {
        if ProcessInfo.processInfo.environment["STORY_SCENE_IMAGES"] == "0" { return false }
        if ProcessInfo.processInfo.environment["STORY_SCENE_IMAGES"] == "1" { return true }
        if UserDefaults.standard.object(forKey: sceneImagesKey) != nil {
            return UserDefaults.standard.bool(forKey: sceneImagesKey)
        }
        return _sceneImagesDefault
    }
    static let sceneImagesKey = "STORY_SCENE_IMAGES"
    static func setSceneImagesOverride(_ on: Bool) { UserDefaults.standard.set(on, forKey: sceneImagesKey) }
    private static let _sceneImagesDefault = true   // ships with v2; backend provisioned. Env "0" disables.

    // MARK: - Reference-media mode (Phase 1B): image (Unsplash) | video (Pixabay)

    /// ONE shared switch for BOTH surfaces (Shooting Idea + Story Guide), per owner §2/§4. `image` keeps the
    /// existing Unsplash behavior and makes ZERO video requests; `video` shows a Pixabay reference video with
    /// image/text fallback. Resolution order mirrors the other flags: env var -> UserDefaults -> compiled
    /// default. Defaults SAFELY to `image` when missing or invalid, so a half-provisioned backend never
    /// breaks the card. Independent of sceneImagesEnabled (which still gates whether images load at all).
    enum ReferenceMediaMode: String { case image, video }

    static var referenceMediaMode: ReferenceMediaMode {
        if let env = ProcessInfo.processInfo.environment[referenceMediaKey],
           let m = ReferenceMediaMode(rawValue: env.lowercased()) { return m }
        if let raw = UserDefaults.standard.string(forKey: referenceMediaKey),
           let m = ReferenceMediaMode(rawValue: raw.lowercased()) { return m }
        return _referenceMediaDefault
    }
    /// True when the app should request/show reference VIDEOS. Also requires sceneImagesEnabled, which is the
    /// master kill-switch for any reference-media network call.
    static var referenceVideoEnabled: Bool { sceneImagesEnabled && referenceMediaMode == .video }

    static let referenceMediaKey = "STORY_REFERENCE_MEDIA_MODE"
    static func setReferenceMediaOverride(_ mode: ReferenceMediaMode) {
        UserDefaults.standard.set(mode.rawValue, forKey: referenceMediaKey)
    }
    private static let _referenceMediaDefault = ReferenceMediaMode.image   // owner §4: safe default is image
}
