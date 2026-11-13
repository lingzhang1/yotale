import Foundation

// Explicit Moment References — the SHARED resolution core used by BOTH pre-creation Creative Direction and
// post-generation Natural-Language Revision. Pure value types, no SwiftData / no UI, so it is unit-testable
// and there is exactly ONE parser + numbering + resolver implementation (owner rule: do not duplicate).
//
// RESPONSIBILITY (owner clarification #4): this maps user references -> stable Moment UUIDs. It does NOT judge
// whether the resulting EditPlan satisfies them — the backend `validate_plan` is the authority on satisfaction.
// Resolution success is NOT proof of correct event/source-range resolution (#5): event-level asks are carried
// as soft direction, never asserted as satisfied here.

/// One Story-scoped, display-numbered Moment. `number` is a 1-based display identifier (NOT a UUID, NOT global)
/// derived from the Story's visible ordering; `id` is the stable Moment UUID that is persisted and sent to the
/// planner.
struct NumberedMoment: Equatable {
    let number: Int
    let id: UUID
    let durationSeconds: Double
    /// Relative media path for the thumbnail (resolved to a URL by the UI via MediaStore). Nil-safe.
    let relativePath: String?
    /// Whether the ORIGINAL bytes are on THIS device right now. Cloud-only (evicted/not-yet-restored) Moments
    /// are still full members — they are shown + referenceable with a cloud badge, never hidden (owner P0).
    /// Defaulted true so every existing construction site (tests, revision) compiles unchanged.
    var localAvailable: Bool = true
}

/// A STABLE snapshot of a Story's Moment numbering, captured when the user opens Creative Direction or Revision.
/// Typed "Moment N" references resolve against THIS snapshot, so a later reorder/add cannot silently change the
/// meaning of an instruction the user already wrote (owner clarification #1). Build once; keep for the session.
struct StoryMomentNumbering: Equatable {
    let items: [NumberedMoment]          // ordered by display number (1..N), gap-free
    private let byNumber: [Int: UUID]
    private let byId: [UUID: Int]

    init(ordered moments: [NumberedMoment]) {
        // Re-stamp numbers 1..N from the given order so the snapshot is always gap-free and 1-based,
        // regardless of how the caller built the list.
        var items: [NumberedMoment] = []
        var byNumber: [Int: UUID] = [:]
        var byId: [UUID: Int] = [:]
        for (i, m) in moments.enumerated() {
            let n = i + 1
            let nm = NumberedMoment(number: n, id: m.id, durationSeconds: m.durationSeconds,
                                    relativePath: m.relativePath)
            items.append(nm); byNumber[n] = m.id; byId[m.id] = n
        }
        self.items = items; self.byNumber = byNumber; self.byId = byId
    }

    var count: Int { items.count }

    /// Resolve a display number to a stable Moment UUID, or nil if out of range.
    func id(forNumber n: Int) -> UUID? { byNumber[n] }

    /// The display number a stable id currently maps to in THIS snapshot (for rendering chips), or nil.
    func number(forId id: UUID) -> Int? { byId[id] }

    func contains(id: UUID) -> Bool { byId[id] != nil }
}

/// A single parsed reference and the directive slot it targets.
enum DirectiveSlot: Equatable { case include, exclude, opening, ending }

struct ParsedReference: Equatable {
    let slot: DirectiveSlot
    let number: Int          // the display number the user typed
    let matchedText: String  // the exact phrase matched (for chip insertion / UI feedback)
}

/// The resolved set of hard directives, keyed by STABLE Moment UUID — this is exactly the shape the backend
/// `revision_context.directives` contract expects (must_include / exclude / opening / ending).
struct ResolvedDirectives: Equatable {
    var mustInclude: [UUID] = []
    var exclude: [UUID] = []
    var opening: UUID? = nil
    var ending: UUID? = nil
    /// [after, before] pairs: `after` appears somewhere after `before`.
    var orderAfter: [[UUID]] = []
    /// [after, before] pairs: `after` appears IMMEDIATELY after `before`.
    var orderAdjacent: [[UUID]] = []

