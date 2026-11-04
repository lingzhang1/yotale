import Foundation

// ShotReferenceQuery — Phase 1A deterministic Unsplash search-query builder for the live-camera
// Shooting Idea card.
//
// WHY THIS EXISTS (owner §6): a visually impressive but IRRELEVANT photo is worse than no photo. The
// reference image must match the SUGGESTED SHOT, so we must NOT search Unsplash with the raw
// AI-generated paragraph (it is long, personal, and semantically noisy). Instead we build a SHORT,
// GENERIC, composition-first phrase from fields the Director already produced — with NO new model call.
//
// GROUNDING / PRIVACY SAFEGUARDS (owner §6):
//   * Pure + deterministic. No inference, no network, no randomness.
//   * Uses ONLY a bounded shot-composition vocabulary + already-generic Director fields
//     (framing / cameraMotion / subjectAction) and a lightly keyword-extracted title.
//   * NEVER emits a raw free-form instruction/summary, a URL, an email, user media, personal names,
//     private descriptions, or camera-frame content.
//   * Output is a handful of generic keywords suitable for stock-image discovery, mirroring the
//     Guide `visual_reference_query` convention. The backend ALSO re-sanitizes + hard-bounds it.
//
// MATCHING PRIORITY (owner §6, in order): 1) shot composition / perspective, 2) main subject category,
// 3) environment / scene type, 4) mood when relevant. The builder layers these, composition first.
//
// The vocabulary is a LIMITED pattern set, NOT a hardcoded mapping for every possible idea. When no
// confident composition/subject signal is present, the builder returns nil => the card shows text-only
// (owner: "No confident match -> no image", never a decorative/placeholder photo).
enum ShotReferenceQuery {

    /// Build a generic stock-photo search phrase for a Director shot idea, or nil when there is no
    /// confident, grounded signal (=> text-only card, never a random placeholder).
    ///
    /// - Parameters:
    ///   - shot:    the Director's ShotContractDTO (framing / cameraMotion / subjectAction / instruction).
    ///   - conceptTitle:   the Director concept title (generic scene label, e.g. "A Quiet Moment at Work").
    ///   - conceptSummary: the Director concept summary (generic one-liner; used only for scene-type hints).
    static func build(shot: ShotContractDTO?,
                      conceptTitle: String?,
                      conceptSummary: String?) -> String? {
        var tokens: [String] = []

        // 1) COMPOSITION / PERSPECTIVE — highest priority. Prefer the Director's explicit framing field;
        //    otherwise infer a composition pattern from a bounded keyword scan of framing + instruction.
        let compositionText = [shot?.framing, shot?.cameraMotion, shot?.instruction]
            .compactMap { $0 }.joined(separator: " ")
        if let comp = compositionPattern(from: compositionText) {
            tokens.append(contentsOf: comp)
        }

        // 2) MAIN SUBJECT CATEGORY — from the Director's subjectAction (already generic), else inferred
        //    from the title/instruction via a bounded subject vocabulary.
        let subjectText = [shot?.subjectAction, conceptTitle, shot?.instruction]
            .compactMap { $0 }.joined(separator: " ")
        if let subj = subjectCategory(from: subjectText) {
            tokens.append(contentsOf: subj)
        }

        // 3) ENVIRONMENT / SCENE TYPE — from title + summary via a bounded environment vocabulary.
        let envText = [conceptTitle, conceptSummary].compactMap { $0 }.joined(separator: " ")
        if let env = environmentType(from: envText), !tokens.contains(env) {
            tokens.append(env)
        }

        // 4) MOOD — only when clearly signaled and only one word, to avoid steering toward irrelevant art.
        if let mood = moodHint(from: envText), tokens.count < 5 {
            tokens.append(mood)
        }

        // Dedup (preserve order), bound to a handful of keywords, and require a real composition OR
        // subject signal — otherwise there is nothing grounded to search for.
        let deduped = dedupPreservingOrder(tokens)
        guard hasGroundedSignal(deduped) else { return nil }
        let phrase = deduped.prefix(6).joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return phrase.isEmpty ? nil : phrase
    }

    // MARK: - Bounded vocabularies (limited pattern set, not a per-idea mapping)

