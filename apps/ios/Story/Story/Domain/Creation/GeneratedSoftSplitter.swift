import Foundation

// GeneratedSoftSplitter — separates sentences the APP generated from the user's own words.
//
// The saved Customize draft text (StoryModel.creativeDirectionText) is the planner's FULL soft direction: the
// user's text PLUS sentences Customize appended (soft quick shortcuts such as "Prefer shorter, punchier shots",
// and the Mood preset phrase such as "Give it a cinematic feel"). Re-opening Customize used to drop all of it
// into the text box, so generated sentences were fed back through the AI interpreter as if the user had typed
// them. The interpreter sometimes files a pacing/music sentence under "unsupported", which blocked Create with a
// misleading clarify message. This splits them back out: generated sentences restore as toggles / the Mood row,
// and only the user's own words remain as text.
//
// Matching is EXACT on the known generated phrases (case-insensitive, ignoring surrounding whitespace and a
// trailing period) — a sentence the user wrote that merely resembles one is kept untouched.

enum GeneratedSoftSplitter {

    struct Result: Equatable {
        /// The user's own words, with every generated sentence removed. "" when nothing user-authored remains.
        var userText: String
        /// The generated phrases (as passed in, un-normalized) that were found and removed.
        var matched: Set<String>
    }

    static func split(_ text: String, generated: [String]) -> Result {
        func norm(_ s: String) -> String {
            var t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            while t.hasSuffix(".") { t.removeLast() }
            return t.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        }
        let byNorm = Dictionary(generated.filter { !$0.isEmpty }.map { (norm($0), $0) },
                                uniquingKeysWith: { first, _ in first })
        var kept: [String] = []
        var matched = Set<String>()
        // Sentences are joined with ". " everywhere the app appends; split on the same separator.
        for piece in text.components(separatedBy: ". ") {
            if let g = byNorm[norm(piece)] { matched.insert(g) } else { kept.append(piece) }
        }
        let user = kept.joined(separator: ". ").trimmingCharacters(in: .whitespacesAndNewlines)
        return Result(userText: user, matched: matched)
    }
}
