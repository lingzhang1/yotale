"""Billing V1 enforcement wiring: modes (off | observe | enforce), the two meters, typed 402 errors, the fail-closed
store policy, the entitlement read model, the controlled refund, worker settlement, and NO-BYPASS route coverage."""
from __future__ import annotations

import io
import json
import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PIL import Image

from app import billing_gate, quota_gate
from app.auth import CognitoConfig, CognitoJwtVerifier, IdentityStore
from app.deps import get_asset_understanding_engine
from app.main import create_app
from app.throttle import CLASS_POLICIES, ROUTE_CLASS
from asset_engine import DEFAULT_AU_MODEL, RealAssetUnderstandingEngine
from billing import BillingConfig, BillingLedger, PlanLimits
from billing.fakes import FakeDDB
from model_gateway import FakeModelGateway, ProviderError
from user_quota import QuotaConfig, UserQuota
from user_quota.fakes import FakeDDB as QuotaFakeDDB

REGION, POOL, CLIENT_ID = "us-east-1", "us-east-1_TESTPOOL", "testclientid123"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}"
T0 = 1_800_000_000


def _make_key(kid="kidA"):
    import jwt.algorithms
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return key, jwk


KEY, JWK = _make_key()


def _auth(sub="u1"):
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iss": ISSUER, "token_use": "access", "client_id": CLIENT_ID,
                      "iat": now, "exp": now + 3600}, KEY, algorithm="RS256", headers={"kid": "kidA"})
    return {"Authorization": f"Bearer {tok}"}


class FakeVerifier(CognitoJwtVerifier):
    def __init__(self):
        super().__init__(CognitoConfig(region=REGION, user_pool_id=POOL, app_client_id=CLIENT_ID))

    def _fetch_jwks(self):
        return {"keys": [JWK]}


class FakeIdentity(IdentityStore):
    def __init__(self):
        super().__init__(claims_table="t", users_table="u")

    def resolve(self, cognito_sub, *, verified_email=None):
        return f"story-{cognito_sub}"


class JobStore:
    """Async-job store double that records terminalisation, like the real store."""
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.enqueued: list[str] = []

    def stage_request(self, job_id, body_json, sheets):
        return f"jobs/{job_id}/"

    def create_or_get(self, *, operation_id, owner, approach, critique_requested, staging_prefix, sheet_order,
                      payload_fingerprint, has_body=True):
        import edit_plan_jobs as _jobs
        jid = _jobs.job_id_for(operation_id)
        created = jid not in self.jobs
        if created:
            self.jobs[jid] = {"job_id": jid, "operation_id": operation_id, "owner": owner, "status": "queued"}
        return jid, created

    def enqueue(self, job_id):
        self.enqueued.append(job_id)

    def deny(self, job_id, category, detail=""):
        self.jobs[job_id].update(status="failed", failure_category=category)
        return True

    def delete_staging(self, prefix):
        pass

    def get(self, job_id):
        return self.jobs.get(job_id)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k, v in {"STORY_ENVIRONMENT": "beta", "STORY_COGNITO_USER_POOL_ID": POOL, "STORY_COGNITO_APP_CLIENT_ID": CLIENT_ID,
                 "STORY_EPIDEMIC_MODE": "prototyping", "STORY_QUOTA_MODE": "observe",
                 "STORY_THROTTLE_MODE": "observe"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("STORY_USER_USAGE_TABLE", raising=False)
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)


