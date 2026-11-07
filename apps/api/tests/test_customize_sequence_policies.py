"""Customize UX v2 — PLAN-LEVEL tests for the two sequence policies (owner §13: test the actual EditPlan
behavior, not just UI serialization).

The storyboard (iOS) produces, for an arranged sequence 3 -> 7 -> 12:
  - Policy A ("allow others"): directives must_include=[3,7,12] + order_after chain [[7,3],[12,7]];
    the full eligible moments[] is sent.
  - Policy B ("only selected"): the SAME directives, but moments[] is RESTRICTED to {3,7,12} client-side
    (EditPlanRequestBuilder.allowedSourceSet) — the planner then cannot cite any other id.

These tests verify the BACKEND half end-to-end against the deterministic validator + satisfaction scorer:
  * ordering is an OBJECTIVE (unmet order is disclosed, never a hard ship-block) — owner decision;
  * a correct-order plan satisfies the objective; an out-of-order plan reports it unmet but still ships;
  * Policy B's guarantee ("no footage from unselected Moments") holds BY CONSTRUCTION — a segment can only
    cite an id present in moments[], so restricting moments[] is the enforcement. We assert that invariant
    directly: given a Policy-B-restricted inputs, any plan the validator passes references only allowed ids,
    and a plan that cites an unselected id is caught as a HARD reference error.
"""
from __future__ import annotations

from uuid import uuid4

from edit_planner import (
    EditPlanInputs,
    validate_plan,
    assess_creative_intent,
    repair_directive_placement,
)
import edit_planner as _ep


def _hard_errors(plan, inp):
    """The HARD directive errors only (ship-blocking), separated from OBJECTIVE misses — this is the layer
    that decides rejection, independent of the legacy objective-in-hard-gate flag."""
    moments = {str(m["id"]).lower(): m for m in inp.moments}
    hard, _obj = _ep._validate_directives_split(plan, inp, moments)
    return hard

M3 = str(uuid4())
M7 = str(uuid4())
M12 = str(uuid4())
M_OTHER = str(uuid4())   # an eligible Moment the user did NOT select


def _inputs_full(**over):
    """Inputs with the FULL eligible set (Policy A): 3, 7, 12 AND an unselected other Moment."""
    base = dict(
        story_id=str(uuid4()), creative_intent_id=str(uuid4()),
        creative_intent={"target_duration_seconds": 20.0, "desired_feeling": ["calm"]},
        story_guide={"framing_summary": "a journey"},
        story_coverage={"sufficiency": "sufficient"},
        moments=[
            {"id": M3, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "border sign"},
            {"id": M7, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "the climb"},
            {"id": M12, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "last descent"},
            {"id": M_OTHER, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "a rest stop"},
        ],
        music_plan={},   # no-music path (matches EditPlanRequestBuilder's no-music mode)
    )
    base.update(over)
    return EditPlanInputs(**base)


def _inputs_only_selected(**over):
    """Inputs as the iOS allowedSourceSet (Policy B) would build them: moments[] RESTRICTED to {3,7,12}.
    The unselected Moment is simply absent from the payload — the planner can never reference it."""
    base = dict(
        story_id=str(uuid4()), creative_intent_id=str(uuid4()),
        creative_intent={"target_duration_seconds": 20.0, "desired_feeling": ["calm"]},
        story_guide={"framing_summary": "a journey"},
        story_coverage={"sufficiency": "sufficient"},
        moments=[
            {"id": M3, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "border sign"},
            {"id": M7, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "the climb"},
            {"id": M12, "duration_seconds": 10.0, "useful_segments": [[0.0, 9.0]], "summary": "last descent"},
        ],
        music_plan={},
    )
    base.update(over)
    return EditPlanInputs(**base)


def _rev(directives):
    return {"mode": "revise", "directives": directives}


def _seq_directives():
    """The directives the storyboard derives for 3 -> 7 -> 12 (order_after is [after, before])."""
    return {"must_include": [M3, M7, M12], "order_after": [[M7, M3], [M12, M7]]}


