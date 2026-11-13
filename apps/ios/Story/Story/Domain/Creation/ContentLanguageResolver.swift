import Foundation

// ContentLanguageResolver — decides the language of Story-specific generated content (Story Guide, Shooting
// Ideas, coverage text). Pure and deterministic: NO model call, NO network. The result is sent to the backend as the
// optional `content_language` request field and is NEVER persisted (derived again from the Story each time), so
// existing Stories need no migration and changing the app language never regenerates or rewrites old content.
//
// Policy (first match wins):
//   1. An EXPLICIT language request in the user's text ("in English", "请用中文", "用英文回答"…).
//   2. (Reserved) a Story-specific stored preference — none exists today; adding one later slots in here.
//   3. The language of the SUBSTANTIVE Story text (title + description + event context + the instruction).
//      "Substantive" = at least `minLetters` letters/characters once digits, punctuation and URLs are ignored, so an
//      unrelated short input ("ok", "好", "3") never flips the language.
//   4. The app language.
//
// The app language is never changed by any of this.
enum ContentLanguageResolver {
    /// Minimum signal (Han characters, or Latin letters) before text counts as substantive.
    static let minHan = 2
    static let minLatinLetters = 8

    static func resolve(explicitRequestIn texts: [String] = [],
                        substantiveTexts: [String],
                        appLanguage: ResolvedLanguage) -> ContentLanguage {
        // 1. explicit request
        for t in texts.reversed() {            // most recent instruction wins
            if let e = explicitLanguageRequest(in: t) { return e }
        }
        // 3. substantive Story text
        let joined = substantiveTexts.joined(separator: "\n")
        if let d = dominantLanguage(of: joined) { return d }
        // 4. app language
        return appLanguage.contentLanguage
    }

    /// Dominant language of `text`, or nil when there is not enough signal.
    /// Han characters carry roughly 1.5× the content of a Latin word, so compare Han characters with Latin WORDS.
    static func dominantLanguage(of text: String) -> ContentLanguage? {
        let (han, latinLetters, latinWords) = counts(text)
        let enough = han >= minHan || latinLetters >= minLatinLetters
        guard enough else { return nil }
        if han == 0 { return .en }
        if latinLetters == 0 { return .zhHans }
        return han >= latinWords ? .zhHans : .en
    }

    /// Han characters, Latin letters, Latin words. URLs/emails are stripped first so a pasted link cannot sway it.
    static func counts(_ text: String) -> (han: Int, latinLetters: Int, latinWords: Int) {
        let cleaned = stripLinks(text)
        var han = 0, letters = 0, words = 0
        var inWord = false
        for u in cleaned.unicodeScalars {
            if isHan(u) { han += 1; inWord = false }
            else if (u.value >= 0x41 && u.value <= 0x5A) || (u.value >= 0x61 && u.value <= 0x7A) {
                letters += 1
                if !inWord { words += 1; inWord = true }
            } else { inWord = false }
        }
        return (han, letters, words)
    }

    static func isHan(_ u: Unicode.Scalar) -> Bool {
        (u.value >= 0x4E00 && u.value <= 0x9FFF) || (u.value >= 0x3400 && u.value <= 0x4DBF) ||
        (u.value >= 0xF900 && u.value <= 0xFAFF) || (u.value >= 0x20000 && u.value <= 0x2A6DF)
    }

    private static func stripLinks(_ s: String) -> String {
        s.replacingOccurrences(of: #"https?://\S+|\S+@\S+\.\S+"#, with: " ", options: .regularExpression)
    }

    /// "Please answer in English" / "用中文" / "请用英文" … → the requested language.
    static func explicitLanguageRequest(in text: String) -> ContentLanguage? {
        let t = text.lowercased()
        let zhPatterns = [#"\b(in|into|using)\s+(simplified\s+)?(chinese|mandarin)\b"#,
                          #"(用|使用|请用|请使用|以|改用|换成|翻译成|翻译为)\s*(简体)?(中文|汉语|普通话|国语)"#]
        let enPatterns = [#"\b(in|into|using)\s+english\b"#, #"\banswer\s+in\s+english\b"#,
                          #"(用|使用|请用|请使用|以|改用|换成|翻译成|翻译为)\s*(英文|英语)"#]
        let zh = zhPatterns.contains { t.range(of: $0, options: .regularExpression) != nil }
        let en = enPatterns.contains { t.range(of: $0, options: .regularExpression) != nil }
        if zh == en { return nil }   // none, or contradictory
        return zh ? .zhHans : .en
    }
}

// MARK: - Request value (what is actually sent as `content_language`)

extension ContentLanguageResolver {
    /// The `content_language` request value, or nil to leave the backend at its default.
    ///
    /// Policy: send "zh-Hans" when the resolved language is Chinese. When it resolves to English, send "en" ONLY if
    /// some of the text contains Chinese (so a Chinese note inside an English Story cannot flip the output); a
    /// pure-English Story sends nothing, so the English request — prompt, cache key, idempotency key — is
    /// byte-identical to the pre-localization behaviour.
    static func requestValue(explicitRequestIn: [String] = [], substantiveTexts: [String],
                             appLanguage: ResolvedLanguage = L10n.current) -> String? {
        let resolved = resolve(explicitRequestIn: explicitRequestIn, substantiveTexts: substantiveTexts,
                               appLanguage: appLanguage)
        if resolved == .zhHans { return ContentLanguage.zhHans.rawValue }
        let anyHan = (explicitRequestIn + substantiveTexts).contains { counts($0).han > 0 }
        return anyHan ? ContentLanguage.en.rawValue : nil
    }

    /// Story-derived value. `instruction` (the latest user instruction) is checked for an explicit language request
    /// and also counts as substantive text; `eventContext` likewise.
    static func requestValue(for story: StoryModel, instruction: String? = nil, eventContext: String? = nil,
                             appLanguage: ResolvedLanguage = L10n.current) -> String? {
        let instr = (instruction ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let ctx = (eventContext ?? story.eventContext ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let texts = [story.title, story.intentRawText, story.creativeDirectionText ?? "", ctx, instr]
        return requestValue(explicitRequestIn: instr.isEmpty ? [] : [instr], substantiveTexts: texts,
                            appLanguage: appLanguage)
    }

    /// Capture-context value (Shooting Idea / Director). Standalone captures use the optional direction text.
    static func requestValue(for context: CaptureContext, appLanguage: ResolvedLanguage = L10n.current) -> String? {
        switch context {
        case .story(let s):
            return requestValue(for: s, appLanguage: appLanguage)
        case .standalone(let direction):
            return requestValue(substantiveTexts: [direction ?? ""], appLanguage: appLanguage)
        }
    }
}