class Rig:
    def __init__(self, mode, cfg=None, quota=None):
        self.ddb, self.t = FakeDDB(), [T0]
        clock = lambda: self.t[0]  # noqa: E731
        cfg = cfg or BillingConfig()
        self.live = BillingLedger(ddb=self.ddb, table="t", cfg=cfg, clock=clock)
        self.shadow = BillingLedger(ddb=self.ddb, table="t", cfg=cfg, shadow=True, clock=clock)
        os.environ["STORY_BILLING_MODE"] = mode
        self.app = create_app()
        self.app.state._jwt_verifier_override = FakeVerifier()
        self.app.state._identity_store_override = FakeIdentity()
        self.app.state._billing_ledger_override = {"observe": self.shadow, "enforce": self.live}
        self.store = JobStore()
        self.app.state._job_store_override = self.store
        if quota is not None:
            self.app.state._user_quota = quota
        self.c = TestClient(self.app)

    def submit(self, op, sub="u1"):
        body = json.dumps({"story_id": "11111111-1111-4111-8111-111111111111",
                           "creative_intent_id": "22222222-2222-4222-8222-222222222222",
                           "creative_intent": {}, "moments": []})
        return self.c.post("/v1/edit-plan-jobs", headers=_auth(sub),
                           data={"operation_id": op, "body": body, "sheet_order": "[]"})


uid = "story-u1"


# ---- video credits through the async submit route ---------------------------------------------------------------

def test_enforce_allows_the_free_allowance_then_returns_a_typed_402_and_terminalises_the_job():
    r = Rig("enforce")
    assert r.submit("a").status_code == 202 and r.submit("b").status_code == 202
    third = r.submit("c")
    assert third.status_code == 402
    body = third.json()
    assert body["error"] == "video_credits_exhausted" and body["action"] == "subscribe"
    assert body["contract_version"] == 3
    assert body["entitlement"]["videos"] == {"total": 2, "used": 0, "reserved": 2, "remaining": 0}
    assert len(r.store.enqueued) == 2                                       # the denied job was never enqueued
    denied_job = [j for j in r.store.jobs.values() if j["status"] == "failed"]
    assert len(denied_job) == 1 and denied_job[0]["failure_category"] == "billing_denied"   # so reconcile cannot run it


def test_duplicate_submit_does_not_charge_twice():
    r = Rig("enforce")
    assert r.submit("a").status_code == 202
    assert r.submit("a").status_code == 202                                  # client retry: recovered, created=False
    e = r.live.get_entitlement(uid)
    assert (e.v_resv, e.v_avail) == (1, 1)


def test_off_mode_touches_nothing():
    r = Rig("off")
    for i in range(5):
        assert r.submit(f"op{i}").status_code == 202
    assert r.ddb.writes == 0


def test_observe_mode_never_denies_and_never_debits_the_live_ledger():
    r = Rig("observe")
    for i in range(4):
        assert r.submit(f"op{i}").status_code == 202                         # 2 over the allowance: still allowed
    assert r.live.get_entitlement(uid) is None                               # no customer-visible state
    s = r.shadow.get_entitlement(uid)
    assert (s.v_resv, s.v_avail) == (2, 0)                                   # shadow shows what WOULD have happened
    assert len(r.store.enqueued) == 4


def test_legacy_or_missing_usage_table_is_inert(monkeypatch):
    r = Rig("enforce")
    r.app.state._billing_ledger_override = None
    monkeypatch.delenv("STORY_USER_USAGE_TABLE", raising=False)
    assert r.submit("a").status_code == 202                                  # unprovisioned env: no gate, no crash


def test_store_outage_fails_closed_in_enforce_and_open_in_observe():
    class Boom(FakeDDB):
        def transact_write_items(self, TransactItems):
            raise RuntimeError("down")

    for mode, expected in (("enforce", 503), ("observe", 202)):
        r = Rig(mode)
        boom = BillingLedger(ddb=Boom(), table="t", shadow=(mode == "observe"), clock=lambda: T0)
        r.app.state._billing_ledger_override = {mode: boom}
        resp = r.submit("a")
        assert resp.status_code == expected
        if mode == "enforce":
            assert resp.json()["error"] == "billing_unavailable"


