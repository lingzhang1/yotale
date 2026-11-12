"""Deterministic duration fit (packages/edit_planner/duration_fit.py) + its adoption in RealEditPlannerEngine.

No model is invoked. Plans are built so every segment is technically valid (in-bounds, span/speed consistent);
the fit must keep them valid, shrink only, keep AU payoffs, honor directives / music anchors / native audio /
deliberate repetition, never impose a minimum shot length, and report exactly what shipped."""
from __future__ import annotations

import copy
from uuid import uuid4

import pytest

from edit_planner import EditPlanInputs, RealEditPlannerEngine, validate_plan
from edit_planner.duration_fit import FIT_BAND, RETAIN_FRACTION, delivered_total_seconds, fit_plan_duration
from model_gateway import FakeModelGateway


def _moment(dur=20.0, peak=None, event=None, cand=None, events=None):
    m = {"id": str(uuid4()), "duration_seconds": dur, "useful_segments": [[0.0, dur]], "summary": "x"}
    if peak is not None:
        a, b = cand or (max(0.0, peak - 2), min(dur, peak + 2))
        m["editorial"] = {"visual_candidates": [{"start_time": a, "end_time": b, "peak_time": peak, "confidence": 0.9}]}
    evs = events if events is not None else ([event] if event else [])
    m["events"] = [{"start_time": e[0], "end_time": e[1], "description": "e"} for e in evs]
    return m


def _seg(order, m, a, b, speed=1.0, native="duck", anchor=None, transition=None, role=None):
    s = {"order": order, "asset_id": m["id"], "source_start_seconds": a, "source_end_seconds": b,
         "output_duration_seconds": round((b - a) / speed, 3), "speed": speed, "native_audio": native}
    if anchor:
        s["music_alignment"] = {"anchor": anchor}
    if transition:
        s["transition"] = transition
    if role:
        s["narrative_role"] = role
    return s


def _inputs(moments, target, etype="highlights", rc=None, music=False):
    kw = {}
    if music:
        kw = dict(music_analysis={"duration_seconds": 120.0, "bpm": 120.0, "beats": [0.0, 0.5], "downbeats": [0.0]},
                  music_asset_id="epidemic:t")
    return EditPlanInputs(story_id=str(uuid4()), creative_intent_id=str(uuid4()),
                          creative_intent={"target_duration_seconds": float(target)}, story_guide={}, story_coverage={},
                          moments=moments, music_plan={}, editorial_type=etype, revision_context=rc, **kw)


def _plan(segs):
    return {"target_duration_seconds": 0, "feasible": True, "segments": segs}


def _assert_shrunk_valid(orig, fitted, inputs):
    assert validate_plan(copy.deepcopy(fitted), inputs) == []
    by = {}
    for s in orig["segments"]:
        by.setdefault(s["asset_id"], []).append(s)
    for k, s in enumerate(fitted["segments"]):
        assert s["order"] == k and "_orig" not in s
        assert any(o["source_start_seconds"] - 1e-6 <= s["source_start_seconds"]
                   and s["source_end_seconds"] <= o["source_end_seconds"] + 1e-6
                   and o["speed"] == s["speed"] and o["native_audio"] == s["native_audio"]
                   for o in by[s["asset_id"]]), "a fitted range must lie inside an original segment of that Moment"
        assert abs(s["output_duration_seconds"] - (s["source_end_seconds"] - s["source_start_seconds"]) / s["speed"]) < 0.01


def _payoffs_on_screen(fitted, moments):
    mm = {m["id"]: m for m in moments}
    return all(any(s["source_start_seconds"] <= vc["peak_time"] <= s["source_end_seconds"]
                   for s in fitted["segments"] if s["asset_id"] == mid)
               for mid in {s["asset_id"] for s in fitted["segments"]}
               for vc in (mm[mid].get("editorial") or {}).get("visual_candidates", [])
               if any(o["asset_id"] == mid for o in fitted["segments"]))


# ---------------------------------------------------------------------------- length / type

