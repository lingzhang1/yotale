"""Replay deletions into PITR-restored tables before they serve traffic (design rev 3, section 5.8).

A PITR restore always creates NEW tables, so restored `users` / `user-usage` rows serve nothing until the API is
deliberately repointed. Replay runs against those new tables, driven by the request items (which are never part
of the restore), not by the restored users-row status. Run with dry=True until it reports zero, then repoint.
"""
from __future__ import annotations

import dataclasses

from . import config as C
from .request_store import RequestStore, _s, is_conditional_failure
from .targets import Targets


def replay_after_restore(cfg: C.DeletionConfig, ddb, *, restored_users: str, restored_usage: str,
                         dry: bool = True) -> dict:
    store = RequestStore(ddb, cfg)
    rcfg = dataclasses.replace(cfg, users_table=restored_users, usage_table=restored_usage)
    t = Targets(rcfg, ddb, s3=None, cognito=None, dry=dry)
    report = {"requests": 0, "usage_rows": 0, "bindings": 0, "users_tombstoned": 0, "users_set_deleting": 0}
    for req in store.scan_requests():
        uid, state = req["uid"], req.get("state")
        report["requests"] += 1
        gkeys = set(store.children(uid, C.SK_GKEY)) | t.billing_identifiers(uid)
        report["bindings"] += t.bindings(uid, gkeys)
        if state in (C.STATE_COMPLETED, C.STATE_CLOSED) or req.get("phase") not in ("quiesce", "content"):
            # billing rows were already deleted live (phase >= billing): remove what the restore brought back.
            report["usage_rows"] += t.usage_partition(uid)
        row = t.user(uid)
        if row is None:
            continue
        status = (row.get("account_status") or {}).get("S", "active")
        if state in (C.STATE_COMPLETED, C.STATE_CLOSED):
            if status != "deleted":
                report["users_tombstoned"] += 1
                if not dry:
                    _force_status(ddb, restored_users, uid, "deleted", req["request_id"], tombstone=True)
        elif status != "deleting":
            report["users_set_deleting"] += 1
            if not dry:
                _force_status(ddb, restored_users, uid, "deleting", req["request_id"], tombstone=False)
    report["clean"] = all(report[k] == 0 for k in ("usage_rows", "bindings", "users_tombstoned", "users_set_deleting"))
    return report


def _force_status(ddb, table: str, uid: str, status: str, request_id: str, *, tombstone: bool) -> None:
    ue = "SET account_status = :s, deletion_request_id = :rid"
    if tombstone:
        ue += " REMOVE cognito_sub, verified_email"
    try:
        ddb.update_item(TableName=table, Key={"story_user_id": _s(uid)}, UpdateExpression=ue,
                        ConditionExpression="attribute_exists(story_user_id)",
                        ExpressionAttributeValues={":s": _s(status), ":rid": _s(request_id)})
    except Exception as e:  # noqa: BLE001 — a row deleted meanwhile needs nothing
        if not is_conditional_failure(e):
            raise
