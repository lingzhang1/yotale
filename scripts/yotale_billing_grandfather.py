#!/usr/bin/env python3
"""Grandfather existing beta accounts into the `beta_grandfathered` (unlimited) billing entitlement.

MUST be run (by the owner, per environment) BEFORE `STORY_BILLING_MODE=enforce` is turned on. Otherwise an existing
beta tester would be created as a Free starter on their first request after the flip.

Dry-run by default: it only prints what it would change. `--apply` writes. It never deletes anything, is idempotent,
and only touches accounts that already exist in the users table.

    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta            # dry run
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --apply
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --apply --exclude <story_user_id>

`--exclude` keeps an account OUT (it will be treated as a normal Free starter), e.g. a test account used to rehearse
the real customer experience.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages"))

ELIGIBLE_BETA = ("invited", "eligible")


def select_accounts(user_items: list[dict], exclude: set[str]) -> list[str]:
    """Pure: which story_user_ids to grandfather. Active, beta-invited/eligible accounts only."""
    out = []
    for it in user_items:
        uid = it.get("story_user_id", {}).get("S")
        if not uid or uid in exclude:
            continue
        if it.get("account_status", {}).get("S", "active") != "active":
            continue
        if it.get("beta_access_status", {}).get("S", "eligible") not in ELIGIBLE_BETA:
            continue
        out.append(uid)
    return sorted(out)


def scan_users(ddb, table: str) -> list[dict]:
    items, kw = [], {"TableName": table}
    while True:
        r = ddb.scan(**kw)
        items += r.get("Items", [])
        if "LastEvaluatedKey" not in r:
            return items
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--environment", required=True, choices=["development", "beta", "gamma", "production"])
    ap.add_argument("--profile", required=True, help="AWS profile for the target account (SSO, created by you)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--apply", action="store_true", help="write the entitlements (default: dry run)")
    ap.add_argument("--exclude", action="append", default=[], help="story_user_id to leave as a Free starter")
    a = ap.parse_args(argv)

    import boto3
    from billing import BillingLedger

    sess = boto3.Session(profile_name=a.profile, region_name=a.region)
    ddb = sess.client("dynamodb")
    users_table, usage_table = f"story-{a.environment}-users", f"story-{a.environment}-user-usage"
    uids = select_accounts(scan_users(ddb, users_table), set(a.exclude))
    print(f"{a.environment}: {len(uids)} account(s) selected from {users_table}")
    for u in uids:
        print(f"  {u}")
    if not a.apply:
        print("dry run: nothing written. Re-run with --apply to grandfather these accounts.")
        return 0
    ledger = BillingLedger(ddb=ddb, table=usage_table)          # LIVE namespace: this is real entitlement state
    for u in uids:
        ent = ledger.grandfather(u)
        print(f"  grandfathered {u}: plan={ent.plan} unlimited={ent.unlimited}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
