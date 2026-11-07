import Foundation

// MomentSequence — the Customize UX v2 visual-storyboard model (owner "Customize UX v2" 2026-11-06).
//
// ONE source of truth for a user-arranged Moment order + its inclusion policy. The old Moment picker silently
// mapped every selection to must_include with no visible semantics; this model makes order + inclusion/
// exclusion EXPLICIT and derives the backend representation deterministically.
//
// Two policies (owner §5), BOTH with ordering kept as an OBJECTIVE (never promoted to HARD, no new planner
// rejection loop — owner decision 2026-11-06):
//
//   .allowOthers (Policy A): the selected ids are required (must_include) in their relative order
//     (order_after chain). OTHER eligible Moments MAY appear between them — the editor chooses. Relative
//     order, NOT adjacency.
//
//   .onlySelected (Policy B): ONLY the selected ids may contribute footage. This is enforced by the
//     planner's EXISTING eligibility mechanism — the client builds moments[] from the selected set ONLY, so
//     a segment can physically only cite a selected asset_id (EditPlanRequestBuilder: eligibleIds ==
//     moments[].id, no top-N). We do NOT rely on creative `exclude` for the allowed-set (owner: creative
//     exclude is an objective, not a guarantee). Relative order is still an OBJECTIVE (order_after chain).
//
// The model carries STABLE Moment UUIDs only; array position is render-order, never identity (owner §4).
// `isActive` distinguishes "user arranged a sequence" from the default "AI chooses order" (no sequence => no
// ordering/inclusion constraint at all; full AI editorial freedom — owner §5 Default).

/// Inclusion policy for a user-arranged Moment sequence (owner §5).
enum SequencePolicy: String, Codable, Equatable {
    /// Policy A — selected Moments required in relative order; the editor may add other eligible Moments.
    case allowOthers
    /// Policy B — only the selected Moments may be used; relative order preserved as an objective.
    case onlySelected
}

/// A user-arranged Moment sequence. Empty / inactive => AI chooses order (the default). Order is the array
/// order; identity is the UUID. A Moment never appears twice (enforced on mutation).
struct MomentSequence: Codable, Equatable {
    /// Ordered, de-duplicated stable Moment ids. Position = intended output order.
    private(set) var orderedIds: [UUID]
    var policy: SequencePolicy

    init(orderedIds: [UUID] = [], policy: SequencePolicy = .allowOthers) {
        // De-dup defensively, preserving first-seen order (owner §4: "never duplicate the same Moment").
        var seen = Set<UUID>()
        self.orderedIds = orderedIds.filter { seen.insert($0).inserted }
        self.policy = policy
    }

    /// True when the user has arranged a real sequence. An empty sequence means "AI chooses order" — the
    /// default that imposes NO ordering/inclusion constraint (owner §5 Default).
    var isActive: Bool { !orderedIds.isEmpty }

    var count: Int { orderedIds.count }

    // ---- mutation (identity-safe; never duplicates) ---------------------------------------------------

    mutating func add(_ id: UUID) {
        guard !orderedIds.contains(id) else { return }   // never duplicate (owner §4)
        orderedIds.append(id)
    }

    mutating func addAll(_ ids: [UUID]) {
        for id in ids { add(id) }
    }

    mutating func remove(_ id: UUID) {
        // Removing an ordered Moment removes ONLY its ordered requirement; it does NOT imply exclusion
        // (owner §7). Its remaining status then follows the policy + any explicit rules, never an implicit
        // reversal — for .allowOthers it becomes optional; for .onlySelected it leaves the allowed set.
        orderedIds.removeAll { $0 == id }
    }

    /// Reset to "AI chooses order" — clears the sequence (owner §4 "Reset to AI order").
    mutating func reset() { orderedIds.removeAll() }

    /// Move the Moment at `from` to `to` (drag/tap reorder). Identity-preserving; bounds-checked.
    mutating func move(from: Int, to: Int) {
        guard orderedIds.indices.contains(from) else { return }
        let clampedTo = max(0, min(to, orderedIds.count - 1))
        guard from != clampedTo else { return }
        let id = orderedIds.remove(at: from)
        orderedIds.insert(id, at: clampedTo)
    }

    // ---- derivation to the backend representation -----------------------------------------------------

