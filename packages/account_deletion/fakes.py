"""Test doubles for account deletion (tests only; never used in a deployed path).

FakeDDB is a multi-table DynamoDB double. It EVALUATES the real expression grammar through the billing fake's
evaluator (SET / ADD / REMOVE, if_not_exists, AND / OR / NOT, comparisons, attribute_exists,
attribute_not_exists, begins_with), so a test fails when an expression would fail or behave differently on real
DynamoDB. Key conditions are evaluated with the same evaluator. Query and Scan paginate with `page_size`, so
pagination bugs show up. FakeS3 and FakeCognito model only the calls the deletion worker makes.
"""
from __future__ import annotations

import copy
import threading
from typing import Optional

from billing.fakes import FakeClientError, apply_update, evaluate_condition

# table name -> (partition key, sort key or None)
DEFAULT_SCHEMAS = {
    "requests": ("pk", "sk"),
    "users": ("story_user_id", None),
    "claims": ("claim_key", None),
    "usage": ("story_user_id", "quota_period"),
    "media": ("story_user_id", "cloud_media_id"),
    "stories": ("story_user_id", "story_id"),
    "understanding": ("story_user_id", "moment_id"),
    "ratelimits": ("story_user_id", "rl_key"),
    "jobs": ("job_id", None),
}


def _check_values_used(values: dict, *texts: Optional[str]) -> None:
    text = " ".join(t for t in texts if t)
    for ph in values:
        if ph not in text:   # real DynamoDB rejects unused ExpressionAttributeValues
            raise ValueError(f"ValidationException: unused expression attribute value {ph}")