def test_operational_quota_denial_after_a_billing_hold_releases_the_hold_and_the_job():
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="t",
                  cfg=QuotaConfig(user_monthly_usd=5, user_daily_gens=40, max_active_jobs=1, global_monthly_usd=60))
    os.environ["STORY_QUOTA_MODE"] = "enforce"
    r = Rig("enforce", quota=q)
    assert r.submit("a").status_code == 202
    second = r.submit("b")
    assert second.status_code == 429 and second.json()["error"] == "quota_exceeded"      # 429 stays operational
    e = r.live.get_entitlement(uid)
    assert (e.v_resv, e.v_avail) == (1, 1)                                   # only the first job holds a credit
    assert any(j["failure_category"] == "quota_denied" for j in r.store.jobs.values() if j["status"] == "failed")


# ---- Moment analysis through the AU route -----------------------------------------------------------------------

_GOOD = {
    "observed": {"summary": "A quiet meal.", "subjects": ["meal"],
                 "events": [{"start_time": 0.0, "end_time": 20.0, "description": "eating"}],
                 "temporal_order_note": "sustained", "useful_segments": [{"start_time": 0.0, "end_time": 20.0, "why_useful": "calm"}]},
    "story_context": {"story_utility": "strong_elsewhere", "requested_shot_contribution": "fulfilled",
                      "requested_beat_contribution": "serves beat_endofday"},
}


def _jpeg():
    b = io.BytesIO()
    Image.new("RGB", (24, 24), (90, 110, 130)).save(b, format="JPEG")
    return b.getvalue()


def _au(c, moment, sub="u1"):
    files = [("frames", (f"f{i}.jpg", _jpeg(), "image/jpeg")) for i in range(24)]
    fmeta = json.dumps([{"t_ms": i * 100} for i in range(24)])
    return c.post("/v1/asset-understanding", headers=_auth(sub),
                  data={"meta": json.dumps({"moment_id": moment}), "frames_meta": fmeta}, files=files)


def _mid(i):
    return f"00000000-0000-4000-8000-{i:012d}"


def _au_rig(mode, gateway=None, moments=3):
    r = Rig(mode, cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=moments)))
    engine = RealAssetUnderstandingEngine(gateway or FakeModelGateway(response=_GOOD), model_id=DEFAULT_AU_MODEL)
    r.app.dependency_overrides[get_asset_understanding_engine] = lambda: engine
    return r


def test_au_charges_unique_new_moments_only_and_reuse_is_free():
    r = _au_rig("enforce")
    assert _au(r.c, _mid(1)).status_code == 200
    assert _au(r.c, _mid(1)).status_code == 200                              # same moment again: cache/retry/re-analysis
    e = r.live.get_entitlement(uid)
    assert (e.m_used, e.m_avail, e.m_resv) == (1, 2, 0)


def test_au_exhaustion_returns_402_but_already_analysed_moments_still_work():
    r = _au_rig("enforce")
    for i in range(3):
        assert _au(r.c, _mid(i)).status_code == 200
    blocked = _au(r.c, _mid(99))
    assert blocked.status_code == 402 and blocked.json()["error"] == "moment_allowance_exhausted"
    assert blocked.json()["entitlement"]["moments"]["remaining"] == 0
    assert _au(r.c, _mid(1)).status_code == 200                              # reuse is free even at zero remaining


def test_failed_analysis_never_spends_the_allowance():
    r = _au_rig("enforce", gateway=FakeModelGateway(error=ProviderError("boom")))
    assert _au(r.c, _mid(1)).status_code == 503
    e = r.live.get_entitlement(uid)
    assert (e.m_used, e.m_resv, e.m_avail) == (0, 0, 3)
    r.app.dependency_overrides[get_asset_understanding_engine] = lambda: RealAssetUnderstandingEngine(
        FakeModelGateway(response=_GOOD), model_id=DEFAULT_AU_MODEL)
    assert _au(r.c, _mid(1)).status_code == 200                              # a retry then charges exactly once
    assert r.live.get_entitlement(uid).m_used == 1


def test_au_observe_and_off_never_block():
    for mode in ("observe", "off"):
        r = _au_rig(mode, moments=1)
        for i in range(3):
            assert _au(r.c, _mid(i)).status_code == 200
        assert r.live.get_entitlement(uid) is None


