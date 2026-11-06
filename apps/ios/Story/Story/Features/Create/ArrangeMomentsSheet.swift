import SwiftUI

// Arrange Moments — the Customize UX v2 visual storyboard (owner "Customize UX v2" 2026-11-06, §4/§5/§7).
//
// Replaces the ambiguous include-only Moment picker. The user ADDS Moments to an explicit sequence, reorders
// by drag (native) OR tap (accessible alternative), and picks a POLICY (allow others between / only
// selected). Order and inclusion are explicit and VISIBLE — no hidden must_include. Default (nothing
// arranged) imposes nothing: "AI chooses order".
//
// Emits a MomentSequence (stable ids + policy) on Save — the single source of truth the Customize screen
// serializes to directives (Policy A) and/or an allowed-source-set (Policy B). Thumbnails/durations come from
// the existing numbering snapshot + MomentThumbnailCache (no new extraction, no media copy).
//
// Ordering is an OBJECTIVE end-to-end (owner decision): the copy here says "intended order", never promises
// the final cut will match exactly — the Customize screen shows the validated result separately.

struct ArrangeMomentsSheet: View {
    let numbering: StoryMomentNumbering
    let momentForId: (UUID) -> MomentModel?
    /// The sequence to edit (seeded from the current draft so reopening is non-destructive — owner §4).
    let initial: MomentSequence
    /// Returns the arranged sequence on Save (or an inactive one if the user cleared it).
    let onSave: (MomentSequence) -> Void

    @Environment(\.dismiss) private var dismiss

    // Working state. `orderedIds` is the sequence; `policy` the inclusion rule. Identity = UUID, never index.
    @State private var orderedIds: [UUID]
    @State private var policy: SequencePolicy
    @State private var showAdder = false
    /// Tap-reorder (accessibility): the id currently "picked up". Tapping another slot moves the picked id
    /// before it; tapping the same slot cancels. A keyboard/VoiceOver-friendly alternative to drag (owner §4).
    @State private var tapMoveId: UUID?
    /// The card currently highlighted as the drop target while a Moment is being dragged over it.
    @State private var dropTargetId: UUID?

    init(numbering: StoryMomentNumbering,
         momentForId: @escaping (UUID) -> MomentModel?,
         initial: MomentSequence,
         onSave: @escaping (MomentSequence) -> Void) {
        self.numbering = numbering
        self.momentForId = momentForId
        self.initial = initial
        self.onSave = onSave
        _orderedIds = State(initialValue: initial.orderedIds)
        _policy = State(initialValue: initial.policy)
    }

    private var sequence: MomentSequence { MomentSequence(orderedIds: orderedIds, policy: policy) }
    private func number(_ id: UUID) -> Int? { numbering.number(forId: id) }

