"""Billing V1 / B2: Apple StoreKit 2 server integration.

Everything the client says is a CLAIM. This module turns Apple-signed JWS data into entitlement changes:

* `AppleVerifier` is the only seam that touches Apple's library. `AppStoreVerifier` wraps
  `appstoreserverlibrary.SignedDataVerifier`: certificate chain to the pinned Apple roots, signature, bundle id, app id
  (production) and environment. Tests inject a fake that returns decoded payloads, so the policy below is tested without
  minting Apple signatures; the real wrapper is tested separately for rejection of forged data.
* `AppleBilling` holds the policy: product allowlist, appAccountToken ownership, one-account-per-transaction binding,
  notification-type -> plan-state mapping. Ordering guards (event time, billing-period order) live in the ledger's
  conditional writes, not here.

Never logged or stored: the signed JWS, the private key, prices, storefront, or any payment detail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from .ledger import BillingLedger
from .model import ST_PLUS_ACTIVE, ST_PLUS_EXPIRED, ST_PLUS_GRACE, TransactionBoundElsewhere

log = logging.getLogger("billing.apple")

# Public identifiers (not secrets). The product id is permanent in App Store Connect.
BUNDLE_ID = "com.lingzhang.story"
APP_APPLE_ID = 6826007175
PLUS_PRODUCT_ID = "com.lingzhang.story.plus.monthly"
SUBSCRIPTION_GROUP_ID = "22593497"

SANDBOX, PRODUCTION = "Sandbox", "Production"
ROOTS_DIR = Path(__file__).parent / "apple_roots"


def allowed_environments(story_environment: str) -> tuple[str, ...]:
    """TestFlight purchases are Sandbox, so development and beta accept ONLY Sandbox; gamma/production accept ONLY
    Production. A sandbox purchase on production would grant real entitlements for free, so accepting App Review's sandbox
    purchases there is an explicit owner decision, not a default."""
    return (PRODUCTION,) if story_environment.strip().lower() in ("production", "prod", "gamma") else (SANDBOX,)


# ---- errors -------------------------------------------------------------------------------------------------------
class AppleError(Exception):
    """`code` is the stable machine-readable string the API returns; `status` is the HTTP status."""
    code, status = "apple_error", 422

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.code)


class InvalidSignature(AppleError):
    code, status = "invalid_signed_data", 422


class WrongEnvironment(AppleError):
    code, status = "wrong_environment", 422


class ProductNotAllowed(AppleError):
    code, status = "product_not_allowed", 422


class MissingAccountToken(AppleError):
    code, status = "missing_app_account_token", 422


class AccountTokenMismatch(AppleError):
    code, status = "app_account_token_mismatch", 403


class TransactionBound(AppleError):
    code, status = "transaction_bound_elsewhere", 409


class AppleNotConfigured(AppleError):
    code, status = "apple_not_configured", 503


# ---- normalized, VERIFIED data --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Txn:
    original_transaction_id: str
    transaction_id: str
    product_id: str
    bundle_id: str
    environment: str
    app_account_token: Optional[str]
    purchase_s: int
    expires_s: Optional[int]
    revocation_s: Optional[int]
    signed_s: int
    type: str = "Auto-Renewable Subscription"


@dataclass(frozen=True)
class Renewal:
    grace_expires_s: Optional[int] = None
    in_billing_retry: bool = False


@dataclass(frozen=True)
class Notification:
    uuid: str
    type: str
    subtype: Optional[str]
    signed_s: int
    environment: str
    txn: Optional[Txn]
    renewal: Optional[Renewal]


class AppleVerifier(Protocol):
    def verify_transaction(self, signed: str) -> Txn: ...
    def verify_notification(self, signed: str) -> Notification: ...


def _s(ms) -> Optional[int]:
    return None if ms is None else int(ms) // 1000


def _enum(v) -> str:
    return str(getattr(v, "value", v) or "")


def _txn_from_payload(p) -> Txn:
    token = getattr(p, "appAccountToken", None)
    return Txn(
        original_transaction_id=str(p.originalTransactionId), transaction_id=str(p.transactionId),
        product_id=str(p.productId), bundle_id=str(p.bundleId), environment=_enum(p.environment),
        app_account_token=str(token).lower() if token else None,
        purchase_s=_s(p.purchaseDate) or 0, expires_s=_s(p.expiresDate), revocation_s=_s(p.revocationDate),
        signed_s=_s(p.signedDate) or 0, type=_enum(p.type))


class AppStoreVerifier:
    """Real verifier. One `SignedDataVerifier` per accepted environment, built lazily from the pinned Apple roots."""

    def __init__(self, environments: tuple[str, ...], *, roots_dir: Path = ROOTS_DIR,
                 online_checks: Optional[bool] = None):
        self._envs = environments
        self._roots = [p.read_bytes() for p in sorted(roots_dir.glob("*.cer"))]
        if not self._roots:
            raise AppleNotConfigured("no Apple root certificates found")
        # OCSP revocation checks need outbound network: on for Production only, so Sandbox/dev never fails on connectivity.
        self._online = (PRODUCTION in environments) if online_checks is None else online_checks
        self._v: dict[str, object] = {}

    def _verifier(self, env: str):
        if env not in self._v:
            from appstoreserverlibrary.models.Environment import Environment
            from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
            self._v[env] = SignedDataVerifier(self._roots, self._online, Environment(env), BUNDLE_ID, APP_APPLE_ID)
        return self._v[env]

    def _try(self, fn):
        """Run `fn(verifier)` per accepted environment. Valid data for an environment this deployment does not accept is
        reported as WrongEnvironment, never silently accepted."""
        from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus
        last: Optional[Exception] = None
        for env in self._envs:
            try:
                return fn(self._verifier(env))
            except VerificationException as e:
                last = e
                if e.status != VerificationStatus.INVALID_ENVIRONMENT:
                    break
        if last is not None and getattr(last, "status", None) == VerificationStatus.INVALID_ENVIRONMENT:
            raise WrongEnvironment("signed data is for an environment this deployment does not accept") from last
        raise InvalidSignature(f"verification failed: {getattr(getattr(last, 'status', None), 'name', 'error')}") from last

    def verify_transaction(self, signed: str) -> Txn:
        if not isinstance(signed, str) or not signed or len(signed) > 20000:
            raise InvalidSignature("empty or oversized signed transaction")
        return _txn_from_payload(self._try(lambda v: v.verify_and_decode_signed_transaction(signed)))

    def verify_notification(self, signed: str) -> Notification:
        if not isinstance(signed, str) or not signed or len(signed) > 60000:
            raise InvalidSignature("empty or oversized signed payload")

        def run(v):
            n = v.verify_and_decode_notification(signed)
            data = n.data
            txn = renewal = None
            if data is not None and data.signedTransactionInfo:
                txn = _txn_from_payload(v.verify_and_decode_signed_transaction(data.signedTransactionInfo))
            if data is not None and data.signedRenewalInfo:
                r = v.verify_and_decode_renewal_info(data.signedRenewalInfo)
                renewal = Renewal(grace_expires_s=_s(r.gracePeriodExpiresDate),
                                  in_billing_retry=bool(r.isInBillingRetryPeriod))
            return Notification(uuid=str(n.notificationUUID), type=_enum(n.notificationType),
                                subtype=_enum(n.subtype) or None, signed_s=_s(n.signedDate) or 0,
                                environment=_enum(data.environment) if data is not None else "", txn=txn, renewal=renewal)

        return self._try(run)


# ---- policy -------------------------------------------------------------------------------------------------------
ACTIVATE = frozenset({"SUBSCRIBED", "DID_RENEW", "OFFER_REDEEMED", "RENEWAL_EXTENDED", "REFUND_REVERSED"})
EXPIRE = frozenset({"EXPIRED", "GRACE_PERIOD_EXPIRED", "REFUND", "REVOKE"})
# Informational only: no entitlement change. (PRICE_INCREASE / consent, renewal-preference changes, test pings.)
INFO = frozenset({"DID_CHANGE_RENEWAL_PREF", "DID_CHANGE_RENEWAL_STATUS", "PRICE_INCREASE", "REFUND_DECLINED", "TEST",
                  "CONSUMPTION_REQUEST", "RENEWAL_EXTENSION", "EXTERNAL_PURCHASE_TOKEN", "ONE_TIME_CHARGE",
                  "RESCIND_CONSENT", "METADATA_UPDATE", "MIGRATION", "PRICE_CHANGE"})


def period_id(t: Txn) -> str:
    """One id per billing period: every renewal has a new transactionId under the same originalTransactionId."""
    return f"apple:{t.original_transaction_id}:{t.transaction_id}"


class AppleBilling:
    def __init__(self, ledger: BillingLedger, verifier: AppleVerifier, *, environments: tuple[str, ...],
                 clock=None):
        import time
        self.ledger, self.verifier, self.envs = ledger, verifier, environments
        self._clock = clock or time.time

    def _now(self) -> int:
        return int(self._clock())

    def _check(self, t: Txn) -> None:
        if t.bundle_id != BUNDLE_ID:
            raise InvalidSignature("bundle mismatch")
        if t.environment not in self.envs:
            raise WrongEnvironment(t.environment)
        if t.product_id != PLUS_PRODUCT_ID:
            raise ProductNotAllowed(t.product_id)
        if t.type and t.type != "Auto-Renewable Subscription":
            raise ProductNotAllowed(f"type {t.type}")

    def _is_live(self, t: Txn) -> bool:
        return t.revocation_s is None and t.expires_s is not None and t.expires_s > self._now()

    # ---- client-submitted transaction -------------------------------------------------------------------------
    def submit_transaction(self, uid: str, signed_transaction: str) -> dict:
        """The app posts a StoreKit transaction JWS. Grants Plus only for a live, verified, correctly-owned transaction.
        An expired or revoked transaction NEVER writes: a client replaying an old receipt cannot downgrade, and expiry is
        driven by Apple's signed notifications / reconciliation."""
        t = self.verifier.verify_transaction(signed_transaction)
        self._check(t)
        token = self.ledger.get_or_create_apple_account_token(uid).lower()
        if t.app_account_token is None:
            raise MissingAccountToken("purchase carries no appAccountToken")
        if t.app_account_token != token:
            raise AccountTokenMismatch("transaction belongs to a different YoTale account")
        try:
            self.ledger.index_apple_token(uid, token)
            self.ledger.bind_apple_transaction(t.original_transaction_id, uid)
        except TransactionBoundElsewhere as e:
            raise TransactionBound("transaction is bound to another account") from e
        if not self._is_live(t):
            log.info("billing_apple_txn", extra={"result": "not_active", "env": t.environment})
            return {"result": "not_active", "entitlement": self.ledger.entitlement_view(uid)}
        self.ledger.apply_subscription(
            uid, status=ST_PLUS_ACTIVE, period_id=period_id(t), period_start=t.purchase_s, period_end=t.expires_s,
            event_ts=t.signed_s, orig_txn=t.original_transaction_id)
        log.info("billing_apple_txn", extra={"result": "applied", "env": t.environment})
        return {"result": "applied", "entitlement": self.ledger.entitlement_view(uid)}

    # ---- App Store Server Notifications V2 --------------------------------------------------------------------
    def handle_notification(self, signed_payload: str) -> dict:
        """Verify, de-duplicate, map and apply one notification. Returns an outcome dict. Raises only for a payload that
        fails verification (HTTP 4xx, Apple will not retry a bad signature usefully) or a store failure (5xx, Apple retries)."""
        n = self.verifier.verify_notification(signed_payload)
        if n.environment and n.environment not in self.envs:
            raise WrongEnvironment(n.environment)
        if n.txn is not None:
            self._check(n.txn)
        if self.ledger.apple_event_seen(n.uuid):
            return {"outcome": "duplicate", "type": n.type}
        outcome = self._apply(n)
        self.ledger.record_apple_event(n.uuid, ntype=n.type, outcome=outcome)
        log.info("billing_apple_notification", extra={"type": n.type, "subtype": n.subtype, "outcome": outcome})
        return {"outcome": outcome, "type": n.type}

    def _resolve_uid(self, t: Txn) -> Optional[str]:
        uid = self.ledger.apple_txn_owner(t.original_transaction_id)
        if uid:
            if t.app_account_token:
                tok_uid = self.ledger.uid_for_apple_token(t.app_account_token)
                if tok_uid and tok_uid != uid:
                    return None          # token and binding disagree: never act on ambiguous identity
            return uid
        if t.app_account_token:
            uid = self.ledger.uid_for_apple_token(t.app_account_token)
            if uid:
                try:
                    self.ledger.bind_apple_transaction(t.original_transaction_id, uid)
                except TransactionBoundElsewhere:
                    return None
                return uid
        return None

    def _apply(self, n: Notification) -> str:
        if n.type in INFO or n.txn is None:
            return "info"
        if n.type not in ACTIVATE and n.type not in EXPIRE and n.type != "DID_FAIL_TO_RENEW":
            return "ignored_type"
        t = n.txn
        uid = self._resolve_uid(t)
        if uid is None:
            # No account yet (the app has not posted this purchase). The app's POST /transactions or reconciliation
            # converges; acknowledging avoids an endless retry loop for an event we cannot attribute.
            return "unmatched"
        if n.type in ACTIVATE:
            if not self._is_live(t):
                return "stale_not_live"
            self.ledger.apply_subscription(uid, status=ST_PLUS_ACTIVE, period_id=period_id(t), period_start=t.purchase_s,
                                           period_end=t.expires_s, event_ts=n.signed_s, orig_txn=t.original_transaction_id)
            return "applied_active"
        if n.type == "DID_FAIL_TO_RENEW" and n.subtype == "GRACE_PERIOD":
            grace_end = n.renewal.grace_expires_s if n.renewal else None
            if grace_end is None or grace_end <= self._now():
                return "grace_already_over"
            self.ledger.apply_subscription(uid, status=ST_PLUS_GRACE, period_id=period_id(t), period_start=t.purchase_s,
                                           period_end=t.expires_s or grace_end, event_ts=n.signed_s, grace_end=grace_end,
                                           orig_txn=t.original_transaction_id)
            return "applied_grace"
        # EXPIRED, GRACE_PERIOD_EXPIRED, REFUND, REVOKE, DID_FAIL_TO_RENEW without grace (billing retry, no access).
        self.ledger.apply_subscription(uid, status=ST_PLUS_EXPIRED, period_id=period_id(t), period_start=t.purchase_s,
                                       period_end=t.expires_s or n.signed_s, event_ts=n.signed_s,
                                       orig_txn=t.original_transaction_id)
        return "applied_expired"

    # ---- reconciliation (missed webhooks) ----------------------------------------------------------------------
    # Apple subscription status codes from the App Store Server API (Get All Subscription Statuses).
    STATUS_ACTIVE, STATUS_EXPIRED, STATUS_BILLING_RETRY, STATUS_GRACE, STATUS_REVOKED = 1, 2, 3, 4, 5

    def apply_status(self, uid: str, status_code: int, t: Txn, renewal: Optional[Renewal]) -> str:
        """Apply an Apple-reported CURRENT status (from the server API, already signature-verified) for an account that owns
        this transaction. Uses the same ledger guards as notifications, so a stale reconcile cannot undo a newer event."""
        self._check(t)
        if self.ledger.apple_txn_owner(t.original_transaction_id) != uid:
            raise TransactionBound("transaction is not bound to this account")
        now = self._now()
        if status_code == self.STATUS_ACTIVE and self._is_live(t):
            self.ledger.apply_subscription(uid, status=ST_PLUS_ACTIVE, period_id=period_id(t), period_start=t.purchase_s,
                                           period_end=t.expires_s, event_ts=now, orig_txn=t.original_transaction_id)
            return "applied_active"
        if status_code == self.STATUS_GRACE and renewal is not None and (renewal.grace_expires_s or 0) > now:
            self.ledger.apply_subscription(uid, status=ST_PLUS_GRACE, period_id=period_id(t), period_start=t.purchase_s,
                                           period_end=t.expires_s or now, event_ts=now, grace_end=renewal.grace_expires_s,
                                           orig_txn=t.original_transaction_id)
            return "applied_grace"
        self.ledger.apply_subscription(uid, status=ST_PLUS_EXPIRED, period_id=period_id(t), period_start=t.purchase_s,
                                       period_end=t.expires_s or now, event_ts=now, orig_txn=t.original_transaction_id)
        return "applied_expired"
