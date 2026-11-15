import Foundation

// ServerMessageLocalizer — presentation-only mapping for the few human-readable strings the edit interpreter
// returns (`blocking` reasons and server-added `unresolved` clauses). Their wording is the server's contract and is
// NOT changed; this only decides what a Chinese-UI user sees. English UI: the text passes through byte-identical.
//
// Known server templates (packages/edit_planner preflight_directives, revision_interpreter grounding/mapping) map
// to natural Chinese WITHOUT the internal Moment ids some of them embed. Anything unrecognised that is plainly
// English `blocking` reason falls back to one generic, honest Chinese line, so a Chinese UI never shows a raw
// English reason. `unresolved` clauses are the user's own words and are never rewritten (see presentUnresolved).
enum ServerMessageLocalizer {
    /// A `blocking` reason (always server-authored).
    static func present(_ message: String, language: ResolvedLanguage = L10n.current) -> String {
        present(message, language: language, serverAuthored: true)
    }

    /// `unresolved` clauses are usually the USER'S OWN words quoted back (in any language) and must never be
    /// replaced; only the server's own "Moment N is not in this Story" template is localized.
    static func presentUnresolved(_ messages: [String], language: ResolvedLanguage = L10n.current) -> [String] {
        messages.map { present($0, language: language, serverAuthored: false) }
    }

    private static func present(_ message: String, language: ResolvedLanguage, serverAuthored: Bool) -> String {
        guard language == .zhHans else { return message }
        if containsHan(message) { return message }
        let m = message.lowercased()
        // "Moment 7 is not in this Story" (interpreter id mapping) keeps its number.
        if let r = message.range(of: #"^Moment (\d+) is not in this Story"#, options: .regularExpression),
           let n = Int(message[r].split(separator: " ")[1]) {
            return L10n.t("Moment \(n) doesn't exist in this Story.", in: language)
        }
        guard serverAuthored else { return message }
        for (needle, key) in table where m.contains(needle) {
            return L10n.t(key, in: language)
        }
        return L10n.t("This request has a conflict. Please adjust it and try again.", in: language)
    }

    /// Ordered: the first matching needle wins (more specific first).
    private static let table: [(String, String.LocalizationValue)] = [
        ("unsupported_exclude", "Your request only says which Moments to use or how to order them, but the result would remove some. Say which Moments to remove, or rephrase."),
        ("is not in this story", "A Moment you mentioned isn't in this Story."),
        ("both required and excluded", "The same Moment is asked to be both kept and removed."),
        ("keep at least 2", "Removing those Moments leaves too little to make a video. Keep at least 2."),
        ("excluded but also used in an ordering", "A removed Moment is also used in your ordering."),
        ("contradictory ordering", "The ordering in your request contradicts itself."),
        ("can't immediately follow more than one", "One Moment can't come right after several others."),
        ("can't each immediately follow", "Several Moments can't all come right after the same one."),
        ("set as the opening but also ordered after", "The opening Moment is also placed after another Moment."),
        ("set as the ending but another moment is ordered after", "The ending Moment has another Moment placed after it."),
    ]

    private static func containsHan(_ s: String) -> Bool {
        s.unicodeScalars.contains { ContentLanguageResolver.isHan($0) }
    }
}
