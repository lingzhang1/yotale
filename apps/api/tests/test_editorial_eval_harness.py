"""Offline evaluation harness (scripts/editorial_eval.py): deterministic, model-free, comparison-safe."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
sys.path.insert(0, os.path.dirname(__file__))

import editorial_eval as E                                  # noqa: E402
import _v55_fixtures as fx                                  # noqa: E402
import edit_planner as ep                                   # noqa: E402


def _job(jid, etype, mode, target, before, after, n_after, dropped=0, ver="edit_plan/5.3", calls=1, extra=None, n_moments=30):
    segs = [{"order": i, "asset_id": f"{i:08x}-0000-4000-8000-000000000000", "source_start_seconds": 0,
             "source_end_seconds": after / n_after, "output_duration_seconds": after / n_after, "native_audio": "keep"}
            for i in range(n_after)]
    d = {"model_calls": calls, "first_pass_executable": True, "completion": "complete", "sheet_count": 6,
         "prompt_version": ver, "editorial": {"requested": etype, "prompt_version": ver},
         "rev_diag": {"mode": mode}, "input_tokens": 1000, "output_tokens": 100, "model_id": "gpt-5.1",
         "duration_fit": {"applied": True, "adopted": True, "before_s": before, "after_s": after,
                          "changes": [1, 2], "dropped": [None] * dropped}}
    d.update(extra or {})
    return {"job_id": jid + "-0000", "created_at": 100, "updated_at": 145, "plan": {"target_duration_seconds": target,
            "segments": segs}, "diagnostics": d, "request_ref": {"sheet_order": json.dumps(
                [f"{i:08x}-0000-4000-8000-000000000000" for i in range(n_moments)])}}


def test_metrics_row_matches_the_worked_baseline_numbers():
    row = E.job_metrics(_job("aaaaaaaa", "highlights", None, 90, 158.6, 128.7, 24, dropped=1))
    assert row["pre_fit_total_s"] == 158.6 and row["pre_fit_overshoot_pct"] == 76.2
    assert row["delivered_s"] == 128.7 and row["delivered_overshoot_pct"] == 43.0
    assert row["pre_fit_shots"] == 25 and row["pre_fit_mean_s"] == 6.34
    assert row["operation"] == "original" and row["model_calls"] == 1 and row["job_latency_s"] == 45.0
    assert row["fit_changes"] == 2 and row["fit_dropped"] == 1 and row["target_source"] == "unrecorded"


def test_metrics_uses_recorded_selection_when_present():
    sel = {"budget": {"pre_fit_total_s": 100.0}, "pre_fit": {"n": 20}, "shots": {}, "used": [{"p": True}, {"p": False}],
           "opening": {"p": True}, "unused_payoff": [{"m": "x"}], "n_moments": 12, "editorial_type": "highlights"}
    row = E.job_metrics(_job("bbbbbbbb", "highlights", None, 90, 158.6, 95.0, 20, ver="edit_plan/5.5",
                             extra={"selection": sel}))
    assert row["pre_fit_total_s"] == 100.0 and row["pre_fit_shots"] == 20 and row["pre_fit_mean_s"] == 5.0
    assert row["payoff_shots"] == 1 and row["opening_is_payoff"] is True and row["unused_payoff_moments"] == 1
    assert row["moments"] == 12 and row["prompt_version"] == "edit_plan/5.5"


def test_compare_rejects_explore_vs_original():
    rows = [E.job_metrics(_job("aaaaaaaa", "full_story", None, 155, 170, 156, 29)),
            E.job_metrics(_job("bbbbbbbb", "full_story", "explore", 155, 172, 156, 29, ver="edit_plan/5.5"))]
    w = E.comparison_warnings(rows)
    assert any("INVALID COMPARISON" in x and "Explore must not be compared with an Original" in x for x in w)


def test_compare_flags_different_targets_and_same_version():
    rows = [E.job_metrics(_job("aaaaaaaa", "highlights", None, 90, 150, 100, 20)),
            E.job_metrics(_job("bbbbbbbb", "highlights", None, 60, 80, 62, 14))]
    w = " ".join(E.comparison_warnings(rows))
    assert "different target durations" in w and "not a baseline/candidate pair" in w


def test_clean_matched_pair_has_no_invalid_warning():
    rows = [E.job_metrics(_job("aaaaaaaa", "highlights", None, 90, 150, 100, 20)),
            E.job_metrics(_job("bbbbbbbb", "highlights", None, 90, 95, 91, 22, ver="edit_plan/5.5"))]
    assert not [x for x in E.comparison_warnings(rows) if x.startswith(("INVALID", "NOT COMPARABLE"))]


def test_markdown_states_quality_is_not_measured():
    md = E.to_markdown([E.job_metrics(_job("aaaaaaaa", "highlights", None, 90, 150, 100, 20))], [])
    assert "Quality is NOT measured here" in md and "| label |" in md


def test_render_is_offline_restores_state_and_shows_both_versions(tmp_path):
    case = {"creative_intent": {"target_duration_seconds": 90}, "moments": fx.red_jacket_group(), "sound_preference": None,
            "editorial_type": "highlights", "editorial_mode": "highlights", "creative_brief": fx.LEGACY_BRIEF,
            "n_placeholder_images": 5}
    cf = tmp_path / "case.json"; cf.write_text(json.dumps(case))
    before = (ep._EDIT_PLAN_VERSION, ep._v53_active, ep._v55_active)
    assert E.main(["render", "--case", str(cf), "--out", str(tmp_path / "o")]) == 0
    assert (ep._EDIT_PLAN_VERSION, ep._v53_active, ep._v55_active) == before        # module state restored
    u53 = (tmp_path / "o" / "5.3" / "user.txt").read_text()
    u55 = (tmp_path / "o" / "5.5" / "user.txt").read_text()
    assert "EDITORIAL TYPE = HIGHLIGHTS" in u53 and "TYPE STRATEGY — HIGHLIGHTS" in u55
    assert "BUDGET (advisory" in u55 and "BUDGET (advisory" not in u53
    assert (tmp_path / "o" / "user.diff").read_text().startswith("--- user@5.3")
    s = json.loads((tmp_path / "o" / "summary.json").read_text())
    assert s["5.3"]["budget_hint"] is None and s["5.5"]["budget_hint"]["suggested_shots"] == [10, 10]


def test_calls_are_split_planner_repair_and_critique():
    r = E.job_metrics(_job("aaaaaaaa", "highlights", None, 90, 100, 95, 20, calls=2, extra={"executability_repairs_used": 1}))
    assert (r["model_calls"], r["planner_calls"], r["repair_calls"], r["critique_attempted"]) == (2, 1, 1, False)
    c = E.job_metrics(_job("bbbbbbbb", "highlights", None, 90, 100, 95, 20, calls=3, extra={"critique_attempted": True}))
    assert c["planner_calls"] == 1 and c["critique_attempted"] is True


def test_compare_warns_when_critique_was_on():
    j = _job("aaaaaaaa", "highlights", None, 90, 100, 95, 20, calls=3, extra={"critique_attempted": True})
    j["critique_requested"] = True
    w = E.comparison_warnings([E.job_metrics(j)])
    assert any(x.startswith("CRITIQUE ON") and "STORY_CRITIQUE_REVISION" in x for x in w)
    assert not [x for x in E.comparison_warnings([E.job_metrics(_job("cccccccc", "highlights", None, 90, 100, 95, 20))])
                if x.startswith(("CRITIQUE", "PLANNER CALLS"))]
