"""scripts/editorial_replay.py — frozen-request integrity, refusal rules and worker-path parity. Offline: no network,
no model, no AWS (the S3 `capture` command is exercised only through its pure helpers)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
for rel in ("scripts", "packages", ".", "apps/api/tests"):
    sys.path.insert(0, str(ROOT / rel))

import editorial_replay as R                                 # noqa: E402
import edit_planner as ep                                    # noqa: E402
import edit_plan_jobs as _jobs                               # noqa: E402
import _v55_fixtures as fx                                   # noqa: E402
from model_gateway import FakeModelGateway                   # noqa: E402

MIDS = [f"bbbbbbbb-0000-4000-8000-00000000000{i}" for i in range(1, 4)]


def _envelope(etype="highlights", rc=None, critique=False, target=35.0):
    ms = [{"id": m, "duration_seconds": 10.0, "useful_segments": [[0, 9]],
           "editorial": {"visual_candidates": [{"start_time": 1, "end_time": 4, "role": "payoff", "confidence": 0.9, "visual_value": "x"}],
                         "narrative_candidates": []}, "events": [{"start_time": 0, "end_time": 5, "description": "d"}]} for m in MIDS]
    body = {"story_id": "11111111-1111-4111-8111-111111111111", "creative_intent_id": "22222222-2222-4222-8222-222222222222",
            "creative_intent": {"target_duration_seconds": target, "tone": "x", "raw_text": "hike"}, "story_guide": {"framing_summary": "g"},
            "story_coverage": {"strengths": ["s"]}, "moments": ms, "music_plan": {"character": {"energy": "calm"}},
            "sound_preference": "balanced", "editorial_type": etype, "editorial_mode": "highlights"}
    if rc is not None:
        body["revision_context"] = rc
    return json.dumps({"body": json.dumps(body), "sheet_order": MIDS, "creative_brief": fx.LEGACY_BRIEF,
                       "critique_revision": critique, "approach": "storytelling"})


def _freeze(tmp_path, **kw):
    sheets = [(m, b"\xff\xd8" + bytes([i]) * 50) for i, m in enumerate(MIDS)]
    d = tmp_path / "case"
    R._case_write(d, _envelope(**kw), sheets, {"operation": (kw.get("rc") or {}).get("mode") or "original", "editorial_type": kw.get("etype", "highlights"),
                                                "target_s": 35.0, "critique_revision": bool(kw.get("critique")),
                                                "has_directives": False, "has_soft_direction": False})
    return d


def test_freeze_writes_a_private_verifiable_case(tmp_path):
    d = _freeze(tmp_path)
    assert R.verify_case(d)["ok"] is True
    man = json.loads((d / "manifest.json").read_text())
    assert set(man["components"]) >= {"moments_payload", "story_guide", "story_coverage", "creative_intent_and_target",
                                      "operation_and_instructions", "sound_preference", "music", "sheet_bytes", "sheet_order"}


@pytest.mark.parametrize("victim", ["envelope.json", "sheets/" + MIDS[1] + ".jpg"])
def test_any_tampering_is_detected_before_a_run(tmp_path, victim):
    d = _freeze(tmp_path)
    p = d / victim
    p.write_bytes(p.read_bytes() + b"x")
    assert R.verify_case(d)["ok"] is False
    assert R.main(["run", "--case", str(d), "--arm", "A", "--version", "5.5", "--out", str(tmp_path / "o")]) == 3


def test_two_arms_of_one_case_have_identical_input_components(tmp_path):
    d = _freeze(tmp_path)
    env, body, sheets, man = R.load_case(d)
    a = R.component_hashes(body, env.get("creative_brief"), sheets)
    b = R.component_hashes(json.loads(json.dumps(body)), env.get("creative_brief"), [(m, bytes(x)) for m, x in sheets])
    assert a == b == man["components"]
    body2 = json.loads(json.dumps(body)); body2["story_coverage"] = {"strengths": ["CHANGED"]}
    assert R.component_hashes(body2, env.get("creative_brief"), sheets)["story_coverage"] != a["story_coverage"]   # a Coverage change is visible


def test_refuses_critique_explore_and_directed_requests(tmp_path):
    for kw in (dict(critique=True), dict(rc={"mode": "explore", "base_version_id": "v"})):
        d = tmp_path / ("c" + str(len(os.listdir(tmp_path))))
        d.mkdir()
        dd = _freeze(d, **kw)
        assert R.main(["run", "--case", str(dd), "--arm", "A", "--version", "5.5", "--out", str(d / "o")]) == 3


def test_one_attempt_per_arm_unless_forced(tmp_path):
    d = _freeze(tmp_path)
    out = tmp_path / "o"; out.mkdir(); (out / "result.json").write_text("{}")
    assert R.main(["run", "--case", str(d), "--arm", "A", "--version", "5.5", "--out", str(out)]) == 4


def test_dry_run_reports_prompt_sizes_for_both_versions_without_a_model(tmp_path, capsys):
    d = _freeze(tmp_path)
    import subprocess
    outs = {}
    for v in ("5.5", "5.6"):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "editorial_replay.py"), "run", "--case", str(d), "--arm", "X",
                            "--version", v, "--out", str(tmp_path / f"o{v}"), "--dry-run"],
                           env=dict(os.environ, PYTHONPATH=f"{ROOT}:{ROOT}/packages"), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-500:]
        outs[v] = json.loads(r.stdout)
    assert outs["5.5"]["prompt_version"] == "edit_plan/5.5" and outs["5.6"]["prompt_version"] == "edit_plan/5.6"
    assert outs["5.6"]["system_tokens"] < outs["5.5"]["system_tokens"]
    assert outs["5.5"]["source_hash"] == outs["5.6"]["source_hash"]


def test_replay_builds_exactly_the_prompt_the_worker_builds(tmp_path, monkeypatch):
    """The replay's input construction must equal the worker's. Run the same envelope through the REAL worker path with a
    recording gateway and compare the user message with the one the replay would send."""
    spec = importlib.util.spec_from_file_location("rpworker", str(ROOT / "apps/api/app/worker.py"))
    worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
    d = _freeze(tmp_path)
    env, body, sheets, _ = R.load_case(d)
    seen = []

    class Store:
        job = {"job_id": "J", "status": "queued", "operation_type": _jobs.OP_EDIT_PLAN,
               "request_ref": {"staging_prefix": "jobs/J/", "sheet_order": json.dumps(MIDS)}}
        def get(self, j): return self.job
        def claim_lease(self, j): return "t"
        def is_cancel_requested(self, j): return False
        def mark_cancelled(self, j): return True
        def load_request(self, p, o): return (d / "envelope.json").read_text(), sheets
        def complete(self, *a, **k): return True
        def fail(self, *a, **k): seen.append(a); return True
        def delete_staging(self, p): pass
    plan = {"target_duration_seconds": 2, "feasible": True, "segments": [
        {"order": 0, "asset_id": MIDS[0], "source_start_seconds": 1, "source_end_seconds": 3, "output_duration_seconds": 2,
         "speed": 1.0, "native_audio": "keep"}]}
    gw = FakeModelGateway(response=plan)
    monkeypatch.setattr(worker, "_build_engine", lambda: ep.RealEditPlannerEngine(gw))
    for ver in ("5.5", "5.6"):
        monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", ver)
        gw.calls.clear()
        worker._run_edit_plan(Store(), "J", Store.job)
        mine = ep._build_user(R._inputs(env, body, sheets))
        assert gw.calls[0].user_content == mine, ver
        assert len(gw.calls[0].images) == len(MIDS)


def test_the_tool_has_no_endpoint_flag_or_persistent_logging():
    src = (ROOT / "scripts" / "editorial_replay.py").read_text()
    for bad in ("put_object", "delete_object", "logging.getLogger", "FastAPI", "add_argument(\"--live\""):
        assert bad not in src
