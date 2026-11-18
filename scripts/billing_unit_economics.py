#!/usr/bin/env python3
"""Provisional unit economics for the Free starter and Plus plans (stdlib only, no network).

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
STORAGE_PER_USER_MONTH = 0.15  # S3 media: beta owner holds 5.4 GB = $0.12/month at $0.023/GB-month
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


def plan_row(name, moments, videos, sheets_per_video, *, commission, retry=RETRY_FACTOR, unmeasured=UNMEASURED_PER_VIDEO,
             revenue=PRICE):
    au = au_cost(moments)
    plans = videos * ((original(sheets_per_video) + explore(sheets_per_video)) / 2)
    ai = (au + plans) * retry + videos * unmeasured
    cost = ai + STORAGE_PER_USER_MONTH
    net = revenue * (1 - commission)
    return name, ai, cost, net, (net - cost) / net if net else float("nan")


def main() -> None:
    print("== Workload costs (USD, AI only; lower bounds where noted)")
    for n, c, note in workloads():
        print(f"  {n:<74s} ${c:6.3f}   [{note}]")

    print("\n== Free starter, full use: 30 Moments + 2 videos (no revenue)")
    for sheets in (10, 30, 90):
        c2 = au_cost(30) + 2 * original(sheets)
        print(f"  videos on {sheets:>2d}-sheet stories: ${c2:5.2f} measured-model, ${c2 * RETRY_FACTOR + 2 * UNMEASURED_PER_VIDEO:5.2f} "
              f"with retry {RETRY_FACTOR}x + ${UNMEASURED_PER_VIDEO:.2f}/video unmeasured buffer")

    print(f"\n== Plus ${PRICE}/month, FULL allotment: 100 Moments + 12 videos (retry {RETRY_FACTOR}x, "
          f"${UNMEASURED_PER_VIDEO:.2f}/video unmeasured buffer, ${STORAGE_PER_USER_MONTH:.2f} storage)")
    print(f"  {'case':<34s}{'AI cost':>9s}{'total cost':>12s}   {'net @15%':>9s} {'margin':>7s}   {'net @30%':>9s} {'margin':>7s}")
    for label, sheets in (("small stories (30 sheets/video)", 30), ("large stories (90 sheets/video)", 90)):
        r15 = plan_row(label, 100, 12, sheets, commission=0.15)
        r30 = plan_row(label, 100, 12, sheets, commission=0.30)
        print(f"  {label:<34s}${r15[1]:8.2f}${r15[2]:11.2f}   ${r15[3]:8.2f} {r15[4]*100:6.0f}%   ${r30[3]:8.2f} {r30[4]*100:6.0f}%")

    print("\n== Sensitivity: large stories, Plus full allotment, margin by assumption (net @15% / @30%)")
    for retry in (1.0, 1.25, 1.9):
        for unm in (0.0, 0.10, 0.30):
            r15 = plan_row("", 100, 12, 90, commission=0.15, retry=retry, unmeasured=unm)
            r30 = plan_row("", 100, 12, 90, commission=0.30, retry=retry, unmeasured=unm)
            print(f"  retry {retry:>4.2f}x, unmeasured ${unm:.2f}/video: cost ${r15[2]:5.2f}  margin {r15[4]*100:4.0f}% / {r30[4]*100:4.0f}%")

    print("\n== Break-even videos (large stories) for Plus at 12-video price, margin 70% target @15% commission")
    net = PRICE * 0.85
    budget = net * 0.30 - STORAGE_PER_USER_MONTH
    per_video = (au_cost(100) / 12 + (original(90) + explore(90)) / 2) * RETRY_FACTOR + UNMEASURED_PER_VIDEO
    print(f"  AI budget for 70% margin: ${budget:.2f}; cost per video incl. its AU share: ${per_video:.3f}; "
          f"=> about {budget / per_video:.1f} large-story videos")


if __name__ == "__main__":
    main()