def test_trial_expiry_is_a_typed_402_on_both_meters():
    r = _au_rig("enforce")
    r.live.reserve_video(uid, "seed")
    r.live.settle_video(uid, "seed")                                         # the first video starts the 14-day clock
    r.t[0] += 15 * 86400
    a = _au(r.c, _mid(2))
    s = r.submit("a")
    assert a.status_code == s.status_code == 402
    assert a.json()["error"] == s.json()["error"] == "trial_expired"


# ---- sync video routes (middleware) -----------------------------------------------------------------------------

def _sync_app(ledger, mode="enforce", status=200):
    os.environ["STORY_BILLING_MODE"] = mode
    app = FastAPI()
    app.state._billing_ledger_override = {mode: ledger}

    @app.post("/v1/edit-plan")
    def plan():
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=status, content={"ok": status < 300})

    app.middleware("http")(billing_gate.billing_middleware)

    class P:
        story_user_id = "story-u1"
        is_legacy = False

    @app.middleware("http")
    async def auth(request: Request, call_next):
        request.state.principal = P()
        return await call_next(request)

    return TestClient(app)


def test_sync_planner_route_settles_on_success_and_releases_on_failure():
    ddb = FakeDDB()
    L = BillingLedger(ddb=ddb, table="t", clock=lambda: T0)
    ok = _sync_app(L)
    assert ok.post("/v1/edit-plan").status_code == 200
    e = L.get_entitlement(uid)
    assert (e.v_used, e.v_resv, e.v_avail) == (1, 0, 1)
    bad = _sync_app(L, status=500)
    assert bad.post("/v1/edit-plan").status_code == 500
    e = L.get_entitlement(uid)
    assert (e.v_used, e.v_resv, e.v_avail) == (1, 0, 1)                      # failure returned its credit
    assert ok.post("/v1/edit-plan").status_code == 200
    assert ok.post("/v1/edit-plan").status_code == 402                       # allowance (2) exhausted


# ---- entitlement endpoint and refund ----------------------------------------------------------------------------

def test_entitlement_endpoint_contract_in_each_mode():
    off = Rig("off").c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert {k: v for k, v in off.items() if k not in ("offer", "capabilities")} == {"contract_version": 3, "billing_mode": "off", "enforced": False}
    assert off["capabilities"]["video_generation"] == "metered" and off["capabilities"]["subscription"]["status"] == "none"

    obs = Rig("observe").c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert obs["billing_mode"] == "observe" and obs["enforced"] is False and obs["plan"] == "free_starter"

    r = Rig("enforce")
    body = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert body["enforced"] is True and body["status"] == "free_starter"
    assert body["videos"]["remaining"] == 2 and body["moments"]["remaining"] == 30
    assert body["trial"] == {"state": "not_started", "started_at": None, "ends_at": None, "days": 14}
    assert body["upgrade"]["eligible"] is True
    import uuid
    assert uuid.UUID(body["apple_app_account_token"])                        # stable UUID for StoreKit appAccountToken
    assert r.c.get("/v1/billing/entitlement", headers=_auth()).json()["apple_app_account_token"] == body["apple_app_account_token"]
    assert r.c.get("/v1/billing/entitlement").status_code == 401             # authenticated only


def _completed(r, op):
    import edit_plan_jobs as _jobs
    scoped = f"{uid}\x1f{op}"
    jid = _jobs.job_id_for(scoped)
    r.store.jobs[jid].update(status="completed", plan={"segments": [{"asset_id": "a"}]})
    r.live.settle_video(uid, scoped)
    return jid, scoped


