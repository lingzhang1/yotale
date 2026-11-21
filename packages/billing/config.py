"""Billing V1 configuration: plan limits (reviewed code) and the one runtime switch, `STORY_BILLING_MODE`.

Single configuration source rules (owner decision, 2026-11-18):
* The MODE (`off | observe | enforce`) is owned by `release/release.json` (environments.<env>.billing_mode). CDK emits it to the API
  and the worker, `scripts/release_config_gate.py` verifies the running values equal the manifest, and this module validates it at
  application startup. There is no other way to set it.
* UNSET means off (the current beta rollout posture). An explicitly set but invalid value is an error, never silently off: a typo must
  not quietly disable (or quietly enable) a money-relevant gate. Startup (`validate_billing_config`) and every read raise
  `BillingConfigError`, so a bad deployment fails its health check instead of running with the wrong posture.
* Allowances and trial length are CODE (`BillingConfig` below), changed by a reviewed PR and stamped with `config_version` on every
  entitlement. There is deliberately NO environment override for them: a second, unaudited source for the numbers that decide
  whether a customer is charged is rejected by the release gate (`STORY_BILLING_PLANS_JSON` is a removed setting).
* The values are PROVISIONAL (see billing-b0-cost-attribution-and-unit-economics.md) and must not change before B0 produces broader
  real cost data.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

MODE_OFF, MODE_OBSERVE, MODE_ENFORCE = "off", "observe", "enforce"
VALID_MODES = (MODE_OFF, MODE_OBSERVE, MODE_ENFORCE)
REMOVED_ENV = "STORY_BILLING_PLANS_JSON"


class BillingConfigError(RuntimeError):
    """The billing configuration is invalid. Raised instead of falling back, so the posture is never guessed."""


def billing_mode() -> str:
    raw = os.environ.get("STORY_BILLING_MODE")
    if raw is None:
        return MODE_OFF                       # unset: the current beta rollout default
    mode = raw.strip().lower()
    if mode not in VALID_MODES:
        raise BillingConfigError(
            f"STORY_BILLING_MODE={raw!r} is invalid; expected one of {', '.join(VALID_MODES)} (unset means off)")
    return mode


def validate_billing_config() -> str:
    """Startup validation (API `create_app`, worker handler). Returns the effective mode or raises BillingConfigError."""
    if os.environ.get(REMOVED_ENV) is not None:
        raise BillingConfigError(f"{REMOVED_ENV} is a removed setting; allowances are reviewed code in packages/billing/config.py")
    BillingConfig().validate()
    return billing_mode()


@dataclass(frozen=True)
class PlanLimits:
    videos: int
    moments: int


@dataclass(frozen=True)
class BillingConfig:
    free_starter: PlanLimits = PlanLimits(videos=2, moments=30)
    # Billing V2 (owner decision 2026-11-20): YoTale Plus is UNLIMITED ordinary creation and analysis while the subscription is active
    # or in grace. There is deliberately no Plus PlanLimits: unlimited is derived from plan + effective status at read time
    # (Entitlement.unlimited_at), never stored, and no finite Plus totals are written. Operational protection (rate limits, active-job
    # concurrency, the global breaker, WAF) is separate and lives in throttle/quota_gate, not here.
    trial_days: int = 14
    # Controlled refund of a settled video credit for a device render failure the client reports. The server cannot see
    # on-device rendering, so the claim is capped, windowed, one-per-operation, evidence-bearing and audited.
    refunds_per_period: int = 3                  # admin_granted (finite) per period; unlimited accounts have nothing to refund
    free_refunds: int = 1                        # Free starter, for the whole starter allowance
    refund_window_s: int = 24 * 3600
    refund_min_render_attempts: int = 2          # a claim must state that the stored plan was re-rendered before giving up
    # A `reserved` video reservation is never reclaimed by age (the job store is its authority). A `reserved` MOMENT reservation
    # older than this is presumed abandoned (AU takes about 15s; the HTTP stack gives up long before this) and may be reclaimed.
    moment_stale_s: int = 300
    # How long an identical in-flight analysis request waits for the one that owns the work before answering "in progress".
    analysis_wait_s: float = 25.0
    config_version: str = "billing-config/3"     # 3 = Billing V2: unlimited Plus, no finite Plus totals

    def validate(self) -> None:
        if self.free_starter.videos < 0 or self.free_starter.moments < 0:
            raise BillingConfigError("free_starter allowances must be non-negative")
        if self.trial_days < 1 or self.refunds_per_period < 0 or self.free_refunds < 0 or self.refund_window_s < 0 or self.moment_stale_s < 30:
            raise BillingConfigError("invalid trial/refund/stale configuration")
