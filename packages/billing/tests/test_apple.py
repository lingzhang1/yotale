"""B2: Apple purchase verification policy, notification mapping and ordering, run on the in-memory double AND DynamoDB Local.

The verifier is replaced by a fake that returns already-decoded payloads: these tests prove OUR policy (ownership, binding,
mapping, ordering, idempotency). That Apple's signatures are really checked is proven in test_apple_verifier.py."""
from __future__ import annotations

import pytest

from billing import BillingConfig, BillingLedger
from billing.apple import (
    BUNDLE_ID, PLUS_PRODUCT_ID, PRODUCTION, SANDBOX, AccountTokenMismatch, AppleBilling, InvalidSignature, MissingAccountToken,
    Notification, ProductNotAllowed, Renewal, TransactionBound, Txn, WrongEnvironment,
)

T0 = 1_800_000_000
DAY = 86400
MONTH = 30 * DAY


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class FakeVerifier:
    """Maps an opaque string to a prepared Txn / Notification; anything else is a forged signature."""

    def __init__(self):
        self.txns: dict[str, Txn] = {}
        self.notes: dict[str, Notification] = {}

    def verify_transaction(self, signed):
        if signed not in self.txns:
            raise InvalidSignature("forged")
        return self.txns[signed]

    def verify_notification(self, signed):
        if signed not in self.notes:
            raise InvalidSignature("forged")
        return self.notes[signed]


def txn(token, *, orig="1000", tid="1000", start=T0, end=None, product=PLUS_PRODUCT_ID, env=SANDBOX, revoked=None,
        signed=None, bundle=BUNDLE_ID, typ="Auto-Renewable Subscription"):
    return Txn(original_transaction_id=orig, transaction_id=tid, product_id=product, bundle_id=bundle, environment=env,
               app_account_token=token, purchase_s=start, expires_s=end if end is not None else start + MONTH,
               revocation_s=revoked, signed_s=signed if signed is not None else start, type=typ)


@pytest.fixture()
def world(usage_backend):
    ddb, table, _ = usage_backend
    clock = Clock()
    ledger = BillingLedger(ddb=ddb, table=table, clock=clock)
    v = FakeVerifier()
    svc = AppleBilling(ledger, v, environments=(SANDBOX,), clock=clock)

    class W:
        pass
    w = W()
    w.ledger, w.v, w.svc, w.clock = ledger, v, svc, clock
    w.token = lambda uid: ledger.get_or_create_apple_account_token(uid)
    w.note_seq = 0

    def note(ntype, t, *, subtype=None, signed=None, renewal=None, env=SANDBOX):
        w.note_seq += 1
        key = f"n{w.note_seq}"
        w.v.notes[key] = Notification(uuid=f"uuid-{w.note_seq}", type=ntype, subtype=subtype,
                                      signed_s=signed if signed is not None else clock.t, environment=env, txn=t,
                                      renewal=renewal)
        return key
    w.note = note

    def sign(t):
        key = f"t{len(w.v.txns)}"
        w.v.txns[key] = t
        return key
    w.sign = sign
    return w


def not_plus(world, uid):
    e = world.ledger.get_entitlement(uid)
    return e is None or e.plan == "free_starter"


# ---- client-submitted transaction ----------------------------------------------------------------------------------
def test_valid_purchase_grants_plus_from_apple_dates(world):
    tok = world.token("u1")
    out = world.svc.submit_transaction("u1", world.sign(txn(tok)))
    e = out["entitlement"]
    assert out["result"] == "applied" and e["plan"] == "plus" and e["status"] == "plus_active"
    assert e["period"]["start"] == T0 and e["period"]["end"] == T0 + MONTH      # Apple's dates, not a calendar month
    assert e["videos"]["total"] == 12 and e["moments"]["total"] == 100
    assert e["apple_original_transaction_id"] == "1000"


def test_forged_or_unsigned_transaction_is_rejected(world):
    world.token("u1")
    with pytest.raises(InvalidSignature):
        world.svc.submit_transaction("u1", "eyJhbGciOiJub25lIn0.e30.")
    assert not_plus(world, "u1")


def test_repeated_submission_is_idempotent_and_never_resets_usage(world):
    tok = world.token("u1")
    s = world.sign(txn(tok))
    world.svc.submit_transaction("u1", s)
    world.ledger.reserve_video("u1", "op1")
    world.ledger.settle_video("u1", "op1")
    out = world.svc.submit_transaction("u1", s)             # restore purchases / reinstall posts the same transaction again
    assert out["entitlement"]["videos"]["used"] == 1 and out["entitlement"]["videos"]["remaining"] == 11


