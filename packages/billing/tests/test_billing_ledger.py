"""Billing V1 ledger tests: atomic allowance accounting against a DynamoDB double that evaluates real
expression semantics (conditions, ADD, if_not_exists, transactions with rollback)."""
from __future__ import annotations

import threading

import pytest

from billing import (
    reservation_id,
    BillingConfig, BillingDenied, BillingLedger, BillingStoreError, PlanLimits, TransactionBoundElsewhere,
    MOMENT_ALLOWANCE_EXHAUSTED, SUBSCRIPTION_REQUIRED, TRIAL_EXPIRED, VIDEO_CREDITS_EXHAUSTED,
    ST_PLUS_ACTIVE, ST_PLUS_EXPIRED, ST_PLUS_GRACE,
)

T0 = 1_800_000_000
DAY = 86400


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class Env:
    """(ddb, clock) pair, plus the table and backend kind. Indexable like the old tuple: env[0] = ddb, env[1] = clock."""
    def __init__(self, ddb, table, kind):
        self.ddb, self.table, self.kind, self.clock = ddb, table, kind, Clock()

    def __getitem__(self, i):
        return (self.ddb, self.clock)[i]


@pytest.fixture()
def env(usage_backend):
    """Every ledger test runs against the in-memory double AND real DynamoDB Local (skipped with a reason when unavailable)."""
    return Env(*usage_backend)


def mk(env, **kw):
    return BillingLedger(ddb=env.ddb, table=env.table, clock=env.clock, **kw)


def count_items(env, uid):
    r = env.ddb.query(TableName=env.table, KeyConditionExpression="story_user_id = :pk AND begins_with(quota_period, :sk)",
                      ExpressionAttributeValues={":pk": {"S": uid}, ":sk": {"S": "billing"}})
    return len(r["Items"])


class Wrapped:
    """Delegating client wrapper: `hooks` maps a method name to a replacement(call_original, *a, **kw)."""
    def __init__(self, inner, **hooks):
        self._inner, self._hooks = inner, hooks

    def __getattr__(self, name):
        real = getattr(self._inner, name)
        hook = self._hooks.get(name)
        return (lambda *a, **kw: hook(real, *a, **kw)) if hook else real


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


def test_trial_clock_starts_at_the_first_successful_VIDEO_not_at_an_import_or_a_reservation(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")
    L.settle_moment("u1", "m1")                                # a successful analysis does NOT start the clock
    assert L.get_entitlement("u1").trial_end is None
    L.reserve_video("u1", "op1")
    assert L.get_entitlement("u1").trial_end is None          # reserved only
    L.release_video("u1", "op1")
    assert L.get_entitlement("u1").trial_end is None          # a FAILED video never starts the clock
    env[1].advance(3 * DAY)
    L.reserve_video("u1", "op2")
    L.settle_video("u1", "op2")
    e = L.get_entitlement("u1")
    assert e.trial_start == T0 + 3 * DAY and e.trial_end == T0 + 17 * DAY


def test_the_clock_starts_once_and_cannot_be_restarted_by_new_stories_retries_or_refunds(env):
    L = mk(env)
    L.reserve_video("u1", "story-A-op")
    L.settle_video("u1", "story-A-op")
    started = L.get_entitlement("u1").trial_end
    env[1].advance(5 * DAY)
    L.reserve_video("u1", "story-B-op")                         # a different Story
    L.settle_video("u1", "story-B-op")
    assert L.get_entitlement("u1").trial_end == started
    assert L.refund_video("u1", "story-B-op", "render_failed", render_attempts=2) == "refunded"
    assert L.get_entitlement("u1").trial_end == started        # a refund never resets or re-arms it
    L.reserve_video("u1", "story-A-op-retry")
    assert L.get_entitlement("u1").trial_end == started


def test_bounded_pre_video_analysis_and_what_happens_when_all_30_are_used_before_the_first_video(env):
    L = mk(env)
    for i in range(30):
        L.reserve_moment("u1", f"m{i}")
        L.settle_moment("u1", f"m{i}")
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.trial_end) == (0, None)               # no clock yet, nothing left to analyse
    with pytest.raises(BillingDenied) as ei:
        L.reserve_moment("u1", "m-new")
    assert ei.value.code == MOMENT_ALLOWANCE_EXHAUSTED and ei.value.action == "subscribe"
    assert ei.value.snapshot["upgrade"]["blocking"] is True
    h = L.reserve_video("u1", "op1")                           # the 2 video credits are untouched: the user can still create
    assert h.charged
    L.settle_video("u1", "op1")
    assert L.get_entitlement("u1").trial_end == T0 + 14 * DAY  # the clock starts now, at the first video
    assert not L.reserve_moment("u1", "m3").charged            # already-analysed Moments stay usable and free


