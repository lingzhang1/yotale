import SwiftUI

// AppLanguage — the ONE source of truth for the language of fixed interface text.
//
// Three concepts must never be conflated (see specs/.../i18n-zh-hans-*.md):
//   • APP language     — fixed UI text. Chosen here: follow iPhone | English | 简体中文.
//   • INPUT language   — what the user types/speaks to the AI. Independent; never changes the app language.
//   • CONTENT language — language of Story-specific generated content (Guide, Shooting Ideas). See
//                        `ContentLanguage` (resolved per request, never persisted; see ContentLanguageResolver).
//
// Persistence: exactly one UserDefaults key (`AppLanguageStore.defaultsKey`). `.system` stores nothing special:
// the effective language then follows the iOS app-language setting (Settings ▸ YoTale ▸ Language) via
// `Bundle.main.preferredLocalizations`, so per-app language settings keep working. We deliberately do NOT write
// `AppleLanguages` (that would need a relaunch and would compete with the iOS per-app setting).

/// The user's stored choice.
enum AppLanguage: String, CaseIterable, Identifiable, Sendable {
    case system
    case en
    case zhHans = "zh-Hans"

    var id: String { rawValue }

    /// Picker label. Endonyms are never translated, so a user who lands in the wrong language can still find theirs.
    var endonym: String? {
        switch self {
        case .system: return nil          // localized: "Follow iPhone language"
        case .en:     return "English"
        case .zhHans: return "简体中文"
        }
    }
}

/// A language the app actually ships.
enum ResolvedLanguage: String, Sendable {
    case en
    case zhHans = "zh-Hans"

    /// Name of the .lproj folder in the app bundle.
    var lprojName: String { rawValue }
    var locale: Locale { Locale(identifier: rawValue) }
    var contentLanguage: ContentLanguage { self == .zhHans ? .zhHans : .en }

    static let supported: [ResolvedLanguage] = [.en, .zhHans]
}

/// Pure resolution rule (unit-tested).
enum AppLanguageResolver {
    /// `systemPreferred` = the app's preferred localizations in order (iOS already applies per-app language and
    /// the user's language list, restricted to what the app ships). First supported match wins; default English.
    static func resolve(_ preference: AppLanguage, systemPreferred: [String]) -> ResolvedLanguage {
        switch preference {
        case .en: return .en
        case .zhHans: return .zhHans
        case .system:
            for tag in systemPreferred {
                let t = tag.lowercased()
                if t.hasPrefix("zh") { return .zhHans }   // zh-Hans, zh-Hans-CN, zh_CN… (Traditional is not shipped yet)
                if t.hasPrefix("en") { return .en }
            }
            return .en
        }
    }
}

/// Observable store injected at the app root. Views read `effective` / `locale`; non-view code uses `L10n`.
@MainActor
@Observable
final class AppLanguageStore {
    static let defaultsKey = "story.appLanguage"
    static let shared = AppLanguageStore()

    private let defaults: UserDefaults

    var preference: AppLanguage {
        didSet {
            guard preference != oldValue else { return }
            defaults.set(preference.rawValue, forKey: Self.defaultsKey)
        }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.preference = AppLanguageStore.stored(defaults)
    }

    var effective: ResolvedLanguage { L10n.resolved(preference) }
    var locale: Locale { effective.locale }

    nonisolated static func stored(_ defaults: UserDefaults = .standard) -> AppLanguage {
        guard let raw = defaults.string(forKey: defaultsKey), let v = AppLanguage(rawValue: raw) else { return .system }
        return v
    }
}

/// Language of Story-specific generated content sent to the backend as `content_language`.
enum ContentLanguage: String, Sendable, Codable {
    case en
    case zhHans = "zh-Hans"
}

/// Non-SwiftUI string access. Thread-safe (reads UserDefaults + a bundle), so error descriptions, formatters and
/// background code all see the same language as the UI.
///
///     L10n.t("Couldn't send a code.")
///     L10n.t("Resend in \(seconds)s")          // interpolation + plurals work like SwiftUI Text
enum L10n {
    /// Current stored preference → resolved language. Reads UserDefaults each time (cheap) so it can never go stale.
    static var current: ResolvedLanguage { resolved(AppLanguageStore.stored()) }

    static func resolved(_ pref: AppLanguage) -> ResolvedLanguage {
        AppLanguageResolver.resolve(pref, systemPreferred: Bundle.main.preferredLocalizations)
    }

    /// The `<lang>.lproj` sub-bundle for the current language (falls back to the main bundle).
    static var bundle: Bundle { bundle(for: current) }

    static func bundle(for lang: ResolvedLanguage) -> Bundle {
        if let path = Bundle.main.path(forResource: lang.lprojName, ofType: "lproj"), let b = Bundle(path: path) {
            return b
        }
        return Bundle.main
    }

    static var locale: Locale { current.locale }

    /// Localized string for the current app language.
    static func t(_ value: String.LocalizationValue) -> String {
        let lang = current
        return String(localized: value, bundle: bundle(for: lang), locale: lang.locale)
    }

    /// Localized string for an explicit language (tests, previews).
    static func t(_ value: String.LocalizationValue, in lang: ResolvedLanguage) -> String {
        String(localized: value, bundle: bundle(for: lang), locale: lang.locale)
    }
}

/// Locale-aware formatting, always in the APP language (never the input/content language).
enum L10nFormat {
    /// "m:ss" clock for media durations. Digits are Latin in both shipped languages; kept in one place so it
    /// can follow the locale later without touching call sites.
    static func clock(_ seconds: Double) -> String {
        let total = max(0, Int(seconds.rounded()))
        return String(format: "%d:%02d", total / 60, total % 60)
    }

    /// Short date, in the app language.
    static func shortDate(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = L10n.locale
        f.dateStyle = .medium
        f.timeStyle = .none
        return f.string(from: date)
    }

    /// Seconds with one decimal ("2.5s" / "2.5 秒" via the catalog key "%@s").
    static func decimal(_ value: Double, fractionDigits: Int = 1) -> String {
        let f = NumberFormatter()
        f.locale = L10n.locale
        f.numberStyle = .decimal
        f.minimumFractionDigits = fractionDigits
        f.maximumFractionDigits = fractionDigits
        return f.string(from: NSNumber(value: value)) ?? String(format: "%.\(fractionDigits)f", value)
    }
}
