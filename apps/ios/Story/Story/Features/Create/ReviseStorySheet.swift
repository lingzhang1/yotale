import SwiftUI

// Post-generation Natural-Language Revision — the Revise entry. Shares the SAME interpretation
// (InterpretationCoordinator / MomentReferenceResolver) and, since Customize UX v2, the SAME Arrange Moments
// storyboard as pre-creation Customize (ArrangeMomentsSheet, `.revise` mode) instead of the old include-only
// Moment picker. The user types a change and/or repositions Moments; on Apply we resolve them into hard
// directives + a soft-direction string and hand them to the coordinator's Revise path, which carries the
// EXACT base plan so unaffected edits are preserved. In Revise the storyboard only REPOSITIONS (others stay).
//
// SOURCE-MOMENT vs GENERATED-SEGMENT (owner Phase F): this sheet references SOURCE Moments only
// ("include/exclude/start-with Moment N"). A segment-occurrence reference ("remove the third shot") is a
// DIFFERENT concept and is intentionally NOT a Moment reference — it is left as free-text soft direction and
// not parsed as a Moment number, so the two can never be conflated.
struct ReviseStorySheet: View {
    let story: StoryModel
    let base: GeneratedOutputModel
    /// Display label of the version being edited ("V3"), shown as "Editing Version N" so the user knows which
    /// version a revise acts on. The selected versionId is captured by the caller at op start (not the latest).
    var versionLabel: String = L10n.t("this version")
    /// Apply the revision: resolved hard directives + the raw instruction (soft direction).
    let onApply: (ResolvedDirectives, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var instruction = ""
    // Customize UX v2: the storyboard replaces the old include-only Moment picker + chip list. In Revise it only
    // REPOSITIONS the chosen Moments (policy is always "others stay" — see ArrangeMomentsSheet.Mode.revise).
    // Inactive by default = "keep the current order".
    @State private var momentSequence = MomentSequence()
    @State private var showArrange = false
    @State private var clarification: String?
    // Pre-submit capability confirmation (Phase 4): a mixed supported+unsupported ask confirms partial
    // execution before planning; a fully-unsupported ask is blocked with an explanation and never planned.
    // Instant + local — the backend guard remains authoritative.
    @State private var confirmPartial: String?     // non-nil => show the partial-execution confirm alert
    @State private var unsupportedBlock: String?   // non-nil => show the fully-unsupported explanation alert
    // Interpretation lifecycle (owner safeguards #1/#2) — mirror of CustomizeYourStoryView.
    @State private var isInterpreting = false
    @State private var interpretToken = UUID()
    @Environment(AuthStore.self) private var auth
    @Environment(\.modelContext) private var modelContext
    @State private var cloudGate = CloudAuthGateModel()
    @State private var retryable = false

    // Number ALL linked Moments by stable StoryMomentLink order (cloud-only included) so "Moment N" is the same
    // Moment on every device; local availability is a per-item badge, never a filter (owner P0).
    private var numbering: StoryMomentNumbering { StoryMomentNumbering(story: story.moments) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("What would you like to change?")
                        .font(StoryTheme.displayItalic(24)).foregroundStyle(StoryTheme.cream)
                    // Phase 3 — selected-version clarity. Names the version this revise acts on (captured at op
                    // start by the caller, never defaulted to latest) and states the preservation default.
                    Text("Editing \(versionLabel)")
                        .font(StoryTheme.body(13, .semibold)).foregroundStyle(StoryTheme.gold)
                    Text("Story keeps the existing edit unless you ask to change it.")
                        .font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textSecondary)

                    StoryTextField(placeholder: "Start with Moment 8, drop Moment 4, make it more cinematic…",
                                   text: $instruction, minHeight: 140)
                        .onChange(of: instruction) { _, _ in
                            interpretToken = UUID()
                            if retryable { retryable = false; clarification = nil }
                        }

                    if !story.moments.isEmpty { momentOrderRow }
                    if let clarification {
                        Text(clarification).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.danger)
                    }
                    if retryable {
                        Button { apply() } label: {
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
                    PromptSuggestionChips(
                        title: L10n.t("Try asking Story…"),
                        suggestions: PromptSuggestions.revise(firstMomentNumber: numbering.items.first?.number),
                        text: $instruction,
                        onInsert: { interpretToken = UUID(); if retryable { retryable = false; clarification = nil } })
                    CapabilityInfoButton()
                    Spacer(minLength: 8)
                }
                .padding(StoryTheme.screenPadding)
            }
            .background(StoryTheme.ink)
            .navigationTitle("Revise").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { interpretToken = UUID(); dismiss() }.foregroundStyle(StoryTheme.textSecondary)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isInterpreting ? L10n.t("Understanding…") : L10n.t("Apply")) { apply() }
                        .fontWeight(.semibold)
                        .foregroundStyle((canApply && !isInterpreting) ? StoryTheme.gold : StoryTheme.textMuted)
                        .disabled(!canApply || isInterpreting)
                }
            }
            .sheet(isPresented: $showArrange) {
                ArrangeMomentsSheet(
                    mode: .revise,
                    numbering: numbering,
                    momentForId: { id in story.moments.first { $0.id == id } },
                    initial: momentSequence,
                    onSave: { momentSequence = $0 })
            }
            // Phase 4 — fully-unsupported ask: explain + preserve, never plan.
            .alert("Can't do that edit yet", isPresented: Binding(
                get: { unsupportedBlock != nil }, set: { if !$0 { unsupportedBlock = nil } })) {
                Button("OK", role: .cancel) { unsupportedBlock = nil }
            } message: { Text(unsupportedBlock ?? "") }
            // Phase 4 — mixed ask: confirm applying only the supported part before planning.
            .alert("Apply supported parts?", isPresented: Binding(
                get: { confirmPartial != nil }, set: { if !$0 { confirmPartial = nil } })) {
                Button("Apply supported") {
                    let t = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
                    confirmPartial = nil; proceedApply(t)
                }
                Button("Cancel", role: .cancel) { confirmPartial = nil }
            } message: { Text(confirmPartial ?? "") }
            .cloudAuthGate(cloudGate)
        }
    }

    private var canApply: Bool {
        !instruction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || momentSequence.isActive
    }

    /// "Moment order" row — mirrors Customize. Default "Keep current order"; opens the storyboard (revise mode)
    /// to reposition specific Moments. No include-only chips, no hidden must_include.
    private var momentOrderRow: some View {
        Button { showArrange = true } label: {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Moment order").font(StoryTheme.body(15, .semibold)).foregroundStyle(StoryTheme.cream)
                    Text(sequenceSummary).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                HStack(spacing: 5) {
                    Text(momentSequence.isActive ? L10n.t("Edit") : L10n.t("Arrange"))
                        .font(StoryTheme.body(13, .medium)).foregroundStyle(StoryTheme.cream)
                    Image(systemName: "arrow.right").font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(StoryTheme.cream)
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
                .overlay(Capsule().stroke(StoryTheme.cream.opacity(0.25), lineWidth: 1))
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Moment order. \(sequenceSummary)")
        .accessibilityHint("Opens the storyboard to reposition Moments")
    }

    private var sequenceSummary: String {
        guard momentSequence.isActive else { return L10n.t("Keep current order") }
        let nums = momentSequence.orderedIds.compactMap { numbering.number(forId: $0) }.map(String.init)
        return L10n.t("\(nums.count) repositioned · \(nums.joined(separator: " → "))")
    }

    private func apply() {
        guard !isInterpreting else { return }                         // duplicate-tap (#1)
        let snapshotText = instruction.trimmingCharacters(in: .whitespacesAndNewlines)
        // Phase 4 — pre-submit capability feedback (instant, local; backend remains authoritative). A fully
        // unsupported ask is explained and NOT planned (version preserved, no replacement). A mixed ask asks
        // the user to confirm applying only the supported part before any expensive planning. A chips-only
        // revise (no text) has nothing to classify.
        switch CapabilityClassifier.classify(snapshotText) {
        case .allUnsupported(let nouns):
            unsupportedBlock = L10n.t("Story can't do \(CapabilityClassifier.phrase(nouns)) yet — it re-cuts, re-times, reorders, sets transitions and changes the soundtrack. Your current version is kept. Try rephrasing with a supported change.")
            return
        case .mixed(let nouns):
            confirmPartial = L10n.t("Story can't do \(CapabilityClassifier.phrase(nouns)) yet. Apply the supported parts of your request and skip that?")
            return
        case .supported:
            break
        }
        proceedApply(snapshotText)
    }

    /// The actual interpret+apply flow (unchanged), reached once capability pre-checks pass or the user
    /// confirms partial execution. Paid NL interpretation is a cloud action — require a session first; the gate
    /// resumes THIS exact call once after sign-in (no duplicate inference, snapshot preserved).
    private func proceedApply(_ snapshotText: String) {
        cloudGate.run { self.performApply(snapshotText) }
    }

    private func performApply(_ snapshotText: String) {
        let snapshotSequence = momentSequence
        let n = numbering
        let token = UUID()
        interpretToken = token
        clarification = nil; retryable = false; isInterpreting = true

        Task {
            let outcome = await InterpretationCoordinator.interpret(
                snapshotText, numbering: n,
                summaryForId: { id in story.moments.first { $0.id == id }?.caption })
            await MainActor.run {
                guard interpretToken == token else { return }          // stale-drop (#1)
                isInterpreting = false
                let musicSuffix = outcome.unsupportedMusicNote.map { "\n\($0)" } ?? ""
                switch outcome.kind {
                case .serviceFailure:
                    retryable = true
                    clarification = (outcome.blocking.first ?? L10n.t("Couldn't interpret that right now.")) + musicSuffix
                    return
                case .clarify:
                    clarification = clarificationText(outcome, numbering: n) + musicSuffix
                    return
                case .ok:
                    break
                }
                var directives = outcome.directives
                // Surface a storyboard<->typed-text contradiction BEFORE planning (owner §10) rather than let
                // the planner reject it as a hard conflict (e.g. "drop Moment 8" typed while Moment 8 is in the
                // repositioned sequence). Block with a short, actionable message; nothing is silently dropped.
                let conflicts = snapshotSequence.conflicts(with: directives)
                if let msg = Self.conflictMessage(conflicts, numbering: n) {
                    clarification = msg
                    return
                }
                // Fold the repositioned sequence (must_include + order_after). Revise mode never restricts the
                // source set, so the base edit's other clips are preserved via the base plan carried by onApply.
                snapshotSequence.apply(to: &directives)
                if !musicSuffix.isEmpty { clarification = outcome.unsupportedMusicNote }  // non-blocking note
                // Pass the interpreter's RESIDUAL soft direction (creative leftover only), NOT the raw
                // instruction. For a pure-structural revise ("Start with Moment 1, then Moment 6, end with
                // Moment 2") the residual is empty, so the engine runs its deterministic reorder and preserves
                // every base clip (no model re-plan, no "N clips dropped" preservation violation). The raw
                // `instruction` text stays in this sheet's state for display/history (owner req #6). A genuine
                // creative residual ("make it cinematic") is preserved and still routes to the model.
                onApply(directives, outcome.softDirection)
                dismiss()
            }
        }
    }

    private func clarificationText(_ o: InterpretationOutcome, numbering: StoryMomentNumbering) -> String {
        if !o.unresolvedMomentNumbers.isEmpty {
            let list = o.unresolvedMomentNumbers.map { L10n.t("Moment \($0)") }.joined(separator: L10n.current == .zhHans ? "、" : ", ")
            return L10n.t("\(list) couldn't be matched (this Story has \(numbering.count)). Reposition it with “Arrange”, or rephrase.")
        }
        if !o.unresolved.isEmpty {
            return L10n.t("I couldn’t apply: “\(o.unresolved.joined(separator: "”, “"))”. Try rephrasing it, or use “Arrange” to set the order.")
        }
        if let b = o.blocking.first { return b }
        return L10n.t("Please rephrase your instruction so I can apply it.")
    }

    /// Plain-language message for a storyboard<->typed conflict (owner §10). nil when there is no conflict.
    private static func conflictMessage(_ conflicts: [MomentSequence.Conflict],
                                        numbering: StoryMomentNumbering) -> String? {
        func names(_ ids: [UUID]) -> String {
            ids.compactMap { numbering.number(forId: $0) }.sorted().map { L10n.t("Moment \($0)") }.joined(separator: L10n.current == .zhHans ? "、" : ", ")
        }
        for c in conflicts {
            switch c {
            case .excludedButSequenced(let ids):
                return L10n.t("\(names(ids)) is both in your arranged order and asked to be dropped. Remove it from the order, or don’t drop it.")
            case .outsideOnlySelected(let ids):
                return L10n.t("\(names(ids)) isn’t in your selected Moments. Add it in Arrange, or remove the mention.")
            case .openingDiffersFromTopCard(let typed, let top):
                return L10n.t("Your text says to start with \(names([typed])), but your order starts with \(names([top])). Drag the one you want to the top in Arrange, or edit the text.")
            case .endingDiffersFromLastCard(let typed, let last):
                return L10n.t("Your text says to end with \(names([typed])), but your order ends with \(names([last])). Drag the one you want to the bottom in Arrange, or edit the text.")
            }
        }
        return nil
    }
}
