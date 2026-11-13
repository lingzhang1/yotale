import Foundation

/// Developer-only backend OVERRIDE for DEBUG builds: an Xcode scheme environment row (attached launch only).
///
/// How the app picks its backend (see `StoryEnvironment`):
///   • Beta / TestFlight / Release builds: ONLY the values baked from the xcconfig at build time. Nothing here
///     is read.
///   • DEBUG builds: per key, a scheme env row (this type) → the baked Development.xcconfig value → the
///     built-in development default.
/// To switch stage, switch SCHEME (Story = dev, Story (Beta) = beta) — not env rows.
///
/// HISTORY: this type used to PERSIST any scheme value into UserDefaults so a detached launch kept it. That
/// made a Debug build silently stick to whatever backend a past scheme once pointed at, long after the rows
/// were removed, and its launch log reported those saved values even in a Beta build (which never used them).
/// Persistence is gone; `clearLegacyOverrides` deletes values saved by older builds. Consequence: a scheme
/// override row applies only to an ATTACHED launch; a detached Debug launch uses Development.xcconfig.
/// These are NON-SECRET identifiers (pool id, public client id, hosted domain, API URL) — never credentials.
enum StoryLaunchConfig {
    /// The config keys a DEBUG scheme row may override.
    static let keys = [
        "STORY_API_BASE_URL",
        "STORY_COGNITO_REGION",
        "STORY_COGNITO_USER_POOL_ID",
        "STORY_COGNITO_APP_CLIENT_ID",
        "STORY_COGNITO_DOMAIN_PREFIX",
        "STORY_COGNITO_REDIRECT_URI",
    ]

    /// UserDefaults prefix older builds persisted under (kept ONLY so they can be cleared).
    static let legacyStorePrefix = "StoryLaunchConfig."

    /// Delete backend values persisted by older builds. Call once at launch, before anything reads the
    /// environment. Returns the number of keys removed (0 once clean). Touches nothing else in UserDefaults.
    @discardableResult
    static func clearLegacyOverrides(_ defaults: UserDefaults = .standard) -> Int {
        var removed = 0
        for k in keys where defaults.object(forKey: legacyStorePrefix + k) != nil {
            defaults.removeObject(forKey: legacyStorePrefix + k)
            removed += 1
        }
        return removed
    }

    /// The scheme-row override for `key` on THIS launch, or nil. Never reads persisted state.
    static func value(_ key: String, environment: [String: String] = ProcessInfo.processInfo.environment) -> String? {
        guard let v = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines), !v.isEmpty else { return nil }
        return v
    }
}
