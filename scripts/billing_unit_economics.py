#!/usr/bin/env python3
"""Provisional unit economics for the Free starter and the (unlimited, Billing V2) Plus plan (stdlib only, no network).

Every input is either MEASURED (cited from specs/story-specs/spec/implementation-plan/billing-measured-cost-dev-beta.md)
or an explicit ASSUMPTION flagged below. Re-run after `model_call_usage` has collected a week of data and replace the
assumptions with measured values.

    python3 scripts/billing_unit_economics.py
"""
from __future__ import annotations

# --- prices (USD per 1M tokens; packages/observability _DEFAULT_PRICING, list-price ESTIMATES) -----------------
GPT51_IN, GPT51_OUT = 1.25, 10.00
GEM_IN, GEM_OUT = 0.30, 2.50

# --- MEASURED -----------------------------------------------------------------------------------------------
AU_IN, AU_OUT = 30_200, 640                 # tokens per asset-understanding call (beta, Nov 17-18, n=439)
AU_CALLS_PER_MOMENT = 95 / 90               # Iceland: 95 AU calls for 90 moments (retries/duplicates)
# edit_plan/5.6 single-call fit from 10 retained jobs (dev + beta): input tokens ~ 5,454 + 827 per sheeted moment.
EP_IN_BASE, EP_IN_PER_SHEET = 5_454, 827
EP_OUT_ORIGINAL, EP_OUT_EXPLORE = 3_900, 3_500   # tokens; measured range 1.9k-6.1k (original), 1.9k-5.7k (explore)
REVISE_COST = 0.071                          # one text-only revise (Iceland, 23.7k in / 4.2k out); n=1

# --- ASSUMPTIONS (not measured; replace after model_call_usage data) -------------------------------------------
UNMEASURED_PER_VIDEO = 0.10    # coverage/guide/creative-intent/music-plan/duration per video (no token logs yet)
AU_THINKING_FACTOR = 1.0       # Gemini thinking tokens are not in the AU log; 1.0 = measured lower bound
STORAGE_GB_PER_USER = 5.4      # MEASURED: the heaviest beta user holds 5.4 GB of originals = $0.124/month at $0.023/GB-month
EGRESS_GB_PER_USER_MONTH = 2.0 # ASSUMPTION (no measurement): restores/downloads to other devices, at $0.09/GB
STORAGE_PER_USER_MONTH = STORAGE_GB_PER_USER * 0.023 + EGRESS_GB_PER_USER_MONTH * 0.09   # storage + egress, non-AI infra per user
RETRY_FACTOR = 1.25            # incurred-cost multiplier for retries/failed attempts (pre-5.6 jobs averaged 1.5-1.9x)
PRICE = 9.99


def au_cost(moments: int) -> float:
    per_call = AU_IN / 1e6 * GEM_IN + AU_OUT / 1e6 * GEM_OUT
    return moments * AU_CALLS_PER_MOMENT * per_call * AU_THINKING_FACTOR


def plan_cost(sheets: int, out_tokens: int) -> float:
    tin = EP_IN_BASE + EP_IN_PER_SHEET * sheets
    return tin / 1e6 * GPT51_IN + out_tokens / 1e6 * GPT51_OUT


def original(sheets: int) -> float: return plan_cost(sheets, EP_OUT_ORIGINAL)
def explore(sheets: int) -> float: return plan_cost(sheets, EP_OUT_EXPLORE)


def workloads() -> list[tuple[str, float, str]]:
    iceland_measured = 1.406  # real, lower bound
    return [
        ("1. 10-Moment Story, one video", au_cost(10) + original(10), "model (fit), not directly measured"),
        ("2. 30-Moment Story, two videos + one revise",
         au_cost(30) + original(30) + explore(30) + REVISE_COST, "model; revise measured n=1"),
        ("3. 90-Moment Story, three outputs (Iceland)", iceland_measured, "MEASURED, lower bound"),
        ("4a. 30 reused Moments, 5 more versions", 5 * explore(30), "model (fit)"),
        ("4b. 90 reused Moments, 5 more versions", 5 * explore(90), "model (fit); 89-sheet explores measured $0.126-$0.168"),
        ("5a. 30-Moment Story, 2 videos + revise, retry factor 1.25x (simulated)",
         (au_cost(30) + original(30) + explore(30) + REVISE_COST) * RETRY_FACTOR, "SIMULATION"),
        ("5b. same, retry factor 1.9x (pre-5.6 observed calls/job, worst case)",
         (au_cost(30) + original(30) + explore(30) + REVISE_COST) * 1.9, "SIMULATION"),
    ]


# --- Billing V2: YoTale Plus is UNLIMITED (owner decision 2026-11-20) ---------------------------------------------
# There is no allotment to model. The Plus section is a SENSITIVITY over video operations per paying subscriber per month.
# An "operation" is one Original, Explore (Create Another Version) or Revise. The mix and the import volumes are ASSUMPTIONS.
OPS_PER_SUBSCRIBER = (10, 30, 60, 100, 300)
OP_MIX = {"original": 0.5, "explore": 0.3, "revise": 0.2}      # ASSUMPTION: replace with the measured Original/Explore/Revise mix
NEW_MOMENTS_PER_MONTH = (30, 150)                               # ASSUMPTION: light vs heavy import behaviour


