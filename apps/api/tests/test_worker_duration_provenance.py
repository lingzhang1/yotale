"""Worker run path (apps/api/app/worker.py _run_edit_plan): the persisted job diagnostics carry the deterministic
duration fit, the effective prompt version, and the API / worker code revisions, and the published plan is the
fitted one. No AWS, no real model (FakeModelGateway + FakeStore)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

_ROOT = Path(__file__).resolve().parents[3]
for rel in (".", "packages", "apps/api"):
    p = str((_ROOT / rel).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)

import edit_plan_jobs as _jobs  # noqa: E402
import edit_planner  # noqa: E402
from model_gateway import FakeModelGateway  # noqa: E402

_spec = importlib.util.spec_from_file_location("dpworker", str(_ROOT / "apps/api/app/worker.py"))
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


class FakeStore:
    def __init__(self, job, envelope):
        self.job, self.envelope = dict(job), envelope
        self.completed = None
        self.failed = None
        self.lease = None

    def get(self, job_id):
        return self.job

    def claim_lease(self, job_id):
        if self.job["status"] in _jobs.TERMINAL:
            return None
        self.lease = "tok"
        self.job["status"] = "running"
        return self.lease

    def is_cancel_requested(self, job_id):
        return False

    def mark_cancelled(self, job_id):
        return True

    def load_request(self, prefix, order):
        return json.dumps(self.envelope), []

    def complete(self, job_id, plan, diag, token):
        self.completed = (plan, diag)
        self.job["status"] = "completed"
        return True

    def fail(self, job_id, category, detail, token=None):
        self.failed = (category, detail)
        return True

    def delete_staging(self, prefix):
        pass


def _setup(monkeypatch, envelope_extra=None):
    mids = [str(uuid4()) for _ in range(5)]
    moments = [{"id": m, "duration_seconds": 20.0, "useful_segments": [[0.0, 20.0]],
                "editorial": {"visual_candidates": [{"start_time": 8, "end_time": 12, "peak_time": 10, "confidence": 0.9}]}}
               for m in mids]
    body = {"story_id": str(uuid4()), "creative_intent_id": str(uuid4()),
            "creative_intent": {"target_duration_seconds": 50.0}, "moments": moments, "music_plan": {}}
    env = {"body": json.dumps(body), "sheet_order": [], "approach": "storytelling",
           "build_provenance": {"commit_sha": "abc123", "selection_policy": "evidence_select/2"},
           **(envelope_extra or {})}
    plan = {"target_duration_seconds": 50, "feasible": True, "segments": [
        {"order": i, "asset_id": m, "source_start_seconds": 2.0, "source_end_seconds": 18.0,
         "output_duration_seconds": 16.0, "speed": 1.0, "native_audio": "keep"} for i, m in enumerate(mids)]}
    monkeypatch.setattr(worker, "_build_engine",
                        lambda: edit_planner.RealEditPlannerEngine(FakeModelGateway(response=plan)))
    job = {"job_id": "J1", "status": "queued", "operation_type": _jobs.OP_EDIT_PLAN,
           "request_ref": {"staging_prefix": "jobs/J1/", "sheet_order": "[]"}}
    return FakeStore(job, env)


def _bake(monkeypatch, tmp_path, sha):
    """Simulate the artifact layout: <root>/BUILD_SHA beside <root>/packages/observability/__init__.py."""
    import observability
    pkg = tmp_path / "packages" / "observability"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    if sha is not None:
        (tmp_path / "BUILD_SHA").write_text(sha + "\n")
    monkeypatch.setattr(observability, "__file__", str(pkg / "__init__.py"))


def test_build_sha_reads_the_artifact_stamp_or_reports_unknown(monkeypatch, tmp_path):
    import observability
    _bake(monkeypatch, tmp_path, "0123456789ab-dirty")
    assert observability.build_sha() == "0123456789ab-dirty"
    (tmp_path / "BUILD_SHA").unlink()
    assert observability.build_sha() == "unknown"


def test_worker_persists_fitted_plan_and_provenance(monkeypatch, tmp_path):
    _bake(monkeypatch, tmp_path, "deadbeef1234")
    s = _setup(monkeypatch, {"api_build_sha": "cafe00001234"})
    assert worker._run_one(s, "J1") == "completed", s.failed
    plan, diag = s.completed
    total = sum(seg["output_duration_seconds"] for seg in plan["segments"])
    assert abs(total - 50.0) <= 5.0                                  # fitted (model proposed 80s)
    assert diag["duration_fit"]["before_s"] == 80.0 and diag["duration_fit"]["adopted"] is True
    assert diag["prompt_version"] == edit_planner.PROMPT_VERSION
    assert diag["worker_build_sha"] == "deadbeef1234"
    assert diag["api_build_sha"] == "cafe00001234"
    assert diag["build_provenance"]["selection_policy"] == "evidence_select/2"   # device key passes through


def test_worker_provenance_defaults_to_unknown_for_old_envelopes(monkeypatch, tmp_path):
    _bake(monkeypatch, tmp_path, None)                                # artifact without a stamp
    s = _setup(monkeypatch)                                           # pre-change envelope: no api_build_sha
    assert worker._run_one(s, "J1") == "completed", s.failed
    _plan, diag = s.completed
    assert diag["worker_build_sha"] == "unknown"
    assert "api_build_sha" not in diag