    /// Composition / camera-perspective patterns -> generic stock keywords. Matched against lowercased
    /// framing/motion/instruction text. First match wins (most specific listed first).
    private static let compositionPatterns: [(needles: [String], keywords: [String])] = [
        (["close-up", "close up", "closeup", "macro", "detail"], ["close up", "detail"]),
        (["overhead", "top down", "top-down", "flat lay", "flatlay", "bird"], ["overhead", "flat lay"]),
        (["wide", "landscape", "establishing", "vista", "panorama"], ["wide", "landscape"]),
        (["symmetr", "corridor", "aisle", "leading line", "hallway", "perspective"], ["symmetrical", "leading lines"]),
        (["low angle", "low-angle", "looking up"], ["low angle"]),
        (["high angle", "high-angle", "looking down"], ["high angle"]),
        (["over the shoulder", "over-the-shoulder", "back view", "from behind"], ["back view"]),
        (["portrait", "headshot", "face"], ["portrait"]),
        (["pan ", "panning", "tracking", "follow"], ["motion"]),
    ]

    private static func compositionPattern(from text: String) -> [String]? {
        let t = text.lowercased()
        for pat in compositionPatterns where pat.needles.contains(where: { t.contains($0) }) {
            return pat.keywords
        }
        return nil
    }

    /// Main-subject categories -> generic keywords. Bounded; first match wins.
    private static let subjectPatterns: [(needles: [String], keywords: [String])] = [
        (["keyboard", "laptop", "typing", "desk", "workspace", "office", "computer"], ["workspace", "hands keyboard"]),
        (["cook", "food", "kitchen", "meal", "baking", "recipe", "chef"], ["food preparation", "hands"]),
        (["walk", "stroll", "hike", "trail", "running", "jog"], ["walking subject"]),
        (["mountain", "summit", "peak", "ridge", "alpine"], ["mountain"]),
        (["beach", "ocean", "sea", "coast", "shore", "wave"], ["coast"]),
        (["forest", "woods", "tree", "trail", "park", "garden"], ["nature"]),
        (["coffee", "cup", "mug", "tea", "cafe"], ["coffee cup"]),
        (["child", "kid", "baby", "toddler"], ["child"]),
        (["dog", "cat", "pet", "animal"], ["pet"]),
        (["flower", "plant", "bloom", "bouquet"], ["flowers"]),
        (["hand", "hands", "fingers"], ["hands"]),
        (["face", "portrait", "smile", "expression"], ["portrait"]),
        (["street", "city", "urban", "building"], ["street"]),
        (["book", "reading", "page", "notebook"], ["reading"]),
        (["window", "light", "sunlight", "golden hour"], ["window light"]),
    ]

    private static func subjectCategory(from text: String) -> [String]? {
        let t = text.lowercased()
        for pat in subjectPatterns where pat.needles.contains(where: { t.contains($0) }) {
            return pat.keywords
        }
        return nil
    }

    /// Environment / scene type -> single generic keyword.
    private static let environmentPatterns: [(needles: [String], keyword: String)] = [
        (["office", "desk", "work", "meeting"], "office"),
        (["kitchen", "cooking", "dining"], "kitchen"),
        (["outdoor", "outside", "mountain", "trail", "beach", "park", "nature"], "outdoor"),
        (["home", "living room", "bedroom", "indoor", "interior"], "indoor"),
        (["city", "street", "urban", "downtown"], "urban"),
    ]

    private static func environmentType(from text: String) -> String? {
        let t = text.lowercased()
        for pat in environmentPatterns where pat.needles.contains(where: { t.contains($0) }) {
            return pat.keyword
        }
        return nil
    }

    /// Mood (single word, optional). Only surfaced when explicitly signaled.
    private static let moodPatterns: [(needles: [String], keyword: String)] = [
        (["quiet", "calm", "peaceful", "serene", "still"], "calm"),
        (["warm", "cozy", "intimate"], "warm"),
        (["bright", "vibrant", "lively", "energetic"], "vibrant"),
        (["moody", "dramatic", "dark"], "moody"),
    ]

    private static func moodHint(from text: String) -> String? {
        let t = text.lowercased()
        for pat in moodPatterns where pat.needles.contains(where: { t.contains($0) }) {
            return pat.keyword
        }
        return nil
    }

    // MARK: - Helpers

    private static func dedupPreservingOrder(_ tokens: [String]) -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        for raw in tokens {
            let t = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !t.isEmpty, !seen.contains(t) else { continue }
            seen.insert(t)
            out.append(t)
        }
        return out
    }

    /// A query is only worth sending if it carries a real composition OR subject signal. Environment/mood
    /// alone is too weak to return a RELEVANT photo (owner: conservative matching, omit rather than guess).
    private static func hasGroundedSignal(_ tokens: [String]) -> Bool {
        let weakOnly: Set<String> = ["office", "kitchen", "outdoor", "indoor", "urban",
                                     "calm", "warm", "vibrant", "moody"]
        return tokens.contains { !weakOnly.contains($0) }
    }
}
