"""Billing V2: unlimited YoTale Plus, through the REAL route handlers with fakes (no AWS, no model calls).

Every quota test states its config explicitly (never env defaults):
  CDK  = what every CDK-deployed environment sets: 500 gens/day, $50/month (beta), 2 active jobs
  CODE = the QuotaConfig.from_env() code defaults:  20 gens/day,  $8/month,       2 active jobs
The global breaker is set high (or low, where the test is about it) so a per-user result is never a global one.
"""
from __future__ import annotations

import pytest
from billing import (
    ST_PLUS_ACTIVE,
    ST_PLUS_EXPIRED,
    BillingConfig,
    BillingLedger,
    PlanLimits,
)
from billing.fakes import FakeDDB
from user_quota import QuotaConfig, UserQuota
from user_quota.fakes import FakeDDB as QuotaFakeDDB

from tests.test_billing_au_binding import _GOOD, CountingGateway, frames_of, mid
from tests.test_billing_au_binding import Rig as AURig
from tests.test_billing_gate import Rig, _auth, uid

T0 = 1_800_000_000
DAY = 86400
CDK = QuotaConfig(user_monthly_usd=50.0, user_daily_gens=500, max_active_jobs=2, global_monthly_usd=1_000_000.0)
CODE = QuotaConfig(user_monthly_usd=8.0, user_daily_gens=20, max_active_jobs=2, global_monthly_usd=1_000_000.0)


def subscribe(led: BillingLedger, u: str = uid, *, end: int = T0 + 30 * DAY, status: str = ST_PLUS_ACTIVE, ts: int = T0):
    return led.apply_subscription(u, status=status, period_id="p1", period_start=T0, period_end=end, event_ts=ts, orig_txn="otx-1")


def video_records(ddb: FakeDDB, u: str = uid) -> list:
    return [k for k in ddb.items if k[0] == u and k[1].startswith("billing#v#")]


def finish_job(rig: Rig, q: UserQuota, op: str, *, actual_usd: float) -> None:
    """What the worker does at a terminal state: settle the actual spend and free the active-job slot."""
    job = next(j for j in rig.store.jobs.values() if j["operation_id"].endswith(op))
    q.settle(uid, job["operation_id"], actual_usd=actual_usd)
    q.release_slot(uid, job["job_id"])


@pytest.fixture()
def quota_enforced(monkeypatch):
    monkeypatch.setenv("STORY_QUOTA_MODE", "enforce")


# ---- videos: billing ---------------------------------------------------------------------------------------------

def test_plus_creates_its_13th_30th_and_61st_video_with_no_billing_denial_and_one_record_each():
    r = Rig("enforce")
    subscribe(r.live)
    for i in range(1, 62):
        resp = r.submit(f"v{i}")
        assert resp.status_code == 202, (i, resp.text)
    assert len(video_records(r.ddb)) == 61                               # one operation record per video (attribution)
    e = r.live.get_entitlement(uid)
    assert (e.v_resv, e.v_used) == (0, 0)                               # no counter is spent: unlimited
    view = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert view["unlimited"] is True and view["videos"] is None and view["capabilities"]["video_generation"] == "unlimited"


def test_duplicate_submit_and_duplicate_sqs_delivery_yield_one_operation_record(monkeypatch):
    from app import worker
    r = Rig("enforce")
    subscribe(r.live)
    assert r.submit("dup").status_code == 202
    assert r.submit("dup").status_code == 202                           # client retry with the same operation id
    assert len(video_records(r.ddb)) == 1 and len(r.store.enqueued) == 1
    monkeypatch.setattr(worker, "_billing_ledger", lambda: r.live)
    job = next(iter(r.store.jobs.values()))
    assert worker._billing_authorize_job(job) == (True, "")
    assert worker._billing_authorize_job(job) == (True, "")             # SQS redelivery
    assert len(video_records(r.ddb)) == 1


def test_a_plus_that_lapses_mid_queue_still_runs_the_job_authorized_at_submit(monkeypatch):
    from app import worker
    r = Rig("enforce")
    subscribe(r.live)
    assert r.submit("queued").status_code == 202
    subscribe(r.live, status=ST_PLUS_EXPIRED, ts=T0 + 1)                # expires while the job waits
    monkeypatch.setattr(worker, "_billing_ledger", lambda: r.live)
    job = next(iter(r.store.jobs.values()))
    assert worker._billing_authorize_job(job) == (True, "")
    third = r.submit("after-lapse")
    assert third.status_code == 402 and third.json()["error"] == "subscription_required"   # never credits wording for Plus


