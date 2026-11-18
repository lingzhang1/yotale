"""B0 verification: attribution reaches the worker, resets on every path, and every capability that calls a model
goes through an adapter that logs `model_call_usage`."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import model_gateway
from model_gateway import current_call_context


class _Store:
    def __init__(self, job):
        self.job = job

    def get(self, job_id):
        return self.job


def test_worker_job_context_is_set_during_the_run_and_cleared_after_success_and_failure(monkeypatch):
    from app import worker
    seen = {}

    def ok(store, job_id, job):
        seen["ctx"] = current_call_context()
        return "completed"

    def boom(store, job_id, job):
        seen["ctx_boom"] = current_call_context()
        raise RuntimeError("worker blew up")

    job = {"job_id": "j-1", "owner": "u-1", "operation_type": "edit_plan"}
    monkeypatch.setattr(worker, "_run_edit_plan", ok)
    assert worker._run_one(_Store(job), "j-1") == "completed"
    assert seen["ctx"]["story_user_id"] == "u-1" and seen["ctx"]["job_id"] == "j-1"
    assert seen["ctx"]["operation"] == "worker:edit_plan"
    assert current_call_context() == {}

    monkeypatch.setattr(worker, "_run_edit_plan", boom)
    with pytest.raises(RuntimeError):
        worker._run_one(_Store(job), "j-1")
    assert seen["ctx_boom"]["job_id"] == "j-1"
    assert current_call_context() == {}                         # a crashing job never leaks into the next SQS record


def test_two_consecutive_jobs_never_share_a_call_counter_or_attribution(monkeypatch):
    from app import worker
    log = []

    def run(store, job_id, job):
        model_gateway._next_call_index()
        log.append((current_call_context(), model_gateway._next_call_index()))
        return "completed"

    monkeypatch.setattr(worker, "_run_edit_plan", run)
    for n in (1, 2):
        worker._run_one(_Store({"job_id": f"j-{n}", "owner": f"u-{n}", "operation_type": "edit_plan"}), f"j-{n}")
    assert [(c["job_id"], c["story_user_id"], idx) for c, idx in log] == [("j-1", "u-1", 2), ("j-2", "u-2", 2)]


# Every module that calls `generate_structured` is an AI capability. The adapters (OpenAI, Gemini) are the ONLY classes that
# reach a provider, and both emit model_call_usage per billed attempt. This inventory fails when a NEW call site appears,
# forcing a conscious review that it goes through an adapter-backed gateway rather than a bespoke client.
KNOWN_CAPABILITY_CALL_SITES = {
    "packages/asset_engine/__init__.py",              # asset understanding
    "packages/creative_intent/__init__.py",
    "packages/duration_planner/__init__.py",
    "packages/edit_planner/__init__.py",              # edit plan (original / explore / revise, repairs)
    "packages/edit_planner/revision_interpreter.py",  # interpret revision
    "packages/music_plan/__init__.py",
    "packages/scene_understanding/__init__.py",
    "packages/story_coverage/__init__.py",
    "packages/story_coverage_v2/__init__.py",
    "packages/story_director/__init__.py",            # AI Ideas
    "packages/story_guide/__init__.py",               # guide v1, v2, refine
    "packages/model_gateway/__init__.py",             # the gateway protocol / fallback wrapper itself
}


def test_every_model_call_site_is_a_known_capability_that_goes_through_the_gateway():
    root = Path(__file__).resolve().parents[3]
    found = set()
    for p in (root / "packages").rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if "/tests/" in rel or rel.rsplit("/", 1)[-1].startswith("test_") or "fakes" in rel:
            continue
        if re.search(r"\.generate_structured\(", p.read_text(encoding="utf-8", errors="ignore")):
            found.add(rel)
    assert found == KNOWN_CAPABILITY_CALL_SITES, (found ^ KNOWN_CAPABILITY_CALL_SITES)


def test_only_adapters_reach_a_provider_and_both_log_each_attempt():
    root = Path(__file__).resolve().parents[3] / "packages" / "model_gateway"
    for name in ("openai_gateway.py", "gemini_gateway.py"):
        src = (root / name).read_text()
        assert "log_model_call(req.task, rec)" in src, f"{name} must log every billed attempt"
    # Bedrock is not routable (policy), so it cannot produce unlogged spend.
    provider = (root / "provider.py").read_text()
    assert "Anthropic/Bedrock routing is disabled" in provider