class FakeDDB:
    def __init__(self, schemas: Optional[dict] = None, page_size: int = 1000):
        self.schemas = dict(schemas or DEFAULT_SCHEMAS)
        self.tables: dict[str, dict[tuple, dict]] = {t: {} for t in self.schemas}
        self.page_size = page_size
        self.lock = threading.RLock()
        self.fail_next: dict[str, Exception] = {}   # op name -> exception raised once (failure injection)
        self.on_write = None                        # hook(op, table, key) called after each write (race injection)

    # ---- helpers ---------------------------------------------------------------------------------------
    def add_table(self, name: str, pk: str, sk: Optional[str] = None) -> None:
        self.schemas[name] = (pk, sk)
        self.tables.setdefault(name, {})

    def _k(self, table: str, key_or_item: dict) -> tuple:
        pk, sk = self.schemas[table]
        return (key_or_item[pk]["S"], key_or_item[sk]["S"] if sk else "")

    def _maybe_fail(self, op: str) -> None:
        exc = self.fail_next.pop(op, None)
        if exc is not None:
            raise exc

    def _written(self, op, table, key):
        if self.on_write:
            hook, self.on_write = self.on_write, None   # one-shot, and never re-entrant
            try:
                hook(op, table, key)
            finally:
                if self.on_write is None:
                    self.on_write = hook

    def put(self, table: str, item: dict) -> None:
        """Test seeding (no conditions)."""
        with self.lock:
            self.tables[table][self._k(table, item)] = copy.deepcopy(item)

    def count(self, table: str) -> int:
        return len(self.tables[table])

    # ---- DynamoDB API ----------------------------------------------------------------------------------
    def get_item(self, TableName, Key, ConsistentRead=False, **_):
        self._maybe_fail("get_item")
        with self.lock:
            it = self.tables[TableName].get(self._k(TableName, Key))
            return {"Item": copy.deepcopy(it)} if it else {}

    def put_item(self, TableName, Item, ConditionExpression=None, ExpressionAttributeNames=None,
                 ExpressionAttributeValues=None, **_):
        self._maybe_fail("put_item")
        with self.lock:
            self._put_locked(TableName, Item, ConditionExpression, ExpressionAttributeNames, ExpressionAttributeValues)
        self._written("put_item", TableName, Item)
        return {}

    def _put_locked(self, table, item, cond, names, values):
        names, values = names or {}, values or {}
        _check_values_used(values, cond)
        k = self._k(table, item)
        if not evaluate_condition(cond, self.tables[table].get(k) or {}, names, values):
            raise FakeClientError("ConditionalCheckFailedException")
        self.tables[table][k] = copy.deepcopy(item)

    def update_item(self, TableName, Key, UpdateExpression, ConditionExpression=None,
                    ExpressionAttributeNames=None, ExpressionAttributeValues=None, ReturnValues=None, **_):
        self._maybe_fail("update_item")
        with self.lock:
            item = self._update_locked(TableName, Key, UpdateExpression, ConditionExpression,
                                       ExpressionAttributeNames, ExpressionAttributeValues)
        self._written("update_item", TableName, Key)
        return {"Attributes": copy.deepcopy(item)} if ReturnValues == "ALL_NEW" else {}

    def _update_locked(self, table, key, ue, cond, names, values):
        names, values = names or {}, values or {}
        _check_values_used(values, ue, cond)
        k = self._k(table, key)
        existing = self.tables[table].get(k)
        if not evaluate_condition(cond, existing or {}, names, values):
            raise FakeClientError("ConditionalCheckFailedException")
        item = copy.deepcopy(existing) if existing is not None else copy.deepcopy(dict(key))
        apply_update(item, ue, names, values)
        self.tables[table][k] = item
        return item

    def delete_item(self, TableName, Key, ConditionExpression=None, ExpressionAttributeNames=None,
                    ExpressionAttributeValues=None, **_):
        self._maybe_fail("delete_item")
        with self.lock:
            self._delete_locked(TableName, Key, ConditionExpression, ExpressionAttributeNames, ExpressionAttributeValues)
        self._written("delete_item", TableName, Key)
        return {}

    def _delete_locked(self, table, key, cond, names, values):
        names, values = names or {}, values or {}
        _check_values_used(values, cond)
        k = self._k(table, key)
        if not evaluate_condition(cond, self.tables[table].get(k) or {}, names, values):
            raise FakeClientError("ConditionalCheckFailedException")
        self.tables[table].pop(k, None)

    def batch_write_item(self, RequestItems, **_):
        self._maybe_fail("batch_write_item")
        with self.lock:
            for table, reqs in RequestItems.items():
                if len(reqs) > 25:
                    raise ValueError("ValidationException: more than 25 requests in a batch")
                for r in reqs:
                    if "DeleteRequest" in r:
                        self.tables[table].pop(self._k(table, r["DeleteRequest"]["Key"]), None)
                    else:
                        it = r["PutRequest"]["Item"]
                        self.tables[table][self._k(table, it)] = copy.deepcopy(it)
        return {"UnprocessedItems": {}}

    def _page(self, table, matches, start, limit):
        ordered = sorted(matches, key=lambda kv: kv[0])
        if start:
            sk0 = self._k(table, start)
            ordered = [kv for kv in ordered if kv[0] > sk0]
        size = min(self.page_size, limit or self.page_size)
        page = ordered[:size]
        out = {"Items": [copy.deepcopy(v) for _, v in page], "Count": len(page)}
        if len(ordered) > size:
            pk, sk = self.schemas[table]
            last = page[-1][1]
            out["LastEvaluatedKey"] = {pk: last[pk], **({sk: last[sk]} if sk else {})}
        return out

    def query(self, TableName, KeyConditionExpression, ExpressionAttributeValues=None, FilterExpression=None,
              ExpressionAttributeNames=None, ExclusiveStartKey=None, Limit=None, ProjectionExpression=None,
              ConsistentRead=False, **_):
        self._maybe_fail("query")
        names, values = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        _check_values_used(values, KeyConditionExpression, FilterExpression)
        with self.lock:
            keyed = [(k, v) for k, v in self.tables[TableName].items()
                     if evaluate_condition(KeyConditionExpression, v, names, values)]
            out = self._page(TableName, keyed, ExclusiveStartKey, Limit)
            out["Items"] = [it for it in out["Items"] if evaluate_condition(FilterExpression, it, names, values)]
            return out

    def scan(self, TableName, FilterExpression=None, ExpressionAttributeNames=None, ExpressionAttributeValues=None,
             ExclusiveStartKey=None, Limit=None, ProjectionExpression=None, ConsistentRead=False, **_):
        self._maybe_fail("scan")
        names, values = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        _check_values_used(values, FilterExpression)
        with self.lock:
            out = self._page(TableName, list(self.tables[TableName].items()), ExclusiveStartKey, Limit)
            out["Items"] = [it for it in out["Items"] if evaluate_condition(FilterExpression, it, names, values)]
            return out

    def transact_write_items(self, TransactItems, **_):
        self._maybe_fail("transact_write_items")
        with self.lock:
            snapshot = copy.deepcopy(self.tables)
            reasons = ["None"] * len(TransactItems)
            try:
                for i, ti in enumerate(TransactItems):
                    try:
                        if "Put" in ti:
                            p = ti["Put"]
                            self._put_locked(p["TableName"], p["Item"], p.get("ConditionExpression"),
                                             p.get("ExpressionAttributeNames"), p.get("ExpressionAttributeValues"))
                        elif "Update" in ti:
                            u = ti["Update"]
                            self._update_locked(u["TableName"], u["Key"], u["UpdateExpression"],
                                                u.get("ConditionExpression"), u.get("ExpressionAttributeNames"),
                                                u.get("ExpressionAttributeValues"))
                        elif "Delete" in ti:
                            d = ti["Delete"]
                            self._delete_locked(d["TableName"], d["Key"], d.get("ConditionExpression"),
                                                d.get("ExpressionAttributeNames"), d.get("ExpressionAttributeValues"))
                        else:
                            c = ti["ConditionCheck"]
                            it = self.tables[c["TableName"]].get(self._k(c["TableName"], c["Key"])) or {}
                            if not evaluate_condition(c.get("ConditionExpression"), it,
                                                      c.get("ExpressionAttributeNames") or {},
                                                      c.get("ExpressionAttributeValues") or {}):
                                raise FakeClientError("ConditionalCheckFailedException")
                    except FakeClientError:
                        reasons[i] = "ConditionalCheckFailed"
                        raise
            except FakeClientError:
                self.tables = snapshot
                raise FakeClientError("TransactionCanceledException", reasons)
        return {}