def test_a_failed_unmetered_job_releases_its_record_when_the_quota_denies_the_submit(quota_enforced):
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="q",
                  cfg=QuotaConfig(user_monthly_usd=50.0, user_daily_gens=500, max_active_jobs=1, global_monthly_usd=1e6))
    r = Rig("enforce", quota=q)
    subscribe(r.live)
    assert r.submit("a").status_code == 202
    denied = r.submit("b")                                               # active_jobs = 1: busy
    assert denied.status_code == 429
    states = [r.ddb.items[k]["b_state"]["S"] for k in video_records(r.ddb)]
    assert sorted(states) == ["released", "reserved"]                    # owns-operation (not owns-charge) released it


def test_free_starter_exhaustion_still_returns_its_402s():
    r = Rig("enforce")
    assert r.submit("a").status_code == 202 and r.submit("b").status_code == 202
    body = r.submit("c").json()
    assert body["error"] == "video_credits_exhausted" and body["action"] == "subscribe"


# ---- videos: per-user quota exemption ----------------------------------------------------------------------------

@pytest.mark.parametrize("cfg,name", [(CDK, "cdk"), (CODE, "code_defaults")])
def test_plus_is_exempt_from_the_per_user_quota_caps(quota_enforced, cfg, name):
    """$1.00 actual per video, so the counterfactual (same config, no subscription) is denied by a per-user cap well before 61."""
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="q", cfg=cfg)
    r = Rig("enforce", quota=q)
    subscribe(r.live)
    for i in range(1, 62):
        resp = r.submit(f"v{i}")
        assert resp.status_code == 202, (name, i, resp.text)
        finish_job(r, q, f"v{i}", actual_usd=1.0)
    item = q._c().get_item(TableName="q", Key=q._key(uid, __import__("user_quota")._period())).get("Item")
    assert float(item["settled_usd"]["N"]) == pytest.approx(61.0)        # spend is still recorded for attribution

    q2 = UserQuota(ddb=QuotaFakeDDB(), usage_table="q", cfg=cfg)
    r2 = Rig("enforce", quota=q2)
    r2.live.grandfather(uid)                                             # unlimited for BILLING, but no subscription
    statuses = []
    for i in range(1, 62):
        resp = r2.submit(f"v{i}")
        statuses.append(resp.status_code)
        if resp.status_code == 202:
            finish_job(r2, q2, f"v{i}", actual_usd=1.0)
        else:
            assert resp.json()["scope"] in ("user_monthly_usd", "user_daily_gens") and "busy" not in resp.json()
            break
    assert statuses[-1] == 429, f"{name}: the caps, not luck, were what the exemption lifted"


def test_an_entitlement_read_failure_falls_back_to_normal_caps_never_uncapped(quota_enforced):
    class Broken:
        def get_entitlement(self, u):
            raise RuntimeError("store down")
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="q", cfg=CODE)
    r = Rig("off", quota=q)
    r.app.state._live_billing_ledger_override = Broken()
    codes = []
    for i in range(1, 25):
        resp = r.submit(f"v{i}")
        codes.append(resp.status_code)
        if resp.status_code == 202:
            finish_job(r, q, f"v{i}", actual_usd=0.01)
    assert codes.count(202) == 20 and codes[20] == 429                  # CODE: 20 gens/day applies


def test_active_jobs_and_the_global_breaker_are_retryable_busy_for_plus(quota_enforced):
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="q", cfg=CDK)
    r = Rig("enforce", quota=q)
    subscribe(r.live)
    assert r.submit("a").status_code == 202 and r.submit("b").status_code == 202
    busy = r.submit("c")
    body = busy.json()
    assert busy.status_code == 429 and body["busy"] is True and body["scope"] == "active_jobs"
    assert body["error"] == "quota_exceeded" and body["retry_after_seconds"] == 30 == int(busy.headers["Retry-After"])

    q2 = UserQuota(ddb=QuotaFakeDDB(), usage_table="q",
                   cfg=QuotaConfig(user_monthly_usd=50.0, user_daily_gens=500, max_active_jobs=2, global_monthly_usd=0.2))
    r2 = Rig("enforce", quota=q2)
    subscribe(r2.live)
    assert r2.submit("a").status_code == 202
    trip = r2.submit("b")                                                # 0.15 + 0.15 > 0.2: the shared breaker
    assert trip.status_code == 429 and trip.json()["busy"] is True and trip.json()["scope"] == "global_monthly_usd"
    assert int(trip.headers["Retry-After"]) == 300


# ---- observe mode (S2) -------------------------------------------------------------------------------------------

