import Foundation

// ServerMessageLocalizer — presentation-only mapping for the human-readable strings the edit interpreter returns
// (`blocking` reasons and server-added `unresolved` clauses). Their wording is the server's contract and is NOT
// changed; this only decides what a Chinese-UI user sees. English UI: the text passes through byte-identical.
//
// Rule: localization must never HIDE an actionable detail.
//   • Known server templates (packages/edit_planner preflight_directives, revision_interpreter grounding/mapping)
//     map to natural Chinese that KEEPS the detail: which Moment (an internal id is replaced by the Moment's
//     display number from the caller's numbering snapshot — "第 3 个瞬间"), and how many Moments remain.
//   • An id the snapshot cannot resolve becomes "某个瞬间" (the raw UUID is not actionable for a user).
//   • An UNKNOWN English `blocking` reason is shown as one Chinese lead-in FOLLOWED BY the original server text,
//     so nothing is lost.
//   • `unresolved` clauses are usually the user's own words and are never rewritten (see presentUnresolved).
enum ServerMessageLocalizer {
    /// A `blocking` reason (server-authored).
    static func present(_ message: String, numbering: StoryMomentNumbering? = nil,
                        language: ResolvedLanguage = L10n.current) -> String {
        render(message, numbering: numbering, language: language, serverAuthored: true)
    }

    /// `unresolved` clauses: only the server's own "Moment N is not in this Story" template is localized; any other
    /// clause is the user's verbatim text (in any language) and is returned unchanged.
    static func presentUnresolved(_ messages: [String], language: ResolvedLanguage = L10n.current) -> [String] {
        messages.map { render($0, numbering: nil, language: language, serverAuthored: false) }
    }

    private static func render(_ message: String, numbering: StoryMomentNumbering?, language: ResolvedLanguage,
                               serverAuthored: Bool) -> String {
        guard language == .zhHans else { return message }
        if message.unicodeScalars.contains(where: ContentLanguageResolver.isHan) { return message }

        // "Moment 7 is not in this Story" (interpreter number mapping) keeps its number.
        if let g = groups(message, #"^Moment (\d+) is not in this Story"#), let n = Int(g[0]) {
            return L10n.t("Moment \(n) doesn't exist in this Story.", in: language)
        }
        guard serverAuthored else { return message }

        func name(_ raw: String) -> String {
            if let id = UUID(uuidString: raw), let n = numbering?.number(forId: id) {
                return L10n.momentInSentence(n, in: language)
            }
            if let n = Int(raw) { return L10n.momentInSentence(n, in: language) }
            return L10n.t("a Moment", in: language)
        }
        let id = "'([^']+)'"
        if message.lowercased().hasPrefix("unsupported_exclude") {
            return L10n.t("Your request only says which Moments to use or how to order them, but the result would remove some. Say which Moments to remove, or rephrase.", in: language)
        }
        if let g = groups(message, "^Moment \(id) is not in this Story") {
            return L10n.t("\(name(g[0])) isn't in this Story.", in: language)
        }
        if let g = groups(message, "^Moment \(id) is both required and excluded") {
            return L10n.t("\(name(g[0])) is asked to be both kept and removed.", in: language)
        }
        if let g = groups(message, #"leaves only (\d+) to build from"#), let n = Int(g[0]) {
            return L10n.t("Removing those Moments leaves only \(n) to build from. Keep at least 2.", in: language)
        }
        if let g = groups(message, "^Moment \(id) is excluded but also used in an ordering") {
            return L10n.t("\(name(g[0])) is removed but also used in your ordering.", in: language)
        }
        if let g = groups(message, "^Contradictory ordering between Moment \(id) and \(id)") {
            return L10n.t("The ordering of \(name(g[0])) and \(name(g[1])) contradicts itself.", in: language)
        }
        if let g = groups(message, "^Moment \(id) can't immediately follow more than one Moment") {
            return L10n.t("\(name(g[0])) can't come right after several Moments.", in: language)
        }
        if let g = groups(message, "^More than one Moment can't each immediately follow Moment \(id)") {
            return L10n.t("Several Moments can't all come right after \(name(g[0])).", in: language)
        }
        if let g = groups(message, "^Moment \(id) is set as the opening but also ordered after") {
            return L10n.t("\(name(g[0])) is the opening but is also placed after another Moment.", in: language)
        }
        if let g = groups(message, "^Moment \(id) is set as the ending but another Moment is ordered after it") {
            return L10n.t("\(name(g[0])) is the ending but another Moment is placed after it.", in: language)
        }
        // Unknown English reason: never hide it.
        return L10n.t("This request has a conflict. Please adjust it and try again. (\(message))", in: language)
    }

    private static func groups(_ s: String, _ pattern: String) -> [String]? {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
              let m = re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) else { return nil }
        let ns = s as NSString
        return (1..<max(m.numberOfRanges, 1)).compactMap { i in
            let r = m.range(at: i); return r.location == NSNotFound ? nil : ns.substring(with: r)
        }
    }
}
