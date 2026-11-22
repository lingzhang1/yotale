"""The durable deletion request: acceptance, receipt status, lease and phase advance (design rev 3, 5.2-5.4).

Item shapes in the `account-deletions` table (PK `pk`, SK `sk`):
  * request   pk=<story_user_id>         sk="request"          the source of truth and the deletion ledger
  * child     pk=<story_user_id>         sk="job#<id>" | "gkey#token#<t>" | "gkey#txn#<id>"   discovered keys
  * pointer   pk="receipt#<request_id>"  sk="pointer"          uid; makes request_id unique, lets status be read
Discovered keys are separate items (not string sets on the request), so concurrent discovery is a union by
construction and an account with many jobs never approaches the 400 KB item limit.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional

from . import config as C


class LeaseLost(Exception):
    """A conditional write found that this run no longer owns the request (taken over, or phase moved on)."""


def _s(v: str) -> dict:
    return {"S": str(v)}


def _n(v) -> dict:
    return {"N": str(int(v))}


def plain(item: dict) -> dict:
    out = {}
    for k, v in (item or {}).items():
        if "S" in v:
            out[k] = v["S"]
        elif "N" in v:
            f = float(v["N"])
            out[k] = int(f) if f == int(f) else f
        elif "BOOL" in v:
            out[k] = v["BOOL"]
    return out


def error_code(e: Exception) -> str:
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        code = (resp.get("Error") or {}).get("Code")
        if code:
            return str(code)[:64]
    return type(e).__name__[:64]


def is_conditional_failure(e: Exception) -> bool:
    return error_code(e) == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in type(e).__name__


def receipt_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass
class AcceptResult:
    outcome: str            # accepted | idempotent | already_requested | not_active
    request: Optional[dict]


class RequestStore:
    def __init__(self, ddb, cfg: C.DeletionConfig):
        self.ddb, self.cfg = ddb, cfg
        self.t = cfg.requests_table

    # ---- keys ------------------------------------------------------------------------------------------
    @staticmethod
    def _rk(uid: str) -> dict:
        return {"pk": _s(uid), "sk": _s(C.SK_REQUEST)}

    # ---- acceptance (the durable boundary, design 5.3) -------------------------------------------------
    def accept(self, uid: str, request_id: str, receipt_hash_hex: str, now: int) -> AcceptResult:
        """One TransactWriteItems: request item + receipt pointer + users row active -> deleting.

        Returns accepted / idempotent (same request_id already accepted) / already_requested (another request
        exists for this account) / not_active (users row missing or not active). Any other failure raises: the
        caller must treat the outcome as unknown and resolve it through the receipt status."""
        request = {
            "pk": _s(uid), "sk": _s(C.SK_REQUEST), "uid": _s(uid), "request_id": _s(request_id),
            "receipt_hash": _s(receipt_hash_hex), "accepted_at": _n(now), "state": _s(C.STATE_ACTIVE),
            "phase": _s(C.PHASES[0]), "phase_seq": _n(1), "next_run_at": _n(now), "lease_until": _n(0),
            "fail_count": _n(0), "clean_passes": _n(0),
        }
        pointer = {"pk": _s(C.RECEIPT_PK + request_id), "sk": _s(C.SK_POINTER), "uid": _s(uid)}
        try:
            self.ddb.transact_write_items(TransactItems=[
                {"Put": {"TableName": self.t, "Item": request, "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"TableName": self.t, "Item": pointer, "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Update": {
                    "TableName": self.cfg.users_table, "Key": {"story_user_id": _s(uid)},
                    "UpdateExpression": "SET account_status = :del, deletion_request_id = :rid",
                    "ConditionExpression": "attribute_exists(story_user_id) AND "
                                           "(attribute_not_exists(account_status) OR account_status = :act)",
                    "ExpressionAttributeValues": {":del": _s("deleting"), ":rid": _s(request_id),
                                                  ":act": _s("active")}}},
            ])
            return AcceptResult("accepted", self.get(uid))
        except Exception as e:  # noqa: BLE001
            if error_code(e) != "TransactionCanceledException" and "TransactionCanceled" not in type(e).__name__:
                raise
            reasons = [r.get("Code", "None") for r in (getattr(e, "response", {}) or {}).get("CancellationReasons", [])]
            if reasons and reasons[0] == "ConditionalCheckFailed":
                existing = self.get(uid)
                if existing and existing.get("request_id") == request_id:
                    return AcceptResult("idempotent", existing)
                return AcceptResult("already_requested", existing)
            if len(reasons) > 2 and reasons[2] == "ConditionalCheckFailed":
                return AcceptResult("not_active", None)
            raise

    # ---- reads -------------------------------------------------------------------------------------------
    def get(self, uid: str) -> Optional[dict]:
        it = self.ddb.get_item(TableName=self.t, Key=self._rk(uid), ConsistentRead=True).get("Item")
        return plain(it) if it else None

    def status_by_receipt(self, request_id: str, secret: str) -> Optional[dict]:
        """Public status (design 5.3): None for an unknown id AND for a wrong secret (same answer)."""
        ptr = self.ddb.get_item(TableName=self.t, Key={"pk": _s(C.RECEIPT_PK + request_id), "sk": _s(C.SK_POINTER)},
                                ConsistentRead=True).get("Item")
        if not ptr:
            receipt_hash(secret)   # same work on both paths
            return None
        req = self.get(ptr["uid"]["S"])
        if not req or req.get("request_id") != request_id:
            return None
        if not hmac.compare_digest(receipt_hash(secret), str(req.get("receipt_hash", ""))):
            return None
        return public_view(req)

    def scan_requests(self) -> list[dict]:
        """Every request item (pointer and child items filtered out). shortcut: a Scan is fine at one item per
        deletion ever; add a sparse GSI on next_run_at when the table reaches thousands of items."""
        out, kw = [], {"TableName": self.t, "FilterExpression": "sk = :r",
                       "ExpressionAttributeValues": {":r": _s(C.SK_REQUEST)}}
        while True:
            resp = self.ddb.scan(**kw)
            out.extend(plain(it) for it in resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def children(self, uid: str, prefix: str) -> list[str]:
        """Discovered keys under `prefix` (job# or gkey#), returned without the prefix."""
        out, kw = [], {"TableName": self.t, "KeyConditionExpression": "pk = :p AND begins_with(sk, :x)",
                       "ExpressionAttributeValues": {":p": _s(uid), ":x": _s(prefix)}, "ConsistentRead": True}
        while True:
            resp = self.ddb.query(**kw)
            out.extend(it["sk"]["S"][len(prefix):] for it in resp.get("Items", []))
            if not resp.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def record_child(self, uid: str, prefix: str, key: str, now: int) -> None:
        """Idempotent: a second discovery of the same key rewrites the same item."""
        self.ddb.put_item(TableName=self.t, Item={"pk": _s(uid), "sk": _s(prefix + key), "found_at": _n(now)})

    # ---- lease and state transitions (design 5.4) -----------------------------------------------------
    def acquire(self, uid: str, run_id: str, now: int, *, force: bool = False) -> bool:
        cond = ("attribute_exists(pk) AND (#st = :a OR #st = :c) "
                "AND (attribute_not_exists(lease_until) OR lease_until < :now)")
        if not force:
            cond += " AND next_run_at <= :now"
        try:
            self.ddb.update_item(
                TableName=self.t, Key=self._rk(uid),
                UpdateExpression="SET lease_owner = :run, lease_until = :lu",
                ConditionExpression=cond, ExpressionAttributeNames={"#st": "state"},
                ExpressionAttributeValues={":run": _s(run_id), ":lu": _n(now + C.LEASE_S), ":now": _n(now),
                                           ":a": _s(C.STATE_ACTIVE), ":c": _s(C.STATE_COMPLETED)})
            return True
        except Exception as e:  # noqa: BLE001
            if is_conditional_failure(e):
                return False
            raise

    def _owned_update(self, uid, run_id, now, seq, sets: dict, *, adds: Optional[dict] = None,
                      if_not_exists: Optional[dict] = None, require_live: bool = True) -> None:
        names = {"#st": "state"} if "state" in sets else {}
        vals = {":run": _s(run_id), ":seq": _n(seq)}
        parts = []
        for i, (k, v) in enumerate(sets.items()):
            a = "#st" if k == "state" else k
            vals[f":s{i}"] = v
            parts.append(f"{a} = :s{i}")
        for i, (k, v) in enumerate((if_not_exists or {}).items()):
            vals[f":i{i}"] = v
            parts.append(f"{k} = if_not_exists({k}, :i{i})")
        ue = "SET " + ", ".join(parts)
        if adds:
            add_parts = []
            for i, (k, v) in enumerate(adds.items()):
                vals[f":a{i}"] = v
                add_parts.append(f"{k} :a{i}")
            ue += " ADD " + ", ".join(add_parts)
        cond = "lease_owner = :run AND phase_seq = :seq"
        if require_live:
            cond += " AND lease_until > :now"
            vals[":now"] = _n(now)
        try:
            self.ddb.update_item(TableName=self.t, Key=self._rk(uid), UpdateExpression=ue, ConditionExpression=cond,
                                 ExpressionAttributeValues=vals, **({"ExpressionAttributeNames": names} if names else {}))
        except Exception as e:  # noqa: BLE001
            if is_conditional_failure(e):
                raise LeaseLost(uid) from e
            raise

    def advance(self, uid: str, run_id: str, now: int, seq: int, next_phase: str, *, sets: Optional[dict] = None,
                if_not_exists: Optional[dict] = None) -> None:
        """Move to the next phase: owner- and phase_seq-checked, monotonic, resets fail_count."""
        if C.phase_seq(next_phase) != seq + 1:
            raise ValueError(f"non-monotonic advance {seq} -> {next_phase}")
        s = {"phase": _s(next_phase), "phase_seq": _n(seq + 1), "fail_count": _n(0), **(sets or {})}
        self._owned_update(uid, run_id, now, seq, s, if_not_exists=if_not_exists)

    def release(self, uid: str, run_id: str, now: int, seq: int, next_run_at: int, *,
                sets: Optional[dict] = None) -> None:
        """Planned wait: give up the lease until next_run_at. Never touches fail_count."""
        s = {"next_run_at": _n(next_run_at), "lease_until": _n(0), **(sets or {})}
        self._owned_update(uid, run_id, now, seq, s)

    def fail(self, uid: str, run_id: str, now: int, seq: int, prev_fail_count: int, code: str,
             already_alerted: bool) -> tuple[int, bool]:
        """A phase raised: count it, back off, release. Returns (fail_count, alert_now)."""
        n = prev_fail_count + 1
        sets = {"last_error_code": _s(code[:64]), "next_run_at": _n(now + C.backoff_s(n)), "lease_until": _n(0)}
        alert = n >= C.STALL_FAIL_COUNT and not already_alerted
        if alert:
            sets["stalled_alerted_at"] = _n(now)
        self._owned_update(uid, run_id, now, seq, sets, adds={"fail_count": _n(1)}, require_live=False)
        return n, alert


def public_view(req: dict) -> dict:
    """What the client may learn about its own request: accepted | in_progress | completed."""
    state = req.get("state")
    if state in (C.STATE_COMPLETED, C.STATE_CLOSED):
        return {"state": "completed", "completed_at": req.get("completed_at")}
    phase = req.get("phase")
    return {"state": "accepted" if phase == C.PHASES[0] else "in_progress", "completed_at": None}
