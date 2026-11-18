"""Billing V1 configuration: plan limits and policy constants. Everything provisional is overridable.

Allowances and prices are PROVISIONAL (see billing-b0-cost-attribution-and-unit-economics.md): they are data, not code.
Override with ONE env var, `STORY_BILLING_PLANS_JSON`, e.g.
    {"free_starter": {"videos": 2, "moments": 30, "trial_days": 14},
     "plus": {"videos": 12, "moments": 100}, "refunds_per_period": 3}
No per-limit env vars: fewer flags, one place to change an allowance.

`STORY_BILLING_MODE` is read here too: off | observe | enforce (anything else is treated as off, the safe value).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

MODE_OFF, MODE_OBSERVE, MODE_ENFORCE = "off", "observe", "enforce"


def billing_mode() -> str:
    m = os.environ.get("STORY_BILLING_MODE", MODE_OFF).strip().lower()
    return m if m in (MODE_OFF, MODE_OBSERVE, MODE_ENFORCE) else MODE_OFF


@dataclass(frozen=True)
class PlanLimits:
    videos: int
    moments: int


@dataclass(frozen=True)
class BillingConfig:
    free_starter: PlanLimits = PlanLimits(videos=2, moments=30)
    plus: PlanLimits = PlanLimits(videos=12, moments=100)
    trial_days: int = 14
    # Controlled refund of a settled video credit for a device render failure the client reports. The server
    # cannot see on-device rendering, so the claim is capped, windowed, one-per-operation, and audited.
    refunds_per_period: int = 3
    refund_window_s: int = 24 * 3600
    # A `reserved` Moment reservation older than this is considered abandoned (the AU request crashed) and may be
    # reclaimed. AU takes ~15s; the HTTP stack gives up long before this.
    stale_reservation_s: int = 30 * 60
    config_version: str = "billing-config/1"

    @classmethod
    def from_env(cls) -> "BillingConfig":
        raw = os.environ.get("STORY_BILLING_PLANS_JSON", "").strip()
        if not raw:
            return cls()
        try:
            d = json.loads(raw)
            fs, pl = d.get("free_starter", {}), d.get("plus", {})
            base = cls()
            return cls(
                free_starter=PlanLimits(int(fs.get("videos", base.free_starter.videos)),
                                        int(fs.get("moments", base.free_starter.moments))),
                plus=PlanLimits(int(pl.get("videos", base.plus.videos)), int(pl.get("moments", base.plus.moments))),
                trial_days=int(fs.get("trial_days", base.trial_days)),
                refunds_per_period=int(d.get("refunds_per_period", base.refunds_per_period)),
                refund_window_s=int(d.get("refund_window_s", base.refund_window_s)),
                stale_reservation_s=int(d.get("stale_reservation_s", base.stale_reservation_s)),
                config_version=str(d.get("config_version", "billing-config/override")),
            )
        except (ValueError, TypeError, AttributeError):
            return cls()  # a malformed override must never break the API; defaults apply
