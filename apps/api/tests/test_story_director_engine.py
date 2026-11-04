"""Unit tests for the Story Director engine with a FAKE gateway (no network).

Proves: initialize/next build the right requests; server mints UUID ids over
model-supplied ones; referential integrity (shot->beat) and decision/shot
coherence are enforced; the safety guard rejects unsafe instructions; failures
surface instead of fabricating a plan.
"""

from __future__ import annotations

import pytest

from model_gateway import FakeModelGateway, ProviderError, StructuredOutputError
from story_director import (
    PROMPT_VERSION,
    TASK_INIT,
    DirectorOutput,
    RealStoryDirectorEngine,
)

_CI = {"summary": "TMB hike, peaceful + adventurous", "emphasis": ["journey"]}
_SU = {"summary": "A room with a backpack, chair, window.", "environment_tags": ["indoor"],
       "operator_space": "moderate", "subjects": [{"label": "backpack", "prominence": "high"}]}


def _good(model_shot_id="shot1"):
    # Model returns non-UUID ids (shot1 / b1) — the engine must mint UUIDs.
    return {
        "concept": {"id": "c1", "title": "Preparation", "summary": "The journey begins at home."},
        "plan": {
            "id": "p1", "concept_id": "c1",
            "beats": [{"id": "b_prep", "purpose": "Show preparation."}],
            "shots": [{"id": model_shot_id, "order": 1, "beat_id": "b_prep",
                       "purpose": "Capture the packed bag.", "instruction": "Film the backpack by the door."}],
        },
        "director_state": {"current_beat_id": "b_prep", "beat_progress": []},
        "decision": {"action": "capture_shot",
                     "shot": {"id": model_shot_id, "order": 1, "beat_id": "b_prep",
                              "purpose": "Capture the packed bag.", "instruction": "Film the backpack by the door."}},
    }


def test_initialize_mints_uuid_ids_and_validates():
    gw = FakeModelGateway(response=_good())
    out = RealStoryDirectorEngine(gw).initialize(_CI, _SU)
    assert isinstance(out, DirectorOutput)
    # ids were non-UUID in the response; engine minted valid UUIDs.
    import uuid
    uuid.UUID(str(out.concept.id)); uuid.UUID(str(out.plan.shots[0].id))
    # beat_id (free string) preserved and referenced correctly.
    assert out.plan.shots[0].beat_id == "b_prep"
    # decision shot id aligns with the plan shot id (same model id -> same UUID).
    assert str(out.decision.shot.id) == str(out.plan.shots[0].id)


def test_initialize_request_is_versioned():
    gw = FakeModelGateway(response=_good())
    RealStoryDirectorEngine(gw).initialize(_CI, _SU)
    req = gw.calls[0]
    assert req.task == TASK_INIT
    assert req.prompt_version == PROMPT_VERSION


def test_next_operation():
    gw = FakeModelGateway(response=_good())
    out = RealStoryDirectorEngine(gw).next({"creative_intent": _CI, "scene_understanding": _SU,
                                            "story_state": {"moments": []}})
    assert out.decision.action.value in ("capture_shot", "retry_shot", "rescan_scene", "create_now")


def test_shot_without_beat_is_rejected():
    bad = _good(); bad["plan"]["shots"][0]["beat_id"] = "nonexistent_beat"
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_shot_missing_purpose_or_instruction_rejected():
    bad = _good(); bad["plan"]["shots"][0]["purpose"] = None
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_capture_shot_without_shot_rejected():
    bad = _good(); bad["decision"] = {"action": "capture_shot"}
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_create_now_with_shot_rejected():
    bad = _good(); bad["decision"] = {"action": "create_now", "shot": bad["plan"]["shots"][0]}
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_create_now_without_shot_ok():
    ok = _good(); ok["decision"] = {"action": "create_now"}
    out = RealStoryDirectorEngine(FakeModelGateway(response=ok)).initialize(_CI, _SU)
    assert out.decision.action.value == "create_now"
    assert out.decision.shot is None


def test_safety_guard_rejects_walk_backward_near_edge():
    bad = _good()
    bad["plan"]["shots"][0]["instruction"] = "Walk backward toward the edge while filming your partner."
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_no_beats_rejected():
    bad = _good(); bad["plan"]["beats"] = []
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=bad)).initialize(_CI, _SU)


def test_provider_error_propagates():
    with pytest.raises(ProviderError):
        RealStoryDirectorEngine(FakeModelGateway(error=ProviderError("down"))).initialize(_CI, _SU)


