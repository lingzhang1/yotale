import SwiftUI

// Customize Your Story — replaces the compact DurationChoiceView sheet. Two sections, both built from existing
// intelligence (no new universal defaults): Section A Story Length (Highlights / Full Story / Custom) off the
// Duration Intelligence recommendation; Section B Sound (Immersive / Balanced / Music-led) showing the Story's
// INFERRED recommendation while letting the user override it. Dark editorial Figma language; whole rows are
// tappable; obvious selected states; concise explanations; NO sliders/percentages/jargon in the main flow
// (an exact-seconds field stays behind the Custom row). The Music Picker flow downstream is unchanged.
struct CustomizeYourStoryView: View {
    let rec: DurationRecommendation
    let inferredSound: SoundPreference?         // advisory recommendation (nil => none inferred)
    let initialExplicitSound: SoundPreference?  // the user's prior explicit choice, if any
    let initialEditingApproach: EditingApproach // the Story's current approach (default .storytelling)
    /// Whether the Visual-first option can be honored right now (StoryMultimodalPlanning.enabled). When false
    /// the Editing Approach section is HIDDEN entirely — we never present an option that silently can't run.
    let visualFirstAvailable: Bool
    /// STABLE Moment-number snapshot for Creative Direction (Stage 2). Empty => the section is hidden (no
    /// referenceable Moments). Typed "Moment N" references resolve against THIS snapshot.
    let numbering: StoryMomentNumbering
    /// Resolve a stable Moment id -> MomentModel for the visual picker's live thumbnails (no media copy).
    let momentForId: (UUID) -> MomentModel?
    /// Draft Creative Direction text to repopulate (survives navigation / failed generation).
    let initialCreativeDirection: String
    /// Draft reference chips to repopulate (stable ids; display numbers re-derived from `numbering`).
    let initialReferenceChipIds: [UUID]
    /// Issue 1 — the Story's EXISTING target length (seconds) and editorial mode, when one was already chosen.
    /// Used to PREFILL the length selection so re-opening Customize shows the user's prior choice instead of
    /// silently resetting to the recommendation. An explicit "custom" mode seeds the exact-seconds Custom row
    /// (provenance preserved); "highlights"/"full" re-selects that editorial row. nil => seed from `rec`.
    let initialExplicitTargetSeconds: Double?
    let initialEditorialMode: String?
    /// Part B — the FULL set of persisted hard directives currently saved on the Story (opening, ending,
    /// adjacency, order, must-include, exclude), so the sheet can SHOW them and let the user clear them. The
    /// free-text `initialCreativeDirection` only round-trips the soft text + was the only visible surface for
    /// opening/adjacency before; this makes every active structural directive visible. nil => none saved.
    let initialSavedDirectives: ResolvedDirectives?
    /// Returns chosen duration (seconds), sound, length wire, editing approach, resolved HARD directives (nil
    /// when none), the SOFT creative-direction text, the chip ids, and the parsed MUSIC intent — so the caller
    /// persists the draft, forwards directives + soft_direction to the edit planner, and routes an explicit
    /// music preference to MusicPlan (owner Music-Routing §1).
    let onCreate: (Double, SoundPreference, String, EditingApproach, ResolvedDirectives?, String, [UUID], ParsedMusicIntent, MomentSequence) -> Void
    let onCancel: () -> Void

    enum LengthChoice: Hashable { case highlights, full, custom
        var wire: String { switch self { case .highlights: return "highlights"; case .full: return "full"; case .custom: return "custom" } }
    }

    /// PURE prefill decision for the length row (issue 1), extracted so it is unit-testable without a SwiftUI
    /// host. An existing editorial mode wins (preserve the user's prior choice / explicit-custom provenance);
    /// otherwise Full when a recommended point exists, else Custom.
    static func seedLength(editorialMode: String?, hasRecommendedPoint: Bool) -> LengthChoice {
        switch (editorialMode ?? "").lowercased() {
        case "custom":     return .custom
        case "highlights": return .highlights
        case "full":       return .full
        default:           return hasRecommendedPoint ? .full : .custom
        }
    }

    // MARK: - P1-D Video Type (PRIMARY) + independent Duration

    /// The two consumer editorial types. This is the PRIMARY selection (P1-D §4) and the source the request's
    /// editorial breadth (`mode`) derives from. A type is NOT a duration preset (§4); duration is chosen
    /// independently below. Wire values match the P1-C contract (`highlights` / `full`).
    enum VideoType: Hashable, CaseIterable {
        case highlights, full
        var wire: String { self == .highlights ? "highlights" : "full" }
        var title: String { self == .highlights ? "Highlights" : "Full Story" }
        var blurb: String {
            self == .highlights ? "The best visual moments, beautifully cut."
                                 : "More of the journey, people, and atmosphere."
        }
    }

    /// Independent duration control (P1-D §8). Recommended is TYPE-AWARE (Highlights → highlights range,
    /// Full Story → recommended range); Custom is an explicit length for EITHER type. Highlights/Full are
    /// NEVER reintroduced as duration choices (§8).
    enum DurationChoice: Hashable { case recommended, custom }

    /// PURE seed for the primary Video Type. OWNER DECISION (P1-D, 2026-10-26, "option B"): the sheet ALWAYS
    /// opens on Highlights — the product default — regardless of the Story's persisted `editorialMode`. The
    /// user opts into Full Story per attempt; a prior Full Story generation does NOT pre-select Full Story on
    /// re-open. (This intentionally overrides the earlier prior-choice prefill for TYPE; duration/sound prefill
    /// is unchanged.) Historical records are never rewritten — this governs only the sheet's initial selection.
    static func seedVideoType(editorialMode: String?) -> VideoType { .highlights }

    /// PURE seed for the duration control: a historical explicit `custom` length, or a prior explicit target
    /// that differs from the type's recommended point, opens as Custom; otherwise Recommended.
    static func seedDurationChoice(editorialMode: String?, explicitTarget: Double?) -> DurationChoice {
        if (editorialMode ?? "").lowercased() == "custom" { return .custom }
        return explicitTarget != nil ? .custom : .recommended
    }

