"""B2: the REAL verifier (appstoreserverlibrary) against a minted test chain: valid data passes, every forgery is rejected, and
Apple's production roots are pinned by fingerprint."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from billing.apple import (
    ROOTS_DIR, SANDBOX, PRODUCTION, AppStoreVerifier, InvalidSignature, WrongEnvironment, allowed_environments,
)

import apple_fixtures as fx

pytest.importorskip("appstoreserverlibrary")

TOKEN = "3b3f1f3e-8f4b-4f6e-9a55-0a1b2c3d4e5f"


@pytest.fixture()
def chain():
    return fx.make_chain()


def verifier(chain, tmp_path, envs=(SANDBOX,)):
    return AppStoreVerifier(envs, roots_dir=fx.write_root(chain, tmp_path / "roots"), online_checks=False)


def test_valid_transaction_is_decoded(chain, tmp_path):
    t = verifier(chain, tmp_path).verify_transaction(fx.sign(chain, fx.txn_payload(token=TOKEN)))
    assert t.original_transaction_id == "1000" and t.product_id == "com.lingzhang.story.plus.monthly"
    assert t.app_account_token == TOKEN and t.environment == SANDBOX
    assert t.expires_s == 1_802_592_000 and t.purchase_s == 1_800_000_000


def test_valid_notification_decodes_nested_transaction_and_renewal(chain, tmp_path):
    payload = fx.notification_payload(chain, ntype="DID_FAIL_TO_RENEW", subtype="GRACE_PERIOD",
                                      txn=fx.txn_payload(token=TOKEN),
                                      renewal={"gracePeriodExpiresDate": 1_801_000_000_000, "isInBillingRetryPeriod": True,
                                               "originalTransactionId": "1000", "environment": "Sandbox"})
    n = verifier(chain, tmp_path).verify_notification(fx.sign(chain, payload))
    assert n.type == "DID_FAIL_TO_RENEW" and n.subtype == "GRACE_PERIOD" and n.environment == SANDBOX
    assert n.txn.app_account_token == TOKEN and n.renewal.grace_expires_s == 1_801_000_000 and n.renewal.in_billing_retry


def test_chain_to_an_untrusted_root_is_rejected(chain, tmp_path):
    attacker = fx.make_chain()
    forged = fx.sign(attacker, fx.txn_payload(token=TOKEN))
    with pytest.raises(InvalidSignature):
        verifier(chain, tmp_path).verify_transaction(forged)         # valid structure, signed under the attacker's own root


def test_tampered_payload_is_rejected(chain, tmp_path):
    good = fx.sign(chain, fx.txn_payload(token=TOKEN))
    head, body, sig = good.split(".")
    other = fx.sign(chain, fx.txn_payload(token=TOKEN, expires_ms=9_999_999_999_000)).split(".")[1]
    with pytest.raises(InvalidSignature):
        verifier(chain, tmp_path).verify_transaction(f"{head}.{other}.{sig}")


def test_unsigned_alg_none_and_garbage_are_rejected(chain, tmp_path):
    v = verifier(chain, tmp_path)
    for bad in ("", "x", "a.b.c", "eyJhbGciOiJub25lIn0.e30.", "e" * 30000):
        with pytest.raises(InvalidSignature):
            v.verify_transaction(bad)
        with pytest.raises(InvalidSignature):
            v.verify_notification(bad)


def test_wrong_bundle_is_rejected(chain, tmp_path):
    with pytest.raises(InvalidSignature):
        verifier(chain, tmp_path).verify_transaction(fx.sign(chain, fx.txn_payload(token=TOKEN, bundle="com.evil.app")))


def test_production_data_on_a_sandbox_only_deployment_is_rejected_as_wrong_environment(chain, tmp_path):
    with pytest.raises(WrongEnvironment):
        verifier(chain, tmp_path, (SANDBOX,)).verify_transaction(fx.sign(chain, fx.txn_payload(token=TOKEN, env="Production")))


def test_sandbox_data_on_a_production_deployment_is_rejected(chain, tmp_path):
    with pytest.raises(WrongEnvironment):
        verifier(chain, tmp_path, (PRODUCTION,)).verify_transaction(fx.sign(chain, fx.txn_payload(token=TOKEN, env="Sandbox")))


def test_leaf_without_apple_marker_is_rejected(tmp_path):
    c = fx.make_chain(leaf_marker=False)
    with pytest.raises(InvalidSignature):
        verifier(c, tmp_path).verify_transaction(fx.sign(c, fx.txn_payload(token=TOKEN)))


# ---- pinned production roots --------------------------------------------------------------------------------------
PINNED = {   # SHA-256 of the DER certificate, as published at apple.com/certificateauthority
    "AppleRootCA-G2.cer": "c2b9b042dd57830e7d117dac55ac8ae19407d38e41d88f3215bc3a89 0444a050".replace(" ", ""),
    "AppleRootCA-G3.cer": "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179",
}


def test_bundled_apple_roots_match_pinned_fingerprints():
    found = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(ROOTS_DIR).glob("*.cer")}
    assert found == PINNED


def test_environment_mapping():
    assert allowed_environments("development") == allowed_environments("beta") == (SANDBOX,)
    assert allowed_environments("production") == allowed_environments("gamma") == (PRODUCTION,)