# ---- DIRECT UX enhancements: nullable scene (Skip Scan) + ephemeral candidates ----

def _cand(shot_id, instr):
    return {"action": "capture_shot",
            "shot": {"id": shot_id, "order": 1, "beat_id": "b_prep",
                     "purpose": "alt purpose", "instruction": instr}}


def test_initialize_accepts_null_scene():
    # Skip Scan: scene_understanding is None. Engine must build a request and validate.
    gw = FakeModelGateway(response=_good())
    out = RealStoryDirectorEngine(gw).initialize(_CI, None)
    assert isinstance(out, DirectorOutput)
    # the request content marks the null-scene mode
    assert "NULL" in gw.calls[0].user_content and "SKIP-SCAN" in gw.calls[0].user_content


def test_candidates_minted_and_do_not_inflate_plan():
    r = _good()
    r["candidates"] = [
        _cand("shot1", "Film the backpack by the door."),          # == decision (candidates[0])
        _cand("altA", "Capture your hands zipping the bag closed."),
        _cand("altB", "Film yourself pausing at the doorway before leaving."),
    ]
    out = RealStoryDirectorEngine(FakeModelGateway(response=r)).initialize(_CI, _SU)
    # plan stays minimal — candidates add NO beats/shots (anti-over-planning)
    assert len(out.plan.beats) == 1 and len(out.plan.shots) == 1
    assert len(out.candidates) == 3
    # each candidate shot id was minted to a UUID
    import uuid
    for c in out.candidates:
        uuid.UUID(str(c.shot.id))
    # candidates[0] mirrors the primary decision action
    assert out.candidates[0].action == out.decision.action


def test_candidates_zero_is_fine():
    out = RealStoryDirectorEngine(FakeModelGateway(response=_good())).initialize(_CI, _SU)
    assert out.candidates == []


def test_candidate_zero_action_must_match_primary():
    r = _good()
    r["candidates"] = [{"action": "rescan_scene"}, _cand("altA", "something")]
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=r)).initialize(_CI, _SU)


def test_unsafe_candidate_is_rejected():
    r = _good()
    r["candidates"] = [
        _cand("shot1", "Film the backpack by the door."),
        _cand("altA", "Walk backward toward the edge while filming."),
    ]
    with pytest.raises(StructuredOutputError):
        RealStoryDirectorEngine(FakeModelGateway(response=r)).initialize(_CI, _SU)


# ---- Phase 1A: per-shot visual_reference_query (story_director/v2) ---------

from story_director import (  # noqa: E402
    PROMPT_VERSION as _PV,
    REFERENCE_QUERY_KEY,
    SCHEMA_VERSION as _SV,
    sanitize_reference_query,
)


def _with_queries():
    r = _good()
    r["plan"]["shots"][0][REFERENCE_QUERY_KEY] = "close up backpack by door"
    r["decision"]["shot"][REFERENCE_QUERY_KEY] = "close up backpack by door"
    alt = _cand("altA", "Film your hands zipping the bag.")
    alt["shot"][REFERENCE_QUERY_KEY] = "Hands Zipping   Backpack Close Up"
    bad = _cand("altB", "Film the window light on the bag.")
    bad["shot"][REFERENCE_QUERY_KEY] = "https://example.com 42 !!!"   # nothing usable after normalizing
    r["candidates"] = [{"action": "capture_shot", "shot": dict(r["decision"]["shot"])}, alt, bad]
    r["director_state"]["last_decision"] = {"action": "capture_shot", "shot": dict(r["decision"]["shot"])}
    return r


def test_v2_prompt_and_schema_versions():
    assert _PV == "story_director/v2" and _SV == "story_director.envelope/2"
    gw = FakeModelGateway(response=_good())
    RealStoryDirectorEngine(gw).initialize(_CI, _SU)
    req = gw.calls[0]
    assert req.prompt_version == "story_director/v2"
    assert "VISUAL REFERENCE QUERY" in req.system


def test_model_facing_schema_offers_optional_shot_query_but_not_the_map():
    schema = RealStoryDirectorEngine(FakeModelGateway(response=_good()))._schema
    shot = schema["$defs"]["ShotContract"]
    assert REFERENCE_QUERY_KEY in shot["properties"]
    assert REFERENCE_QUERY_KEY not in shot.get("required", [])
    assert "shot_reference_queries" not in schema["properties"]   # server-computed only


