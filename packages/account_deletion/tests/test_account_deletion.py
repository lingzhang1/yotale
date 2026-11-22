"""Account deletion core (D1): state machine, phases, verification, replay, CLI. Fakes only; no AWS."""
from __future__ import annotations

import account_deletion.config as C
import pytest
from account_deletion import RequestStore, Worker, receipt_hash, replay_after_restore
from account_deletion.cli import main as cli_main
from account_deletion.fakes import FakeCognito, FakeDDB, FakeS3
from account_deletion.request_store import LeaseLost
from account_deletion.targets import DeleteIncomplete

A, B = "uid-a", "uid-b"
SUB_A, SUB_B = "sub-a", "sub-b"
T0 = 1_800_000_000


def S(v):
    return {"S": v}


def N(v):
    return {"N": str(v)}


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Env:
    def __init__(self, page_size=2):
        self.cfg = C.fake_config()
        self.ddb = FakeDDB(page_size=page_size)
        self.s3 = FakeS3(page_size=page_size)
        self.cognito = FakeCognito()
        self.clock = Clock()
        self.metrics: list[dict] = []
        self.logs: list[dict] = []
        self.store = RequestStore(self.ddb, self.cfg)
        for uid, sub, email in ((A, SUB_A, "a@example.com"), (B, SUB_B, "b@example.com")):
            self.seed_account(uid, sub, email)

    def worker(self, **kw):
        return Worker(self.cfg, self.ddb, self.s3, self.cognito, clock=self.clock,
                      emit=lambda m, d=None: self.metrics.append(m), log=self.logs.append, **kw)

    def seed_account(self, uid, sub, email):
        d, mb, sb = self.ddb, self.cfg.media_bucket, self.cfg.staging_bucket
        self.cognito.add(email, sub)
        d.put("users", {"story_user_id": S(uid), "cognito_sub": S(sub), "account_status": S("active"),
                        "verified_email": S(email)})
        d.put("claims", {"claim_key": S(f"cognito#{sub}"), "story_user_id": S(uid)})
        for i in range(3):
            d.put("media", {"story_user_id": S(uid), "cloud_media_id": S(f"cm{i}")})
            self.s3.seed(mb, f"media/{uid}/cm{i}/original")
        d.put("media", {"story_user_id": S(uid), "cloud_media_id": S("evidence#m1")})
        self.s3.seed(mb, f"evidence/{uid}/blob1/frames.pack")
        self.s3.seed_upload(mb, f"media/{uid}/cm9/original", f"up-{uid}")
        for i in range(5):
            d.put("stories", {"story_user_id": S(uid), "story_id": S(f"s{i}")})
        d.put("understanding", {"story_user_id": S(uid), "moment_id": S("m1")})
        d.put("understanding", {"story_user_id": S(uid), "moment_id": S("__music_favorites__")})
        tok, orig, orphan = f"tok-{uid}", f"txn-{uid}", f"txn-orphan-{uid}"
        d.put("usage", {"story_user_id": S(uid), "quota_period": S("billing#account"), "b_apple_token": S(tok)})
        d.put("usage", {"story_user_id": S(uid), "quota_period": S("billing#entitlement"), "b_orig_txn": S(orig)})
        d.put("usage", {"story_user_id": S(uid), "quota_period": S("billing#m#m1~x"), "b_state": S("settled")})
        d.put("usage", {"story_user_id": S(uid), "quota_period": S("2026-11")})
        d.put("usage", {"story_user_id": S("__apple_token__"), "quota_period": S(f"billing#token#{tok}"), "b_uid": S(uid)})
        d.put("usage", {"story_user_id": S("__apple_txn__"), "quota_period": S(f"billing#txn#{orig}"), "b_uid": S(uid)})
        # bound by submit_transaction but returned not_active: the entitlement never mentions it (design 2.2)
        d.put("usage", {"story_user_id": S("__apple_txn__"), "quota_period": S(f"billing#txn#{orphan}"), "b_uid": S(uid)})
        d.put("ratelimits", {"story_user_id": S(uid), "rl_key": S("writes#1")})
        for j, st in ((f"job-q-{uid}", "queued"), (f"job-c-{uid}", "completed")):
            d.put("jobs", {"job_id": S(j), "owner": S(uid), "status": S(st)})
            self.s3.seed(sb, f"jobs/{j}/body.json")
            self.s3.seed(sb, f"jobs/{j}/sheets/m1.jpg")

    def accept(self, uid=A, rid="req-a", secret="secret-a"):
        return self.store.accept(uid, rid, receipt_hash(secret), int(self.clock()))

    def req(self, uid=A):
        return self.store.get(uid)

    def remaining(self, uid):
        d, out = self.ddb, {}
        for t, pk in (("media", "story_user_id"), ("stories", "story_user_id"), ("understanding", "story_user_id"),
                      ("usage", "story_user_id"), ("ratelimits", "story_user_id")):
            out[t] = sum(1 for it in d.tables[t].values() if it[pk]["S"] == uid)
        out["bindings"] = sum(1 for it in d.tables["usage"].values() if it.get("b_uid", {}).get("S") == uid)
        out["jobs"] = sum(1 for it in d.tables["jobs"].values() if it["owner"]["S"] == uid)
        out["s3"] = len(self.s3.keys(self.cfg.media_bucket, f"media/{uid}/")) + \
            len(self.s3.keys(self.cfg.media_bucket, f"evidence/{uid}/"))
        out["staging"] = len([k for k in self.s3.keys(self.cfg.staging_bucket) if uid in k])
        out["uploads"] = sum(1 for k in self.s3.uploads.get(self.cfg.media_bucket, {}).values() if f"/{uid}/" in k)
        return out

    def run_until_quiet(self, w, max_runs=20):
        for _ in range(max_runs):
            res = w.run(f"run-{self.clock.t}")
            if not res["due"]:
                return
        raise AssertionError("never went quiet")