    /// The relative-order pairs for the chain: [[b, a]] meaning "b comes after a" for each adjacent pair in
    /// the arranged order. This is `order_after` (relative), NOT `order_adjacent` — other Moments may fall
    /// between them in Policy A, and in Policy B the chain still only asserts relative order (owner §5:
    /// "Do not interpret relative order as immediate adjacency").
    var orderAfterPairs: [[UUID]] {
        guard orderedIds.count >= 2 else { return [] }
        var pairs: [[UUID]] = []
        for i in 1..<orderedIds.count {
            // order_after is [after, before]: orderedIds[i] comes after orderedIds[i-1].
            pairs.append([orderedIds[i], orderedIds[i - 1]])
        }
        return pairs
    }

    /// For Policy B: the ALLOWED source set (the selected ids). The client restricts moments[] to this set so
    /// the planner can only ever cite a selected asset_id — the existing eligibility mechanism IS the
    /// enforcement (owner §6). Returns nil for Policy A or an inactive sequence (full eligible set is used).
    var allowedSourceSet: Set<UUID>? {
        guard isActive, policy == .onlySelected else { return nil }
        return Set(orderedIds)
    }

    /// Fold this sequence's REQUIRED-INCLUSION + RELATIVE-ORDER into a ResolvedDirectives value (merged with
    /// any directives the NL text already produced). Ordering stays an objective on the backend; this only
    /// populates the typed slots the validator reads.
    ///
    /// - allowOthers: selected ids -> must_include; chain -> order_after. Other Moments remain eligible.
    /// - onlySelected: selected ids -> must_include; chain -> order_after. The ALLOWED-SET restriction is NOT
    ///   expressed as `exclude` here — it is applied by filtering moments[] (allowedSourceSet). We still add
    ///   must_include so each selected Moment is a required objective.
    func apply(to directives: inout ResolvedDirectives) {
        guard isActive else { return }
        for id in orderedIds where !directives.mustInclude.contains(id) {
            directives.mustInclude.append(id)
        }
        for pair in orderAfterPairs where !directives.orderAfter.contains(pair) {
            directives.orderAfter.append(pair)
        }
    }

    // ---- persistence (draft survival across close/reopen — owner §4) ----------------------------------

    func toJSON() -> String? {
        guard isActive, let data = try? JSONEncoder().encode(self) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func fromJSON(_ json: String?) -> MomentSequence? {
        guard let json, let data = json.data(using: .utf8),
              let s = try? JSONDecoder().decode(MomentSequence.self, from: data), s.isActive else { return nil }
        return s
    }
}

// MARK: - Conflicts between the storyboard and typed instructions (owner §10)

extension MomentSequence {

    /// A contradiction between the arranged sequence and what the user typed. Surfaced BEFORE any paid planning
    /// call with a short, actionable message — the planner would otherwise reject the request as a hard
    /// directive conflict / ineligible reference (never silently dropping either side).
    enum Conflict: Equatable {
        /// Typed "drop/skip/exclude" for a Moment that is also in the arranged sequence (required AND excluded).
        case excludedButSequenced([UUID])
        /// Policy "only the selected Moments" is on, but the typed text names Moments outside the sequence
        /// (opening / ending / include / order) — they are not eligible under that policy.
        case outsideOnlySelected([UUID])
    }

    /// Conflicts between this sequence and the directives interpreted from the user's typed text. Pass the
    /// TYPED directives (before `apply(to:)` folds the sequence in). Empty when the sequence is inactive.
    func conflicts(with typed: ResolvedDirectives) -> [Conflict] {
        guard isActive else { return [] }
        let sequenced = Set(orderedIds)
        var out: [Conflict] = []

        let excluded = typed.exclude.filter { sequenced.contains($0) }
        if !excluded.isEmpty { out.append(.excludedButSequenced(excluded.uniqued())) }

        if policy == .onlySelected {
            var referenced: [UUID] = typed.mustInclude
            if let o = typed.opening { referenced.append(o) }
            if let e = typed.ending { referenced.append(e) }
            for p in typed.orderAfter + typed.orderAdjacent { referenced.append(contentsOf: p) }
            // An excluded id outside the set is fine (excluding something already left out is a no-op).
            let outside = referenced.filter { !sequenced.contains($0) }
            if !outside.isEmpty { out.append(.outsideOnlySelected(outside.uniqued())) }
        }
        return out
    }
}

private extension Array where Element == UUID {
    /// De-duplicate preserving first-seen order.
    func uniqued() -> [UUID] {
        var seen = Set<UUID>()
        return filter { seen.insert($0).inserted }
    }
}
