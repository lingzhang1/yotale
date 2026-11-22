"""The scheduled deletion worker (design rev 3, section 5.4).

Triggered only by a 5-minute EventBridge rule (D2). Each run scans the request table, and for every due request
acquires the conditional lease and runs ready phases one after another until a phase waits, a phase fails, or the
240 s budget is spent. There is no queue and no self-enqueue: the request item is the only source of truth.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config as C
from .request_store import LeaseLost, RequestStore, _n, _s, error_code
from .targets import Targets


def _default_emit(metrics: dict, dims: Optional[dict] = None) -> None:
    try:
        from observability import emit_metrics
        emit_metrics(metrics, dims or {})
    except Exception:  # noqa: BLE001 — metrics never break deletion
        pass


def _default_log(rec: dict) -> None:
    print(json.dumps(rec, default=str))


@dataclass
class Advance:
    sets: dict = field(default_factory=dict)
    if_not_exists: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)


@dataclass
class Wait:
    until: int
    sets: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)


@dataclass
class Close:
    sets: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)


class Worker:
    def __init__(self, cfg: C.DeletionConfig, ddb, s3, cognito, *, clock: Callable[[], float] = time.time,
                 emit: Callable = _default_emit, log: Callable = _default_log, budget_s: int = C.RUN_BUDGET_S):
        self.cfg, self.clock, self.emit, self.log, self.budget_s = cfg, clock, emit, log, budget_s
        self.store = RequestStore(ddb, cfg)
        self.targets = Targets(cfg, ddb, s3, cognito)

    def now(self) -> int:
        return int(self.clock())

    # ---- one scheduled run ----------------------------------------------------------------------------------
    def run(self, run_id: str) -> dict:
        started = self.clock()
        now = self.now()
        reqs = self.store.scan_requests()
        overdue = sum(1 for r in reqs if r.get("state") == C.STATE_ACTIVE
                      and int(r.get("accepted_at", now)) < now - C.OVERDUE_S)
        self.emit({"AccountDeletionHeartbeat": 1, "AccountDeletionOverdue": overdue})
        due = sorted((r for r in reqs if r.get("state") in (C.STATE_ACTIVE, C.STATE_COMPLETED)
                      and int(r.get("next_run_at", 0)) <= now), key=lambda r: int(r.get("next_run_at", 0)))
        outcomes: dict[str, str] = {}
        for r in due:
            if self.clock() - started >= self.budget_s:
                break
            outcomes[r["uid"]] = self.process(r["uid"], run_id, started=started)
        return {"due": len(due), "overdue": overdue, "outcomes": outcomes}

    def process(self, uid: str, run_id: str, *, force: bool = False, started: Optional[float] = None) -> str:
        """Lease one request and run ready phases. force=True (operator resume) ignores next_run_at only; the
        lease and every phase's own timing checks (not_before, verify spacing, final_check_at) still apply."""
        started = self.clock() if started is None else started
        if not self.store.acquire(uid, run_id, self.now(), force=force):
            return "busy_or_not_due"
        while True:
            req = self.store.get(uid)
            if not req or req.get("lease_owner") != run_id:
                return "lease_lost"
            seq, phase = int(req["phase_seq"]), req["phase"]
            if self.clock() - started >= self.budget_s:
                try:
                    self.store.release(uid, run_id, self.now(), seq, self.now())
                except LeaseLost:
                    pass
                return "budget"
            t0 = self.clock()
            try:
                res = getattr(self, "_p_" + phase)(uid, req)
            except LeaseLost:
                return "lease_lost"
            except Exception as e:  # noqa: BLE001 — counted, backed off, alerted; never swallowed silently
                code = error_code(e)
                try:
                    n, alert = self.store.fail(uid, run_id, self.now(), seq, int(req.get("fail_count", 0)), code,
                                               bool(req.get("stalled_alerted_at")))
                except LeaseLost:
                    return "lease_lost"
                self._log(req, phase, "failed", t0, error=code, fail_count=n)
                if alert:
                    self.emit({"AccountDeletionStalled": 1})
                return "failed"
            try:
                if isinstance(res, Advance):
                    nxt = C.PHASES[seq]   # PHASES[seq] is the phase after index seq-1
                    self.store.advance(uid, run_id, self.now(), seq, nxt, sets=res.sets,
                                       if_not_exists=res.if_not_exists)
                    self._log(req, phase, "done", t0, **res.counts)
                    continue
                if isinstance(res, Wait):
                    self.store.release(uid, run_id, self.now(), seq, res.until, sets=res.sets)
                    self._log(req, phase, "wait", t0, until=res.until, **res.counts)
                    return "waiting"
                self.store.release(uid, run_id, self.now(), seq, self.now(), sets=res.sets)
                self._log(req, phase, "closed", t0, **res.counts)
                return "closed"
            except LeaseLost:
                return "lease_lost"

    def _log(self, req, phase, outcome, t0, **extra):
        self.log({"msg": "account_deletion_phase", "request_id": req.get("request_id"), "phase": phase,
                  "outcome": outcome, "ms": int((self.clock() - t0) * 1000), **extra})

    # ---- phases (design 5.4 table) -------------------------------------------------------------------------
    def _sub(self, uid) -> Optional[str]:
        u = self.targets.user(uid) or {}
        return (u.get("cognito_sub") or {}).get("S")

    def _p_quiesce(self, uid, req):
        now = self.now()
        cognito = self.targets.cognito_quiesce(self._sub(uid))
        cancelled = self._discover_jobs(uid, now)
        return Advance(if_not_exists={"quiesced_at": _n(now), "not_before": _n(now + C.NOT_BEFORE_DELAY_S)},
                       counts={"cognito": cognito, "jobs_cancelled": cancelled})

    def _discover_jobs(self, uid, now) -> int:
        cancelled = 0
        for job_id, status in self.targets.scan_jobs(uid):
            self.store.record_child(uid, C.SK_JOB, job_id, now)
            if status not in C.JOB_TERMINAL and status != "cancel_requested" and self.targets.cancel_job(job_id):
                cancelled += 1
        return cancelled

    def _p_content(self, uid, req):
        counts = self.targets.media_objects(uid)
        counts.update(self.targets.content_partitions(uid))
        return Advance(counts=counts)

    def _discover_billing(self, uid, now) -> list[str]:
        for g in self.targets.billing_identifiers(uid):
            self.store.record_child(uid, C.SK_GKEY, g, now)
        return self.store.children(uid, C.SK_GKEY)

    def _p_billing(self, uid, req):
        gkeys = self._discover_billing(uid, self.now())
        bindings = self.targets.bindings(uid, gkeys)   # token bindings first, then transactions
        usage = self.targets.usage_partition(uid)      # only after the global keys are recorded and removed
        return Advance(counts={"bindings": bindings, "usage_rows": usage})

    def _p_ratelimit(self, uid, req):
        return Advance(counts={"rate_limit_rows": self.targets.rate_limits(uid)})

    def _p_wait(self, uid, req):
        nb = int(req["not_before"])
        return Wait(nb) if self.now() < nb else Advance()

    def verification_pass(self, uid: str) -> dict:
        """One pass of design 5.5. Returns per-store counts of what was FOUND (and deleted)."""
        now = self.now()
        c: dict = {"jobs_cancelled": self._discover_jobs(uid, now)}
        c["jobs"] = sum(self.targets.job(j, uid) for j in self.store.children(uid, C.SK_JOB))
        c["bindings"] = self.targets.bindings(uid, self._discover_billing(uid, now))
        c["usage_rows"] = self.targets.usage_partition(uid)
        c.update(self.targets.content_partitions(uid))
        c["rate_limit_rows"] = self.targets.rate_limits(uid)
        c.update(self.targets.media_objects(uid))
        return c

    @staticmethod
    def _found(counts: dict) -> int:
        return sum(v for k, v in counts.items() if isinstance(v, int) and k != "jobs_cancelled")

    def _p_verify(self, uid, req):
        now, nb = self.now(), int(req["not_before"])
        if now < nb:                      # a resumed or forced run can never skip the delay
            return Wait(nb)
        counts = self.verification_pass(uid)
        found = self._found(counts)
        clean = int(req.get("clean_passes", 0)) + 1 if found == 0 else 0
        counts["found"] = found
        if clean >= C.CLEAN_PASSES_REQUIRED:
            return Advance(sets={"clean_passes": _n(clean)}, counts=counts)
        return Wait(now + C.VERIFY_SPACING_S, sets={"clean_passes": _n(clean)}, counts=counts)

    def _p_cognito(self, uid, req):
        return Advance(counts={"cognito": self.targets.cognito_delete(self._sub(uid))})

    def _p_finalize(self, uid, req):
        now = self.now()
        result = self.targets.tombstone(uid, req["request_id"], now)
        if result == "not_deleting":
            raise RuntimeError("users_row_not_deleting")   # never tombstone an account that is not being deleted
        completed_at = int(req.get("completed_at") or now)
        self.emit({"AccountDeletionCompleted": 1})
        return Advance(sets={"state": _s(C.STATE_COMPLETED), "next_run_at": _n(completed_at + C.FINAL_CHECK_DELAY_S),
                             "final_check_at": _n(completed_at + C.FINAL_CHECK_DELAY_S)},
                       if_not_exists={"completed_at": _n(now)}, counts={"users_row": result})

    def _p_final_check(self, uid, req):
        now, due = self.now(), int(req["final_check_at"])
        if now < due:
            return Wait(due)
        counts = self.verification_pass(uid)
        found = self._found(counts)
        if found:
            self.emit({"AccountDeletionLateFound": found})
        return Close(sets={"state": _s(C.STATE_CLOSED), "late_found": _n(found), "closed_at": _n(now)}, counts=counts)


def handler(event, context):  # pragma: no cover — wired in D2; exercised through Worker in tests
    import boto3
    cfg = C.DeletionConfig.from_environ()
    w = Worker(cfg, boto3.client("dynamodb", region_name=cfg.region), boto3.client("s3", region_name=cfg.region),
               boto3.client("cognito-idp", region_name=cfg.region))
    return w.run(getattr(context, "aws_request_id", "local"))