def test_refund_endpoint_only_for_a_completed_owned_job_with_evidence_and_only_once():
    r = Rig("enforce")
    assert r.submit("opR").status_code == 202
    refund = lambda sub="u1", **b: r.c.post("/v1/billing/video-refund", headers=_auth(sub), json=b)  # noqa: E731
    claim = dict(operation_id="opR", reason="render_failed", render_attempts=2)
    assert refund(**claim).status_code == 404                                             # job not completed yet
    jid, scoped = _completed(r, "opR")
    assert refund(operation_id="opR", reason="render_failed").status_code == 422          # no evidence of a re-render
    assert refund(operation_id="opR", reason="looks_ugly", render_attempts=2).status_code == 422   # creative reasons do not exist
    assert refund(operation_id="opR", reason="render_failed", render_attempts=1).json()["result"] == "not_eligible:insufficient_evidence"
    ok = refund(**claim, client_build="1.0(7)")
    assert ok.status_code == 200 and ok.json()["result"] == "refunded"
    assert ok.json()["entitlement"]["videos"]["remaining"] == 2
    assert refund(**claim).json()["result"] == "noop"
    assert refund("someone-else", **claim).status_code == 404                              # another account never learns the job exists


def test_a_refund_never_deletes_or_invalidates_the_output_and_resubmitting_costs_nothing():
    r = Rig("enforce")
    r.submit("opR")
    jid, scoped = _completed(r, "opR")
    before = dict(r.store.jobs[jid])
    enq = len(r.store.enqueued)
    res = r.c.post("/v1/billing/video-refund", headers=_auth(), json=dict(operation_id="opR", reason="export_failed", render_attempts=3))
    assert res.json()["result"] == "refunded"
    assert r.store.jobs[jid] == before                                                    # the generated plan and job are untouched
    again = r.submit("opR")                                                               # the client re-renders / re-submits the SAME operation
    assert again.status_code == 202 and again.json()["job_id"] == jid
    assert len(r.store.enqueued) == enq                                                   # no new AI work was queued
    e = r.live.get_entitlement(uid)
    assert (e.v_used, e.v_resv, e.v_avail) == (0, 0, 2)                                   # and no second charge


def test_refund_is_a_noop_when_the_operation_was_never_billed():
    r = Rig("observe")                                                                     # shadow only: nothing live was charged
    r.submit("opR")
    import edit_plan_jobs as _jobs
    r.store.jobs[_jobs.job_id_for(f"{uid}\x1fopR")].update(status="completed")
    res = r.c.post("/v1/billing/video-refund", headers=_auth(), json=dict(operation_id="opR", reason="render_failed", render_attempts=2))
    assert res.status_code == 200 and res.json()["result"].startswith("not_eligible:")     # shadow ledger: nothing settled
    assert r.live.get_entitlement(uid) is None                                            # and nothing live exists to refund


def test_refund_in_off_mode_does_nothing():
    r = Rig("off")
    r.submit("opR")
    res = r.c.post("/v1/billing/video-refund", headers=_auth(), json=dict(operation_id="opR", reason="render_failed", render_attempts=2))
    assert res.json() == {"result": "billing_off", "billing_mode": "off"}


# ---- NO-BYPASS route coverage -----------------------------------------------------------------------------------

def test_every_paid_route_is_explicitly_billed_or_exempt():
    paid = {k for k, cls in ROUTE_CLASS.items() if cls in quota_gate.PAID_CLASSES}
    billed, exempt = set(billing_gate.BILLED_ROUTES), set(billing_gate.BILLING_EXEMPT)
    assert not (billed & exempt), "a route cannot be both billed and exempt"
    assert paid == billed | exempt, f"unclassified paid routes: {sorted(paid - billed - exempt)}; stale: {sorted((billed | exempt) - paid)}"


def test_billed_routes_exist_and_both_planner_routes_are_gated():
    app = create_app()
    real = {(m, r.path) for r in app.routes for m in (getattr(r, "methods", None) or [])}
    assert set(billing_gate.BILLED_ROUTES) <= real
    for route in (("POST", "/v1/edit-plan"), ("POST", "/v1/edit-plan-mm")):
        assert billing_gate.BILLED_ROUTES[route] == "video"
        assert route in billing_gate._SYNC_VIDEO                             # covered by the middleware
    assert billing_gate.BILLED_ROUTES[("POST", "/v1/edit-plan-jobs")] == "video"   # covered in the submit handler
    assert billing_gate.BILLED_ROUTES[("POST", "/v1/asset-understanding")] == "moment"


