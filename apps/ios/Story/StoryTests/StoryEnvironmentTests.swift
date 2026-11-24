import XCTest
@testable import Story

// TestFlight Option A — StoryEnvironment resolution + consistency guard (offline, pure).
//
// The RELEASE-only Info.plist-baked resolution and its fatalError paths cannot be exercised from a unit
// process (no archive, and a fatalError would kill the runner). What IS pure and testable is the
// consistency guard that the release resolver relies on and the hardcoded development default — so these
// lock the tripwire that decides "mixed dev/beta env => reject" and prove the dev default is internally
// consistent. The archive-level verification is the scripts/verify_beta_archive.sh pre-archive gate + the
// device "Beta build" acceptance step.
final class StoryEnvironmentTests: XCTestCase {

    func test_developmentDefault_isConsistent() throws {
        XCTAssertNoThrow(try StoryEnvironment.developmentDefault.assertConsistent())
        XCTAssertEqual(StoryEnvironment.developmentDefault.kind, .development)
        XCTAssertEqual(StoryEnvironment.developmentDefault.userPoolId, "us-east-1_AzfHOEdA5")
    }

    func test_betaLabel_withDevPool_isRejected() {
        // A beta-labelled env carrying the DEV Cognito pool is the exact "mixed" failure the gate must catch.
        let mixed = StoryEnvironment(
            kind: .beta,
            apiBaseURL: URL(string: "https://asxtxgjiis.us-east-1.awsapprunner.com")!,
            cognitoRegion: "us-east-1",
            userPoolId: "us-east-1_AzfHOEdA5",            // DEV pool — mismatch
            appClientId: "4f3dtn9d0nk5uq1hcvbdc7m73c",
            domainPrefix: "story-beta-auth",
            redirectURI: "story://auth")
        XCTAssertThrowsError(try mixed.assertConsistent())
    }

    func test_betaLabel_withDevApi_isRejected() {
        let mixed = StoryEnvironment(
            kind: .beta,
            apiBaseURL: URL(string: "https://ydmju5wdps.us-east-1.awsapprunner.com")!,  // DEV API — mismatch
            cognitoRegion: "us-east-1",
            userPoolId: "us-east-1_3cPNfbrUl",
            appClientId: "4f3dtn9d0nk5uq1hcvbdc7m73c",
            domainPrefix: "story-beta-auth",
            redirectURI: "story://auth")
        XCTAssertThrowsError(try mixed.assertConsistent())
    }

    func test_fullyBeta_isConsistent() throws {
        let beta = StoryEnvironment(
            kind: .beta,
            apiBaseURL: URL(string: "https://asxtxgjiis.us-east-1.awsapprunner.com")!,
            cognitoRegion: "us-east-1",
            userPoolId: "us-east-1_3cPNfbrUl",
            appClientId: "4f3dtn9d0nk5uq1hcvbdc7m73c",
            domainPrefix: "story-beta-auth",
            redirectURI: "story://auth")
        XCTAssertNoThrow(try beta.assertConsistent())
        XCTAssertEqual(beta.kind, .beta)
    }

    // The resolver that the app actually uses must at least produce an internally-consistent environment in
    // whatever configuration the test target builds (DEBUG) — i.e. it never hands back a mixed env.
    func test_current_isInternallyConsistent() throws {
        XCTAssertNoThrow(try StoryEnvironment.current.assertConsistent())
    }
}

// Backend selection no longer persists anything: a scheme row is an attached-launch override only, and values
// saved by older builds (which made a Debug build stick to a past scheme's backend) are cleared at launch.
final class StoryLaunchConfigTests: XCTestCase {
    private var suite: String!
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suite = "StoryLaunchConfigTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        super.tearDown()
    }

    func test_clearLegacyOverrides_removesOnlyTheSavedBackendKeys() {
        for k in StoryLaunchConfig.keys { defaults.set("beta-ish", forKey: StoryLaunchConfig.legacyStorePrefix + k) }
        defaults.set(true, forKey: "STORY_CRITIQUE_REVISION")   // unrelated setting must survive
        XCTAssertEqual(StoryLaunchConfig.clearLegacyOverrides(defaults), StoryLaunchConfig.keys.count)
        for k in StoryLaunchConfig.keys {
            XCTAssertNil(defaults.object(forKey: StoryLaunchConfig.legacyStorePrefix + k), k)
        }
        XCTAssertEqual(defaults.object(forKey: "STORY_CRITIQUE_REVISION") as? Bool, true)
        XCTAssertEqual(StoryLaunchConfig.clearLegacyOverrides(defaults), 0, "idempotent once clean")
    }

    func test_value_readsOnlyThisLaunchsSchemeRow_neverSavedValues() {
        defaults.set("https://stale.example", forKey: StoryLaunchConfig.legacyStorePrefix + "STORY_API_BASE_URL")
        XCTAssertNil(StoryLaunchConfig.value("STORY_API_BASE_URL", environment: [:]),
                     "a saved value from an older build is never used")
        XCTAssertEqual(StoryLaunchConfig.value("STORY_API_BASE_URL", environment: ["STORY_API_BASE_URL": " https://x "]),
                       "https://x")
        XCTAssertNil(StoryLaunchConfig.value("STORY_API_BASE_URL", environment: ["STORY_API_BASE_URL": "  "]))
    }

    func test_launchSummary_reportsTheEnvironmentActuallyInUse() {
        let line = StoryEnvironment.launchSummary()
        let cur = StoryEnvironment.current
        XCTAssertTrue(line.hasPrefix("STORY_ENVIRONMENT kind=\(cur.kind.rawValue) "), line)
        XCTAssertTrue(line.contains("pool=\(cur.userPoolId)"), line)
        XCTAssertTrue(line.contains("api=\(cur.apiBaseURL.host ?? "")"), line)
        XCTAssertTrue(line.contains("consistency=ok"), line)
        XCTAssertFalse(line.contains(cur.appClientId), "the full client id is not logged")
    }
}
