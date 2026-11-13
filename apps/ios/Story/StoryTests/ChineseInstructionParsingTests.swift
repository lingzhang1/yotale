import XCTest
@testable import Story

// Chinese (简体中文) understanding for the LOCAL instruction parsers. Additive to the English behaviour, which is
// re-asserted at the bottom so a regression in either language fails here. Covers: Moment-number detection
// (片段N / 第N个片段 / 第N段, full-width digits, Chinese numerals), directive verbs (从…开始, 以…开头/结尾,
// 不要用, 去掉, 删除, 跳过, 最后…), ordering, implicit follow, music intent, the pre-submit capability
// classifier, and the storyboard<->text conflict detection that consumes parseTyped.
final class ChineseInstructionParsingTests: XCTestCase {

    private func parse(_ t: String) -> [String] {
        MomentReferenceResolver.parseTyped(t).map { "\($0.slot)\($0.number)" }
    }

    // MARK: number parsing

    func testParseNumber_digitsFullWidthAndNumerals() {
        let p = MomentReferenceResolver.parseNumber
        XCTAssertEqual(p("8"), 8)
        XCTAssertEqual(p("８"), 8)
        XCTAssertEqual(p("１２"), 12)
        XCTAssertEqual(p("三"), 3)
        XCTAssertEqual(p("两"), 2)
        XCTAssertEqual(p("十"), 10)
        XCTAssertEqual(p("十二"), 12)
        XCTAssertEqual(p("二十"), 20)
        XCTAssertEqual(p("二十三"), 23)
        XCTAssertNil(p("百"))
        XCTAssertNil(p(""))
    }

    // MARK: reference forms

    func testReferenceForms() {
        XCTAssertEqual(parse("从片段8开始"), ["opening8"])
        XCTAssertEqual(parse("从 片段 8 开始"), ["opening8"])
        XCTAssertEqual(parse("从第8个片段开始"), ["opening8"])
        XCTAssertEqual(parse("从第八段开始"), ["opening8"])
        XCTAssertEqual(parse("从片段８开始"), ["opening8"])
        XCTAssertEqual(parse("从片段十二开始"), ["opening12"])
        XCTAssertEqual(parse("从第十二个片段开始"), ["opening12"])
    }

    // MARK: verbs

    func testOpening() {
        XCTAssertEqual(parse("以片段3开头"), ["opening3"])
        XCTAssertEqual(parse("以片段3为开头"), ["opening3"])
        XCTAssertEqual(parse("用片段3开头"), ["opening3"])
        XCTAssertEqual(parse("片段3放在开头"), ["opening3"])
        XCTAssertEqual(parse("第3个片段放在最前面"), ["opening3"])
    }

    func testEnding() {
        XCTAssertEqual(parse("以片段5结尾"), ["ending5"])
        XCTAssertEqual(parse("以第五个片段为结尾"), ["ending5"])
        XCTAssertEqual(parse("到片段5结束"), ["ending5"])
        XCTAssertEqual(parse("片段5放在最后"), ["ending5"])
        XCTAssertEqual(parse("最后用片段5"), ["ending5"])
    }

    func testExclude() {
        XCTAssertEqual(parse("不要用片段3"), ["exclude3"])
        XCTAssertEqual(parse("去掉片段３"), ["exclude3"])
        XCTAssertEqual(parse("删除第二个片段"), ["exclude2"])
        XCTAssertEqual(parse("跳过片段4"), ["exclude4"])
        XCTAssertEqual(parse("删掉第两段"), ["exclude2"])
        XCTAssertEqual(parse("不要用片段3，去掉片段4"), ["exclude3", "exclude4"])
    }

    func testInclude() {
        XCTAssertEqual(parse("包含片段6"), ["include6"])
        XCTAssertEqual(parse("保留第六个片段"), ["include6"])
        XCTAssertEqual(parse("一定要用片段6"), ["include6"])
    }

    func testMixedSentenceKeepsTextOrderAndSlots() {
        XCTAssertEqual(parse("从片段8开始，不要用片段4，以片段2结尾"), ["opening8", "exclude4", "ending2"])
    }

    func testHigherPriorityPatternClaimsTheSpan() {
        // "用片段3开头" must be opening only (not also include "用片段3").
        XCTAssertEqual(parse("用片段3开头"), ["opening3"])
        // "不要用片段3" must be exclude only (not include via the bare "用").
        XCTAssertEqual(parse("不要用片段3"), ["exclude3"])
    }

    func testNoFalsePositivesOnPlainChinese() {
        XCTAssertEqual(parse("让剪辑更有电影感"), [])
        XCTAssertEqual(parse("第3个镜头慢一点"), [])        // a shot, not a Moment
        XCTAssertEqual(parse("片段"), [])
        XCTAssertEqual(parse(""), [])
    }

    // MARK: ordering