@pytest.mark.parametrize("target,etype", [(32, "highlights"), (50, "highlights"), (50, "full_story")])
def test_overlong_plan_is_pulled_into_band_and_keeps_payoffs(target, etype):
    ms = [_moment(30, peak=15, event=(13, 17)) for _ in range(7)]
    per = target * 1.45 / 7
    p = _plan([_seg(i, m, 15 - per / 2, 15 + per / 2) for i, m in enumerate(ms)])
    inp = _inputs(ms, target, etype)
    f, rep = fit_plan_duration(p, inp)
    assert rep["applied"] and rep["within_band"]
    assert abs(delivered_total_seconds(f["segments"]) - target) <= target * FIT_BAND
    assert len(f["segments"]) == 7 and _payoffs_on_screen(f, ms)
    assert len(rep["changes"]) == rep["trimmed"] > 0
    _assert_shrunk_valid(p, f, inp)


def test_full_story_keeps_the_whole_payoff_event():
    ms = [_moment(30, peak=12, event=(2, 28)) for _ in range(4)]                  # one long meaningful action
    p = _plan([_seg(i, m, 0, 30) for i, m in enumerate(ms)])                       # 120s for a 70s target
    f, frep = fit_plan_duration(p, _inputs(ms, 70, "full_story"))
    assert all(s["source_start_seconds"] <= 2 and s["source_end_seconds"] >= 28 for s in f["segments"])
    assert not frep["within_band"]                                                 # complete actions win; disclosed
    h, hrep = fit_plan_duration(p, _inputs(ms, 70, "highlights"))
    assert hrep["within_band"] and any(s["source_start_seconds"] > 2 or s["source_end_seconds"] < 28 for s in h["segments"])


def test_user_exact_custom_duration_is_also_fitted():
    ms = [_moment(20, peak=10) for _ in range(5)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])                       # 80s for 45s
    f, rep = fit_plan_duration(p, _inputs(ms, 45, rc={"mode": "explore", "duration_target_source": "user_exact"}))
    assert rep["within_band"] and abs(delivered_total_seconds(f["segments"]) - 45) <= 4.5


def test_short_footage_undershoot_is_never_extended():
    ms = [_moment(6, peak=3) for _ in range(4)]
    p = _plan([_seg(i, m, 0, 6) for i, m in enumerate(ms)])                        # 24s, target 50
    f, rep = fit_plan_duration(p, _inputs(ms, 50))
    assert f is p and not rep["applied"] and rep["reason"] == "undershoot_not_extended"


def test_within_band_plan_is_never_touched():
    ms = [_moment(20, peak=10) for _ in range(5)]
    p = _plan([_seg(i, m, 5, 15.8) for i, m in enumerate(ms)])                     # 54s for 50 (+8%)
    f, rep = fit_plan_duration(p, _inputs(ms, 50))
    assert f is p and not rep["applied"] and rep["reason"] == "within_band"


# ---------------------------------------------------------------------------- no minimum shot length

def test_short_planner_shots_are_preserved_and_long_holds_absorb_the_cut():
    ms = [_moment(20, peak=10) for _ in range(6)]
    segs = [_seg(0, ms[0], 9.4, 10.6), _seg(1, ms[1], 0, 16), _seg(2, ms[2], 9.5, 10.7),   # 1.2s punchy cuts
            _seg(3, ms[3], 0, 16), _seg(4, ms[4], 9.3, 10.8), _seg(5, ms[5], 0, 16)]
    p = _plan(segs)                                                                 # 51.9s for 40s
    inp = _inputs(ms, 40)
    f, rep = fit_plan_duration(p, inp)
    assert rep["within_band"]
    for o, s in zip(p["segments"], f["segments"]):
        if o["output_duration_seconds"] < 2:
            assert (s["source_start_seconds"], s["source_end_seconds"]) == (o["source_start_seconds"], o["source_end_seconds"])
    _assert_shrunk_valid(p, f, inp)
    assert validate_plan(copy.deepcopy(p), inp) == []                              # sub-2s shots are valid as-is


