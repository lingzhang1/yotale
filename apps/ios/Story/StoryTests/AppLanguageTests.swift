import XCTest
@testable import Story

// App language preference + content-language policy. Pure logic, no network, no model.
@MainActor
final class AppLanguageTests: XCTestCase {

    private func freshDefaults() -> UserDefaults {
        let name = "AppLanguageTests-\(UUID().uuidString)"
        let d = UserDefaults(suiteName: name)!
        d.removePersistentDomain(forName: name)
        return d
    }

    // MARK: resolution

    func test_system_followsPreferredLocalizations() {
        XCTAssertEqual(AppLanguageResolver.resolve(.system, systemPreferred: ["zh-Hans"]), .zhHans)
        XCTAssertEqual(AppLanguageResolver.resolve(.system, systemPreferred: ["zh-Hans-CN", "en"]), .zhHans)
        XCTAssertEqual(AppLanguageResolver.resolve(.system, systemPreferred: ["en", "zh-Hans"]), .en)
        XCTAssertEqual(AppLanguageResolver.resolve(.system, systemPreferred: ["fr", "de"]), .en)   // unsupported → English
        XCTAssertEqual(AppLanguageResolver.resolve(.system, systemPreferred: []), .en)
    }

    func test_explicitChoice_overridesSystem() {
        XCTAssertEqual(AppLanguageResolver.resolve(.en, systemPreferred: ["zh-Hans"]), .en)
        XCTAssertEqual(AppLanguageResolver.resolve(.zhHans, systemPreferred: ["en"]), .zhHans)
    }

    // MARK: persistence

    func test_preference_defaultsToSystem_andPersists() {
        let d = freshDefaults()
        let s1 = AppLanguageStore(defaults: d)
        XCTAssertEqual(s1.preference, .system)
        s1.preference = .zhHans
        XCTAssertEqual(d.string(forKey: AppLanguageStore.defaultsKey), "zh-Hans")
        let s2 = AppLanguageStore(defaults: d)          // "restart"
        XCTAssertEqual(s2.preference, .zhHans)
        s2.preference = .system
        XCTAssertEqual(AppLanguageStore(defaults: d).preference, .system)
    }

    func test_corruptStoredValue_fallsBackToSystem() {
        let d = freshDefaults()
        d.set("klingon", forKey: AppLanguageStore.defaultsKey)
        XCTAssertEqual(AppLanguageStore(defaults: d).preference, .system)
    }

    func test_singleSourceOfTruth_keyIsStable() {
        XCTAssertEqual(AppLanguageStore.defaultsKey, "story.appLanguage")
    }

    // MARK: L10n bundles (needs the zh-Hans .lproj in the test host app)

    func test_L10n_translatesGlossaryTerms_inBothLanguages() {
        XCTAssertEqual(L10n.t("Start a Story", in: .en), "Start a Story")
        XCTAssertEqual(L10n.t("Moments", in: .zhHans), "片段")
        XCTAssertNotEqual(L10n.t("Create my video", in: .zhHans), "Create my video")
    }

    func test_L10n_plural_usesLanguageRules() {
        XCTAssertEqual(L10n.t("\(1) moment", in: .en), "1 moment")
        XCTAssertEqual(L10n.t("\(3) moments", in: .en), "3 moments")
        XCTAssertTrue(L10n.t("\(3) moments", in: .zhHans).contains("3"))
        XCTAssertFalse(L10n.t("\(3) moments", in: .zhHans).contains("moment"))
    }

    // MARK: content language policy

    func test_content_alwaysFollowsAppLanguage_whateverTheText() {
        let zh = ["京都三日游", "清水寺、锦市场和夜晚的鸭川"], en = ["Three days in New York", "restaurants and a Broadway show"]
        for texts in [zh, en, ["我们去 Kyoto 看樱花"], ["ok"], [""]] {
            XCTAssertEqual(ContentLanguageResolver.resolve(substantiveTexts: texts, appLanguage: .zhHans), .zhHans)
            XCTAssertEqual(ContentLanguageResolver.resolve(substantiveTexts: texts, appLanguage: .en), .en)
        }
        // Even an explicit "in English" does not change it: one language setting, no per-text overrides.
        XCTAssertEqual(ContentLanguageResolver.resolve(explicitRequestIn: ["Please answer in English"],
                                                       substantiveTexts: ["Three days in New York"], appLanguage: .zhHans), .zhHans)
    }

    func test_content_requestValue_followsAppLanguage() {
        XCTAssertEqual(ContentLanguageResolver.requestValue(substantiveTexts: ["TMB Hiking"], appLanguage: .zhHans), "zh-Hans")
        // English app + pure-English text: nothing sent (request byte-identical to before).
        XCTAssertNil(ContentLanguageResolver.requestValue(substantiveTexts: ["TMB Hiking trip"], appLanguage: .en))
        // English app + Chinese note: explicit "en" so the output stays English.
        XCTAssertEqual(ContentLanguageResolver.requestValue(substantiveTexts: ["京都三日游"], appLanguage: .en), "en")
    }

    func test_content_mixedText_usesDominantScript() {
        // Han characters outnumber Latin words.
        XCTAssertEqual(ContentLanguageResolver.dominantLanguage(of: "我们去 Kyoto 看樱花，住在祇园附近"), .zhHans)
        // Mostly English with a Chinese place name.
        XCTAssertEqual(ContentLanguageResolver.dominantLanguage(of: "A week eating our way through Chengdu 成都 street food"), .en)
    }

    func test_content_urlsAndEmails_doNotSway() {
        XCTAssertNil(ContentLanguageResolver.dominantLanguage(of: "see https://example.com/abc"))
    }
}