def test_trial_state_survives_a_new_ledger_instance(env):
    mk(env).reserve_video("u1", "op1")
    mk(env).settle_video("u1", "op1")
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
    L = mk(env)
    for i in range(2):
        L.reserve_video("u1", f"op{i}")
    before = count_items(env, "u1")
    with pytest.raises(BillingDenied):
        L.reserve_video("u1", "op-x")
    assert count_items(env, "u1") == before          # the cancelled transaction left no orphan operation record


def test_store_failure_is_a_store_error_not_a_denial(env):
    def boom(real, *a, **kw):
        raise RuntimeError("ddb down")

    broken = Wrapped(env.ddb, transact_write_items=boom)
    with pytest.raises(BillingStoreError):
        BillingLedger(ddb=broken, table=env.table, clock=env.clock).reserve_video("u1", "op1")


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
    env[1].advance(L.cfg.moment_stale_s + 1)
    h = L.reserve_moment("u1", "m1")
    assert h.charged and h.reason == "reclaimed"
    e = L.get_entitlement("u1")
    assert (e.m_avail, e.m_resv) == (29, 1)                       # still ONE reserved unit
    assert L.reclaim_stale_moments("u1") == 0


def test_reclaim_sweep_releases_abandoned_reservations(env):
    L = mk(env)
    L.reserve_moment("u1", "m1")
    L.reserve_moment("u1", "m2")
    env[1].advance(L.cfg.moment_stale_s + 5)
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


def test_plus_is_unlimited_while_active_and_writes_no_finite_totals(env):
    """Billing V2: no monthly limit, no hidden ceiling. 13th, 30th, 61st video and >100 new Moments: never a billing denial."""
    L = mk(env)
    plus(L)
    e = L.get_entitlement("u1")
    assert (e.plan, e.status, e.v_total, e.m_total) == ("plus", ST_PLUS_ACTIVE, 2, 30)     # no Plus totals written (starter's stay)
    assert e.unlimited is False and e.unlimited_at(env.clock()) is True                     # derived, never stored
    for i in range(61):
        h = L.reserve_video("u1", f"op{i}")
        assert h.reason == "unlimited" and h.owns and not h.charged
        assert L.settle_video("u1", f"op{i}") == "settled"
    for i in range(120):
        assert L.reserve_moment("u1", f"m{i}").owns
        assert L.settle_moment("u1", f"m{i}", result="{}", version="v1") == "settled"
    v = L.entitlement_view("u1")
    assert v["unlimited"] is True and v["videos"] is None and v["moments"] is None
    assert v["capabilities"]["video_generation"] == "unlimited" and v["capabilities"]["subscription"]["status"] == "active"
    renew(L)
    assert L.get_entitlement("u1").period_id == "p2" and L.reserve_video("u1", "after-renewal").reason == "unlimited"


def test_plus_keeps_operation_records_for_idempotency_and_attribution(env):
    """B3: an unlimited Plus takes the SAME record transitions (one record per operation, idempotent, releasable)."""
    L = mk(env)
    plus(L)
    assert L.reserve_video("u1", "op1").owns
    dup = L.reserve_video("u1", "op1")                            # duplicate submit / SQS redelivery
    assert not dup.owns and dup.reason == "idempotent"
    assert L.release_video("u1", "op1") == "released"
    assert L.reserve_video("u1", "op1").owns                      # a retried operation re-opens the same record
    assert L.settle_video("u1", "op1") == "settled" and L.settle_video("u1", "op1") == "noop"
    rec = env.ddb.get_item(TableName=env.table, Key={"story_user_id": {"S": "u1"},
                                                     "quota_period": {"S": f"billing#v#{reservation_id('op1')}"}})["Item"]
    assert rec["b_state"]["S"] == "settled" and "b_unmetered" in rec
    e = L.get_entitlement("u1")
    assert (e.v_resv, e.v_used) == (0, 0)                         # no counter leg for an unmetered record


