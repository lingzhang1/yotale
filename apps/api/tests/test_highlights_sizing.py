"""highlights_sizing/1 — rule-based Highlights duration. Offline: no model, no AWS.

The numbers in the realistic cases are the measured AU payoff counts of the real development Stories (TMB Hiking:
38 Moments, 22 payoff windows in 21 Moments, 537 s useful; Girl with Dress: 21 Moments, 13 windows; Iceland: 68
Moments, 29 windows), so the formula is checked against the owner's data, not toy inputs."""
from __future__ import annotations

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.deps import get_duration_planner_engine                      # noqa: E402
from app.main import create_app                                       # noqa: E402
from duration_planner import RealDurationPlannerEngine, compute_duration_evidence   # noqa: E402
from duration_planner import highlights as H                          # noqa: E402
from model_gateway import FakeModelGateway                            # noqa: E402


def _story(n_moments: int, n_payoff_moments: int, windows_per: int = 1, *, useful: float = 14.0, wire: str = "compact",
           extra_payoff_in_first: int = 0) -> list[dict]:
    ms = []
    for i in range(n_moments):
        m = {"id": f"m{i:03d}", "duration_seconds": useful + 2, "useful_segments": [[0, useful]]}
        has = i < n_payoff_moments
        k = (windows_per if has else 0) + (extra_payoff_in_first if i == 0 else 0)
        wins = [[1.0 + 4 * j, 4.5 + 4 * j] for j in range(k)]
        if wire == "compact":
            m["payoff_windows"] = wins
        elif wire == "editorial":
            m["editorial"] = {"visual_candidates": [{"start_time": a, "end_time": b, "role": "payoff"} for a, b in wins]
                              + [{"start_time": 0, "end_time": 1, "role": "b_roll"}]}
        ms.append(m)
    return ms


def _rec(ms):
    ev = compute_duration_evidence(ms)
    return H.recommend_highlights(ms, ev), ev


def test_tmb_38_moments_with_22_payoff_windows_is_about_35_seconds_not_80():
    ms = _story(38, 21, windows_per=1, extra_payoff_in_first=1)          # 22 windows in 21 Moments
    h, ev = _rec(ms)
    assert ev["feasible_band_seconds"][0] == 76.0                        # the old floor the model was anchored on
    assert h["opportunities"] == 22 and h["moments_with_payoff"] == 21 and h["source"] == "payoff_windows"
    assert h["point_seconds"] == 35.0 and h["range"] == [30.0, 40.0] and sum(h["range"]) / 2 == 35.0
    assert h["uncertain"] is False


@pytest.mark.parametrize("moments,windows,expect", [(21, 13, 20.0), (68, 29, 45.0), (9, 2, 15.0), (12, 10, 15.0)])
def test_other_real_stories(moments, windows, expect):
    ms = _story(moments, windows, 1, useful=20.0)
    h, _ = _rec(ms)
    assert h["point_seconds"] == expect


def test_highlights_length_follows_opportunities_not_moment_count():
    few = _rec(_story(60, 6))[0]["point_seconds"]            # 60 clips, only 6 payoffs
    many = _rec(_story(12, 12, 2))[0]["point_seconds"]       # 12 clips, 24 payoffs
    assert few == 15.0 and many > few
    assert _rec(_story(10, 8))[0]["point_seconds"] == _rec(_story(80, 8))[0]["point_seconds"]   # same payoffs -> same size


def test_clamped_to_short_form_bounds_and_to_the_material():
    assert _rec(_story(200, 200, 2, useful=30))[0]["point_seconds"] == H.MAX_S
    assert _rec(_story(3, 0))[0]["point_seconds"] == H.MIN_S                # evidence present, none flagged -> floor
    tiny = _story(2, 2, 1, useful=3.0)                                      # 6 s of useful footage in total
    h, ev = _rec(tiny)
    assert ev["feasible_band_seconds"][1] == 6.0 and h["point_seconds"] == 6.0 and h["range"][1] <= 6.0


def test_a_clip_counts_at_most_two_windows_and_overlaps_merge():
    m = {"id": "x", "duration_seconds": 40, "useful_segments": [[0, 40]],
         "payoff_windows": [[1, 4], [3, 6], [10, 14], [20, 24], [30, 34]]}
    assert H.count_opportunities([m]) == (2, 1, True)                       # [1,6] merged, then capped at 2
    assert H.count_opportunities([{"id": "y", "payoff_windows": [[1, 1.2], ["a", 3]]}]) == (0, 0, True)   # degenerate/garbage ignored


def test_editorial_wire_shape_is_counted_the_same_and_only_payoff_roles():
    a = _rec(_story(38, 21, 1, wire="compact"))[0]
    b = _rec(_story(38, 21, 1, wire="editorial"))[0]
    assert a["opportunities"] == b["opportunities"] == 21 and a["point_seconds"] == b["point_seconds"]   # b_roll ignored


