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
AI_IDEA_ALLOWANCE_EXHAUSTED = "ai_idea_allowance_exhausted"
DENIAL_CODES = (TRIAL_EXPIRED, VIDEO_CREDITS_EXHAUSTED, MOMENT_ALLOWANCE_EXHAUSTED, SUBSCRIPTION_REQUIRED, AI_IDEA_ALLOWANCE_EXHAUSTED)

ACTION_SUBSCRIBE, ACTION_WAIT_RENEWAL, ACTION_CONTACT = "subscribe", "wait_for_renewal", "contact_support"

# 2 = Billing V2 (additive over 1): unlimited Plus, `capabilities`, null allowances for unlimited accounts. Every key the
# contract-1 client requires is still present (see apps/api/tests/test_billing_v2_unlimited_plus.py and the Swift compat test).
# 3 = AI-idea meter (additive over 2): `ideas` allowance (null unless metered), capabilities.ai_ideas, denial code
# ai_idea_allowance_exhausted. Every contract-2 key is unchanged.
CONTRACT_VERSION = 3
CAPABILITIES_VERSION = 1
CAP_UNLIMITED, CAP_METERED = "unlimited", "metered"


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
    kind: str                      # video | moment | idea
    key: str                       # reservation id (video) or moment id
    state: str                     # reserved | settled | released | unlimited
    charged: bool
    reason: str = ""               # why not charged: idempotent | already_analyzed | in_flight | unlimited
    # Billing V2: this call OWNS the operation record (it created or reclaimed the reservation), whether or not it took a counter.
    # An unlimited (unmetered) hold owns its record without a charge; it must still settle or release it.
    owns: bool = False


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
    # AI-idea meter. None = the counters were never written (an entitlement created before billing-config/4); the ledger
    # initializes them lazily to the Free starter allowance on the first metered idea.
    i_total: Optional[int] = None
    i_avail: int = 0
    i_resv: int = 0
    i_used: int = 0
    refunds: int = 0
    orig_txn: Optional[str] = None
    gf_cutoff: Optional[str] = None      # rollout cutoff of the grandfathering cohort (audit + cohort rollback)
    # Billing V2 (S8): an Apple subscription bought by a beta_grandfathered / admin_granted account is recorded HERE, beside the
    # plan, so the purchase is visible and a grandfather rollback converts the account to Plus instead of losing the subscription.
    sub_status: Optional[str] = None
    sub_period_id: Optional[str] = None
    sub_period_start: Optional[int] = None
    sub_period_end: Optional[int] = None
    sub_grace_end: Optional[int] = None
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

    def subscription_status(self, now: int) -> Optional[str]:
        """Effective Apple subscription status (plus_active | plus_grace | plus_expired) or None when the account never subscribed.
        For a Plus account it is the plan status; for a grandfathered/admin account it is the side record (S8)."""
        if self.plan == PLAN_PLUS:
            return self.effective_status(now)
        if not self.sub_status:
            return None
        if self.sub_status == ST_PLUS_ACTIVE and self.sub_period_end is not None and now > self.sub_period_end:
            return ST_PLUS_EXPIRED
        if self.sub_status == ST_PLUS_GRACE and self.sub_grace_end is not None and now > self.sub_grace_end:
            return ST_PLUS_EXPIRED
        return self.sub_status

    def has_active_subscription(self, now: int) -> bool:
        return self.subscription_status(now) in (ST_PLUS_ACTIVE, ST_PLUS_GRACE)

    def unlimited_at(self, now: int) -> bool:
        """Billing V2: unlimited is DERIVED at read time, never stored for Plus (B4). Expiry is checked FIRST, so a lapsed Plus
        can never keep unlimited access. The stored `unlimited` flag is only ever set by grandfathering."""
        if self.has_active_subscription(now):
            return True
        if self.effective_status(now) == ST_PLUS_EXPIRED:
            return False
        return self.unlimited or self.effective_status(now) == ST_BETA

    def ideas_metered(self, now: int) -> bool:
        """The AI-idea meter applies ONLY to a Free starter. Plus, grandfathered and admin-granted accounts are unmetered for
        ideas (a lapsed Plus is refused by the subscription check before this matters)."""
        return self.plan == PLAN_FREE and not self.unlimited_at(now)

    def trial_state(self, now: int) -> str:
        if self.plan != PLAN_FREE:
            return "not_applicable"
        if self.trial_end is None:
            return "not_started"
        return "expired" if now > self.trial_end else "active"
