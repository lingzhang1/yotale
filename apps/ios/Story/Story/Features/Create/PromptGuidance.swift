import SwiftUI

// P0 Creative Direction UX — prompt guidance + capability awareness (iOS-only; no backend/contract change).
// Two small REUSABLE pieces shared by Customize (pre-creation Creative Direction) and Revise (post-generation):
//   • PromptSuggestionChips — a compact "Try asking Story…" row of tappable examples that INSERT/APPEND
//     editable text into the instruction field. Never auto-submits. Example Moment references use a REAL
//     Moment number from the live numbering snapshot (never a hardcoded nonexistent N).
//   • CapabilityInfoButton + CapabilitySheet — a small (i) affordance opening a concise "What can Story edit?"
//     sheet with the supported list and a short unsupported list (so the main screen is not overwhelmed).
// Styling reuses StoryTheme + the shared FlowLayout (one wrapping-chip layout, no duplication).

/// One tappable example. `text` is what gets appended to the instruction field (editable, not submitted).
struct PromptSuggestion: Identifiable, Equatable {
    let id = UUID()
    let label: String   // short chip label
    let text: String    // full instruction fragment appended to the field
}

/// A compact "Try asking Story…" section. Tapping a chip APPENDS its text to the bound instruction (with a
/// separating space/period), places the caret implicitly at the end, and never submits. Designed to sit
/// directly beneath the instruction field.
struct PromptSuggestionChips: View {
    let title: String
    let suggestions: [PromptSuggestion]
    @Binding var text: String
    /// Called after an append so the host can invalidate any in-flight interpretation (stale-drop safeguard),
    /// exactly as a manual edit would.
    var onInsert: () -> Void = {}

    var body: some View {
        if suggestions.isEmpty { EmptyView() } else {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(StoryTheme.body(12, .medium)).foregroundStyle(StoryTheme.textSecondary)
                FlowLayout(spacing: 8) {
                    ForEach(suggestions) { s in
                        Button { append(s.text) } label: {
                            HStack(spacing: 5) {
                                Text(s.label).font(StoryTheme.body(13, .medium)).foregroundStyle(StoryTheme.cream)
                                Image(systemName: "plus").font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(StoryTheme.textSecondary)
                            }
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(StoryTheme.surface, in: Capsule())
                            .overlay(Capsule().stroke(StoryTheme.cream.opacity(0.14), lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Insert example: \(s.label)")
                    }
                }
            }
        }
    }

    private func append(_ fragment: String) {
        let cur = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if cur.isEmpty {
            text = fragment
        } else {
            // Join with a period+space unless the current text already ends in sentence punctuation.
            let sep: String
            if cur.hasSuffix("。") || cur.hasSuffix("！") || cur.hasSuffix("？") { sep = "" }
            else if cur.hasSuffix(".") || cur.hasSuffix("!") || cur.hasSuffix("?") { sep = " " }
            else { sep = L10n.current == .zhHans ? "。" : ". " }
            text = cur + sep + fragment
        }
        onInsert()
    }
}

/// The small (i) affordance + its sheet. Compact: a one-line supported summary opens the full list on tap.
struct CapabilityInfoButton: View {
    @State private var showSheet = false
    var body: some View {
        Button { showSheet = true } label: {
            HStack(spacing: 5) {
                Text("Editing capabilities").font(StoryTheme.body(12, .medium))
                Image(systemName: "info.circle").font(.system(size: 13, weight: .regular))
            }
            .foregroundStyle(StoryTheme.textSecondary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("What can Story edit?")
        .sheet(isPresented: $showSheet) { CapabilitySheet() }
    }
}

/// "What can Story edit?" — the supported list (what to ask for) and a short unsupported list (what it can't
/// do yet), so a user forms realistic instructions before submitting. Kept concise on purpose.
struct CapabilitySheet: View {
    @Environment(\.dismiss) private var dismiss

    private var supported: [(String, String)] { [
        ("scissors", L10n.t("Trim, reorder and select clips")),
        ("timer", L10n.t("Change how long each shot plays")),
        ("gauge.with.dots.needle.67percent", L10n.t("Adjust playback speed (within limits)")),
        ("square.on.square.dashed", L10n.t("Apply supported transitions (cut, crossfade, fade)")),
        ("music.note", L10n.t("Change the soundtrack")),
        ("speaker.wave.2", L10n.t("Keep, duck or mute the original audio")),
        ("waveform.path", L10n.t("Align cuts with the music's beats")),
    ] }
    private var unsupported: [String] { [
        L10n.t("Color grading and filters"),
        L10n.t("Brightness / exposure adjustments"),
        L10n.t("Stabilization"),
        L10n.t("Text overlays and subtitles"),
        L10n.t("Advanced zoom / reframing"),
        L10n.t("Background replacement"),
    ] }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Story can").font(StoryTheme.body(15, .semibold)).foregroundStyle(StoryTheme.cream)
                        ForEach(supported, id: \.1) { icon, label in
                            HStack(spacing: 10) {
                                Image(systemName: icon).font(.system(size: 14)).foregroundStyle(StoryTheme.gold)
                                    .frame(width: 22)
                                Text(label).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream.opacity(0.92))
                            }
                        }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Not yet supported").font(StoryTheme.body(15, .semibold))
                            .foregroundStyle(StoryTheme.textSecondary)
                        ForEach(unsupported, id: \.self) { label in
                            HStack(spacing: 10) {
                                Image(systemName: "minus").font(.system(size: 12, weight: .bold))
                                    .foregroundStyle(StoryTheme.textMuted).frame(width: 22)
                                Text(label).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textSecondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(StoryTheme.screenPadding)
            }
            .background(StoryTheme.ink)
            .navigationTitle("What can Story edit?").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }.fontWeight(.semibold).foregroundStyle(StoryTheme.gold)
                }
            }
        }
    }
}