def test_trim_never_goes_below_half_the_planned_shot():
    ms = [_moment(20) for _ in range(4)]                                            # no payoff anywhere
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])                       # 64s for 10s
    f, rep = fit_plan_duration(p, _inputs(ms, 10))
    assert all(s["output_duration_seconds"] >= RETAIN_FRACTION * 16 - 1e-6 for s in f["segments"])


# ---------------------------------------------------------------------------- drops and repetition

def test_excessively_long_plan_drops_longest_low_value_shots_and_keeps_payoffs():
    pay = [_moment(20, peak=10) for _ in range(3)]
    scenic = [_moment(20) for _ in range(6)]
    order = [pay[0]] + scenic[:3] + [pay[1]] + scenic[3:] + [pay[2]]
    p = _plan([_seg(i, m, 2, 18 if m in pay else 2 + 6 + i) for i, m in enumerate(order)])
    inp = _inputs(order, 28)
    f, rep = fit_plan_duration(p, inp)
    assert rep["within_band"] and rep["dropped"]
    kept = {s["asset_id"] for s in f["segments"]}
    assert {m["id"] for m in pay} <= kept
    assert f["segments"][0]["asset_id"] == pay[0]["id"] and f["segments"][-1]["asset_id"] == pay[2]["id"]
    first_drop = rep["dropped"][0]
    assert first_drop["planned_out_s"] == max(s["output_duration_seconds"] for s in p["segments"]
                                      if s["asset_id"] in {m["id"] for m in scenic})   # longest first
    _assert_shrunk_valid(p, f, inp)


def test_literal_repeat_is_dropped_but_separate_action_and_labelled_callback_stay():
    a = _moment(30, peak=5)
    b, c = _moment(20, peak=10), _moment(20, peak=10)
    p = _plan([_seg(0, b, 2, 18), _seg(1, a, 0, 12),
               _seg(2, a, 2, 11),                                   # literal repeat (fully inside 0-12)
               _seg(3, a, 19, 27),                                  # separate action, no payoff, no overlap
               _seg(4, a, 1, 10, role="callback to the opening view"),   # deliberate reprise
               _seg(5, c, 2, 18)])
    f, rep = fit_plan_duration(p, _inputs([a, b, c], 40))
    assert [d["why"] for d in rep["dropped"] if d["why"] == "literal_repeat"] == ["literal_repeat"]
    assert rep["dropped"][0]["range"] == [2, 11]
    kept_a = [s for s in f["segments"] if s["asset_id"] == a["id"]]
    assert any(s["source_start_seconds"] >= 19 - 1e-6 for s in kept_a)              # separate action kept
    assert any(s.get("narrative_role", "").startswith("callback") for s in kept_a)   # callback kept


def test_partial_overlap_is_not_a_literal_repeat():
    a, b, c = _moment(30, peak=5), _moment(20, peak=10), _moment(20, peak=10)
    p = _plan([_seg(0, b, 2, 18), _seg(1, a, 0, 10), _seg(2, a, 6, 16), _seg(3, c, 2, 18)])   # 40% overlap
    _f, rep = fit_plan_duration(p, _inputs([a, b, c], 36))
    assert not any(d["why"] == "literal_repeat" for d in rep["dropped"])


def test_directive_referenced_moments_and_repetition_are_never_dropped():
    pay0, pay1 = _moment(20, peak=10), _moment(20, peak=10)
    req = _moment(20)
    order = [pay0, req, req, pay1]                       # user-required Moment, used twice (overlapping)
    p = _plan([_seg(0, pay0, 2, 18), _seg(1, req, 2, 18), _seg(2, req, 3, 17), _seg(3, pay1, 2, 18)])
    f, rep = fit_plan_duration(p, _inputs([pay0, req, pay1], 10), protected_ids={req["id"]})
    assert [s["asset_id"] for s in f["segments"]] == [m["id"] for m in order]
    assert not rep["dropped"] and not rep["within_band"]                           # honest: still long


def test_only_selected_moments_policy_never_adds_a_moment():
    ms = [_moment(20, peak=10) for _ in range(4)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])
    f, _ = fit_plan_duration(p, _inputs(ms, 40))
    assert {s["asset_id"] for s in f["segments"]} <= {s["asset_id"] for s in p["segments"]}


