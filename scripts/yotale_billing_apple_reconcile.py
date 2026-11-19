#!/usr/bin/env python3
"""Reconcile ONE account's Plus entitlement with Apple (recovers a missed or failed App Store Server Notification).

Run by the OWNER from their machine with their own AWS profile; the App Store Server API key is read from Secrets Manager into
memory only (never printed or written). DRY-RUN BY DEFAULT: it asks Apple for the subscription's current signed status, verifies
the signatures, prints the decision and writes nothing.

    # dry run (reads Apple + the ledger)
    python3 scripts/yotale_billing_apple_reconcile.py --environment beta --profile yotale-beta --user-id <story_user_id>
    # apply (same ledger guards as a webhook: an older state can never overwrite a newer one)
    python3 scripts/yotale_billing_apple_reconcile.py --environment beta --profile yotale-beta --user-id <story_user_id> --apply --confirm beta

The account must already own the original transaction (bound when the app posted the purchase). Reconciling never attaches a
transaction to an account. Secret: JSON with key_id, issuer_id, private_key (default name YoTale-Apple-Key, --secret-id to change).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--environment", required=True, choices=["development", "beta", "production"])
    ap.add_argument("--profile", default=None)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--secret-id", default="YoTale-Apple-Key")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    a = ap.parse_args(argv)
    if a.apply and a.confirm != a.environment:
        print("refusing: --apply requires --confirm <environment>", file=sys.stderr)
        return 2

    import boto3
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient
    from appstoreserverlibrary.models.Environment import Environment
    from billing import BillingLedger
    from billing.apple import BUNDLE_ID, AppleBilling, AppStoreVerifier, allowed_environments

    session = boto3.Session(profile_name=a.profile, region_name=a.region)
    secret = json.loads(session.client("secretsmanager").get_secret_value(SecretId=a.secret_id)["SecretString"])
    envs = allowed_environments(a.environment)
    env = Environment(envs[0])
    ledger = BillingLedger(ddb=session.client("dynamodb"), table=f"story-{a.environment}-user-usage", region=a.region)
    ent = ledger.get_entitlement(a.user_id)
    orig = getattr(ent, "orig_txn", None) if ent else None
    if not orig:
        print("no Apple original transaction is bound to this account; nothing to reconcile")
        return 0
    if ledger.apple_txn_owner(orig) != a.user_id:
        print("original transaction is not bound to this account; refusing")
        return 3

    client = AppStoreServerAPIClient(secret["private_key"].encode(), secret["key_id"], secret["issuer_id"], BUNDLE_ID, env)
    verifier = AppStoreVerifier(envs)
    svc = AppleBilling(ledger, verifier, environments=envs)
    resp = client.get_all_subscription_statuses(orig)
    decided = []
    for group in resp.data or []:
        for item in group.lastTransactions or []:
            if str(item.originalTransactionId) != str(orig):
                continue
            t = verifier.verify_transaction(item.signedTransactionInfo)
            renewal = None
            if item.signedRenewalInfo:
                from billing.apple import Renewal, _s
                r = verifier._try(lambda v: v.verify_and_decode_renewal_info(item.signedRenewalInfo))
                renewal = Renewal(grace_expires_s=_s(r.gracePeriodExpiresDate), in_billing_retry=bool(r.isInBillingRetryPeriod))
            decided.append((int(item.status.value), t, renewal))
    if not decided:
        print("Apple returned no status for this transaction")
        return 0
    for code, t, renewal in decided:
        print(f"apple status={code} period_end={t.expires_s} product={t.product_id} env={t.environment}")
        if a.apply:
            print("result:", svc.apply_status(a.user_id, code, t, renewal))
        else:
            print("dry run: no write (use --apply --confirm", a.environment + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