ZERO = {"media": 0, "stories": 0, "understanding": 0, "usage": 0, "ratelimits": 0, "bindings": 0, "jobs": 0,
        "s3": 0, "staging": 0, "uploads": 0}


def drive_to_completion(env, w):
    for _ in range(12):
        env.run_until_quiet(w)
        r = env.req()
        if r["state"] == C.STATE_COMPLETED:
            return
        env.clock.t = max(env.clock.t, int(r["next_run_at"]))
    raise AssertionError(f"not completed: {env.req()}")


# ---- full lifecycle ----------------------------------------------------------------------------------------
def test_full_lifecycle_deletes_everything_for_a_and_nothing_for_b():
    env = Env()
    before_b = env.remaining(B)
    assert env.accept().outcome == "accepted"
    assert env.ddb.tables["users"][(A, "")]["account_status"]["S"] == "deleting"
    w = env.worker()
    env.run_until_quiet(w)
    r = env.req()
    assert r["phase"] == "wait" and r["next_run_at"] == r["not_before"] == T0 + C.NOT_BEFORE_DELAY_S
    assert env.cognito.users["a@example.com"]["enabled"] is False          # quiesced via the ListUsers fallback
    assert env.cognito.users["a@example.com"]["signed_out"] == 1
    assert env.ddb.tables["jobs"][(f"job-q-{A}", "")]["status"]["S"] == "cancel_requested"
    left = env.remaining(A)
    assert left["media"] == left["stories"] == left["understanding"] == left["usage"] == left["bindings"] == 0
    assert left["s3"] == left["uploads"] == 0 and left["jobs"] == 2       # jobs wait for verification

    # nothing runs before not_before, even when the scheduler fires
    env.clock.t += 60
    assert env.worker().run("early")["due"] == 0

    drive_to_completion(env, w)
    r = env.req()
    assert r["state"] == C.STATE_COMPLETED and r["phase"] == "final_check" and r["clean_passes"] == 2
    assert env.remaining(A) == ZERO
    assert "a@example.com" not in env.cognito.users
    u = env.ddb.tables["users"][(A, "")]
    assert u["account_status"]["S"] == "deleted" and "cognito_sub" not in u and "verified_email" not in u
    assert (f"cognito#{SUB_A}", "") in env.ddb.tables["claims"]               # identity claim kept (8.13)
    assert env.remaining(B) == before_b and "b@example.com" in env.cognito.users
    assert {"AccountDeletionCompleted": 1} in env.metrics

    env.clock.t = int(r["final_check_at"])
    env.run_until_quiet(w)
    r = env.req()
    assert r["state"] == C.STATE_CLOSED and r["late_found"] == 0