def test_legacy_finite_plus_reservation_settled_after_v2_does_not_leave_a_stuck_reservation(env):
    """B3: a reservation taken by a pre-V2 finite Plus (counter taken) and settled after V2 (derived unlimited) still runs its
    counter leg, decided from the RECORD, so b_v_resv cannot stay stuck."""
    L = mk(env)
    plus(L)
    # simulate a pre-V2 finite Plus entitlement with an open metered reservation
    env.ddb.update_item(TableName=env.table, Key={"story_user_id": {"S": "u1"}, "quota_period": {"S": "billing#entitlement"}},
                        UpdateExpression="SET b_v_total = :t, b_v_avail = :a, b_v_resv = :r, b_v_used = :z",
                        ExpressionAttributeValues={":t": {"N": "12"}, ":a": {"N": "11"}, ":r": {"N": "1"}, ":z": {"N": "0"}})
    env.ddb.update_item(TableName=env.table, Key={"story_user_id": {"S": "u1"},
                                                  "quota_period": {"S": f"billing#v#{reservation_id('legacy')}"}},
                        UpdateExpression="SET b_state = :rs, b_kind = :k, b_period = :p, b_updated = :now",
                        ExpressionAttributeValues={":rs": {"S": "reserved"}, ":k": {"S": "video"}, ":p": {"S": "p1"},
                                                   ":now": {"N": str(T0)}})
    assert L.settle_video("u1", "legacy") == "settled"
    e = L.get_entitlement("u1")
    assert (e.v_resv, e.v_used) == (0, 1)
    assert L.entitlement_view("u1")["videos"] is None              # legacy counters are not shown and not a limit
    assert L.reserve_video("u1", "next").reason == "unlimited"


def test_an_unmetered_record_never_decrements_a_counter_it_did_not_take(env):
    """B3 reverse case: a record reserved while unlimited, finished after the account became finite (grandfather rollback)."""
    L = mk(env)
    L.grandfather("u1", cutoff="c1")
    assert L.reserve_video("u1", "op1").owns
    assert L.revoke_grandfather("u1", "c1") == "reverted"
    assert L.release_video("u1", "op1") == "released"             # no TransactionCanceled loop, no BillingStoreError
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv) == (2, 0) and invariant(e, "video")


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
        assert ei.value.code == SUBSCRIPTION_REQUIRED                 # never credits/allowance/trial wording for Plus
    v = L.entitlement_view("u1")
    assert v["unlimited"] is False and v["capabilities"]["subscription"]["status"] == "expired"
    rec = env.ddb.get_item(TableName=env.table, Key={"story_user_id": {"S": "u1"},
                                                     "quota_period": {"S": f"billing#v#{reservation_id('op1')}"}})["Item"]
    assert rec["b_state"]["S"] == "settled"                           # delivered work untouched


def test_a_lapsed_plus_account_is_shown_no_starter_counters_but_free_and_admin_are(env):
    """S1: stale starter counters on an expired Plus record must not reach the client."""
    L = mk(env)
    plus(L)
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 31 * DAY)
    v = L.entitlement_view("u1")
    assert v["videos"] is None and v["moments"] is None and v["capabilities"]["subscription"]["status"] == "expired"
    f = L.entitlement_view("free-user")
    assert f["plan"] == "free_starter" and f["videos"]["remaining"] == 2 and f["moments"] is not None
    L.admin_grant("u2", videos=5, moments=50, reason="support")
    assert L.entitlement_view("u2")["videos"]["total"] == 5


