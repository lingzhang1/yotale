"""Per-store enumerate/delete operations for one account (design rev 3, sections 2, 5.4, 5.5).

Every method is idempotent and returns how many things it FOUND (and, unless dry, deleted), so the same code
serves the deletion phases, the verification passes and the operator's dry-run counts. Nothing here imports the
billing gate or the Apple verifier: billing rows are addressed directly by their key shapes.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

from . import config as C
from .request_store import _n, _s, error_code, is_conditional_failure


class DeleteIncomplete(Exception):
    """A store reported items it could not delete; the phase fails and is retried."""


class Targets:
    def __init__(self, cfg: C.DeletionConfig, ddb, s3, cognito=None, *, dry: bool = False):
        self.cfg, self.ddb, self.s3, self.cognito, self.dry = cfg, ddb, s3, cognito, dry

    # ---- DynamoDB partitions -----------------------------------------------------------------------------
    def partition(self, table: str, pk: str, sk: str, uid: str) -> int:
        """Delete every item in partition `uid` of `table`, whatever its sort key. Paginated."""
        found = 0
        kw = {"TableName": table, "KeyConditionExpression": "#pk = :u", "ExpressionAttributeNames": {"#pk": pk},
              "ExpressionAttributeValues": {":u": _s(uid)}, "ConsistentRead": True}
        while True:
            resp = self.ddb.query(**kw)
            keys = [{pk: it[pk], sk: it[sk]} for it in resp.get("Items", [])]
            found += len(keys)
            if not self.dry:
                self._batch_delete(table, keys)
            if not resp.get("LastEvaluatedKey"):
                return found
            if self.dry:
                kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            # when deleting, re-query from the start: the deleted page is gone, so the next page is first

    def _batch_delete(self, table: str, keys: list[dict]) -> None:
        for i in range(0, len(keys), 25):
            pending = [{"DeleteRequest": {"Key": k}} for k in keys[i:i + 25]]
            for attempt in range(5):
                resp = self.ddb.batch_write_item(RequestItems={table: pending})
                pending = (resp.get("UnprocessedItems") or {}).get(table) or []
                if not pending:
                    break
                time.sleep(0.05 * (2 ** attempt))
            if pending:
                raise DeleteIncomplete(f"{table}: {len(pending)} unprocessed deletes")

    def content_partitions(self, uid: str) -> dict:
        c = self.cfg
        return {"media": self.partition(c.media_table, "story_user_id", "cloud_media_id", uid),
                "stories": self.partition(c.stories_table, "story_user_id", "story_id", uid),
                "understanding": self.partition(c.understanding_table, "story_user_id", "moment_id", uid)}

    def usage_partition(self, uid: str) -> int:
        return self.partition(self.cfg.usage_table, "story_user_id", "quota_period", uid)

    def rate_limits(self, uid: str) -> int:
        return self.partition(self.cfg.rate_limit_table, "story_user_id", "rl_key", uid)

    # ---- S3 ------------------------------------------------------------------------------------------------
    def prefix(self, bucket: str, prefix: str) -> int:
        found, token = 0, None
        while True:
            kw = {"Bucket": bucket, "Prefix": prefix}
            if token and self.dry:
                kw["ContinuationToken"] = token
            resp = self.s3.list_objects_v2(**kw)
            keys = [o["Key"] for o in resp.get("Contents", []) or []]
            found += len(keys)
            if keys and not self.dry:
                for i in range(0, len(keys), 1000):
                    r = self.s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]],
                                                                      "Quiet": True})
                    if r.get("Errors"):
                        raise DeleteIncomplete(f"s3 {prefix}: {len(r['Errors'])} objects not deleted "
                                               f"({r['Errors'][0].get('Code')})")
            if not resp.get("IsTruncated"):
                return found
            token = resp.get("NextContinuationToken")

    def uploads(self, bucket: str, prefix: str) -> int:
        """Abort every unfinished multipart upload under `prefix` (parts sent after an abort fail)."""
        found, km, um = 0, None, None
        while True:
            kw = {"Bucket": bucket, "Prefix": prefix}
            if km:
                kw.update(KeyMarker=km, UploadIdMarker=um)
            resp = self.s3.list_multipart_uploads(**kw)
            ups = resp.get("Uploads", []) or []
            found += len(ups)
            if not self.dry:
                for u in ups:
                    self.s3.abort_multipart_upload(Bucket=bucket, Key=u["Key"], UploadId=u["UploadId"])
            if not resp.get("IsTruncated"):
                return found
            km, um = resp.get("NextKeyMarker"), resp.get("NextUploadIdMarker")

    def media_objects(self, uid: str) -> dict:
        b = self.cfg.media_bucket
        out = {}
        for p in (f"media/{uid}/", f"evidence/{uid}/"):
            out[f"uploads:{p.split('/')[0]}"] = self.uploads(b, p)
            out[f"s3:{p.split('/')[0]}"] = self.prefix(b, p)
        return out

    # ---- edit-plan jobs and staging ---------------------------------------------------------------------
    def scan_jobs(self, uid: str) -> list[tuple[str, str]]:
        """(job_id, status) for every job row owned by uid. Scan filtered on owner: the table has no user index
        (the edit-plan reconcile already scans the same way)."""
        out, kw = [], {"TableName": self.cfg.jobs_table, "FilterExpression": "#o = :u",
                       "ExpressionAttributeNames": {"#o": "owner"}, "ExpressionAttributeValues": {":u": _s(uid)}}
        while True:
            resp = self.ddb.scan(**kw)
            out.extend((it["job_id"]["S"], (it.get("status") or {}).get("S", "")) for it in resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def cancel_job(self, job_id: str) -> bool:
        """queued|running -> cancel_requested (the same transition as JobStore.request_cancel)."""
        if self.dry:
            return False
        try:
            self.ddb.update_item(
                TableName=self.cfg.jobs_table, Key={"job_id": _s(job_id)},
                UpdateExpression="SET #s = :cr, updated_at = :now",
                ConditionExpression="attribute_exists(job_id) AND (#s = :q OR #s = :r)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":cr": _s("cancel_requested"), ":now": _n(time.time()),
                                           ":q": _s("queued"), ":r": _s("running")})
            return True
        except Exception as e:  # noqa: BLE001
            if is_conditional_failure(e):
                return False
            raise

    def job(self, job_id: str, uid: str) -> int:
        """Delete staging `jobs/<job_id>/` (derivable from the id after the row is gone), then the row, only if
        the row is this account's. Returns objects + rows found."""
        found = self.prefix(self.cfg.staging_bucket, f"{C.STAGING_PREFIX}{job_id}/")
        it = self.ddb.get_item(TableName=self.cfg.jobs_table, Key={"job_id": _s(job_id)}, ConsistentRead=True).get("Item")
        if it and (it.get("owner") or {}).get("S") == uid:
            found += 1
            if not self.dry:
                try:
                    self.ddb.delete_item(TableName=self.cfg.jobs_table, Key={"job_id": _s(job_id)},
                                         ConditionExpression="attribute_not_exists(job_id) OR #o = :u",
                                         ExpressionAttributeNames={"#o": "owner"},
                                         ExpressionAttributeValues={":u": _s(uid)})
                except Exception as e:  # noqa: BLE001
                    if not is_conditional_failure(e):
                        raise
        return found

    # ---- billing (design 2.2) ---------------------------------------------------------------------------
    def billing_identifiers(self, uid: str) -> set[str]:
        """Global binding keys ("token#<t>" / "txn#<id>") that point at uid. Always includes the b_uid Query of
        __apple_txn__, because submit_transaction binds a transaction before checking it is live, so the
        entitlement row may never mention it. shortcut: the two global-partition Queries read the whole
        partition; record every bound id on the account row at bind time when volume grows."""
        keys: set[str] = set()
        t = self.cfg.usage_table
        acct = self._get_usage(uid, C.BILLING_ACCOUNT_SK)
        tok = (acct.get("b_apple_token") or {}).get("S")
        if tok:
            keys.add("token#" + tok)   # the index key uses the stored token verbatim (index_apple_token)
        for sk in (C.BILLING_ENTITLEMENT_SK, "billing-shadow#entitlement"):
            orig = (self._get_usage(uid, sk).get("b_orig_txn") or {}).get("S")
            if orig:
                keys.add("txn#" + orig)
        for pk, sk_prefix, kind in ((C.APPLE_TOKEN_PK, C.TOKEN_SK_PREFIX, "token#"),
                                    (C.APPLE_TXN_PK, C.TXN_SK_PREFIX, "txn#")):
            kw = {"TableName": t, "KeyConditionExpression": "story_user_id = :p AND begins_with(quota_period, :x)",
                  "FilterExpression": "b_uid = :u",
                  "ExpressionAttributeValues": {":p": _s(pk), ":x": _s(sk_prefix), ":u": _s(uid)}}
            while True:
                resp = self.ddb.query(**kw)
                keys.update(kind + it["quota_period"]["S"][len(sk_prefix):] for it in resp.get("Items", []))
                if not resp.get("LastEvaluatedKey"):
                    break
                kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return keys

    def _get_usage(self, pk: str, sk: str) -> dict:
        return self.ddb.get_item(TableName=self.cfg.usage_table,
                                 Key={"story_user_id": _s(pk), "quota_period": _s(sk)}).get("Item") or {}

    def bindings(self, uid: str, gkeys: Iterable[str]) -> int:
        """Delete global bindings that still point at uid: ALL token bindings first, then transaction bindings,
        so a notification arriving in between cannot re-bind a transaction through the token index
        (_resolve_uid, packages/billing/apple.py). Conditional on b_uid = uid: never another account's row."""
        found = 0
        ordered = sorted(gkeys, key=lambda k: 0 if k.startswith("token#") else 1)
        for g in ordered:
            kind, _, val = g.partition("#")
            pk, sk = ((C.APPLE_TOKEN_PK, C.TOKEN_SK_PREFIX + val) if kind == "token"
                      else (C.APPLE_TXN_PK, C.TXN_SK_PREFIX + val))
            key = {"story_user_id": _s(pk), "quota_period": _s(sk)}
            it = self.ddb.get_item(TableName=self.cfg.usage_table, Key=key, ConsistentRead=True).get("Item")
            if not it or (it.get("b_uid") or {}).get("S") != uid:
                continue
            found += 1
            if self.dry:
                continue
            try:
                self.ddb.delete_item(TableName=self.cfg.usage_table, Key=key, ConditionExpression="b_uid = :u",
                                     ExpressionAttributeValues={":u": _s(uid)})
            except Exception as e:  # noqa: BLE001
                if not is_conditional_failure(e):
                    raise
        return found

    # ---- users row -----------------------------------------------------------------------------------------
    def user(self, uid: str) -> Optional[dict]:
        return self.ddb.get_item(TableName=self.cfg.users_table, Key={"story_user_id": _s(uid)},
                                 ConsistentRead=True).get("Item")

    def tombstone(self, uid: str, request_id: str, now: int) -> str:
        """users row -> tombstone (design 3). Never creates a row; accepts an existing tombstone."""
        if self.dry:
            return "dry"
        try:
            self.ddb.update_item(
                TableName=self.cfg.users_table, Key={"story_user_id": _s(uid)},
                UpdateExpression="SET account_status = :d, deleted_at = if_not_exists(deleted_at, :now), "
                                 "deletion_request_id = :rid REMOVE cognito_sub, verified_email",
                ConditionExpression="attribute_exists(story_user_id) AND "
                                    "(account_status = :deleting OR account_status = :d)",
                ExpressionAttributeValues={":d": _s("deleted"), ":deleting": _s("deleting"), ":now": _n(now),
                                           ":rid": _s(request_id)})
            return "tombstoned"
        except Exception as e:  # noqa: BLE001
            if not is_conditional_failure(e):
                raise
            return "absent" if self.user(uid) is None else "not_deleting"

    # ---- Cognito ---------------------------------------------------------------------------------------------
    def cognito_username(self, sub: str) -> Optional[str]:
        """The admin-API username for a sub: try the sub itself, then ListUsers by sub. None = no such user."""
        pool = self.cfg.user_pool_id
        try:
            u = self.cognito.admin_get_user(UserPoolId=pool, Username=sub)
            attrs = {a["Name"]: a["Value"] for a in u.get("UserAttributes", [])}
            if attrs.get("sub") == sub:
                return u["Username"]
        except Exception as e:  # noqa: BLE001
            if error_code(e) != "UserNotFoundException":
                raise
        resp = self.cognito.list_users(UserPoolId=pool, Filter=f'sub = "{_quote(sub)}"', Limit=1)
        users = resp.get("Users", [])
        return users[0]["Username"] if users else None

    def cognito_quiesce(self, sub: Optional[str]) -> str:
        if not sub:
            return "no_sub"
        name = self.cognito_username(sub)
        if name is None:
            return "absent"
        if self.dry:
            return "present"
        for op in (self.cognito.admin_disable_user, self.cognito.admin_user_global_sign_out):
            try:
                op(UserPoolId=self.cfg.user_pool_id, Username=name)
            except Exception as e:  # noqa: BLE001
                if error_code(e) != "UserNotFoundException":
                    raise
                return "absent"
        return "disabled"

    def cognito_delete(self, sub: Optional[str]) -> str:
        if not sub:
            return "no_sub"
        name = self.cognito_username(sub)
        if name is None:
            return "absent"
        if self.dry:
            return "present"
        try:
            self.cognito.admin_delete_user(UserPoolId=self.cfg.user_pool_id, Username=name)
        except Exception as e:  # noqa: BLE001
            if error_code(e) != "UserNotFoundException":
                raise
        return "deleted"


def _quote(v: str) -> str:
    """A Cognito sub is a UUID; refuse anything that could break out of the ListUsers filter string."""
    if any(ch in v for ch in '"\\') or len(v) > 128:
        raise ValueError("unexpected characters in cognito sub")
    return v