def test_observe_mode_never_logs_would_deny_for_a_live_plus_and_shows_plus():
    r = Rig("observe")
    r.app.state._live_billing_ledger_override = r.live
    seen = []
    r.app.state._quota_metric_hook = lambda name, cls: seen.append(name)
    subscribe(r.live)
    for i in range(5):                                                   # past the shadow Free starter's 2 videos
        assert r.submit(f"o{i}").status_code == 202
    assert "BillingWouldDeny" not in seen and "BillingObservePlus" in seen
    view = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert view["plan"] == "plus" and view["unlimited"] is True


# ---- Moments (AU) ------------------------------------------------------------------------------------------------

def test_plus_analyzes_more_than_100_new_moments_with_records_and_no_counter(usage_backend):
    r = AURig(usage_backend)
    subscribe(r.live, "story-u1")
    for i in range(1, 106):
        assert r.one(mid(i), frames_of(i % 200)).status_code == 200, i
    assert r.gw.n == 105
    e = r.ent()
    assert (e.m_used, e.m_resv) == (0, 0)
    assert r.one(mid(7), frames_of(7)).status_code == 200                 # re-import: cached result, no model call
    assert r.gw.n == 105


def test_concurrent_identical_au_for_plus_coalesces_into_one_model_run(usage_backend):
    import asyncio
    r = AURig(usage_backend, gateway=CountingGateway(_GOOD, delay=0.4))
    subscribe(r.live, "story-u1")

    async def go(c):
        return await asyncio.gather(*(r.post(c, mid(), frames_of(90)) for _ in range(5)))

    assert [x.status_code for x in r.run(go)] == [200] * 5
    assert r.gw.n == 1


def test_free_starter_moment_exhaustion_still_returns_its_402(usage_backend):
    r = AURig(usage_backend, cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=2), analysis_wait_s=3.0))
    assert r.one(mid(1), frames_of(1)).status_code == 200 and r.one(mid(2), frames_of(2)).status_code == 200
    third = r.one(mid(3), frames_of(3))
    assert third.status_code == 402 and third.json()["error"] == "moment_allowance_exhausted"


def test_expired_plus_au_is_subscription_required_not_an_allowance_message(usage_backend):
    r = AURig(usage_backend)
    subscribe(r.live, "story-u1", end=T0 + DAY)
    r.t[0] = T0 + 2 * DAY
    resp = r.one(mid(1), frames_of(1))
    assert resp.status_code == 402 and resp.json()["error"] == "subscription_required"


@pytest.mark.parametrize("cfg,name", [(CDK, "cdk"), (CODE, "code_defaults")])
def test_plus_au_is_exempt_from_per_user_quota_caps(usage_backend, quota_enforced, cfg, name):
    r = AURig(usage_backend)
    q = UserQuota(ddb=QuotaFakeDDB(), usage_table="q", cfg=cfg)
    r.app.state._user_quota = q
    subscribe(r.live, "story-u1")
    for i in range(1, 106):                                              # > CODE's 20 gens/day and > 100 new Moments
        resp = r.one(mid(i), frames_of(i % 200))
        assert resp.status_code == 200, (name, i, resp.text)
    if name == "code_defaults":                                          # counterfactual: no subscription, same config
        other = [r.one(mid(500 + i), frames_of(i), sub="u2").status_code for i in range(1, 23)]
        assert other.count(429) >= 1 and other[:20] == [200] * 20


# ---- contract compatibility (B5) ---------------------------------------------------------------------------------

def _assert_contract1_decodes(p: dict) -> None:
    """Mirrors the REQUIRED fields of the shipped contract-1 Swift structs (BillingModels.swift at 40a77f5)."""
    assert isinstance(p["billing_mode"], str) and isinstance(p["enforced"], bool)
    if p.get("offer") is not None:
        plus = p["offer"]["plus"]
        assert isinstance(plus["product_id"], str) and isinstance(plus["videos"], int) and isinstance(plus["moments"], int)
    for k in ("videos", "moments"):
        if p.get(k) is not None:
            assert all(isinstance(p[k][f], int) for f in ("total", "used", "reserved", "remaining"))
    if p.get("trial") is not None:
        assert isinstance(p["trial"]["state"], str)
    if p.get("upgrade") is not None:
        assert all(isinstance(p["upgrade"][f], bool) for f in ("eligible", "suggest", "blocking"))


@pytest.mark.parametrize("mode", ["off", "observe", "enforce"])
def test_the_v2_payload_still_decodes_with_the_contract1_model(mode):
    r = Rig(mode)
    r.app.state._live_billing_ledger_override = r.live
    free = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    _assert_contract1_decodes(free)
    subscribe(r.live)
    plus = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    _assert_contract1_decodes(plus)
    assert plus["contract_version"] == 2 and plus["offer"]["plus"]["unlimited"] is True
    if mode != "off" or plus.get("plan"):
        assert plus["videos"] is None and plus["capabilities"]["subscription"]["status"] == "active"