    var isEmpty: Bool {
        mustInclude.isEmpty && exclude.isEmpty && opening == nil && ending == nil
        && orderAfter.isEmpty && orderAdjacent.isEmpty
    }

    /// Encode to the backend wire shape (lowercased uuid strings). Omits empty slots so an absent directive is
    /// simply not present (behavior-unchanged on the backend).
    func wireDictionary() -> [String: Any] {
        // Directive ids MUST be lowercased to match the moments[] ids and segment asset_ids, which the
        // moments payload builder (StoryCreationCoordinator.momentsPayload) lowercases. The backend compares
        // directive ids against those ids; an UPPERCASE uuidString here never matches -> the opening/ending/
        // order directive is silently unenforced (every "new version" comes back as the same default edit).
        var d: [String: Any] = [:]
        if !mustInclude.isEmpty { d["must_include"] = mustInclude.map { $0.uuidString.lowercased() } }
        if !exclude.isEmpty { d["exclude"] = exclude.map { $0.uuidString.lowercased() } }
        if let o = opening { d["opening"] = o.uuidString.lowercased() }
        if let e = ending { d["ending"] = e.uuidString.lowercased() }
        if !orderAfter.isEmpty { d["order_after"] = orderAfter.map { $0.map { $0.uuidString.lowercased() } } }
        if !orderAdjacent.isEmpty { d["order_adjacent"] = orderAdjacent.map { $0.map { $0.uuidString.lowercased() } } }
        return d
    }

    /// Encode as a JSONValue `directives` object (the type the planner request carries). Nil when empty, so an
    /// absent directive set leaves the request byte-identical to today.
    func jsonValue() -> JSONValue? {
        if isEmpty { return nil }
        // Lowercase every id (see wireDictionary): moments[] ids + segment asset_ids are lowercased, so the
        // backend's directive enforcement only matches when directive ids are lowercase too.
        var o: [String: JSONValue] = [:]
        if !mustInclude.isEmpty { o["must_include"] = .array(mustInclude.map { .string($0.uuidString.lowercased()) }) }
        if !exclude.isEmpty { o["exclude"] = .array(exclude.map { .string($0.uuidString.lowercased()) }) }
        if let op = opening { o["opening"] = .string(op.uuidString.lowercased()) }
        if let en = ending { o["ending"] = .string(en.uuidString.lowercased()) }
        if !orderAfter.isEmpty {
            o["order_after"] = .array(orderAfter.map { .array($0.map { .string($0.uuidString.lowercased()) }) })
        }
        if !orderAdjacent.isEmpty {
            o["order_adjacent"] = .array(orderAdjacent.map { .array($0.map { .string($0.uuidString.lowercased()) }) })
        }
        return .object(o)
    }

    /// Decode persisted directives from the stored wire JSON (StoryModel.creativeDirectivesJSON).
    static func fromWireJSON(_ json: String?) -> ResolvedDirectives? {
        guard let json, let data = json.data(using: .utf8),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
        func ids(_ v: Any?) -> [UUID] { ((v as? [String]) ?? []).compactMap { UUID(uuidString: $0) } }
        func pairs(_ v: Any?) -> [[UUID]] {
            ((v as? [[String]]) ?? []).compactMap { p in
                let us = p.compactMap { UUID(uuidString: $0) }
                return us.count == 2 ? us : nil
            }
        }
        var d = ResolvedDirectives()
        d.mustInclude = ids(obj["must_include"])
        d.exclude = ids(obj["exclude"])
        d.opening = (obj["opening"] as? String).flatMap { UUID(uuidString: $0) }
        d.ending = (obj["ending"] as? String).flatMap { UUID(uuidString: $0) }
        d.orderAfter = pairs(obj["order_after"])
        d.orderAdjacent = pairs(obj["order_adjacent"])
        return d.isEmpty ? nil : d
    }