def test_unlimited_is_never_granted_at_or_after_the_period_end(env):
    """B4: expiry is checked before any unlimited shortcut, at the exact instant."""
    L = mk(env)
    plus(L, end=T0 + 30 * DAY)
    env[1].advance(30 * DAY)                                          # exactly period_end: still active
    assert L.reserve_video("u1", "at-end").reason == "unlimited"
    env[1].advance(1)
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "after-end")
    assert ei.value.code == SUBSCRIPTION_REQUIRED
    assert L.get_entitlement("u1").unlimited_at(env.clock()) is False


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
    assert L.reserve_video("u1", "op1").reason == "unlimited"
    env[1].advance(3 * DAY)
    with pytest.raises(BillingDenied) as ei:
        L.reserve_video("u1", "op2")
    assert ei.value.code == SUBSCRIPTION_REQUIRED


def test_resubscribing_after_expiry_restores_unlimited(env):
    L = mk(env)
    plus(L)
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 31 * DAY)
    plus(L, period="p9", start=T0 + 40 * DAY, end=T0 + 70 * DAY, ts=T0 + 40 * DAY)
    env[1].advance(41 * DAY)
    assert L.reserve_video("u1", "op1").reason == "unlimited"


def test_free_user_upgrading_becomes_unlimited_and_loses_the_trial_gate(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    L.reserve_video("u1", "op2")
    L.settle_video("u1", "op2")
    with pytest.raises(BillingDenied):
        L.reserve_video("u1", "op3")                                  # the Free starter is spent
    plus(L)
    e = L.get_entitlement("u1")
    assert e.plan == "plus" and e.cfg == L.cfg.config_version == "billing-config/4"
    env[1].advance(20 * DAY)                                      # past the old trial end: irrelevant for Plus
    assert L.reserve_video("u1", "op3").reason == "unlimited"


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

def test_refund_returns_one_credit_once_and_is_capped_per_period(env):
    L = mk(env)
    L.admin_grant("u1", videos=12, moments=10, reason="support")      # finite paid-style plan (Plus is unlimited in V2)
    for i in range(5):
        L.reserve_video("u1", f"op{i}")
        L.settle_video("u1", f"op{i}")
    assert L.refund_video("u1", "op0", "render_failed", render_attempts=2) == "refunded"
    assert L.refund_video("u1", "op0", "render_failed", render_attempts=2) == "noop"             # once per operation
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_avail, e.refunds) == (4, 8, 1) and invariant(e, "video")
    assert L.refund_video("u1", "op1", "x", render_attempts=2) == "refunded"
    assert L.refund_video("u1", "op2", "x", render_attempts=2) == "refunded"
    assert L.refund_video("u1", "op3", "x", render_attempts=2) == "not_eligible:refund_cap"       # 3 per period


def test_an_unlimited_plus_video_has_nothing_to_refund(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    assert L.refund_video("u1", "op1", "render_failed", render_attempts=2) == "not_eligible:period_or_plan"


def test_refund_requires_a_settled_recent_operation_in_the_same_period(env):
    L = mk(env)
    plus(L)
    assert L.refund_video("u1", "nope", "x", render_attempts=2) == "not_eligible:unknown_operation"
    L.reserve_video("u1", "op1")
    assert L.refund_video("u1", "op1", "x", render_attempts=2) == "not_eligible:not_settled"
    L.settle_video("u1", "op1")
    env[1].advance(L.cfg.refund_window_s + 1)
    assert L.refund_video("u1", "op1", "x", render_attempts=2) == "not_eligible:window_elapsed"


def test_refund_is_blocked_after_the_period_rolls_over(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    renew(L)
    assert L.refund_video("u1", "op1", "x", render_attempts=2) == "not_eligible:period_or_plan"


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


def test_unset_mode_is_off_and_valid_modes_are_accepted(monkeypatch):
    from billing import billing_mode
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)
    assert billing_mode() == "off"
    for m in ("off", "observe", "enforce", " Enforce "):
        monkeypatch.setenv("STORY_BILLING_MODE", m)
        assert billing_mode() == m.strip().lower()


@pytest.mark.parametrize("bad", ["", "enforced", "ON", "true", "1", "disabled", "observe,enforce"])
def test_an_explicitly_invalid_mode_raises_instead_of_silently_disabling_billing(monkeypatch, bad):
    from billing import BillingConfigError, billing_mode, validate_billing_config
    monkeypatch.setenv("STORY_BILLING_MODE", bad)
    with pytest.raises(BillingConfigError):
        billing_mode()
    with pytest.raises(BillingConfigError):
        validate_billing_config()


def test_the_removed_plans_override_is_rejected_at_startup(monkeypatch):
    from billing import BillingConfigError, validate_billing_config
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)
    monkeypatch.setenv("STORY_BILLING_PLANS_JSON", '{"plus": {"videos": 999}}')
    with pytest.raises(BillingConfigError):
        validate_billing_config()
    monkeypatch.delenv("STORY_BILLING_PLANS_JSON")
    assert validate_billing_config() == "off"
    assert not hasattr(BillingConfig(), "plus")                                # Billing V2: Plus has no finite allowance
    assert BillingConfig().free_starter == PlanLimits(videos=2, moments=30)


