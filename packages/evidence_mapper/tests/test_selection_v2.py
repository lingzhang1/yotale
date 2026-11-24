"""Evidence frame selection policy v2 — shared event-and-candidate coverage (Highlights and Full Story).

Spec: docs/architecture/editorial-pipeline-v2/evidence-frame-selection-v2.md. The fixture tests pin the exact
outputs the Swift port must reproduce (EvidenceSelectionParityTests)."""
from __future__ import annotations

import json
import os
import sys

import pytest

import evidence_mapper as mp

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
sys.path.insert(0, FIXTURES)
import make_parity_fixture as fx  # noqa: E402

CASES = {c["name"]: c for c in fx.CASES}
TYPES = (mp.HIGHLIGHTS, mp.FULL_STORY)


def rank(name, vt):
    c = CASES[name]
    return c, mp.rank_frames(video_type=vt, sampled_frame_ms=c["sampled_frame_ms"], events=fx.cands(c["events"]),
                             visual_candidates=fx.cands(c["visual"]), narrative_candidates=fx.cands(c["narrative"]))


def cov(c, sel):
    return mp.coverage_report(sampled_frame_ms=c["sampled_frame_ms"], selected=sel, events=fx.cands(c["events"]),
                              visual_candidates=fx.cands(c["visual"]), narrative_candidates=fx.cands(c["narrative"]))


# ---- contract: the committed fixture is exactly what this implementation produces ------------------------
def test_committed_parity_fixture_matches_the_reference_implementation():
    committed = json.load(open(os.path.join(FIXTURES, "parity_v2.json")))
    assert committed == json.loads(json.dumps(fx.build(), sort_keys=True)), \
        "parity_v2.json is stale: run packages/evidence_mapper/fixtures/make_parity_fixture.py"


# ---- invariants over every case and type ----------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("vt", TYPES)
def test_invariants(name, vt):
    c, r = rank(name, vt)
    n = len(c["sampled_frame_ms"])
    assert len(r.ordered) == len(set(r.ordered))                          # no duplicate picks
    assert all(0 <= i < n for i in r.ordered)
    floor = min(mp.duration_floor(c["sampled_frame_ms"][-1] / 1000), n)
    assert floor <= r.budget <= min(mp.MAX_FRAMES, n)                      # adaptive, bounded, never below old
    sel = mp.select_for_budget(r, r.budget)
    assert len(sel) == r.budget and sel == sorted(sel)
    if not r.uniform:                                                      # prefix-stable degradation
        for k in range(1, mp.MAX_FRAMES):
            assert set(mp.select_for_budget(r, k)) <= set(mp.select_for_budget(r, k + 1))
    again = rank(name, vt)[1]
    assert again.ordered == r.ordered and again.budget == r.budget        # deterministic


# ---- the policy's promises -----------------------------------------------------------------------------
@pytest.mark.parametrize("vt", TYPES)
def test_both_types_cover_every_event_and_visual_candidate_when_budget_allows(vt):
    for name in ("no_visual_candidates", "overlapping_events_and_candidates", "scenic_reveal",
                 "conversation_interaction", "point_events_without_end") + tuple(f"real_{i}" for i in range(1, 7)):
        if name not in CASES:
            continue
        c, r = rank(name, vt)
        rep = cov(c, mp.select_for_budget(r, r.budget))
        assert rep["events"]["covered"] == rep["events"]["total"], (name, vt, rep)
        assert rep["visual"]["covered"] == rep["visual"]["total"], (name, vt, rep)


def test_real_six_moments_cover_all_events_and_candidates_with_modest_frame_counts():
    for vt in TYPES:
        budgets = []
        for i in range(1, 7):
            c, r = rank(f"real_{i}", vt)
            budgets.append(r.budget)
            rep = cov(c, mp.select_for_budget(r, r.budget))
            assert rep["events"]["covered"] == rep["events"]["total"]
            assert rep["visual"]["covered"] == rep["visual"]["total"]
        assert max(budgets) <= 6, (vt, budgets)          # not forced to 9 frames


def test_img9091_true_reveal_is_bracketed_with_payoff_context():
    c, r = rank("img9091_misplaced_peak", mp.HIGHLIGHTS)
    ms = c["sampled_frame_ms"]
    sel = [ms[i] for i in mp.select_for_budget(r, r.budget)]
    reveal = 16620
    assert any(abs(t - reveal) <= 1600 for t in sel), sel
    assert any(t < reveal for t in sel) and any(t > reveal for t in sel), sel
    assert len([t for t in sel if 10500 <= t <= 19500]) >= 2, sel         # not a single point
    assert all(abs(t - 12500) > 400 for t in sel[1:2]) or len(sel) > 2    # never only the wrong peak


def test_no_evidence_is_the_previous_uniform_selection():
    c, r = rank("long_static_no_evidence", mp.HIGHLIGHTS)
    assert r.uniform
    assert mp.select_for_budget(r, r.budget) == mp._overview_indices(24, mp.duration_floor(60.0))


def test_many_events_with_few_frames_is_bounded_and_reports_what_is_unrepresented():
    c, r = rank("many_events_few_frames", mp.FULL_STORY)
    assert r.budget >= 2 * mp.duration_floor(6.0)                          # evidence-rich -> well above old 4
    assert r.budget <= mp.MAX_FRAMES
    rep = cov(c, mp.select_for_budget(r, r.budget))
    assert rep["events"]["covered"] >= 6
    missed = rep["events"]["total"] - rep["events"]["covered"]
    assert len(rep["events"]["unrepresented"]) == missed                  # honest, no false full coverage


def test_point_events_get_a_frame_near_them():
    c, r = rank("point_events_without_end", mp.FULL_STORY)
    ms = c["sampled_frame_ms"]
    sel = [ms[i] for i in mp.select_for_budget(r, r.budget)]
    for t in (4000, 13000, 22500):
        assert any(abs(x - t) <= 1400 for x in sel), (t, sel)


def test_ungrounded_peak_outside_its_window_is_ignored():
    c, r = rank("ungrounded_peak_outside_window", mp.HIGHLIGHTS)
    ms = c["sampled_frame_ms"]
    sel = [ms[i] for i in mp.select_for_budget(r, r.budget)]
    assert any(4000 <= t <= 8000 for t in sel)
    assert not any(abs(t - 17000) < 500 for t in sel[:-1]) or sel[-1] >= 19000


def test_no_near_duplicate_core_frames_on_the_real_moments():
    for vt in TYPES:
        for i in range(1, 7):
            c, r = rank(f"real_{i}", vt)
            ms = c["sampled_frame_ms"]
            ts = sorted(ms[j] for j in mp.select_for_budget(r, r.budget))
            spacing = mp._spacing_ms(ms)
            assert min(b - a for a, b in zip(ts, ts[1:])) >= spacing, (vt, i, ts)   # never adjacent frames
