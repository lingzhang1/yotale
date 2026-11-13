"""content_language (i18n en / zh-Hans) — backend integration tests. FAKE gateways only (no network/model).

Covers: runtime system-prompt suffix present/absent (None => byte-identical), Chinese survives request building,
Chinese revise interpretation + grounding guard, Han search queries -> graceful no-image path, coverage job
cache/fingerprint keys, endpoint tolerance (unknown language never 4xx), music-plan vocabulary guard.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import scene_image as si
from app.deps import (
    get_creative_intent_engine,
    get_duration_planner_engine,
    get_story_coverage_v2_engine,
    get_story_director_engine,
    get_story_guide_refine_engine,
    get_story_guide_v2_engine,
)
from app.main import create_app
from creative_intent import RealCreativeIntentEngine
from duration_planner import DurationPlannerInputs, RealDurationPlannerEngine
from edit_planner.revision_interpreter import (
    CHINESE_GUIDANCE, _SYSTEM_V1, _SYSTEM_V2, exclude_is_supported, ground_directives, interpret_revision,
    system_for_instruction,
)
from language_policy import content_language_instruction
from model_gateway import FakeModelGateway, StructuredResult, Usage
from story_coverage import CoverageInput, RealStoryCoverageEngine
from story_coverage_v2 import CoverageV2Input, RealStoryCoverageMapper, RealStoryJudgmentEngine
from story_director import RealStoryDirectorEngine, sanitize_reference_query
from story_guide import (
    GuideInput, RealStoryGuideRefineEngine, RealStoryGuideV2Engine, RefineInput,
)

ZH = content_language_instruction("zh-Hans")
EN = content_language_instruction("en")
_ROOT = Path(__file__).resolve().parents[3]


# ------------------------------------------------------------------------------------------------ guide v2
_GUIDE_RESP = {"framing_summary": "x", "scenes": [{"id": "s1", "title": "t", "what_to_capture": "w",
                                                   "how_to_shoot": "h", "why_it_matters": "y"}]}
_ZH_INTENT = {"summary": "东京三日游", "title": "我的东京之旅", "raw_user_description": "想拍美食和夜景，节奏轻松"}


def _v2_req(lang, intent=None):
    gw = FakeModelGateway(response=_GUIDE_RESP)
    eng = RealStoryGuideV2Engine(gw)
    return eng.build_request(GuideInput(story_id=uuid.uuid4(), creative_intent=intent or {"summary": "Trip"},
                                        scope={}, content_language=lang)), eng


def test_guide_v2_prompt_byte_identical_without_language():
    req, eng = _v2_req(None)
    assert req.system == eng._system                       # exactly the on-disk prompt
    assert _v2_req("fr")[0].system == eng._system          # unknown language ignored
    assert ZH not in req.system and EN not in req.system


def test_guide_v2_zh_suffix_appended_and_prompt_prefix_untouched():
    req, eng = _v2_req("zh-CN")
    assert req.system.startswith(eng._system) and req.system.endswith(ZH)
    assert req.prompt_version == "story_guide/v2"          # version string NOT bumped
    req_en, _ = _v2_req("en")
    assert req_en.system.endswith(EN)


def test_guide_v2_user_content_english_unchanged_and_chinese_survives_unescaped():
    en_req, _ = _v2_req(None, {"summary": "Trip"})
    assert '"summary": "Trip"' in en_req.user_content
    req, _ = _v2_req("zh-Hans", _ZH_INTENT)
    assert "东京三日游" in req.user_content and "我的东京之旅" in req.user_content
    assert "\\u" not in req.user_content                   # not \\uXXXX-escaped


def test_guide_v2_mints_ids_with_chinese_content_intact():
    gw = FakeModelGateway(response={"framing_summary": "为你的东京之旅", "scenes": [
        {"id": "s1", "title": "涩谷夜景", "what_to_capture": "霓虹灯下的路口", "how_to_shoot": "手持慢慢推近",
         "why_it_matters": "夜晚的节奏", "visual_reference_query": "wide city crossing night"}]})
    g = RealStoryGuideV2Engine(gw).generate(GuideInput(story_id=uuid.uuid4(), creative_intent=_ZH_INTENT,
                                                       scope={}, content_language="zh-Hans"))
    assert g.scenes[0].id == "scene_01" and g.scenes[0].title == "涩谷夜景"
    assert g.scenes[0].visual_reference_query == "wide city crossing night"


def test_guide_refine_suffix_and_instruction_survives():
    gw = FakeModelGateway(response={"framing_summary": "x", "scenes": []})
    eng = RealStoryGuideRefineEngine(gw)
    base = dict(story_id=uuid.uuid4(), creative_intent={}, scope={}, current_framing_summary="",
                current_scenes=[], captured_scene_ids=[], pinned_scene_ids=[],
                user_instruction="多加一些美食镜头", event_context="我们在东京")
    r0 = eng.build_request(RefineInput(**base))
    assert r0.system == eng._system
    r1 = eng.build_request(RefineInput(**base, content_language="zh"))
    assert r1.system.endswith(ZH)
    assert "多加一些美食镜头" in r1.user_content and "我们在东京" in r1.user_content


# ------------------------------------------------------------------------------------------------ coverage
def test_coverage_v1_suffix():
    eng = RealStoryCoverageEngine(FakeModelGateway(response={}))
    mk = lambda **k: CoverageInput(story_id=uuid.uuid4(), creative_intent={"summary": "一次旅行"}, scope={},
                                    moment_understandings=[], **k)
    assert eng.build_request(mk()).system == eng._system
    r = eng.build_request(mk(content_language="zh-Hans"))
    assert r.system.endswith(ZH) and "一次旅行" in r.user_content


def test_coverage_v2_mapper_and_judge_suffix():
    guide = {"framing_summary": "f", "dimensions": [{"id": "d1", "label": "夜景", "purpose": "p",
                                                      "capture_possibilities": []}]}
    mapper_gw = FakeModelGateway(response={"dimension_coverage": [{"story_guide_dimension_id": "d1",
                                                                   "state": "strong"}],
                                           "strengths": [], "redundancies": []})
    mapper = RealStoryCoverageMapper(mapper_gw)
    inp = CoverageV2Input(story_id=uuid.uuid4(), story_guide=guide, creative_intent={}, scope={},
                          moment_understandings=[])
    mapper.map(inp)
    assert mapper_gw.calls[0].system == mapper._system
    assert "夜景" in mapper_gw.calls[0].user_content
    inp.content_language = "zh-Hans"
    mapper.map(inp)
    assert mapper_gw.calls[1].system.endswith(ZH)

    jgw = FakeModelGateway(response={"sufficiency": {"status": "workable", "reason": "r"}, "story_idea": None})
    judge = RealStoryJudgmentEngine(jgw)
    ev = {"creative_intent": {}, "scope": {}, "positive_actual_story_evidence": ["夜景很强"],
          "material_scope_evidence": {}, "redundancy": [], "pending_count": 0}
    judge.judge(ev)
    assert jgw.calls[0].system == judge._system
    judge.judge(ev, content_language="zh-Hans")
    assert jgw.calls[1].system.endswith(ZH)
    assert "夜景很强" in jgw.calls[1].user_content


def test_duration_and_creative_intent_suffix():
    gw = FakeModelGateway(response={"recommended_range_seconds": [20, 30], "highlights_range_seconds": [10, 15],
                                    "feasible_ceiling_seconds": 40, "rationale": "r"})
    eng = RealDurationPlannerEngine(gw)
    ev = {"feasible_band_seconds": [5, 40]}
    eng.recommend(DurationPlannerInputs(creative_intent={"summary": "x"}, evidence=ev))
    assert gw.calls[0].system == eng._system
    eng.recommend(DurationPlannerInputs(creative_intent={"summary": "x"}, evidence=ev, content_language="zh-Hans"))
    assert gw.calls[1].system.endswith(ZH)

    ci = RealCreativeIntentEngine(FakeModelGateway(response={}))
    assert ci.build_request("hello").system == ci._system
    r = ci.build_request("我想拍一个关于外婆的故事", "zh-Hans")
    assert r.system.endswith(ZH) and "我想拍一个关于外婆的故事" in r.user_content


# ------------------------------------------------------------------------------------------------ director
_DIR_RESP = {
    "concept": {"id": "c1", "title": "准备", "summary": "旅程从家里开始。"},
    "plan": {"id": "p1", "concept_id": "c1", "beats": [{"id": "b1", "purpose": "展示准备。"}],
             "shots": [{"id": "s1", "order": 1, "beat_id": "b1", "purpose": "拍背包。",
                        "instruction": "拍门口的背包。", "visual_reference_query": "close up backpack door"}]},
    "director_state": {"current_beat_id": "b1", "beat_progress": []},
    "decision": {"action": "capture_shot", "shot": {"id": "s1", "order": 1, "beat_id": "b1", "purpose": "拍背包。",
                                                    "instruction": "拍门口的背包。"}},
}


def test_director_suffix_and_chinese_output_survives():
    gw = FakeModelGateway(response=_DIR_RESP)
    eng = RealStoryDirectorEngine(gw)
    eng.initialize({"summary": "徒步"}, None)
    assert gw.calls[0].system == eng._system
    out = eng.initialize({"summary": "徒步"}, None, content_language="zh-Hans")
    assert gw.calls[1].system.endswith(ZH) and "徒步" in gw.calls[1].user_content
    assert out.decision.shot.instruction == "拍门口的背包。"
    assert list(out.shot_reference_queries.values()) == ["close up backpack door"]
    eng.next({"creative_intent": {}}, content_language="zh")
    assert gw.calls[2].system.endswith(ZH)


def test_director_han_reference_query_is_unusable_not_garbage():
    assert sanitize_reference_query("close up 吉他 bookshelf") is None
    assert sanitize_reference_query("吉他") is None
    assert sanitize_reference_query("close up acoustic guitar") == "close up acoustic guitar"   # English unchanged
    resp = json.loads(json.dumps(_DIR_RESP))
    resp["plan"]["shots"][0]["visual_reference_query"] = "特写 背包"
    out = RealStoryDirectorEngine(FakeModelGateway(response=resp)).initialize({"summary": "x"}, None)
    assert out.shot_reference_queries == {}                # text-only card, no raise


def test_director_unsafe_backstop_covers_chinese():
    resp = json.loads(json.dumps(_DIR_RESP))
    resp["plan"]["shots"][0]["instruction"] = "边走边后退着拍"
    resp["decision"]["shot"]["instruction"] = "边走边后退着拍"
    from model_gateway import StructuredOutputError
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=resp)).initialize({"summary": "x"}, None)


# ------------------------------------------------------------------------------------------------ scene image / video
def test_scene_image_normalize_query_han_is_unusable():
    assert si.normalize_query("wide shot city skyline") == "wide shot city skyline"   # English unchanged
    assert si.normalize_query("城市天际线") is None
    assert si.normalize_query("wide 城市 skyline") is None          # never a half-query sent to the provider


class _Boom:
    def search_one(self, q):                                       # pragma: no cover - must not be called
        raise AssertionError("provider must not be called for a Han query")


def test_scene_image_and_video_endpoints_gracefully_fall_back_for_han(monkeypatch):
    import app.main as main_mod
    main_mod._SCENE_IMAGE_CACHE = None
    main_mod._SCENE_IMAGE_CLIENT_FACTORY = lambda: _Boom()
    try:
        c = TestClient(create_app())
        r = c.post("/v1/scene-image", json={"query": "城市夜景 特写"})
        assert r.status_code == 200 and r.json() == {"image": None, "status": "invalid_query"}
        monkeypatch.setenv("STORY_REFERENCE_MEDIA_MODE", "video")
        r2 = c.post("/v1/scene-video", json={"query": "城市夜景", "technique_text": "缓慢推近"})
        assert r2.status_code == 200 and r2.json() == {"video": None, "status": "invalid_query"}
    finally:
        main_mod._SCENE_IMAGE_CLIENT_FACTORY = None
        main_mod._SCENE_IMAGE_CACHE = None


# ------------------------------------------------------------------------------------------------ revision interpreter
class _GW:
    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_structured(self, req):
        self.calls.append(req)
        return StructuredResult(data=self.data, usage=Usage())


_NUM = [{"number": i, "id": f"id-{i}", "summary": f"片段{i}"} for i in range(1, 9)]
_ZH_DIRECTIVE = {"must_include": [], "exclude": [7], "opening": 3, "ending": None, "order_after": [],
                 "order_adjacent": [], "soft_direction": "", "unsupported": []}


def test_ascii_instruction_prompt_is_byte_identical():
    gw = _GW(dict(_ZH_DIRECTIVE))
    interpret_revision("Start with Moment 3 and remove Moment 7", _NUM, gw)
    assert gw.calls[0].system == _SYSTEM_V2
    gw1 = _GW(dict(_ZH_DIRECTIVE))
    interpret_revision("Start with Moment 3 and remove Moment 7", _NUM, gw1, prompt_version="revision_interpret/1")
    assert gw1.calls[0].system == _SYSTEM_V1
    assert system_for_instruction(_SYSTEM_V2, "use moment 3, then 4") == _SYSTEM_V2


def test_chinese_revise_resolves_to_real_moment_ids_and_prompt_has_guidance():
    instr = "从片段3开始，不要使用片段7"
    gw = _GW(dict(_ZH_DIRECTIVE))                    # fake model returns opening=3, exclude=[7]
    r = interpret_revision(instr, _NUM, gw)
    sys_prompt = gw.calls[0].system
    assert sys_prompt.startswith(_SYSTEM_V2) and sys_prompt.endswith(CHINESE_GUIDANCE)
    for needle in ("从片段3开始，不要使用片段7", "片段N", "第N个片段", "镜头N", "第N段", "一二三", "两 = 2",
                   "０-９", "从…开始", "不要用", "必须包含", "紧接着", "放在…后面", "节奏更快", "VERBATIM"):
        assert needle in sys_prompt, needle
    assert instr in gw.calls[0].user_content                         # original text preserved, not translated
    assert r.directives == {"opening": "id-3", "exclude": ["id-7"]}
    assert not r.unresolved
    # the grounding guard must NOT flag the Chinese exclude (不要使用 is an omission cue)
    assert ground_directives(r) == []


def test_chinese_inclusion_only_still_flags_unsupported_exclude():
    r = interpret_revision("从片段3开始，片段2紧接着", _NUM, _GW(dict(_ZH_DIRECTIVE)))
    assert ground_directives(r) and "unsupported_exclude" in ground_directives(r)[0]


@pytest.mark.parametrize("text", [
    "不要用片段7", "把第7个片段去掉", "删掉镜头7", "跳过片段7", "排除片段7", "只用片段1、2、3", "除了片段3都不要",
    "Remove Moment 7", "use only 1, 2",
])
def test_exclude_cues_supported(text):
    assert exclude_is_supported(text)


@pytest.mark.parametrize("text", ["从片段3开始", "片段5放在最后", "第3个片段紧接着第2个片段", "Use Moment 3 first"])
def test_exclude_cues_not_supported_for_pure_ordering(text):
    assert not exclude_is_supported(text)


def test_mixed_and_fullwidth_instructions_get_guidance():
    for instr in ("Start with 片段3 and drop Moment 7", "use moment ３ first", "use moment 3，then 4", "第三个片段放最前"):
        gw = _GW(dict(_ZH_DIRECTIVE))
        interpret_revision(instr, _NUM, gw)
        assert gw.calls[0].system.endswith(CHINESE_GUIDANCE), instr
        assert instr.strip() in gw.calls[0].user_content


def test_interpret_endpoint_chinese_end_to_end(monkeypatch):
    gw = _GW(dict(_ZH_DIRECTIVE))
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "get_model_gateway", lambda: gw)
    ids = {i: str(uuid.uuid4()) for i in range(1, 9)}
    moments = [{"number": i, "id": ids[i], "summary": f"片段{i}"} for i in ids]
    r = TestClient(create_app()).post("/v1/interpret-revision",
                                      json={"instruction": "从片段3开始，不要使用片段7", "moments": moments})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["directives"] == {"opening": ids[3], "exclude": [ids[7]]}
    assert b["blocking"] == [] and b["can_submit"] is True
    assert len(gw.calls) == 1                                        # no needless reinterpretation


# ------------------------------------------------------------------------------------------------ endpoints
class _Rec:
    """Records the kwargs/inputs each engine receives; returns a schema-valid minimal result."""
    def __init__(self):
        self.seen = []


def test_guide_v2_endpoint_unknown_and_variant_language_never_4xx():
    seen = []

    class _E:
        def generate(self, inp):
            seen.append(inp.content_language)
            from story_guide import MockStoryGuideV2Engine
            return MockStoryGuideV2Engine().generate(inp)

    app = create_app()
    app.dependency_overrides[get_story_guide_v2_engine] = lambda: _E()
    c = TestClient(app)
    for raw in (None, "zh_Hans", "en-US", "klingon", "", "zh-Hant", 5):
        body = {"story_id": str(uuid.uuid4()), "creative_intent": _ZH_INTENT, "scope": {}}
        if raw is not None:
            body["content_language"] = raw
        r = c.post("/v1/story-guide-v2", json=body)
        if raw == 5:
            assert r.status_code == 422                      # wrong JSON type only; strings are never rejected
        else:
            assert r.status_code == 200, (raw, r.text)
    assert seen == [None, "zh-Hans", "en", None, None, None]


def test_director_endpoint_passes_language_only_when_set():
    calls = []

    class _E:
        def initialize(self, *a, **k):
            calls.append(("init", a, k))
            return RealStoryDirectorEngine(FakeModelGateway(response=_DIR_RESP)).initialize({"summary": "x"}, None)

        def next(self, *a, **k):
            calls.append(("next", a, k))
            return RealStoryDirectorEngine(FakeModelGateway(response=_DIR_RESP)).initialize({"summary": "x"}, None)

    app = create_app()
    app.dependency_overrides[get_story_director_engine] = lambda: _E()
    c = TestClient(app)
    c.post("/v1/director/initialize", json={"creative_intent": {}, "scene_understanding": None})
    c.post("/v1/director/initialize", json={"creative_intent": {}, "content_language": "zh-CN"})
    c.post("/v1/director/next", json={"prior": {}})
    c.post("/v1/director/next", json={"prior": {}, "content_language": "zh"})
    assert calls[0][2] == {} and calls[1][2] == {"content_language": "zh-Hans"}
    assert calls[2][2] == {} and calls[3][2] == {"content_language": "zh-Hans"}


def test_creative_intent_endpoint_language_kwarg_only_when_set():
    calls = []

    class _E:
        def resolve(self, raw_text, **k):
            calls.append(k)
            from creative_intent import MockCreativeIntentEngine
            return MockCreativeIntentEngine().resolve(raw_text)

    app = create_app()
    app.dependency_overrides[get_creative_intent_engine] = lambda: _E()
    c = TestClient(app)
    assert c.post("/v1/creative-intent", json={"raw_text": "我想拍外婆"}).status_code == 200
    assert c.post("/v1/creative-intent", json={"raw_text": "我想拍外婆", "content_language": "zh"}).status_code == 200
    assert calls == [{}, {"content_language": "zh-Hans"}]


# ------------------------------------------------------------------------------------------------ coverage job keys
def _cov_body(**extra):
    b = {"story_id": "00000000-0000-0000-0000-0000000000aa",
         "story_guide": {"dimensions": [{"id": "d1", "label": "x", "purpose": "p", "capture_possibilities": []}]},
         "creative_intent": {"target_duration_seconds": 30.0}, "scope": {}, "moment_understandings": [],
         "pending_count": 0}
    b.update(extra)
    return json.dumps(b)


def _submit(body):
    from .test_coverage_jobs_api import FakeStore, _client
    store = FakeStore()
    c = _client(store)
    r = c.post("/v1/story-coverage/v2/jobs", data={"operation_id": "op-1", "body": body})
    assert r.status_code == 202, r.text
    job = next(iter(store.jobs.values()))
    return job["fp"], job["request_ref"]["body_json"]


def test_coverage_job_key_identical_when_language_absent_or_unknown():
    fp0, stored0 = _submit(_cov_body())
    fp_null, stored_null = _submit(_cov_body(content_language=None))
    fp_bad, stored_bad = _submit(_cov_body(content_language="klingon"))
    assert fp0 == fp_null == fp_bad
    assert stored0 == stored_null == stored_bad and "content_language" not in stored0


def test_coverage_job_key_differs_by_normalized_language():
    fp0, _ = _submit(_cov_body())
    fp_zh, stored = _submit(_cov_body(content_language="zh_CN"))
    fp_zh2, _ = _submit(_cov_body(content_language="zh-Hans"))
    fp_en, _ = _submit(_cov_body(content_language="en-US"))
    assert fp_zh == fp_zh2                       # variants collapse to the same canonical key
    assert len({fp0, fp_zh, fp_en}) == 3
    assert json.loads(stored)["content_language"] == "zh-Hans"


def test_worker_reads_content_language_into_input():
    src = (_ROOT / "apps/api/app/worker.py").read_text()
    assert 'content_language=b.get("content_language")' in src


# ------------------------------------------------------------------------------------------------ music plan guard
def test_music_plan_prompt_unchanged_for_ascii_and_english_vocab_for_han():
    from music_plan import MusicPlanInputs, _system_for
    base = MusicPlanInputs(story_id="s", creative_intent={"summary": "Trip"}, music_direction={"mood_tags": ["calm"]},
                           target_duration_seconds=30.0)
    assert _system_for("SYS", base) == "SYS"
    zh = MusicPlanInputs(story_id="s", creative_intent={"summary": "东京之旅"}, music_direction={},
                         target_duration_seconds=30.0)
    out = _system_for("SYS", zh)
    assert out.startswith("SYS") and "ENGLISH music-catalog vocabulary" in out


# ------------------------------------------------------------------------------------------------ schema surface
def test_openapi_exposes_optional_content_language_on_expected_requests():
    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    for name in ("StoryGuideRequest", "StoryGuideRefineRequest", "StoryCoverageRequest", "StoryCoverageV2Request",
                 "DirectorInitializeRequest", "DirectorNextRequest", "DurationRecommendationRequest",
                 "ResolveCreativeIntentRequest"):
        s = schemas[name]
        assert "content_language" in s["properties"], name
        assert "content_language" not in s.get("required", []), name
