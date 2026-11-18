"""Billing V1 ledger tests: atomic allowance accounting against a DynamoDB double that evaluates real
expression semantics (conditions, ADD, if_not_exists, transactions with rollback)."""
from __future__ import annotations

import threading

import pytest

from billing import (
    BillingConfig, BillingDenied, BillingLedger, BillingStoreError, PlanLimits, TransactionBoundElsewhere,
    MOMENT_ALLOWANCE_EXHAUSTED, SUBSCRIPTION_REQUIRED, TRIAL_EXPIRED, VIDEO_CREDITS_EXHAUSTED,
    ST_PLUS_ACTIVE, ST_PLUS_EXPIRED, ST_PLUS_GRACE,
)
from billing.fakes import FakeDDB

T0 = 1_800_000_000
DAY = 86400


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture()
def env():
    return FakeDDB(), Clock()


def mk(env, **kw):
    ddb, clock = env
    return BillingLedger(ddb=ddb, table="t", clock=clock, **kw)


def invariant(ent, kind):
    if kind == "video":
        return ent.v_avail + ent.v_resv + ent.v_used == ent.v_total
    return ent.m_avail + ent.m_resv + ent.m_used == ent.m_total


def run_threads(fn, args_list):
    ts = [threading.Thread(target=fn, args=a) for a in args_list]
    [t.start() for t in ts]
    [t.join() for t in ts]


# ---- entitlement creation + trial clock ------------------------------------------------------------------------

def test_free_starter_created_once_under_concurrency(env):
    L = mk(env)
    got = []
    run_threads(lambda: got.append(L.ensure_entitlement("u1")), [()] * 12)
    assert {e.created for e in got} == {T0}
    e = L.get_entitlement("u1")
    assert (e.plan, e.status, e.v_total, e.m_total, e.trial_end) == ("free_starter", "free_starter", 2, 30, None)


def test_trial_starts_at_first_successful_operation_not_at_reserve(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    assert L.get_entitlement("u1").trial_end is None
    L.release_video("u1", "op1")
    assert L.get_entitlement("u1").trial_end is None
    L.reserve_moment("u1", "m1")
    L.settle_moment("u1", "m1")
    e = L.get_entitlement("u1")
    assert e.trial_start == T0 and e.trial_end == T0 + 14 * DAY


def test_trial_state_survives_a_new_ledger_instance(env):
    mk(env).reserve_moment("u1", "m1")
    mk(env).settle_moment("u1", "m1")
    assert mk(env).get_entitlement("u1").trial_end == T0 + 14 * DAY      # reinstall/relogin == same server state


# ---- video credits ---------------------------------------------------------------------------------------------

def test_video_reserve_settle_counters(env):
    L = mk(env)
    h = L.reserve_video("u1", "op1")
    assert h.charged and h.state == "reserved"
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (1, 1, 0) and invariant(e, "video")
    assert L.settle_video("u1", "op1") == "settled"
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (1, 0, 1) and invariant(e, "video")


def test_exhaustion_is_typed_and_carries_the_snapshot(env):
    L = mk(env)
    for i in range(2):
        L.reserve_video("u1", f"op{i}")
        L.settle_video("u1", f"op{i}")
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "op3")
    d = ei.value
    assert d.code == VIDEO_CREDITS_EXHAUSTED and d.action == "subscribe"
    assert d.snapshot["videos"] == {"total": 2, "used": 2, "reserved": 0, "remaining": 0}
    assert d.snapshot["upgrade"]["blocking"] is True


def test_reservations_hold_credits_so_concurrent_requests_cannot_overspend(env):
    L = mk(env)
    results = []

    def go(i):
        try:
            results.append(("ok", L.reserve_video("u1", f"op{i}").charged))
        except BillingDenied as d:
            results.append(("denied", d.code))

    run_threads(go, [(i,) for i in range(20)])
    assert sum(1 for r in results if r[0] == "ok") == 2
    assert sum(1 for r in results if r == ("denied", VIDEO_CREDITS_EXHAUSTED)) == 18
    e = L.get_entitlement("u1")
    assert e.v_resv == 2 and e.v_avail == 0 and invariant(e, "video")


