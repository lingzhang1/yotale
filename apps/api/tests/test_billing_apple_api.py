"""B2 HTTP surface: POST /v1/billing/transactions (authenticated) and POST /v1/billing/apple-notifications (public, signature
only), driven with the REAL verifier against a minted test chain. No Apple network, no AWS."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "billing" / "tests"))
import apple_fixtures as fx  # noqa: E402

from app.main import create_app  # noqa: E402
from billing import BillingLedger  # noqa: E402
from billing.apple import SANDBOX, AppleBilling, AppStoreVerifier  # noqa: E402
from billing.fakes import FakeDDB  # noqa: E402
from tests.test_billing_gate import FakeIdentity, FakeVerifier, _auth  # noqa: E402

T0 = 1_800_000_000
MS = 1000


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_ENVIRONMENT", "beta")
    monkeypatch.delenv("STORY_BILLING_MODE", raising=False)       # billing OFF: Apple endpoints must still work
    chain = fx.make_chain()
    ledger = BillingLedger(ddb=FakeDDB(), table="t", clock=lambda: T0)
    verifier = AppStoreVerifier((SANDBOX,), roots_dir=fx.write_root(chain, tmp_path / "roots"), online_checks=False)
    app = create_app()
    app.state._jwt_verifier_override = FakeVerifier()
    app.state._identity_store_override = FakeIdentity()
    app.state._apple_billing_override = AppleBilling(ledger, verifier, environments=(SANDBOX,), clock=lambda: T0)

    class R:
        pass
    r = R()
    r.c, r.chain, r.ledger = TestClient(app), chain, ledger
    r.token = lambda sub: ledger.get_or_create_apple_account_token(f"story-{sub}")
    r.txn = lambda tok, **kw: fx.sign(chain, fx.txn_payload(token=tok, purchase_ms=T0 * MS, expires_ms=(T0 + 30 * 86400) * MS,
                                                            signed_ms=T0 * MS, **kw))
    return r


def post_txn(rig, sub, signed):
    return rig.c.post("/v1/billing/transactions", headers=_auth(sub), json={"signed_transaction": signed})


def test_transactions_requires_authentication(rig):
    assert rig.c.post("/v1/billing/transactions", json={"signed_transaction": "x"}).status_code == 401


def test_purchase_grants_plus_even_while_billing_mode_is_off(rig):
    r = post_txn(rig, "u1", rig.txn(rig.token("u1")))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "applied" and body["entitlement"]["plan"] == "plus" and body["entitlement"]["status"] == "plus_active"
    # live ledger, not the shadow one
    assert rig.ledger.get_entitlement("story-u1").plan == "plus"


@pytest.mark.parametrize("signed,status,code", [
    ("", 422, None),
    ("eyJhbGciOiJub25lIn0.e30.", 422, "invalid_signed_data"),
])
def test_garbage_transaction_is_rejected(rig, signed, status, code):
    r = post_txn(rig, "u1", signed)
    assert r.status_code == status
    if code:
        assert r.json()["error"] == code


def test_client_supplied_plan_price_or_expiry_is_ignored(rig):
    r = rig.c.post("/v1/billing/transactions", headers=_auth("u1"), json={
        "signed_transaction": rig.txn(rig.token("u1")), "plan": "pro", "videos": 9999, "expires_at": 4_000_000_000, "price": "0.00"})
    assert r.status_code == 200 and r.json()["entitlement"]["videos"]["total"] == 12


def test_other_accounts_purchase_and_foreign_binding(rig):
    t1 = rig.token("u1")
    rig.token("u2")
    signed = rig.txn(t1)
    assert post_txn(rig, "u1", signed).status_code == 200
    r = post_txn(rig, "u2", signed)                       # u2 replays u1's receipt
    assert r.status_code == 403 and r.json()["error"] == "app_account_token_mismatch"
    assert rig.ledger.get_entitlement("story-u2") is None or rig.ledger.get_entitlement("story-u2").plan != "plus"


def test_missing_app_account_token_is_rejected(rig):
    rig.token("u1")
    r = post_txn(rig, "u1", rig.txn(None))
    assert r.status_code == 422 and r.json()["error"] == "missing_app_account_token"


def test_wrong_product_and_wrong_environment_are_rejected(rig):
    tok = rig.token("u1")
    assert post_txn(rig, "u1", rig.txn(tok, product="com.lingzhang.story.pro.monthly")).json()["error"] == "product_not_allowed"
    assert post_txn(rig, "u1", rig.txn(tok, env="Production")).json()["error"] == "wrong_environment"


# ---- notifications ----------------------------------------------------------------------------------------------
def note(rig, ntype, tok, *, uuid="11111111-1111-4111-8111-111111111111", subtype=None, signed_s=T0 + 40, txn_kw=None):
    txn = fx.txn_payload(token=tok, purchase_ms=T0 * MS, expires_ms=(T0 + 30 * 86400) * MS, signed_ms=signed_s * MS,
                         **(txn_kw or {}))
    p = fx.notification_payload(rig.chain, ntype=ntype, subtype=subtype, uuid=uuid, txn=txn, signed_ms=signed_s * MS)
    return fx.sign(rig.chain, p)


def test_notification_endpoint_is_reachable_without_a_bearer_token(rig):
    tok = rig.token("u1")
    rig.ledger.index_apple_token("story-u1", tok)
    r = rig.c.post("/v1/billing/apple-notifications", json={"signedPayload": note(rig, "SUBSCRIBED", tok, subtype="INITIAL_BUY")})
    assert r.status_code == 200 and r.json()["outcome"] == "applied_active"
    assert rig.ledger.get_entitlement("story-u1").plan == "plus"


def test_notification_forgery_is_rejected_and_changes_nothing(rig):
    tok = rig.token("u1")
    rig.ledger.index_apple_token("story-u1", tok)
    attacker = fx.make_chain()
    forged = fx.sign(attacker, fx.notification_payload(attacker, ntype="SUBSCRIBED", txn=fx.txn_payload(token=tok)))
    for body in ({"signedPayload": forged}, {"signedPayload": "garbage"}, {"signedPayload": 7}, {}):
        r = rig.c.post("/v1/billing/apple-notifications", json=body)
        assert r.status_code in (422,), (body, r.status_code)
    assert rig.ledger.get_entitlement("story-u1") is None or rig.ledger.get_entitlement("story-u1").plan != "plus"


def test_duplicate_notification_delivery_is_idempotent(rig):
    tok = rig.token("u1")
    rig.ledger.index_apple_token("story-u1", tok)
    n = note(rig, "SUBSCRIBED", tok)
    assert rig.c.post("/v1/billing/apple-notifications", json={"signedPayload": n}).json()["outcome"] == "applied_active"
    assert rig.c.post("/v1/billing/apple-notifications", json={"signedPayload": n}).json()["outcome"] == "duplicate"


def test_unprovisioned_environment_returns_503_not_a_grant(monkeypatch):
    monkeypatch.delenv("STORY_USER_USAGE_TABLE", raising=False)
    app = create_app()
    app.state._jwt_verifier_override = FakeVerifier()
    app.state._identity_store_override = FakeIdentity()
    c = TestClient(app)
    assert c.post("/v1/billing/transactions", headers=_auth("u1"), json={"signed_transaction": "x"}).status_code == 503
    assert c.post("/v1/billing/apple-notifications", json={"signedPayload": "x"}).status_code == 503