    /// PURE: render the active persisted directives as human-readable lines using the STABLE numbering, so the
    /// user sees exactly what is saved (e.g. "Start with Moment 1", "Moment 6 right after Moment 1"). Part B.
    static func savedDirectiveLines(_ d: ResolvedDirectives?, numbering: StoryMomentNumbering) -> [String] {
        guard let d, !d.isEmpty else { return [] }
        func n(_ id: UUID) -> String { numbering.number(forId: id).map { "Moment \($0)" } ?? "a Moment" }
        var lines: [String] = []
        if let o = d.opening { lines.append("Start with \(n(o))") }
        if let e = d.ending { lines.append("End with \(n(e))") }
        for p in d.orderAdjacent where p.count == 2 { lines.append("\(n(p[0])) right after \(n(p[1]))") }
        for p in d.orderAfter where p.count == 2 { lines.append("\(n(p[0])) after \(n(p[1]))") }
        let incOnly = d.mustInclude.filter { $0 != d.opening && $0 != d.ending }
        if !incOnly.isEmpty { lines.append("Include " + incOnly.map(n).joined(separator: ", ")) }
        if !d.exclude.isEmpty { lines.append("Exclude " + d.exclude.map(n).joined(separator: ", ")) }
        return lines
    }

    /// PURE prefill decision for the exact Custom seconds: the user's prior EXPLICIT target wins (preserve
    /// provenance), else the recommended point, else the feasible-band midpoint.
    static func seedCustomSeconds(explicitTarget: Double?, recommendedPoint: Double?,
                                  bandLo: Double?, bandHi: Double?) -> Double {
        (explicitTarget ?? recommendedPoint ?? ((bandLo ?? 10) + (bandHi ?? 30)) / 2).rounded()
    }

    @State private var length: LengthChoice
    @State private var videoType: VideoType          // P1-D PRIMARY selection
    @State private var durationChoice: DurationChoice // P1-D independent duration (Recommended/Custom)
    @State private var moreOptionsExpanded = false    // P1-D §8 — collapsed by default
    @State private var sound: SoundPreference
    @State private var approach: EditingApproach
    @State private var customSeconds: Double
    /// OPTIONAL style presets (Phase B). Multi-select, OFF by default; applied per-output only (folded into
    /// soft_direction + music seed in performInterpretation), never written to durable Story CreativeIntent.
    @State private var selectedPresets: Set<StylePreset> = []
    /// Advanced section (Editing Approach) collapsed by default — progressive disclosure (decision 4).
    @State private var showAdvanced = false
    // Stage 2 Creative Direction (optional). Draft text + reference chips, resolved to directives on Create.
    @State private var creativeDirection: String
    @State private var chips: [MomentReferenceChipModel]
    // Customize UX v2 — the visual-storyboard sequence (ordered Moments + policy). Inactive by default ("AI
    // chooses order"); opening Arrange edits it. Persisted in the draft so close/reopen is non-destructive.
    @State private var momentSequence: MomentSequence
    @State private var showArrange = false
    @State private var showMoodSheet = false   // Customize UX v2 §9: compact single-select Mood sheet
    /// Selected SOFT quick shortcuts (shorter shots, cut to the beat, ...). Toggles that ride soft_direction at
    /// submit; deliberately never written into the instruction text the interpreter reads.
    @State private var softShortcuts: Set<QuickShortcut> = []
    @State private var clarification: String?
    // Interpretation lifecycle (owner safeguards #1/#2): guard duplicate taps, drop stale async responses, and
    // carry a retryable failure. `interpretToken` is bumped on every input edit / dismissal so a response that
    // resolves AFTER the user changed the text or left the sheet is discarded instead of submitting.
    @State private var isInterpreting = false
    @State private var interpretToken = UUID()
    @State private var retryableInstruction: String?   // non-nil => a Retry affordance is shown
    /// Part B — the active persisted structural directives (opening/adjacency/order/must-include/exclude),
    /// shown in a "Saved instructions" summary the user can clear. Cleared => removed from the submitted set.
    @State private var savedDirectives: ResolvedDirectives?
    @Environment(AuthStore.self) private var auth
    @State private var cloudGate = CloudAuthGateModel()

