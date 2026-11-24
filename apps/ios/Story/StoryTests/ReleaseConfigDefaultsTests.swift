import XCTest
@testable import Story

/// P1-G0: accepted product features need NO manually injected flag, environment variable or UserDefaults value.
/// These tests run with whatever the test host provides (no scheme env is relied on) and assert the standard
/// behavior plus the two deliberately retained/baked settings.
final class ReleaseConfigDefaultsTests: XCTestCase {

    override func setUp() {
        super.setUp()
        // A stale developer override on this simulator must never decide an assertion below.
        UserDefaults.standard.removeObject(forKey: StoryMultimodalPlanning.critiqueFlagKey)
        UserDefaults.standard.removeObject(forKey: StoryGuideFeatures.referenceMediaKey)
    }

    /// Apple Sign In is BAKED per build configuration (xcconfig -> Info.plist), not an Xcode Run argument or
    /// persisted value. Neither the dev nor the beta Cognito pool has a SignInWithApple IdP today, so both
    /// configurations bake 0 and the button stays hidden — deterministically, however the app is launched.
    func test_appleSignIn_isBakedAndOffUntilTheIdpExists() {
        UserDefaults.standard.set("1", forKey: "STORY_APPLE_SIGNIN_AVAILABLE")   // a stale/legacy persisted value
        defer { UserDefaults.standard.removeObject(forKey: "STORY_APPLE_SIGNIN_AVAILABLE") }
        let baked = Bundle.main.infoDictionary?["StoryAppleSignInAvailable"] as? String
        XCTAssertTrue(baked == "0" || baked == "1", "Info.plist must carry an explicit 0/1 (got \(String(describing: baked)))")
        XCTAssertEqual(StoryAuthConfig.appleSignInAvailable, baked == "1",
                       "availability must come ONLY from the baked value, never UserDefaults/env")
    }

    /// The retained critique pass defaults OFF (owner 2026-11-15: ~+20-28 s of planning for no demonstrated gain)
    /// and can still be turned ON, and back OFF, without a code change.
    func test_critiqueRevision_isRetainedAndDefaultsOff() {
        UserDefaults.standard.removeObject(forKey: StoryMultimodalPlanning.critiqueFlagKey)
        XCTAssertFalse(StoryMultimodalPlanning.critiqueRevisionEnabled, "a plain original create plans in ONE call")
        defer { UserDefaults.standard.removeObject(forKey: StoryMultimodalPlanning.critiqueFlagKey) }
        StoryMultimodalPlanning.setCritiqueOverride(true)
        XCTAssertTrue(StoryMultimodalPlanning.critiqueRevisionEnabled, "the retained setting can turn the 3-call path on")
        StoryMultimodalPlanning.setCritiqueOverride(false)
        XCTAssertFalse(StoryMultimodalPlanning.critiqueRevisionEnabled)
    }

    /// The critique-pass rules that the removed STORY_CRITIQUE_EXPLORE / kept STORY_CRITIQUE_REVISION settings
    /// used to blur: original Create + full re-edit run it; Explore and targeted Revise never do; the retained
    /// setting can switch it off; text-only (non-multimodal) planning never runs it.
    func test_critiqueDecision_originalYes_exploreAndTargetedReviseNo() {
        typealias P = StoryMultimodalPlanning
        XCTAssertTrue(P.critiqueApplies(wantMultimodal: true, critiqueEnabled: true, isExplore: false, reviseScope: nil),
                      "original Create runs the critique pass")
        XCTAssertTrue(P.critiqueApplies(wantMultimodal: true, critiqueEnabled: true, isExplore: false, reviseScope: .fullReedit),
                      "a full re-edit (Path C) keeps the original behavior")
        XCTAssertFalse(P.critiqueApplies(wantMultimodal: true, critiqueEnabled: true, isExplore: true, reviseScope: nil),
                       "Explore plans in ONE call, always")
        XCTAssertFalse(P.critiqueApplies(wantMultimodal: true, critiqueEnabled: true, isExplore: false,
                                         reviseScope: .targeted(needsImages: false)),
                       "a targeted revise is a bounded change, no critique")
        XCTAssertFalse(P.critiqueApplies(wantMultimodal: true, critiqueEnabled: false, isExplore: false, reviseScope: nil),
                       "with the setting off (the default) even an original Create plans in one call")
        XCTAssertFalse(P.critiqueApplies(wantMultimodal: false, critiqueEnabled: true, isExplore: false, reviseScope: nil),
                       "text-only planning never runs a multimodal critique")
    }

    /// Reference media (parked video feature) defaults to image with nothing configured.
    func test_referenceMedia_defaultsToImageAndVideoStaysOff() {
        XCTAssertEqual(StoryGuideFeatures.referenceMediaMode, .image)
        XCTAssertFalse(StoryGuideFeatures.referenceVideoEnabled)
    }

    /// Diagnostics never need a switch and never touch the network: the breadcrumb call is a no-throw local log.
    func test_diagnosticBreadcrumb_isLocalAndSwitchFree() {
        MediaEngineV1.beacon("release-config-defaults probe")   // must simply return; no env flag involved
    }
}