def test_verification_needs_two_clean_passes_ten_minutes_apart():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    env.clock.t = int(env.req()["not_before"])
    env.run_until_quiet(w)                  # pass 1 finds the recorded jobs + staging -> not clean
    r = env.req()
    assert r["phase"] == "verify" and r["clean_passes"] == 0 and r["next_run_at"] == env.clock.t + C.VERIFY_SPACING_S
    env.clock.t = int(r["next_run_at"])
    env.run_until_quiet(w)
    assert env.req()["clean_passes"] == 1 and env.req()["phase"] == "verify"
    env.clock.t = int(env.req()["next_run_at"])
    env.run_until_quiet(w)
    assert env.req()["state"] == C.STATE_COMPLETED


# ---- acceptance boundary and receipt status ---------------------------------------------------------------
def test_accept_is_idempotent_and_conflicts_for_another_request_id():
    env = Env()
    assert env.accept().outcome == "accepted"
    assert env.accept().outcome == "idempotent"
    res = env.accept(rid="req-other", secret="other")
    assert res.outcome == "already_requested" and res.request["request_id"] == "req-a"
    assert env.store.status_by_receipt("req-other", "other") is None   # the losing pointer was never written


def test_accept_refuses_missing_or_inactive_users_row_and_writes_nothing():
    env = Env()
    env.ddb.tables["users"][(A, "")]["account_status"] = S("suspended")
    assert env.accept().outcome == "not_active"
    assert env.req() is None and env.store.status_by_receipt("req-a", "secret-a") is None
    assert env.store.accept("uid-missing", "r2", receipt_hash("s"), T0).outcome == "not_active"
    assert (("uid-missing", "")) not in env.ddb.tables["users"]


def test_accept_other_failure_raises_so_the_client_treats_it_as_unknown():
    env = Env()
    env.ddb.fail_next["transact_write_items"] = RuntimeError("ProvisionedThroughputExceeded")
    with pytest.raises(RuntimeError):
        env.accept()


def test_status_by_receipt_reveals_nothing_without_the_secret():
    env = Env()
    env.accept()
    assert env.store.status_by_receipt("req-a", "wrong") is None
    assert env.store.status_by_receipt("req-unknown", "secret-a") is None
    assert env.store.status_by_receipt("req-a", "secret-a") == {"state": "accepted", "completed_at": None}
    drive_to_completion(env, env.worker())
    assert env.store.status_by_receipt("req-a", "secret-a")["state"] == "completed"


# ---- lease and concurrency --------------------------------------------------------------------------------
def test_second_run_cannot_acquire_a_live_lease():
    env = Env()
    env.accept()
    assert env.store.acquire(A, "run-1", T0)
    assert not env.store.acquire(A, "run-2", T0 + 10)
    assert env.store.acquire(A, "run-2", T0 + C.LEASE_S + 1)     # expired lease: takeover


def test_stale_run_cannot_write_after_takeover():
    env = Env()
    env.accept()
    assert env.store.acquire(A, "run-1", T0)
    assert env.store.acquire(A, "run-2", T0 + C.LEASE_S + 1)
    with pytest.raises(LeaseLost):
        env.store.advance(A, "run-1", T0 + C.LEASE_S + 2, 1, "content")
    with pytest.raises(LeaseLost):
        env.store.release(A, "run-1", T0 + C.LEASE_S + 2, 1, T0)
    assert env.req()["phase"] == "quiesce" and env.req()["lease_owner"] == "run-2"


