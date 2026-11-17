"""Rule-based HIGHLIGHTS sizing (highlights_sizing/1). No model call.

Why: the frozen duration_recommendation/1 model call returned a Highlights range anchored on the deterministic
feasible-band floor (2 s x Moment count: 38 Moments -> a 76 s floor -> "about 80 s"), so a short-form Highlights
recommendation scaled with how many clips were imported, not with how many genuinely attractive opportunities
there are. This module replaces ONLY the Highlights range with a deterministic function of the AU visual payoff
windows. Full Story, the frozen prompt, the evidence function and Custom duration are untouched.

Formula (every constant is named below and covered by tests):
    opportunities  = distinct AU `payoff` windows (merged per Moment, at most MAX_WINDOWS_PER_MOMENT per Moment)
    raw seconds    = opportunities x SHOT_S x USE_FRACTION     (a typical 2.2 s shot, ~70% of windows used)
    point          = raw rounded to 5 s, clamped to [MIN_S, MAX_S], then capped by the useful-footage ceiling
    range          = point +- 15% (the Create screen shows the midpoint)

An AU `payoff` tag says where the analysis saw an action worth showing; it is NOT a measure of how appealing the
footage is. It is used because it is the only per-Moment signal available before planning. When the request carries
no visual evidence at all (an older client, or Moments analysed before editorial AU existed) a damped footage-only
estimate is used and the result is flagged uncertain; it never reintroduces a per-Moment floor.
"""
from __future__ import annotations

from typing import Any

SIZING_VERSION = "highlights_sizing/1"
SHOT_S = 2.2                    # typical Highlights shot (the v5.6 strategy prefers 1-2.5 s)
USE_FRACTION = 0.7              # share of payoff windows a selective cut actually uses
MIN_S = 15.0                    # shortest Highlights worth suggesting
MAX_S = 60.0                    # longest short-form Highlights suggestion
MAX_WINDOWS_PER_MOMENT = 2      # one clip rarely yields more than two distinct shots
MIN_WINDOW_S = 0.5              # ignore degenerate windows
SPREAD = 0.15                   # +- around the point
ROUND_TO_S = 5.0
FALLBACK_OPPORTUNITY_PER_MOMENT = 0.5   # footage-only estimate: about half the Moments hold a payoff
FALLBACK_MIN_MOMENT_USEFUL_S = 1.5


def _pairs(raw: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for w in raw or []:
        s = e = None
        if isinstance(w, (list, tuple)) and len(w) >= 2:
            s, e = w[0], w[1]
        elif isinstance(w, dict):
            s, e = w.get("start", w.get("start_time")), w.get("end", w.get("end_time"))
        try:
            s, e = float(s), float(e)
        except (TypeError, ValueError):
            continue
        if e - s >= MIN_WINDOW_S:
            out.append((s, e))
    return out


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    spans = sorted(spans)
    merged: list[tuple[float, float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def moment_payoff_windows(m: dict) -> tuple[bool, list[tuple[float, float]]]:
    """(has_visual_evidence, payoff windows) for one Moment. Evidence is present when the Moment carries the compact
    `payoff_windows` list (even an empty one) or an AU `editorial.visual_candidates` list."""
    if isinstance(m.get("payoff_windows"), list):
        return True, _merge(_pairs(m["payoff_windows"]))
    ed = m.get("editorial")
    if isinstance(ed, dict) and isinstance(ed.get("visual_candidates"), list):
        spans = _pairs([(v.get("start_time"), v.get("end_time")) for v in ed["visual_candidates"]
                        if isinstance(v, dict) and v.get("role") == "payoff"])
        return True, _merge(spans)
    return False, []


def count_opportunities(moments: list[dict]) -> tuple[int, int, bool]:
    """(distinct payoff windows, Moments holding one, any visual evidence present)."""
    windows = with_payoff = 0
    seen = False
    for m in moments or []:
        if not isinstance(m, dict):
            continue
        has, ws = moment_payoff_windows(m)
        seen = seen or has
        n = min(len(ws), MAX_WINDOWS_PER_MOMENT)
        windows += n
        with_payoff += 1 if n else 0
    return windows, with_payoff, seen


def recommend_highlights(moments: list[dict], evidence: dict) -> dict:
    """Deterministic Highlights range. Returns {range, point_seconds, source, opportunities, ...}."""
    ceiling = float((evidence.get("feasible_band_seconds") or [0, 0])[1] or 0.0)
    windows, with_payoff, seen = count_opportunities(moments)
    if seen:
        source, opportunities, uncertain = "payoff_windows", float(windows), False
    else:
        usable = sum(1 for p in evidence.get("per_moment") or []
                     if float(p.get("useful_coverage_seconds") or 0.0) >= FALLBACK_MIN_MOMENT_USEFUL_S)
        source, opportunities, uncertain = "footage_only", usable * FALLBACK_OPPORTUNITY_PER_MOMENT, True
    raw = opportunities * SHOT_S * USE_FRACTION
    point = round(raw / ROUND_TO_S) * ROUND_TO_S
    point = min(max(point, MIN_S), MAX_S)
    if ceiling > 0:
        point = min(point, ceiling)            # never beyond the material
    low_limit = min(5.0, point)
    delta = max(0.0, min(round(point * SPREAD), point - low_limit, (ceiling - point) if ceiling > 0 else 1e9))
    lo, hi = round(point - delta, 1), round(point + delta, 1)
    return {"range": [lo, hi], "point_seconds": round(point, 1), "source": source, "uncertain": uncertain,
            "opportunities": round(opportunities, 1), "moments_with_payoff": with_payoff, "raw_seconds": round(raw, 1),
            "version": SIZING_VERSION}


def apply_highlights_sizing(rec: dict, moments: list[dict], evidence: dict) -> dict:
    """Replace the model's Highlights range with the rule-based one; leave every other field of the recommendation as
    returned (Full Story range, ceiling, rationale). The model's own value is kept under `sizing.model_highlights_range`
    for diagnostics. Never raises: on any problem the recommendation is returned unchanged."""
    try:
        h = recommend_highlights(moments, evidence)
    except Exception:
        return rec
    out = dict(rec)
    out["sizing"] = {"highlights": {**{k: h[k] for k in ("version", "source", "uncertain", "opportunities",
                                                         "moments_with_payoff", "raw_seconds")},
                                    "model_highlights_range": rec.get("highlights_range_seconds")}}
    out["highlights_range_seconds"] = h["range"]
    return out


__all__ = ["SIZING_VERSION", "recommend_highlights", "apply_highlights_sizing", "count_opportunities",
           "moment_payoff_windows"]
