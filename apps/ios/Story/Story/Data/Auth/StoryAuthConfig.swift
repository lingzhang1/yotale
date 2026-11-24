import Foundation

/// Client-side Cognito configuration for the Story auth flows (P0 Beta Auth Increment 4).
///
/// These are NON-SECRET identifiers (pool id, public app-client id, hosted domain) — never credentials.
/// Dev defaults match the provisioned `story-development-auth` stack; override at launch via environment for
/// staging/prod. There is NO client secret (the iOS app client is public, PKCE-protected).
enum StoryAuthConfig {
    static let region = StoryEnvironment.current.cognitoRegion
    static let userPoolId = StoryEnvironment.current.userPoolId
    static let appClientId = StoryEnvironment.current.appClientId
    /// Cognito hosted domain PREFIX (the full host is `<prefix>.auth.<region>.amazoncognito.com`).
    static let domainPrefix = StoryEnvironment.current.domainPrefix
    /// Native custom-scheme redirect registered on the app client + in Info.plist URL types.
    static let redirectURI = StoryEnvironment.current.redirectURI
    static let appleProviderName = "SignInWithApple"
    static let googleProviderName = "Google"

    /// Federated providers this build offers, BAKED per build configuration (Development.xcconfig /
    /// Beta.xcconfig `STORY_FEDERATED_PROVIDERS` → Info.plist `StoryFederatedProviders`), exactly like the rest
    /// of the environment identity: no Xcode Run argument, no persisted UserDefaults. Unknown names, `none` and
    /// an unresolved `$(...)` token yield nothing. scripts/release_config_gate.py rejects Google without Apple
    /// (App Store Guideline 4.8) and, post-deploy, any listed provider missing from that environment's pool.
    static var federatedProviders: Set<String> {
        let raw = (Bundle.main.infoDictionary?["StoryFederatedProviders"] as? String) ?? ""
        let known: Set<String> = [appleProviderName, googleProviderName]
        return Set(raw.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }).intersection(known)
    }

    /// Apple sign-in is only offered when the build lists the Apple IdP (configured on the pool).
    static var appleSignInAvailable: Bool { federatedProviders.contains(appleProviderName) }
    /// Google is only offered alongside Apple (App Store Guideline 4.8), even if a build lists it alone.
    static var googleSignInAvailable: Bool { appleSignInAvailable && federatedProviders.contains(googleProviderName) }

    static var domainHost: String { "\(domainPrefix).auth.\(region).amazoncognito.com" }
    static var tokenEndpoint: URL { URL(string: "https://\(domainHost)/oauth2/token")! }
    static var idpBase: URL { URL(string: "https://cognito-idp.\(region).amazonaws.com/")! }
    static func authorizeURL(provider: String, state: String, codeChallenge: String) -> URL {
        var c = URLComponents(string: "https://\(domainHost)/oauth2/authorize")!
        c.queryItems = [
            .init(name: "response_type", value: "code"),
            .init(name: "client_id", value: appClientId),
            .init(name: "identity_provider", value: provider),
            .init(name: "redirect_uri", value: redirectURI),
            .init(name: "scope", value: "openid email profile"),
            .init(name: "state", value: state),
            .init(name: "code_challenge", value: codeChallenge),
            .init(name: "code_challenge_method", value: "S256"),
        ]
        return c.url!
    }
}
