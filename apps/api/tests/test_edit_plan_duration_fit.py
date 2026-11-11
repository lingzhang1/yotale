"""Deterministic duration fit (packages/edit_planner/duration_fit.py) + its adoption in RealEditPlannerEngine.

No model is invoked. Plans are built so every segment is technically valid (in-bounds, span/speed consistent);
the fit must keep them valid, shrink only, keep AU payoffs, honor directives / music anchors / native audio,
and report honestly when the cut still runs long."""
from __future__ import annotations

from uuid import uuid4

import pytest

from edit_planner import EditPlanInputs, RealEditPlannerEngine, validate_plan
from edit_planner.duration_fit import FIT_BAND, MIN_SEGMENT_OUT_S, delivered_total_seconds, fit_plan_duration
from model_gateway import FakeModelGateway


def _moment(dur=20.0, peak=None, event=None, cand=None):
    m = {"id": str(uuid4()), "duration_seconds": dur, "useful_segments": [[0.0, dur]], "summary": "x"}
    if peak is not None:
        a, b = cand or (max(0.0, peak - 2), min(dur, peak + 2))
        m["editorial"] = {"visual_candidates": [{"start_time": a, "end_time": b, "peak_time": peak, "confidence": 0.9}]}
    m["events"] = [{"start_time": e[0], "end_time": e[1], "description": "e"} for e in ([event] if event else [])]
    return m


def _seg(order, m, a, b, speed=1.0, native="keep", anchor=None, transition=None):
    s = {"order": order, "asset_id": m["id"], "source_start_seconds": a, "source_end_seconds": b,
         "output_duration_seconds": round((b - a) / speed, 3), "speed": speed, "native_audio": native}
    if anchor:
        s["music_alignment"] = {"anchor": anchor}
    if transition:
        s["transition"] = transition
    return s


def _inputs(moments, target, etype="highlights", rc=None):
    return EditPlanInputs(story_id=str(uuid4()), creative_intent_id=str(uuid4()),
                          creative_intent={"target_duration_seconds": float(target)}, story_guide={}, story_coverage={},
                          moments=moments, music_plan={}, editorial_type=etype, revision_context=rc)


def _plan(segs):
    return {"target_duration_seconds": 0, "feasible": True, "segments": segs}


def _assert_shrunk_valid(orig, fitted, inputs):
    assert validate_plan(fitted, inputs) == []
    by = {}
    for s in orig["segments"]:
        by.setdefault(s["asset_id"], []).append(s)
    for k, s in enumerate(fitted["segments"]):
        assert s["order"] == k
        assert any(o["source_start_seconds"] - 1e-6 <= s["source_start_seconds"]
                   and s["source_end_seconds"] <= o["source_end_seconds"] + 1e-6
                   and o["speed"] == s["speed"] and o["native_audio"] == s["native_audio"]
                   for o in by[s["asset_id"]]), "a fitted range must lie inside an original segment of that Moment"
        assert abs(s["output_duration_seconds"] - (s["source_end_seconds"] - s["source_start_seconds"]) / s["speed"]) < 0.01


def _payoffs_kept(fitted, moments):
    mm = {m["id"]: m for m in moments}
    for s in fitted["segments"]:
        for vc in (mm[s["asset_id"]].get("editorial") or {}).get("visual_candidates", []):
            p = vc["peak_time"]
            yield p, s["source_start_seconds"] <= p <= s["source_end_seconds"]


# ---------------------------------------------------------------------------- per-length / per-type fits

@pytest.mark.parametrize("target,etype", [(32, "highlights"), (50, "highlights"), (50, "full_story")])
def test_overlong_plan_is_pulled_into_band_and_keeps_payoffs(target, etype):
    ms = [_moment(20, peak=10, event=(8, 12)) for _ in range(7)]
    per = target * 1.45 / 7
    p = _plan([_seg(i, m, 10 - per / 2, 10 + per / 2) for i, m in enumerate(ms)])
    inp = _inputs(ms, target, etype)
    f, rep = fit_plan_duration(p, inp)
    assert rep["applied"] and rep["within_band"]
    assert abs(delivered_total_seconds(f["segments"]) - target) <= target * FIT_BAND
    assert len(f["segments"]) == 7                         # payoff shots are never dropped
    assert all(kept for _, kept in _payoffs_kept(f, ms))
    _assert_shrunk_valid(p, f, inp)


