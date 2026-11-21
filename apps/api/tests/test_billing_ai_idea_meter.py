"""Billing V2 AI-idea meter (owner decision 2026-11-21): one unit per SUCCESSFUL in-camera AI idea call
(/v1/director/initialize, /v1/director/next), Free starter only (50), Plus / grandfathered / admin unmetered, a typed 402
`ai_idea_allowance_exhausted` in enforce, never a deny in observe, nothing at all in off, and the trial clock never starts on an idea."""
from __future__ import annotations

import pytest
from app.deps import get_story_director_engine
from billing import BillingConfig, BillingDenied, BillingLedger, PlanLimits
from billing.model import AI_IDEA_ALLOWANCE_EXHAUSTED, PLAN_FREE, ST_PLUS_ACTIVE
from fastapi.testclient import TestClient
from model_gateway import FakeModelGateway, ProviderError
from story_director import RealStoryDirectorEngine

from tests.test_billing_gate import (
    T0,
    Rig,
    _auth,
    _env,  # noqa: F401  (re-export the autouse env fixture)
)
from tests.test_content_language import _DIR_RESP

INIT = "/v1/director/initialize"
NEXT = "/v1/director/next"


class _Engine:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def _out(self):
        return RealStoryDirectorEngine(FakeModelGateway(response=_DIR_RESP)).initialize({"summary": "x"}, None)

    def initialize(self, *a, **k):
        self.calls += 1
        if self.fail:
            raise ProviderError("down")
        return self._out()

    def next(self, *a, **k):
        self.calls += 1
        if self.fail:
            raise ProviderError("down")
        return self._out()


def _rig(mode, ideas=3, fail=False):
    r = Rig(mode, cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=30, ideas=ideas)))
    eng = _Engine(fail=fail)
    r.app.dependency_overrides[get_story_director_engine] = lambda: eng
    r.c = TestClient(r.app)
    return r, eng


def _init(r, sub="u1"):
    return r.c.post(INIT, headers=_auth(sub), json={"creative_intent": {}, "scene_understanding": None})


def _next(r, sub="u1"):
    return r.c.post(NEXT, headers=_auth(sub), json={"prior": {}})


def _uid(sub="u1"):
    return f"story-{sub}"


# ---- ledger ------------------------------------------------------------------------------------------------------

def _ledger(backend, ideas=2):
    ddb, table, _kind = backend
    return BillingLedger(ddb=ddb, table=table, clock=lambda: T0,
                         cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=30, ideas=ideas)))


def test_free_starter_gets_the_idea_allowance_and_a_typed_denial_when_spent(usage_backend):
    L = _ledger(usage_backend, ideas=2)
    for op in ("a", "b"):
        assert L.reserve_idea("u", op).charged
        assert L.settle_idea("u", op) == "settled"
    with pytest.raises(BillingDenied) as e:
        L.reserve_idea("u", "c")
    assert e.value.code == AI_IDEA_ALLOWANCE_EXHAUSTED and e.value.action == "subscribe"
    v = L.entitlement_view("u")
    assert v["ideas"] == {"total": 2, "used": 2, "reserved": 0, "remaining": 0}
    assert v["capabilities"]["ai_ideas"] == "metered"


def test_a_failed_idea_is_released_never_charged_and_never_starts_the_trial_clock(usage_backend):
    L = _ledger(usage_backend, ideas=1)
    assert L.reserve_idea("u", "a").charged
    assert L.release_idea("u", "a") == "released"
    e = L.get_entitlement("u")
    assert (e.i_avail, e.i_resv, e.i_used) == (1, 0, 0)
    assert L.reserve_idea("u", "b").charged and L.settle_idea("u", "b") == "settled"
    e = L.get_entitlement("u")
    assert e.trial_start is None and e.trial_end is None, "only a settled VIDEO starts the 14-day clock"


def test_a_pre_meter_free_starter_is_initialized_lazily_exactly_once(usage_backend):
    L = _ledger(usage_backend, ideas=2)
    L.ensure_entitlement("u")
    # simulate an entitlement written before billing-config/4 (no b_i_* counters)
    L._c().update_item(TableName=L.table, Key=L._ent_key("u"), UpdateExpression="REMOVE b_i_total, b_i_avail, b_i_resv, b_i_used")
    assert L.get_entitlement("u").i_total is None
    assert L.entitlement_view("u")["ideas"]["remaining"] == 2, "shows the full starter allowance before the first idea"
    assert L.reserve_idea("u", "a").charged and L.settle_idea("u", "a") == "settled"
    e = L.get_entitlement("u")
    assert (e.i_total, e.i_avail, e.i_used) == (2, 1, 1)


