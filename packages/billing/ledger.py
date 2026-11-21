"""Billing V1 ledger: server-authoritative entitlements and allowance accounting on the shared UserUsage table.

Design (see specs/.../billing-v1-spec.md):

* Same table as user_quota (`story-<env>-user-usage`, PK story_user_id, SK quota_period), new SK namespaces, so no new
  infrastructure and no new IAM beyond what the quota module already has (GetItem + UpdateItem + TransactWriteItems).
  Items are created with UpdateItem (upsert + condition), never PutItem.
* ONE entitlement item per user holds counters; ONE item per operation (video) or per Moment is the durable ledger
  record with its own state. Every state change is a single TransactWriteItems over {operation item, entitlement item},
  so a counter and its record can never disagree and a retry can never double count.
* Atomic caps WITHOUT arithmetic in conditions (DynamoDB forbids it): the entitlement stores `avail` directly, reserve
  does `ADD avail -1` guarded by `avail >= 1`. No read-modify-write is relied on for consumption. Reads are only used to
  choose the right typed denial and to pick the transition; the write re-asserts everything it depends on
  (`b_ver`, state, period id, avail) and a cancelled transaction re-reads and re-decides (bounded loop).
* Trial clock: starts when the FIRST VIDEO settles (not at an import, a reservation or a failed operation). Before that, only the
  bounded 30-analysis allowance is spendable; see `docs` in billing-v1-spec.md for what happens if it is exhausted first.
* Reservation state machine, all transitions idempotent:
      none -> reserved -> settled | released        released -> reserved (same operation retried)
      settled -> refunded (controlled, capped)      released -> settled (late: work was delivered after a release)
* A reservation remembers the period it was charged against (`b_period`). After a subscription renewal the counters are
  new; settling or releasing an old-period reservation only moves the record, never the new period's counters.
* `shadow=True` writes the SAME structure under the `billing-shadow#` namespace. Observe mode uses it, so hypothetical
  decisions are computed from real accounting without debiting any customer-visible counter, and flipping to enforce
  starts from clean counters.
* Moments are charged once per account per moment id, ever (`m#<moment_id>`), so cache hits, retries, duplicate uploads,
  concurrent duplicates and re-analysis never spend the allowance twice.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Callable, Optional

from .config import BillingConfig
from .model import (
    ACTION_CONTACT, ACTION_SUBSCRIBE, AI_IDEA_ALLOWANCE_EXHAUSTED, ACTION_WAIT_RENEWAL, BillingDenied, BillingStoreError, CAP_METERED, CAP_UNLIMITED,
    CAPABILITIES_VERSION, CONTRACT_VERSION, Entitlement,
    Hold, MOMENT_ALLOWANCE_EXHAUSTED, PLAN_ADMIN, PLAN_BETA, PLAN_FREE, PLAN_PLUS, RS_REFUNDED, RS_RELEASED, RS_RESERVED,
    RS_SETTLED, ST_ADMIN, ST_BETA, ST_FREE, ST_PLUS_ACTIVE, ST_PLUS_EXPIRED, ST_PLUS_GRACE, SUBSCRIPTION_REQUIRED,
    TRIAL_EXPIRED, TransactionBoundElsewhere, VIDEO_CREDITS_EXHAUSTED,
)

_RES_NS = uuid.UUID("6f6c1b4e-0000-4000-8000-000000000005")
# Cached analysis results above this size are not stored in the ledger item (DynamoDB items are limited to 400 KB).
MAX_CACHED_RESULT_BYTES = 300_000
LIVE, SHADOW = "billing#", "billing-shadow#"
APPLE_TXN_PK = "__apple_txn__"
APPLE_TOKEN_PK = "__apple_token__"
APPLE_EVT_PK = "__apple_evt__"
_MAX_TRIES = 5

_ATTRS = {"video": ("b_v_avail", "b_v_resv", "b_v_used"), "moment": ("b_m_avail", "b_m_resv", "b_m_used"),
          "idea": ("b_i_avail", "b_i_resv", "b_i_used")}


def reservation_id(operation_id: str) -> str:
    return str(uuid.uuid5(_RES_NS, operation_id))


def _n(v: float | int) -> dict:
    return {"N": str(int(v)) if float(v) == int(v) else str(v)}


def _s(v: str) -> dict:
    return {"S": v}


def _err_name(e: Exception) -> str:
    return type(e).__name__


def _reasons(e: Exception) -> list[str]:
    r = getattr(e, "response", None) or {}
    return [x.get("Code", "") for x in (r.get("CancellationReasons") or [])]


def _is_cond_fail(e: Exception) -> bool:
    n = _err_name(e)
    if "ConditionalCheckFailed" in n:
        return True
    if "TransactionCanceled" in n:
        rs = _reasons(e)
        return bool(rs) and all(c in ("ConditionalCheckFailed", "None") for c in rs)
    return False


def _is_conflict(e: Exception) -> bool:
    return "TransactionConflict" in str(e) or any(c == "TransactionConflict" for c in _reasons(e))


def _int(item: dict, k: str, default: int = 0) -> int:
    v = item.get(k)
    return int(float(v["N"])) if v and "N" in v else default


def _opt(item: dict, k: str) -> Optional[int]:
    v = item.get(k)
    return int(float(v["N"])) if v and "N" in v else None


def _str(item: dict, k: str, default: str = "") -> str:
    v = item.get(k)
    return v["S"] if v and "S" in v else default


def parse_entitlement(uid: str, it: dict) -> Entitlement:
    return Entitlement(
        uid=uid, plan=_str(it, "b_plan", PLAN_FREE), status=_str(it, "b_status", ST_FREE),
        unlimited=bool(it.get("b_unlimited", {}).get("BOOL", False)),
        trial_start=_opt(it, "b_trial_start"), trial_end=_opt(it, "b_trial_end"),
        period_id=_str(it, "b_period_id", "starter"), period_start=_opt(it, "b_period_start"),
        period_end=_opt(it, "b_period_end"), grace_end=_opt(it, "b_grace_end"),
        v_total=_int(it, "b_v_total"), v_avail=_int(it, "b_v_avail"), v_resv=_int(it, "b_v_resv"), v_used=_int(it, "b_v_used"),
        m_total=_int(it, "b_m_total"), m_avail=_int(it, "b_m_avail"), m_resv=_int(it, "b_m_resv"), m_used=_int(it, "b_m_used"),
        i_total=_opt(it, "b_i_total"), i_avail=_int(it, "b_i_avail"), i_resv=_int(it, "b_i_resv"), i_used=_int(it, "b_i_used"),
        refunds=_int(it, "b_refunds"), orig_txn=(_str(it, "b_orig_txn") or None), gf_cutoff=(_str(it, "b_gf_cutoff") or None), ver=_int(it, "b_ver", 1),
        cfg=_str(it, "b_cfg"), created=_int(it, "b_created"), updated=_int(it, "b_updated"),
        sub_status=(_str(it, "b_sub_status") or None), sub_period_id=(_str(it, "b_sub_pid") or None),
        sub_period_start=_opt(it, "b_sub_pstart"), sub_period_end=_opt(it, "b_sub_pend"), sub_grace_end=_opt(it, "b_sub_grace_end"),
    )


class BillingLedger:
    def __init__(self, *, ddb=None, table: str = "", region: str = "us-east-1", cfg: Optional[BillingConfig] = None,
                 shadow: bool = False, clock: Callable[[], float] = time.time):
        import os
        self._ddb = ddb
        self.table = table or os.environ.get("STORY_USER_USAGE_TABLE", "")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.cfg = cfg or BillingConfig()
        self.shadow = shadow
        self.ns = SHADOW if shadow else LIVE
        self._clock = clock

    # ---- plumbing ---------------------------------------------------------------------------------------------
    def _c(self):
        if self._ddb is None:
            import boto3
            self._ddb = boto3.client("dynamodb", region_name=self.region)
        return self._ddb

    def _now(self) -> int:
        return int(self._clock())

    def _key(self, uid: str, sk: str) -> dict:
        return {"story_user_id": _s(uid), "quota_period": _s(sk)}

    def _ent_key(self, uid: str) -> dict:
        return self._key(uid, f"{self.ns}entitlement")

    def _get(self, uid: str, sk: str) -> dict:
        try:
            return self._c().get_item(TableName=self.table, Key=self._key(uid, sk), ConsistentRead=True).get("Item") or {}
        except Exception as e:  # noqa: BLE001
            raise BillingStoreError(f"get_item: {_err_name(e)}") from e

    def _update(self, uid: str, sk: str, ue: str, values: dict, cond: Optional[str] = None) -> bool:
        """Single conditional write. True = applied, False = condition failed, BillingStoreError = store problem."""
        kw: dict[str, Any] = {"TableName": self.table, "Key": self._key(uid, sk), "UpdateExpression": ue,
                              "ExpressionAttributeValues": values}
        if cond:
            kw["ConditionExpression"] = cond
        try:
            self._c().update_item(**kw)
            return True
        except Exception as e:  # noqa: BLE001
            if _is_cond_fail(e):
                return False
            raise BillingStoreError(f"update_item: {_err_name(e)}") from e

    def _txn(self, legs: list[dict]) -> bool:
        """All-or-nothing across the operation item and the entitlement item. True = committed, False = a guard
        failed (caller re-reads and re-decides). Transient conflicts are retried with the SAME idempotent legs."""
        items = [{"Update": {"TableName": self.table, **leg}} for leg in legs]
        for attempt in range(5):
            try:
                self._c().transact_write_items(TransactItems=items)
                return True
            except Exception as e:  # noqa: BLE001
                if _is_cond_fail(e):
                    return False
                if _is_conflict(e):
                    # Concurrent transactions on the same entitlement item (one account importing many clips at once).
                    # Back off with jitter and retry the SAME idempotent legs; a conflict is never a policy decision.
                    time.sleep(random.uniform(0.01, 0.04) * (attempt + 1))
                    continue
                raise BillingStoreError(f"transact: {_err_name(e)}") from e
        return False

    # ---- entitlement lifecycle --------------------------------------------------------------------------------
    def get_entitlement(self, uid: str) -> Optional[Entitlement]:
        it = self._get(uid, f"{self.ns}entitlement")
        return parse_entitlement(uid, it) if it else None

    def ensure_entitlement(self, uid: str) -> Entitlement:
        """Return the entitlement, creating the Free starter on first use. Creation is create-only (conditional), so
        concurrent first calls produce exactly one record. The 14-day trial clock does NOT start here; it starts at
        the first SUCCESSFUL billable operation (see `_finish`)."""
        cur = self.get_entitlement(uid)
        if cur is not None:
            return cur
        now, lim = self._now(), self.cfg.free_starter
        vals = {":plan": _s(PLAN_FREE), ":st": _s(ST_FREE), ":pid": _s("starter"), ":ver": _n(1),
                ":vt": _n(lim.videos), ":mt": _n(lim.moments), ":it": _n(lim.ideas), ":zero": _n(0),
                ":cfg": _s(self.cfg.config_version), ":now": _n(now)}
        ue = ("SET b_plan = :plan, b_status = :st, b_period_id = :pid, b_ver = :ver, b_cfg = :cfg, "
              "b_created = :now, b_updated = :now, "
              "b_v_total = :vt, b_v_avail = :vt, b_v_resv = :zero, b_v_used = :zero, "
              "b_m_total = :mt, b_m_avail = :mt, b_m_resv = :zero, b_m_used = :zero, "
              "b_i_total = :it, b_i_avail = :it, b_i_resv = :zero, b_i_used = :zero, b_refunds = :zero")
        self._update(uid, f"{self.ns}entitlement", ue, vals, "attribute_not_exists(b_plan)")
        got = self.get_entitlement(uid)
        if got is None:
            raise BillingStoreError("entitlement create did not persist")
        return got

    def get_or_create_apple_account_token(self, uid: str) -> str:
        """Stable per-account UUID for StoreKit `appAccountToken` (Apple requires a UUID; story_user_id is not
        guaranteed to be one). Always in the LIVE namespace: it is identity, not usage, and must be identical in
        observe and enforce."""
        sk = "billing#account"
        it = self._get(uid, sk)
        if it and "b_apple_token" in it:
            if "b_tok_idx" not in it:       # created before the reverse index existed: index once, then remember
                self._index_account_token(uid, sk, it["b_apple_token"]["S"])
            return it["b_apple_token"]["S"]
        self._update(uid, sk, "SET b_apple_token = :t, b_created = :now",
                     {":t": _s(str(uuid.uuid4())), ":now": _n(self._now())}, "attribute_not_exists(b_apple_token)")
        token = self._get(uid, sk)["b_apple_token"]["S"]      # the winner of a concurrent create
        self._index_account_token(uid, sk, token)
        return token

    def _index_account_token(self, uid: str, sk: str, token: str) -> None:
        """Make the token resolvable to the account BEFORE any purchase. Apple can deliver SUBSCRIBED a few seconds before the
        app posts its transaction; without this index that notification cannot be attributed. Idempotent, create-only."""
        self.index_apple_token(uid, token)
        self._update(uid, sk, "SET b_tok_idx = :one", {":one": _n(1)})

    def _ensure_idea_counters(self, uid: str, ent: Entitlement) -> Entitlement:
        """A Free starter created before the AI-idea meter (billing-config/4) has no `b_i_*` counters. Write the starter
        allowance ONCE (create-only on b_i_total, so concurrent first ideas initialize exactly once), then re-read."""
        if ent.plan != PLAN_FREE or ent.i_total is not None:
            return ent
        lim = self.cfg.free_starter
        self._update(uid, f"{self.ns}entitlement",
                     "SET b_i_total = :it, b_i_avail = :it, b_i_resv = :z, b_i_used = :z, b_updated = :now",
                     {":it": _n(lim.ideas), ":z": _n(0), ":now": _n(self._now()), ":free": _s(PLAN_FREE)},
                     "attribute_not_exists(b_i_total) AND b_plan = :free")
        return self.get_entitlement(uid) or ent

    # ---- decisions --------------------------------------------------------------------------------------------
    def _decide(self, ent: Entitlement, kind: str, now: int) -> None:
        """Raise BillingDenied if this entitlement cannot start one more `kind` unit; return None otherwise."""
        eff = ent.effective_status(now)
        snap = lambda: self._view(ent, now)  # noqa: E731
        if ent.unlimited_at(now):            # derived; checks expiry FIRST, so a lapsed Plus never reaches here (B4)
            return
        if eff == ST_PLUS_EXPIRED:
            raise BillingDenied(SUBSCRIPTION_REQUIRED, ACTION_SUBSCRIBE, snap())
        if kind == "idea" and not ent.ideas_metered(now):
            return                           # ideas are metered for the Free starter only
        avail = {"video": ent.v_avail, "moment": ent.m_avail, "idea": ent.i_avail}[kind]
        if ent.plan == PLAN_FREE and ent.trial_end is not None and now > ent.trial_end:
            raise BillingDenied(TRIAL_EXPIRED, ACTION_SUBSCRIBE, snap())
        if avail < 1:
            code = {"video": VIDEO_CREDITS_EXHAUSTED, "moment": MOMENT_ALLOWANCE_EXHAUSTED,
                    "idea": AI_IDEA_ALLOWANCE_EXHAUSTED}[kind]
            action = (ACTION_SUBSCRIBE if ent.plan == PLAN_FREE
                      else ACTION_CONTACT if ent.plan == PLAN_ADMIN else ACTION_WAIT_RENEWAL)
            raise BillingDenied(code, action, snap())

    # ---- reserve / settle / release (video credit) ---------------------------------------------------------------
    def reserve_video(self, uid: str, operation_id: str) -> Hold:
        rid = reservation_id(operation_id)
        return self._reserve(uid, "video", f"{self.ns}v#{rid}", rid)

    def settle_video(self, uid: str, operation_id: str) -> str:
        return self._finish(uid, "video", f"{self.ns}v#{reservation_id(operation_id)}", settle=True)

    def release_video(self, uid: str, operation_id: str) -> str:
        return self._finish(uid, "video", f"{self.ns}v#{reservation_id(operation_id)}", settle=False)

    # ---- reserve / settle / release (AI idea while shooting) ------------------------------------------------------
    # One unit per SUCCESSFUL idea call. `operation_id` is per request; a failed call is released (never charged), and the
    # trial clock never starts on an idea (only a settled video starts it, see `_finish`).
    def reserve_idea(self, uid: str, operation_id: str) -> Hold:
        rid = reservation_id(operation_id)
        return self._reserve(uid, "idea", f"{self.ns}i#{rid}", rid)

    def settle_idea(self, uid: str, operation_id: str) -> str:
        return self._finish(uid, "idea", f"{self.ns}i#{reservation_id(operation_id)}", settle=True)

    def release_idea(self, uid: str, operation_id: str) -> str:
        return self._finish(uid, "idea", f"{self.ns}i#{reservation_id(operation_id)}", settle=False)

    # ---- reserve / settle / release (new unique Moment analysis) --------------------------------------------------
    @staticmethod
    def _mid(moment_id: str) -> str:
        return str(moment_id).strip().lower()

    def reserve_moment(self, uid: str, moment_key: str, *, attrs: Optional[dict] = None) -> Hold:
        """Reserve one analysis unit for an analysis record. `moment_key` is opaque to the ledger (the analysis module builds
        `<moment id>~<source id>`); `attrs` are recorded on the FIRST reservation only (fingerprint, version, binding...)."""
        mk = self._mid(moment_key)
        return self._reserve(uid, "moment", f"{self.ns}m#{mk}", mk, attrs)

    def settle_moment(self, uid: str, moment_key: str, *, result: Optional[str] = None, version: Optional[str] = None) -> str:
        attrs: dict = {}
        if result is not None and len(result.encode("utf-8")) <= MAX_CACHED_RESULT_BYTES:
            attrs["b_result"] = _s(result)
            if version:
                attrs["b_ver"] = _s(version)
        elif result is not None:
            attrs["b_result_skipped"] = _n(1)           # too large to cache: later identical requests refresh without charge
        return self._finish(uid, "moment", f"{self.ns}m#{self._mid(moment_key)}", settle=True, attrs=attrs)

    def release_moment(self, uid: str, moment_key: str) -> str:
        return self._finish(uid, "moment", f"{self.ns}m#{self._mid(moment_key)}", settle=False)

    # ---- analysis records: read model + paid-already refresh ---------------------------------------------------
    def read_moment(self, uid: str, moment_key: str) -> dict:
        """Compact view of one analysis record (empty dict when absent). `result` is the cached analysis JSON, if any."""
        it = self._get(uid, f"{self.ns}m#{self._mid(moment_key)}")
        if not it:
            return {}
        return {"state": _str(it, "b_state"), "fp": _str(it, "b_fp"), "ver": _str(it, "b_ver"), "result": _str(it, "b_result") or None,
                "bind": _str(it, "b_bind"), "claim": _str(it, "b_claim"), "updated": _int(it, "b_updated"),
                "refreshing": _opt(it, "b_rf_ts"), "fails": _int(it, "b_fails"), "corr": _str(it, "b_corr")}

    def begin_refresh(self, uid: str, moment_key: str, corr: str = "") -> bool:
        """Re-run an ALREADY-PAID analysis (new analysis version, or no cached result) WITHOUT a new charge. At most one caller
        wins at a time (a stale claim older than `moment_stale_s` can be taken over). True = this caller owns the refresh."""
        now = self._now()
        return self._update(uid, f"{self.ns}m#{self._mid(moment_key)}",
                            "SET b_rf = :run, b_rf_ts = :now, b_corr = :corr",
                            {":run": _s("running"), ":now": _n(now), ":stale": _n(now - self.cfg.moment_stale_s),
                             ":st": _s(RS_SETTLED), ":corr": _s(corr[:64] or "-")},
                            "b_state = :st AND (attribute_not_exists(b_rf) OR b_rf_ts < :stale)")

    def finish_refresh(self, uid: str, moment_key: str, result: Optional[str], version: str) -> bool:
        attrs_sets, vals = "b_ver = :v, b_updated = :now", {":v": _s(version), ":now": _n(self._now()), ":run": _s("running")}
        if result is not None and len(result.encode("utf-8")) <= MAX_CACHED_RESULT_BYTES:
            attrs_sets += ", b_result = :r"
            vals[":r"] = _s(result)
        return self._update(uid, f"{self.ns}m#{self._mid(moment_key)}", f"SET {attrs_sets} REMOVE b_rf, b_rf_ts, b_result_skipped",
                            vals, "b_rf = :run")

    def abort_refresh(self, uid: str, moment_key: str) -> bool:
        return self._update(uid, f"{self.ns}m#{self._mid(moment_key)}", "SET b_updated = :now REMOVE b_rf, b_rf_ts",
                            {":now": _n(self._now()), ":run": _s("running")}, "b_rf = :run")

    # ---- core: reserve ----------------------------------------------------------------------------------------
    def _reserve(self, uid: str, kind: str, sk: str, key: str, attrs: Optional[dict] = None) -> Hold:
        avail_a, resv_a, _used_a = _ATTRS[kind]
        for _ in range(_MAX_TRIES):
            now = self._now()
            ent = self.ensure_entitlement(uid)
            if kind == "idea":
                ent = self._ensure_idea_counters(uid, ent)
            res = self._get(uid, sk)
            st = _str(res, "b_state") or None
            if st in (RS_SETTLED, RS_REFUNDED):
                return Hold(kind, key, RS_SETTLED, False, "already_analyzed" if kind == "moment" else "idempotent")
            unmetered = "b_unmetered" in res
            if st == RS_RESERVED:
                age = now - _int(res, "b_updated", now)
                if kind == "moment" and age >= self.cfg.moment_stale_s:
                    # The request that held this reservation is presumed dead; take it over WITHOUT a second
                    # charge. The compare-and-set on b_updated lets exactly one caller win a stale reclaim.
                    if self._update(uid, sk, "SET b_updated = :now",
                                    {":now": _n(now), ":rs": _s(RS_RESERVED), ":old": _n(_int(res, "b_updated"))},
                                    "b_state = :rs AND b_updated = :old"):
                        return Hold(kind, key, RS_RESERVED, not unmetered, "reclaimed", owns=True)
                    continue
                return Hold(kind, key, RS_RESERVED, False, "idempotent" if kind == "video" else "in_flight")
            self._decide(ent, kind, now)             # may raise BillingDenied (typed)
            if ent.unlimited_at(now) or (kind == "idea" and not ent.ideas_metered(now)):
                # Billing V2 (B3): an unlimited account takes the SAME record transitions (create-only reservation, reserved ->
                # settled | released, cached analysis result, coalescing, stale takeover, attribution) and skips ONLY the
                # entitlement counter leg. `b_unmetered` on the RECORD says no counter was taken, so settle/release decide the
                # counter leg from the record, never from the live entitlement (which may have changed since).
                vals = {":rs": _s(RS_RESERVED), ":k": _s(kind), ":p": _s(ent.period_id), ":now": _n(now), ":one": _n(1)}
                cond = "attribute_not_exists(b_state)"
                if st == RS_RELEASED:
                    cond = "b_state = :rel"
                    vals[":rel"] = _s(RS_RELEASED)
                extra = ""
                for i, (an, av) in enumerate((attrs or {}).items()):
                    vals[f":x{i}"] = av
                    extra += f", {an} = :x{i}"
                if self._update(uid, sk, "SET b_state = :rs, b_kind = :k, b_period = :p, b_unmetered = :one, "
                                         "b_created = if_not_exists(b_created, :now), b_updated = :now" + extra, vals, cond):
                    return Hold(kind, key, RS_RESERVED, False, "unlimited", owns=True)
                continue                             # a concurrent identical request created it first: re-read and re-decide

            res_vals = {":rs": _s(RS_RESERVED), ":k": _s(kind), ":p": _s(ent.period_id), ":now": _n(now)}
            res_cond = "attribute_not_exists(b_state)"
            if st == RS_RELEASED:
                res_cond = "b_state = :rel"
                res_vals[":rel"] = _s(RS_RELEASED)
            ent_vals = {":one": _n(1), ":neg1": _n(-1), ":ver": _n(ent.ver), ":now": _n(now)}
            ent_cond = f"{avail_a} >= :one AND b_ver = :ver"
            if ent.plan == PLAN_FREE:
                ent_cond += " AND (attribute_not_exists(b_trial_end) OR b_trial_end >= :now)"
            extra_sets = ""
            for i, (an, av) in enumerate((attrs or {}).items()):
                res_vals[f":x{i}"] = av
                extra_sets += f", {an} = :x{i}"
            ok = self._txn([
                {"Key": self._key(uid, sk),
                 "UpdateExpression": "SET b_state = :rs, b_kind = :k, b_period = :p, "
                                     "b_created = if_not_exists(b_created, :now), b_updated = :now" + extra_sets
                                     + " REMOVE b_unmetered",
                 "ConditionExpression": res_cond, "ExpressionAttributeValues": res_vals},
                {"Key": self._ent_key(uid),
                 "UpdateExpression": f"SET b_updated = :now ADD {avail_a} :neg1, {resv_a} :one",
                 "ConditionExpression": ent_cond, "ExpressionAttributeValues": ent_vals},
            ])
            if ok:
                return Hold(kind, key, RS_RESERVED, True, owns=True)
        raise BillingStoreError("reserve: contention not resolved")

    # ---- core: settle / release -------------------------------------------------------------------------------
    def _finish(self, uid: str, kind: str, sk: str, *, settle: bool, attrs: Optional[dict] = None) -> str:
        avail_a, resv_a, used_a = _ATTRS[kind]
        for _ in range(_MAX_TRIES):
            now = self._now()
            res = self._get(uid, sk)
            st = _str(res, "b_state") or None
            if st is None:
                return "missing"
            if settle and st in (RS_SETTLED, RS_REFUNDED):
                return "noop"
            if (not settle) and st in (RS_RELEASED, RS_SETTLED, RS_REFUNDED):
                return "noop"            # releasing a settled credit is a refund, never a silent release
            late = settle and st == RS_RELEASED       # work was delivered after the credit was released
            new_state = RS_SETTLED if settle else RS_RELEASED
            res_vals = {":ns": _s(new_state), ":from": _s(st), ":now": _n(now)}
            res_ue = "SET b_state = :ns, b_updated = :now"
            if settle:
                res_ue += ", b_settled_at = :now"
            for i, (an, av) in enumerate((attrs or {}).items()):
                res_ue += f", {an} = :x{i}"
                res_vals[f":x{i}"] = av
            if (not settle) and kind == "moment":
                res_ue += " ADD b_fails :one"            # failed analysis attempts stay visible next to the (uncharged) record
                res_vals[":one"] = _n(1)
            legs = [{"Key": self._key(uid, sk), "UpdateExpression": res_ue,
                     "ConditionExpression": "b_state = :from", "ExpressionAttributeValues": res_vals}]
            ent = self.get_entitlement(uid)
            # The counter leg runs only for a record that TOOK a counter at reserve time (no `b_unmetered`), and only in the
            # period it was taken in. Deciding from the record (not `ent` being unlimited now) keeps a pre-V2 reservation that is
            # settled after V2 from leaving `b_*_resv` stuck, and never decrements a counter an unmetered record never took (B3).
            metered = "b_unmetered" not in res
            if metered and ent is not None and ent.period_id == _str(res, "b_period"):
                ent_vals: dict = {":pid": _s(ent.period_id), ":now": _n(now), ":one": _n(1)}
                ue = "SET b_updated = :now"
                if settle and kind == "video" and ent.plan == PLAN_FREE:
                    # The 14-day clock starts at the first successfully GENERATED VIDEO (owner decision 2026-11-18), never at
                    # an import/analysis, a reservation, or a failed/released operation. if_not_exists makes it start exactly
                    # once, so creating more Stories, retrying, or re-authenticating can never restart or extend it.
                    ue += ", b_trial_start = if_not_exists(b_trial_start, :now), b_trial_end = if_not_exists(b_trial_end, :tend)"
                    ent_vals[":tend"] = _n(now + self.cfg.trial_days * 86400)
                if late:
                    ue += f" ADD {used_a} :one, {avail_a} :neg1"          # overage is allowed: the work already exists
                    ent_vals[":neg1"] = _n(-1)
                    cond = "b_period_id = :pid"
                elif settle:
                    ue += f" ADD {resv_a} :neg1, {used_a} :one"
                    ent_vals[":neg1"] = _n(-1)
                    cond = f"b_period_id = :pid AND {resv_a} >= :one"
                else:
                    ue += f" ADD {resv_a} :neg1, {avail_a} :one"
                    ent_vals[":neg1"] = _n(-1)
                    cond = f"b_period_id = :pid AND {resv_a} >= :one"
                legs.append({"Key": self._ent_key(uid), "UpdateExpression": ue, "ConditionExpression": cond,
                             "ExpressionAttributeValues": ent_vals})
            if self._txn(legs):
                return "settled" if settle else "released"
        raise BillingStoreError("finish: contention not resolved")

    # ---- controlled refund of a settled video credit ----------------------------------------------------------
    def refund_cap(self, ent: Entitlement) -> int:
        return self.cfg.free_refunds if ent.plan == PLAN_FREE else self.cfg.refunds_per_period

    def refund_video(self, uid: str, operation_id: str, reason: str, *, render_attempts: int = 0, client_build: str = "") -> str:
        """Return one settled video credit after a device render failure the client reports. The server cannot see on-device
        rendering, so a claim is accepted only when ALL of these hold (each checked atomically in the transaction where it can be):
          * the operation has a SETTLED credit record under THIS account (an unbilled or foreign operation has none),
          * the claim states at least `refund_min_render_attempts` renders of the stored plan (a plan is re-renderable without any
            new AI work, so a single failure is retried first, never refunded),
          * it is the first refund for that operation, within `refund_window_s` of settlement, in the SAME period,
          * the per-period cap is not reached (Free starter: 1, Plus: 3).
        It only returns the credit; the generated plan/output is never touched or invalidated. Evidence (reason, attempts, client
        build) is stored on the operation record for audit. Returns refunded | noop | not_eligible:<why>."""
        sk = f"{self.ns}v#{reservation_id(operation_id)}"
        if int(render_attempts) < self.cfg.refund_min_render_attempts:
            return "not_eligible:insufficient_evidence"
        for _ in range(_MAX_TRIES):
            now = self._now()
            res = self._get(uid, sk)
            st = _str(res, "b_state") or None
            if st is None:
                return "not_eligible:unknown_operation"
            if st == RS_REFUNDED:
                return "noop"
            if st != RS_SETTLED:
                return "not_eligible:not_settled"
            if now - _int(res, "b_settled_at", 0) > self.cfg.refund_window_s:
                return "not_eligible:window_elapsed"
            ent = self.get_entitlement(uid)
            if ent is None or ent.period_id != _str(res, "b_period") or ent.unlimited_at(now) or "b_unmetered" in res:
                return "not_eligible:period_or_plan"
            cap = self.refund_cap(ent)
            if ent.refunds >= cap:
                return "not_eligible:refund_cap"
            ok = self._txn([
                {"Key": self._key(uid, sk),
                 "UpdateExpression": "SET b_state = :rf, b_updated = :now, b_refund_reason = :why, b_refund_attempts = :att, "
                                     "b_refund_build = :bld",
                 "ConditionExpression": "b_state = :st",
                 "ExpressionAttributeValues": {":rf": _s(RS_REFUNDED), ":st": _s(RS_SETTLED), ":now": _n(now),
                                               ":why": _s(str(reason)[:40]), ":att": _n(int(render_attempts)),
                                               ":bld": _s((client_build or "-")[:40])}},
                {"Key": self._ent_key(uid),
                 "UpdateExpression": "SET b_updated = :now ADD b_v_used :neg1, b_v_avail :one, b_refunds :one",
                 "ConditionExpression": "b_period_id = :pid AND b_refunds < :cap AND b_v_used >= :one",
                 "ExpressionAttributeValues": {":pid": _s(ent.period_id), ":cap": _n(cap),
                                               ":now": _n(now), ":neg1": _n(-1), ":one": _n(1)}},
            ])
            if ok:
                return "refunded"
        raise BillingStoreError("refund: contention not resolved")

    # ---- reconciliation ---------------------------------------------------------------------------------------
    def reconcile_video_job(self, uid: str, operation_id: str, job_status: str) -> str:
        """Drive a video reservation to the state its job's durable terminal status demands. A COMPLETED job settles
        (the result was durably recorded, so the credit is owed even if the worker died before settling); every other
        terminal status releases. Idempotent; safe to call from the sweep and from the worker."""
        if job_status == "completed":
            return self.settle_video(uid, operation_id)
        return self.release_video(uid, operation_id)

    def reclaim_stale_moments(self, uid: str, limit: int = 25) -> int:
        """Release Moment reservations abandoned by a crashed AU request, for ONE account, bounded to `limit` releases.
        Uses Query (partition + begins_with), so it needs dynamodb:Query on the table. Without that permission it is a no-op:
        a stale reservation is still reclaimed one at a time, with no extra charge, when the same Moment is retried
        (`plan_analysis` step 3). Pages through the filtered Query because DynamoDB applies Limit BEFORE the filter."""
        cutoff = self._now() - self.cfg.moment_stale_s
        released, start = 0, None
        for _page in range(20):
            kw: dict[str, Any] = dict(
                TableName=self.table, KeyConditionExpression="story_user_id = :pk AND begins_with(quota_period, :sk)",
                FilterExpression="b_state = :rs AND b_updated < :cut",
                ExpressionAttributeValues={":pk": _s(uid), ":sk": _s(f"{self.ns}m#"), ":rs": _s(RS_RESERVED), ":cut": _n(cutoff)})
            if start:
                kw["ExclusiveStartKey"] = start
            try:
                r = self._c().query(**kw)
            except Exception:  # noqa: BLE001  (AccessDenied until Query is granted; never break the caller)
                return released
            for it in r.get("Items", []):
                mk = it["quota_period"]["S"].split("m#", 1)[-1]
                if self.release_moment(uid, mk) == "released":
                    released += 1
                    if released >= limit:
                        return released
            start = r.get("LastEvaluatedKey")
            if not start:
                break
        return released

    # ---- plan changes (Apple server integration calls these in B2) ------------------------------------------------
    def _plan_update(self, uid: str, ent: Entitlement, sets: dict[str, dict], extra_cond: str = "",
                     extra_vals: Optional[dict] = None) -> bool:
        now = self._now()
        names = list(sets)
        ue = "SET b_ver = :nver, b_updated = :now, " + ", ".join(f"{k} = :v{i}" for i, k in enumerate(names))
        vals = {":nver": _n(ent.ver + 1), ":now": _n(now), ":ver": _n(ent.ver), **(extra_vals or {})}
        for i, k in enumerate(names):
            vals[f":v{i}"] = sets[k]
        cond = "b_ver = :ver" + (f" AND {extra_cond}" if extra_cond else "")
        return self._update(uid, f"{self.ns}entitlement", ue, vals, cond)

    def grandfather(self, uid: str, cutoff: Optional[str] = None) -> Entitlement:
        """Existing beta accounts keep unrestricted use. Idempotent. `cutoff` (the rollout date the owner chose) is recorded on the
        entitlement so the change is auditable and can be rolled back for exactly this cohort (`revoke_grandfather`)."""
        for _ in range(_MAX_TRIES):
            ent = self.ensure_entitlement(uid)
            if ent.plan == PLAN_BETA:
                return ent
            sets = {"b_plan": _s(PLAN_BETA), "b_status": _s(ST_BETA), "b_unlimited": {"BOOL": True}}
            if cutoff:
                sets["b_gf_cutoff"] = _s(cutoff)
            if self._plan_update(uid, ent, sets):
                break
        return self.get_entitlement(uid)  # type: ignore[return-value]

    def revoke_grandfather(self, uid: str, cutoff: str) -> str:
        """Rollback for ONE cohort: an account grandfathered with this exact `cutoff` becomes a normal Free starter with fresh starter
        counters (a grandfathered account's usage was never counted, so there is nothing to carry over). Never touches an account
        that was not grandfathered with this cutoff, or one that has since moved to a paid plan. Returns reverted | noop."""
        for _ in range(_MAX_TRIES):
            ent = self.get_entitlement(uid)
            if ent is None or ent.plan != PLAN_BETA:
                return "noop"
            it = self._get(uid, f"{self.ns}entitlement")
            if _str(it, "b_gf_cutoff") != cutoff:
                return "noop"
            now = self._now()
            if ent.has_active_subscription(now):
                # S8: the tester PAID for Plus while grandfathered. Rolling the cohort back must not drop that: the account becomes
                # Plus with the recorded Apple period (unlimited is derived; no counters are written).
                vals = {":plan": _s(PLAN_PLUS), ":st": _s(ent.sub_status or ST_PLUS_ACTIVE), ":no": {"BOOL": False},
                        ":pid": _s(ent.sub_period_id or "plus"), ":ps": _n(ent.sub_period_start or now),
                        ":pe": _n(ent.sub_period_end or now), ":nver": _n(ent.ver + 1), ":now": _n(now),
                        ":cfg": _s(self.cfg.config_version), ":beta": _s(PLAN_BETA), ":cut": _s(cutoff), ":ver": _n(ent.ver)}
                ue = ("SET b_plan = :plan, b_status = :st, b_unlimited = :no, b_period_id = :pid, b_period_start = :ps, "
                      "b_period_end = :pe, b_ver = :nver, b_updated = :now, b_cfg = :cfg")
                if ent.sub_grace_end is not None:
                    ue += ", b_grace_end = :ge"
                    vals[":ge"] = _n(ent.sub_grace_end)
                ue += " REMOVE b_gf_cutoff, b_trial_start, b_trial_end, b_sub_status, b_sub_pid, b_sub_pstart, b_sub_pend, b_sub_grace_end"
                if self._update(uid, f"{self.ns}entitlement", ue, vals, "b_plan = :beta AND b_gf_cutoff = :cut AND b_ver = :ver"):
                    return "reverted"
                continue
            lim = self.cfg.free_starter
            ok = self._update(
                uid, f"{self.ns}entitlement",
                "SET b_plan = :plan, b_status = :st, b_unlimited = :no, b_period_id = :pid, b_ver = :nver, b_updated = :now, "
                "b_v_total = :vt, b_v_avail = :vt, b_v_resv = :z, b_v_used = :z, b_m_total = :mt, b_m_avail = :mt, "
                "b_m_resv = :z, b_m_used = :z, b_i_total = :it, b_i_avail = :it, b_i_resv = :z, b_i_used = :z, "
                "b_refunds = :z, b_cfg = :cfg REMOVE b_gf_cutoff, b_trial_start, b_trial_end",
                {":plan": _s(PLAN_FREE), ":st": _s(ST_FREE), ":no": {"BOOL": False}, ":pid": _s("starter"), ":nver": _n(ent.ver + 1),
                 ":now": _n(now), ":vt": _n(lim.videos), ":mt": _n(lim.moments), ":it": _n(lim.ideas), ":z": _n(0),
                 ":cfg": _s(self.cfg.config_version),
                 ":beta": _s(PLAN_BETA), ":cut": _s(cutoff), ":ver": _n(ent.ver)},
                "b_plan = :beta AND b_gf_cutoff = :cut AND b_ver = :ver")
            if ok:
                return "reverted"
        raise BillingStoreError("revoke_grandfather: contention not resolved")

    def admin_grant(self, uid: str, *, videos: int, moments: int, until: Optional[int] = None, reason: str = "") -> Entitlement:
        """Support grant: fresh finite allowances, optionally time-limited. Replaces the current period counters."""
        for _ in range(_MAX_TRIES):
            ent = self.ensure_entitlement(uid)
            now = self._now()
            sets = {"b_plan": _s(PLAN_ADMIN), "b_status": _s(ST_ADMIN), "b_unlimited": {"BOOL": False},
                    "b_period_id": _s(f"admin:{now}"), "b_period_start": _n(now),
                    "b_v_total": _n(videos), "b_v_avail": _n(videos), "b_v_resv": _n(0), "b_v_used": _n(0),
                    "b_m_total": _n(moments), "b_m_avail": _n(moments), "b_m_resv": _n(0), "b_m_used": _n(0),
                    "b_refunds": _n(0), "b_grant_reason": _s(reason[:80])}
            if until is not None:
                sets["b_period_end"] = _n(until)
            if self._plan_update(uid, ent, sets):
                break
        return self.get_entitlement(uid)  # type: ignore[return-value]

    def apply_subscription(self, uid: str, *, status: str, period_id: str, period_start: int, period_end: int,
                           event_ts: int, grace_end: Optional[int] = None, orig_txn: Optional[str] = None) -> Entitlement:
        """Apply a VERIFIED Apple subscription state (B2 calls this after signature verification; the client never does).

        * Period boundaries come from Apple, not the calendar. Billing V2: Plus is unlimited (derived at read time), so a new
          `period_id` writes NO finite allowance totals; it only moves the period (and resets the refund counter).
        * `event_ts` (Apple's signed time) orders events: an older event than the one already applied is ignored, so a
          delayed webhook cannot resurrect an expired subscription or undo a renewal.
        * Grandfathered and admin-granted accounts are never downgraded by a store event. Billing V2 (S8): their Apple
          subscription is recorded BESIDE the plan (`b_sub_*`), so the purchase shows as Active and a grandfather rollback turns
          the account into Plus instead of losing a paid subscription."""
        if status not in (ST_PLUS_ACTIVE, ST_PLUS_GRACE, ST_PLUS_EXPIRED):
            raise ValueError(f"unsupported subscription status {status!r}")
        for _ in range(_MAX_TRIES):
            ent = self.ensure_entitlement(uid)
            vals = {":ets": _n(event_ts), ":pend": _n(period_end)}
            if ent.plan in (PLAN_BETA, PLAN_ADMIN):
                sets: dict[str, dict] = {"b_sub_status": _s(status), "b_sub_pid": _s(period_id), "b_sub_pstart": _n(period_start),
                                         "b_sub_pend": _n(period_end), "b_evt_ts": _n(event_ts)}
                if orig_txn:
                    sets["b_orig_txn"] = _s(orig_txn)
                if grace_end is not None:
                    sets["b_sub_grace_end"] = _n(grace_end)
                guard = "(attribute_not_exists(b_evt_ts) OR b_evt_ts <= :ets) AND (attribute_not_exists(b_sub_pend) OR b_sub_pend <= :pend)"
            else:
                sets = {"b_plan": _s(PLAN_PLUS), "b_status": _s(status), "b_evt_ts": _n(event_ts),
                        "b_period_end": _n(period_end), "b_period_start": _n(period_start), "b_cfg": _s(self.cfg.config_version)}
                if orig_txn:
                    sets["b_orig_txn"] = _s(orig_txn)
                if grace_end is not None:
                    sets["b_grace_end"] = _n(grace_end)
                if status == ST_PLUS_EXPIRED:
                    sets["b_period_id"] = _s(period_id)       # converge on the newest known period without touching counters
                if status != ST_PLUS_EXPIRED and (ent.plan != PLAN_PLUS or ent.period_id != period_id):
                    sets.update({"b_period_id": _s(period_id), "b_refunds": _n(0)})
                # Event order (Apple's signed time) AND period order: a state for an OLDER billing period (a replayed old
                # transaction, a refund of last month's charge) can never overwrite a newer period, even with a fresher
                # signature time.
                guard = "(attribute_not_exists(b_evt_ts) OR b_evt_ts <= :ets)"
                if ent.plan == PLAN_PLUS:
                    guard += " AND (attribute_not_exists(b_period_end) OR b_period_end <= :pend)"
                else:
                    vals.pop(":pend")
            ok = self._plan_update(uid, ent, sets, guard, vals)
            if ok:
                return self.get_entitlement(uid)  # type: ignore[return-value]
            cur = self.get_entitlement(uid)
            if cur is not None and cur.ver == ent.ver:
                return cur            # the failed guard was the event-order check: a newer event already applied
        raise BillingStoreError("apply_subscription: contention not resolved")

    def bind_apple_transaction(self, original_transaction_id: str, uid: str) -> None:
        """Bind an Apple original transaction to exactly ONE YoTale account (create-only). Raises
        TransactionBoundElsewhere if another account already owns it."""
        sk = f"billing#txn#{original_transaction_id}"
        applied = self._update(APPLE_TXN_PK, sk, "SET b_uid = :u, b_created = :now",
                               {":u": _s(uid), ":now": _n(self._now())}, "attribute_not_exists(b_uid)")
        if applied:
            return
        owner = _str(self._get(APPLE_TXN_PK, sk), "b_uid")
        if owner != uid:
            raise TransactionBoundElsewhere(original_transaction_id)

    # ---- Apple identity indexes + event journal (B2) ----------------------------------------------------------
    def index_apple_token(self, uid: str, token: str) -> None:
        """Reverse index appAccountToken -> account, so a server notification that arrives before the app has posted its
        transaction can still find the account. Create-only; a token is never re-pointed at another account."""
        sk = f"billing#token#{token}"
        if self._update(APPLE_TOKEN_PK, sk, "SET b_uid = :u, b_created = :now",
                        {":u": _s(uid), ":now": _n(self._now())}, "attribute_not_exists(b_uid)"):
            return
        if _str(self._get(APPLE_TOKEN_PK, sk), "b_uid") != uid:
            raise TransactionBoundElsewhere(f"token:{token}")

    def uid_for_apple_token(self, token: str) -> Optional[str]:
        return _str(self._get(APPLE_TOKEN_PK, f"billing#token#{token}"), "b_uid") or None

    def apple_txn_owner(self, original_transaction_id: str) -> Optional[str]:
        return _str(self._get(APPLE_TXN_PK, f"billing#txn#{original_transaction_id}"), "b_uid") or None

    def apple_event_seen(self, notification_uuid: str) -> bool:
        return bool(self._get(APPLE_EVT_PK, f"billing#evt#{notification_uuid}"))

    def record_apple_event(self, notification_uuid: str, *, ntype: str, outcome: str) -> bool:
        """Journal a PROCESSED notification (create-only). False = already journalled (a duplicate delivery)."""
        return self._update(APPLE_EVT_PK, f"billing#evt#{notification_uuid}",
                            "SET b_type = :t, b_outcome = :o, b_created = :now",
                            {":t": _s(ntype[:40]), ":o": _s(outcome[:40]), ":now": _n(self._now())},
                            "attribute_not_exists(b_type)")

    # ---- read model -------------------------------------------------------------------------------------------
    def entitlement_view(self, uid: str, *, create: bool = True) -> dict:
        ent = self.ensure_entitlement(uid) if create else self.get_entitlement(uid)
        if ent is None:
            return {"contract_version": CONTRACT_VERSION, "plan": None}
        return self._view(ent, self._now())

    def _view(self, ent: Entitlement, now: int) -> dict:
        eff = ent.effective_status(now)
        trial = ent.trial_state(now)
        free = ent.plan == PLAN_FREE
        unlimited = ent.unlimited_at(now)
        # S1: counters belong only to accounts whose allowance is a real finite one. A lapsed Plus keeps stale starter counters in
        # its item; showing them (as "0 left") next to a subscription_required denial would be wrong.
        counters = (not unlimited) and ent.plan in (PLAN_FREE, PLAN_ADMIN)
        remaining_v, remaining_m = max(ent.v_avail, 0), max(ent.m_avail, 0)
        ideas_metered = ent.ideas_metered(now)
        # A pre-meter Free starter has no b_i_* yet: it shows the full starter allowance until its first idea initializes them.
        i_total = ent.i_total if ent.i_total is not None else self.cfg.free_starter.ideas
        i_avail = ent.i_avail if ent.i_total is not None else self.cfg.free_starter.ideas
        sub = ent.subscription_status(now)
        if ent.plan == PLAN_PLUS:
            sub_end = ent.grace_end if sub == ST_PLUS_GRACE and ent.grace_end else ent.period_end
        else:
            sub_end = ent.sub_grace_end if sub == ST_PLUS_GRACE and ent.sub_grace_end else ent.sub_period_end
        return {
            "contract_version": CONTRACT_VERSION,
            "plan": ent.plan, "status": eff, "unlimited": unlimited,
            "trial": {"state": trial, "started_at": ent.trial_start, "ends_at": ent.trial_end,
                      "days": self.cfg.trial_days},
            "period": {"id": ent.period_id, "start": ent.period_start, "end": ent.period_end},
            # Billing V2: only Free starter and admin-granted accounts have an allowance to show. null (not 0) otherwise, so neither the
            # contract-1 nor the V2 client prints a counter; legacy counters stored on a Plus record stay in the item, unread.
            "videos": {"total": ent.v_total, "used": ent.v_used, "reserved": ent.v_resv, "remaining": remaining_v} if counters else None,
            "moments": {"total": ent.m_total, "used": ent.m_used, "reserved": ent.m_resv, "remaining": remaining_m} if counters else None,
            # Contract 3: the AI-idea allowance, Free starter only (null for every unmetered account).
            "ideas": ({"total": i_total, "used": ent.i_used, "reserved": ent.i_resv, "remaining": max(i_avail, 0)}
                      if ideas_metered else None),
            "refunds": {"used": ent.refunds, "allowed": 0 if unlimited else self.refund_cap(ent)},
            "upgrade": {"eligible": (free or eff == ST_PLUS_EXPIRED) and not unlimited,
                        "suggest": free and ent.v_used >= 1,     # nudge after the first finished video, never a block
                        "blocking": free and (trial == "expired" or remaining_v < 1 or remaining_m < 1)},
            "capabilities": {
                "version": CAPABILITIES_VERSION,
                "video_generation": CAP_UNLIMITED if unlimited else CAP_METERED,
                "moment_analysis": CAP_UNLIMITED if unlimited else CAP_METERED,
                "ai_ideas": CAP_METERED if ideas_metered else CAP_UNLIMITED,
                # Apple-verified subscription state, independent of the plan label (a grandfathered tester who bought Plus is
                # `active` here). `ends_at` is the server's verified period (or grace) end: the renewal or expiry date.
                "subscription": {"status": {ST_PLUS_ACTIVE: "active", ST_PLUS_GRACE: "grace", ST_PLUS_EXPIRED: "expired"}.get(sub or "", "none"),
                                 "ends_at": sub_end if sub else None},
            },
            "entitlement_version": ent.ver, "apple_original_transaction_id": ent.orig_txn,
        }