def _seg(order, asset_id):
    return {"order": order, "asset_id": asset_id, "source_start_seconds": 0.0, "source_end_seconds": 6.0,
            "output_duration_seconds": 6.0, "native_audio": "keep"}


def _plan(asset_ids):
    return {"target_duration_seconds": float(6 * len(asset_ids)), "feasible": True,
            "segments": [_seg(i, a) for i, a in enumerate(asset_ids)]}


# ---- Policy A: relative order as an OBJECTIVE, others allowed -------------------------------------------

def test_policyA_correct_order_with_other_moment_satisfies():
    # 3, (other), 7, 12 — the other Moment falls BETWEEN, which Policy A allows; relative order 3<7<12 holds.
    inp = _inputs_full(revision_context=_rev(_seq_directives()))
    plan = _plan([M3, M_OTHER, M7, M12])
    assert not _hard_errors(plan, inp), "ordering/inclusion are objectives, never hard here"
    a = assess_creative_intent(plan, inp)
    assert a["satisfied"], f"relative order + inclusion satisfied: {a['material_unmet']}"


def test_policyA_wrong_order_still_ships_but_discloses():
    # 12 before 7 — violates the relative order. Ordering is an OBJECTIVE: NOT a hard block, but disclosed.
    inp = _inputs_full(revision_context=_rev(_seq_directives()))
    plan = _plan([M3, M12, M7])
    assert not _hard_errors(plan, inp), "a playable video is never hard-blocked for a creative ordering miss (owner §6)"
    a = assess_creative_intent(plan, inp)
    assert not a["satisfied"]
    codes = {m["code"] for m in a["material_unmet"]}
    assert "ordering" in codes, f"the unmet order must be disclosed, never claimed satisfied: {a}"


def test_policyA_missing_selected_moment_disclosed_not_blocked():
    # M12 required but absent from the plan — inclusion objective unmet, disclosed, still ships (not hard).
    inp = _inputs_full(revision_context=_rev(_seq_directives()))
    plan = _plan([M3, M7])
    assert not _hard_errors(plan, inp), "a missing required Moment is an objective miss, not a hard block"
    a = assess_creative_intent(plan, inp)
    assert not a["satisfied"]
    assert "inclusion" in {m["code"] for m in a["material_unmet"]}


# ---- Policy B: ONLY selected Moments may contribute footage --------------------------------------------

def test_policyB_plan_over_restricted_set_references_only_selected():
    # With moments[] restricted to {3,7,12}, a valid plan can only cite those ids — the guarantee by
    # construction. The correctly-ordered plan has NO errors at all (hard or objective), and every segment's
    # asset_id is in the allowed set.
    inp = _inputs_only_selected(revision_context=_rev(_seq_directives()))
    plan = _plan([M3, M7, M12])
    assert not validate_plan(plan, inp), "a correctly-ordered only-selected plan ships clean"
    allowed = {M3, M7, M12}
    cited = {s["asset_id"] for s in plan["segments"]}
    assert cited <= allowed, f"Policy B must never admit footage from an unselected Moment: {cited - allowed}"


def test_policyB_citing_unselected_moment_is_a_hard_reference_error():
    # If a plan somehow cited M_OTHER while moments[] is restricted to {3,7,12}, the validator REJECTS it as a
    # hard "asset_id not in moments[]" error — so the restriction is genuinely enforced, not advisory.
    inp = _inputs_only_selected(revision_context=_rev(_seq_directives()))
    plan = _plan([M3, M_OTHER, M12])   # M_OTHER is NOT in the restricted moments[]
    hard = validate_plan(plan, inp)
    assert hard, "citing a Moment absent from moments[] must be a HARD validation error"
    assert any("M_OTHER".lower() in e.lower() or M_OTHER in e or "not" in e.lower() for e in hard), \
        f"the hard error should name the out-of-set asset_id: {hard}"