def test_advance_is_monotonic_and_checks_phase_seq():
    env = Env()
    env.accept()
    env.store.acquire(A, "r", T0)
    with pytest.raises(ValueError):
        env.store.advance(A, "r", T0, 1, "billing")              # skipping a phase is refused
    env.store.advance(A, "r", T0, 1, "content")
    with pytest.raises(LeaseLost):
        env.store.advance(A, "r", T0, 1, "content")              # a replay of the same advance fails


def test_concurrent_discovery_is_a_union():
    env = Env()
    env.accept()
    env.store.record_child(A, C.SK_JOB, "j1", T0)
    env.store.record_child(A, C.SK_JOB, "j2", T0)
    env.store.record_child(A, C.SK_JOB, "j1", T0 + 5)
    assert sorted(env.store.children(A, C.SK_JOB)) == ["j1", "j2"]


def test_quiesced_at_and_not_before_are_set_once():
    env = Env()
    env.accept()
    w = env.worker()
    env.store.acquire(A, "r", T0)
    env.store.advance(A, "r", T0, 1, "content", if_not_exists={"quiesced_at": N(T0), "not_before": N(T0 + 10)})
    env.store.release(A, "r", T0, 2, T0)
    env.ddb.tables["requests"][(A, "request")].update({"phase": S("quiesce"), "phase_seq": N(1)})   # simulate a re-run
    env.clock.t = T0 + 1000
    w.process(A, "r2", force=True)
    assert env.req()["not_before"] == T0 + 10


