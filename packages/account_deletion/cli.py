"""Operator CLI for account deletion (design rev 3, sections 5.8 and 5.10; decision 8.17).

    python -m account_deletion.cli --env dev --account <id> --user-pool-id <pool> [--profile P] <command>

Commands:
  count  --uid U                      read-only: what the account still holds in every store
  status --uid U                      read-only: the request item
  request --uid U --identity-checked --confirm-env ENV
                                      operator-initiated deletion (email request after the identity check);
                                      goes through the same acceptance transaction as the API
  resume --uid U --confirm-env ENV    run ready phases now (same lease; cannot skip the 70-minute delay)
  replay-after-restore --restored-users T --restored-usage T [--execute --confirm-env ENV]
                                      dry run by default; repoint the API only after it reports clean

Every mutating command requires --confirm-env equal to --env. There are no ad hoc delete commands.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import uuid

from . import config as C
from .replay import replay_after_restore
from .request_store import RequestStore, receipt_hash
from .targets import Targets
from .worker import Worker


def _clients(args):
    import boto3
    sess = boto3.Session(profile_name=args.profile, region_name=args.region)
    return sess.client("dynamodb"), sess.client("s3"), sess.client("cognito-idp")


def _require_env(args) -> None:
    if getattr(args, "confirm_env", None) != args.env:
        raise SystemExit(f"refusing: pass --confirm-env {args.env} to change data in {args.env}")


def count(cfg, ddb, s3, cognito, uid: str) -> dict:
    t = Targets(cfg, ddb, s3, cognito, dry=True)
    sub = ((t.user(uid) or {}).get("cognito_sub") or {}).get("S")
    out = {"users_row": (t.user(uid) or {}).get("account_status", {}).get("S", "absent") if t.user(uid) else "absent",
           "cognito": t.cognito_quiesce(sub)}
    out.update(t.content_partitions(uid))
    out.update(t.media_objects(uid))
    out["usage_rows"] = t.usage_partition(uid)
    out["rate_limit_rows"] = t.rate_limits(uid)
    out["bindings"] = t.bindings(uid, t.billing_identifiers(uid))
    jobs = t.scan_jobs(uid)
    out["jobs"] = len(jobs)
    out["staging_objects"] = sum(t.prefix(cfg.staging_bucket, f"{C.STAGING_PREFIX}{j}/") for j, _ in jobs)
    return out


def main(argv=None, *, clients=None) -> int:
    p = argparse.ArgumentParser(prog="account_deletion")
    p.add_argument("--env", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--user-pool-id", required=True)
    p.add_argument("--profile", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("count", "status", "request", "resume"):
        sp = sub.add_parser(name)
        sp.add_argument("--uid", required=True)
        if name in ("request", "resume"):
            sp.add_argument("--confirm-env")
        if name == "request":
            sp.add_argument("--identity-checked", action="store_true",
                            help="the requester replied from the account email and confirmed a fresh sign-in code")
    rp = sub.add_parser("replay-after-restore")
    rp.add_argument("--restored-users", required=True)
    rp.add_argument("--restored-usage", required=True)
    rp.add_argument("--execute", action="store_true")
    rp.add_argument("--confirm-env")
    args = p.parse_args(argv)

    cfg = C.DeletionConfig.for_env(args.env, account=args.account, region=args.region, user_pool_id=args.user_pool_id)
    ddb, s3, cognito = clients or _clients(args)
    now = int(time.time())
    if args.cmd == "count":
        out = count(cfg, ddb, s3, cognito, args.uid)
    elif args.cmd == "status":
        out = RequestStore(ddb, cfg).get(args.uid) or {"state": "none"}
        out.pop("receipt_hash", None)
    elif args.cmd == "request":
        _require_env(args)
        if not args.identity_checked:
            raise SystemExit("refusing: confirm the identity check (decision 8.17) with --identity-checked")
        rid = str(uuid.uuid4())
        res = RequestStore(ddb, cfg).accept(args.uid, rid, receipt_hash(secrets.token_hex(32)), now)
        out = {"outcome": res.outcome, "request_id": (res.request or {}).get("request_id")}
    elif args.cmd == "resume":
        _require_env(args)
        out = {"outcome": Worker(cfg, ddb, s3, cognito).process(args.uid, f"operator-{uuid.uuid4()}", force=True)}
    else:
        if args.execute:
            _require_env(args)
        out = replay_after_restore(cfg, ddb, restored_users=args.restored_users, restored_usage=args.restored_usage,
                                   dry=not args.execute)
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
