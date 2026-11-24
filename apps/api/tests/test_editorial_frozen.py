"""scripts/editorial_frozen.py — freeze / breakdown / dry-run replay. Offline: no network, no model, no AWS."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
sys.path.insert(0, os.path.dirname(__file__))

import editorial_frozen as FZ                               # noqa: E402
import _v55_fixtures as fx                                  # noqa: E402


def _au(mid, dur=10.0):
    return {"moment_id": {"S": mid}, "understanding_json": {"S": json.dumps({
        "observed": {"summary": "A hiker crosses a stream.", "subjects": ["hiker"],
                     "events": [{"start_time": 0, "end_time": 5, "description": "crosses"}],
                     "useful_segments": [{"start_time": 0, "end_time": 8}]},
        "editorial": {"visual_candidates": [{"start_time": 1, "end_time": 4, "role": "payoff", "confidence": 0.9,
                                             "visual_value": "stream", "evidence": "X"}], "narrative_candidates": []},
        "sampled_frame_ms": [0, 700, 1400]})}}


def _doc(mids):
    return {"story": {"id": "11111111-1111-4111-8111-111111111111", "intent": {"summary": "hike", "tone": "x"}},
            "moment_refs": [{"moment_id": m, "duration_seconds": 10.0, "added_at": i} for i, m in enumerate(mids)],
            "derived": {"guide": {"json": json.dumps({"framing_summary": "g", "scenes": []})},
                        "coverage": {"json": json.dumps({"dimension_coverage": []})},
                        "music_plan": {"json": json.dumps({"character": {"energy": "calm"}})}}}


@pytest.fixture
def case():
    mids = [f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in range(1, 4)]
    return FZ.freeze_case([_au(m) for m in mids], _doc(mids), editorial_type="highlights", target_s=90.0)


def test_freeze_reproduces_the_ios_payload_and_strips_provenance_text(case):
    assert len(case["moments"]) == 3 and case["creative_intent"]["target_duration_seconds"] == 90.0
    m = case["moments"][0]
    assert m["id"] == m["id"].upper() and m["useful_segments"] == [[0, 8]] and m["sampled_frame_ms"] == [0, 700, 1400]
    assert "evidence" not in m["editorial"]["visual_candidates"][0]               # same sanitising as the planner
    assert case["editorial_type"] == "highlights" and case["n_placeholder_images"] == 3


def test_two_arms_get_identical_source_evidence(case):
    a, b = FZ.breakdown(case, "5.5"), FZ.breakdown(case, "5.6")
    assert a["moments"] == b["moments"] == 3 and a["images"] == b["images"] == 3
    assert FZ.EV._inputs_from_case(dict(case)).moments == FZ.EV._inputs_from_case(dict(case)).moments


def test_breakdown_reports_components_and_56_is_smaller(case):
    a, b = FZ.breakdown(case, "5.5"), FZ.breakdown(case, "5.6")
    assert {"system_prompt", "user_directives"} <= set(a["components"])
    assert b["components"]["system_prompt"] < a["components"]["system_prompt"]
    assert b["text_tokens"] < a["text_tokens"] and b["input_tokens_estimate"] == b["text_tokens"] + b["image_tokens_estimate"]
    assert "moments.sampled_frame_ms" in a["components"] and "moments.sampled_frame_ms" not in b["components"]


def test_breakdown_does_not_leak_the_selected_version(case):
    import edit_planner as ep
    before = ep._EDIT_PLAN_VERSION
    FZ.breakdown(case, "5.6")
    assert ep._EDIT_PLAN_VERSION == before


def test_replay_is_a_dry_run_and_live_is_not_wired(case, tmp_path, capsys):
    p = tmp_path / "case.json"; p.write_text(json.dumps(case))
    assert FZ.main(["replay", "--case", str(p), "--versions", "5.5", "5.6"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"].startswith("DRY RUN") and [x["version"] for x in out["plan"]] == ["5.5", "5.6"]
    assert FZ.main(["replay", "--case", str(p), "--live"]) == 2


def test_no_network_or_model_imports_in_the_tool():
    src = open(FZ.__file__).read()
    for bad in ("import boto3", "import requests", "urllib.request", "ModelGateway(", "BedrockGateway", "OpenAIGateway"):
        assert bad not in src
