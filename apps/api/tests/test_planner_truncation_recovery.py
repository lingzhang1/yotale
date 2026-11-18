"""Large-Story planner reliability: truncation recovery, output-budget policy, retry/deadline bounds, failure
diagnostics. Offline only: a scripted stub gateway stands in for the providers (no model call, no AWS).

These tests prove the CONTRACT between the provider adapters and the planner (a truncation error leads to one
bounded retry at a larger budget). They do not prove that a real 68-Moment Story now succeeds: that needs the
approved live validation."""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

import edit_planner as ep                                                    # noqa: E402
import _v55_fixtures as fx                                                   # noqa: E402
from edit_planner import EditPlanInputs, RealEditPlannerEngine, estimate_output_budget   # noqa: E402
from model_gateway import (OutputTruncatedError, ProviderError, StructuredOutputError,   # noqa: E402
                           StructuredResult, Usage, make_attempt)

_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("trworker", str(_ROOT / "apps/api/app/worker.py"))
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


class Scripted:
    """Stub gateway. `need` = output tokens the plan needs: a call whose cap is below it raises the typed
    truncation error exactly as the adapters do. `fail_with` raises that error on every call instead."""

    def __init__(self, plan, *, need=0, provider="openai", fail_with=None, fallback_on_trunc=False):
        self.plan, self.need, self.provider, self.fail_with = plan, need, provider, fail_with
        self.caps: list[int] = []
        self.deadlines: list = []
        self.last_attempts: list[dict] = []
        self.last_fallback, self.last_error = False, None

    def generate_structured(self, req):
        self.caps.append(req.max_tokens)
        self.deadlines.append(req.deadline_ts)
        if self.fail_with is not None:
            self.last_attempts = [make_attempt(provider=self.provider, model="m", n=1, max_tokens=req.max_tokens,
                                               latency_ms=5, outcome="error", error=self.fail_with)]
            raise self.fail_with
        if req.max_tokens < self.need:
            self.last_attempts = [make_attempt(provider=self.provider, model="m", n=1, max_tokens=req.max_tokens,
                                               latency_ms=5, outcome="truncated", finish_reason="length",
                                               usage=Usage(10, req.max_tokens, req.max_tokens + 10))]
            raise OutputTruncatedError("output truncated at max_tokens (increase max_tokens)",
                                       provider=self.provider, finish_reason="length", max_tokens=req.max_tokens)
        self.last_attempts = [make_attempt(provider=self.provider, model="m", n=1, max_tokens=req.max_tokens,
                                           latency_ms=5, outcome="ok", finish_reason="stop",
                                           usage=Usage(1000, 5000, 6000))]
        return StructuredResult(data=self.plan, usage=Usage(1000, 5000, 6000), model="m", provider=self.provider,
                                stop_reason="stop")


def _moments(n):
    return [{"id": str(uuid4()), "duration_seconds": 10.0, "useful_segments": [[0.0, 10.0]],
             "summary": f"moment {i}"} for i in range(n)]


def _inputs(n_moments, target, etype="highlights"):
    ms = _moments(n_moments)
    return fx.make_inputs(moments=ms, image_moment_order=[m["id"] for m in ms],
                          creative_intent={"target_duration_seconds": target},
                          editorial_type=etype, editorial_mode="highlights" if etype == "highlights" else "full")


def _plan_for(inp, n_shots, target):
    each = round(target / n_shots, 3)
    segs = [{"order": i, "asset_id": inp.moments[i % len(inp.moments)]["id"], "source_start_seconds": 0.0,
             "source_end_seconds": each, "output_duration_seconds": each, "speed": 1.0, "native_audio": "keep",
             "narrative_role": "r"} for i in range(n_shots)]
    return {"target_duration_seconds": round(sum(s["output_duration_seconds"] for s in segs), 3),
            "feasible": True, "segments": segs}


# 12. budget estimation -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("target,etype,lo,hi", [
    (35, "highlights", 8192, 8192),        # short video: the floor
    (135, "highlights", 8192, 10240),      # large-Story Highlights ask
    (290, "highlights", 16384, 16384),     # long Highlights: bounded by the initial cap (escalation goes higher)
    (155, "full_story", 8192, 8192),       # Full Story shots are longer: far fewer segments
    (600, "full_story", 8192, 16384),
])
def test_initial_budget_scales_with_duration_and_type(target, etype, lo, hi):
    assert lo <= estimate_output_budget(target, etype) <= hi


def test_budget_is_monotonic_bounded_and_independent_of_moment_count():
    vals = [estimate_output_budget(t, "highlights") for t in range(10, 700, 10)]
    assert vals == sorted(vals) and min(vals) >= 8192 and max(vals) <= 16384
    assert estimate_output_budget(None, None) == 8192 and estimate_output_budget("bad", "highlights") == 8192
    assert estimate_output_budget(135, "highlights", cap=9000) <= 9000
    import inspect
    assert list(inspect.signature(estimate_output_budget).parameters) == ["target_seconds", "editorial_type",
                                                                          "floor", "cap"]   # no Moment-count input