def test_two_devices_racing_for_the_last_credit_one_wins(env):
    L = mk(env)
    L.reserve_video("u1", "a")
    L.settle_video("u1", "a")
    out = []

    def dev(op):
        try:
            out.append(L.reserve_video("u1", op).charged)
        except BillingDenied:
            out.append("denied")

    run_threads(dev, [("devA",), ("devB",)])
    assert sorted(map(str, out)) == ["True", "denied"]


def test_duplicate_reserve_settle_release_are_idempotent(env):
    L = mk(env)
    assert L.reserve_video("u1", "op1").charged
    again = L.reserve_video("u1", "op1")
    assert not again.charged and again.reason == "idempotent"
    assert L.settle_video("u1", "op1") == "settled"
    assert L.settle_video("u1", "op1") == "noop"                 # duplicate SQS delivery
    assert L.release_video("u1", "op1") == "noop"                # a late failure path cannot un-charge a delivered video
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (1, 0, 1)
    assert not L.reserve_video("u1", "op1").charged              # retried submit after completion: not charged again


def test_concurrent_duplicate_settles_count_once(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    run_threads(L.settle_video, [("u1", "op1")] * 10)
    e = L.get_entitlement("u1")
    assert (e.v_resv, e.v_used) == (0, 1) and invariant(e, "video")


def test_failed_generation_releases_and_the_same_op_can_retry(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    assert L.release_video("u1", "op1") == "released"
    assert L.release_video("u1", "op1") == "noop"
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (2, 0, 0)
    assert L.reserve_video("u1", "op1").charged                  # released -> reserved again
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv) == (1, 1) and invariant(e, "video")


def test_late_completion_after_release_still_charges_the_delivered_work(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.release_video("u1", "op1")                                  # e.g. swept as orphaned
    assert L.settle_video("u1", "op1") == "settled"               # but the result was durably recorded
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_used) == (1, 1) and invariant(e, "video")


def test_reconcile_after_worker_crash_between_result_and_settle(env):
    L = mk(env)
    L.reserve_video("u1", "done")
    L.reserve_video("u1", "died")
    assert L.reconcile_video_job("u1", "done", "completed") == "settled"
    assert L.reconcile_video_job("u1", "died", "failed") == "released"
    assert L.reconcile_video_job("u1", "done", "completed") == "noop"
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (1, 0, 1)


def test_reserve_is_all_or_nothing_when_the_credit_guard_fails(env):
    ddb, _ = env
    L = mk(env)
    for i in range(2):
        L.reserve_video("u1", f"op{i}")
    before = len([k for k in ddb.items if k[0] == "u1"])
    with pytest.raises(BillingDenied):
        L.reserve_video("u1", "op-x")
    assert len([k for k in ddb.items if k[0] == "u1"]) == before    # no orphan operation record was created


def test_store_failure_is_a_store_error_not_a_denial(env):
    class Boom(FakeDDB):
        def transact_write_items(self, TransactItems):
            raise RuntimeError("ddb down")

    with pytest.raises(BillingStoreError):
        BillingLedger(ddb=Boom(), table="t", clock=env[1]).reserve_video("u1", "op1")


# ---- trial expiry -----------------------------------------------------------------------------------------------

def test_trial_expiry_blocks_both_meters_but_never_touches_delivered_videos(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    env[1].advance(14 * DAY + 1)
    for fn, arg in ((L.reserve_video, "op2"), (L.reserve_moment, "m9")):
        with pytest.raises(BillingDenied) as ei:
            fn("u1", arg)
        assert ei.value.code == TRIAL_EXPIRED and ei.value.action == "subscribe"
    assert L.get_entitlement("u1").v_used == 1
    assert L.entitlement_view("u1")["trial"]["state"] == "expired"


def test_trial_not_expired_at_the_boundary(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    env[1].advance(14 * DAY)
    assert L.reserve_video("u1", "op2").charged


def test_upgrade_suggested_after_first_video_but_not_blocking(env):
    L = mk(env)
    assert L.entitlement_view("u1")["upgrade"] == {"eligible": True, "suggest": False, "blocking": False}
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    assert L.entitlement_view("u1")["upgrade"] == {"eligible": True, "suggest": True, "blocking": False}


# ---- moments ----------------------------------------------------------------------------------------------------

def test_new_moment_charged_once_and_reuse_is_free(env):
    L = mk(env)
    assert L.reserve_moment("u1", "M1").charged
    assert L.settle_moment("u1", "m1") == "settled"            # case-insensitive moment id
    again = L.reserve_moment("u1", "m1")
    assert not again.charged and again.reason == "already_analyzed"
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.m_used) == (29, 1) and invariant(e, "moment")


def test_concurrent_duplicate_analysis_of_one_moment_charges_once(env):
    L = mk(env)
    holds = []
    run_threads(lambda: holds.append(L.reserve_moment("u1", "m1")), [()] * 10)
    assert sum(1 for h in holds if h.charged) == 1
    assert {h.reason for h in holds if not h.charged} <= {"in_flight", "idempotent"}
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.m_resv) == (29, 1)


def test_failed_analysis_releases_and_retry_charges_once(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")
    L.release_moment("u1", "m1")
    assert L.get_entitlement("u1").m_avail == 30
    assert L.reserve_moment("u1", "m1").charged
    L.settle_moment("u1", "m1")
    assert L.get_entitlement("u1").m_used == 1


def test_uncharged_duplicate_does_not_own_the_charge(env):
    L = mk(env)
    owner = L.reserve_moment("u1", "m1")
    dup = L.reserve_moment("u1", "m1")
    assert owner.charged and not dup.charged     # caller contract: release only a hold with charged=True
    L.settle_moment("u1", "m1")
    assert L.get_entitlement("u1").m_used == 1


def test_duplicate_succeeds_after_owner_failed_and_released(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")
    L.reserve_moment("u1", "m1")
    L.release_moment("u1", "m1")                                  # owner failed
    assert L.settle_moment("u1", "m1") == "settled"               # duplicate delivered the analysis
    e = L.get_entitlement("u1")
    assert (e.m_used, e.m_avail) == (1, 29) and invariant(e, "moment")


def test_moment_allowance_exhausts_independently_of_videos(env):
    L = mk(env)
    for i in range(30):
        L.reserve_moment("u1", f"m{i}")
        L.settle_moment("u1", f"m{i}")
    with pytest.raises(BillingDenied) as ei:
        L.reserve_moment("u1", "m-extra")
    assert ei.value.code == MOMENT_ALLOWANCE_EXHAUSTED
    assert L.reserve_video("u1", "op1").charged                   # video credits unaffected
    assert not L.reserve_moment("u1", "m3").charged               # an already-analyzed Moment stays free


def test_bulk_import_cannot_exceed_the_allowance_concurrently(env):
    L = mk(env)
    ok = []

    def go(i):
        try:
            ok.append(L.reserve_moment("u1", f"m{i}").charged)
        except BillingDenied:
            pass

    run_threads(go, [(i,) for i in range(60)])
    assert sum(ok) == 30
    assert invariant(L.get_entitlement("u1"), "moment")


def test_stale_moment_reservation_is_reclaimed_without_a_second_charge(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")                                  # request crashed here
    env[1].advance(L.cfg.stale_reservation_s + 1)
    h = L.reserve_moment("u1", "m1")
    assert h.charged and h.reason == "reclaimed"
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.m_resv) == (29, 1)                       # still ONE reserved unit
    assert L.reclaim_stale_moments("u1") == 0


def test_reclaim_sweep_releases_abandoned_reservations(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")
    L.reserve_moment("u1", "m2")
    env[1].advance(L.cfg.stale_reservation_s + 5)
    L.reserve_moment("u1", "m3")                                  # fresh one must survive
    assert L.reclaim_stale_moments("u1") == 2
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.m_resv) == (29, 1) and invariant(e, "moment")


# ---- Plus subscription ------------------------------------------------------------------------------------------

def plus(L, uid="u1", *, period="p1", start=T0, end=T0 + 30 * DAY, ts=T0, status=ST_PLUS_ACTIVE, **kw):
    return L.apply_subscription(uid, status=status, period_id=period, period_start=start, period_end=end,
                                event_ts=ts, orig_txn="otx-1", **kw)


def renew(L, period="p2", ts=T0 + 30 * DAY):
    return plus(L, period=period, start=ts, end=ts + 30 * DAY, ts=ts)


def test_plus_has_its_own_allowances_and_resets_at_the_apple_boundary(env):
    L = mk(env)
    plus(L)
    e = L.get_entitlement("u1")
    assert (e.plan, e.status, e.v_total, e.m_total) == ("plus", ST_PLUS_ACTIVE, 12, 100)
    for i in range(12):
        L.reserve_video("u1", f"op{i}")
        L.settle_video("u1", f"op{i}")
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "op13")
    assert ei.value.code == VIDEO_CREDITS_EXHAUSTED and ei.value.action == "wait_for_renewal"
    renew(L)
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_avail, e.m_avail) == (0, 12, 100) and e.period_id == "p2"


def test_unused_plus_allowance_does_not_roll_over(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    renew(L)
    assert L.get_entitlement("u1").v_avail == 12


def test_in_flight_reservation_from_the_old_period_never_touches_the_new_counters(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "slow")
    renew(L)
    assert L.settle_video("u1", "slow") == "settled"
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_resv, e.v_avail) == (0, 0, 12)          # the new period is untouched
    assert L.settle_video("u1", "slow") == "noop"


def test_delayed_older_webhook_cannot_undo_a_newer_state(env):
    L = mk(env)
    plus(L, ts=100)
    plus(L, status=ST_PLUS_EXPIRED, ts=200)
    stale = plus(L, status=ST_PLUS_ACTIVE, ts=150)                # arrives late
    assert stale.status == ST_PLUS_EXPIRED
    assert plus(L, status=ST_PLUS_EXPIRED, ts=200).status == ST_PLUS_EXPIRED   # exact redelivery is harmless


def test_expired_subscription_requires_resubscribing_and_keeps_delivered_work(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 31 * DAY)
    for fn, arg in ((L.reserve_video, "op2"), (L.reserve_moment, "m1")):
        with pytest.raises(BillingDenied) as ei:
            fn("u1", arg)
        assert ei.value.code == SUBSCRIPTION_REQUIRED
    assert L.get_entitlement("u1").v_used == 1


def test_period_end_passing_without_a_webhook_is_enforced_from_the_clock(env):
    L = mk(env)
    plus(L)
    env[1].advance(30 * DAY + 1)
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "op1")
    assert ei.value.code == SUBSCRIPTION_REQUIRED
    assert L.entitlement_view("u1")["status"] == ST_PLUS_EXPIRED