def test_billing_denial_status_is_402_never_the_operational_429():
    assert billing_gate.denial_response.__doc__ and "402" in billing_gate.denial_response.__doc__


# ---- worker settlement ------------------------------------------------------------------------------------------

def test_worker_settles_completed_jobs_and_releases_the_rest_idempotently(monkeypatch):
    from app import worker
    ddb = FakeDDB()
    L = BillingLedger(ddb=ddb, table="t", clock=lambda: T0)
    monkeypatch.setattr(worker, "_billing_ledger", lambda: L)
    L.reserve_video(uid, "done")
    L.reserve_video(uid, "bad")
    worker._billing_finish_job({"owner": uid, "operation_id": "done"}, completed=True)
    worker._billing_finish_job({"owner": uid, "operation_id": "done"}, completed=True)      # SQS redelivery
    worker._billing_finish_job({"owner": uid, "operation_id": "bad"}, completed=False)
    e = L.get_entitlement(uid)
    assert (e.v_used, e.v_resv, e.v_avail) == (1, 0, 1)
    worker._billing_finish_job({"owner": "dev", "operation_id": "x"}, completed=True)       # legacy dev job: ignored
    worker._billing_finish_job({"owner": uid, "operation_id": "coverage-op"}, completed=False)  # no reservation: no-op
    assert L.get_entitlement(uid).v_used == 1


def test_worker_ledger_is_off_without_mode_or_table(monkeypatch):
    from app import worker
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)
    assert worker._billing_ledger() is None
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    monkeypatch.delenv("STORY_USER_USAGE_TABLE", raising=False)
    assert worker._billing_ledger() is None


# ---- startup validation ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["enforced", "ON", "true", ""])
def test_application_startup_fails_on_an_invalid_billing_mode(monkeypatch, bad):
    from billing import BillingConfigError
    monkeypatch.setenv("STORY_BILLING_MODE", bad)
    with pytest.raises(BillingConfigError):
        create_app()


def test_application_startup_accepts_unset_and_valid_modes_and_rejects_the_removed_override(monkeypatch):
    from billing import BillingConfigError
    for ok in (None, "off", "observe", "enforce"):
        if ok is None:
            monkeypatch.delenv("STORY_BILLING_MODE", raising=False)
        else:
            monkeypatch.setenv("STORY_BILLING_MODE", ok)
        create_app()
    monkeypatch.setenv("STORY_BILLING_PLANS_JSON", "{}")
    with pytest.raises(BillingConfigError):
        create_app()


def test_worker_handler_fails_loudly_on_an_invalid_billing_mode(monkeypatch):
    from billing import BillingConfigError
    from app import worker
    monkeypatch.setenv("STORY_BILLING_MODE", "enforced")
    with pytest.raises(BillingConfigError):
        worker.handler({"Records": []}, None)


# ---- observe mode: provably shadow-only --------------------------------------------------------------------------

def test_observe_mode_writes_only_shadow_items_plus_the_identity_token_and_never_blocks_a_customer():
    r = Rig("observe")
    for i in range(5):                                                       # well past the 2-video allowance
        assert r.submit(f"op{i}").status_code == 202
    assert r.c.get("/v1/billing/entitlement", headers=_auth()).status_code == 200
    mine = sorted(sk for (pk, sk) in r.ddb.items if pk == uid)
    live = [sk for sk in mine if sk.startswith("billing#")]
    shadow = [sk for sk in mine if sk.startswith("billing-shadow#")]
    assert live == ["billing#account"]                    # the ONLY live write: the stable Apple appAccountToken (identity, not usage)
    assert "billing-shadow#entitlement" in shadow
    assert len([sk for sk in shadow if sk.startswith("billing-shadow#v#")]) == 2    # 2 held; the 3 over-allowance submits would-deny
    assert r.live.get_entitlement(uid) is None            # no live counters, no live trial clock, no live reservations
    assert r.shadow.get_entitlement(uid).v_resv == 2      # the shadow ledger shows the hypothetical decision (2 held, 3 would-deny)