def test_plus_grandfathered_and_admin_accounts_are_unmetered_for_ideas(usage_backend):
    L = _ledger(usage_backend, ideas=0)                               # a zero allowance proves nothing is decremented
    L.apply_subscription("plus", status=ST_PLUS_ACTIVE, period_id="p1", period_start=T0 - 10, period_end=T0 + 30 * 86400,
                         event_ts=T0)
    L.grandfather("beta")
    L.admin_grant("admin", videos=1, moments=1)
    for uid in ("plus", "beta", "admin"):
        h = L.reserve_idea(uid, "x")
        assert not h.charged and h.reason == "unlimited"
        assert L.settle_idea(uid, "x") == "settled"
        v = L.entitlement_view(uid)
        assert v["ideas"] is None and v["capabilities"]["ai_ideas"] == "unlimited"
    with pytest.raises(BillingDenied):
        L.reserve_idea("free", "x")                    # control: the Free starter with 0 ideas is refused
    assert L.get_entitlement("free").plan == PLAN_FREE


def test_idea_exhaustion_does_not_block_video_or_moment_and_vice_versa(usage_backend):
    L = _ledger(usage_backend, ideas=1)
    assert L.reserve_idea("u", "i1").charged and L.settle_idea("u", "i1") == "settled"
    assert L.reserve_video("u", "v1").charged, "ideas and videos are independent meters"
    v = L.entitlement_view("u")
    assert v["upgrade"]["blocking"] is False, "running out of ideas never blocks creating"


# ---- API wiring ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("route", [INIT, NEXT])
def test_enforce_meters_each_successful_idea_call_then_returns_the_typed_402(route):
    r, eng = _rig("enforce", ideas=2)
    call = _init if route == INIT else _next
    assert call(r).status_code == 200 and call(r).status_code == 200
    third = call(r)
    assert third.status_code == 402
    body = third.json()
    assert body["error"] == AI_IDEA_ALLOWANCE_EXHAUSTED and body["action"] == "subscribe"
    assert eng.calls == 2, "a refused idea never reaches the model"
    assert r.live.get_entitlement(_uid()).i_used == 2


def test_enforce_a_failed_idea_call_is_released():
    r, _ = _rig("enforce", ideas=1, fail=True)
    assert _init(r).status_code == 503
    e = r.live.get_entitlement(_uid())
    assert (e.i_avail, e.i_resv, e.i_used) == (1, 0, 0)


def test_observe_never_denies_an_idea_and_writes_no_live_counter():
    r, eng = _rig("observe", ideas=1)
    for _ in range(3):
        assert _init(r).status_code == 200
    assert eng.calls == 3
    assert r.live.get_entitlement(_uid()) is None, "observe never creates or debits the live entitlement"
    assert r.shadow.get_entitlement(_uid()).i_used == 1


def test_off_performs_no_idea_accounting():
    r, _ = _rig("off", ideas=1)
    for _ in range(3):
        assert _init(r).status_code == 200
    assert r.live.get_entitlement(_uid()) is None and r.shadow.get_entitlement(_uid()) is None


def test_unauthenticated_idea_calls_are_not_metered():
    r, _ = _rig("enforce", ideas=1)
    for _ in range(2):
        assert r.c.post(INIT, json={"creative_intent": {}, "scene_understanding": None}).status_code in (200, 401)
    assert r.live.get_entitlement(_uid()) is None


def test_entitlement_endpoint_reports_the_idea_allowance_in_enforce():
    r, _ = _rig("enforce", ideas=3)
    assert _init(r).status_code == 200
    body = r.c.get("/v1/billing/entitlement", headers=_auth()).json()
    assert body["contract_version"] == 3
    assert body["ideas"] == {"total": 3, "used": 1, "reserved": 0, "remaining": 2}
    assert body["capabilities"]["ai_ideas"] == "metered"
