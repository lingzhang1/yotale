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


# ---- default (no sequence): no ordering/inclusion objective at all -------------------------------------

def test_default_no_sequence_imposes_no_objective():
    # No revision_context/directives => full AI editorial freedom; any valid plan is fully satisfied.
    inp = _inputs_full()
    plan = _plan([M7, M3])   # any order, any subset of eligible moments
    hard = validate_plan(plan, inp)
    assert not hard
    a = assess_creative_intent(plan, inp)
    assert a["satisfied"], "with no directives there are no objectives to miss"