# ---------------------------------------------------------------------------- music / audio / arithmetic

def test_music_anchor_and_everything_before_it_are_untouched():
    ms = [_moment(20, peak=10) for _ in range(5)]
    segs = [_seg(0, ms[0], 2, 18), _seg(1, ms[1], 2, 18, anchor="downbeat"),
            _seg(2, ms[2], 2, 18), _seg(3, ms[3], 2, 18), _seg(4, ms[4], 2, 18)]
    p = _plan(segs)
    inp = _inputs(ms, 60, music=True)
    f, rep = fit_plan_duration(p, inp)
    for k in (0, 1):
        assert (f["segments"][k]["source_start_seconds"], f["segments"][k]["source_end_seconds"]) == (2, 18)
    assert all(c["order"] >= 2 for c in rep["changes"])
    _assert_shrunk_valid(p, f, inp)


def test_stripped_crossfades_are_not_subtracted_and_transition_is_clamped():
    ms = [_moment(20, peak=10) for _ in range(4)]
    segs = [_seg(0, ms[0], 2, 18), _seg(1, ms[1], 2, 18, speed=2.0, native="keep"),
            _seg(2, ms[2], 2, 18, transition={"type": "crossfade", "duration_seconds": 6.0}), _seg(3, ms[3], 2, 18)]
    p = _plan(segs)
    assert delivered_total_seconds(p["segments"]) == 56.0                          # 16 + 8 + 16 + 16, no overlap
    inp = _inputs(ms, 40)
    vp = copy.deepcopy(p)
    validate_plan(vp, inp)
    assert vp["_duration_delta_fraction"] == pytest.approx(0.4, abs=1e-3)         # delivered, not 56 - 6
    f, rep = fit_plan_duration(p, inp)
    xf = next(s for s in f["segments"] if s.get("transition"))
    assert xf["transition"]["duration_seconds"] <= xf["output_duration_seconds"]
    fast = f["segments"][1]
    assert fast["speed"] == 2.0 and abs(fast["output_duration_seconds"] - (fast["source_end_seconds"] - fast["source_start_seconds"]) / 2) < 0.01
    assert rep["within_band"]


def test_native_audio_keep_keeps_its_au_event_with_or_without_a_payoff():
    with_payoff = [_moment(30, peak=15, event=(10, 21)) for _ in range(2)]
    no_payoff = [_moment(30, events=[(0, 4), (4, 22), (22, 30)]) for _ in range(2)]
    ms = with_payoff + no_payoff
    p = _plan([_seg(i, m, 0, 30, native="keep") for i, m in enumerate(ms)])
    f, _ = fit_plan_duration(p, _inputs(ms, 60))
    for s in f["segments"]:
        if s["asset_id"] in {m["id"] for m in with_payoff}:
            assert s["source_start_seconds"] <= 10 and s["source_end_seconds"] >= 21
        else:
            assert s["source_start_seconds"] <= 4 and s["source_end_seconds"] >= 22


def test_input_plan_is_never_mutated():
    ms = [_moment(20, peak=10) for _ in range(4)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])
    snap = repr(p)
    fit_plan_duration(p, _inputs(ms, 30))
    assert repr(p) == snap


# ---------------------------------------------------------------------------- engine adoption

def _model_plan(segs):
    return {"target_duration_seconds": 50, "feasible": True, "segments": copy.deepcopy(segs)}


def test_engine_ships_fitted_plan_and_records_it(monkeypatch):
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 50))
    total = sum(s.output_duration_seconds for s in out.segments)
    d = eng.last_diagnostics["duration_fit"]
    assert abs(total - 50) <= 5 and d["adopted"] and d["before_s"] == 80.0 and d["after_s"] == pytest.approx(total)
    assert all(s.transition is None for s in out.segments)                         # device renders straight cuts
    assert eng.last_diagnostics["completion"] == "complete"