def test_full_story_keeps_the_whole_payoff_event():
    ms = [_moment(30, peak=12, event=(6, 18)) for _ in range(4)]
    p = _plan([_seg(i, m, 0, 30, native="duck") for i, m in enumerate(ms)])   # 120s for a 50s target
    f, rep = fit_plan_duration(p, _inputs(ms, 50, "full_story"))
    for s in f["segments"]:
        assert s["source_start_seconds"] <= 6 and s["source_end_seconds"] >= 18   # complete action survives
    h, _ = fit_plan_duration(p, _inputs(ms, 50, "highlights"))
    assert any(s["source_start_seconds"] > 6 or s["source_end_seconds"] < 18 for s in h["segments"])  # Highlights may cut inside it


def test_user_exact_custom_duration_is_also_fitted():
    ms = [_moment(20, peak=10) for _ in range(5)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])                      # 80s for 45s
    inp = _inputs(ms, 45, rc={"mode": "explore", "duration_target_source": "user_exact"})
    f, rep = fit_plan_duration(p, inp)
    assert rep["within_band"] and abs(delivered_total_seconds(f["segments"]) - 45) <= 4.5


def test_short_footage_undershoot_is_never_extended():
    ms = [_moment(6, peak=3) for _ in range(4)]
    p = _plan([_seg(i, m, 0, 6) for i, m in enumerate(ms)])                       # 24s, target 50
    f, rep = fit_plan_duration(p, _inputs(ms, 50))
    assert f is p and not rep["applied"] and rep["reason"] == "undershoot_not_extended"


def test_within_band_plan_is_untouched():
    ms = [_moment(20, peak=10) for _ in range(5)]
    p = _plan([_seg(i, m, 5, 15.8) for i, m in enumerate(ms)])                    # 54s for 50 (+8%)
    f, rep = fit_plan_duration(p, _inputs(ms, 50))
    assert f is p and not rep["applied"] and rep["reason"] == "within_band"


def test_excessively_long_plan_drops_low_value_shots_then_fits():
    pay = [_moment(20, peak=10) for _ in range(3)]
    scenic = [_moment(20) for _ in range(6)]                                      # no AU payoff
    order = [pay[0]] + scenic[:3] + [pay[1]] + scenic[3:] + [pay[2]]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(order)])                   # 144s for 15s (+860%)
    inp = _inputs(order, 15)   # trimming to floors (~19.5s) is not enough -> optional no-payoff shots go
    f, rep = fit_plan_duration(p, inp)
    assert rep["within_band"] and rep["dropped"]
    kept = {s["asset_id"] for s in f["segments"]}
    assert {m["id"] for m in pay} <= kept                                         # every payoff shot stays
    assert f["segments"][0]["asset_id"] == pay[0]["id"] and f["segments"][-1]["asset_id"] == pay[2]["id"]
    assert all(s["output_duration_seconds"] >= MIN_SEGMENT_OUT_S - 1e-6 for s in f["segments"])
    _assert_shrunk_valid(p, f, inp)


def test_repeated_footage_of_one_moment_is_dropped_but_a_distinct_recut_with_payoff_stays():
    a = _moment(30, peak=5)
    a["editorial"]["visual_candidates"].append({"start_time": 20, "end_time": 26, "peak_time": 23, "confidence": 0.8})
    b, c = _moment(20, peak=10), _moment(20, peak=10)
    p = _plan([_seg(0, b, 2, 18), _seg(1, a, 0, 12), _seg(2, a, 3, 11), _seg(3, a, 19, 27), _seg(4, c, 2, 18)])
    f, rep = fit_plan_duration(p, _inputs([a, b, c], 36))
    assert [d["why"] for d in rep["dropped"]] == ["repeats_footage"]             # 3-11 repeats 0-12
    assert sum(s["asset_id"] == a["id"] for s in f["segments"]) == 2             # 19-27 (own payoff) kept


def test_required_and_ordered_moments_are_never_dropped():
    pay0, pay1 = _moment(20, peak=10), _moment(20, peak=10)
    req = [_moment(20) for _ in range(3)]                                         # no payoff, but directive-referenced
    order = [pay0] + req + [pay1]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(order)])                   # 80s for 20s
    protected = {req[0]["id"], req[1]["id"], req[2]["id"]}
    f, rep = fit_plan_duration(p, _inputs(order, 8), protected_ids=protected)   # floors (11s) > band
    assert [s["asset_id"] for s in f["segments"]] == [m["id"] for m in order]    # same shots, same order
    assert not rep["dropped"] and not rep["within_band"]                          # honest: still long


def test_only_selected_moments_policy_never_adds_a_moment():
    ms = [_moment(20, peak=10) for _ in range(4)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])
    f, _ = fit_plan_duration(p, _inputs(ms, 40))
    assert {s["asset_id"] for s in f["segments"]} <= {s["asset_id"] for s in p["segments"]}