# ---- failures, retries, alerts -----------------------------------------------------------------------------
@pytest.mark.parametrize("phase", ["quiesce", "content", "billing", "ratelimit", "verify", "cognito", "finalize"])
def test_crash_in_any_phase_backs_off_and_converges(phase, monkeypatch):
    env = Env()
    env.accept()
    real = getattr(Worker, "_p_" + phase)
    calls = {"n": 0}

    def flaky(self, uid, req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(self, uid, req)

    monkeypatch.setattr(Worker, "_p_" + phase, flaky)
    w = env.worker()
    for _ in range(60):
        env.run_until_quiet(w)
        r = env.req()
        if r["state"] != C.STATE_ACTIVE:
            break
        if r.get("last_error_code") == "RuntimeError" and calls["n"] == 1:
            assert r["fail_count"] == 1 and r["phase"] == phase and r["next_run_at"] == env.clock.t + C.backoff_s(1)
        env.clock.t = int(r["next_run_at"])
    assert env.req()["state"] == C.STATE_COMPLETED and env.req()["fail_count"] == 0
    assert env.remaining(A) == ZERO


def test_crash_between_tombstone_and_completed_recovers(monkeypatch):
    env = Env()
    env.accept()
    w = env.worker()
    real_advance = RequestStore.advance
    state = {"armed": True}

    def advance(self, uid, run_id, now, seq, nxt, **kw):
        if nxt == "final_check" and state["armed"]:
            state["armed"] = False
            raise RuntimeError("crash after tombstone")
        return real_advance(self, uid, run_id, now, seq, nxt, **kw)

    monkeypatch.setattr(RequestStore, "advance", advance)
    with pytest.raises(RuntimeError):
        drive_to_completion(env, w)
    assert env.ddb.tables["users"][(A, "")]["account_status"]["S"] == "deleted"
    assert env.req()["phase"] == "finalize" and env.req()["state"] == C.STATE_ACTIVE
    env.ddb.tables["requests"][(A, "request")]["lease_until"] = N(0)   # the crashed run's lease expires
    env.run_until_quiet(w)
    assert env.req()["state"] == C.STATE_COMPLETED


def test_cognito_already_deleted_is_success():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    env.cognito.users.pop("a@example.com")
    env.clock.t = int(env.req()["not_before"])
    drive_to_completion(env, w)
    assert env.req()["state"] == C.STATE_COMPLETED


def test_waits_never_count_as_failures_and_backoff_schedule():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    assert env.req()["fail_count"] == 0
    assert [C.backoff_s(i) for i in range(1, 8)] == [300, 900, 1800, 3600, 7200, 21600, 21600]


def test_stall_alert_once_at_five_and_retries_continue(monkeypatch):
    env = Env()
    env.accept()
    monkeypatch.setattr(Worker, "_p_quiesce", lambda self, uid, req: (_ for _ in ()).throw(RuntimeError("x")))
    w = env.worker()
    for _ in range(8):
        w.run("r")
        env.clock.t = int(env.req()["next_run_at"])
    r = env.req()
    assert r["fail_count"] == 8 and r["state"] == C.STATE_ACTIVE
    assert env.metrics.count({"AccountDeletionStalled": 1}) == 1
    assert r["stalled_alerted_at"] > 0


def test_overdue_and_heartbeat_metrics():
    env = Env()
    env.accept()
    env.worker().run("r")
    assert env.metrics[0] == {"AccountDeletionHeartbeat": 1, "AccountDeletionOverdue": 0}
    env.clock.t += C.OVERDUE_S + 1
    env.worker().run("r2")
    hb = [m for m in env.metrics if "AccountDeletionHeartbeat" in m]
    assert hb[-1]["AccountDeletionOverdue"] == 1


def test_forced_resume_cannot_skip_the_delay():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    assert w.process(A, "operator", force=True) == "waiting"
    assert env.req()["phase"] == "wait"
    env.ddb.tables["requests"][(A, "request")].update({"phase": S("verify"), "phase_seq": N(6)})
    assert w.process(A, "operator2", force=True) == "waiting"
    assert env.req()["clean_passes"] == 0 and env.req()["next_run_at"] == env.req()["not_before"]


def test_budget_releases_for_the_next_run():
    env = Env()
    env.accept()
    w = env.worker(budget_s=0)
    assert w.process(A, "r") == "budget"
    r = env.req()
    assert r["phase"] == "quiesce" and r["lease_until"] == 0 and r["next_run_at"] <= env.clock.t


def test_s3_delete_error_fails_the_phase_instead_of_reporting_success():
    env = Env()
    env.accept()
    env.s3.fail_delete_keys.add(f"media/{A}/cm0/original")
    env.worker().run("r")
    r = env.req()
    assert r["phase"] == "content" and r["fail_count"] == 1 and r["last_error_code"] == "DeleteIncomplete"
    with pytest.raises(DeleteIncomplete):
        env.worker().targets.prefix(env.cfg.media_bucket, f"media/{A}/")


# ---- late writes (design 5.5) -------------------------------------------------------------------------------
def test_verification_removes_late_writes_across_jobs_staging_uploads_and_billing():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    d, mb, sb = env.ddb, env.cfg.media_bucket, env.cfg.staging_bucket
    # writers that resolved the owner before the flip and wrote afterwards:
    d.put("usage", {"story_user_id": S(A), "quota_period": S("2026-11")})                       # quota settle
    d.put("usage", {"story_user_id": S(A), "quota_period": S("billing#account"), "b_apple_token": S("tok-late")})
    d.put("usage", {"story_user_id": S("__apple_token__"), "quota_period": S("billing#token#tok-late"),
                    "b_uid": S(A)})
    d.put("jobs", {"job_id": S("job-late"), "owner": S(A), "status": S("queued")})              # after the scan
    env.s3.seed(sb, "jobs/job-late/body.json")
    env.s3.seed(mb, f"media/{A}/late/original")                                                  # late single PUT
    env.s3.seed_upload(mb, f"evidence/{A}/late/frames.pack", "up-late")
    env.clock.t = int(env.req()["not_before"])
    env.run_until_quiet(w)
    r = env.req()
    assert r["clean_passes"] == 0
    assert "job-late" in env.store.children(A, C.SK_JOB) and "token#tok-late" in env.store.children(A, C.SK_GKEY)
    assert env.remaining(A) == ZERO
    drive_to_completion(env, w)
    assert env.remaining(A) == ZERO and env.remaining(B)["jobs"] == 2


def test_final_check_reports_and_removes_a_straggler():
    env = Env()
    env.accept()
    w = env.worker()
    drive_to_completion(env, w)
    env.s3.seed(env.cfg.media_bucket, f"media/{A}/straggler/original")
    env.clock.t = int(env.req()["final_check_at"])
    env.run_until_quiet(w)
    assert env.req()["state"] == C.STATE_CLOSED and env.req()["late_found"] == 1
    assert {"AccountDeletionLateFound": 1} in env.metrics and env.remaining(A)["s3"] == 0


def test_token_bindings_are_deleted_before_transaction_bindings():
    env = Env()
    env.accept()
    order = []
    real = env.ddb.delete_item

    def spy(**kw):
        pk = kw["Key"].get("story_user_id", {}).get("S")
        if pk in (C.APPLE_TOKEN_PK, C.APPLE_TXN_PK):
            order.append(pk)
        return real(**kw)

    env.ddb.delete_item = spy
    env.run_until_quiet(env.worker())
    assert order == [C.APPLE_TOKEN_PK, C.APPLE_TXN_PK, C.APPLE_TXN_PK]


def test_another_accounts_binding_is_never_deleted():
    env = Env()
    # A's entitlement names a txn bound to B (a wrong or stale reference): it must survive.
    env.ddb.tables["usage"][(A, "billing#entitlement")]["b_orig_txn"] = S(f"txn-{B}")
    env.accept()
    env.run_until_quiet(env.worker())
    assert env.remaining(B)["bindings"] == 3


def test_finalize_never_creates_a_users_row():
    env = Env()
    env.accept()
    w = env.worker()
    env.run_until_quiet(w)
    env.ddb.tables["users"].pop((A, ""))
    drive_to_completion(env, w)
    assert (A, "") not in env.ddb.tables["users"]


def test_billing_off_account_with_only_a_token_binding():
    env = Env()
    d = env.ddb
    for k in [k for k in d.tables["usage"] if k[0] == A and k[1] != "billing#account"]:
        d.tables["usage"].pop(k)
    for k in [k for k, v in d.tables["usage"].items() if v.get("b_uid", {}).get("S") == A and "txn" in k[1]]:
        d.tables["usage"].pop(k)
    env.accept()
    drive_to_completion(env, env.worker())
    assert env.remaining(A) == ZERO


def test_billing_key_shapes_match_the_ledger():
    from billing import ledger
    assert C.APPLE_TXN_PK == ledger.APPLE_TXN_PK and C.APPLE_TOKEN_PK == ledger.APPLE_TOKEN_PK
    assert ledger.LIVE + "account" == C.BILLING_ACCOUNT_SK and ledger.LIVE + "entitlement" == C.BILLING_ENTITLEMENT_SK


def test_billing_ledger_bindings_are_discovered():
    """Bindings written by the REAL ledger code (not hand-seeded) are found and deleted."""
    from billing import BillingLedger
    from billing.fakes import FakeDDB as BillingFake
    env = Env()
    bf = BillingFake()
    led = BillingLedger(ddb=bf, table="usage", shadow=False)
    tok = led.get_or_create_apple_account_token(A)
    led.bind_apple_transaction("orig-real", A)
    for (pk, sk), it in bf.items.items():
        if pk in (A, C.APPLE_TOKEN_PK, C.APPLE_TXN_PK):
            env.ddb.put("usage", it)
    env.accept()
    env.run_until_quiet(env.worker())
    left = [k for k in env.ddb.tables["usage"] if k[1] in (f"billing#token#{tok}", "billing#txn#orig-real")]
    assert left == []


# ---- restore replay (design 5.8) ---------------------------------------------------------------------------
def _restore(env, src, dst):
    import copy
    env.ddb.add_table(dst, *env.ddb.schemas[src])
    env.ddb.tables[dst] = copy.deepcopy(env.ddb.tables[src])


def test_replay_after_restore_cleans_restored_tables_before_repoint():
    env = Env()
    _restore(env, "users", "users-snap")
    _restore(env, "usage", "usage-snap")             # snapshot taken before the deletion
    env.accept()
    drive_to_completion(env, env.worker())
    dry = replay_after_restore(env.cfg, env.ddb, restored_users="users-snap", restored_usage="usage-snap")
    assert not dry["clean"] and dry["users_tombstoned"] == 1 and dry["bindings"] == 3 and dry["usage_rows"] == 4
    assert env.ddb.tables["users-snap"][(A, "")]["account_status"]["S"] == "active"   # dry run wrote nothing
    real = replay_after_restore(env.cfg, env.ddb, restored_users="users-snap", restored_usage="usage-snap", dry=False)
    assert real["users_tombstoned"] == 1
    again = replay_after_restore(env.cfg, env.ddb, restored_users="users-snap", restored_usage="usage-snap")
    assert again["clean"]
    snap = env.ddb.tables["users-snap"][(A, "")]
    assert snap["account_status"]["S"] == "deleted" and "cognito_sub" not in snap
    assert any(k[0] == B for k in env.ddb.tables["usage-snap"])               # B untouched


def test_replay_sets_restored_row_deleting_for_an_unfinished_request():
    env = Env()
    _restore(env, "users", "users-snap")
    _restore(env, "usage", "usage-snap")
    env.accept()
    env.run_until_quiet(env.worker())                # mid-flight: phase wait
    rep = replay_after_restore(env.cfg, env.ddb, restored_users="users-snap", restored_usage="usage-snap", dry=False)
    assert rep["users_set_deleting"] == 1
    assert env.ddb.tables["users-snap"][(A, "")]["account_status"]["S"] == "deleting"
    assert replay_after_restore(env.cfg, env.ddb, restored_users="users-snap", restored_usage="usage-snap")["clean"]


# ---- operator CLI ------------------------------------------------------------------------------------------
def _cli(env, *args):
    base = ["--env", "test", "--account", "1", "--user-pool-id", "pool"]
    return cli_main(base + list(args), clients=(env.ddb, env.s3, env.cognito))


@pytest.fixture
def cli_env(monkeypatch):
    env = Env()
    monkeypatch.setattr(C.DeletionConfig, "for_env", classmethod(lambda cls, *a, **k: C.fake_config()))
    return env


def test_cli_count_is_read_only(cli_env, capsys):
    before = {t: dict(v) for t, v in cli_env.ddb.tables.items()}
    assert _cli(cli_env, "count", "--uid", A) == 0
    out = capsys.readouterr().out
    assert '"stories": 5' in out and '"bindings": 3' in out and '"jobs": 2' in out
    assert {t: dict(v) for t, v in cli_env.ddb.tables.items()} == before


def test_cli_mutations_require_confirm_env_and_identity_check(cli_env):
    with pytest.raises(SystemExit):
        _cli(cli_env, "request", "--uid", A, "--identity-checked")
    with pytest.raises(SystemExit):
        _cli(cli_env, "request", "--uid", A, "--confirm-env", "test")
    with pytest.raises(SystemExit):
        _cli(cli_env, "resume", "--uid", A)
    assert cli_env.req() is None


def test_cli_request_then_resume_uses_the_state_machine(cli_env, capsys):
    assert _cli(cli_env, "request", "--uid", A, "--identity-checked", "--confirm-env", "test") == 0
    assert '"outcome": "accepted"' in capsys.readouterr().out
    assert _cli(cli_env, "resume", "--uid", A, "--confirm-env", "test") == 0
    assert cli_env.req()["phase"] == "wait"
    _cli(cli_env, "status", "--uid", A)
    assert "receipt_hash" not in capsys.readouterr().out