# ---- forced interleaving: the atomic guard, not luck or speed, prevents overspend -----------------------------

def racing(env, n):
    """Holds the first n entitlement reads at a barrier so every thread decides from the SAME stale snapshot before any of
    them writes: the worst-case check-then-write interleaving. Works on both backends."""
    state = {"hits": 0, "armed": False}
    barrier, gate = threading.Barrier(n), threading.Lock()

    def get_item(real, TableName, Key, **kw):
        out = real(TableName=TableName, Key=Key, **kw)
        if state["armed"] and Key["quota_period"]["S"].endswith("entitlement"):
            with gate:
                state["hits"] += 1
                mine = state["hits"] <= n
            if mine:
                barrier.wait(timeout=10)
        return out

    return Wrapped(env.ddb, get_item=get_item), state


@pytest.mark.parametrize("kind", ["video", "moment"])
def test_stale_snapshot_race_cannot_overspend(env, kind):
    n = 12
    ddb, state = racing(env, n)
    L = BillingLedger(ddb=ddb, table=env.table, clock=env.clock, cfg=BillingConfig(free_starter=PlanLimits(videos=2, moments=3)))
    L.ensure_entitlement("u1")
    state["armed"] = True
    won = []

    def go(i):
        try:
            h = L.reserve_video("u1", f"op{i}") if kind == "video" else L.reserve_moment("u1", f"m{i}")
            won.append(h.charged)
        except BillingDenied:
            pass

    run_threads(go, [(i,) for i in range(n)])
    cap = 2 if kind == "video" else 3
    assert sum(won) == min(n, cap)
    e = L.get_entitlement("u1")
    assert invariant(e, kind) and (e.v_avail if kind == "video" else e.m_avail) >= 0


def test_stale_snapshot_race_on_the_last_credit_lets_exactly_one_through(env):
    n = 6
    ddb, state = racing(env, n)
    L = BillingLedger(ddb=ddb, table=env.table, clock=env.clock, cfg=BillingConfig(free_starter=PlanLimits(videos=1, moments=1)))
    L.ensure_entitlement("u1")
    state["armed"] = True
    won = []

    def go(i):
        try:
            won.append(L.reserve_video("u1", f"op{i}").charged)
        except BillingDenied:
            pass

    run_threads(go, [(i,) for i in range(n)])
    assert sum(won) == 1 and L.get_entitlement("u1").v_avail == 0


# ---- refund safety ---------------------------------------------------------------------------------------------------

def test_a_refund_needs_evidence_the_stored_plan_was_re_rendered(env):
    L = mk(env)
    L.admin_grant("u1", videos=5, moments=5, reason="support")
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    assert L.refund_video("u1", "op1", "render_failed") == "not_eligible:insufficient_evidence"                   # no claim of retries
    assert L.refund_video("u1", "op1", "render_failed", render_attempts=1) == "not_eligible:insufficient_evidence"
    assert L.get_entitlement("u1").v_used == 1                                                                    # nothing moved
    assert L.refund_video("u1", "op1", "render_failed", render_attempts=2, client_build="1.0(42)") == "refunded"
    rec = env.ddb.get_item(TableName=env.table, Key={"story_user_id": {"S": "u1"},
                                                     "quota_period": {"S": f"billing#v#{reservation_id('op1')}"}})["Item"]
    assert rec["b_refund_attempts"]["N"] == "2" and rec["b_refund_build"]["S"] == "1.0(42)"   # audit evidence is kept