def test_wrong_account_token_is_rejected(world):
    world.token("u1")
    other = world.token("u2")
    with pytest.raises(AccountTokenMismatch):
        world.svc.submit_transaction("u1", world.sign(txn(other)))       # u2's purchase presented by u1
    assert not_plus(world, "u1")


def test_missing_account_token_is_rejected(world):
    world.token("u1")
    with pytest.raises(MissingAccountToken):
        world.svc.submit_transaction("u1", world.sign(txn(None)))


def test_one_transaction_cannot_entitle_two_accounts(world):
    tok1 = world.token("u1")
    s = world.sign(txn(tok1))
    world.svc.submit_transaction("u1", s)
    # u2 learns u1's token (it is just a UUID the client holds) and replays the same signed transaction as their own
    with pytest.raises(AccountTokenMismatch):
        world.svc.submit_transaction("u2", s)
    # even a token swap cannot bind the original transaction twice
    world.ledger.get_or_create_apple_account_token("u2")
    with pytest.raises((AccountTokenMismatch, TransactionBound)):
        world.svc.submit_transaction("u2", world.sign(txn(world.token("u2"), orig="1000", tid="1001")))
    assert not_plus(world, "u2")


@pytest.mark.parametrize("kw,exc", [
    ({"product": "com.lingzhang.story.pro.monthly"}, ProductNotAllowed),
    ({"env": PRODUCTION}, WrongEnvironment),
    ({"bundle": "com.someone.else"}, InvalidSignature),
    ({"typ": "Consumable"}, ProductNotAllowed),
])
def test_unaccepted_product_environment_bundle_type(world, kw, exc):
    tok = world.token("u1")
    with pytest.raises(exc):
        world.svc.submit_transaction("u1", world.sign(txn(tok, **kw)))
    assert not_plus(world, "u1")


def test_expired_or_revoked_transaction_never_writes(world):
    tok = world.token("u1")
    world.svc.submit_transaction("u1", world.sign(txn(tok, tid="1", start=T0 - 2 * MONTH, end=T0 + MONTH, signed=T0 - 2 * MONTH)))
    world.clock.t = T0 + 2 * MONTH
    # a client replaying an expired receipt, or a revoked one, must not downgrade OR upgrade anything
    before = world.ledger.get_entitlement("u1")
    r1 = world.svc.submit_transaction("u1", world.sign(txn(tok, tid="2", start=T0 - MONTH, end=T0 + MONTH * 1, signed=T0)))
    r2 = world.svc.submit_transaction("u1", world.sign(txn(tok, tid="3", start=T0 + MONTH, end=T0 + 3 * MONTH,
                                                           revoked=T0 + MONTH + 1, signed=T0 + MONTH)))
    after = world.ledger.get_entitlement("u1")
    assert r1["result"] == r2["result"] == "not_active" and after.ver == before.ver


def test_old_period_replay_cannot_reset_allowances(world):
    tok = world.token("u1")
    old = world.sign(txn(tok, tid="1", start=T0, end=T0 + MONTH, signed=T0))
    world.svc.submit_transaction("u1", old)
    world.clock.t = T0 + MONTH
    world.svc.submit_transaction("u1", world.sign(txn(tok, tid="2", start=T0 + MONTH, end=T0 + 2 * MONTH, signed=T0 + MONTH)))
    world.ledger.reserve_video("u1", "opA")
    world.ledger.settle_video("u1", "opA")
    # a transaction for the FIRST period, re-signed later with a fresher signature time, must not roll the period back
    world.clock.t = T0 + MONTH + 100
    world.svc.submit_transaction("u1", world.sign(txn(tok, tid="1", start=T0, end=T0 + MONTH + 200, signed=T0 + MONTH + 100)))
    e = world.ledger.entitlement_view("u1")
    assert e["period"]["id"].endswith(":2") and e["videos"]["used"] == 1


# ---- notifications -------------------------------------------------------------------------------------------------
def buy(world, uid="u1", **kw):
    tok = world.token(uid)
    world.svc.submit_transaction(uid, world.sign(txn(tok, **kw)))
    return tok


