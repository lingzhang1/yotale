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

    // ---- regression: previous version's Moments must not leak into the next version -----------------------

    func test_saved_directives_drop_storyboard_owned_slots_keep_the_rest() {
        var saved = ResolvedDirectives()
        saved.mustInclude = [a, b, c]            // the previous version's whole Moment list
        saved.orderAfter = [[b, a], [c, b]]      // and its order chain
        saved.opening = d
        saved.exclude = [c]
        let kept = saved.withoutStoryboardOwned()
        XCTAssertEqual(kept?.mustInclude, [], "must_include belongs to the storyboard, not a stale copy")
        XCTAssertEqual(kept?.orderAfter, [])
        XCTAssertEqual(kept?.opening, d, "typed-text structure (opening) is preserved")
        XCTAssertEqual(kept?.exclude, [c], "exclude is preserved")
    }

    func test_saved_directives_with_only_storyboard_slots_become_nil() {
        var saved = ResolvedDirectives()
        saved.mustInclude = [a, b]
        saved.orderAfter = [[b, a]]
        XCTAssertNil(saved.withoutStoryboardOwned(), "nothing left => nil, so no phantom 'saved directive' remains")
    }

    func test_pruned_sequence_is_the_only_source_of_must_include() {
        // New version: previous list was [a,b,c,d]; the user pruned the sequence to [b,d].
        var saved = ResolvedDirectives()
        saved.mustInclude = [a, b, c, d]
        saved.orderAfter = [[b, a], [c, b], [d, c]]
        var request = saved.withoutStoryboardOwned() ?? ResolvedDirectives()
        MomentSequence(orderedIds: [b, d], policy: .onlySelected).apply(to: &request)
        XCTAssertEqual(Set(request.mustInclude), [b, d], "no stale a/c leak back in")
        XCTAssertEqual(request.orderAfter, [[d, b]])
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
        XCTAssertEqual(s.conflicts(with: typed), [.outsideOnlySelected([d])])
    }

    func test_no_conflict_for_allowOthers_with_outside_reference() {
        var typed = ResolvedDirectives(); typed.opening = d
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