def test_grace_period_keeps_access_until_grace_end(env):
    L = mk(env)
    plus(L, status=ST_PLUS_GRACE, grace_end=T0 + 33 * DAY)
    env[1].advance(31 * DAY)
    assert L.reserve_video("u1", "op1").charged
    env[1].advance(3 * DAY)
    with pytest.raises(BillingDenied):
        L.reserve_video("u1", "op2")


def test_resubscribing_after_expiry_restores_allowances(env):
    L = mk(env)
    plus(L)
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 31 * DAY)
    plus(L, period="p9", start=T0 + 40 * DAY, end=T0 + 70 * DAY, ts=T0 + 40 * DAY)
    env[1].advance(41 * DAY)
    assert L.reserve_video("u1", "op1").charged


def test_free_user_upgrading_gets_plus_counters_and_loses_the_trial_gate(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    plus(L)
    e = L.get_entitlement("u1")
    assert (e.plan, e.v_used, e.v_avail) == ("plus", 0, 12)
    env[1].advance(20 * DAY)                                      # past the old trial end: irrelevant for Plus
    assert L.reserve_video("u1", "op2").charged


# ---- grandfathered / admin --------------------------------------------------------------------------------------

def test_grandfathered_accounts_are_unlimited_and_are_not_counted(env):
    L = mk(env)
    L.grandfather("u1")
    for i in range(50):
        assert L.reserve_video("u1", f"op{i}").reason == "unlimited"
        assert L.reserve_moment("u1", f"m{i}").reason == "unlimited"
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_resv, e.m_used) == (0, 0, 0)
    assert L.entitlement_view("u1")["status"] == "beta_grandfathered"