def test_renewal_notification_starts_new_period_and_resets_allowances(world):
    tok = buy(world)
    world.ledger.reserve_video("u1", "op1")
    world.ledger.settle_video("u1", "op1")
    world.clock.t = T0 + MONTH
    renewed = txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH, signed=T0 + MONTH)
    out = world.svc.handle_notification(world.note("DID_RENEW", renewed, signed=T0 + MONTH))
    assert out["outcome"] == "applied_active"
    e = world.ledger.entitlement_view("u1")
    assert e["period"]["start"] == T0 + MONTH and e["videos"]["used"] == 0 and e["videos"]["remaining"] == 12


def test_duplicate_notification_is_acknowledged_once(world):
    tok = buy(world)
    world.clock.t = T0 + MONTH
    key = world.note("DID_RENEW", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH), signed=T0 + MONTH)
    assert world.svc.handle_notification(key)["outcome"] == "applied_active"
    world.ledger.reserve_video("u1", "op2")
    world.ledger.settle_video("u1", "op2")
    assert world.svc.handle_notification(key)["outcome"] == "duplicate"        # redelivery must not reset the new period
    assert world.ledger.entitlement_view("u1")["videos"]["used"] == 1


def test_delayed_older_event_cannot_undo_a_newer_one(world):
    tok = buy(world)
    # expiry processed first (newer), then a delayed RENEW signed earlier arrives
    world.clock.t = T0 + 3 * MONTH
    world.svc.handle_notification(world.note("EXPIRED", txn(tok, end=T0 + MONTH), signed=T0 + 2 * MONTH))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_expired"
    late = txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 4 * MONTH, signed=T0 + MONTH)
    world.svc.handle_notification(world.note("DID_RENEW", late, signed=T0 + MONTH))     # older signed time
    assert world.ledger.entitlement_view("u1")["status"] == "plus_expired"


def test_grace_then_recovery_then_expiry(world):
    tok = buy(world)
    world.clock.t = T0 + MONTH + DAY
    grace_end = T0 + MONTH + 16 * DAY
    out = world.svc.handle_notification(world.note(
        "DID_FAIL_TO_RENEW", txn(tok, end=T0 + MONTH), subtype="GRACE_PERIOD", signed=T0 + MONTH + DAY,
        renewal=Renewal(grace_expires_s=grace_end, in_billing_retry=True)))
    assert out["outcome"] == "applied_grace"
    assert world.ledger.entitlement_view("u1")["status"] == "plus_grace"
    # billing recovers: the renewal arrives inside grace
    world.clock.t = T0 + MONTH + 3 * DAY
    world.svc.handle_notification(world.note(
        "DID_RENEW", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH, signed=T0 + MONTH + 3 * DAY),
        signed=T0 + MONTH + 3 * DAY))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_active"
    world.clock.t = T0 + 3 * MONTH
    world.svc.handle_notification(world.note("EXPIRED", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH),
                                             signed=T0 + 2 * MONTH + DAY))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_expired"


def test_billing_retry_without_grace_expires(world):
    tok = buy(world)
    world.clock.t = T0 + MONTH + DAY
    out = world.svc.handle_notification(world.note("DID_FAIL_TO_RENEW", txn(tok, end=T0 + MONTH), subtype=None,
                                                   signed=T0 + MONTH + DAY, renewal=Renewal(in_billing_retry=True)))
    assert out["outcome"] == "applied_expired"


def test_refund_revokes_current_period_but_old_period_refund_does_not(world):
    tok = buy(world)
    world.clock.t = T0 + MONTH
    world.svc.handle_notification(world.note("DID_RENEW", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH,
                                                              signed=T0 + MONTH), signed=T0 + MONTH))
    # refund of LAST month's charge: the current paid period stays active
    world.svc.handle_notification(world.note("REFUND", txn(tok, tid="1000", end=T0 + MONTH, revoked=T0 + MONTH + 5),
                                             signed=T0 + MONTH + 5))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_active"
    # refund of the CURRENT period revokes access immediately
    world.svc.handle_notification(world.note("REFUND", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH,
                                                           revoked=T0 + MONTH + 9), signed=T0 + MONTH + 9))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_expired"
    # and a refund reversal restores it
    world.svc.handle_notification(world.note("REFUND_REVERSED", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH),
                                             signed=T0 + MONTH + 20))
    assert world.ledger.entitlement_view("u1")["status"] == "plus_active"


def test_notification_before_app_posts_transaction_uses_token_index(world):
    tok = world.token("u1")             # the app asked for its token (entitlement read) before purchasing
    world.ledger.index_apple_token("u1", tok)
    out = world.svc.handle_notification(world.note("SUBSCRIBED", txn(tok), subtype="INITIAL_BUY", signed=T0))
    assert out["outcome"] == "applied_active" and world.ledger.entitlement_view("u1")["plan"] == "plus"