def test_free_starter_gets_one_refund_not_a_loop_of_free_videos(env):
    L = mk(env)
    for op in ("a", "b"):
        L.reserve_video("u1", op)
        L.settle_video("u1", op)
    assert L.refund_video("u1", "a", "render_failed", render_attempts=2) == "refunded"
    assert L.refund_video("u1", "b", "render_failed", render_attempts=2) == "not_eligible:refund_cap"
    assert L.entitlement_view("u1")["refunds"] == {"used": 1, "allowed": 1}


def test_a_refund_for_another_accounts_or_an_unbilled_operation_is_impossible(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    assert L.refund_video("u2", "op1", "render_failed", render_attempts=2) == "not_eligible:unknown_operation"   # another account
    assert L.refund_video("u1", "never-billed", "render_failed", render_attempts=2) == "not_eligible:unknown_operation"
    L.grandfather("u3")
    L.reserve_video("u3", "opx")                                                                                  # unlimited: unmetered record
    L.settle_video("u3", "opx")
    assert L.refund_video("u3", "opx", "render_failed", render_attempts=2) == "not_eligible:period_or_plan"
    assert L.get_entitlement("u1").v_used == 1


def test_concurrent_refund_claims_for_one_operation_refund_once(env):
    L = mk(env)
    L.admin_grant("u1", videos=5, moments=5, reason="support")
    L.reserve_video("u1", "op1")
    L.settle_video("u1", "op1")
    out = []
    run_threads(lambda: out.append(L.refund_video("u1", "op1", "render_failed", render_attempts=2)), [()] * 8)
    assert out.count("refunded") == 1 and set(out) <= {"refunded", "noop"}
    e = L.get_entitlement("u1")
    assert (e.v_used, e.refunds) == (0, 1) and invariant(e, "video")


# ---- grandfathering cohort and rollback ------------------------------------------------------------------------------

def test_grandfathering_records_its_cohort_and_can_be_rolled_back_for_exactly_that_cohort(env):
    L = mk(env)
    L.grandfather("a", cutoff="2026-12-01")
    L.grandfather("a", cutoff="2026-12-01")                                  # idempotent re-run
    L.grandfather("b", cutoff="2026-11-01")
    L.ensure_entitlement("c")                                                # a later signup: a normal Free starter
    assert L.get_entitlement("a").plan == "beta_grandfathered" and L.get_entitlement("c").plan == "free_starter"
    assert L.revoke_grandfather("a", "2099-01-01") == "noop"                 # wrong cohort: untouched
    assert L.revoke_grandfather("c", "2026-12-01") == "noop"                 # never grandfathered
    assert L.revoke_grandfather("a", "2026-12-01") == "reverted"
    assert L.revoke_grandfather("a", "2026-12-01") == "noop"                 # idempotent
    a = L.get_entitlement("a")
    assert (a.plan, a.unlimited, a.v_avail, a.m_avail, a.trial_end) == ("free_starter", False, 2, 30, None)
    assert L.get_entitlement("b").plan == "beta_grandfathered"               # the other cohort is unaffected
    assert L.reserve_video("a", "op1").charged                               # and limits apply again


def test_a_grandfathered_account_that_moved_to_a_paid_plan_is_never_rolled_back(env):
    L = mk(env)
    L.grandfather("a", cutoff="2026-12-01")
    L.admin_grant("a", videos=5, moments=5, reason="support")
    assert L.revoke_grandfather("a", "2026-12-01") == "noop"
    assert L.get_entitlement("a").plan == "admin_granted"


# ---- worker/recovery and period-attribution scenarios (run on DynamoDB Local too) ------------------------------------

def test_a_cancelled_job_releases_its_reservation_through_reconciliation(env):
    L = mk(env)
    L.reserve_video("u1", "op1")
    assert L.reconcile_video_job("u1", "op1", "cancelled") == "released"
    assert L.reconcile_video_job("u1", "op1", "cancelled") == "noop"
    e = L.get_entitlement("u1")
    assert (e.v_avail, e.v_resv, e.v_used) == (2, 0, 0)
    assert L.reserve_video("u1", "op1").charged                              # a re-opened operation can reserve again


def test_a_reservation_keeps_the_period_it_was_charged_in_after_a_renewal(env):
    L = mk(env)
    plus(L)
    L.reserve_video("u1", "slow")
    renew(L)
    L.settle_video("u1", "slow")
    rec = env.ddb.get_item(TableName=env.table, Key={"story_user_id": {"S": "u1"},
                                                     "quota_period": {"S": f"billing#v#{reservation_id('slow')}"}})["Item"]
    assert rec["b_period"]["S"] == "p1" and rec["b_state"]["S"] == "settled"          # historical attribution preserved
    assert L.get_entitlement("u1").period_id == "p2"


def test_a_plus_that_lapses_after_submit_still_runs_the_job_authorized_at_submit(env):
    """Worker re-authorization finds the record reserved at submit and does not re-decide on the lapsed entitlement."""
    L = mk(env)
    plus(L)
    assert L.reserve_video("u1", "queued").owns                    # API submit
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 1)                     # lapses while the job waits in the queue
    h = L.reserve_video("u1", "queued")                            # worker _billing_authorize_job
    assert h.reason == "idempotent"
    assert L.reconcile_video_job("u1", "queued", "completed") == "settled"
    with pytest.raises(BillingDenied):
        L.reserve_video("u1", "new-after-lapse")                   # a NEW video needs the subscription


