"""Revise "no-op" verdict must account for SHOT TIMING (device test 2026-11-06).

A revise "Shorten each shot to around 5 seconds" returned the same 8 clips in the same order but with different
in/out points and shot lengths (total 32.6s -> 38.2s). The continuity check compared only clip ids + order, so it
reported "the change you asked for didn't alter the edit — effectively the same as your current one", which is
false. A retime IS an edit. A genuinely identical cut must still be reported as a no-op (honest "couldn't apply").

The fixtures below are the REAL base/revised segment timings from the failing dev job.
"""
from __future__ import annotations

import edit_planner as ep

# (asset prefix, source_start, source_end, output_duration) — real values from dev jobs f38e7cfa (base) / f8b414f5.
_IDS = ["eec285e2", "0fb19f5c", "6b520717", "86f45acd", "388fd8d6", "1d1c65b0", "55ec8e0e", "43e129bb"]
_BASE = [(3.0, 8.5, 5.5), (11.2, 15.7, 4.5), (0.0, 2.8, 2.8), (4.8, 8.3, 3.5),
         (13.0, 17.3, 4.3), (8.5, 12.5, 4.0), (9.5, 13.46, 3.96), (1.5, 5.5, 4.0)]
_REVISED = [(3.0, 8.0, 5.0), (11.2, 16.1, 4.9), (0.0, 5.0, 5.0), (4.8, 8.5, 3.7),
            (13.0, 18.0, 5.0), (8.5, 13.5, 5.0), (0.0, 5.0, 5.0), (1.5, 6.152, 4.652)]


def _plan(rows, ids=_IDS):
    return {"target_duration_seconds": 35.0, "feasible": True, "segments": [
        {"order": i, "asset_id": ids[i], "source_start_seconds": a, "source_end_seconds": b,
         "output_duration_seconds": d, "native_audio": "keep"} for i, (a, b, d) in enumerate(rows)]}


def _rc(**over):
    return {"mode": "revise", "soft_direction": "Shorten each shot to around 5 seconds",
            "directives": {"must_include": [_IDS[0]], "order_after": []}, **over}


def test_real_failing_case_retime_with_same_clips_and_order_is_a_real_edit_not_a_noop():
    cont = ep._continuity_assessment(_plan(_BASE), _plan(_REVISED), _rc())
    assert cont is not None
    assert cont["verdict"] != "noop", "every shot's timing changed (32.6s -> 38.2s): that is an edit"
    assert cont["verdict"] == "ok"
    assert cont["retimed"] is True
    assert cont["reordered"] is False


def test_identical_cut_is_still_an_honest_noop():
    cont = ep._continuity_assessment(_plan(_BASE), _plan(_BASE), _rc())
    assert cont["verdict"] == "noop"
    assert cont["retimed"] is False


def test_sub_threshold_normalization_jitter_is_still_a_noop():
    # <= 0.2s differences (e.g. clamping to a Moment's end) are not an edit the user would notice.
    jittered = [(a + 0.05, b - 0.1, d - 0.1) for (a, b, d) in _BASE]
    cont = ep._continuity_assessment(_plan(_BASE), _plan(jittered), _rc())
    assert cont["verdict"] == "noop"


def test_a_single_clip_retime_beyond_threshold_counts():
    rows = list(_BASE)
    a, b, d = rows[3]
    rows[3] = (a, b - 1.0, d - 1.0)               # one shot 1s shorter
    cont = ep._continuity_assessment(_plan(_BASE), _plan(rows), _rc())
    assert cont["verdict"] == "ok" and cont["retimed"] is True


def test_speed_change_counts_as_a_retime():
    revised = _plan(_BASE)
    revised["segments"][0]["speed"] = 1.5
    cont = ep._continuity_assessment(_plan(_BASE), revised, _rc())
    assert cont["verdict"] == "ok" and cont["retimed"] is True


def test_segment_count_change_is_not_a_noop():
    longer = _plan(_BASE + [(0.0, 3.0, 3.0)], ids=_IDS + [_IDS[0]])
    cont = ep._continuity_assessment(_plan(_BASE), longer, _rc())
    assert cont["verdict"] != "noop"


def test_order_change_alone_is_still_a_real_edit():
    ids = list(_IDS); ids[0], ids[1] = ids[1], ids[0]
    cont = ep._continuity_assessment(_plan(_BASE), _plan(_BASE, ids=ids), _rc())
    assert cont["verdict"] == "ok" and cont["reordered"] is True
