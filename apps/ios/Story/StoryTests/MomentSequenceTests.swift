import XCTest
@testable import Story

// Customize UX v2 — MomentSequence model (storyboard order + policy). Pure logic; no network, no UI.
// Verifies the identity-safe mutation, the order_after derivation, Policy A vs B allowed-set, and draft
// round-trip — the single source of truth the storyboard serializes to directives (owner §4/§5/§6/§7).
final class MomentSequenceTests: XCTestCase {

    private let a = UUID(), b = UUID(), c = UUID(), d = UUID()

    // ---- default / inactive ---------------------------------------------------------------------------

    func test_empty_is_inactive_no_constraints() {
        let s = MomentSequence()
        XCTAssertFalse(s.isActive)
        XCTAssertEqual(s.orderAfterPairs, [])
        XCTAssertNil(s.allowedSourceSet)
        var dir = ResolvedDirectives()
        s.apply(to: &dir)
        XCTAssertTrue(dir.isEmpty, "an inactive sequence imposes NO directive (AI chooses order)")
    }

    // ---- identity-safe mutation (never duplicates; array pos != identity) -----------------------------

    func test_add_dedups_never_duplicates() {
        var s = MomentSequence()
        s.add(a); s.add(b); s.add(a)   // re-adding a is a no-op
        XCTAssertEqual(s.orderedIds, [a, b])
    }

    func test_addAll_dedups_preserves_first_seen_order() {
        var s = MomentSequence(orderedIds: [a])
        s.addAll([b, a, c])
        XCTAssertEqual(s.orderedIds, [a, b, c])
    }

    func test_init_dedups() {
        let s = MomentSequence(orderedIds: [a, b, a, c, b])
        XCTAssertEqual(s.orderedIds, [a, b, c])
    }

    func test_remove_clears_only_ordered_requirement() {
        var s = MomentSequence(orderedIds: [a, b, c])
        s.remove(b)
        XCTAssertEqual(s.orderedIds, [a, c], "removing b drops its order slot; a and c keep their order")
    }

    func test_move_reorders_by_identity() {
        var s = MomentSequence(orderedIds: [a, b, c])
        s.move(from: 0, to: 2)         // a to the end
        XCTAssertEqual(s.orderedIds, [b, c, a])
        s.move(from: 2, to: 0)         // a back to the front
        XCTAssertEqual(s.orderedIds, [a, b, c])
    }

    func test_move_out_of_bounds_is_noop() {
        var s = MomentSequence(orderedIds: [a, b])
        s.move(from: 5, to: 0)
        XCTAssertEqual(s.orderedIds, [a, b])
    }

    func test_reset_clears() {
        var s = MomentSequence(orderedIds: [a, b], policy: .onlySelected)
        s.reset()
        XCTAssertFalse(s.isActive)
    }

    // ---- order_after chain (relative order, NOT adjacency) --------------------------------------------

    func test_orderAfter_is_relative_chain() {
        // 3 -> 7 -> 12  =>  [[7,3],[12,7]]  (after, before) — relative, so others may fall between (owner §5)
        let s = MomentSequence(orderedIds: [a, b, c])
        XCTAssertEqual(s.orderAfterPairs, [[b, a], [c, b]])
    }

    func test_single_moment_has_no_order_pairs() {
        let s = MomentSequence(orderedIds: [a])
        XCTAssertEqual(s.orderAfterPairs, [])
    }

    // ---- Policy A: allow others -----------------------------------------------------------------------

    func test_policyA_allows_other_moments_no_source_restriction() {
        let s = MomentSequence(orderedIds: [a, b, c], policy: .allowOthers)
        XCTAssertNil(s.allowedSourceSet, "Policy A never restricts the source set")
        var dir = ResolvedDirectives()
        s.apply(to: &dir)
        XCTAssertEqual(Set(dir.mustInclude), [a, b, c])
        XCTAssertEqual(dir.orderAfter, [[b, a], [c, b]])
        XCTAssertTrue(dir.exclude.isEmpty, "Policy A never excludes")
        XCTAssertEqual(dir.opening, a, "the TOP card is the video's opening")
        XCTAssertEqual(dir.ending, c, "the BOTTOM card is the video's ending")
        XCTAssertTrue(dir.orderAdjacent.isEmpty, "relative order only — never adjacency")
    }

    // ---- Policy B: only selected (allowed-set via eligibility, NOT creative exclude) ------------------