def test_store_events_never_downgrade_grandfathered_or_admin_accounts(env):
    L = mk(env)
    L.grandfather("u1")
    assert plus(L).plan == "beta_grandfathered"
    L.admin_grant("u2", videos=5, moments=50, reason="support")
    assert plus(L, "u2").plan == "admin_granted"


def test_admin_grant_sets_finite_allowances_and_expiry(env):
    L = mk(env)
    L.admin_grant("u1", videos=3, moments=10, until=T0 + 7 * DAY, reason="goodwill")
    e = L.get_entitlement("u1")
    assert (e.status, e.v_avail, e.m_avail) == ("admin_granted", 3, 10)
    env[1].advance(8 * DAY)
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "op1")
    assert ei.value.code == SUBSCRIPTION_REQUIRED


# ---- controlled refund ------------------------------------------------------------------------------------------

def test_refund_returns_one_credit_once_and_is_capped(env):
    L = mk(env)
    plus(L)
    for i in range(5):
        L.reserve_video("u1", f"op{i}")
        L.settle_video("u1", f"op{i}")
    assert L.refund_video("u1", "op0", "render_failed") == "refunded"
    assert L.refund_video("u1", "op0", "render_failed") == "noop"             # once per operation
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_avail, e.refunds) == (4, 8, 1) and invariant(e, "video")
    assert L.refund_video("u1", "op1", "x") == "refunded"
    assert L.refund_video("u1", "op2", "x") == "refunded"
    assert L.refund_video("u1", "op3", "x") == "not_eligible:refund_cap"       # 3 per period