def test_a_grandfathered_tester_who_buys_plus_shows_active_and_rollback_keeps_the_subscription(env):
    """S8: the purchase is recorded beside the grandfathered plan; a cohort rollback converts the account to Plus."""
    L = mk(env)
    L.grandfather("u1", cutoff="c1")
    plus(L, end=T0 + 30 * DAY)
    e = L.get_entitlement("u1")
    assert e.plan == "beta_grandfathered" and e.sub_status == ST_PLUS_ACTIVE and e.orig_txn == "otx-1"
    v = L.entitlement_view("u1")
    assert v["capabilities"]["subscription"] == {"status": "active", "ends_at": T0 + 30 * DAY} and v["unlimited"] is True
    assert L.revoke_grandfather("u1", "c1") == "reverted"
    e = L.get_entitlement("u1")
    assert (e.plan, e.status, e.period_id, e.period_end) == ("plus", ST_PLUS_ACTIVE, "p1", T0 + 30 * DAY)
    assert L.reserve_video("u1", "op1").reason == "unlimited"
    plus(L, status=ST_PLUS_EXPIRED, ts=T0 + 31 * DAY)               # Apple events keep applying to the converted account
    assert L.get_entitlement("u1").status == ST_PLUS_EXPIRED


def test_a_grandfathered_rollback_without_an_active_subscription_is_unchanged(env):
    L = mk(env)
    L.grandfather("u1", cutoff="c1")
    plus(L, end=T0 + DAY)
    env[1].advance(2 * DAY)                                         # the side subscription has lapsed
    assert L.revoke_grandfather("u1", "c1") == "reverted"
    assert L.get_entitlement("u1").plan == "free_starter"


def test_out_of_order_entitlement_events_converge_regardless_of_arrival_order(env):
    import itertools
    events = [dict(status=ST_PLUS_ACTIVE, period="p1", start=T0, end=T0 + 30 * DAY, ts=100),
              dict(status=ST_PLUS_ACTIVE, period="p2", start=T0 + 30 * DAY, end=T0 + 60 * DAY, ts=200),
              dict(status=ST_PLUS_EXPIRED, period="p2", start=T0 + 30 * DAY, end=T0 + 60 * DAY, ts=300)]
    finals = set()
    for n, order in enumerate(itertools.permutations(events)):
        L = mk(env)
        for e in order:
            plus(L, f"perm{n}", period=e["period"], start=e["start"], end=e["end"], ts=e["ts"], status=e["status"])
        got = L.get_entitlement(f"perm{n}")
        finals.add((got.status, got.period_id))
    assert finals == {(ST_PLUS_EXPIRED, "p2")}       # every one of the 6 arrival orders ends in the newest state