def test_notification_for_unknown_account_is_acknowledged_without_effect(world):
    out = world.svc.handle_notification(world.note("DID_RENEW", txn("00000000-0000-0000-0000-000000000000")))
    assert out["outcome"] == "unmatched"


def test_notification_cannot_attach_a_transaction_to_a_second_account(world):
    tok1 = buy(world, "u1")
    tok2 = world.token("u2")
    world.ledger.index_apple_token("u2", tok2)
    # an event naming u1's original transaction but carrying u2's token is ambiguous identity: acknowledged, no effect
    out = world.svc.handle_notification(world.note("DID_RENEW", txn(tok2, orig="1000", tid="1001", start=T0 + MONTH),
                                                   signed=T0 + MONTH))
    assert out["outcome"] == "unmatched"
    assert not_plus(world, "u2")


def test_forged_notification_and_wrong_environment_rejected(world):
    with pytest.raises(InvalidSignature):
        world.svc.handle_notification("not-a-real-jws")
    tok = world.token("u1")
    with pytest.raises(WrongEnvironment):
        world.svc.handle_notification(world.note("DID_RENEW", txn(tok, env=PRODUCTION), env=PRODUCTION))


def test_informational_notifications_change_nothing(world):
    tok = buy(world)
    before = world.ledger.get_entitlement("u1")
    for t in ("DID_CHANGE_RENEWAL_STATUS", "PRICE_INCREASE", "TEST", "REFUND_DECLINED", "CONSUMPTION_REQUEST"):
        assert world.svc.handle_notification(world.note(t, txn(tok)))["outcome"] == "info"
    assert world.ledger.get_entitlement("u1").ver == before.ver


def test_store_events_never_downgrade_grandfathered_or_admin_accounts(world):
    tok = world.token("u1")
    world.ledger.index_apple_token("u1", tok)
    world.ledger.grandfather("u1", "2026-11-19")
    world.svc.handle_notification(world.note("EXPIRED", txn(tok), signed=T0))
    assert world.ledger.get_entitlement("u1").plan == "beta_grandfathered"


def test_concurrent_notifications_converge(world):
    import threading
    tok = buy(world)
    world.clock.t = T0 + MONTH
    keys = [world.note("DID_RENEW", txn(tok, tid="1001", start=T0 + MONTH, end=T0 + 2 * MONTH), signed=T0 + MONTH)
            for _ in range(1)]
    keys += [keys[0]] * 5          # the same delivery arriving concurrently
    res, errs = [], []

    def run(k):
        try:
            res.append(world.svc.handle_notification(k)["outcome"])
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=run, args=(k,)) for k in keys]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    e = world.ledger.entitlement_view("u1")
    assert e["period"]["start"] == T0 + MONTH and e["videos"]["remaining"] == 12 and e["status"] == "plus_active"


# ---- reconciliation (apply_status) ---------------------------------------------------------------------------------
def test_reconcile_recovers_a_missed_expiry_and_a_missed_renewal(world):
    tok = buy(world)
    world.clock.t = T0 + 2 * MONTH
    t = txn(tok, end=T0 + MONTH)
    assert world.svc.apply_status("u1", 2, t, None) == "applied_expired"
    assert world.ledger.entitlement_view("u1")["status"] == "plus_expired"
    renewed = txn(tok, tid="1002", start=T0 + 2 * MONTH, end=T0 + 3 * MONTH)
    assert world.svc.apply_status("u1", 1, renewed, None) == "applied_active"
    assert world.ledger.entitlement_view("u1")["status"] == "plus_active"


def test_reconcile_grace_and_billing_retry(world):
    tok = buy(world)
    world.clock.t = T0 + MONTH + DAY
    t = txn(tok, end=T0 + MONTH)
    assert world.svc.apply_status("u1", 4, t, Renewal(grace_expires_s=T0 + MONTH + 10 * DAY)) == "applied_grace"
    assert world.ledger.entitlement_view("u1")["status"] == "plus_grace"
    assert world.svc.apply_status("u1", 3, t, None) == "applied_expired"          # billing retry without grace: no access


def test_reconcile_refuses_a_transaction_the_account_does_not_own(world):
    buy(world, "u1")
    tok2 = world.token("u2")
    with pytest.raises(TransactionBound):
        world.svc.apply_status("u2", 1, txn(tok2, orig="1000"), None)