    init(rec: DurationRecommendation, inferredSound: SoundPreference?, initialExplicitSound: SoundPreference?,
         initialEditingApproach: EditingApproach = .default, visualFirstAvailable: Bool = false,
         numbering: StoryMomentNumbering = StoryMomentNumbering(ordered: []),
         momentForId: @escaping (UUID) -> MomentModel? = { _ in nil },
         initialCreativeDirection: String = "", initialReferenceChipIds: [UUID] = [],
         initialExplicitTargetSeconds: Double? = nil, initialEditorialMode: String? = nil,
         initialSavedDirectives: ResolvedDirectives? = nil,
         initialMomentSequence: MomentSequence? = nil,
         onCreate: @escaping (Double, SoundPreference, String, EditingApproach, ResolvedDirectives?, String, [UUID], ParsedMusicIntent, MomentSequence) -> Void,
         onCancel: @escaping () -> Void) {
        self.rec = rec; self.inferredSound = inferredSound; self.initialExplicitSound = initialExplicitSound
        self.initialEditingApproach = initialEditingApproach; self.visualFirstAvailable = visualFirstAvailable
        self.numbering = numbering; self.momentForId = momentForId
        self.initialCreativeDirection = initialCreativeDirection; self.initialReferenceChipIds = initialReferenceChipIds
        self.initialExplicitTargetSeconds = initialExplicitTargetSeconds
        self.initialEditorialMode = initialEditorialMode
        // The storyboard OWNS inclusion (must_include) and relative order (order_after). The previous version's
        // copies of those must never be carried forward as a second, hidden source — they re-listed every old
        // Moment on a new version and, after the user pruned the sequence, were merged back into the request and
        // referenced Moments outside the arranged set (-> directive_ref_ineligible / invalid_after_repair).
        // Typed-text directives re-derive from the persisted instruction text on Create, so dropping the stale
        // copies loses nothing the user can still see.
        let keptSaved = initialSavedDirectives?.withoutStoryboardOwned()
        self.initialSavedDirectives = keptSaved
        self.onCreate = onCreate; self.onCancel = onCancel
        _savedDirectives = State(initialValue: keptSaved)
        // Default length: prefer the Story's EXISTING editorial mode when re-opening (issue 1); else Full Story
        // when a recommended point exists, else Custom. A prior exact "custom" target seeds the Custom row so
        // the user's explicit length is shown (not silently reset to the recommendation).
        _length = State(initialValue: Self.seedLength(editorialMode: initialEditorialMode,
                                                      hasRecommendedPoint: rec.recommendedPointSeconds != nil))
        // P1-D: PRIMARY Video Type (Highlights default; historical custom ≠ Full Story) + independent duration.
        _videoType = State(initialValue: Self.seedVideoType(editorialMode: initialEditorialMode))
        _durationChoice = State(initialValue: Self.seedDurationChoice(
            editorialMode: initialEditorialMode, explicitTarget: initialExplicitTargetSeconds))
        // Default sound: the user's explicit choice if any, else the inferred recommendation, else balanced.
        _sound = State(initialValue: initialExplicitSound ?? inferredSound ?? .balanced)
        // Default approach: the Story's current approach (defaults to .storytelling). If Visual-first is not
        // available, force storytelling so a hidden section can never leave a non-honorable selection.
        _approach = State(initialValue: visualFirstAvailable ? initialEditingApproach : .storytelling)
        // Seed the exact-seconds Custom field: the user's prior EXPLICIT target wins (preserve provenance),
        // else the recommended point, else the feasible-band midpoint.
        _customSeconds = State(initialValue: Self.seedCustomSeconds(
            explicitTarget: initialExplicitTargetSeconds, recommendedPoint: rec.recommendedPointSeconds,
            bandLo: rec.evidence.feasibleBandSeconds.first, bandHi: rec.evidence.feasibleBandSeconds.last))
        // Seed Creative Direction draft (survives navigation / failed generation). Chips re-derive their display
        // number from the current numbering snapshot; an id no longer present is dropped (surfaced on Create).
        // The saved draft text is the planner's FULL soft direction, which includes sentences WE generated
        // (soft shortcuts + the Mood preset phrase). Separate them back out so only the user's own words land in
        // the text box (and reach the interpreter); the generated parts restore as toggles / the Mood row.
        let split = Self.splitGeneratedSoft(initialCreativeDirection)
        _creativeDirection = State(initialValue: split.userText)
        _softShortcuts = State(initialValue: split.shortcuts)
        _selectedPresets = State(initialValue: split.preset.map { [$0] } ?? [])
        // The old Moment-chip list is gone from this screen (the Arrange sheet is the one place Moments are
        // chosen), so no chips are re-seeded from a previous version. `initialReferenceChipIds` is ignored.
        _chips = State(initialValue: [])
        // Seed the storyboard from the PERSISTED sequence (ordered ids + policy), so re-opening shows exactly
        // what was arranged, including "only the selected". Ids no longer present in the snapshot drop out
        // (deleted Moments); a sequence left with nothing is inactive ("AI chooses order").
        let present = (initialMomentSequence?.orderedIds ?? []).filter { numbering.contains(id: $0) }
        _momentSequence = State(initialValue: present.isEmpty
            ? MomentSequence()
            : MomentSequence(orderedIds: present, policy: initialMomentSequence?.policy ?? .allowOthers))
    }

    /// Plain-language message for a storyboard<->typed-text conflict (owner §10); nil when there is none.
    private static func sequenceConflictMessage(_ conflicts: [MomentSequence.Conflict],
                                                numbering: StoryMomentNumbering) -> String? {
        func names(_ ids: [UUID]) -> String {
            ids.compactMap { numbering.number(forId: $0) }.sorted().map { "Moment \($0)" }.joined(separator: ", ")
        }
        for c in conflicts {
            switch c {
            case .excludedButSequenced(let ids):
                return "\(names(ids)) is in your Moment sequence but your text asks to drop it. "
                     + "Remove it from the sequence, or edit the text."
            case .outsideOnlySelected(let ids):
                return "\(names(ids)) isn’t in your sequence, which is set to “Use only the selected Moments”. "
                     + "Add it in Arrange Moments, change that setting, or edit the text."
            }
        }
        return nil
    }

    /// Split a saved soft-direction draft into the user's own words + the soft shortcuts / Mood preset the app
    /// generated (see GeneratedSoftSplitter). Only the user's words are returned as text.
    private static func splitGeneratedSoft(_ text: String)
        -> (userText: String, shortcuts: Set<QuickShortcut>, preset: StylePreset?) {
        let shortcutPhrases = QuickShortcut.allCases.map(\.phrase).filter { !$0.isEmpty }
        let r = GeneratedSoftSplitter.split(text, generated: shortcutPhrases + StylePreset.allCases.map(\.directionPhrase))
        let shortcuts = Set(QuickShortcut.allCases.filter { !$0.phrase.isEmpty && r.matched.contains($0.phrase) })
        let preset = StylePreset.allCases.first { r.matched.contains($0.directionPhrase) }
        return (r.userText, shortcuts, preset)
    }

    private var ceiling: Double { max(rec.recommendation?.feasibleCeilingSeconds ?? 60, rec.evidence.feasibleBandSeconds.last ?? 60) }
    private var floor: Double { max(3, rec.evidence.feasibleBandSeconds.first ?? 5) }
    private var fullSeconds: Double? { rec.recommendedPointSeconds }
    private var highlightsSeconds: Double? { rec.highlightsPointSeconds }
    private var clampedCustom: Double { min(max(customSeconds.rounded(), floor), ceiling) }

    private var chosenSeconds: Double {
        switch length {
        case .highlights: return highlightsSeconds ?? clampedCustom
        case .full:       return fullSeconds ?? clampedCustom
        case .custom:     return clampedCustom
        }
    }

    // MARK: - P1-D derived values

    /// The TYPE-AWARE recommended point (P1-D §4/§8): Highlights → highlights range point, Full Story →
    /// recommended range point. Graceful fallback to the other point when one is missing; nil when neither
    /// exists (the UI then shows no fabricated estimate, §4).
    private var typeRecommendedSeconds: Double? {
        switch videoType {
        case .highlights: return highlightsSeconds ?? fullSeconds
        case .full:       return fullSeconds ?? highlightsSeconds
        }
    }

    /// The seconds actually submitted (P1-D): Custom → the explicit clamped value; Recommended → the
    /// type-aware point, falling back to the clamped custom seed only if no recommendation exists.
    private var p1dChosenSeconds: Double {
        switch durationChoice {
        case .custom:      return clampedCustom
        case .recommended: return typeRecommendedSeconds ?? clampedCustom
        }
    }