def test_idempotent_replay_of_the_whole_lifecycle_changes_nothing(env):
    L = mk(env)
    for _ in range(3):
        L.reserve_video("u1", "op1")
        L.settle_video("u1", "op1")
        L.reserve_moment("u1", "m1~fabc")
        L.settle_moment("u1", "m1~fabc")
    e = L.get_entitlement("u1")
    assert (e.v_used, e.v_resv, e.m_used, e.m_resv) == (1, 0, 1, 0) and invariant(e, "video") and invariant(e, "moment")


# ---- IAM surface: the billing hot path needs no permission beyond what the usage table already grants -----------------

def test_the_whole_billing_lifecycle_uses_only_get_update_and_transact(env):
    """The API and worker roles already hold dynamodb:GetItem, UpdateItem and TransactWriteItems on the usage table (quota module).
    Reservations, settlement, release, refund, renewal, grandfathering, refresh and Apple binding must need nothing else (no Query,
    no Scan, no PutItem). `reclaim_stale_moments` is the only Query user and is NOT on any request path or automatic sweep."""
    used = set()

    class Rec:
        def __init__(self, inner):
            self._i = inner

        def __getattr__(self, name):
            real = getattr(self._i, name)
            if callable(real):
                def call(*a, **kw):
                    used.add(name)
                    return real(*a, **kw)
                return call
            return real

    L = BillingLedger(ddb=Rec(env.ddb), table=env.table, clock=env.clock)
    L.reserve_video("u1", "op1"); L.settle_video("u1", "op1"); L.reserve_video("u1", "op2"); L.release_video("u1", "op2")
    L.reserve_moment("u1", "m1~fabc", attrs={"b_fp": {"S": "abc"}}); L.settle_moment("u1", "m1~fabc", result="{}", version="v1")
    L.read_moment("u1", "m1~fabc"); L.begin_refresh("u1", "m1~fabc", "c"); L.finish_refresh("u1", "m1~fabc", "{}", "v2")
    L.refund_video("u1", "op1", "render_failed", render_attempts=2)
    L.apply_subscription("u1", status=ST_PLUS_ACTIVE, period_id="p1", period_start=T0, period_end=T0 + 30 * DAY, event_ts=1)
    L.bind_apple_transaction("otx", "u1"); L.get_or_create_apple_account_token("u1"); L.entitlement_view("u1")
    L.grandfather("u2", cutoff="2026-12-01"); L.revoke_grandfather("u2", "2026-12-01")
    assert used <= {"get_item", "update_item", "transact_write_items"}, used


def test_stale_moment_sweep_works_when_query_is_permitted_and_is_a_silent_noop_when_it_is_not(env):
    L = mk(env)
    L.reserve_moment("u1", "m1~fa"); L.reserve_moment("u1", "m2~fb")
    env[1].advance(L.cfg.moment_stale_s + 5)

    def denied(real, *a, **kw):
        raise RuntimeError("AccessDeniedException: not authorized to perform dynamodb:Query")

    assert BillingLedger(ddb=Wrapped(env.ddb, query=denied), table=env.table, clock=env.clock).reclaim_stale_moments("u1") == 0
    assert L.get_entitlement("u1").m_resv == 2                                # nothing released without Query...
    assert L.reserve_moment("u1", "m1~fa").reason == "reclaimed"             # ...yet the SAME Moment is reclaimed on retry, uncharged
    assert L.reclaim_stale_moments("u1") == 1                                 # and with Query the other one is swept
    e = L.get_entitlement("u1")
    assert (e.m_resv, e.m_avail) == (1, 29)
