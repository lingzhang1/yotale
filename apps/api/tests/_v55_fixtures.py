"""Shared offline fixtures for the EditPlan v5.5 (Editorial vNext M1) tests. No model, no AWS, no media.

The golden strings in `fixtures/edit_plan_v53_golden.json` were generated from the UNMODIFIED v5.3 planner code
(master e339173) with `regenerate_golden()`; the v5.5 work must keep every one of them byte-identical.
"""
from __future__ import annotations
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from model_gateway import ImageInput                                   # noqa: E402
import edit_planner                                                    # noqa: E402
from edit_planner import EditPlanInputs                                # noqa: E402

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "edit_plan_v53_golden.json")

LEGACY_BRIEF = ("When user intent does not require chronology, prioritize visually engaging and meaningful footage. "
                "Find a compelling opening, construct coherent visual progression, preserve important actions and "
                "payoffs, and choose shot durations appropriate to the material. Do not force a conventional "
                "travel-diary structure.")


def _moment(mid: str, dur: float, useful, *, visual=None, narrative=None, events=None, frames=None) -> dict:
    m = {"id": mid, "duration_seconds": dur, "useful_segments": useful, "summary": f"summary {mid}"}
    if visual is not None or narrative is not None:
        m["editorial"] = {"analysis_version": "v2_editorial",
                          "visual_candidates": visual or [], "narrative_candidates": narrative or []}
    if events is not None:
        m["events"] = events
    if frames is not None:
        m["sampled_frame_ms"] = frames
    return m


def red_jacket_group() -> list[dict]:
    """Three near-similar 'arms raised in a red jacket' Moments with different visual outcomes plus context footage.
    Mirrors the TMB evaluation case; the tests assert the PROMPT asks for a comparison, never which Moment wins."""
    def vc(s, e, role, conf, text, peak=None):
        d = {"start_time": s, "end_time": e, "role": role, "confidence": conf, "visual_value": text,
             "evidence": "frames 1-9 FABRICATED-PROVENANCE"}
        if peak is not None:
            d["peak_time"] = peak
        return d
    return [
        _moment("aaaaaaaa-0000-4000-8000-000000000001", 7.8, [[0, 3], [3.2, 7.5]],
                visual=[vc(0, 3, "payoff", 0.90, "Close red jacket, arms thrown wide against peaks", 1.3)],
                narrative=[{"start_time": 0, "end_time": 7.5, "role": "payoff", "confidence": 0.9,
                            "what_happens": "Hiker raises arms then gazes up", "why_matters": "triumph"}],
                events=[{"start_time": 0, "end_time": 2.6, "description": "arms raised"}],
                frames=[0, 313, 647]),
        _moment("aaaaaaaa-0000-4000-8000-000000000002", 15.0, [[0, 5.2], [9.5, 14.38]],
                visual=[vc(0, 5.2, "payoff", 0.95, "Small figure on a hazy meadow, arms up", 3.75)],
                narrative=[{"start_time": 0, "end_time": 6.2, "role": "payoff", "confidence": 0.92,
                            "what_happens": "Hiker raises arms in celebration", "why_matters": "summit beat"}],
                frames=[0, 615, 1248]),
        _moment("aaaaaaaa-0000-4000-8000-000000000003", 6.4, [[1.58, 6.12]],
                visual=[vc(1.58, 4.5, "payoff", 0.95, "Wide Mont Blanc panorama, arms spread", 2.92)],
                narrative=[{"start_time": 1.32, "end_time": 6.12, "role": "payoff", "confidence": 0.92,
                            "what_happens": "Hiker spreads arms toward the range", "why_matters": "scenic payoff"}],
                frames=[0, 252, 518]),
        _moment("aaaaaaaa-0000-4000-8000-000000000004", 12.6, [[0, 10.5]],
                visual=[vc(0, 4, "establishing", 0.85, "Dawn village below the mountains")],
                narrative=[{"start_time": 0, "end_time": 10.5, "role": "context", "confidence": 0.8,
                            "what_happens": "Village at dawn", "why_matters": "setting"}]),
        _moment("aaaaaaaa-0000-4000-8000-000000000005", 16.3, [[0, 4.5]],
                narrative=[{"start_time": 0, "end_time": 4.5, "role": "context", "confidence": 0.9,
                            "what_happens": "Backpacks and poles outside a church", "why_matters": "stage finish"}]),
    ]