    /// Serialize to the persisted wire JSON string for StoryModel.creativeDirectivesJSON.
    func toWireJSON() -> String? {
        guard !isEmpty,
              let data = try? JSONSerialization.data(withJSONObject: wireDictionary()) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

/// A reference that could NOT be resolved — the user must clarify (owner: never silently substitute/drop).
struct UnresolvedReference: Equatable {
    enum Reason: Equatable { case numberOutOfRange(Int); case momentUnavailable(UUID) }
    let reason: Reason
    let matchedText: String
}

struct ResolutionResult: Equatable {
    var directives: ResolvedDirectives
    var unresolved: [UnresolvedReference]
    /// True when at least one reference failed to resolve — the UI must request clarification before submit.
    var needsClarification: Bool { !unresolved.isEmpty }
}

/// Narrowly-scoped MUSIC intent extracted from a Stage 2 Creative Direction string (owner Music-Routing §1/§3).
/// This is the SMALLEST additive extension to the existing deterministic interpreter — NOT a second parser
/// system and NOT an AI pass. It separates three disjoint concerns so each routes to the right consumer:
///   • `preference` — an EXPLICIT soundtrack preference (genre/mood words like "gentle acoustic",
///     "energetic electronic"). Routes to MusicPlan (MusicDirection). nil when no explicit music words appear.
///   • `beatSync` — "match the cuts to the music" / "sync to the beat". Routes to the EDIT planner's
///     soft_direction only; it must NOT change soundtrack selection (§1, test 2).
/// Generic VISUAL language ("make the cuts faster", "most striking footage") produces NEITHER — never a music
/// preference (§3: no fabrication from visual language).
struct ParsedMusicIntent: Equatable {
    /// An explicit soundtrack preference phrase + the mood tags it maps to (lowercased). nil => no music words.
    var preference: (phrase: String, moodTags: [String])?
    /// True when the user asked to align the edit to the music/beat (edit-side only; no track change).
    var beatSync: Bool

    static func == (l: ParsedMusicIntent, r: ParsedMusicIntent) -> Bool {
        l.beatSync == r.beatSync && l.preference?.phrase == r.preference?.phrase
            && l.preference?.moodTags == r.preference?.moodTags
    }
    var isEmpty: Bool { preference == nil && !beatSync }
}

enum MomentReferenceResolver {
    // Narrow, EXPLICIT music vocabulary (owner §3: no fabrication from generic visual language). Each entry is
    // a soundtrack genre/mood the user can name; mapped to lowercased mood tags that MusicDirection understands.
    // Deliberately small and musical — "cinematic", "acoustic", "electronic", etc. — so a visual word like
    // "faster"/"striking" never produces a music preference.
    private static let musicVocabulary: [(word: String, moods: [String])] = [
        ("acoustic", ["acoustic", "intimate"]), ("gentle", ["calm", "gentle"]), ("soft", ["calm"]),
        ("calm", ["calm"]), ("mellow", ["calm"]), ("ambient", ["atmospheric"]), ("atmospheric", ["atmospheric"]),
        ("cinematic", ["cinematic"]), ("epic", ["epic"]), ("dramatic", ["cinematic", "epic"]),
        ("emotional", ["emotional"]), ("uplifting", ["uplifting"]), ("dreamy", ["dreamy"]),
        ("energetic", ["energetic"]), ("upbeat", ["energetic"]), ("high energy", ["energetic"]),
        ("electronic", ["electronic", "energetic"]), ("edm", ["electronic", "energetic"]),
        ("hip hop", ["hip hop"]), ("hip-hop", ["hip hop"]), ("rock", ["rock"]), ("pop", ["pop"]),
        ("jazz", ["jazz"]), ("classical", ["classical"]), ("orchestral", ["orchestral", "cinematic"]),
        ("folk", ["folk", "acoustic"]), ("piano", ["piano"]), ("guitar", ["acoustic"]),
        // 简体中文 vocabulary (additive)
        ("原声", ["acoustic", "intimate"]), ("轻柔", ["calm", "gentle"]), ("舒缓", ["calm"]), ("平静", ["calm"]),
        ("氛围", ["atmospheric"]), ("电影感", ["cinematic"]), ("史诗", ["epic"]), ("感人", ["emotional"]),
        ("温暖", ["emotional"]), ("治愈", ["calm", "gentle"]), ("梦幻", ["dreamy"]), ("热血", ["energetic"]),
        ("活力", ["energetic"]), ("动感", ["energetic"]), ("欢快", ["energetic"]), ("电子", ["electronic", "energetic"]),
        ("嘻哈", ["hip hop"]), ("摇滚", ["rock"]), ("流行", ["pop"]), ("爵士", ["jazz"]), ("古典", ["classical"]),
        ("钢琴", ["piano"]), ("吉他", ["acoustic"]), ("民谣", ["folk", "acoustic"]),
    ]

    /// Classify the Stage 2 free text into disjoint music concerns WITHOUT a second AI pass (owner §3). An
    /// EXPLICIT music preference requires a music CONTEXT word ("music"/"soundtrack"/"song"/"track"/"beat"/
    /// "tune") in the sentence AND a vocabulary word — so "energetic MUSIC" is a preference but a bare
    /// "energetic opening" (visual) is not (§3: no fabrication from visual language). Beat-sync is detected
    /// separately and never implies a track change (§1, test 2).
    static func parseMusicIntent(_ text: String) -> ParsedMusicIntent {
        let lower = text.lowercased()
        guard !lower.isEmpty else { return ParsedMusicIntent(preference: nil, beatSync: false) }
        // Beat-sync / "match the music": edit-side alignment only. Covers "match ... (to the) music/beat",
        // "sync to the beat", "on the beat", "to the music", "match the cuts".
        let beatSync = ["match the music", "match to the music", "to the music", "match the cuts",
                        "match cuts", "to the beat", "on the beat", "sync to", "beat sync", "beat-sync",
                        "match the beat", "hit the beat",
                        // 简体中文: 卡点 / 踩点 / 跟着音乐剪 / 配合音乐节奏
                        "卡点", "踩点", "跟着音乐", "跟随音乐", "配合音乐", "随音乐", "音乐节奏", "跟着节拍", "跟着鼓点"].contains { lower.contains($0) }
        // Music preference requires an explicit music-context word so visual language can never be mistaken.
        let hasMusicContext = ["music", "soundtrack", "song", "track", "tune", "score", "音乐", "配乐", "歌曲", "背景乐"].contains { lower.contains($0) }
        var preference: (phrase: String, moodTags: [String])? = nil
        if hasMusicContext {
            var moods: [String] = []
            var matched: [String] = []
            for entry in musicVocabulary where lower.contains(entry.word) {
                matched.append(entry.word)
                for m in entry.moods where !moods.contains(m) { moods.append(m) }
            }
            if !moods.isEmpty {
                preference = (phrase: matched.joined(separator: " "), moodTags: moods)
            }
        }
        return ParsedMusicIntent(preference: preference, beatSync: beatSync)
    }

    // MARK: Chinese (简体中文) reference support — additive; English patterns above are untouched.
    // A Chinese Moment reference: 片段8 / 片段 8 / 片段#8 / 片段八 / 第8个片段 / 第八段 / 第８段 (full-width digits,
    // Chinese numerals 一…九十九 and 两 are accepted). Each form has ONE capture group (see `capturedNumbers`).
    private static let zhNum = "[0-9０-９一二三四五六七八九十两]+"
    private static let zhRef = "(?:片段\\s*#?\\s*(\(zhNum))|第\\s*(\(zhNum))\\s*(?:个\\s*片段|段|片段))"

    private static var chinesePatterns: [(DirectiveSlot, String)] {
        let r = zhRef
        return [
            // OPENING — 从片段8开始 / 以片段8开头 / 以片段8为开头 / 用片段8开头 / 片段8放在开头 / 片段8作为开场
            (.opening, "从\\s*\(r)\\s*(?:开始|开头|起)"),
            (.opening, "(?:以|用|拿|让)\\s*\(r)\\s*(?:来\\s*)?(?:作为|做|当)?\\s*(?:为\\s*)?(?:开头|开场|开始|第一个)"),
            (.opening, "\(r)\\s*(?:放|排|安排)?\\s*(?:在|到)?\\s*(?:最\\s*前面?|开头|最开始|第一个?|最先)"),
            (.opening, "\(r)\\s*(?:作为|做|当)\\s*(?:开头|开场)"),
            // ENDING — 以片段8结尾 / 以片段8为结尾 / 到片段8结束 / 片段8放在最后 / 最后用片段8
            (.ending, "(?:以|用|让)\\s*\(r)\\s*(?:来\\s*)?(?:作为|做|当)?\\s*(?:为\\s*)?(?:结尾|收尾|结束|压轴)"),
            (.ending, "(?:到|在)\\s*\(r)\\s*(?:结束|结尾|收尾)"),
            (.ending, "\(r)\\s*(?:放|排|安排)?\\s*(?:在|到)?\\s*(?:最\\s*后面?|结尾|最末|最后一个?)"),
            (.ending, "\(r)\\s*(?:作为|做|当)\\s*(?:结尾|收尾)"),
            (.ending, "最后\\s*(?:用|放|是|选|加)?\\s*\(r)"),
            // EXCLUDE — 不要用片段3 / 去掉片段3 / 删除 / 删掉 / 跳过 / 不用 / 排除
            (.exclude, "(?:不要用|不要使用|别用|不用|不使用|不要|去掉|去除|删除|删掉|移除|跳过|排除|略过|舍弃)\\s*\(r)"),
            // INCLUDE (lowest priority)
            (.include, "(?:包含|包括|使用|加入|添加|保留|加上|必须用|一定要用|用)\\s*\(r)"),
        ]
    }

    /// All Moment numbers captured by a match (in text order), accepting ASCII / full-width digits and Chinese
    /// numerals. Works for the English patterns too (their single group is plain `\d+`).
    private static func capturedNumbers(_ m: NSTextCheckingResult, in ns: NSString) -> [Int] {
        var out: [Int] = []
        guard m.numberOfRanges > 1 else { return out }
        for i in 1..<m.numberOfRanges {
            let r = m.range(at: i)
            if r.location != NSNotFound, let n = parseNumber(ns.substring(with: r)) { out.append(n) }
        }
        return out
    }

    /// Parse "8", "８", "八", "十", "十二", "二十", "二十三", "两" (1…99 for numerals; any digit run for digits).
    static func parseNumber(_ raw: String) -> Int? {
        let s = raw.trimmingCharacters(in: .whitespaces)
        guard !s.isEmpty else { return nil }
        // Digits (ASCII or full-width): fold full-width to ASCII.
        var ascii = ""
        var allDigits = true
        for ch in s.unicodeScalars {
            if ch.value >= 0xFF10 && ch.value <= 0xFF19 {
                ascii.unicodeScalars.append(Unicode.Scalar(ch.value - 0xFF10 + 0x30)!)
            } else if ch.value >= 0x30 && ch.value <= 0x39 {
                ascii.unicodeScalars.append(ch)
            } else { allDigits = false; break }
        }
        if allDigits { return Int(ascii) }
        let digit: [Character: Int] = ["一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                                       "六": 6, "七": 7, "八": 8, "九": 9]
        let chars = Array(s)
        if chars.count == 1 {
            if chars[0] == "十" { return 10 }
            return digit[chars[0]]
        }
        guard let tenIdx = chars.firstIndex(of: "十") else { return nil }
        let tensPart = chars[..<tenIdx], onesPart = chars[(tenIdx + 1)...]
        guard tensPart.count <= 1, onesPart.count <= 1 else { return nil }
        let tens = tensPart.first.flatMap { digit[$0] } ?? (tensPart.isEmpty ? 1 : nil)
        let ones = onesPart.first.flatMap { digit[$0] } ?? (onesPart.isEmpty ? 0 : nil)
        guard let t = tens, let o = ones else { return nil }
        return t * 10 + o
    }

    /// Parse typed "Moment N" references from free text. Deterministic, order-preserving. Recognizes the four
    /// supported forms (owner #3): include / exclude / start-with (opening) / end-with (ending). Anything not
    /// matching a supported pattern is left for the planner as free text (soft direction) — NOT invented.
    static func parseTyped(_ text: String) -> [ParsedReference] {
        guard !text.isEmpty else { return [] }
        // Verb cues -> slot, HIGHEST priority first (an earlier match claims its char range so a lower
        // pattern cannot re-match the same words — this is what stops "start WITH moment 5" also matching the
        // bare include "with moment 5"). Covers natural phrasings: "start with M5" / "use M5 to start" /
        // "M5 to start" / "open on M5" for opening; "end with M8" / "M8 at the end" / "finish on M8" for
        // ending; include/exclude verbs. Anything unmatched stays free-text soft direction (never invented).
        let patterns: [(DirectiveSlot, String)] = [
            // OPENING — verb-before-number ("start with / open on / begin with moment 5")
            (.opening, #"(?:start|open|begin|lead)(?:ing)?\s+(?:with|from|on|off\s+with)?\s*moment\s+#?(\d+)"#),
            // OPENING — number-before-cue ("use moment 5 to start", "moment 5 first", "moment 5 to open")
            (.opening, #"moment\s+#?(\d+)\s+(?:to\s+)?(?:start|open|begin|first|lead|up\s+front|at\s+the\s+(?:start|beginning)|as\s+the\s+(?:opening|first))"#),
            // ENDING — verb-before-number ("end with / finish on / close with moment 8")
            (.ending,  #"(?:end|finish|close)(?:ing)?\s+(?:with|on)?\s*moment\s+#?(\d+)"#),
            // ENDING — number-before-cue ("put moment 8 at the end", "moment 8 last", "moment 8 to end")
            (.ending,  #"moment\s+#?(\d+)\s+(?:to\s+)?(?:at\s+the\s+end|last|to\s+end|to\s+finish|as\s+the\s+(?:ending|last|finale))"#),
            (.ending,  #"put\s+moment\s+#?(\d+)\s+(?:at\s+the\s+end|last)"#),
            // EXCLUDE
            (.exclude, #"(?:exclude|do\s*n[o']?t\s+use|don[o']?t\s+use|remove|drop|skip|without|leave\s+out)\s+moment\s+#?(\d+)"#),
            // INCLUDE (lowest priority; NOT a bare "with" — that over-matched "start with")
            (.include, #"(?:include|use|add|keep|feature)\s+moment\s+#?(\d+)"#),
        ] + chinesePatterns
        let ns = text as NSString
        var claimed = IndexSet()  // character ranges already consumed by a higher-priority pattern
        var withPos: [(pos: Int, ref: ParsedReference)] = []
        for (slot, pat) in patterns {
            guard let re = try? NSRegularExpression(pattern: pat, options: [.caseInsensitive]) else { continue }
            for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
                let full = m.range(at: 0)
                // Skip if this span overlaps a region already claimed by an earlier (higher-priority) pattern.
                if (full.location..<(full.location + full.length)).contains(where: { claimed.contains($0) }) {
                    continue
                }
                guard let n = capturedNumbers(m, in: ns).first else { continue }
                withPos.append((full.location,
                                ParsedReference(slot: slot, number: n, matchedText: ns.substring(with: full))))
                for i in full.location..<(full.location + full.length) { claimed.insert(i) }
            }
        }
        // Return in order of appearance in the text.
        return withPos.sorted { $0.pos < $1.pos }.map { $0.ref }
    }

    /// Parse ORDERING relations between two typed Moment numbers. Returns (after, before, adjacent) triples:
    /// `after` should come after `before`; `adjacent` means immediately after. Deterministic, bounded to the
    /// clear phrasings — anything looser is left to the structured-AI interpretation step (Phase 2).
    ///   "start with M5 then M2"      -> (2, 5, adjacent)   ("then" = immediately next)
    ///   "M5, M2 follows"             -> (2, 5, adjacent)
    ///   "M2 immediately after M5"    -> (2, 5, adjacent)
    ///   "M2 right after M5"          -> (2, 5, adjacent)
    ///   "M2 after M5" / "M2 somewhere after M5" -> (2, 5, non-adjacent)
    static func parseOrdering(_ text: String) -> [(after: Int, before: Int, adjacent: Bool)] {
        guard !text.isEmpty else { return [] }
        let ns = text as NSString
        var out: [(Int, Int, Bool)] = []
        func scan(_ pattern: String, adjacent: Bool, swap: Bool = false) {
            guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return }
            for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
                let nums = capturedNumbers(m, in: ns)
                guard nums.count >= 2 else { continue }
                let x = nums[0], y = nums[1]
                // swap=false: first number is `after`? depends on pattern; callers set it so (after, before).
                let after = swap ? y : x
                let before = swap ? x : y
                out.append((after, before, adjacent))
            }
        }
        // "moment A immediately/right after moment B"  => A after B, adjacent
        scan(#"moment\s+#?(\d+)\s+(?:immediately|right|directly)\s+(?:after|following)\s+moment\s+#?(\d+)"#, adjacent: true)
        // "moment A after moment B" (plain / somewhere) => A after B, non-adjacent
        scan(#"moment\s+#?(\d+)\s+(?:somewhere\s+)?after\s+moment\s+#?(\d+)"#, adjacent: false)
        // "moment B, then moment A" / "moment B then A"  => A after B, adjacent  (swap: first is `before`)
        scan(#"moment\s+#?(\d+)\s*,?\s+then\s+(?:moment\s+)?#?(\d+)"#, adjacent: true, swap: true)
        // "moment B, moment A follows/next" => A after B, adjacent (swap: first is before)
        scan(#"moment\s+#?(\d+)[,\s]+(?:then\s+)?(?:moment\s+)?#?(\d+)\s+(?:follows?|follow|next|afterwards?|comes\s+next)"#, adjacent: true, swap: true)
        // Chinese: "片段A紧接在片段B之后" / "片段A在片段B之后" / "片段B，然后片段A" / "片段B接着片段A"
        let zr = zhRef
        scan("\(zr)\\s*(?:紧接着?|紧跟着?|立刻|马上|直接)\\s*(?:在)?\\s*\(zr)\\s*(?:之后|后面|后)", adjacent: true)
        scan("\(zr)\\s*(?:放|排)?\\s*在\\s*\(zr)\\s*(?:之后|后面|后)", adjacent: false)
        scan("\(zr)\\s*[,，、]?\\s*(?:然后|接着|再接|再放|之后是|后面是|紧接着)\\s*(?:是)?\\s*\(zr)", adjacent: true, swap: true)
        // "moment B ... moment A follow(s)" with an opening/start antecedent: "<start X> and moment A follow"
        // The antecedent is the opening Moment named earlier. Handled by resolveImplicitFollow (below) when a
        // bare "moment A follow(s)" has no explicit before-number — it attaches to the opening directive.
        // de-dupe
        var seen = Set<String>(); var uniq: [(Int, Int, Bool)] = []
        for t in out {
            let k = "\(t.0)-\(t.1)-\(t.2)"
            if !seen.contains(k) { seen.insert(k); uniq.append(t) }
        }
        return uniq
    }

    /// Numbers in a bare "moment A follow(s)/next" clause that has NO explicit "before" number — the user means
    /// A follows whatever was just named (typically the opening). The caller attaches these to the opening
    /// directive. Only returns a number when no explicit ordering already covers it.
    static func parseImplicitFollow(_ text: String) -> [Int] {
        guard !text.isEmpty else { return [] }
        let ns = text as NSString
        var nums: [Int] = []
        // "moment A follow" / "moment A follows" / "moment A next" NOT preceded directly by another "moment N"
        if let re = try? NSRegularExpression(
            pattern: #"moment\s+#?(\d+)\s+(?:to\s+)?(?:follow|follows|next|comes\s+next|afterwards?)"#,
            options: [.caseInsensitive]) {
            for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
                if m.numberOfRanges > 1, let n = Int(ns.substring(with: m.range(at: 1))) { nums.append(n) }
            }
        }
        // Chinese: "片段A紧随其后" / "片段A接着" / "片段A跟在后面" (no explicit antecedent -> the opening).
        if let re = try? NSRegularExpression(
            pattern: "\(zhRef)\\s*(?:紧随其后|随后|接着|紧接着|跟在后面|跟着|其后|接在后面|紧跟)",
            options: []) {
            for m in re.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
                nums.append(contentsOf: capturedNumbers(m, in: ns))
            }
        }
        return nums
    }

    /// Resolve parsed typed references + any visually-selected chip ids against a STABLE numbering snapshot.
    /// `chipSlots` are references already carrying a stable UUID (from the visual picker), so they bypass the
    /// number lookup entirely. Opening/ending are single-valued: the LAST one wins (a later instruction
    /// overrides an earlier one) — surfaced, never silently merged.
    static func resolve(typed: [ParsedReference],
                        chips: [(slot: DirectiveSlot, id: UUID)] = [],
                        ordering: [(after: Int, before: Int, adjacent: Bool)] = [],
                        implicitFollow: [Int] = [],
                        in numbering: StoryMomentNumbering) -> ResolutionResult {
        var d = ResolvedDirectives()
        var unresolved: [UnresolvedReference] = []

        func add(_ slot: DirectiveSlot, _ id: UUID) {
            switch slot {
            case .include: if !d.mustInclude.contains(id) { d.mustInclude.append(id) }
            case .exclude: if !d.exclude.contains(id) { d.exclude.append(id) }
            case .opening: d.opening = id
            case .ending:  d.ending = id
            }
        }

        for r in typed {
            guard let id = numbering.id(forNumber: r.number) else {
                unresolved.append(.init(reason: .numberOutOfRange(r.number), matchedText: r.matchedText))
                continue
            }
            add(r.slot, id)
        }
        for c in chips {
            guard numbering.contains(id: c.id) else {
                // A chip whose Moment was removed from the Story after it was inserted (owner #1 / #2):
                // request clarification rather than sending a dangling id.
                unresolved.append(.init(reason: .momentUnavailable(c.id), matchedText: "Moment \(c.id.uuidString.prefix(8))"))
                continue
            }
            add(c.slot, c.id)
        }
        for o in ordering {
            guard let aid = numbering.id(forNumber: o.after) else {
                unresolved.append(.init(reason: .numberOutOfRange(o.after), matchedText: "Moment \(o.after)")); continue
            }
            guard let bid = numbering.id(forNumber: o.before) else {
                unresolved.append(.init(reason: .numberOutOfRange(o.before), matchedText: "Moment \(o.before)")); continue
            }
            let pair = [aid, bid]
            if o.adjacent {
                if !d.orderAdjacent.contains(pair) { d.orderAdjacent.append(pair) }
            } else {
                if !d.orderAfter.contains(pair) { d.orderAfter.append(pair) }
            }
        }
        // Implicit "moment A follows" with no explicit antecedent attaches to the opening (A immediately after
        // the opening Moment). Only when an opening is set and A resolves and A != opening.
        if let openId = d.opening {
            for n in implicitFollow {
                guard let aid = numbering.id(forNumber: n) else {
                    unresolved.append(.init(reason: .numberOutOfRange(n), matchedText: "Moment \(n)")); continue
                }
                let pair = [aid, openId]
                if aid != openId && !d.orderAdjacent.contains(pair) { d.orderAdjacent.append(pair) }
            }
        }
        return ResolutionResult(directives: d, unresolved: unresolved)
    }
}


// MARK: - SwiftData bridge (keeps the resolver core pure/testable above)

extension StoryMomentNumbering {
    /// Build a snapshot from a Story's ordered Moments (`story.moments`, already ordered by StoryMomentLink
    /// orderIndex then addedAt). Numbers are the 1-based display indices into that STABLE order — EVERY linked
    /// Moment is numbered, including cloud-only ones whose original bytes are not on this device (owner P0:
    /// identity/numbering is independent of local availability, so Moment N is the same on every device).
    /// `localAvailable` reflects whether the original is on disk right now, for the picker's local/cloud badge.
    init(story moments: [MomentModel]) {
        self.init(ordered: moments.map {
            let rel = $0.asset?.relativePath
            let onDisk = rel.map { MediaStore.shared.fileExists(relativePath: $0) } ?? false
            return NumberedMoment(number: 0,  // re-stamped 1..N by the designated init
                                  id: $0.id,
                                  durationSeconds: $0.asset?.durationSeconds ?? 0,
                                  relativePath: rel,
                                  localAvailable: onDisk)
        })
    }
}