    func test_policyB_restricts_source_set_without_exclude() {
        let s = MomentSequence(orderedIds: [a, b, c], policy: .onlySelected)
        XCTAssertEqual(s.allowedSourceSet, [a, b, c],
                       "Policy B allowed set = selected ids (client filters moments[]; planner can cite no other)")
        var dir = ResolvedDirectives()
        s.apply(to: &dir)
        XCTAssertEqual(Set(dir.mustInclude), [a, b, c])
        XCTAssertEqual(dir.orderAfter, [[b, a], [c, b]])
        XCTAssertTrue(dir.exclude.isEmpty,
                      "Policy B does NOT use creative exclude for the allowed set (owner §6) — eligibility does")
        XCTAssertEqual(dir.opening, a, "Policy B also opens on the top card")
    }

    // ---- top card = the video's opening (owner 2026-11-07) -------------------------------------------------

    func test_top_card_follows_a_drag_to_the_top() {
        // The device case: Moment 7 dragged to the top must become the opening.
        var s = MomentSequence(orderedIds: [a, b, c, d])
        s.move(from: 3, to: 0)                           // d dragged to the top
        var dir = ResolvedDirectives(); s.apply(to: &dir)
        XCTAssertEqual(dir.opening, d)
        XCTAssertEqual(dir.orderAfter.first, [a, d], "and the rest of the chain follows from it")
    }

    func test_single_moment_sequence_opens_on_it_but_has_no_ending() {
        var dir = ResolvedDirectives(); MomentSequence(orderedIds: [b]).apply(to: &dir)
        XCTAssertEqual(dir.opening, b)
        XCTAssertNil(dir.ending, "one Moment cannot be both the first and the last shot")
        XCTAssertEqual(dir.mustInclude, [b])
    }

    // ---- bottom card = the video's ending (owner 2026-11-07) -----------------------------------------------

    func test_bottom_card_follows_a_drag_to_the_bottom() {
        var s = MomentSequence(orderedIds: [a, b, c, d])
        s.move(from: 0, to: 3)                           // a dragged to the bottom
        var dir = ResolvedDirectives(); s.apply(to: &dir)
        XCTAssertEqual(dir.opening, b, "the new top card opens")
        XCTAssertEqual(dir.ending, a, "the card dragged to the bottom ends the video")
    }

    func test_two_moment_sequence_opens_and_ends() {
        var dir = ResolvedDirectives(); MomentSequence(orderedIds: [a, b]).apply(to: &dir)
        XCTAssertEqual(dir.opening, a); XCTAssertEqual(dir.ending, b)
    }

    func test_opening_and_ending_are_never_the_same_Moment() {
        for n in 1...5 {
            let ids = (0..<n).map { _ in UUID() }
            var dir = ResolvedDirectives(); MomentSequence(orderedIds: ids).apply(to: &dir)
            if let o = dir.opening, let e = dir.ending { XCTAssertNotEqual(o, e, "n=\(n)") }
        }
    }

    func test_the_top_card_is_never_in_the_after_slot_and_the_bottom_never_in_the_before_slot() {
        // The backend rejects "opening ordered after something" and "ending ordered before something" as hard
        // contradictions. The generated chain must never trip them.
        let ids = (0..<6).map { _ in UUID() }
        var dir = ResolvedDirectives(); MomentSequence(orderedIds: ids).apply(to: &dir)
        XCTAssertFalse(dir.orderAfter.contains { $0[0] == dir.opening }, "opening must never be an 'after'")
        XCTAssertFalse(dir.orderAfter.contains { $0[1] == dir.ending }, "ending must never be a 'before'")
    }

    func test_apply_never_overrides_an_existing_ending() {
        var dir = ResolvedDirectives(); dir.ending = d
        MomentSequence(orderedIds: [a, b]).apply(to: &dir)
        XCTAssertEqual(dir.ending, d)
    }

    func test_conflict_typed_ending_differs_from_bottom_card() {
        var typed = ResolvedDirectives(); typed.ending = a              // "End with Moment a"
        let s = MomentSequence(orderedIds: [a, b, c], policy: .allowOthers)
        XCTAssertEqual(s.conflicts(with: typed), [.endingDiffersFromLastCard(typed: a, last: c)])
    }

    func test_typed_ending_equal_to_bottom_card_is_not_a_conflict() {
        var typed = ResolvedDirectives(); typed.ending = c
        XCTAssertEqual(MomentSequence(orderedIds: [a, b, c]).conflicts(with: typed), [])
    }

    func test_single_moment_sequence_has_no_ending_conflict() {
        var typed = ResolvedDirectives(); typed.ending = d
        XCTAssertEqual(MomentSequence(orderedIds: [a]).conflicts(with: typed), [],
                       "a one-Moment sequence imposes no ending, so a typed ending cannot contradict it")
    }