def test_music_anchor_is_untouched_and_crossfade_clamped_and_not_subtracted():
    ms = [_moment(20, peak=10) for _ in range(4)]
    segs = [_seg(0, ms[0], 2, 18), _seg(1, ms[1], 2, 18, anchor="downbeat"),
            _seg(2, ms[2], 2, 18, transition={"type": "crossfade", "duration_seconds": 6.0}), _seg(3, ms[3], 2, 18)]
    p = _plan(segs)
    assert delivered_total_seconds(p["segments"]) == 64.0                         # contract drops transitions
    f, rep = fit_plan_duration(p, _inputs(ms, 40))
    anchored = next(s for s in f["segments"] if (s.get("music_alignment") or {}).get("anchor") == "downbeat")
    assert (anchored["source_start_seconds"], anchored["source_end_seconds"]) == (2, 18)
    xf = next(s for s in f["segments"] if s.get("transition"))
    assert xf["transition"]["duration_seconds"] <= xf["output_duration_seconds"]
    assert rep["within_band"]


def test_native_audio_keep_does_not_cut_inside_the_payoff_event():
    ms = [_moment(30, peak=15, event=(10, 21)) for _ in range(4)]
    p = _plan([_seg(i, m, 0, 30, native="keep") for i, m in enumerate(ms)])
    f, _ = fit_plan_duration(p, _inputs(ms, 50))
    for s in f["segments"]:
        assert s["source_start_seconds"] <= 10 and s["source_end_seconds"] >= 21


def test_input_plan_is_never_mutated():
    ms = [_moment(20, peak=10) for _ in range(4)]
    p = _plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])
    snap = repr(p)
    fit_plan_duration(p, _inputs(ms, 30))
    assert repr(p) == snap


# ---------------------------------------------------------------------------- engine adoption

def _model_plan(segs):
    return {"target_duration_seconds": 50, "feasible": True,
            "segments": [{k: v for k, v in s.items()} for s in segs]}


def test_engine_ships_fitted_plan_and_records_it(monkeypatch):
    monkeypatch.setenv("STORY_EDITPLAN_OBJECTIVE_DIRECTIVES", "1")
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 50))
    total = sum(s.output_duration_seconds for s in out.segments)
    assert abs(total - 50) <= 5
    d = eng.last_diagnostics["duration_fit"]
    assert d["adopted"] and d["before_s"] == 80.0 and d["within_band"]
    assert eng.last_diagnostics["completion"] == "complete"


def test_engine_discloses_when_cut_still_runs_long(monkeypatch):
    monkeypatch.setenv("STORY_EDITPLAN_OBJECTIVE_DIRECTIVES", "1")
    ms = [_moment(12, peak=6, event=(0, 12)) for _ in range(6)]                  # keep-audio events fill each clip
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 0, 12) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 30))
    assert len(out.segments) == 6                                                 # still a playable video
    assert eng.last_diagnostics["completion"] == "partial"
    assert any(u["code"] == "approx_duration" for u in eng.last_diagnostics["material_unmet"])


def test_engine_skips_fit_for_revise(monkeypatch):
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))
    out = eng.generate(_inputs(ms, 50, rc={"mode": "revise"}))
    assert sum(s.output_duration_seconds for s in out.segments) == pytest.approx(80.0)
    assert "duration_fit" not in eng.last_diagnostics


def test_engine_keeps_original_when_fit_would_be_invalid(monkeypatch):
    ms = [_moment(20, peak=10) for _ in range(5)]
    eng = RealEditPlannerEngine(FakeModelGateway(response=_model_plan([_seg(i, m, 2, 18) for i, m in enumerate(ms)])))

    def broken(plan, inputs, protected_ids=None):
        bad = dict(plan, segments=[dict(s, source_end_seconds=99.0, output_duration_seconds=97.0) for s in plan["segments"]])
        return bad, {"applied": True, "before_s": 80.0, "after_s": 10.0, "target_s": 50.0, "within_band": True,
                     "trimmed": 5, "dropped": []}
    monkeypatch.setattr("edit_planner.duration_fit.fit_plan_duration", broken)
    out = eng.generate(_inputs(ms, 50))
    assert sum(s.output_duration_seconds for s in out.segments) == pytest.approx(80.0)
    assert eng.last_diagnostics["duration_fit"]["adopted"] is False


def test_infeasible_preference_short_cut_ships_unextended_and_empty_stays_terminal():
    # Owner policy 2026-10-25: a playable short cut ships (never extended by the fit); only an empty plan is terminal.
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