def test_policyB_wrong_order_within_selected_still_ships_and_discloses():
    # Even under Policy B, order stays an OBJECTIVE: an out-of-order but valid plan ships, order disclosed.
    inp = _inputs_only_selected(revision_context=_rev(_seq_directives()))
    plan = _plan([M12, M7, M3])
    assert not _hard_errors(plan, inp), "Policy B never hard-blocks a playable video for a creative ordering miss"
    a = assess_creative_intent(plan, inp)
    assert not a["satisfied"]
    assert "ordering" in {m["code"] for m in a["material_unmet"]}


# ---- regression (device test 2026-11-06): stale must_include outside the allowed set -------------------

def test_policyB_stale_must_include_outside_allowed_set_is_a_hard_reference_error():
    # The device bug: a new version's request carried the PREVIOUS version's must_include (an id that is no
    # longer in the restricted moments[]). The validator reports it as a HARD reference error
    # ("not in the eligible source set" -> directive_ref_ineligible -> invalid_after_repair). This pins WHY the
    # client must not carry the old list forward; the iOS fix strips storyboard-owned slots from saved sets.
    stale = {"must_include": [M3, M7, M12, M_OTHER], "order_after": [[M7, M3], [M12, M7]]}
    inp = _inputs_only_selected(revision_context=_rev(stale))      # moments[] = {3,7,12}; M_OTHER absent
    hard = _hard_errors(_plan([M3, M7, M12]), inp)
    assert any("not in the eligible source set" in e for e in hard), hard


def test_policyB_directives_limited_to_allowed_set_have_no_hard_errors():
    # After the fix the request's directives reference ONLY arranged Moments -> no hard reference error.
    inp = _inputs_only_selected(revision_context=_rev(_seq_directives()))
    assert not _hard_errors(_plan([M3, M7, M12]), inp)


# ---- default (no sequence): no ordering/inclusion objective at all -------------------------------------

def test_default_no_sequence_imposes_no_objective():
    # No revision_context/directives => full AI editorial freedom; any valid plan is fully satisfied.
    inp = _inputs_full()
    plan = _plan([M7, M3])   # any order, any subset of eligible moments
    hard = validate_plan(plan, inp)
    assert not hard
    a = assess_creative_intent(plan, inp)
    assert a["satisfied"], "with no directives there are no objectives to miss"


# ---- Revise: repositioning the base edit with the storyboard (Customize UX v2, Revise parity) ------------
# Revise edits an EXISTING video: the base plan is carried and every clip is preserved; the storyboard only
# REPOSITIONS the chosen Moments (Policy A — others stay). The deterministic reorder (no model call) honors the
# order_after chain without dropping, adding or re-timing any segment.

def _revise_ctx(directives):
    return {"mode": "revise", "directives": directives}


def _segkey(plan):
    return sorted((str(x["asset_id"]).lower(), x["source_start_seconds"], x["source_end_seconds"],
                   x["output_duration_seconds"]) for x in plan["segments"])


def test_revise_reposition_reorders_base_plan_deterministically_and_preserves_every_clip():
    # Base edit plays 3, 12, 7, other. The user repositions 3 -> 7 -> 12 (order_after chain, must_include).
    base = _plan([M3, M12, M7, M_OTHER])
    inp = _inputs_full(revision_context=_revise_ctx(_seq_directives()))
    assert _hard_errors(base, inp) == []
    assert not assess_creative_intent(base, inp)["satisfied"], "base order violates the repositioned sequence"

    fixed = repair_directive_placement(base, inp)
    assert fixed is not None, "a pure order violation is fixed by the deterministic reorder (no model call)"
    order = [str(x["asset_id"]).lower() for x in fixed["segments"]]
    assert order.index(M3.lower()) < order.index(M7.lower()) < order.index(M12.lower())
    assert _segkey(fixed) == _segkey(base), "same segments, same timing — nothing dropped, added or re-timed"
    assert assess_creative_intent(fixed, inp)["satisfied"], "and the objective is now actually met"


def test_revise_with_no_sequence_is_untouched():
    # No directives => nothing to repair; the base edit is preserved as-is (Revise default: keep current order).
    base = _plan([M3, M12, M7, M_OTHER])
    inp = _inputs_full(revision_context=_revise_ctx({}))
    assert assess_creative_intent(base, inp)["satisfied"]