    func test_inactive_sequence_sets_no_opening() {
        var dir = ResolvedDirectives(); MomentSequence().apply(to: &dir)
        XCTAssertNil(dir.opening, "no arranged sequence => AI chooses, nothing is pinned")
    }

    func test_apply_never_overrides_an_existing_opening() {
        var dir = ResolvedDirectives(); dir.opening = d      // would already have been surfaced as a conflict
        MomentSequence(orderedIds: [a, b]).apply(to: &dir)
        XCTAssertEqual(dir.opening, d)
    }

    func test_apply_merges_with_existing_directives() {
        var dir = ResolvedDirectives()
        dir.mustInclude = [a]            // say the NL text already required a
        dir.opening = d                  // and pinned an opening
        let s = MomentSequence(orderedIds: [a, b], policy: .allowOthers)
        s.apply(to: &dir)
        XCTAssertEqual(Set(dir.mustInclude), [a, b], "merge is idempotent for a; adds b")
        XCTAssertEqual(dir.opening, d, "existing opening preserved")
        XCTAssertEqual(dir.orderAfter, [[b, a]])
    }

    // ---- draft persistence (survive close/reopen — owner §4) ------------------------------------------

    func test_json_round_trip_preserves_order_and_policy() {
        let s = MomentSequence(orderedIds: [c, a, b], policy: .onlySelected)
        let json = s.toJSON()
        XCTAssertNotNil(json)
        let back = MomentSequence.fromJSON(json)
        XCTAssertEqual(back?.orderedIds, [c, a, b], "order preserved exactly")
        XCTAssertEqual(back?.policy, .onlySelected)
    }

    // ---- conflicts between the storyboard and typed text (owner §10) ---------------------------------------

    func test_conflict_required_and_excluded() {
        var typed = ResolvedDirectives(); typed.exclude = [b]            // "drop Moment b"
        let s = MomentSequence(orderedIds: [a, b, c], policy: .allowOthers)
        XCTAssertEqual(s.conflicts(with: typed), [.excludedButSequenced([b])])
    }

    func test_conflict_typed_reference_outside_only_selected() {
        var typed = ResolvedDirectives(); typed.opening = d              // "Start with Moment d", d not selected
        let s = MomentSequence(orderedIds: [a, b], policy: .onlySelected)
        XCTAssertEqual(s.conflicts(with: typed),
                       [.openingDiffersFromTopCard(typed: d, top: a), .outsideOnlySelected([d])])
    }

    func test_conflict_typed_opening_differs_from_top_card() {
        var typed = ResolvedDirectives(); typed.opening = b             // "Start with Moment b"
        let s = MomentSequence(orderedIds: [a, b, c], policy: .allowOthers)
        XCTAssertEqual(s.conflicts(with: typed), [.openingDiffersFromTopCard(typed: b, top: a)])
    }

    func test_typed_opening_equal_to_top_card_is_not_a_conflict() {
        var typed = ResolvedDirectives(); typed.opening = a
        XCTAssertEqual(MomentSequence(orderedIds: [a, b], policy: .allowOthers).conflicts(with: typed), [])
    }

    func test_no_conflict_for_allowOthers_with_outside_reference() {
        var typed = ResolvedDirectives(); typed.mustInclude = [d]       // "also include Moment d" — not in the sequence
        let s = MomentSequence(orderedIds: [a, b], policy: .allowOthers)
        XCTAssertEqual(s.conflicts(with: typed), [], "others are allowed under Policy A")
    }

    func test_no_conflict_when_sequence_inactive_or_text_inside_set() {
        var typed = ResolvedDirectives(); typed.exclude = [a]; typed.opening = d
        XCTAssertEqual(MomentSequence().conflicts(with: typed), [], "inactive sequence => nothing to contradict")
        var inside = ResolvedDirectives(); inside.opening = a; inside.mustInclude = [b]
        XCTAssertEqual(MomentSequence(orderedIds: [a, b], policy: .onlySelected).conflicts(with: inside), [])
    }

    func test_excluding_something_already_left_out_is_not_a_conflict() {
        var typed = ResolvedDirectives(); typed.exclude = [d]            // d is not in the only-selected set
        XCTAssertEqual(MomentSequence(orderedIds: [a, b], policy: .onlySelected).conflicts(with: typed), [])
    }

    func test_inactive_sequence_serializes_nil() {
        XCTAssertNil(MomentSequence().toJSON(), "an inactive sequence has no draft to persist")
        XCTAssertNil(MomentSequence.fromJSON(nil))
    }
}