def test_engine_preserves_opening_ending_and_ordering_directives(monkeypatch):
    ms = [_moment(20, peak=10) for _ in range(5)] + [_moment(20) for _ in range(3)]
    segs = [_seg(i, m, 2, 18) for i, m in enumerate(ms)]
    rc = {"mode": "explore", "directives": {"opening": ms[0]["id"], "ending": ms[7]["id"],
                                             "must_include": [ms[5]["id"]], "order_after": [[ms[6]["id"], ms[5]["id"]]]}}
    segs = [segs[0], segs[5], segs[6], segs[1], segs[2], segs[3], segs[4], segs[7]]
    for k, s in enumerate(segs):
        s["order"] = k
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan(segs)))
    out = eng.generate(_inputs(ms, 60, rc=rc))
    ids = [str(s.asset_id).lower() for s in out.segments]
    assert ids[0] == ms[0]["id"] and ids[-1] == ms[7]["id"]
    assert ms[5]["id"] in ids and ms[6]["id"] in ids and ids.index(ms[6]["id"]) > ids.index(ms[5]["id"])
    assert eng.last_diagnostics["duration_fit"]["adopted"] and eng.last_diagnostics["creative_satisfaction"] == 1.0


def test_engine_discloses_readably_when_cut_still_runs_long(monkeypatch):
    ms = [_moment(12, peak=6, event=(0, 12)) for _ in range(6)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan(
        [_seg(i, m, 0, 12, native="keep") for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 30))
    d = eng.last_diagnostics
    assert len(out.segments) == 6 and d["completion"] == "partial"
    assert any(u["code"] == "approx_duration" for u in d["material_unmet"])
    assert "approx_duration" not in d["partial_disclosure"]
    assert "instead of the requested 30s" in d["partial_disclosure"]


def test_engine_skips_fit_for_revise():
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 50, rc={"mode": "revise"}))
    assert sum(s.output_duration_seconds for s in out.segments) == pytest.approx(80.0)
    assert "duration_fit" not in eng.last_diagnostics


def test_engine_keeps_original_and_reports_it_when_fit_would_be_invalid(monkeypatch):
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))

    def broken(plan, inputs, protected_ids=None):
        bad = dict(plan, segments=[dict(s, source_end_seconds=99.0, output_duration_seconds=97.0) for s in plan["segments"]])
        return bad, {"applied": True, "before_s": 80.0, "after_s": 10.0, "target_s": 50.0, "within_band": True,
                     "trimmed": 5, "dropped": [], "changes": [{"order": 0}]}
    monkeypatch.setattr("edit_planner.duration_fit.fit_plan_duration", broken)
    out = eng.generate(_inputs(ms, 50))
    d = eng.last_diagnostics["duration_fit"]
    assert sum(s.output_duration_seconds for s in out.segments) == pytest.approx(80.0)
    assert d["adopted"] is False and d["after_s"] == 80.0 and d["trimmed"] == 0 and d["changes"] == []
    assert d["proposed"]["after_s"] == 10.0 and d["within_band"] is False


def test_explore_history_is_read_not_mutated_and_the_new_version_is_fitted():
    ms = [_moment(20, peak=10) for _ in range(5)]
    rc = {"mode": "explore", "base_version_id": "V1", "prior_edit_summaries": [
        {"version_id": "V1", "segments": [{"asset_id": m["id"], "output_duration_seconds": 10.0} for m in ms]}]}
    snap = copy.deepcopy(rc)
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 50, rc=rc))
    assert rc == snap
    assert abs(sum(s.output_duration_seconds for s in out.segments) - 50) <= 5


def test_infeasible_preference_short_cut_ships_unextended_and_empty_stays_terminal():
    ms = [_moment(4, peak=2) for _ in range(2)]
    plan = {"target_duration_seconds": 50, "feasible": False, "infeasible_reason": "not enough footage",
            "segments": [_seg(0, ms[0], 0, 4), _seg(1, ms[1], 0, 4)]}
    eng = RealEditPlannerEngine(FakeModelGateway(response=plan))
    out = eng.generate(_inputs(ms, 50))
    assert sum(s.output_duration_seconds for s in out.segments) == pytest.approx(8.0)
    assert eng.last_diagnostics["duration_fit"]["reason"] == "undershoot_not_extended"
    empty = {"target_duration_seconds": 50, "feasible": False, "infeasible_reason": "nothing usable", "segments": []}
    with pytest.raises(Exception):
        RealEditPlannerEngine(FakeModelGateway(response=empty)).generate(_inputs(ms, 50))