class FakeS3:
    def __init__(self, page_size: int = 1000):
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.uploads: dict[str, dict[str, str]] = {}   # bucket -> upload_id -> key
        self.page_size = page_size
        self.fail_delete_keys: set[str] = set()

    def seed(self, bucket: str, key: str, body: bytes = b"x") -> None:
        self.buckets.setdefault(bucket, {})[key] = body

    def seed_upload(self, bucket: str, key: str, upload_id: str) -> None:
        self.uploads.setdefault(bucket, {})[upload_id] = key

    def keys(self, bucket: str, prefix: str = "") -> list[str]:
        return sorted(k for k in self.buckets.get(bucket, {}) if k.startswith(prefix))

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None, MaxKeys=1000, **_):
        keys = self.keys(Bucket, Prefix)
        start = int(ContinuationToken or 0)
        size = min(self.page_size, MaxKeys)
        page = keys[start:start + size]
        out = {"Contents": [{"Key": k} for k in page], "KeyCount": len(page)}
        if start + size < len(keys):
            out["IsTruncated"] = True
            out["NextContinuationToken"] = str(start + size)
        else:
            out["IsTruncated"] = False
        return out

    def delete_objects(self, Bucket, Delete, **_):
        objs = Delete["Objects"]
        if len(objs) > 1000:
            raise ValueError("MalformedXML: more than 1000 keys")
        errors, deleted = [], []
        for o in objs:
            if o["Key"] in self.fail_delete_keys:
                errors.append({"Key": o["Key"], "Code": "AccessDenied"})
                continue
            self.buckets.get(Bucket, {}).pop(o["Key"], None)
            deleted.append({"Key": o["Key"]})
        return {"Deleted": deleted, **({"Errors": errors} if errors else {})}

    def list_multipart_uploads(self, Bucket, Prefix="", KeyMarker=None, UploadIdMarker=None, **_):
        ups = sorted((k, u) for u, k in self.uploads.get(Bucket, {}).items() if k.startswith(Prefix))
        return {"Uploads": [{"Key": k, "UploadId": u} for k, u in ups], "IsTruncated": False}

    def abort_multipart_upload(self, Bucket, Key, UploadId, **_):
        self.uploads.get(Bucket, {}).pop(UploadId, None)
        return {}


class _NotFound(FakeClientError):
    pass


class FakeCognito:
    """Users keyed by Cognito username; `sub_is_username` models whether AdminGetUser accepts the sub."""

    def __init__(self, sub_is_username: bool = False):
        self.users: dict[str, dict] = {}   # username -> {"sub", "enabled", "signed_out"}
        self.sub_is_username = sub_is_username
        self.calls: list[tuple[str, str]] = []

    def add(self, username: str, sub: str) -> None:
        self.users[username] = {"sub": sub, "enabled": True, "signed_out": 0}

    def _find(self, username: str) -> str:
        if username in self.users:
            return username
        if self.sub_is_username:
            for u, rec in self.users.items():
                if rec["sub"] == username:
                    return u
        raise FakeClientError("UserNotFoundException")

    def admin_get_user(self, UserPoolId, Username):
        u = self._find(Username)
        return {"Username": u, "UserAttributes": [{"Name": "sub", "Value": self.users[u]["sub"]}],
                "Enabled": self.users[u]["enabled"]}

    def list_users(self, UserPoolId, Filter, Limit=1, **_):
        want = Filter.split("=", 1)[1].strip().strip('"')
        return {"Users": [{"Username": u, "Attributes": [{"Name": "sub", "Value": r["sub"]}]}
                          for u, r in self.users.items() if r["sub"] == want][:Limit]}

    def admin_disable_user(self, UserPoolId, Username):
        self.calls.append(("disable", Username))
        self.users[self._find(Username)]["enabled"] = False
        return {}

    def admin_user_global_sign_out(self, UserPoolId, Username):
        self.calls.append(("signout", Username))
        self.users[self._find(Username)]["signed_out"] += 1
        return {}

    def admin_delete_user(self, UserPoolId, Username):
        self.calls.append(("delete", Username))
        self.users.pop(self._find(Username))
        return {}