def test_refund_requires_a_settled_recent_operation_in_the_same_period(env):
    L = mk(env)
    plus(L)
    assert L.refund_video("u1", "nope", "x") == "not_eligible:unknown_operation"
    L.reserve_video("u1", "op1")
    assert L.refund_video("u1", "op1", "x") == "not_eligible:not_settled"
    L.settle_video("u1", "op1")
    env[1].advance(L.cfg.refund_window_s + 1)
    assert L.refund_video("u1", "op1", "x") == "not_eligible:window_elapsed"


def test_refund_is_blocked_after_the_period_rolls_over(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    renew(L)
    assert L.refund_video("u1", "op1", "x") == "not_eligible:period_or_plan"


# ---- shadow (observe) isolation ---------------------------------------------------------------------------------

def test_shadow_accounting_never_touches_live_counters(env):
    live, shadow = mk(env), mk(env, shadow=True)
    for i in range(2):
        shadow.reserve_video("u1", f"op{i}")
        shadow.settle_video("u1", f"op{i}")
    with pytest.raises(BillingDenied):
        shadow.reserve_video("u1", "op3")                         # the hypothetical decision is still computed
    assert live.get_entitlement("u1") is None                     # nothing live was created or debited
    e = live.ensure_entitlement("u1")
    assert (e.v_avail, e.trial_end) == (2, None)                  # flipping to enforce starts clean


# ---- Apple identity ---------------------------------------------------------------------------------------------

def test_apple_account_token_is_a_stable_uuid_even_under_concurrency(env):
    import uuid
    L = mk(env)
    toks = []
    run_threads(lambda: toks.append(L.get_or_create_apple_account_token("u1")), [()] * 8)
    assert len(set(toks)) == 1 and uuid.UUID(toks[0])
    assert mk(env, shadow=True).get_or_create_apple_account_token("u1") == toks[0]      # same identity in observe


def test_a_transaction_cannot_grant_entitlements_to_two_accounts(env):
    L = mk(env)
    L.bind_apple_transaction("otx-9", "u1")
    L.bind_apple_transaction("otx-9", "u1")                       # idempotent for the owner
    with pytest.raises(TransactionBoundElsewhere):
        L.bind_apple_transaction("otx-9", "u2")


# ---- config -----------------------------------------------------------------------------------------------------

def test_allowances_are_configuration_not_code(env):
    L = mk(env, cfg=BillingConfig(free_starter=PlanLimits(videos=1, moments=3)))
    e = L.ensure_entitlement("u1")
    assert (e.v_total, e.m_total) == (1, 3)


def test_malformed_override_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("STORY_BILLING_PLANS_JSON", "{not json")
    assert BillingConfig.from_env().plus == PlanLimits(videos=12, moments=100)
    monkeypatch.setenv("STORY_BILLING_PLANS_JSON", '{"plus": {"videos": 20}}')
    c = BillingConfig.from_env()
    assert c.plus == PlanLimits(videos=20, moments=100) and c.free_starter.videos == 2


# ---- forced interleaving: the atomic guard, not luck or speed, prevents overspend -----------------------------

class RacingDDB(FakeDDB):
    """Holds the first N entitlement reads at a barrier so every thread decides from the SAME stale snapshot before any
    of them writes: the worst-case check-then-write interleaving."""
    def __init__(self, n):
        super().__init__()
        self.barrier, self.n, self.armed, self._hits = threading.Barrier(n), n, False, 0
        self._gate = threading.Lock()

    def get_item(self, TableName, Key, ConsistentRead=False):
        out = super().get_item(TableName, Key, ConsistentRead)
        if self.armed and Key["quota_period"]["S"].endswith("entitlement"):
            with self._gate:
                self._hits += 1
                mine = self._hits <= self.n
            if mine:
                self.barrier.wait(timeout=5)
        return out


@pytest.mark.parametrize("kind", ["video", "moment"])
def test_stale_snapshot_race_cannot_overspend(kind):
    n = 12
    ddb, clock = RacingDDB(n), Clock()
    L = BillingLedger(ddb=ddb, table="t", clock=clock, cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=3)))
    L.ensure_entitlement("u1")
    ddb.armed = True
    won, denied = [], []

    def go(i):
        try:
            h = L.reserve_video("u1", f"op{i}") if kind == "video" else L.reserve_moment("u1", f"m{i}")
            won.append(h.charged)
        except BillingDenied:
            denied.append(1)

    run_threads(go, [(i,) for i in range(n)])
    cap = 2 if kind == "video" else 3
    assert sum(won) == min(n, cap)
    e = L.get_entitlement("u1")
    assert invariant(e, kind) and (e.v_avail if kind == "video" else e.m_avail) >= 0