def test_feasible_false_overshoot_is_shipped_and_fitted():
    ms = [_moment(20, peak=10) for _ in range(5)]
    plan = {"target_duration_seconds": 50, "feasible": False, "infeasible_reason": "cannot condense",
            "segments": [_seg(i, m, 2, 18) for i, m in enumerate(ms)]}
    eng = RealEditPlannerEngine(FakeModelGateway(response=plan))
    out = eng.generate(_inputs(ms, 50))
    assert out.feasible is True and abs(sum(s.output_duration_seconds for s in out.segments) - 50) <= 5


# ---------------------------------------------------------------------------- device-acceptance regressions (2026-11-11)

def _multi_peak_moment(dur, peaks, events):
    m = _moment(dur, events=events)
    m["editorial"] = {"visual_candidates": [{"start_time": max(0.0, p - 1), "end_time": min(dur, p + 1),
                                             "peak_time": p, "confidence": c} for p, c in peaks]}
    return m


def test_every_payoff_in_a_shot_is_kept_not_only_the_strongest():
    # Real case D: boulder clip — raise poles (5.06, conf .95) then turn to face the camera (6.56, conf .90).
    boulder = _multi_peak_moment(6.86, [(5.06, 0.95), (6.56, 0.9)], [(0, 4.1), (4.1, 5.7), (5.7, 6.8)])
    # Real case C/D: church clip — backpack detail (1.33) and the pink-facade reveal (8.17).
    church = _multi_peak_moment(15.6, [(1.333, 0.85), (8.167, 0.88)], [(0, 4.5), (4.5, 11.2), (11.2, 15.6)])
    fillers = [_moment(20) for _ in range(6)]
    ms = [fillers[0], boulder, fillers[1], church, *fillers[2:]]
    segs = [_seg(0, fillers[0], 2, 18), _seg(1, boulder, 4.0, 6.8), _seg(2, fillers[1], 2, 18),
            _seg(3, church, 0.0, 11.5), *[_seg(4 + i, m, 2, 18) for i, m in enumerate(fillers[2:])]]
    p = _plan(segs)
    inp = _inputs(ms, 70)
    f, rep = fit_plan_duration(p, inp)
    assert rep["applied"]
    by = {s["asset_id"]: s for s in f["segments"]}
    assert by[boulder["id"]]["source_end_seconds"] >= 6.56            # the turn to camera survives
    assert by[church["id"]]["source_start_seconds"] <= 1.333          # the backpack detail survives
    assert by[church["id"]]["source_end_seconds"] >= 8.167
    _assert_shrunk_valid(p, f, inp)


def test_kept_native_audio_is_only_cut_on_au_event_boundaries():
    ms = [_moment(30, events=[(0, 3), (3, 9), (9, 14), (14, 21), (21, 30)]) for _ in range(5)]
    p = _plan([_seg(i, m, 0, 30, native="keep") for i, m in enumerate(ms)])   # 150s for 80s
    f, rep = fit_plan_duration(p, _inputs(ms, 80))
    assert rep["applied"]
    bounds = {0, 3, 9, 14, 21, 30}
    for s in f["segments"]:
        assert round(s["source_start_seconds"], 3) in bounds and round(s["source_end_seconds"], 3) in bounds


def test_ducked_audio_is_not_snapped():
    ms = [_moment(30, events=[(0, 3), (3, 9), (9, 14), (14, 21), (21, 30)]) for _ in range(5)]
    p = _plan([_seg(i, m, 0, 30, native="duck") for i, m in enumerate(ms)])
    f, rep = fit_plan_duration(p, _inputs(ms, 80))
    assert rep["within_band"]                                         # free to trim precisely to the target
    assert abs(delivered_total_seconds(f["segments"]) - 80) <= 1