def test_canonical_shot_contract_is_unchanged():
    # The FROZEN canonical ShotContract must not grow the field; it lives only on the envelope.
    from contracts.schemas.ai_contracts import ShotContract
    assert REFERENCE_QUERY_KEY not in ShotContract.model_fields
    assert "visual_reference_query" not in DirectorOutput.model_json_schema()["$defs"]["ShotContract"]["properties"]


def test_reference_queries_keyed_by_minted_ids_and_sanitized():
    out = RealStoryDirectorEngine(FakeModelGateway(response=_with_queries())).initialize(_CI, _SU)
    q = out.shot_reference_queries
    # primary decision shot (same UUID as the plan shot and candidates[0])
    assert q[str(out.decision.shot.id)] == "close up backpack by door"
    assert str(out.candidates[0].shot.id) == str(out.decision.shot.id)
    # alt candidate: whitespace-collapsed + lowercased
    assert q[str(out.candidates[1].shot.id)] == "hands zipping backpack close up"
    # query with no usable words after normalization => no entry => text-only card for that idea
    assert str(out.candidates[2].shot.id) not in q
    # every key is a real minted shot id
    ids = {str(s.id) for s in out.plan.shots} | {str(c.shot.id) for c in out.candidates if c.shot}
    assert set(q) <= ids


def test_missing_queries_yield_empty_map_and_old_shape_still_validates():
    out = RealStoryDirectorEngine(FakeModelGateway(response=_good())).initialize(_CI, _SU)
    assert out.shot_reference_queries == {}


def test_model_authored_map_is_ignored():
    r = _good()
    r["shot_reference_queries"] = {"forged-id": "anything goes"}
    out = RealStoryDirectorEngine(FakeModelGateway(response=r)).initialize(_CI, _SU)
    assert out.shot_reference_queries == {}


def test_reference_query_does_not_leak_into_validated_shots():
    out = RealStoryDirectorEngine(FakeModelGateway(response=_with_queries())).initialize(_CI, _SU)
    dumped = out.model_dump(mode="json")
    blob = str(dumped["plan"]) + str(dumped["decision"]) + str(dumped["candidates"]) + str(dumped["director_state"])
    assert REFERENCE_QUERY_KEY not in blob


@pytest.mark.parametrize("raw,expected", [
    ("close up acoustic guitar bookshelf", "close up acoustic guitar bookshelf"),
    # Owner rule: never withhold a query for FORMAT — normalize instead.
    ("  Person resting on sofa,  wide shot ", "person resting on sofa wide shot"),   # punctuation stripped
    ("guitar", "guitar"),                                                            # one word is fine
    # Real gpt-5.1 output (10 words) previously REJECTED -> no photo on device; now kept.
    ("slow pan medium wide shot guitar bookcase desk window night",
     "slow pan medium wide shot guitar bookcase desk window night"),
    ("a b c d e f g h i j k l m n", "a b c d e f g h i j k l"),                       # truncated to 12
    ("photo of sarah@example.com desk", "photo of desk"),                            # email token removed
    ("see https://example.com/x desk lamp", "see desk lamp"),                        # url token removed
    ("www.example.com desk", "desk"),
    ("shot 4 seconds desk", "shot seconds desk"),                                    # digits stripped
    ("x" * 90, "x" * 90),
    (None, None), (123, None), ("", None), ("   ", None), ("!!! 42 ...", None),     # nothing usable left
    ("office aisle leading lines person", "office aisle leading lines person"),
    ("over-the-shoulder laptop typing", "over-the-shoulder laptop typing"),
])
def test_sanitize_reference_query(raw, expected):
    assert sanitize_reference_query(raw) == expected


def test_long_model_queries_are_kept_for_every_shot():
    # Device regression (Nov 4): 2 of 3 ideas showed no photo because 9-10 word queries were rejected.
    r = _good()
    long_q = "slow pan medium wide shot guitar bookcase desk window night"
    r["plan"]["shots"][0][REFERENCE_QUERY_KEY] = long_q
    r["decision"]["shot"][REFERENCE_QUERY_KEY] = long_q
    alt = _cand("altA", "Frame the guitar by the bookcase.")
    alt["shot"][REFERENCE_QUERY_KEY] = "medium shot acoustic guitar leaning on bookcase indoor night"
    r["candidates"] = [{"action": "capture_shot", "shot": dict(r["decision"]["shot"])}, alt]
    out = RealStoryDirectorEngine(FakeModelGateway(response=r)).initialize(_CI, _SU)
    for c in out.candidates:
        assert str(c.shot.id) in out.shot_reference_queries, "every shot with a query must keep it"