def test_stale_snapshot_race_on_the_last_credit_lets_exactly_one_through():
    n = 6
    ddb = RacingDDB(n)
    L = BillingLedger(ddb=ddb, table="t", clock=Clock(), cfg=BillingConfig(free_starter=PlanLimits(videos=1, moments=1)))
    L.ensure_entitlement("u1")
    ddb.armed = True
    won = []

    def go(i):
        try:
            won.append(L.reserve_video("u1", f"op{i}").charged)
        except BillingDenied:
            pass

    run_threads(go, [(i,) for i in range(n)])
    assert sum(won) == 1 and L.get_entitlement("u1").v_avail == 0


# ---- grandfathering script (pure selection + idempotent apply) ----------------------------------------------------

def test_grandfather_selection_and_idempotent_apply(env):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "gf", Path(__file__).resolve().parents[3] / "scripts" / "yotale_billing_grandfather.py")
    gf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gf)
    S = lambda v: {"S": v}  # noqa: E731
    users = [
        {"story_user_id": S("a"), "account_status": S("active"), "beta_access_status": S("invited")},
        {"story_user_id": S("b"), "account_status": S("suspended"), "beta_access_status": S("invited")},
        {"story_user_id": S("c"), "account_status": S("active"), "beta_access_status": S("revoked")},
        {"story_user_id": S("d"), "account_status": S("active"), "beta_access_status": S("eligible")},
        {"story_user_id": S("rehearsal"), "account_status": S("active"), "beta_access_status": S("invited")},
    ]
    assert gf.select_accounts(users, {"rehearsal"}) == ["a", "d"]
    L = mk(env)
    for _ in range(2):                                            # running it twice changes nothing
        for u in ("a", "d"):
            assert L.grandfather(u).plan == "beta_grandfathered"
    assert L.get_entitlement("rehearsal") is None
    assert L.ensure_entitlement("rehearsal").plan == "free_starter"
