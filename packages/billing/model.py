"""Billing V1 domain model: plan/status vocabulary, the entitlement snapshot, holds, and typed denials."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---- plans and statuses -------------------------------------------------------------------------------------
PLAN_FREE, PLAN_PLUS, PLAN_BETA, PLAN_ADMIN = "free_starter", "plus", "beta_grandfathered", "admin_granted"

ST_FREE = "free_starter"
ST_PLUS_ACTIVE, ST_PLUS_GRACE, ST_PLUS_EXPIRED = "plus_active", "plus_grace", "plus_expired"
ST_BETA, ST_ADMIN = "beta_grandfathered", "admin_granted"
STATUSES = (ST_FREE, ST_PLUS_ACTIVE, ST_PLUS_GRACE, ST_PLUS_EXPIRED, ST_BETA, ST_ADMIN)

# ---- reservation states -------------------------------------------------------------------------------------
# reserved -> settled | released ; settled -> refunded (controlled) ; released -> reserved (retry of the same op)
# "expired/reconciled" is a RELEASE with reason (stale / orphaned); it is not a separate stored state so every
# terminal move stays a single idempotent transition.
RS_RESERVED, RS_SETTLED, RS_RELEASED, RS_REFUNDED = "reserved", "settled", "released", "refunded"

# ---- denial codes (HTTP 402 body `error`) -------------------------------------------------------------------
TRIAL_EXPIRED = "trial_expired"
VIDEO_CREDITS_EXHAUSTED = "video_credits_exhausted"
MOMENT_ALLOWANCE_EXHAUSTED = "moment_allowance_exhausted"
SUBSCRIPTION_REQUIRED = "subscription_required"
DENIAL_CODES = (TRIAL_EXPIRED, VIDEO_CREDITS_EXHAUSTED, MOMENT_ALLOWANCE_EXHAUSTED, SUBSCRIPTION_REQUIRED)

ACTION_SUBSCRIBE, ACTION_WAIT_RENEWAL, ACTION_CONTACT = "subscribe", "wait_for_renewal", "contact_support"

CONTRACT_VERSION = 1


class BillingDenied(Exception):
    """A request the entitlement does not permit. Carries the stable machine-readable code, the user-facing
    action, and the current allowance snapshot so the app can render the right screen without a second call."""

    def __init__(self, code: str, action: str, snapshot: dict):
        super().__init__(code)
        self.code, self.action, self.snapshot = code, action, snapshot


class BillingStoreError(Exception):
    """The billing store failed (not a policy decision). Callers fail closed in enforce, ignore in observe."""


class TransactionBoundElsewhere(Exception):
    """An Apple original_transaction_id is already bound to a DIFFERENT YoTale account."""


@dataclass
class Hold:
    """Result of a reserve call. `charged` is False when the call consumed nothing (idempotent repeat,
    already-analyzed Moment, unlimited plan, in-flight duplicate)."""
    kind: str                      # video | moment
    key: str                       # reservation id (video) or moment id
    state: str                     # reserved | settled | released | unlimited
    charged: bool
    reason: str = ""               # why not charged: idempotent | already_analyzed | in_flight | unlimited


@dataclass
class Entitlement:
    uid: str
    plan: str = PLAN_FREE
    status: str = ST_FREE
    unlimited: bool = False
    trial_start: Optional[int] = None
    trial_end: Optional[int] = None
    period_id: str = "starter"
    period_start: Optional[int] = None
    period_end: Optional[int] = None
    grace_end: Optional[int] = None
    v_total: int = 0
    v_avail: int = 0
    v_resv: int = 0
    v_used: int = 0
    m_total: int = 0
    m_avail: int = 0
    m_resv: int = 0
    m_used: int = 0
    refunds: int = 0
    orig_txn: Optional[str] = None
    ver: int = 1
    cfg: str = ""
    created: int = 0
    updated: int = 0

    # ---- derived (never stored: no sweeper needed for expiry) -----------------------------------------------
    def effective_status(self, now: int) -> str:
        if self.status == ST_PLUS_ACTIVE and self.period_end is not None and now > self.period_end:
            return ST_PLUS_EXPIRED
        if self.status == ST_PLUS_GRACE and self.grace_end is not None and now > self.grace_end:
            return ST_PLUS_EXPIRED
        if self.status == ST_ADMIN and self.period_end is not None and now > self.period_end:
            return ST_PLUS_EXPIRED
        return self.status

    def trial_state(self, now: int) -> str:
        if self.plan != PLAN_FREE:
            return "not_applicable"
        if self.trial_end is None:
            return "not_started"
        return "expired" if now > self.trial_end else "active"