# 1/2/3. truncated at the initial limit, then success after escalation (either provider) --------------------------
@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_truncation_then_success_after_one_escalation(provider):
    inp = _inputs(68, 135)
    gw = Scripted(_plan_for(inp, 45, 135), need=12000, provider=provider)
    eng = RealEditPlannerEngine(gw)
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert out.segments
    assert gw.caps == [d["initial_max_tokens"], d["initial_max_tokens"] * 2] and gw.caps[0] < 12000 <= gw.caps[1]
    assert d["truncation_recovery"] == "recovered" and d["truncation_escalations"] == 1
    assert d["model_calls"] == 1                      # only the successful generation is a billed, completed call
    assert [a["outcome"] for a in d["provider_attempts"]] == ["truncated", "ok"]
    assert all(a["prompt_version"] == ep.PROMPT_VERSION for a in d["provider_attempts"])


# 4. escalated generation also truncated ----------------------------------------------------------------------------
def test_escalated_truncation_fails_after_exactly_two_generations_with_typed_error():
    inp = _inputs(68, 135)
    gw = Scripted(_plan_for(inp, 45, 135), need=10**9)
    eng = RealEditPlannerEngine(gw)
    with pytest.raises(OutputTruncatedError):
        eng.generate(inp)
    assert len(gw.caps) == 2                          # bounded: initial + one escalation, never a loop
    d = eng.last_diagnostics
    assert d["truncation_recovery"] == "failed" and d["last_error_category"] == "truncated"
    assert [a["outcome"] for a in d["provider_attempts"]] == ["truncated", "truncated"]


# 5. unrelated structured-output / provider errors do not escalate --------------------------------------------------
def test_unrelated_structured_error_is_not_retried_as_truncation():
    inp = _inputs(10, 60)
    gw = Scripted(None, fail_with=StructuredOutputError("model did not return a tool call (finish_reason=stop)"))
    eng = RealEditPlannerEngine(gw)
    with pytest.raises(StructuredOutputError) as ei:
        eng.generate(inp)
    assert not isinstance(ei.value, OutputTruncatedError) and len(gw.caps) == 1
    assert eng.last_diagnostics["last_error_category"] == "no_tool_call"


def test_provider_error_is_not_retried_by_the_planner_and_keeps_its_category():
    inp = _inputs(10, 60)
    err = ProviderError("openai 503 server error (retries exhausted)")
    err.primary_failure = {"category": "timeout", "error": "ProviderTimeoutError: slow"}
    gw = Scripted(None, fail_with=err)
    eng = RealEditPlannerEngine(gw)
    with pytest.raises(ProviderError):
        eng.generate(inp)
    d = eng.last_diagnostics
    assert len(gw.caps) == 1 and d["last_error_category"] == "server_error"
    assert d["primary_failure"]["category"] == "timeout"        # the ORIGINAL primary cause survives


# 8. a real validation failure still goes through the existing repair path, not escalation ------------------------
def test_validation_failure_uses_repair_not_truncation_escalation():
    inp = _inputs(10, 60)
    bad = _plan_for(inp, 6, 60)
    bad["segments"][3]["asset_id"] = str(uuid4())               # unknown Moment id
    gw = Scripted(bad)
    eng = RealEditPlannerEngine(gw, executability_repair_attempts=1)
    try:
        eng.generate(inp)
    except Exception:  # noqa: BLE001 - the repair returns the same bad plan; the outcome is not the point
        pass
    d = eng.last_diagnostics
    assert d.get("truncation_escalations", 0) == 0 and d["executability_repairs_used"] == 1
    assert len(gw.caps) == 2 and gw.caps[0] == gw.caps[1]       # same budget: a repair is not an escalation


# 9/10/11. the three fixtures ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("n_moments,target,etype,shots,need,expect_escalation", [
    (68, 135, "highlights", 54, 7000, False),     # 135 s ask: initial budget already fits a normal plan
    (68, 290, "highlights", 100, 18000, True),    # 290 s ask: needs more than the 16,384 initial cap
    (66, 135, "highlights", 56, 5300, False),     # the 66-Moment job that succeeded (about 5.3k per plan)
])
def test_large_story_fixtures(n_moments, target, etype, shots, need, expect_escalation):
    inp = _inputs(n_moments, target, etype)
    gw = Scripted(_plan_for(inp, shots, target), need=need)
    eng = RealEditPlannerEngine(gw)
    out = eng.generate(inp)
    d = eng.last_diagnostics
    assert out.segments and (len(gw.caps) == 2) is expect_escalation
    assert d["model_calls"] == 1 and d.get("critique_attempted") is None        # no extra mandatory inference
    assert max(gw.caps) <= 32768


# 13. retry / deadline policy -----------------------------------------------------------------------------------------
def test_deadline_is_passed_to_every_provider_request():
    inp = _inputs(10, 60)
    gw = Scripted(_plan_for(inp, 6, 60), need=9000)
    eng = RealEditPlannerEngine(gw)
    eng.deadline_ts = time.time() + 600
    eng.generate(inp)
    assert len(gw.deadlines) == 2 and all(d == eng.deadline_ts for d in gw.deadlines)


