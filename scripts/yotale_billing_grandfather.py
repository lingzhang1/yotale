#!/usr/bin/env python3
"""Grandfather the beta accounts that existed BEFORE a chosen rollout cutoff into the `beta_grandfathered` (unlimited) entitlement.

Run by the OWNER, per environment, BEFORE `STORY_BILLING_MODE=enforce` is turned on (otherwise an existing tester would become a Free
starter on their first request). DRY-RUN BY DEFAULT: it reads, prints counts, and writes nothing. It never deletes anything.

Selection is explicit and never open-ended:
  * the account must exist in the users table with `created_at` STRICTLY BEFORE --cutoff (UTC date, required, no default),
  * `account_status = active` and `beta_access_status` in (invited, eligible),
  * not listed in --exclude (e.g. a rehearsal account that should experience the real Free starter).
Accounts created at or after the cutoff are NEVER grandfathered, so future signups are normal Free starters.

    # 1. dry run (reads the users table and entitlements; writes nothing)
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --cutoff 2026-12-01
    # 2. apply (idempotent; --confirm must repeat the environment)
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --cutoff 2026-12-01 --apply --confirm beta
    # 3. rollback for exactly this cohort (dry run first, then --apply --confirm)
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --cutoff 2026-12-01 --rollback
    python3 scripts/yotale_billing_grandfather.py --environment beta --profile yotale-beta --cutoff 2026-12-01 --rollback --apply --confirm beta

Re-running --apply changes nothing (`changed: 0`). A rollback returns an account to a fresh Free starter ONLY if it was grandfathered with
this exact cutoff and has not since moved to another plan. By default only counts are printed; --show-ids prints 8-character id prefixes.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages"))

ELIGIBLE_BETA = ("invited", "eligible")


def cutoff_ts(cutoff: str) -> int:
    d = datetime.datetime.strptime(cutoff, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    return int(d.timestamp())


def classify_users(user_items: list[dict], cutoff: str, exclude: set[str]) -> dict:
    """Pure: bucket every users-table row. Returns {"selected": [uid...], "counts": {...}}."""
    ts = cutoff_ts(cutoff)
    counts = {"scanned": 0, "selected": 0, "excluded_by_flag": 0, "not_active": 0, "not_beta_eligible": 0,
              "missing_created_at": 0, "created_at_or_after_cutoff": 0}
    selected: list[str] = []
    for it in user_items:
        counts["scanned"] += 1
        uid = it.get("story_user_id", {}).get("S")
        if not uid:
            continue
        if uid in exclude:
            counts["excluded_by_flag"] += 1
        elif it.get("account_status", {}).get("S", "active") != "active":
            counts["not_active"] += 1
        elif it.get("beta_access_status", {}).get("S", "eligible") not in ELIGIBLE_BETA:
            counts["not_beta_eligible"] += 1
        elif "N" not in it.get("created_at", {}):
            counts["missing_created_at"] += 1                       # cannot prove it pre-dates the cutoff: never grandfathered
        elif int(float(it["created_at"]["N"])) >= ts:
            counts["created_at_or_after_cutoff"] += 1               # a future/new signup: a normal Free starter
        else:
            selected.append(uid)
            counts["selected"] += 1
    return {"selected": sorted(selected), "counts": counts}


def plan_changes(selected: list[str], entitlements: dict, cutoff: str) -> dict:
    """Pure: what --apply would do for the selected accounts, given their CURRENT entitlements (None = no record yet)."""
    out = {"create_and_grandfather": [], "convert_free_starter": [], "already_this_cohort": [], "skip_other_plan": []}
    for uid in selected:
        ent = entitlements.get(uid)
        if ent is None:
            out["create_and_grandfather"].append(uid)
        elif ent.plan == "beta_grandfathered":
            (out["already_this_cohort"] if ent.gf_cutoff == cutoff else out["skip_other_plan"]).append(uid)
        elif ent.plan == "free_starter":
            out["convert_free_starter"].append(uid)
        else:
            out["skip_other_plan"].append(uid)                      # a paid/admin account is never overwritten
    return out


def plan_rollback(user_ids: list[str], entitlements: dict, cutoff: str) -> list[str]:
    return sorted(u for u in user_ids if (e := entitlements.get(u)) is not None and e.plan == "beta_grandfathered" and e.gf_cutoff == cutoff)


def scan_users(ddb, table: str) -> list[dict]:
    items, kw = [], {"TableName": table}
    while True:
        r = ddb.scan(**kw)
        items += r.get("Items", [])
        if "LastEvaluatedKey" not in r:
            return items
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def _ids(ids: list[str], show: bool) -> str:
    return ", ".join(i[:8] for i in ids) if show else "(ids hidden; use --show-ids)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--environment", required=True, choices=["development", "beta", "gamma", "production"])
    ap.add_argument("--profile", required=True, help="AWS profile for the target account (SSO, created by you)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--cutoff", required=True, help="UTC date YYYY-MM-DD; only accounts created strictly before it are grandfathered")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--rollback", action="store_true", help="revert the cohort grandfathered with this exact cutoff")
    ap.add_argument("--confirm", default="", help="must equal --environment when --apply is used")
    ap.add_argument("--exclude", action="append", default=[], help="story_user_id to leave as a Free starter")
    ap.add_argument("--show-ids", action="store_true")
    a = ap.parse_args(argv)
    try:
        cutoff_ts(a.cutoff)
    except ValueError:
        print("--cutoff must be YYYY-MM-DD", file=sys.stderr)
        return 2
    if a.apply and a.confirm != a.environment:
        print(f"--apply requires --confirm {a.environment}", file=sys.stderr)
        return 2

    import boto3
    from billing import BillingLedger
    ddb = boto3.Session(profile_name=a.profile, region_name=a.region).client("dynamodb")
    users_table, usage_table = f"story-{a.environment}-users", f"story-{a.environment}-user-usage"
    ledger = BillingLedger(ddb=ddb, table=usage_table)          # LIVE namespace: this is real entitlement state
    users = scan_users(ddb, users_table)
    print(f"environment: {a.environment}   cutoff: {a.cutoff}T00:00:00Z   mode: {'APPLY' if a.apply else 'DRY RUN'}"
          f"{'   action: ROLLBACK' if a.rollback else ''}")

    if a.rollback:
        all_ids = [u["story_user_id"]["S"] for u in users if u.get("story_user_id", {}).get("S")]
        ents = {u: ledger.get_entitlement(u) for u in all_ids}                       # read-only
        targets = plan_rollback(all_ids, ents, a.cutoff)
        print(f"users scanned: {len(all_ids)}   grandfathered with this cutoff: {len(targets)}")
        print(f"  would revert to a fresh Free starter: {_ids(targets, a.show_ids)}")
        if not a.apply:
            print("dry run: nothing written.")
            return 0
        reverted = sum(1 for u in targets if ledger.revoke_grandfather(u, a.cutoff) == "reverted")
        print(f"reverted: {reverted}   unchanged: {len(targets) - reverted}")
        return 0

    cls = classify_users(users, a.cutoff, set(a.exclude))
    ents = {u: ledger.get_entitlement(u) for u in cls["selected"]}                   # read-only: never creates a record
    changes = plan_changes(cls["selected"], ents, a.cutoff)
    for k, v in cls["counts"].items():
        print(f"  {k}: {v}")
    print("planned entitlement changes:")
    for k, v in changes.items():
        print(f"  {k}: {len(v)}  {_ids(v, a.show_ids) if v else ''}")
    would_change = len(changes["create_and_grandfather"]) + len(changes["convert_free_starter"])
    print(f"would change: {would_change}   (re-running --apply afterwards would change 0)")
    if not a.apply:
        print("dry run: nothing written. Review the counts, then re-run with --apply --confirm "
              f"{a.environment}.")
        return 0
    changed = 0
    for u in changes["create_and_grandfather"] + changes["convert_free_starter"]:
        ent = ledger.grandfather(u, cutoff=a.cutoff)
        changed += 1 if ent.plan == "beta_grandfathered" else 0
    print(f"changed: {changed}   already in cohort: {len(changes['already_this_cohort'])}   "
          f"skipped (other plan): {len(changes['skip_other_plan'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