    /// Moments not yet in the sequence (candidates for "Add"). Snapshot order for a stable picker.
    private var available: [UUID] {
        let inSeq = Set(orderedIds)
        return numbering.items.map(\.id).filter { !inSeq.contains($0) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Choose the Moments you want to show, then drag to arrange them.")
                        .font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textSecondary)

                    header
                    if orderedIds.isEmpty { emptyState } else { storyboard }

                    addRow
                    Divider().overlay(StoryTheme.cream.opacity(0.1))
                    policySection
                    disclosure
                }
                .padding(StoryTheme.screenPadding)
            }
            .background(StoryTheme.ink)
            .navigationTitle("Arrange Moments")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.foregroundStyle(StoryTheme.textSecondary)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { onSave(sequence); dismiss() }
                        .fontWeight(.semibold).foregroundStyle(StoryTheme.gold)
                }
            }
            .sheet(isPresented: $showAdder) {
                MomentReferencePicker(
                    numbering: numbering, momentForId: momentForId,
                    alreadyReferenced: Set(orderedIds),
                    onConfirm: { ids in
                        // Preserve existing order; append newly-chosen ids in snapshot order; never duplicate.
                        var seq = MomentSequence(orderedIds: orderedIds, policy: policy)
                        seq.addAll(numbering.items.map(\.id).filter { ids.contains($0) })
                        orderedIds = seq.orderedIds
                    })
            }
        }
    }

    // ---- header: Your sequence + Drag-to-reorder hint / Reset ----------------------------------------

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Your sequence").font(StoryTheme.body(16, .semibold)).foregroundStyle(StoryTheme.cream)
            Spacer()
            if orderedIds.isEmpty {
                Text("Press and hold to drag").font(StoryTheme.body(12)).foregroundStyle(StoryTheme.textMuted)
            } else {
                Button("Reset to AI order") { orderedIds = []; tapMoveId = nil }
                    .font(StoryTheme.body(13)).foregroundStyle(StoryTheme.gold)
                    .accessibilityHint("Clears the sequence so the editor chooses the order")
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "rectangle.stack.badge.plus")
                .font(.system(size: 28)).foregroundStyle(StoryTheme.textMuted)
            Text("No sequence yet — the editor chooses the order.")
                .font(StoryTheme.body(13)).foregroundStyle(StoryTheme.textSecondary)
            Text("Add Moments below to arrange them yourself.")
                .font(StoryTheme.body(12)).foregroundStyle(StoryTheme.textMuted)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 20)
        .background(StoryTheme.surface, in: RoundedRectangle(cornerRadius: StoryTheme.field))
    }

    // ---- storyboard: the ordered cards, drag + tap reorder -------------------------------------------

    private var storyboard: some View {
        // NOTE: `.onMove` only works inside a List, not a VStack — it never fired here. Reordering is done with
        // native drag-and-drop on each card instead (`draggable` + `dropDestination`, see `card`), which works
        // in a ScrollView, lifts the card under the finger, and keeps scrolling usable (press-and-hold to drag).
        VStack(spacing: 10) {
            ForEach(orderedIds, id: \.self) { id in
                card(index: orderedIds.firstIndex(of: id) ?? 0, id: id)
            }
        }
    }

    /// Drop `dragged` onto the card `target`: the dragged Moment takes the target's position (identity-based,
    /// via MomentSequence.move so the order logic is the single tested implementation).
    private func moveDragged(_ dragged: UUID, onto target: UUID) {
        guard dragged != target,
              let from = orderedIds.firstIndex(of: dragged),
              let to = orderedIds.firstIndex(of: target) else { return }
        var seq = MomentSequence(orderedIds: orderedIds, policy: policy)
        seq.move(from: from, to: to)
        withAnimation(.easeInOut(duration: 0.18)) { orderedIds = seq.orderedIds }
        tapMoveId = nil
    }

    /// The lifted-card preview shown under the finger while dragging.
    private func dragPreview(_ id: UUID) -> some View {
        HStack(spacing: 10) {
            thumb(id).frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: StoryTheme.field))
            Text(number(id).map { "Moment \($0)" } ?? "Moment")
                .font(StoryTheme.body(15, .semibold)).foregroundStyle(StoryTheme.cream)
        }
        .padding(8)
        .background(StoryTheme.surface, in: RoundedRectangle(cornerRadius: StoryTheme.field))
    }

    /// One storyboard card. Shows the thumbnail, Moment number, duration, a role label (Opening/Next/Ending),
    /// a drag handle, a remove button, and an accessible tap-to-move control. Indices are render-only.
    private func card(index idx: Int, id: UUID) -> some View {
        let role = roleLabel(idx)
        let isPicked = tapMoveId == id
        return HStack(spacing: 12) {
            thumb(id)
                .frame(width: 84, height: 84)
                .clipShape(RoundedRectangle(cornerRadius: StoryTheme.field))
                .overlay(RoundedRectangle(cornerRadius: StoryTheme.field)
                    .stroke(isPicked ? StoryTheme.gold : Color.clear, lineWidth: 2))

            VStack(alignment: .leading, spacing: 3) {
                Text(number(id).map { "Moment \($0)" } ?? "Moment")
                    .font(StoryTheme.body(15, .semibold)).foregroundStyle(StoryTheme.cream)
                Text(role).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.gold)
                if let secs = durationSeconds(id) {
                    Text(secs >= 1 ? "\(Int(secs.rounded()))s clip" : String(format: "%.1fs clip", secs))
                        .font(StoryTheme.body(11)).foregroundStyle(StoryTheme.textMuted)
                }
            }
            Spacer(minLength: 0)

            // Accessible tap-reorder: pick up, then tap another card to drop before it (owner §4 alternative).
            Button {
                handleTapMove(on: id)
            } label: {
                Image(systemName: isPicked ? "arrow.up.arrow.down.circle.fill" : "arrow.up.arrow.down.circle")
                    .font(.system(size: 20)).foregroundStyle(isPicked ? StoryTheme.gold : StoryTheme.textSecondary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(isPicked ? "Cancel move of Moment \(number(id) ?? 0)"
                                         : "Move Moment \(number(id) ?? 0)")
            .accessibilityHint(tapMoveId == nil ? "Double-tap, then double-tap another Moment to place this before it"
                                                : "Double-tap another Moment to place this before it")

            Button(role: .destructive) {
                orderedIds.removeAll { $0 == id }
                if tapMoveId == id { tapMoveId = nil }
            } label: {
                Image(systemName: "xmark.circle.fill").font(.system(size: 20))
                    .foregroundStyle(StoryTheme.textMuted)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Remove Moment \(number(id) ?? 0) from the sequence")

            Image(systemName: "line.3.horizontal").font(.system(size: 16))
                .foregroundStyle(StoryTheme.textMuted).accessibilityHidden(true)
        }
        .padding(10)
        .background(StoryTheme.surface, in: RoundedRectangle(cornerRadius: StoryTheme.field))
        // Gold ring on the card currently under a dragged Moment, so the drop position is obvious.
        .overlay(RoundedRectangle(cornerRadius: StoryTheme.field)
            .stroke(dropTargetId == id ? StoryTheme.gold : Color.clear, lineWidth: 2))
        .contentShape(Rectangle())
        .onTapGesture { if tapMoveId != nil { handleTapMove(on: id) } }
        // Native drag-and-drop: press-and-hold the card, drag, release on another card.
        .draggable(id.uuidString) { dragPreview(id) }
        .dropDestination(for: String.self) { items, _ in
            guard let raw = items.first, let dragged = UUID(uuidString: raw) else { return false }
            moveDragged(dragged, onto: id)
            dropTargetId = nil
            return true
        } isTargeted: { targeted in
            if targeted { dropTargetId = id } else if dropTargetId == id { dropTargetId = nil }
        }
    }

    /// Tap-reorder state machine: first tap picks up `id`; a second tap on a DIFFERENT card moves the picked
    /// id to that card's position; tapping the same card cancels. Identity-based, never index-based.
    private func handleTapMove(on id: UUID) {
        guard let picked = tapMoveId else { tapMoveId = id; return }
        if picked == id { tapMoveId = nil; return }
        guard let fromIdx = orderedIds.firstIndex(of: picked),
              let toIdx = orderedIds.firstIndex(of: id) else { tapMoveId = nil; return }
        var seq = MomentSequence(orderedIds: orderedIds, policy: policy)
        seq.move(from: fromIdx, to: toIdx)
        orderedIds = seq.orderedIds
        tapMoveId = nil
    }

    private func roleLabel(_ idx: Int) -> String {
        if idx == 0 { return "Opening" }
        if idx == orderedIds.count - 1 { return "Ending" }
        return "Next"
    }

    // ---- add row: Add Moments + Add all --------------------------------------------------------------

    private var addRow: some View {
        HStack(spacing: 10) {
            Button { showAdder = true } label: {
                Label("Add Moments", systemImage: "plus")
                    .font(StoryTheme.body(14, .medium)).foregroundStyle(StoryTheme.gold)
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(StoryTheme.surface, in: Capsule())
                    .overlay(Capsule().stroke(StoryTheme.gold.opacity(0.4), lineWidth: 1))
            }
            .buttonStyle(.plain)
            .disabled(available.isEmpty)

            if !available.isEmpty {
                Button("Add all") {
                    var seq = MomentSequence(orderedIds: orderedIds, policy: policy)
                    seq.addAll(numbering.items.map(\.id))   // snapshot order; never duplicates
                    orderedIds = seq.orderedIds
                }
                .font(StoryTheme.body(14)).foregroundStyle(StoryTheme.textSecondary)
                .accessibilityHint("Adds every Moment to the sequence in their current order")
            }
            Spacer()
        }
    }

    // ---- policy: allow others vs only selected -------------------------------------------------------

    private var policySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What about the other Moments?")
                .font(StoryTheme.body(15, .semibold)).foregroundStyle(StoryTheme.cream)
            policyRow(.allowOthers, "AI can include other Moments between these")
            policyRow(.onlySelected, "Use only the selected Moments")
        }
        .opacity(orderedIds.isEmpty ? 0.4 : 1)
        .disabled(orderedIds.isEmpty)
    }

    private func policyRow(_ value: SequencePolicy, _ label: String) -> some View {
        Button { policy = value } label: {
            HStack(spacing: 10) {
                Image(systemName: policy == value ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(policy == value ? StoryTheme.gold : StoryTheme.textMuted)
                Text(label).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream)
                Spacer()
            }
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(policy == value ? [.isSelected] : [])
    }

    // ---- disclosure: plain-language meaning (intended order, never a guarantee — owner §6) -----------

    private var disclosure: some View {
        Text(disclosureText).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.textMuted)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var disclosureText: String {
        guard !orderedIds.isEmpty else {
            return "The editor will choose the order. Add Moments above to arrange them yourself."
        }
        let nums = orderedIds.compactMap { number($0) }.map(String.init).joined(separator: ", ")
        switch policy {
        case .allowOthers:
            return "Moments \(nums) are required in this intended order. The editor may include other Moments "
                 + "between them, and will keep your order when the footage allows."
        case .onlySelected:
            return "Only Moments \(nums) will be used, in this intended order. The editor keeps your order "
                 + "when the footage allows; if it can't fully honor it, the result is shown honestly rather "
                 + "than forced."
        }
    }

    // ---- thumbnail + duration (reuse existing cache + snapshot) --------------------------------------

    @ViewBuilder
    private func thumb(_ id: UUID) -> some View {
        if let m = momentForId(id) {
            ArrangeThumb(moment: m)
        } else {
            RoundedRectangle(cornerRadius: StoryTheme.field).fill(StoryTheme.surfaceAlt)
                .overlay(Image(systemName: "film").foregroundStyle(StoryTheme.textMuted))
        }
    }

    private func durationSeconds(_ id: UUID) -> Double? {
        numbering.items.first { $0.id == id }?.durationSeconds
    }
}

/// Live thumbnail for a storyboard card (reuses MomentThumbnailCache — no new extraction, no media copy).
private struct ArrangeThumb: View {
    let moment: MomentModel
    @State private var img: UIImage?
    var body: some View {
        Color.clear
            .overlay {
                if let img { Image(uiImage: img).resizable().scaledToFill() }
                else { StoryTheme.surfaceAlt.overlay(Image(systemName: "film").foregroundStyle(StoryTheme.textMuted)) }
            }
            .clipped()
            .task { img = await MomentThumbnailCache.shared.thumbnail(for: moment) }
    }
}