    /// The editorial breadth string submitted to `onCreate` (becomes `story.editorialMode`, which the
    /// coordinator's attempt-boundary resolution reads to set `pendingEditorialType`). Driven by the PRIMARY
    /// Video Type — NOT by the duration choice. Custom duration does not make a Highlights into `full`;
    /// `custom` is only used to preserve a historical custom-length record's provenance, never as a type.
    private var p1dMode: String { videoType.wire }

    /// DETERMINISTIC plain-language summary of the current generation settings (M1). No model call. Duration
    /// is included ONLY when a concrete value is known for the chosen length (never invented). Style is named
    /// only when a preset is selected (optional). Reads from live @State so it updates as the user adjusts.
    private var directionSummary: String {
        // P1-D §9 dynamic summary: "Highlights · About 23 seconds · Balanced sound". Reflects current state;
        // the duration is shown as an APPROXIMATE recommendation (never a guaranteed output length) and is
        // omitted entirely when no estimate exists (no fabricated number). Feel is appended only when chosen.
        var parts: [String] = [videoType.title]
        if let d = durationSummaryText { parts.append(d) }
        switch sound {
        case .immersive: parts.append("Immersive sound")
        case .balanced:  parts.append("Balanced sound")
        case .musicLed:  parts.append("Music-led sound")
        }
        let feels = StylePreset.allCases.filter { selectedPresets.contains($0) }.map { $0.label }
        if !feels.isEmpty { parts.append(feels.joined(separator: ", ")) }
        return parts.joined(separator: " · ")
    }

    /// The duration phrase for the summary + type cards. Custom → exact; Recommended → "About Ns" when a
    /// type-aware recommendation exists, else nil (show nothing — never a fabricated estimate, §4/§9).
    private var durationSummaryText: String? {
        switch durationChoice {
        case .custom:      return "Custom \(Int(clampedCustom.rounded())) seconds"
        case .recommended: return typeRecommendedSeconds.map { "About \(Int($0.rounded())) seconds" }
        }
    }

    /// Per-type approximate recommendation shown on each Video Type card ("About 23s"), or nil when Duration
    /// Intelligence has no valid recommendation for that type (§4 — show no fabricated estimate).
    private func cardEstimate(for type: VideoType) -> String? {
        let s: Double? = (type == .highlights) ? (highlightsSeconds ?? fullSeconds)
                                               : (fullSeconds ?? highlightsSeconds)
        return s.map { "About \(Int($0.rounded()))s" }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // 1. HEADER (P1-D §3)
                VStack(alignment: .leading, spacing: 6) {
                    Text("Create Your Video").font(StoryTheme.display(26)).foregroundStyle(StoryTheme.cream)
                    Text("Choose how you want your moments to come together.")
                        .font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textSecondary)
                }

                // 2. VIDEO TYPE (PRIMARY, §4) — two cards, Highlights default.
                videoTypeSection

