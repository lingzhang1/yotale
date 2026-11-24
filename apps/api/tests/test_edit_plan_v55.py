"""EditPlan v5.5 (Editorial vNext M1) — offline tests. No model call, no AWS, no media.

Covers: v5.3 byte-identity (golden), isolated version resolution, one-authority editorial policy per type, the
type-aware brief, legacy-instruction reconciliation, the deterministic budget hint, sound defaults, repair/critique
consistency, deterministic selection diagnostics, and engine integration with a fake gateway (no extra model call).
Aesthetic judgments are NEVER asserted as Moment-id outcomes."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

import edit_planner as ep                                            # noqa: E402
import _v55_fixtures as fx                                           # noqa: E402
from edit_planner import (EditPlanInputs, RealEditPlannerEngine, _build_critique, _build_repair, _build_revision,  # noqa: E402
                          _build_user, compute_budget_hint, selection_diagnostics, validate_plan)
from model_gateway import FakeModelGateway                           # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
H = fx.CASES["highlights_original"]
F = fx.CASES["full_story_explore"]


@pytest.fixture
def v55(monkeypatch):
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", "5.5")
    monkeypatch.setattr(ep, "_v53_active", lambda: True)
    monkeypatch.setattr(ep, "_v55_active", lambda: True)


@pytest.fixture
def v53(monkeypatch):
    monkeypatch.setattr(ep, "_v53_active", lambda: True)
    monkeypatch.setattr(ep, "_v55_active", lambda: False)


def _py(code: str, env: dict | None = None) -> str:
    e = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "packages")]))
    e.pop("STORY_EDIT_PLAN_VERSION", None)
    e.update(env or {})
    r = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip()


# --------------------------------------------------------------------------------------------------------------
# 1. v5.3 stays byte-identical
# --------------------------------------------------------------------------------------------------------------
def test_v53_prompts_byte_identical_to_golden():
    golden = json.load(open(fx.GOLDEN_PATH))
    now = fx.render_all()
    assert set(golden) == set(now)
    for k in golden:
        assert now[k] == golden[k], f"v5.3 prompt drifted: {k}"


def test_v53_system_prompt_file_untouched():
    import hashlib
    sha = hashlib.sha256(open(os.path.join(ROOT, "prompts", "edit_plan", "5.3", "system.md"), "rb").read()).hexdigest()
    assert sha == "6ec7e05020b6773defbf8f8f8787cd04cec5f3331b0217d32b3ecd636af02373", "prompts/edit_plan/5.3/system.md must stay the frozen accepted baseline"


# --------------------------------------------------------------------------------------------------------------
# 2. isolated candidate: resolution, never default
# --------------------------------------------------------------------------------------------------------------
def test_default_is_53_and_55_is_never_default():
    assert _py("import edit_planner as e;print(e._EDIT_PLAN_DEFAULT, e.PROMPT_VERSION, e._v53_active(), e._v55_active())"
               ) == "5.3 edit_plan/5.3 True False"


def test_version_55_resolves_only_when_selected():
    out = _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v53_active(), e._v55_active(), "
              "'TYPE STRATEGY' in e._load_system())", {"STORY_EDIT_PLAN_VERSION": "5.5"})
    assert out == "edit_plan/5.5 True True True"


def test_unknown_version_falls_back_to_default():
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v55_active())",
               {"STORY_EDIT_PLAN_VERSION": "5.7"}) == "edit_plan/5.3 False"


def test_existing_53_cand_dir_does_not_parse_as_55():
    assert _py("import edit_planner as e;print(e.PROMPT_VERSION, e._v55_active())",
               {"STORY_EDIT_PLAN_VERSION": "5.3-cand"}) == "edit_plan/5.3-cand False"


# --------------------------------------------------------------------------------------------------------------
# 3. the 5.5 system prompt: invariants verbatim, breadth bias gone
# --------------------------------------------------------------------------------------------------------------
def _sys(ver: str) -> str:
    t = open(os.path.join(ROOT, "prompts", "edit_plan", ver, "system.md")).read()
    return t.split("-->", 1)[1].strip() if t.lstrip().startswith("<!--") else t.strip()


def _section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_55_keeps_executability_native_audio_and_hard_rules_verbatim():
    a, b = _sys("5.3"), _sys("5.5")
    for start, end in [("- NATIVE AUDIO (first-class", "- MUSIC ALIGNMENT"),
                       ("- MUSIC ALIGNMENT", "HARD RULES:"),
                       ("HARD RULES:", "EXECUTABILITY INVARIANTS"),
                       ("- VALID SOURCE RANGE:", "- TOTAL "),
                       ("- TRANSITIONS ACCOUNTED FOR:", "- STORY TARGET BEATS TRACK LENGTH")]:
        assert _section(a, start, end) == _section(b, start, end), start


def test_55_removes_breadth_bias_and_stale_duration_language():
    b = _sys("5.5")
    assert "favor BREADTH" not in b and "even when its" not in b and "CREATIVE FREEDOM OVER PACING" not in b
    assert "±20%" not in b and "hard feasibility TOLERANCE" not in b
    assert "TYPE STRATEGY" in b and "single authority" in b
    # a type-specific strategy lives in the user message only, never in the system prompt
    assert "HOOK" not in b and "COMPARE" not in b


# --------------------------------------------------------------------------------------------------------------
# 4. one coherent policy per type; type-aware brief; legacy reconciliation
# --------------------------------------------------------------------------------------------------------------
def test_highlights_policy_active_and_distinct(v55):
    u = _build_user(fx.make_inputs(**H))
    assert "TYPE STRATEGY — HIGHLIGHTS" in u
    for must in ("COMPARE similar footage", "HOOK:", "Keep the strongest", "peak_time and confidence", "trust the frames",
                 "SELECT, do not cover", "start at the action"):
        assert must in u, must
    assert "TYPE STRATEGY — FULL STORY" not in u


def test_full_story_policy_active_and_distinct(v55):
    u = _build_user(fx.make_inputs(**F))
    assert "TYPE STRATEGY — FULL STORY" in u
    for must in ("NOT a longer Highlights montage", "never invent dialogue", "Do not invent a departure",
                 "import order, NOT chronology", "complete meaningful actions"):
        assert must in u, must
    assert "HOOK:" not in u and "COMPARE similar footage" not in u


def test_full_story_never_receives_the_highlights_brief(v55):
    u = _build_user(fx.make_inputs(**F))                       # client (older iOS) still sends the Highlights brief
    assert fx.LEGACY_BRIEF not in u
    assert "compelling opening" not in u and "does not require chronology" not in u
    assert ep._V55_BRIEFS["full_story"] in u                   # but it is NOT left without an editorial objective
    uh = _build_user(fx.make_inputs(**H))
    assert ep._V55_BRIEFS["highlights"] in uh and fx.LEGACY_BRIEF not in uh


def test_type_aware_brief_only_when_client_sent_a_brief(v55):
    u = _build_user(fx.make_inputs(creative_brief=None, **H))
    assert "=== CREATIVE DIRECTION ===" not in u and "TYPE STRATEGY — HIGHLIGHTS" in u


def test_legacy_instructions_reconciled(v55):
    for extra in (H, F):
        u = _build_user(fx.make_inputs(**extra))
        assert "EDITORIAL MODE =" not in u and "EDITORIAL TYPE =" not in u        # no legacy line, no 5.3 directive
        payload = json.loads(u.split("\nINPUT:\n", 1)[1].rsplit("\n\nReturn ONLY", 1)[0])
        assert "editorial_mode" not in payload and payload["editorial_type"] == extra["editorial_type"]


def test_legacy_path_kept_when_type_absent_or_unrecognized(v55):
    for kw in (dict(editorial_mode="highlights", editorial_type=None), dict(editorial_mode="full", editorial_type="bogus")):
        u = _build_user(fx.make_inputs(**kw))
        assert "TYPE STRATEGY" not in u and "BUDGET (advisory" not in u
        assert "EDITORIAL MODE = " in u and fx.LEGACY_BRIEF in u                  # unchanged legacy behavior


def test_strategy_text_hardcodes_no_moment_ids():
    for t in ("highlights", "full_story"):
        s = ep._v55_strategy(t) + ep._V55_BRIEFS[t]
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", s)


def test_explicit_opening_directive_is_rendered_and_wins(v55):
    u = _build_user(fx.make_inputs(**fx.CASES["highlights_opening_directive"]))
    assert "=== VERSION CONTEXT ===" in u and "aaaaaaaa-0000-4000-8000-000000000004" in u
    assert "explicit user directives (opening, ending, must-include, ordering) always win" in u
    assert "HOOK:" in u                                                          # hook is a preference, not a rule


def test_operation_semantics_preserved(v55):
    ex = _build_user(fx.make_inputs(**F))                                         # Explore keeps its objective
    assert "MEANINGFULLY DIFFERENT" in ex and "BUDGET (advisory" in ex
    rv = _build_user(fx.make_inputs(**fx.CASES["revise_with_base_plan"]))         # Revise stays a diff of its base
    assert "REVISE of the user's EXISTING edit" in rv and "BASE PLAN" in rv
    assert "BUDGET (advisory" not in rv and "When a VERSION CONTEXT above says REVISE" in rv
    orig = _build_user(fx.make_inputs(**H))
    assert "=== VERSION CONTEXT ===" not in orig


# --------------------------------------------------------------------------------------------------------------
# 5. deterministic budget hint
# --------------------------------------------------------------------------------------------------------------
def _hi(target, n_moments, etype="highlights", **kw):
    ms = [{"id": f"m{i}", "duration_seconds": 10.0, "useful_segments": [[0, 10]]} for i in range(n_moments)]
    inp = fx.make_inputs(moments=ms, images=[], image_moment_order=[], editorial_type=etype,
                         creative_intent={"target_duration_seconds": target}, **kw)
    return compute_budget_hint(inp, etype)


def test_budget_hint_numbers(v55):
    h = _hi(90, 35)
    assert h["suggested_shots"] == [18, 30] and h["typical_shot_s"] == [3.0, 5.0] and h["target_s"] == 90.0
    f = _hi(155, 35, "full_story")
    assert f["suggested_shots"] == [17, 31] and f["typical_shot_s"] == [5.0, 9.0]
    assert _hi(16, 25)["suggested_shots"] == [3, 5]
    assert _hi(90, 5)["suggested_shots"] == [10, 10]         # never suggests more than 2 shots per Moment
    assert _hi(2, 3)["suggested_shots"][0] >= 1


def test_budget_hint_is_deterministic_and_type_specific(v55):
    assert _hi(90, 35) == _hi(90, 35)
    assert _hi(90, 35)["suggested_shots"] != _hi(90, 35, "full_story")["suggested_shots"]


def test_budget_hint_skipped_for_revise_no_type_no_target(v55):
    assert _hi(90, 5, revision_context={"mode": "revise"}) is None
    assert _hi(90, 5, "bogus") is None
    inp = fx.make_inputs(creative_intent={}, **H)
    assert compute_budget_hint(inp, "highlights") is None


def test_custom_duration_and_independence_from_type(v55):
    ms = fx.red_jacket_group()
    a = fx.make_inputs(moments=ms, creative_intent={"target_duration_seconds": 47}, **H)
    b = fx.make_inputs(moments=ms, creative_intent={"target_duration_seconds": 47}, **F)
    assert compute_budget_hint(a)["target_s"] == 47.0 == compute_budget_hint(b)["target_s"]   # type never changes the target
    assert "the target is 47s" in _build_user(a)


def test_budget_text_is_advisory_not_a_quota(v55):
    u = _build_user(fx.make_inputs(**H))
    assert "advisory, not a quota" in u and "lands within about ±10%" in u and "may run longer than typical" in u
    assert not re.search(r"\b(must|exactly)\b[^.\n]*shots", u.split("BUDGET", 1)[1].split("INPUT:", 1)[0])


# --------------------------------------------------------------------------------------------------------------
# 6. sound
# --------------------------------------------------------------------------------------------------------------
def test_user_sound_preference_is_authoritative(v55):
    for pref in ("immersive", "music_led", "balanced"):
        u = _build_user(fx.make_inputs(sound_preference=pref, **H))
        assert "SOUND PREFERENCE = " + pref in u and "SOUND DEFAULT" not in u


def test_type_sound_defaults_only_when_no_preference(v55):
    uh = _build_user(fx.make_inputs(sound_preference=None, **H))
    uf = _build_user(fx.make_inputs(sound_preference=None, **F))
    assert "SOUND DEFAULT = music-forward" in uh and "SOUND DEFAULT = keep" in uf
    assert "audio-safe" not in uh                                                # we never claim AU edges are audio-safe cuts
    assert "not where sound can be cut cleanly" in uh


# --------------------------------------------------------------------------------------------------------------
# 7. repair / critique consistency
# --------------------------------------------------------------------------------------------------------------
def test_repair_prompt_never_invites_long_plans_in_55(v55):
    r = _build_repair(fx.make_inputs(**H), {"segments": []}, ["e"])
    assert "±10%" in r and "up to +50%" not in r and "Running somewhat LONG" not in r
    assert "output_duration_seconds MUST equal" in r                              # executability rules intact


def test_repair_prompt_unchanged_in_53(v53):
    r = _build_repair(fx.make_inputs(**H), {"segments": []}, ["e"])
    assert "up to +50%" in r


def test_critique_uses_type_brief_and_full_story_questions(v55):
    c = _build_critique(fx.make_inputs(**F), {"segments": []})
    assert "FULL STORY video" in c and ep._V55_BRIEFS["full_story"] in c and fx.LEGACY_BRIEF not in c
    ch = _build_critique(fx.make_inputs(**H), {"segments": []})
    assert "SHORT-FORM SOCIAL" in ch and ep._V55_BRIEFS["highlights"] in ch
    assert ep._V55_BRIEFS["full_story"] in _build_revision(fx.make_inputs(**F), {"segments": []}, "x")


# --------------------------------------------------------------------------------------------------------------
# 8. selection diagnostics: deterministic, privacy-safe, no model
# --------------------------------------------------------------------------------------------------------------
def _plan_for(inp, picks):
    segs = []
    for i, (idx, a, b) in enumerate(picks):
        segs.append({"order": i, "asset_id": inp.moments[idx]["id"], "source_start_seconds": a,
                     "source_end_seconds": b, "output_duration_seconds": round(b - a, 2), "native_audio": "keep",
                     "speed": 1.0})
    return {"target_duration_seconds": 90, "segments": segs}


def _distinct_prefix_moments():
    ms = fx.red_jacket_group()
    for i, m in enumerate(ms):
        m["id"] = f"{0xa0 + i:02x}{i:06x}-0000-4000-8000-00000000000{i}"
    return ms


def test_selection_diagnostics_shape_and_privacy(v55):
    ms = _distinct_prefix_moments()
    inp = fx.make_inputs(moments=ms, image_moment_order=[m["id"] for m in ms], **H)
    plan = _plan_for(inp, [(3, 0, 8), (1, 0, 5.2), (2, 1.58, 4.5)])
    pre = _plan_for(inp, [(3, 0, 10), (1, 0, 5.2), (2, 1.58, 6.1), (4, 0, 4.5)])
    d = selection_diagnostics(plan, inp, {"duration_fit": {"applied": True, "adopted": True, "before_s": 25.8,
                                                           "after_s": 16.6, "changes": [1], "dropped": [1]}}, pre)
    assert d["editorial_type"] == "highlights" and d["brief"] == "type_aware" and d["prompt_version"] == ep.PROMPT_VERSION
    assert d["shots"]["n"] == 3 and d["shots"]["distinct"] == 3 and d["pre_fit"]["n"] == 4
    assert d["budget"]["pre_fit_total_s"] > d["budget"]["delivered_s"] and d["budget"]["hint"]["suggested_shots"] == [10, 10]   # 5 Moments => at most 2 shots each
    assert d["opening"]["m"] == ms[3]["id"][:8] and d["opening"]["p"] is False         # opening is an establishing shot here
    assert d["used"][1]["p"] is True and d["used"][1]["role"] == "payoff"
    assert {u["m"] for u in d["unused_payoff"]} == {ms[0]["id"][:8]} and len(d["unused_payoff"]) == 1
    assert d["sheets"] == {"count": 5, "bytes": 5 * 3}
    assert d["fit"]["dropped"] == 1 and d["fit"]["adopted"] is True
    s = json.dumps(d)
    assert "FABRICATED" not in s and "Close red jacket" not in s                  # no AU prose, no evidence strings
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", s)                          # no full Moment ids
    assert json.loads(s) == d


def test_selection_diagnostics_lists_are_bounded(v55):
    ms = [{"id": f"{i:08x}-0000-4000-8000-000000000000", "duration_seconds": 5.0, "useful_segments": [[0, 5]],
           "editorial": {"visual_candidates": [{"start_time": 0, "end_time": 2, "role": "payoff", "confidence": 0.9}]}}
          for i in range(200)]
    inp = fx.make_inputs(moments=ms, images=[], image_moment_order=[], **H)
    plan = {"segments": [{"order": i, "asset_id": ms[i]["id"], "source_start_seconds": 0, "source_end_seconds": 1,
                          "output_duration_seconds": 1, "native_audio": "keep"} for i in range(100)]}
    d = selection_diagnostics(plan, inp, {}, None)
    assert len(d["used"]) == ep._SEL_MAX_USED and len(d["unused_payoff"]) == ep._SEL_MAX_UNUSED


def test_selection_diagnostics_emitted_for_every_version_without_failing(v53):
    inp = fx.make_inputs(**H)
    d = selection_diagnostics(_plan_for(inp, [(0, 0, 3)]), inp, {}, None)
    assert d["budget"]["hint"] is None and d["brief"] == "client"                  # v5.3: no hint, client brief


# --------------------------------------------------------------------------------------------------------------
# 9. engine integration with a fake gateway: no extra model call, valid plan, diagnostics recorded
# --------------------------------------------------------------------------------------------------------------
def _valid_plan(inp):
    ms = inp.moments
    picks = [(2, 1.58, 4.5), (0, 0, 3.0), (1, 0, 5.2), (3, 0, 4.0)]
    segs = []
    for i, (idx, a, b) in enumerate(picks):
        segs.append({"order": i, "asset_id": ms[idx]["id"], "source_start_seconds": a, "source_end_seconds": b,
                     "output_duration_seconds": round(b - a, 3), "speed": 1.0, "native_audio": "keep",
                     "narrative_role": "r"})
    total = sum(s["output_duration_seconds"] for s in segs)
    return {"target_duration_seconds": total, "feasible": True, "segments": segs}


@pytest.mark.parametrize("extra", [H, F])
def test_engine_one_call_valid_plan_and_diagnostics(v55, extra):
    inp = fx.make_inputs(**dict(extra, creative_intent={"target_duration_seconds": 15.0}))
    eng = RealEditPlannerEngine(FakeModelGateway(response=_valid_plan(inp)))
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert d["model_calls"] == 1                                                   # no mandatory extra call
    assert d.get("critique_attempted") is None and d["completion"] in ("complete", "partial")
    assert d["first_pass_executable"] is True and out.segments            # valid, executable, unchanged contract
    sel = d["selection"]
    assert sel["editorial_type"] == extra["editorial_type"] and sel["brief"] == "type_aware"
    assert sel["shots"]["n"] >= 1 and sel["budget"]["target_s"] == 15.0
    assert sel["opening"]["m"]


def test_engine_system_prompt_is_the_55_prompt_when_selected(monkeypatch):
    monkeypatch.setattr(ep, "_PROMPT_PATH", __import__("pathlib").Path(ROOT) / "prompts" / "edit_plan" / "5.5" / "system.md")
    eng = RealEditPlannerEngine(FakeModelGateway(response={}))
    assert "TYPE STRATEGY" in eng._system and "favor BREADTH" not in eng._system


def test_worker_whitelists_selection_diagnostics():
    src = open(os.path.join(ROOT, "apps", "api", "app", "worker.py")).read()
    assert '"selection")}' in src


# --------------------------------------------------------------------------------------------------------------
# 10. M1 review: critique coupling, hint safety, diagnostics correctness
# --------------------------------------------------------------------------------------------------------------
def _fake_critique_gateway(inp):
    """Gateway that answers the plan call with a valid plan and the critique/revision calls with text/plan."""
    class GW(FakeModelGateway):
        pass
    return GW(response=_valid_plan(inp))


@pytest.mark.parametrize("etype", ["highlights", "full_story"])
def test_v55_alone_never_enables_critique(v55, etype):
    """The critique pass needs an explicit client opt-in (critique_revision) AND a brief. Selecting 5.5, sending a brief and
    a type must stay at ONE planner call."""
    inp = fx.make_inputs(**dict(fx.CASES["highlights_original"], editorial_type=etype,
                                creative_intent={"target_duration_seconds": 15.0}))
    assert inp.critique_revision is False and inp.creative_brief
    eng = RealEditPlannerEngine(FakeModelGateway(response=_valid_plan(inp)))
    eng.generate(inp)
    assert eng.last_diagnostics["model_calls"] == 1 and "critique_attempted" not in eng.last_diagnostics


def test_critique_is_opt_in_only_and_needs_a_brief(v55):
    src = open(os.path.join(ROOT, "packages", "edit_planner", "__init__.py")).read()
    assert "if inputs.critique_revision and inputs.creative_brief:" in src          # the ONLY trigger
    api = open(os.path.join(ROOT, "apps", "api", "app", "main.py")).read()
    assert api.count("critique_revision: bool = Form(default=False") == 2             # sync + job endpoints default OFF
    assert "bool(env.get(\"critique_revision\"))" in open(os.path.join(ROOT, "apps", "api", "app", "worker.py")).read()


def test_critique_runs_only_when_the_client_opts_in(v55):
    inp = fx.make_inputs(**dict(fx.CASES["highlights_original"], critique_revision=True,
                                creative_intent={"target_duration_seconds": 15.0}))
    gw = FakeModelGateway(response=_valid_plan(inp))
    eng = RealEditPlannerEngine(gw)
    eng.generate(inp)
    assert eng.last_diagnostics.get("critique_attempted") is True                    # explicit opt-in is honored, not hidden


# ---- budget hint cannot contradict comparative selection --------------------------------------------------------
def test_hint_states_it_is_not_a_quota_or_limit_and_allows_fewer_stronger_shots(v55):
    u = _build_user(fx.make_inputs(**H))
    b = u.split("BUDGET", 1)[1].split("\nINPUT:", 1)[0]
    for must in ("NOT a minimum or maximum shot length", "NOT a shot count", "never overrides the user's instructions",
                 "Fewer, stronger shots are fine", "rather than adding weak or repetitive footage",
                 "complete actions, meaningful sound and striking continuous shots intact"):
        assert must in b, must
    assert "SELECT, do not cover" in u and "using fewer Moments is correct" in u        # selection objective is present too
    assert not re.search(r"\b(at least|at most|exactly|required|must use)\b", b, re.I)


def test_plan_below_the_suggested_shot_count_is_accepted_untouched(v55):
    """The hint never becomes a validator/fitter rule: a plan with FEWER shots than suggested ships as the model wrote it."""
    inp = fx.make_inputs(**dict(H, creative_intent={"target_duration_seconds": 90.0}))
    assert compute_budget_hint(inp)["suggested_shots"][0] > 3
    plan = _valid_plan(inp)                                                           # 4 shots, far below the suggestion
    assert validate_plan(plan, inp) == []
    eng = RealEditPlannerEngine(FakeModelGateway(response=plan))
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert d["model_calls"] == 1 and len(out.segments) == 4 and d["first_pass_executable"] is True
    assert d["selection"]["shots"]["n"] == 4 and d["selection"]["budget"]["hint"]["suggested_shots"][0] > 4


def test_validator_and_fitter_do_not_read_the_hint():
    import inspect
    from edit_planner import duration_fit
    for fn in (ep.validate_plan, ep.assess_creative_intent):
        assert "suggested_shots" not in inspect.getsource(fn) and "compute_budget_hint" not in inspect.getsource(fn)
    assert "suggested_shots" not in inspect.getsource(duration_fit)


def test_user_directives_and_type_win_over_hint_text(v55):
    u = _build_user(fx.make_inputs(**fx.CASES["highlights_opening_directive"]))
    assert "never overrides the user's instructions" in u and "always win over this strategy" in u


# ---- selection diagnostics: correct, independent, collision-safe, serialisable ---------------------------------
def _independent_selection_check(plan, inp):
    """Recompute from first principles, sharing no code with selection_diagnostics."""
    used = [str(s["asset_id"]).lower() for s in sorted(plan["segments"], key=lambda x: x["order"])]
    outs = [float(s["output_duration_seconds"]) for s in plan["segments"]]
    payoff_ids = set()
    for m in inp.moments:
        for v in (m.get("editorial") or {}).get("visual_candidates", []):
            if v.get("role") == "payoff":
                payoff_ids.add(m["id"].lower())
    return {"n": len(used), "distinct": len(set(used)), "total": round(sum(outs), 2),
            "unused_payoff": sorted(payoff_ids - set(used))}


def test_selection_numbers_match_an_independent_recomputation(v55):
    ms = _distinct_prefix_moments()
    inp = fx.make_inputs(moments=ms, image_moment_order=[m["id"] for m in ms], **H)
    plan = _plan_for(inp, [(3, 0, 8), (1, 0, 5.2), (1, 9.5, 12.5), (2, 1.58, 4.5)])
    d = selection_diagnostics(plan, inp, {}, plan)
    ind = _independent_selection_check(plan, inp)
    assert (d["shots"]["n"], d["shots"]["distinct"], d["budget"]["delivered_s"]) == (ind["n"], ind["distinct"], ind["total"])
    refs = {m["id"].lower(): m["id"][:8] for m in ms}
    assert sorted(u["m"] for u in d["unused_payoff"]) == sorted(refs[i] for i in ind["unused_payoff"])
    assert d["budget"]["pre_fit_total_s"] == d["budget"]["delivered_s"]               # no fit => pre == delivered
    assert [u["m"] for u in d["used"]] == [refs[str(s["asset_id"]).lower()] for s in plan["segments"]]


def test_short_refs_never_collide_within_a_job():
    same = [f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in range(5)]
    r = ep._short_refs(same)
    assert len(set(r.values())) == 5 and all(len(v) >= 8 for v in r.values())
    assert all(full.startswith(ref) for full, ref in r.items())                      # a ref is always a prefix of its id
    mixed = ["abcdefgh", "abcdefghij", "abcdefghik", "m1", "m10"]
    r2 = ep._short_refs(mixed)
    assert len(set(r2.values())) == len(mixed)
    rand = [__import__("uuid").uuid4().hex for _ in range(200)]
    rr = ep._short_refs(rand)
    assert len(set(rr.values())) == 200 and max(len(v) for v in rr.values()) <= 10    # random ids stay short
    assert ep._short_refs(same) == ep._short_refs(list(reversed(same)))              # deterministic


def test_diagnostics_with_colliding_prefixes_stay_unambiguous(v55):
    inp = fx.make_inputs(**H)                                                         # fixture ids all start "aaaaaaaa"
    plan = _plan_for(inp, [(0, 0, 3), (1, 0, 5.2), (2, 1.58, 4.5)])
    d = selection_diagnostics(plan, inp, {}, None)
    refs = [u["m"] for u in d["used"]]
    assert len(set(refs)) == 3
    assert not ({u["m"] for u in d["unused_payoff"]} & set(refs))                    # an unused ref never equals a used ref


def test_selection_serialises_through_the_job_store_unchanged(v55):
    from edit_plan_jobs import _ser, _deser_val
    ms = _distinct_prefix_moments()
    inp = fx.make_inputs(moments=ms, image_moment_order=[m["id"] for m in ms], **H)
    d = selection_diagnostics(_plan_for(inp, [(3, 0, 8), (1, 0, 5.2)]), inp, {}, None)
    back = _deser_val({"M": _ser(d)})
    assert json.loads(json.dumps(back)) == json.loads(json.dumps(d))                  # no loss through the DynamoDB codec
    assert len(json.dumps(d)) < 20000                                                  # small enough for a job item


def test_diagnostics_store_no_images_and_no_prompt_text(v55):
    ms = _distinct_prefix_moments()
    inp = fx.make_inputs(moments=ms, image_moment_order=[m["id"] for m in ms], **H)
    s = json.dumps(selection_diagnostics(_plan_for(inp, [(3, 0, 8)]), inp, {}, None))
    for banned in ("TYPE STRATEGY", "CREATIVE DIRECTION", "BUDGET", "xff", "base64", "data:image"):
        assert banned not in s
