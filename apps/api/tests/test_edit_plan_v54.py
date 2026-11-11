"""EditPlan v5.4 EXPERIMENT — version-scoping tests (no live model). v5.4 changes ONLY user-message wording
(visual-evidence interpretation + one per-type sentence on AU events). These pin that v5.3 stays a valid,
byte-identical control and that the 5.4 system body is 5.3 verbatim."""
from __future__ import annotations
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import edit_planner
from edit_planner import EditPlanInputs, _build_user

_CI = {"target_duration_seconds": 30}
_V53_VISUAL = (
    "VISUAL EVIDENCE: in addition to the text, you receive timestamped contact-sheet frames for each "
    "Moment, labeled with Moment id and source timestamp. Use them to judge visual distinctness, "
    "composition, expressiveness and precise source ranges. Frames are evidence for the SAME Moments "
    "in the JSON — never invent footage not present.\n")


def _inputs(**kw):
    base = dict(story_id="s", creative_intent_id="c", creative_intent=_CI, story_guide={}, story_coverage={},
                moments=[{"id": "m1", "duration_seconds": 30, "useful_segments": [[0, 10]]}], music_plan={},
                images=[object()], image_moment_order=["m1"])
    base.update(kw)
    return EditPlanInputs(**base)


def _version(monkeypatch, v53: bool, v54: bool):
    monkeypatch.setattr(edit_planner, "_v53_active", lambda: v53)
    monkeypatch.setattr(edit_planner, "_v54_active", lambda: v54)


def test_v53_control_keeps_the_shipped_visual_wording(monkeypatch):
    _version(monkeypatch, True, False)
    u = _build_user(_inputs(editorial_type="highlights"))
    assert _V53_VISUAL in u                                   # byte-identical shipped block
    assert "EVIDENCE ANCHOR" not in u and "COMPARE MOMENTS" not in u
    assert "how the action builds" not in u                   # no v5.4 per-type sentence


def test_v54_replaces_precise_source_range_claim(monkeypatch):
    _version(monkeypatch, True, True)
    u = _build_user(_inputs(editorial_type="highlights"))
    assert "precise source ranges" not in u
    assert "SPARSE samples" in u and "EVIDENCE ANCHOR" in u and "NOT an exact action or cut boundary" in u
    assert "COMPARE MOMENTS WITH EACH OTHER" in u
    assert "never invent footage not present" in u           # hard grounding sentence kept
    assert "EDITORIAL TYPE = HIGHLIGHTS" in u                 # v5.3 type directive still present


def test_v54_per_type_sentences(monkeypatch):
    _version(monkeypatch, True, True)
    h = _build_user(_inputs(editorial_type="highlights"))
    f = _build_user(_inputs(editorial_type="full_story"))
    assert "how the action builds" in h and "Do NOT assume the order of the Moments" not in h
    assert "Do NOT assume the order of the Moments" in f and "how the action builds" not in f
    assert "EDITORIAL TYPE = FULL STORY" in f


def test_v54_adds_nothing_without_images_or_type(monkeypatch):
    _version(monkeypatch, True, True)
    u = _build_user(_inputs(images=[], image_moment_order=[], editorial_type=None))
    assert "VISUAL EVIDENCE" not in u and "how the action builds" not in u


def test_version_parse(monkeypatch):
    for v, exp in (("5.3", False), ("5.4", True), ("5.2", False), ("5", False), ("garbage", False)):
        monkeypatch.setattr(edit_planner, "_EDIT_PLAN_VERSION", v)
        assert edit_planner._v54_active() is exp, v
    monkeypatch.setattr(edit_planner, "_EDIT_PLAN_VERSION", "5.4")
    assert edit_planner._v53_active() is True                # 5.4 keeps every v5.3 behavior


def test_54_system_body_is_53_verbatim():
    base = Path(edit_planner.__file__).resolve().parent.parent.parent / "prompts" / "edit_plan"

    def body(v):
        return (base / v / "system.md").read_text().split("-->", 1)[1].strip()
    assert body("5.4") == body("5.3")