                // 3. CREATIVE DIRECTION (§6) — directly below Video Type. Only when there are referenceable
                // Moments. Natural-language + typed "Moment N" refs + visual picker; unresolved hard refs BLOCK.
                if numbering.count > 0 {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Anything you want to include?")
                            .font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
                        StoryTextField(placeholder: "Start with the mountain reveal, show the best moments, and make the cuts follow the music…",
                                       text: $creativeDirection, minHeight: 92)
                            .onChange(of: creativeDirection) { _, _ in
                                interpretToken = UUID()
                                if retryableInstruction != nil { retryableInstruction = nil; clarification = nil }
                            }
                        // Suggestion chips (§6): 2–3 shown, type-adapted, insert via the existing mechanism
                        // (append-only, never replacing typed text). Moment-reference picker stays accessible
                        // but unobtrusive, beside the chips.
                        suggestionChipRow
                        if let clarification {
                            Text(clarification).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.danger)
                        }
                        if retryableInstruction != nil {
                            Button { attemptCreate() } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "arrow.clockwise").font(.system(size: 12, weight: .semibold))
                                    Text("Retry").font(StoryTheme.body(13, .medium))
                                }
                                .foregroundStyle(StoryTheme.gold)
                                .padding(.horizontal, 12).padding(.vertical, 8)
                                .overlay(Capsule().stroke(StoryTheme.gold.opacity(0.5), lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                // 3b. MOMENT SEQUENCE (Customize UX v2 §3/§4) — optional visual storyboard. Default "AI chooses
                // order"; Arrange opens the drag-to-order sheet. No all-Moment chips on the main screen.
                if numbering.count > 0 { momentSequenceSection }

                // 4. FEELING / STYLE PRESETS (§7) — optional, initial small set, independent of type.
                feelSection

                // 5. MORE OPTIONS (§8) — collapsed by default: Duration · Sound · Music.
                moreOptionsSection
            }
            .padding(24)
            .padding(.bottom, 8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .presentationBackground(StoryTheme.ink)
        // 6. PERSISTENT CREATE ACTION (§3/§9/§13) — safe-area-aware bottom region that stays visible with the
        // keyboard open, More Options expanded, and across iPhone sizes. Carries the dynamic summary.
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 10) {
                Text(directionSummary)
                    .font(StoryTheme.body(13)).foregroundStyle(StoryTheme.cream.opacity(0.78))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Summary: \(directionSummary)")
                Button { attemptCreate() } label: {
                    HStack(spacing: 8) {
                        if isInterpreting { ProgressView().tint(StoryTheme.ink) }
                        Text(isInterpreting ? "Understanding…" : "Create my video")
                            .font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.ink)
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, 16)
                    .background(StoryTheme.cream).clipShape(Capsule())
                    .opacity(isInterpreting ? 0.7 : 1)
                }
                .buttonStyle(.plain)
                .disabled(isInterpreting)
                .accessibilityLabel("Create my video")
                Button("Cancel") { interpretToken = UUID(); onCancel() }
                    .font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textMuted)
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 8)
            .background(.ultraThinMaterial)
            .overlay(Rectangle().frame(height: 1).foregroundStyle(StoryTheme.cream.opacity(0.08)), alignment: .top)
        }
        .onDisappear { interpretToken = UUID() }   // drop any in-flight interpretation on dismissal (#1)
        // Customize UX v2: the visual storyboard. Edits momentSequence in place; the draft persists in @State
        // so closing/reopening Customize is non-destructive (owner §4).
        .sheet(isPresented: $showArrange) {
            ArrangeMomentsSheet(
                numbering: numbering,
                momentForId: momentForId,
                initial: momentSequence,
                onSave: { momentSequence = $0 })
        }
        .sheet(isPresented: $showMoodSheet) { moodSheet }   // Customize UX v2 §9
        .cloudAuthGate(cloudGate)
    }

    /// Resolve the typed references + chips against the stable snapshot. Hard references that cannot resolve
    /// Interpret the instruction through the SHARED InterpretationCoordinator, then hand the resolved directives
    /// to the caller. Owner safeguards: an immutable snapshot of the visible text + chips + numbering is taken
    /// BEFORE the async call; a duplicate tap is ignored while interpreting; a response whose token no longer
    /// matches (text edited or sheet dismissed) is DROPPED; a service failure keeps the draft and offers Retry;
    /// unresolved references BLOCK submit with clarification. Never silently downgrade a hard clause.
    private func attemptCreate() {
        guard !isInterpreting else { return }                 // duplicate-tap protection (#1)
        // Paid NL interpretation is a cloud action — require a session first. The gate stores THIS closure and
        // resumes it exactly once after sign-in, so the draft/chips snapshot below is taken from the values the
        // user sees at resume time and the paid call fires only once (no duplicate inference).
        cloudGate.run { self.performInterpretation() }
    }

    private func performInterpretation() {
        guard !isInterpreting else { return }
        // Immutable submission snapshot (#1): the exact values the user sees right now.
        let snapshotText = creativeDirection.trimmingCharacters(in: .whitespacesAndNewlines)
        let snapshotChips = chips
        let snapshotSequence = momentSequence      // Customize UX v2: the arranged storyboard at submit time
        let snapshotShortcuts = softShortcuts      // soft quick-shortcut toggles at submit time
        let snapshotNumbering = numbering
        let token = UUID()
        interpretToken = token
        clarification = nil
        retryableInstruction = nil
        isInterpreting = true

        Task {
            let outcome = await InterpretationCoordinator.interpret(
                snapshotText, numbering: snapshotNumbering,
                summaryForId: { id in momentForId(id)?.caption })

            await MainActor.run {
                // Stale-response drop (#1): the user edited the text or dismissed the sheet mid-flight.
                guard interpretToken == token else { return }
                isInterpreting = false

                // Music ask the typed-directive contract can't express yet — surface honestly (#5).
                let musicSuffix = outcome.unsupportedMusicNote.map { "\n\($0)" } ?? ""

                switch outcome.kind {
                case .serviceFailure:
                    retryableInstruction = snapshotText     // preserve draft + offer Retry (#2)
                    clarification = (outcome.blocking.first ?? "Couldn't interpret that right now.") + musicSuffix
                    return
                case .clarify:
                    // Thumbnail clarification when numeric refs are unresolved, else text (#2).
                    clarification = clarificationText(outcome) + musicSuffix
                    return
                case .ok:
                    break
                }

                // Merge the visual-picker include chips into the interpreted directives (chips are include-only;
                // the typed text owns opening/ending/ordering via the coordinator). Keeps BOTH inputs, one path.
                var directives = outcome.directives
                // Owner §10: a contradiction between the storyboard and the typed text is explained BEFORE any
                // paid planning call, instead of the planner rejecting it (a typed "Start with Moment 9" under
                // "only these Moments" is an ineligible reference; "drop Moment 4" while 4 is sequenced is
                // required-AND-excluded). Nothing is silently dropped on either side.
                if let msg = Self.sequenceConflictMessage(snapshotSequence.conflicts(with: directives),
                                                          numbering: snapshotNumbering) {
                    clarification = msg
                    return
                }
                for c in snapshotChips where !directives.mustInclude.contains(c.id) {
                    directives.mustInclude.append(c.id)
                }
                // Part B — fold in the SAVED structural directives the user KEPT (savedDirectives reflects any
                // Clear). New typed text wins per-slot (opening/ending it set); otherwise the saved value is
                // preserved. If the user Cleared (savedDirectives == nil) nothing is folded -> request drops
                // them. Never silently retains a cleared directive; never silently drops a kept one.
                if let saved = savedDirectives {
                    if directives.opening == nil { directives.opening = saved.opening }
                    if directives.ending == nil { directives.ending = saved.ending }
                    for id in saved.mustInclude where !directives.mustInclude.contains(id) { directives.mustInclude.append(id) }
                    for id in saved.exclude where !directives.exclude.contains(id) { directives.exclude.append(id) }
                    for p in saved.orderAfter where !directives.orderAfter.contains(p) { directives.orderAfter.append(p) }
                    for p in saved.orderAdjacent where !directives.orderAdjacent.contains(p) { directives.orderAdjacent.append(p) }
                }
                // Customize UX v2: fold the visual storyboard into the directives. An ACTIVE sequence adds its
                // Moments as must_include and its relative order as an order_after chain (ordering stays an
                // OBJECTIVE on the backend — never promoted to HARD). The allowed-source-set for Policy B rides
                // separately (sequencePolicyForBuild below), applied by filtering moments[] — NOT via exclude.
                let seq = snapshotSequence
                seq.apply(to: &directives)
                let finalDirectives: ResolvedDirectives? = directives.isEmpty ? nil : directives
                var music = MomentReferenceResolver.parseMusicIntent(snapshotText)
                if !musicSuffix.isEmpty { clarification = outcome.unsupportedMusicNote }  // non-blocking note

                // OPTIONAL style presets (Phase B, decisions 2B–2E). Applied PER OUTPUT ONLY: the preset phrase
                // is APPENDED after the user's own soft text (NL wins, 2D); the music seed is used ONLY when the
                // user expressed no music preference of their own (2D). Nothing here writes durable Story
                // CreativeIntent — the phrase rides soft_direction and the moods ride ParsedMusicIntent, both
                // per-attempt (2E). None selected => byte-identical to before.
                let contribution = StylePresetContribution.from(
                    selectedPresets, userHasMusicPreference: music.preference != nil)
                var effectiveSoft = snapshotText
                // Soft quick shortcuts ride soft_direction AFTER interpretation (never interpreted, so they can
                // never raise a clarify). Stable order; user's own words always come first.
                let shortcutSuffix = QuickShortcut.allCases
                    .filter { snapshotShortcuts.contains($0) }.map(\.phrase).joined(separator: ". ")
                if !shortcutSuffix.isEmpty {
                    effectiveSoft = effectiveSoft.isEmpty ? shortcutSuffix : effectiveSoft + ". " + shortcutSuffix
                }
                if !contribution.directionSuffix.isEmpty {
                    effectiveSoft = effectiveSoft.isEmpty
                        ? contribution.directionSuffix
                        : effectiveSoft + ". " + contribution.directionSuffix
                }
                if music.preference == nil, !contribution.musicMoodTags.isEmpty {
                    let phrase = selectedPresets.count == 1
                        ? (selectedPresets.first?.label.lowercased() ?? "") + " music"
                        : contribution.musicMoodTags.joined(separator: " · ") + " music"
                    music.preference = (phrase: phrase, moodTags: contribution.musicMoodTags)
                }

                onCreate(p1dChosenSeconds, sound, p1dMode, approach, finalDirectives,
                         effectiveSoft, snapshotChips.map(\.id), music, snapshotSequence)
            }
        }
    }

    /// Clarification copy for an unresolved/ambiguous interpretation. Numeric unresolved refs name the Moment
    /// numbers (the picker lets the user pick visually); a non-numeric (semantic) ambiguity asks to rephrase or
    /// use the picker — never silently dropped (#2/#6).
    private func clarificationText(_ o: InterpretationOutcome) -> String {
        if !o.unresolvedMomentNumbers.isEmpty {
            let list = o.unresolvedMomentNumbers.map { "Moment \($0)" }.joined(separator: ", ")
            return "\(list) couldn't be matched (this Story has \(numbering.count)). Choose Moments with “Arrange Moments”, or rephrase."
        }
        if !o.unresolved.isEmpty {
            // "Add Moment reference" no longer exists on this screen; point at what does.
            return "I couldn’t apply: “" + o.unresolved.joined(separator: "”, “")
                + "”. Try rephrasing it, or use “Arrange Moments” to set the order."
        }
        if let b = o.blocking.first { return b }
        return "Please rephrase your instruction so I can apply it."
    }

    // MARK: - row builders

    @ViewBuilder
    private func section<Content: View>(title: String, subtitle: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
            Text(subtitle).font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textMuted)
            VStack(spacing: 10) { content() }.padding(.top, 2)
        }
    }

    // MARK: - P1-D section builders

    /// VIDEO TYPE (§4) — the two primary cards. Highlights left, Full Story right; gold ring + check on the
    /// selected one. Each card carries its blurb and a type-aware approximate estimate (omitted when none).
    @ViewBuilder private var videoTypeSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Video type").font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
            HStack(alignment: .top, spacing: 12) {
                videoTypeCard(.highlights)
                videoTypeCard(.full)
            }
        }
    }

    @ViewBuilder private func videoTypeCard(_ type: VideoType) -> some View {
        let selected = videoType == type
        Button { withAnimation(.easeInOut(duration: 0.12)) { videoType = type } } label: {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(type.title).font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
                    Spacer()
                    Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(selected ? StoryTheme.gold : StoryTheme.textMuted)
                        .font(.system(size: 18))
                }
                Text(type.blurb).font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let est = cardEstimate(for: type) {
                    Text(est).font(StoryTheme.body(13)).foregroundStyle(StoryTheme.cream.opacity(0.7)).padding(.top, 2)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 112, alignment: .topLeading)
            .background(StoryTheme.surfaceAlt.opacity(selected ? 0.9 : 0.5))
            .overlay(RoundedRectangle(cornerRadius: 16)
                .stroke(selected ? StoryTheme.gold : StoryTheme.cream.opacity(0.10), lineWidth: selected ? 2 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(type.title). \(type.blurb)\(cardEstimate(for: type).map { ". " + $0 } ?? "")")
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
    }

    /// Suggestion chips (§6): 2–3 initially, type-adapted, insert via append (never replacing typed text) so
    /// directive semantics are unchanged. The Moment-reference picker stays accessible but unobtrusive.
    @ViewBuilder private var suggestionChipRow: some View {
        FlowLayout(spacing: 8) {
            // Customize UX v2 §8 — actionable quick shortcuts. Structural ones (Arrange / Start with / End
            // with / Use every Moment) reuse the STORYBOARD so there is ONE ordering system (never a second
            // competing one, never "type a Moment number"). The rest append plain NL text to the draft.
            ForEach(QuickShortcut.allCases, id: \.self) { sc in
                let on = softShortcuts.contains(sc)
                Button { handleShortcut(sc) } label: {
                    HStack(spacing: 5) {
                        Image(systemName: on ? "checkmark" : sc.icon).font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(on ? StoryTheme.ink : (sc.isStructural ? StoryTheme.gold : StoryTheme.textSecondary))
                        Text(sc.label).font(StoryTheme.body(13, .medium))
                            .foregroundStyle(on ? StoryTheme.ink : StoryTheme.cream)
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(on ? StoryTheme.cream : Color.clear, in: Capsule())
                    .overlay(Capsule().stroke(
                        on ? StoryTheme.gold
                           : (sc.isStructural ? StoryTheme.gold : StoryTheme.cream).opacity(sc.isStructural ? 0.5 : 0.14),
                        lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(sc.accessibilityLabel)
                .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
            }
        }
    }

    /// The §8 quick-editing shortcuts. `isStructural` ones drive the storyboard (one ordering system);
    /// the others append a supported NL phrase to the creative-direction draft.
    private enum QuickShortcut: CaseIterable {
        case arrange, startWith, endWith, useEvery, shorterShots, longerShots, cutToBeat, keepAudio

        var label: String {
            switch self {
            case .arrange:      return "Arrange Moments"
            case .startWith:    return "Start with…"
            case .endWith:      return "End with…"
            case .useEvery:     return "Use every Moment"
            case .shorterShots: return "Shorter shots"
            case .longerShots:  return "Longer scenic shots"
            case .cutToBeat:    return "Cut to the beat"
            case .keepAudio:    return "Keep original audio"
            }
        }
        /// Structural shortcuts reuse the storyboard (ordering/inclusion), so they open Arrange rather than
        /// typing text. Non-structural ones are soft creative phrases appended to the NL draft.
        var isStructural: Bool {
            switch self {
            case .arrange, .startWith, .endWith, .useEvery: return true
            default: return false
            }
        }
        var icon: String {
            switch self {
            case .arrange:      return "rectangle.stack"
            case .startWith:    return "arrow.up.to.line"
            case .endWith:      return "arrow.down.to.line"
            case .useEvery:     return "square.grid.2x2"
            case .shorterShots: return "scissors"
            case .longerShots:  return "mountain.2"
            case .cutToBeat:    return "metronome"
            case .keepAudio:    return "waveform"
            }
        }
        /// The NL phrase appended for a non-structural shortcut (a SUPPORTED soft-direction phrasing — owner
        /// §8: shot-duration hints refer to output EXCERPTS, never promise exact per-shot timing).
        var phrase: String {
            switch self {
            case .shorterShots: return "Prefer shorter, punchier shots"
            case .longerShots:  return "Let the scenic shots breathe a little longer"
            case .cutToBeat:    return "Make the cuts follow the music"
            case .keepAudio:    return "Keep the original audio from the clips"
            default:            return ""
            }
        }
        var accessibilityLabel: String {
            isStructural ? "\(label): opens the storyboard" : "Add instruction: \(label)"
        }
    }

    /// Route a quick shortcut. Structural -> the storyboard (ONE ordering system, owner §8); the user picks
    /// the opening/ending/order visually there, never by typing a Moment number. Soft -> append NL text.
    private func handleShortcut(_ sc: QuickShortcut) {
        switch sc {
        case .arrange, .startWith, .endWith:
            // All three open the same storyboard. Start/End are framed by the storyboard's first/last slot
            // (role labels Opening/Ending), so there is no separate opening/ending directive UI to drift.
            showArrange = true
        case .useEvery:
            // "Use every Moment" = at least an excerpt from each eligible Moment (owner §8), expressed as an
            // active sequence over ALL Moments. Policy stays .allowOthers (require each; order is the snapshot
            // order the user can then rearrange) — NOT .onlySelected, since "use every" is about inclusion.
            var seq = MomentSequence(orderedIds: momentSequence.orderedIds, policy: momentSequence.policy)
            seq.addAll(numbering.items.map(\.id))
            momentSequence = seq
            showArrange = true   // open so the user can see/confirm/reorder; nothing is silently forced
        default:
            // Soft preference: a TOGGLE, not text. It is added to the planner's soft_direction at submit (like
            // the Mood preset) and never goes through the AI interpreter — the interpreter files a pacing/music
            // sentence under "unsupported" at times, which blocked Create with a misleading clarify message.
            if softShortcuts.contains(sc) { softShortcuts.remove(sc) } else { softShortcuts.insert(sc) }
        }
    }

    /// Append a suggestion to the creative-direction draft (never replace), mirroring PromptSuggestionChips so
    /// a chip never silently discards previously typed instructions (§6).
    private func appendSuggestion(_ fragment: String) {
        let cur = creativeDirection.trimmingCharacters(in: .whitespacesAndNewlines)
        if cur.isEmpty { creativeDirection = fragment }
        else {
            let sep = (cur.hasSuffix(".") || cur.hasSuffix("!") || cur.hasSuffix("?")) ? " " : ". "
            creativeDirection = cur + sep + fragment
        }
        interpretToken = UUID()
        if retryableInstruction != nil { retryableInstruction = nil; clarification = nil }
    }

    /// Type-adapted suggestions (§6): a small, non-mandatory set. Reuses the existing supported directive
    /// phrasings; Highlights leans visual/pace, Full Story leans coverage — plus the shared "keep original audio".
    private var p1dSuggestions: [String] {
        switch videoType {
        case .highlights: return ["Beautiful views first", "Follow the music", "Keep original audio"]
        case .full:       return ["Show the whole journey", "Follow the music", "Keep original audio"]
        }
    }

    /// MOMENT SEQUENCE (Customize UX v2 §3/§4) — a compact row: "AI chooses order" by default, or a short
    /// summary of the arranged sequence, with an "Arrange" button opening the storyboard sheet. Tapping the
    /// row (or Arrange) opens ArrangeMomentsSheet. No all-Moment chips on the main screen (owner §3).
    @ViewBuilder private var momentSequenceSection: some View {
        Button { showArrange = true } label: {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Moment sequence").font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
                    Text(sequenceSummary).font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                HStack(spacing: 5) {
                    Text(momentSequence.isActive ? "Edit" : "Arrange")
                        .font(StoryTheme.body(14, .medium)).foregroundStyle(StoryTheme.cream)
                    Image(systemName: "arrow.right").font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(StoryTheme.cream)
                }
                .padding(.horizontal, 14).padding(.vertical, 9)
                .overlay(Capsule().stroke(StoryTheme.cream.opacity(0.25), lineWidth: 1))
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Moment sequence. \(sequenceSummary)")
        .accessibilityHint("Opens the storyboard to choose and arrange Moments")
    }

    /// The compact one-line summary under "Moment sequence". Default = "AI chooses order"; active = the order
    /// + policy in plain words. Never presents the order as a guarantee (owner §6 — "intended").
    private var sequenceSummary: String {
        guard momentSequence.isActive else { return "AI chooses order" }
        let nums = momentSequence.orderedIds.compactMap { numbering.number(forId: $0) }.map(String.init)
        let order = nums.joined(separator: " → ")
        let policy = momentSequence.policy == .onlySelected ? "only these Moments" : "others allowed between"
        return "\(nums.count) arranged · \(order) · \(policy)"
    }

    /// FEELING / STYLE (§7) — optional, initial small set (Cinematic/Energetic/Emotional/Playful) with an
    /// unobtrusive reveal for the rest. Multi-select, independent of Video Type, folded per-output only.
    @ViewBuilder private var feelSection: some View {
        // Customize UX v2 §9 — ONE compact optional row, not a chip grid. Shows the chosen mood or "No
        // preference"; tapping opens a single-select sheet (5 options + Clear). Mood is a SOFT preference: it
        // rides soft_direction + the music seed EXACTLY as before (selectedPresets is still the plumbing), so
        // nothing downstream changes — it just never overrides ordering/inclusion/sound/music decisions (§9).
        Button { showMoodSheet = true } label: {
            HStack {
                Text("Mood").font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
                Text("Optional").font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textMuted)
                Spacer()
                HStack(spacing: 5) {
                    Text(moodLabel).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream.opacity(0.85))
                    Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(StoryTheme.textMuted)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Mood, optional. \(moodLabel)")
        .accessibilityHint("Opens a list of moods to choose one")
    }

    /// The 5 compact §9 moods, each a friendly label over an existing StylePreset (so the soft-direction +
    /// music-seed plumbing is unchanged). Single-select: choosing one replaces any prior; Clear empties it.
    private var moodOptions: [(label: String, preset: StylePreset)] {
        [("Calm & scenic", .calm), ("Fast & energetic", .energetic), ("Warm & personal", .emotional),
         ("Playful", .playful), ("Cinematic", .cinematic)]
    }

    /// The row's trailing text: the chosen mood's friendly label, or "No preference" when none is set.
    private var moodLabel: String {
        guard let p = selectedPresets.first,
              let m = moodOptions.first(where: { $0.preset == p }) else { return "No preference" }
        return m.label
    }

    /// The single-select Mood sheet (§9): 5 options + Clear. Choosing one sets exactly one preset (mood is
    /// single-select here even though selectedPresets is a Set — we keep at most one so downstream phrasing is
    /// a single clear mood, never a pile of conflicting feels).
    @ViewBuilder private var moodSheet: some View {
        NavigationStack {
            List {
                ForEach(moodOptions, id: \.preset) { opt in
                    Button {
                        selectedPresets = [opt.preset]; showMoodSheet = false
                    } label: {
                        HStack {
                            Text(opt.label).foregroundStyle(StoryTheme.cream)
                            Spacer()
                            if selectedPresets.first == opt.preset {
                                Image(systemName: "checkmark").foregroundStyle(StoryTheme.gold)
                            }
                        }
                    }
                    .listRowBackground(StoryTheme.surface)
                }
                Button(role: .destructive) {
                    selectedPresets = []; showMoodSheet = false
                } label: { Text("Clear — no preference") }
                    .listRowBackground(StoryTheme.surface)
            }
            .scrollContentBackground(.hidden).background(StoryTheme.ink)
            .navigationTitle("Overall mood").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { showMoodSheet = false }.foregroundStyle(StoryTheme.gold)
                }
            }
        }
        .presentationDetents([.medium])
    }

    /// MORE OPTIONS (§8) — one collapsed-by-default section holding Duration · Sound · Music.
    @ViewBuilder private var moreOptionsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button { withAnimation(.easeInOut(duration: 0.15)) { moreOptionsExpanded.toggle() } } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("More options").font(StoryTheme.body(17, .semibold)).foregroundStyle(StoryTheme.cream)
                        Text("Duration · Sound · Music").font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textMuted)
                    }
                    Spacer()
                    Image(systemName: moreOptionsExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(StoryTheme.textMuted)
                }
            }.buttonStyle(.plain)
            .accessibilityLabel("More options. Duration, Sound, Music. \(moreOptionsExpanded ? "Expanded" : "Collapsed")")
            if moreOptionsExpanded {
                durationSection
                soundSection
            }
        }
    }

    /// DURATION (§8) — independent of type: Recommended (type-aware) or Custom. Highlights/Full are NEVER
    /// duration choices here.
    @ViewBuilder private var durationSection: some View {
        section(title: "Duration", subtitle: "Recommended is tuned to your video type, or set your own.") {
            row(selected: durationChoice == .recommended, title: "Recommended",
                detail: videoType == .highlights ? "A concise highlights length" : "Room for the fuller story",
                trailing: typeRecommendedSeconds.map { "~\(Int($0.rounded()))s" }) { durationChoice = .recommended }
            row(selected: durationChoice == .custom, title: "Custom",
                detail: "Set a specific length", trailing: "Your choice") { durationChoice = .custom }
            if durationChoice == .custom {
                HStack(spacing: 12) {
                    TextField("seconds", value: $customSeconds, format: .number)
                        .keyboardType(.numberPad)
                        .font(StoryTheme.display(20)).foregroundStyle(StoryTheme.cream)
                        .frame(width: 90).padding(.horizontal, 12).padding(.vertical, 8)
                        .background(StoryTheme.surfaceAlt).clipShape(RoundedRectangle(cornerRadius: 10))
                    Text("seconds").font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textSecondary)
                    Spacer()
                    Stepper("", value: $customSeconds, in: floor...ceiling, step: 1).labelsHidden()
                }
                Text("\(Int(floor))–\(Int(ceiling))s fits your footage")
                    .font(StoryTheme.body(12)).foregroundStyle(StoryTheme.textMuted)
            }
        }
    }

    // Advanced subsections (Sound retained under More Options; Story-length replaced by durationSection and
    // Editing-approach removed entirely per P1-D §5 — approach is forced .storytelling at init).
    @ViewBuilder private var soundSection: some View {
        section(title: "Sound", subtitle: "How should your Story feel and sound?") {
            soundRow(.immersive, "Immersive", "Bring natural sounds, voices and atmosphere forward")
            soundRow(.balanced, "Balanced", "Blend original sounds with background music")
            soundRow(.musicLed, "Music-led", "Let the soundtrack lead the experience")
        }
    }

    @ViewBuilder
    private func soundRow(_ value: SoundPreference, _ title: String, _ detail: String) -> some View {
        let isRec = (initialExplicitSound == nil && inferredSound == value)
        row(selected: sound == value, title: title,
            detail: detail, trailing: isRec ? "Recommended" : nil) { sound = value }
    }

    /// A whole-row tappable option with an obvious selected state (gold ring + check).
    @ViewBuilder
    private func row(selected: Bool, title: String, detail: String, trailing: String?, _ tap: @escaping () -> Void) -> some View {
        Button(action: tap) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? StoryTheme.gold : StoryTheme.textMuted)
                    .font(.system(size: 18))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(StoryTheme.body(16, .medium)).foregroundStyle(StoryTheme.cream)
                    Text(detail).font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textSecondary)
                        .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if let trailing {
                    Text(trailing).font(StoryTheme.body(13)).foregroundStyle(selected ? StoryTheme.gold : StoryTheme.textMuted)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(StoryTheme.surfaceAlt.opacity(selected ? 0.9 : 0.5))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(selected ? StoryTheme.gold : StoryTheme.cream.opacity(0.08), lineWidth: 1.5))
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }
}