// MARK: - Example sets (Customize vs Revise). Opening examples use a REAL Moment number from the snapshot.

enum PromptSuggestions {
    /// Customize (pre-creation Creative Direction): opening / include-exclude / visual selection / pacing /
    /// music + native audio. `firstMomentNumber` is the lowest real Moment number (nil => omit the opening
    /// example rather than invent a number).
    static func customize(firstMomentNumber: Int?) -> [PromptSuggestion] {
        var out: [PromptSuggestion] = []
        if let n = firstMomentNumber {
            out.append(.init(label: L10n.t("Start with Moment \(n)"), text: L10n.t("Start with Moment \(n)")))
        }
        out.append(contentsOf: [
            .init(label: L10n.t("Keep each shot around 5 seconds"), text: L10n.t("Keep each shot around 5 seconds")),
            .init(label: L10n.t("Use the most beautiful views first"), text: L10n.t("Use the most beautiful views first")),
            .init(label: L10n.t("Make cuts follow the music"), text: L10n.t("Make the cuts follow the music")),
            .init(label: L10n.t("Keep the original audio"), text: L10n.t("Keep the original audio")),
        ])
        return out
    }

    /// Revise (post-generation): preserve footage / shorten shots / reorder / replace opening / pacing /
    /// change music. `firstMomentNumber` feeds the "replace opening" example with a real number.
    static func revise(firstMomentNumber: Int?) -> [PromptSuggestion] {
        // Moment ORDER is no longer a typed suggestion ("Open with Moment 1", "Reorder the Moments so the best one
        // comes first"): ordering is chosen visually in the Arrange storyboard (Customize UX v2), never by typing
        // Moment numbers. `firstMomentNumber` is kept for call-site compatibility and is intentionally unused.
        _ = firstMomentNumber
        return [
            .init(label: L10n.t("Shorten each shot to ~5 seconds"), text: L10n.t("Shorten each shot to around 5 seconds")),
            .init(label: L10n.t("Make the pacing faster"), text: L10n.t("Make the pacing faster")),
            .init(label: L10n.t("Change the soundtrack"), text: L10n.t("Change the soundtrack to something calmer")),
        ]
    }
}

// MARK: - Pre-submit capability classification (Phase 4)
//
// A SMALL iOS mirror of the backend `_classify_unsupported_ops` vocabulary, used ONLY for instant pre-submit
// feedback (no network round-trip per keystroke). It is NOT a second NLP parser and NOT the authority — the
// backend guard remains the final word; this just lets the UI warn/confirm before an expensive job. Keep the
// two vocabularies in sync when either changes. Verdicts mirror the backend: .supported / .mixed / .allUnsupported.

enum CapabilityVerdict: Equatable {
    case supported
    case mixed(unsupported: [String])        // some supported edit + some unsupported effect
    case allUnsupported(unsupported: [String])
}