def test_revise_repositioned_moment_missing_from_base_is_disclosed_not_invented():
    # M7 is not in the base video. Repositioning it cannot conjure footage into the edit: the reorder leaves the
    # plan alone and the unmet inclusion is DISCLOSED (never claimed satisfied), and it is still not a hard block.
    base = _plan([M3, M12])
    inp = _inputs_full(revision_context=_revise_ctx(_seq_directives()))
    assert _hard_errors(base, inp) == []
    a = assess_creative_intent(base, inp)
    assert not a["satisfied"]
    assert "inclusion" in {m["code"] for m in a["material_unmet"]}


# ---- top card = the video's opening (owner 2026-11-07) ------------------------------------------------------
# The storyboard now ALSO sends opening = the top card (alongside must_include + the order_after chain). Opening
# stays an OBJECTIVE; a plan that misses it ships and is disclosed, and the deterministic reorder (no model call)
# puts the top Moment first without dropping, adding or re-timing any segment.

def _seq_directives_with_opening():
    return {**_seq_directives(), "opening": M3}


def _split_errors(plan, inp):
    moments = {str(m["id"]).lower(): m for m in inp.moments}
    return _ep._validate_directives_split(plan, inp, moments)


def test_opening_plus_storyboard_chain_is_not_a_hard_conflict():
    # The top card is never the "after" of any pair, so opening + chain cannot trip the contradiction checks.
    inp = _inputs_full(revision_context=_rev(_seq_directives_with_opening()))
    hard, _obj = _split_errors(_plan([M3, M_OTHER, M7, M12]), inp)
    assert hard == []


def test_plan_opening_on_top_card_satisfies_the_sequence():
    inp = _inputs_full(revision_context=_rev(_seq_directives_with_opening()))
    plan = _plan([M3, M_OTHER, M7, M12])           # opens on 3, 7 then 12 later, an unselected clip between
    assert assess_creative_intent(plan, inp)["satisfied"]


def test_plan_not_opening_on_top_card_ships_but_discloses_opening():
    inp = _inputs_only_selected(revision_context=_rev(_seq_directives_with_opening()))
    plan = _plan([M7, M3, M12])                    # the device case: the wrong Moment is first
    hard, _ = _split_errors(plan, inp)
    assert hard == [], "a playable video is never hard-blocked for a creative opening miss"
    a = assess_creative_intent(plan, inp)
    assert not a["satisfied"]
    assert "opening" in {m["code"] for m in a["material_unmet"]}, "never claimed satisfied when it isn't"


def test_deterministic_repair_moves_the_top_card_first_without_touching_any_segment():
    inp = _inputs_full(revision_context=_rev(_seq_directives_with_opening()))
    base = _plan([M_OTHER, M7, M3, M12])           # an unselected clip first, 3 later
    assert not assess_creative_intent(base, inp)["satisfied"]
    fixed = _ep.repair_directive_placement(base, inp)
    assert fixed is not None, "a pure placement miss is fixed by the deterministic reorder (no model call)"
    order = [str(s["asset_id"]).lower() for s in fixed["segments"]]
    assert order[0] == M3.lower(), "the top card opens the video"
    assert order.index(M3.lower()) < order.index(M7.lower()) < order.index(M12.lower())
    assert _segkey(fixed) == _segkey(base), "same segments and timing — nothing dropped, added or re-timed"
    assert assess_creative_intent(fixed, inp)["satisfied"]


def test_revise_with_top_card_opening_repositions_the_base_edit_deterministically():
    # Revise: base edit plays 7, 3, 12, other. The user repositions 3 to the top (3 -> 7 -> 12).
    inp = _inputs_full(revision_context=_revise_ctx(_seq_directives_with_opening()))
    base = _plan([M7, M3, M12, M_OTHER])
    fixed = _ep.repair_directive_placement(base, inp)
    assert fixed is not None
    order = [str(s["asset_id"]).lower() for s in fixed["segments"]]
    assert order[0] == M3.lower()
    assert _segkey(fixed) == _segkey(base)
    assert assess_creative_intent(fixed, inp)["satisfied"]