def op_cost(sheets: int) -> float:
    """Expected model cost of one video operation (measured-token fit, list prices), before retries and the unmeasured buffer."""
    return OP_MIX["original"] * original(sheets) + OP_MIX["explore"] * explore(sheets) + OP_MIX["revise"] * REVISE_COST


def subscriber_month(ops: int, sheets: int, new_moments: int, *, commission: float, retry: float = RETRY_FACTOR,
                     unmeasured: float = UNMEASURED_PER_VIDEO, infra: float | None = None, revenue: float = PRICE):
    """(AI cost, total cost, net revenue, margin) for one Plus subscriber-month. SIMULATION built on the measured fits above."""
    ai = (au_cost(new_moments) + ops * op_cost(sheets)) * retry + ops * unmeasured
    cost = ai + (STORAGE_PER_USER_MONTH if infra is None else infra)
    net = revenue * (1 - commission)
    return ai, cost, net, (net - cost) / net if net else float("nan")


def main() -> None:
    print("== Workload costs (USD, AI only; lower bounds where noted)")
    for n, c, note in workloads():
        print(f"  {n:<74s} ${c:6.3f}   [{note}]")

    print("\n== Free starter, full use: 30 Moments + 2 videos (no revenue)   [model from MEASURED token fits]")
    for sheets in (10, 30, 90):
        c2 = au_cost(30) + 2 * original(sheets)
        print(f"  videos on {sheets:>2d}-sheet stories: ${c2:5.2f} measured-model, ${c2 * RETRY_FACTOR + 2 * UNMEASURED_PER_VIDEO:5.2f} "
              f"with retry {RETRY_FACTOR}x + ${UNMEASURED_PER_VIDEO:.2f}/video unmeasured buffer")

    print(f"\n== Plus ${PRICE}/month, UNLIMITED: sensitivity by video operations per subscriber-month   [SIMULATION]")
    print(f"   per-op cost = {OP_MIX} mix of measured-fit Original/Explore + measured revise (n=1); retry {RETRY_FACTOR}x;")
    print(f"   ${UNMEASURED_PER_VIDEO:.2f}/op unmeasured buffer (ASSUMPTION); storage+egress ${STORAGE_PER_USER_MONTH:.2f}/user-month")
    print(f"  {'ops':>4s} {'story':>9s} {'new Moments':>12s} {'AI cost':>9s} {'total':>8s}   {'margin @15%':>11s} {'margin @30%':>11s}")
    for ops in OPS_PER_SUBSCRIBER:
        for sheets in (30, 90):
            for nm in NEW_MOMENTS_PER_MONTH:
                ai, cost, _n15, m15 = subscriber_month(ops, sheets, nm, commission=0.15)
                _ai, _c, _n30, m30 = subscriber_month(ops, sheets, nm, commission=0.30)
                print(f"  {ops:>4d} {sheets:>3d} sheets {nm:>12d} ${ai:8.2f} ${cost:7.2f}   {m15*100:10.0f}% {m30*100:10.0f}%")

    print("\n== Sensitivity: 60 ops/subscriber, 90-sheet stories, 150 new Moments, margin by assumption (@15% / @30%)   [SIMULATION]")
    for retry in (1.0, 1.25, 1.9):
        for unm in (0.0, 0.10, 0.30):
            _a, c15, _n, m15 = subscriber_month(60, 90, 150, commission=0.15, retry=retry, unmeasured=unm)
            _a, _c, _n, m30 = subscriber_month(60, 90, 150, commission=0.30, retry=retry, unmeasured=unm)
            print(f"  retry {retry:>4.2f}x, unmeasured ${unm:.2f}/op: cost ${c15:6.2f}  margin {m15*100:4.0f}% / {m30*100:4.0f}%")

    print("\n== Sensitivity: storage + egress per user-month (60 ops, 90-sheet stories, 150 new Moments)   [SIMULATION]")
    for infra in (0.15, 0.30, 1.00, 3.00):
        _a, c15, _n, m15 = subscriber_month(60, 90, 150, commission=0.15, infra=infra)
        _a, _c, _n, m30 = subscriber_month(60, 90, 150, commission=0.30, infra=infra)
        print(f"  storage+egress ${infra:4.2f}/user-month: cost ${c15:6.2f}  margin {m15*100:4.0f}% / {m30*100:4.0f}%")

    print("\n== Break-even ops per subscriber-month (net revenue = cost), 150 new Moments   [SIMULATION]")
    for commission in (0.15, 0.30):
        for sheets in (30, 90):
            net = PRICE * (1 - commission)
            fixed = au_cost(150) * RETRY_FACTOR + STORAGE_PER_USER_MONTH
            per_op = op_cost(sheets) * RETRY_FACTOR + UNMEASURED_PER_VIDEO
            print(f"  commission {commission*100:2.0f}%, {sheets:>2d}-sheet stories: about {(net - fixed) / per_op:5.0f} ops "
                  f"(${per_op:.3f}/op incl. retry + buffer)")
    print("\n  These numbers are for monitoring and planning only. They are not a quota and do not authorize one (owner decision).")


if __name__ == "__main__":
    main()