def make_inputs(**kw) -> EditPlanInputs:
    moments = kw.pop("moments", None) or red_jacket_group()
    base = dict(
        story_id="11111111-1111-4111-8111-111111111111", creative_intent_id="22222222-2222-4222-8222-222222222222",
        creative_intent={"target_duration_seconds": 90, "tone": "adventurous", "raw_text": "8 days hiking"},
        story_guide={"framing_summary": "a hike"}, story_coverage={"pending_count": 0},
        moments=moments, music_plan={"character": "uplifting"},
        sound_preference="balanced",
        images=[ImageInput(b"\xff\xd8x") for _ in moments],
        image_moment_order=[m["id"] for m in moments],
        creative_brief=LEGACY_BRIEF,
    )
    base.update(kw)
    return EditPlanInputs(**base)


CASES = {
    "highlights_original": dict(editorial_type="highlights", editorial_mode="highlights"),
    "full_story_explore": dict(
        editorial_type="full_story", editorial_mode="full",
        revision_context={"mode": "explore", "base_version_id": "v1",
                          "prior_edit_summaries": [{"moment_sequence": ["aaaaaaaa-0000-4000-8000-000000000004"]}]}),
    "legacy_no_type_text_only": dict(editorial_mode="highlights", images=[], image_moment_order=[],
                                     creative_brief=None, sound_preference=None),
    "highlights_opening_directive": dict(
        editorial_type="highlights", editorial_mode="highlights",
        revision_context={"mode": "explore", "base_version_id": "v1",
                          "directives": {"opening": "aaaaaaaa-0000-4000-8000-000000000004"}}),
    "revise_with_base_plan": dict(
        editorial_type="highlights", editorial_mode="highlights",
        revision_context={"mode": "revise", "soft_direction": "make it warmer",
                          "base_plan": {"segments": [{"order": 0, "asset_id": "aaaaaaaa-0000-4000-8000-000000000004"}]}}),
}


def render_all() -> dict[str, str]:
    """Every prompt string the planner builds for the fixture cases, with the v5.3 gate forced on (v5.5 off)."""
    out: dict[str, str] = {}
    orig = edit_planner._v53_active
    orig_ver = edit_planner._EDIT_PLAN_VERSION
    edit_planner._v53_active = lambda: True
    edit_planner._EDIT_PLAN_VERSION = "5.3"   # the default is now 5.6; this golden pins the 5.3 rollback path
    try:
        for name, extra in CASES.items():
            inp = make_inputs(**extra)
            out[f"{name}::user"] = edit_planner._build_user(inp)
        inp = make_inputs(**CASES["highlights_original"])
        out["repair"] = edit_planner._build_repair(inp, {"segments": []}, ["seg0: example error"])
        out["critique"] = edit_planner._build_critique(inp, {"segments": []})
        out["revision"] = edit_planner._build_revision(inp, {"segments": []}, "critique text")
    finally:
        edit_planner._v53_active = orig
        edit_planner._EDIT_PLAN_VERSION = orig_ver
    return out


GOLDEN_55_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "edit_plan_v55_golden.json")


def render_all_55() -> dict[str, str]:
    """Every prompt string the planner builds for the fixture cases with the SELECTED version forced to 5.5. The
    golden file was generated from master (929a060, before any v5.6 code) and pins that 5.5 stays unchanged."""
    out: dict[str, str] = {}
    orig = edit_planner._EDIT_PLAN_VERSION
    edit_planner._EDIT_PLAN_VERSION = "5.5"
    try:
        for name, extra in CASES.items():
            out[f"{name}::user"] = edit_planner._build_user(make_inputs(**extra))
        inp = make_inputs(**CASES["highlights_original"])
        out["repair"] = edit_planner._build_repair(inp, {"segments": []}, ["seg0: example error"])
        out["critique"] = edit_planner._build_critique(inp, {"segments": []})
        out["revision"] = edit_planner._build_revision(inp, {"segments": []}, "critique text")
    finally:
        edit_planner._EDIT_PLAN_VERSION = orig
    return out


def regenerate_golden() -> None:
    os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
    with open(GOLDEN_PATH, "w") as f:
        json.dump(render_all(), f, indent=1, sort_keys=True, ensure_ascii=False)


def regenerate_golden_55() -> None:
    with open(GOLDEN_55_PATH, "w") as f:
        json.dump(render_all_55(), f, indent=1, sort_keys=True, ensure_ascii=False)


if __name__ == "__main__":
    regenerate_golden()
    print("wrote", GOLDEN_PATH)