    func testOrdering() {
        let a = MomentReferenceResolver.parseOrdering("片段6紧接在片段2之后")
        XCTAssertEqual(a.count, 1)
        XCTAssertEqual(a.first?.after, 6); XCTAssertEqual(a.first?.before, 2); XCTAssertEqual(a.first?.adjacent, true)

        let b = MomentReferenceResolver.parseOrdering("片段四在片段一之后")
        XCTAssertEqual(b.first?.after, 4); XCTAssertEqual(b.first?.before, 1); XCTAssertEqual(b.first?.adjacent, false)

        let c = MomentReferenceResolver.parseOrdering("片段2，然后片段7")
        XCTAssertEqual(c.first?.after, 7); XCTAssertEqual(c.first?.before, 2); XCTAssertEqual(c.first?.adjacent, true)
    }

    func testImplicitFollow() {
        XCTAssertEqual(MomentReferenceResolver.parseImplicitFollow("从片段1开始，片段3紧随其后"), [3])
    }

    // MARK: resolution end-to-end (Chinese text -> stable UUID directives)

    func testResolvesAgainstNumberingSnapshot() {
        let ids = (0..<9).map { _ in UUID() }
        let numbering = StoryMomentNumbering(ordered: ids.enumerated().map {
            NumberedMoment(number: $0.offset + 1, id: $0.element, durationSeconds: 4, relativePath: nil)
        })
        let text = "从片段８开始，不要用第四个片段，以片段二结尾"
        let r = MomentReferenceResolver.resolve(typed: MomentReferenceResolver.parseTyped(text), in: numbering)
        XCTAssertFalse(r.needsClarification)
        XCTAssertEqual(r.directives.opening, ids[7])
        XCTAssertEqual(r.directives.exclude, [ids[3]])
        XCTAssertEqual(r.directives.ending, ids[1])

        let out = MomentReferenceResolver.resolve(typed: MomentReferenceResolver.parseTyped("从片段12开始"), in: numbering)
        XCTAssertTrue(out.needsClarification)   // out-of-range Chinese reference is surfaced, not dropped
    }

    func testSequenceTextConflictDetectionSeesChineseOpening() {
        let ids = (0..<5).map { _ in UUID() }
        let numbering = StoryMomentNumbering(ordered: ids.enumerated().map {
            NumberedMoment(number: $0.offset + 1, id: $0.element, durationSeconds: 4, relativePath: nil)
        })
        let seq = MomentSequence(orderedIds: [ids[0], ids[1]], policy: .allowOthers)
        let typed = MomentReferenceResolver.resolve(
            typed: MomentReferenceResolver.parseTyped("从片段3开始"), in: numbering).directives
        let conflicts = seq.conflicts(with: typed)
        XCTAssertFalse(conflicts.isEmpty, "Chinese 'start with Moment 3' must conflict with a sequence starting at Moment 1")

        let dropped = MomentReferenceResolver.resolve(
            typed: MomentReferenceResolver.parseTyped("去掉片段1"), in: numbering).directives
        XCTAssertFalse(seq.conflicts(with: dropped).isEmpty)
    }

    // MARK: music intent

    func testChineseMusicIntent() {
        let m = MomentReferenceResolver.parseMusicIntent("来点轻柔的钢琴音乐，剪辑卡点")
        XCTAssertTrue(m.beatSync)
        XCTAssertEqual(m.preference?.moodTags.contains("calm"), true)
        XCTAssertEqual(m.preference?.moodTags.contains("piano"), true)
        // Visual-only language never produces a music preference.
        XCTAssertTrue(MomentReferenceResolver.parseMusicIntent("节奏快一点，画面更震撼").isEmpty)
    }

    // MARK: capability classifier

    func testClassifierChinese() {
        XCTAssertEqual(CapabilityClassifier.classify("缩短每个镜头，把节奏加快"), .supported)
        if case .allUnsupported = CapabilityClassifier.classify("给画面加滤镜") {} else { XCTFail("filters unsupported") }
        if case .allUnsupported = CapabilityClassifier.classify("加上字幕") {} else { XCTFail("subtitles unsupported") }
        if case .mixed(let nouns) = CapabilityClassifier.classify("缩短镜头并加上滤镜") {
            XCTAssertEqual(nouns, ["filters"])
        } else { XCTFail("mixed expected") }
    }

    // MARK: English behaviour unchanged

    func testEnglishUnchanged() {
        XCTAssertEqual(parse("Start with Moment 8, drop Moment 4, end with Moment 2"),
                       ["opening8", "exclude4", "ending2"])
        XCTAssertEqual(parse("use moment 5 to start"), ["opening5"])
        XCTAssertEqual(parse("make it more cinematic"), [])
        let o = MomentReferenceResolver.parseOrdering("moment 2 immediately after moment 5")
        XCTAssertEqual(o.first?.after, 2); XCTAssertEqual(o.first?.before, 5); XCTAssertEqual(o.first?.adjacent, true)
        XCTAssertEqual(CapabilityClassifier.classify("add a filter"), .allUnsupported(unsupported: ["filters"]))
    }
}