def test_ceiling_bounds_the_escalation():
    inp = _inputs(68, 290)
    gw = Scripted(_plan_for(inp, 100, 290), need=10**9)
    eng = RealEditPlannerEngine(gw, max_tokens_ceiling=16384)
    with pytest.raises(OutputTruncatedError):
        eng.generate(inp)
    assert len(gw.caps) == 1 and gw.caps[0] == 16384            # nothing larger than the configured ceiling


# 15. routing across supported prompt versions -----------------------------------------------------------------------
@pytest.mark.parametrize("ver,prompt", [("5.3", "edit_plan/5.3"), ("5.5", "edit_plan/5.5"), ("5.6", "edit_plan/5.6")])
def test_recovery_is_version_independent(monkeypatch, ver, prompt):
    monkeypatch.setattr(ep, "_EDIT_PLAN_VERSION", ver)
    monkeypatch.setattr(ep, "PROMPT_VERSION", prompt)
    inp = _inputs(20, 135)
    gw = Scripted(_plan_for(inp, 20, 135), need=9500)
    eng = RealEditPlannerEngine(gw)
    eng.generate(inp)
    d = eng.last_diagnostics
    assert d["truncation_recovery"] == "recovered" and d["provider_attempts"][0]["prompt_version"] == prompt


# 14. sanitized diagnostics for failed jobs --------------------------------------------------------------------------
def test_failure_diagnostics_are_small_sanitized_and_complete():
    exc = OutputTruncatedError("output truncated at maxOutputTokens (increase max_tokens)", provider="gemini")
    exc.primary_failure = {"category": "timeout", "error": "ProviderTimeoutError: openai request timed out after 60s"}
    diag = {"provider_attempts": [{"role": "primary", "provider": "openai", "outcome": "timeout", "latency_ms": 60001},
                                  {"role": "fallback", "provider": "gemini", "outcome": "truncated",
                                   "max_tokens": 8192, "reasoning_tokens": 5000}],
            "initial_max_tokens": 8192, "truncation_recovery": "failed", "truncation_escalations": 1,
            "last_error_category": "truncated", "raw_response": "MUST-NOT-LEAK", "user_content": "MUST-NOT-LEAK"}
    out = worker._failure_diagnostics(diag, exc)
    assert out["truncation_recovery"] == "failed" and out["primary_failure"]["category"] == "timeout"
    assert out["error_type"] == "OutputTruncatedError" and out["prompt_version"] == ep.PROMPT_VERSION
    assert "MUST-NOT-LEAK" not in repr(out) and "raw_response" not in out
    assert worker._with_primary_failure("output truncated", exc) == "output truncated | primary provider: timeout"


def test_worker_failure_path_persists_diagnostics_and_sets_the_deadline(monkeypatch):
    """End to end through _run_edit_plan: both provider generations truncate; the job fails once, with the
    attempt history stored on the failed record and the planner given a wall-clock deadline."""
    import json
    import edit_plan_jobs as _jobs

    class Store:
        def __init__(self, job, env): self.job, self.env, self.failed, self.diag = job, env, None, None
        def get(self, j): return self.job
        def claim_lease(self, j): self.job["status"] = "running"; return "tok"
        def is_cancel_requested(self, j): return False
        def mark_cancelled(self, j): return True
        def load_request(self, prefix, order): return json.dumps(self.env), []
        def complete(self, *a, **k): raise AssertionError("must not complete")
        def fail(self, job_id, category, detail, token=None, diagnostics=None):
            self.failed, self.diag = (category, detail), diagnostics; return True
        def delete_staging(self, p): pass

    inp = _inputs(68, 135)
    body = {"story_id": str(uuid4()), "creative_intent_id": str(uuid4()),
            "creative_intent": {"target_duration_seconds": 135.0}, "moments": inp.moments, "music_plan": {},
            "editorial_type": "highlights", "editorial_mode": "highlights"}
    env = {"body": json.dumps(body), "sheet_order": [], "approach": "visual_first"}
    gw = Scripted(_plan_for(inp, 45, 135), need=10**9, provider="gemini")
    holder = {}

    def build():
        holder["eng"] = RealEditPlannerEngine(gw)
        return holder["eng"]

    monkeypatch.setattr(worker, "_build_engine", build)
    job = {"job_id": "J9", "status": "queued", "operation_type": _jobs.OP_EDIT_PLAN,
           "request_ref": {"staging_prefix": "jobs/J9/", "sheet_order": "[]"}}
    s = Store(job, env)
    assert worker._run_one(s, "J9") == "failed:invalid_after_repair"
    assert s.failed[0] == "invalid_after_repair" and "truncated" in s.failed[1]
    assert s.diag["truncation_recovery"] == "failed" and len(s.diag["provider_attempts"]) == 2
    assert holder["eng"].deadline_ts and holder["eng"].deadline_ts > time.time() + 300
