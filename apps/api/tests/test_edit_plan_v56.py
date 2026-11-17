"""EditPlan v5.6 (Editorial vNext "radical simplification") — offline tests. No model call, no AWS, no media.

Covers: v5.3 / v5.5 byte-identity, isolated version resolution, the short system prompt, one strategy per type
with no competing instruction, the type-specific input projections (what is dropped and what must survive),
the pacing hint, directive/Custom/operation semantics, one model call, the under-length disclosure (never a
rejection), the pacing diagnostics against an independent recomputation, and the token budget. Aesthetic
judgments are NEVER asserted as Moment-id outcomes."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

import edit_planner as ep                                            # noqa: E402
import _v55_fixtures as fx                                           # noqa: E402
from edit_planner import (EditPlanInputs, RealEditPlannerEngine, _build_repair, _build_user,   # noqa: E402
                          compute_budget_hint, selection_diagnostics, validate_plan)
from model_gateway import FakeModelGateway                           # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
H = fx.CASES["highlights_original"]
F = fx.CASES["full_story_explore"]


@pytest.fixture
def v56(monkeypatch):
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.6")


@pytest.fixture
def v55(monkeypatch):
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.5")


def _py(code: str, env: dict | None = None) -> str:
    e = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "packages")]))
    e.pop("STORY_EDIT_PLAN_VERSION", None)
    e.update(env or {})
    r = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip()


def _sys(ver: str) -> str:
    t = open(os.path.join(ROOT, "prompts", "edit_plan", ver, "system.md")).read()
    return t.split("-->", 1)[1].strip() if t.lstrip().startswith("<!--") else t.strip()


def _split(user: str) -> tuple[str, dict]:
    head, _, rest = user.partition("\nINPUT:\n")
    return head, json.loads(rest.rsplit("\n\nReturn ONLY", 1)[0])


def _rich_moments() -> list[dict]:
    """Moments shaped like the real iOS payload: summary + evidence + editorial + events + sampled_frame_ms."""
    def m(i, dur, useful, vcs, ncs, events, summary):
        return {"id": f"bbbbbbbb-0000-4000-8000-00000000000{i}", "duration_seconds": dur, "useful_segments": useful,
                "summary": summary + " · subjects: a, b · events: " + "; ".join(e["description"] for e in events),
                "evidence": {"summary": summary, "subjects": ["hiker", "waterfall", "trail", "sky", "rock", "extra"],
                             "events": [{"what": e["description"], "t": e["start_time"], "t_end": e["end_time"]} for e in events],
                             "temporal_order_note": "NOTE-TEMPORAL"},
                "editorial": {"analysis_version": "v2", "visual_candidates": vcs, "narrative_candidates": ncs},
                "events": events, "sampled_frame_ms": [0, 700, 1400, 2100]}
    vc = lambda s, e, role, conf, text, pk=None: {"start_time": s, "end_time": e, "role": role, "confidence": conf,
                                                  "visual_value": text, "peak_time": pk, "evidence": "FABRICATED"}
    nc = lambda s, e, w: {"start_time": s, "end_time": e, "role": "progression", "confidence": 0.9, "what_happens": w,
                          "why_matters": "WHYMATTERS", "spoken_meaning": "unknown"}
    ev = lambda s, e, d: {"start_time": s, "end_time": e, "description": d}
    return [
        m(1, 16.1, [[0, 9.5], [10.5, 16.07]], [vc(0, 8.5, "b_roll", 0.85, "stream crossing", 4.9),
                                               vc(11.9, 16.07, "payoff", 0.9, "walks to camera", 15.4)],
          [nc(0, 16.07, "Hiker crosses the stream then climbs")], [ev(0, 9.5, "crosses stream"), ev(9.5, 16.07, "walks up")],
          "Hiker crosses a stream"),
        m(2, 8.0, [[0, 8.0]], [vc(1, 4, "payoff", 0.95, "arms wide at the peaks", 2.5)],
          [nc(0, 8, "Hiker raises arms")], [ev(0, 3, "arms raised")], "Arms raised"),
        {"id": "bbbbbbbb-0000-4000-8000-000000000003", "duration_seconds": 6.0, "useful_segments": [[0, 6.0]],
         "summary": "A short plain clip with no analysis"},
    ]


def _inp(extra=None, **kw):
    ms = _rich_moments()
    base = dict(moments=ms, image_moment_order=[x["id"] for x in ms])
    base.update(kw)
    return fx.make_inputs(**dict(extra or H, **base))


# --------------------------------------------------------------------------------------------------------------
# 1. earlier versions stay byte-identical
# --------------------------------------------------------------------------------------------------------------
def test_v53_goldens_still_byte_identical():
    golden = json.load(open(fx.GOLDEN_PATH))
    now = fx.render_all()
    assert set(golden) == set(now) and all(now[k] == golden[k] for k in golden)


def test_v55_prompts_byte_identical_to_pre_v56_golden():
    """Every v5.5 prompt string (user x5 cases, repair, critique, revision) equals what master 929a060 produced."""
    golden = json.load(open(fx.GOLDEN_55_PATH))
    now = fx.render_all_55()
    assert set(golden) == set(now)
    for k in golden:
        assert now[k] == golden[k], f"v5.5 prompt drifted: {k}"


def test_v55_system_prompt_file_untouched():
    import hashlib
    sha = hashlib.sha256(open(os.path.join(ROOT, "prompts", "edit_plan", "5.5", "system.md"), "rb").read()).hexdigest()
    assert sha == "eb4c403d00097cfefb80742d61b86d3af35cc8707bedb4d19b50efc62eec8df9", "prompts/edit_plan/5.5/system.md must stay the accepted predecessor, unchanged"


# --------------------------------------------------------------------------------------------------------------
# 2. isolated candidate
# --------------------------------------------------------------------------------------------------------------
def test_default_is_still_53():
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v55_active(), e._v56_active())"
               ) == "edit_plan/5.3 False False"


def test_version_56_resolves_only_when_selected():
    out = _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v53_active(), e._v55_active(), e._v56_active())",
              {"STORY_EDIT_PLAN_VERSION": "5.6"})
    assert out == "edit_plan/5.6 True True True"


def test_55_does_not_enable_56_and_unknown_falls_back():
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v55_active(), e._v56_active())",
               {"STORY_EDIT_PLAN_VERSION": "5.5"}) == "edit_plan/5.5 True False"
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v56_active())",
               {"STORY_EDIT_PLAN_VERSION": "5.7"}) == "edit_plan/5.3 False"
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v56_active())",
               {"STORY_EDIT_PLAN_VERSION": "5.3-cand"}) == "edit_plan/5.3-cand False"


# --------------------------------------------------------------------------------------------------------------
# 3. the 5.6 system prompt
# --------------------------------------------------------------------------------------------------------------
def test_56_system_prompt_is_much_shorter_than_55():
    a, b = len(_sys("5.5").split()), len(_sys("5.6").split())
    assert b <= 700 and b < 0.45 * a, (a, b)


def test_56_system_prompt_has_no_type_or_breadth_bias():
    t = _sys("5.6").lower()
    for bad in ("highlights", "full story", "full_story", "breadth", "storyguide", "storycoverage", "story guide",
                "coverage", "narrative progression", "strongest achievable", "default to keep", "quiet->build",
                "significance-weighted", "editorial_mode", "editorial_type"):
        assert bad not in t, bad


def test_56_system_prompt_keeps_every_mechanical_rule():
    t = _sys("5.6")
    for needle in ("asset_id MUST be one of the given Moment ids",
                   "0 <= source_start_seconds < source_end_seconds <= the Moment's real duration",
                   "(source_end_seconds - source_start_seconds) / speed", "0.5x–2.0x",
                   "keep = full presence", "duck", "mute", "never set a music_alignment anchor",
                   "MusicAnalysis", "straight cuts", "narrative_role", "feasible=false", "Return ONLY the EditPlan via the tool",
                   "explicit directives", "trust the frames", "Never invent"):
        assert needle.lower() in t.lower(), needle
    assert "never rejected for its length" in t


def test_56_system_prompt_does_not_tell_the_model_to_declare_infeasible_for_a_short_cut():
    t = " ".join(_sys("5.6").split())
    assert "do not use it merely for ending somewhat short" in t
    assert "A shorter, stronger edit is better" in t


# --------------------------------------------------------------------------------------------------------------
# 4. strategies are exclusive and nothing competes
# --------------------------------------------------------------------------------------------------------------
def test_highlights_strategy_text_and_exclusivity(v56):
    u = _build_user(_inp())
    assert "MAKE THE MOST VISUALLY EXCITING SHORT VIDEO POSSIBLE." in u
    for needle in ("Compare the visual quality of ALL Moments", "Confidence is not appeal", "several distinct payoffs "
                   "within the first ~10 seconds", "1–2.5 s", "a preference, not a rule", "No routine establishing shots",
                   "Do not force chronology", "Do not include every Moment", "Never speed footage up"):
        assert needle in u, needle
    assert "FULL STORY (narrative-led)" not in u and "4–10 s" not in u


def test_full_story_strategy_text_and_exclusivity(v56):
    u = _build_user(_inp(F))
    assert "STRATEGY — FULL STORY (narrative-led)" in u and "4–10 s" in u and "import order, not chronology" in u
    assert "Preserve natural audio" in u
    assert "VISUALLY EXCITING" not in u and "1–2.5 s" not in u and "HIGHLIGHTS (image-led)" not in u


@pytest.mark.parametrize("extra", [H, F])
def test_no_competing_instruction_blocks(v56, extra):
    u = _build_user(_inp(extra))
    assert "CREATIVE DIRECTION" not in u                    # the strategy IS the brief
    assert fx.LEGACY_BRIEF[:40] not in u                    # a client's generic brief never reaches the model
    assert "EDITORIAL MODE" not in u and "EDITORIAL TYPE =" not in u and "TYPE STRATEGY" not in u
    head, payload = _split(u)
    assert "editorial_mode" not in payload and "editorial_type" not in payload
    assert u.count("STRATEGY —") == 1


def test_type_unknown_or_missing_uses_the_legacy_path(v56):
    for extra in (dict(editorial_type=None, editorial_mode="highlights"), dict(editorial_type="weird")):
        u = _build_user(_inp(extra))
        assert "STRATEGY —" not in u and "INPUT:" in u


def test_strategy_text_hardcodes_no_moment_ids():
    import re
    src = open(os.path.join(ROOT, "packages", "edit_planner", "__init__.py")).read()
    block = src[src.index("def _v56_strategy"):src.index("def _budget_block_v56")]
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", block)


# --------------------------------------------------------------------------------------------------------------
# 5. projections
# --------------------------------------------------------------------------------------------------------------
def test_highlights_projection_is_compact_and_image_led(v56):
    u = _build_user(_inp())
    head, p = _split(u)
    assert "story_guide" not in p and "story_coverage" not in p
    for m in p["moments"]:
        for dropped in ("evidence", "editorial", "narrative_candidates", "sampled_frame_ms", "analysis_version", "events"
                        ) if m.get("visual_candidates") else ("evidence", "editorial", "narrative_candidates", "sampled_frame_ms"):
            assert dropped not in m, dropped
    for s in ("NOTE-TEMPORAL", "WHYMATTERS", "FABRICATED", "confidence", "Hiker crosses the stream then climbs"):
        assert s not in u, s
    m1 = p["moments"][0]
    assert m1["id"].startswith("bbbbbbbb") and m1["duration_seconds"] == 16.1 and m1["useful_segments"] == [[0, 9.5], [10.5, 16.07]]
    assert [v["role"] for v in m1["visual_candidates"]] == ["b_roll", "payoff"]
    assert m1["visual_candidates"][1] == {"start": 11.9, "end": 16.07, "peak": 15.4, "role": "payoff", "value": "walks to camera"}
    assert len(m1["subjects"]) == 5


def test_highlights_moment_without_visual_candidates_gets_a_short_text_hint(v56):
    _, p = _split(_build_user(_inp()))
    m3 = p["moments"][2]
    assert m3["id"].endswith("3") and m3["useful_segments"] == [[0, 6.0]]
    assert m3["summary"] == "A short plain clip with no analysis"


def test_full_story_projection_keeps_narrative_and_compacts_guide_and_coverage(v56):
    long_guide = {"framing_summary": "G" * 400, "scenes": [
        {"id": "scene_01", "title": "T", "why_it_matters": "W", "what_to_capture": "WTC", "how_to_shoot": "HTS",
         "capture_possibilities": [{"label": "CP"}], "visual_reference_query": "VRQ"}]}
    long_cov = {"dimension_coverage": [{"story_guide_dimension_id": "scene_01", "state": "could_use_more", "note": "NOTE-X",
                                        "evidence_moment_ids": ["bbbbbbbb-0000-4000-8000-000000000001"]}],
                "strengths": ["s1"], "redundancies": ["r1"], "sufficiency": {"status": "sufficient", "reason": "enough"},
                "source_understanding_ids": ["bbbbbbbb-0000-4000-8000-000000000001"]}
    u = _build_user(_inp(F, story_guide=long_guide, story_coverage=long_cov))
    head, p = _split(u)
    m1 = p["moments"][0]
    assert m1["summary"] == "Hiker crosses a stream" and len(m1["events"]) == 2
    assert m1["narrative_candidates"][0]["what_happens"] == "Hiker crosses the stream then climbs"
    assert all(set(v) == {"start", "end", "role"} for v in m1["visual_candidates"])
    for s in ("sampled_frame_ms", "WHYMATTERS", "NOTE-TEMPORAL", "FABRICATED"):
        assert s not in u
    g, c = p["story_guide"], p["story_coverage"]
    assert len(g["framing_summary"]) <= 200 and g["scenes"] == [{"id": "scene_01", "title": "T", "why_it_matters": "W"}]
    for s in ("WTC", "HTS", "CP", "VRQ", "NOTE-X", "source_understanding_ids"):
        assert s not in u
    assert c["dimensions"] == [{"id": "scene_01", "state": "could_use_more"}]
    assert c["strengths"] == ["s1"] and c["redundancies"] == ["r1"] and c["sufficiency"]["status"] == "sufficient"


def test_projection_never_mutates_inputs_or_validation_data(v56):
    inp = _inp()
    before = json.dumps(inp.moments, sort_keys=True)
    _build_user(inp)
    _build_user(_inp(F))
    assert json.dumps(inp.moments, sort_keys=True) == before
    assert "sampled_frame_ms" in inp.moments[0] and "evidence" in inp.moments[0]       # validation sees the full Moment


def test_ids_and_identity_survive_in_both_projections(v56):
    for extra in (H, F):
        inp = _inp(extra)
        u = _build_user(inp)
        _, p = _split(u)
        assert [m["id"] for m in p["moments"]] == [m["id"] for m in inp.moments]
        for mid in inp.image_moment_order:
            assert mid in u.split("\nINPUT:")[0]                          # image order list kept for sheet identity


def test_music_plan_compact_and_music_analysis_unchanged(v56):
    ma = {"bpm": 120, "beats": [0.5, 1.0], "downbeats": [0.5], "highlight": {"start": 3, "end": 9}}
    mp = {"audio_strategy": {"soundtrack_role": "supportive"}, "character": {"energy": "dynamic", "mood_tags": ["x"]},
          "energy_arc": [{"start_fraction": 0, "end_fraction": 1, "intensity": "rising", "label": "L", "note": "NOTE-ARC"}],
          "provenance": {"model_id": "PROV"}}
    u = _build_user(_inp(music_plan=mp, music_analysis=ma))
    _, p = _split(u)
    assert p["music_analysis"] == ma and "NOTE-ARC" not in u and "PROV" not in u
    assert p["music_plan"]["energy_arc"][0]["intensity"] == "rising" and p["music_plan"]["audio_strategy"]
    assert "Pace the cuts to the real beats" in u
    assert "Pace the cuts to the music plan" in _build_user(_inp(music_plan=mp))


def test_user_sound_preference_is_authoritative_and_defaults_live_in_strategy(v56):
    u = _build_user(_inp(sound_preference="immersive"))
    assert "SOUND PREFERENCE = immersive" in u
    assert "Sound default: music-forward" in _build_user(_inp(sound_preference=None))
    assert "Sound default: keep" in _build_user(_inp(F, sound_preference=None))


# --------------------------------------------------------------------------------------------------------------
# 6. pacing hint (advisory) and versioning
# --------------------------------------------------------------------------------------------------------------
def test_pacing_hint_numbers_per_type_and_version(v56, monkeypatch):
    big = [dict(_rich_moments()[0], id=f"cccccccc-0000-4000-8000-{i:012d}") for i in range(38)]
    inp = _inp(H, moments=big, image_moment_order=[m["id"] for m in big], creative_intent={"target_duration_seconds": 90})
    h = compute_budget_hint(inp)
    assert h["typical_shot_s"] == [1.0, 2.5] and h["suggested_shots"] == [36, 76]        # capped at 2 x Moments
    f = compute_budget_hint(_inp(F, creative_intent={"target_duration_seconds": 90}))
    assert f["typical_shot_s"] == [4.0, 10.0] and f["suggested_shots"] == [6, 6]         # 9..22 both capped at 6 (3 Moments x 2)
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.5")
    assert compute_budget_hint(inp)["typical_shot_s"] == [3.0, 5.0]
    assert compute_budget_hint(_inp(F))["typical_shot_s"] == [5.0, 9.0]


def test_pacing_hint_text_is_advisory(v56):
    u = _build_user(_inp(creative_intent={"target_duration_seconds": 30}))
    b = u[u.index("BUDGET"):u.index("INPUT:")]
    assert "advisory" in b and "not a quota or a limit on shot length" in b and "end somewhat short" in b
    assert "±10%" not in b                                              # the system prompt owns the duration rule


def test_validator_and_fitter_do_not_read_the_pacing_hint():
    src = open(os.path.join(ROOT, "packages", "edit_planner", "__init__.py")).read()
    fit = open(os.path.join(ROOT, "packages", "edit_planner", "duration_fit.py")).read()
    assert "_V56_TYPICAL_SHOT_S" not in fit and "compute_budget_hint" not in fit and "typical_shot" not in fit
    val = src[src.index("def validate_plan"):src.index("def _validate_directives_split")]
    assert "typical_shot" not in val and "_V56" not in val


# --------------------------------------------------------------------------------------------------------------
# 7. directives, Custom target, operations
# --------------------------------------------------------------------------------------------------------------
def test_explicit_opening_directive_is_rendered(v56):
    u = _build_user(_inp(fx.CASES["highlights_opening_directive"]))
    assert "aaaaaaaa-0000-4000-8000-000000000004" in u.split("\nINPUT:")[0]
    assert "Explicit user directives always win" in u or "Explicit user directives always win." in u


def test_custom_target_is_carried_verbatim_and_independent_of_type(v56):
    for extra in (H, F):
        u = _build_user(_inp(extra, creative_intent={"target_duration_seconds": 90, "raw_text": "x"}))
        _, p = _split(u)
        assert p["target_duration_seconds"] == 90 and p["creative_intent"]["target_duration_seconds"] == 90


def test_operation_semantics_preserved(v56):
    assert "REVISE" in _build_user(_inp(fx.CASES["revise_with_base_plan"])) or "revise" in _build_user(_inp(fx.CASES["revise_with_base_plan"])).lower()
    assert compute_budget_hint(_inp(fx.CASES["revise_with_base_plan"])) is None
    u = _build_user(_inp(F))
    assert "explore" in u.lower() or "VERSION CONTEXT" in u


def test_repair_prompt_is_the_55_one(v56):
    r = _build_repair(_inp(), {"segments": []}, ["seg0: e"])
    assert "Do NOT lengthen the plan to keep more footage" in r


# --------------------------------------------------------------------------------------------------------------
# 8. engine: one call, no new rejection, under-length disclosure, pacing diagnostics
# --------------------------------------------------------------------------------------------------------------
def _plan(inp, picks):
    segs = [{"order": i, "asset_id": inp.moments[idx]["id"], "source_start_seconds": a, "source_end_seconds": b,
             "output_duration_seconds": round(b - a, 3), "speed": 1.0, "native_audio": "keep", "narrative_role": "r"}
            for i, (idx, a, b) in enumerate(picks)]
    return {"target_duration_seconds": round(sum(s["output_duration_seconds"] for s in segs), 3), "feasible": True, "segments": segs}


@pytest.mark.parametrize("extra", [H, F])
def test_engine_one_call_and_unchanged_contract(v56, extra):
    inp = _inp(extra, creative_intent={"target_duration_seconds": 9.0})
    plan = _plan(inp, [(1, 1.0, 3.0), (0, 11.9, 14.0), (1, 4.0, 6.0), (2, 0, 3.0)])
    eng = RealEditPlannerEngine(FakeModelGateway(response=plan))
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert d["model_calls"] == 1 and d.get("critique_attempted") is None and out.segments
    assert d["first_pass_executable"] is True and d["selection"]["prompt_version"].startswith("edit_plan/")
    assert not validate_plan(plan, inp)                                  # the unchanged validator accepts it


def test_short_cut_ships_and_is_disclosed_never_rejected(v56):
    inp = _inp(H, creative_intent={"target_duration_seconds": 90})
    plan = _plan(inp, [(1, 1.0, 3.0), (0, 11.9, 14.0), (2, 0, 2.0)])           # 6 s vs a 90 s ask
    eng = RealEditPlannerEngine(FakeModelGateway(response=plan))
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert out.segments and d["final"] == "executable" and d["completion"] == "partial" and d["model_calls"] == 1
    assert any(m["code"] == "approx_duration" for m in d["material_unmet"])
    assert "instead of the requested 90s" in d["partial_disclosure"] and "ran out" in d["partial_disclosure"]


def test_near_target_cut_is_complete_and_55_never_adds_the_disclosure(monkeypatch):
    inp = _inp(H, creative_intent={"target_duration_seconds": 6})
    plan = _plan(inp, [(1, 1.0, 3.0), (0, 11.9, 14.0), (2, 0, 2.0)])
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.6")
    e1 = RealEditPlannerEngine(FakeModelGateway(response=plan)); e1.generate(inp)
    assert e1.last_diagnostics["completion"] == "complete"
    inp2 = _inp(H, creative_intent={"target_duration_seconds": 90})
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.5")
    e2 = RealEditPlannerEngine(FakeModelGateway(response=plan)); e2.generate(inp2)
    assert e2.last_diagnostics["completion"] == "complete" and "partial_disclosure" not in e2.last_diagnostics


def test_pacing_diagnostics_match_an_independent_recomputation(v56):
    inp = _inp(H, creative_intent={"target_duration_seconds": 12})
    picks = [(1, 1.0, 3.0), (0, 11.9, 14.4), (1, 4.0, 5.0), (0, 0, 6.0), (2, 0, 2.0)]
    plan = _plan(inp, picks)
    d = selection_diagnostics(plan, inp, {}, plan)
    p = d["pacing"]
    outs = [b - a for _, a, b in picks]
    assert p["cuts"] == 4
    assert p["share_le_2_5"] == round(sum(1 for o in outs if o <= 2.5) / len(outs), 3)
    assert p["buckets"] == {"le1": 1, "1_2.5": 3, "2.5_4": 0, "4_10": 1, "gt10": 0}
    # opening window = shots starting before 10 s of output time: starts at 0, 2, 4.5, 5.5, 11.5 -> first four
    assert p["opening"]["shots"] == 4
    # payoff shots in the opening: picks 0 (Moment 2 payoff 1-4 overlaps 1-3) and 1 (Moment 1 payoff 11.9-16.07)
    assert p["opening"]["payoff_shots"] == 2 and p["opening"]["distinct_payoffs"] == 2


def test_pacing_block_absent_before_56(v55):
    inp = _inp(H)
    plan = _plan(inp, [(1, 1.0, 3.0)])
    assert selection_diagnostics(plan, inp, {}, plan)["pacing"] is None


def test_pacing_diagnostics_serialise_as_json(v56):
    inp = _inp(H)
    plan = _plan(inp, [(1, 1.0, 3.0), (0, 11.9, 14.4)])
    json.dumps(selection_diagnostics(plan, inp, {}, plan))


# --------------------------------------------------------------------------------------------------------------
# 9. token budget (skipped when tiktoken is not installed)
# --------------------------------------------------------------------------------------------------------------
def test_56_text_is_far_smaller_than_55_on_a_realistic_payload(monkeypatch):
    base = _rich_moments()
    moments = []
    for i in range(38):
        for b in base[:2]:
            moments.append(dict(b, id=f"dddddddd-0000-4000-8000-{len(moments):012d}"))
        if len(moments) >= 38:
            break
    moments = moments[:38]
    sizes = {}
    for ver in ("5.5", "5.6"):
        monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", ver)
        inp = fx.make_inputs(**dict(H, moments=moments, image_moment_order=[m["id"] for m in moments],
                                    creative_intent={"target_duration_seconds": 90}))
        sizes[ver] = len(_sys(ver)) + len(_build_user(inp))
    assert sizes["5.6"] < 0.5 * sizes["5.5"], sizes
