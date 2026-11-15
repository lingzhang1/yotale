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

    func test_content_chineseDescription_withEnglishApp_isChinese() {
        let r = ContentLanguageResolver.resolve(substantiveTexts: ["京都三日游", "清水寺、锦市场和夜晚的鸭川"],
                                                appLanguage: .en)
        XCTAssertEqual(r, .zhHans)
    }

    func test_content_englishDescription_withChineseApp_isEnglish() {
        let r = ContentLanguageResolver.resolve(substantiveTexts: ["Three days in New York", "restaurants and a Broadway show"],
                                                appLanguage: .zhHans)
        XCTAssertEqual(r, .en)
    }

    func test_content_shortUnrelatedInput_doesNotFlipLanguage() {
        // Story is English; user types "好" — insufficient signal alone, and the Story text still decides.
        let r = ContentLanguageResolver.resolve(substantiveTexts: ["Three days in New York", "好"], appLanguage: .zhHans)
        XCTAssertEqual(r, .en)
        // No Story text at all and only a tiny input → app language.
        XCTAssertEqual(ContentLanguageResolver.resolve(substantiveTexts: ["ok"], appLanguage: .zhHans), .zhHans)
        XCTAssertEqual(ContentLanguageResolver.resolve(substantiveTexts: [""], appLanguage: .en), .en)
    }

    func test_content_explicitRequest_winsOverEverything() {
        XCTAssertEqual(ContentLanguageResolver.resolve(explicitRequestIn: ["Please answer in English"],
                                                       substantiveTexts: ["京都三日游，清水寺"], appLanguage: .zhHans), .en)
        XCTAssertEqual(ContentLanguageResolver.resolve(explicitRequestIn: ["请用中文回答"],
                                                       substantiveTexts: ["Three days in New York"], appLanguage: .en), .zhHans)
        XCTAssertEqual(ContentLanguageResolver.resolve(explicitRequestIn: ["用英文写"],
                                                       substantiveTexts: [], appLanguage: .zhHans), .en)
    }

    func test_content_contradictoryExplicit_isIgnored() {
        XCTAssertNil(ContentLanguageResolver.explicitLanguageRequest(in: "in English and in Chinese"))
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