def test_off_mode_performs_no_billing_reads_or_writes_at_all():
    r = Rig("off")
    for i in range(3):
        assert r.submit(f"op{i}").status_code == 202
    body = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert {k: v for k, v in body.items() if k not in ("offer", "capabilities")} == {"contract_version": 3, "billing_mode": "off", "enforced": False}   # `offer`/`capabilities` are static, not a read     # not even the token record is created
    assert r.ddb.writes == 0 and not [k for k in r.ddb.items if k[0] == uid]


# ---- worker pre-run authorization (closes the crash window between the job row and the reservation) -------------------

class _StubStore:
    def __init__(self, job):
        self.job, self.failed, self.deleted, self.work_started = job, [], [], False

    def claim_lease(self, job_id):
        return "tok"

    def load_request(self, prefix, order):
        self.work_started = True
        raise AssertionError("model work must not start without authorization")

    def fail(self, job_id, category, detail, token=None, diagnostics=None):
        self.failed.append(category)
        return True

    def delete_staging(self, prefix):
        self.deleted.append(prefix)


def _job(op="op-w"):
    return {"job_id": "j", "owner": uid, "operation_id": f"{uid}\x1f{op}", "status": "queued", "operation_type": "edit_plan",
            "request_ref": {"staging_prefix": "p/", "sheet_order": "[]"}}


def test_a_job_with_no_reservation_is_authorised_by_reserving_now_when_the_entitlement_allows(monkeypatch):
    from app import worker
    L = BillingLedger(ddb=FakeDDB(), table="t", clock=lambda: T0)
    monkeypatch.setattr(worker, "_billing_ledger", lambda: L)
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    job = _job()
    assert worker._billing_authorize_job(job) == (True, "")                     # the crash-window job gets a reservation now
    assert L.get_entitlement(uid).v_resv == 1
    assert worker._billing_authorize_job(job) == (True, "")                     # SQS redelivery: idempotent, no second hold
    assert L.get_entitlement(uid).v_resv == 1


def test_an_unauthorised_job_never_starts_model_work_and_is_terminalised(monkeypatch):
    from app import worker
    L = BillingLedger(ddb=FakeDDB(), table="t", clock=lambda: T0, cfg=BillingConfig(free_starter=PlanLimits(videos=1, moments=1)))
    L.reserve_video(uid, "someone-else"); L.settle_video(uid, "someone-else")        # the only credit is gone
    monkeypatch.setattr(worker, "_billing_ledger", lambda: L)
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    store = _StubStore(_job())
    assert worker._run_edit_plan(store, "j", store.job) == "failed:billing_denied"
    assert store.failed == ["billing_denied"] and store.deleted == ["p/"] and store.work_started is False


def test_pre_run_authorization_is_inert_outside_enforce_and_for_legacy_jobs(monkeypatch):
    from app import worker
    L = BillingLedger(ddb=FakeDDB(), table="t", clock=lambda: T0)
    monkeypatch.setattr(worker, "_billing_ledger", lambda: L)
    for mode in ("off", "observe"):
        monkeypatch.setenv("STORY_BILLING_MODE", mode)
        assert worker._billing_authorize_job(_job()) == (True, "")
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    assert worker._billing_authorize_job({**_job(), "owner": "dev"}) == (True, "")
    assert L.get_entitlement(uid) is None                                       # nothing was written in any of those cases


def test_a_billing_store_outage_at_the_worker_fails_open_not_a_paying_customers_job(monkeypatch):
    from app import worker

    class Boom:
        def reserve_video(self, *a, **k):
            from billing import BillingStoreError
            raise BillingStoreError("down")

    monkeypatch.setattr(worker, "_billing_ledger", lambda: Boom())
    monkeypatch.setenv("STORY_BILLING_MODE", "enforce")
    assert worker._billing_authorize_job(_job()) == (True, "")
