import Foundation

/// Billing V1 / B3: the legal pages Apple requires next to a subscription purchase.
/// Terms of Use is Apple's standard Licensed Application EULA. The Privacy Policy is the published YoTale page, in the app language.
/// If the pages move (e.g. to yotale.ai/privacy), change them HERE only.
enum LegalLinks {
    static let termsOfUse = URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!
    static let privacyPolicyEnglish = URL(string: "https://lingzhang1.github.io/yotale-legal/privacy.html")!
    static let privacyPolicyChinese = URL(string: "https://lingzhang1.github.io/yotale-legal/privacy-zh.html")!

    static func privacyPolicy(for language: ResolvedLanguage) -> URL {
        language == .zhHans ? privacyPolicyChinese : privacyPolicyEnglish
    }
}