enum CapabilityClassifier {
    /// (regex, human noun) — mirrors the backend UNSUPPORTED map.
    private static let unsupported: [(String, String)] = [
        (#"color[- ]?correct|colou?r grad"#, "color correction"),
        (#"\bfilter\b|\bfilters\b|\blut\b"#, "filters"),
        (#"\bbright(er|ness)?\b|\bcontrast\b|\bsaturat|\bexposure\b|\bvibran|\btint\b|\bhue\b"#, "brightness/color adjustments"),
        (#"\bwarm(er|th)?\b|\bcool(er)?\b|\bteal\b|film look|color (tone|tint)|more (blue|green|red|orange|yellow|purple|pink|golden|vivid|colou?rful)|(blue|green|red|orange|yellow|purple|golden)r\b|make .*(sky|colou?rs?|grass|water|sunset) "#, "color tone changes"),
        (#"\bglow\b|\bvignette\b|\bbloom\b|light leak"#, "glow/vignette effects"),
        (#"\bblur\b|\bsharpen\b|\bgrain\b"#, "blur/sharpen effects"),
        (#"\bzoom\b|\bcrop\b|\breframe\b|\bpan\b|ken burns|re-?frame|punch in"#, "zoom/reframe"),
        (#"\bstabili[sz]e|\bstabili[sz]ation|anti-?shake"#, "stabilization"),
        (#"\btext\b|\bcaption|\bsubtitle|\bsticker|\boverlay|title card"#, "text/overlays"),
        (#"green ?screen|chroma ?key|remove background|replace background"#, "background replacement"),
        // 简体中文 vocabulary (additive; English patterns above are unchanged). Nouns stay the English keys
        // (they are localized for display at the call site via `phrase`).
        (#"调色|色彩校正|色彩分级"#, "color correction"),
        (#"滤镜|滤色"#, "filters"),
        (#"亮度|对比度|饱和度|曝光|色调|变亮|调亮|调暗"#, "brightness/color adjustments"),
        (#"更暖|暖色|冷色|偏蓝|偏绿|偏红|胶片感|复古色|更鲜艳|更多彩"#, "color tone changes"),
        (#"光晕|暗角|柔光|漏光"#, "glow/vignette effects"),
        (#"模糊|锐化|颗粒"#, "blur/sharpen effects"),
        (#"放大|缩放|裁切|变焦|重新构图|推近"#, "zoom/reframe"),
        (#"防抖|稳定画面|去抖"#, "stabilization"),
        (#"文字|字幕|贴纸|标题卡|叠加"#, "text/overlays"),
        (#"绿幕|抠像|换背景|替换背景|去除背景"#, "background replacement"),
    ]
    /// Genuine edit verbs/targets (mirrors the backend SUPPORTED set) — presence => MIXED, not all-unsupported.
    private static let supportedPattern =
        #"shorten|length|trim|\bcut\b|duration|pace|pacing|faster|slow(er)?|\bspeed\b|reorder|rearrange|\bswap\b|opening|ending|move (moment|clip|shot|it)|\binclude\b|\bexclude\b|\bremove\b|add moment|crossfade|\bfade\b|dissolve|transition|\bmusic\b|soundtrack|\btrack\b|\bsong\b|\bmute\b|\bduck\b|缩短|时长|修剪|剪辑|节奏|加快|放慢|变慢|变快|速度|调整顺序|重新排序|交换|开头|结尾|包含|排除|删除|去掉|淡入|淡出|转场|音乐|配乐|歌曲|静音"#

    static func classify(_ instruction: String) -> CapabilityVerdict {
        let text = instruction.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { return .supported }
        var nouns: [String] = []
        for (pat, noun) in unsupported where matches(pat, text) && !nouns.contains(noun) { nouns.append(noun) }
        if nouns.isEmpty { return .supported }
        return matches(supportedPattern, text) ? .mixed(unsupported: nouns)
                                               : .allUnsupported(unsupported: nouns)
    }

    /// Human phrase for a noun list: "a or b" / "a, b or c".
    static func phrase(_ nouns: [String]) -> String {
        guard let first = nouns.first else { return "" }
        let zh = L10n.current == .zhHans
        let loc: (String) -> String = { zh ? Self.localizedNoun($0) : $0 }
        if nouns.count == 1 { return loc(first) }
        let head = nouns.dropLast().map(loc).joined(separator: zh ? "、" : ", ")
        return head + (zh ? "或" : " or ") + loc(nouns[nouns.count - 1])
    }

    /// Chinese display names for the (English-keyed) unsupported-effect nouns.
    private static func localizedNoun(_ noun: String) -> String {
        switch noun {
        case "color correction": return "调色"
        case "filters": return "滤镜"
        case "brightness/color adjustments": return "亮度/色彩调整"
        case "color tone changes": return "色调变化"
        case "glow/vignette effects": return "光晕/暗角效果"
        case "blur/sharpen effects": return "模糊/锐化效果"
        case "zoom/reframe": return "缩放/重新构图"
        case "stabilization": return "防抖"
        case "text/overlays": return "文字/叠加层"
        case "background replacement": return "背景替换"
        default: return noun
        }
    }

    private static func matches(_ pattern: String, _ text: String) -> Bool {
        text.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
    }
}