def test_no_visual_evidence_uses_a_damped_footage_estimate_and_is_flagged_uncertain():
    ms = _story(38, 0, wire="none")
    h, ev = _rec(ms)
    assert h["source"] == "footage_only" and h["uncertain"] is True
    assert h["opportunities"] == 19.0 and h["point_seconds"] == 30.0        # 0.5 per Moment, damped; not the 76 s floor
    assert h["point_seconds"] < ev["feasible_band_seconds"][0]


def test_range_midpoint_is_the_point_and_ranges_are_ordered():
    for n in (1, 5, 13, 22, 40, 90):
        h, _ = _rec(_story(max(n, 3), n, 1))
        lo, hi = h["range"]
        assert lo <= h["point_seconds"] <= hi and abs((lo + hi) / 2 - h["point_seconds"]) < 0.51


def test_apply_replaces_only_the_highlights_range_and_keeps_the_models_value_for_diagnosis():
    ms = _story(38, 21, 1, extra_payoff_in_first=1)
    ev = compute_duration_evidence(ms)
    model = {"recommended_range_seconds": [120, 150], "highlights_range_seconds": [80, 100],
             "feasible_ceiling_seconds": 500.0, "rationale": "r", "payoff_breathing": True}
    out = H.apply_highlights_sizing(dict(model), ms, ev)
    assert out["highlights_range_seconds"] == [30.0, 40.0]
    for k in ("recommended_range_seconds", "feasible_ceiling_seconds", "rationale", "payoff_breathing"):
        assert out[k] == model[k]
    s = out["sizing"]["highlights"]
    assert s["model_highlights_range"] == [80, 100] and s["version"] == "highlights_sizing/1" and s["source"] == "payoff_windows"
    assert H.apply_highlights_sizing(dict(model), ms, None)["highlights_range_seconds"] == [80, 100]   # internal failure: unchanged, never raises


def test_module_is_pure_and_the_frozen_prompt_and_evidence_are_untouched():
    src = open(H.__file__).read()
    for bad in ("gateway", "boto3", "requests", "StructuredRequest"):
        assert bad not in src
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    import duration_planner as dp
    assert dp.PROMPT_VERSION == "duration_recommendation/1"
    ev = compute_duration_evidence(_story(38, 21))
    assert ev["feasible_band_seconds"][0] == 76.0        # shared evidence unchanged: Full Story's input is as before


# ---- endpoint -------------------------------------------------------------------------------------------------
def _client(engine):
    app = create_app()
    app.dependency_overrides[get_duration_planner_engine] = lambda: engine
    return TestClient(app)


def _model(**over):
    r = {"recommended_range_seconds": [120, 150], "highlights_range_seconds": [80, 100], "feasible_ceiling_seconds": 530.0,
         "rationale": "scenic hike", "payoff_breathing": False}
    r.update(over)
    return r


def _body(ms, **kw):
    b = {"creative_intent": {"raw_text": "hike", "theme": "scenic"}, "moments": ms}
    b.update(kw)
    return b


def test_endpoint_highlights_follows_payoffs_full_story_follows_the_model():
    gw = FakeModelGateway(response=_model())
    c = _client(RealDurationPlannerEngine(gw))
    r = c.post("/v1/duration-recommendation", json=_body(_story(38, 21, 1, extra_payoff_in_first=1)))
    assert r.status_code == 200 and len(gw.calls) == 1                      # Full Story still uses ONE model call
    rec = r.json()["recommendation"]
    assert rec["highlights_range_seconds"] == [30.0, 40.0]                    # was the model's 80-100
    assert rec["recommended_range_seconds"] == [120, 150]                     # Full Story unchanged
    assert rec["sizing"]["highlights"]["model_highlights_range"] == [80, 100]
    assert set(rec) >= {"recommended_range_seconds", "highlights_range_seconds", "feasible_ceiling_seconds", "rationale"}  # iOS DTO keys intact


def test_endpoint_old_client_without_payoff_data_still_gets_a_sane_highlights_range():
    c = _client(RealDurationPlannerEngine(FakeModelGateway(response=_model())))
    rec = c.post("/v1/duration-recommendation", json=_body(_story(38, 0, wire="none"))).json()["recommendation"]
    assert rec["highlights_range_seconds"] == [26.0, 34.0]                  # 19 estimated opportunities -> 30 s, not 80
    assert rec["sizing"]["highlights"]["source"] == "footage_only" and rec["sizing"]["highlights"]["uncertain"] is True


def test_endpoint_model_failure_keeps_the_existing_manual_fallback_and_custom_stays_authoritative():
    from model_gateway import ProviderError
    c = _client(RealDurationPlannerEngine(FakeModelGateway(error=ProviderError("down"))))
    d = c.post("/v1/duration-recommendation", json=_body(_story(10, 5), creative_intent={"target_duration_seconds": 90})).json()
    assert d["recommendation"] is None and d["explicit_target_seconds"] == 90.0 and d["evidence"]["n_moments"] == 10
