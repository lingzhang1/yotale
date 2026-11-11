"""Deterministic DURATION FIT for a technically-valid EditPlan (no model call, no prompt change).

Why: since the owner's 2026-10-25 decision duration never blocks a plan (good: a playable cut always ships), but
nothing then pulled an over-long cut back toward the requested length. Runtime evidence (TMB Hiking, dev
2026-11-10): rendered length == sum of segment output durations (transitions are dropped by the contract, so
straight cuts), and the planner's totals ran +15% / +21% / +46% over target; offline replays +29..58%.

What it does (only when the delivered total is more than FIT_TRIGGER over target, aiming AT the target):
  A. drop a REDUNDANT re-cut: a second segment of a Moment already in the edit that holds no AU payoff peak;
  B. trim slack proportionally from every trimmable segment, cutting lead-in/tail AWAY from the AU payoff
     (visual-candidate peak), never below MIN_SEGMENT_OUT_S, never outside the original source range;
  C. if still over the band, drop optional low-value segments (no AU payoff peak), lowest value first.
Never touched: the opening and ending segments' presence, any segment of a directive-referenced Moment
(opening / ending / must_include / ordering / adjacency) — those may only be trimmed, never dropped — and any
segment with a music anchor (beat/downbeat/highlight). Speed, native_audio, order and asset ids are preserved;
source ranges only shrink, so they stay within real footage and within the original useful range.
Undershoot is never "fixed" here (we do not invent or extend footage); it is only reported.

The caller re-validates the fitted plan and adopts it only if it is still technically valid and does not lower
creative-objective satisfaction; otherwise the original plan ships unchanged.
"""
from __future__ import annotations

import copy
from typing import Any

FIT_TRIGGER = 0.10          # fit only when delivered total > target * (1 + FIT_TRIGGER)
FIT_BAND = 0.10             # stage C stops dropping once total <= target * (1 + FIT_BAND)
MIN_SEGMENT_OUT_S = 2.0     # never trim a segment's output below this (or below its original length)
PAYOFF_HALF_WINDOW_S = 1.25 # protected source window around an AU visual-candidate peak
_EPS = 1e-6


def delivered_total_seconds(segs: list[dict]) -> float:
    """What the device actually renders: transitions are dropped by the EditPlan/2 contract (_to_contract sets
    transition=None) so the timeline is straight cuts — the plain sum of output durations, with no crossfade
    overlap subtracted."""
    return round(sum(float(s.get("output_duration_seconds") or 0.0) for s in segs), 3)


def _speed(s: dict) -> float:
    try:
        v = float(s.get("speed") or 1.0)
        return v if v > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _anchored(s: dict) -> bool:
    ma = s.get("music_alignment") or {}
    return isinstance(ma, dict) and (ma.get("anchor") or "none") not in ("none", "")


def _peaks(moment: dict | None) -> list[tuple[float, float]]:
    """(peak_time, confidence) of the Moment's AU visual candidates (advisory payoff hints)."""
    out: list[tuple[float, float]] = []
    ed = (moment or {}).get("editorial") or {}
    for vc in ed.get("visual_candidates") or []:
        if isinstance(vc, dict) and isinstance(vc.get("peak_time"), (int, float)):
            c = vc.get("confidence")
            out.append((float(vc["peak_time"]), float(c) if isinstance(c, (int, float)) else 0.0))
    return out


def _events(moment: dict | None) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for e in (moment or {}).get("events") or []:
        if isinstance(e, dict) and isinstance(e.get("start_time"), (int, float)):
            a = float(e["start_time"])
            b = float(e["end_time"]) if isinstance(e.get("end_time"), (int, float)) else a
            out.append((a, max(a, b)))
    return out


def _payoff(seg: dict, moment: dict | None) -> float | None:
    """The strongest AU payoff peak inside this segment's source range, if any."""
    a, b = float(seg["source_start_seconds"]), float(seg["source_end_seconds"])
    inside = [(p, c) for p, c in _peaks(moment) if a - _EPS <= p <= b + _EPS]
    return max(inside, key=lambda pc: (pc[1], -pc[0]))[0] if inside else None


def _core(seg: dict, moment: dict | None, whole_event: bool = False) -> tuple[float, float]:
    """Protected SOURCE window: around the payoff peak — widened to the whole containing AU event when the
    segment keeps its native audio (a kept sound/action is not cut mid-event) or when `whole_event` (Full Story:
    complete meaningful actions); else centered. At least MIN_SEGMENT_OUT_S of output, always inside the
    segment's own range."""
    a, b = float(seg["source_start_seconds"]), float(seg["source_end_seconds"])
    sp = _speed(seg)
    need = min(b - a, MIN_SEGMENT_OUT_S * sp)
    p = _payoff(seg, moment)
    if p is not None:
        lo, hi = p - PAYOFF_HALF_WINDOW_S, p + PAYOFF_HALF_WINDOW_S
        if whole_event or (seg.get("native_audio") or "keep") == "keep":
            for ea, eb in _events(moment):
                if ea - _EPS <= p <= eb + _EPS:
                    lo, hi = min(lo, ea), max(hi, eb)
    else:
        mid = (a + b) / 2
        lo, hi = mid - need / 2, mid + need / 2
    lo, hi = max(a, lo), min(b, hi)
    if hi - lo < need:  # expand symmetrically inside [a, b] to the floor
        grow = need - (hi - lo)
        lo = max(a, lo - grow / 2)
        hi = min(b, hi + grow / 2)
        if hi - lo < need:
            lo, hi = (a, a + need) if lo == a else (b - need, b)
    return lo, hi


def _set_range(seg: dict, a: float, b: float) -> None:
    seg["source_start_seconds"] = round(a, 3)
    seg["source_end_seconds"] = round(b, 3)
    seg["output_duration_seconds"] = round((seg["source_end_seconds"] - seg["source_start_seconds"]) / _speed(seg), 3)
    tr = seg.get("transition")
    if isinstance(tr, dict) and isinstance(tr.get("duration_seconds"), (int, float)):
        tr["duration_seconds"] = min(float(tr["duration_seconds"]), seg["output_duration_seconds"])


def fit_plan_duration(plan: dict, inputs: Any, protected_ids: set[str] | None = None) -> tuple[dict, dict]:
    """Return (fitted_plan_copy, report). The input plan is never mutated. report['applied'] says whether
    anything changed; the caller decides adoption after re-validation."""
    target = float((inputs.creative_intent or {}).get("target_duration_seconds") or 0.0)
    segs_in = sorted(plan.get("segments") or [], key=lambda s: s.get("order", 0))
    before = delivered_total_seconds(segs_in)
    report: dict[str, Any] = {"applied": False, "target_s": target, "before_s": before, "after_s": before,
                              "trimmed": 0, "dropped": [], "within_band": None}
    if target <= 0 or not segs_in:
        report["reason"] = "no_target"
        return plan, report
    report["within_band"] = before <= target * (1 + FIT_BAND) + _EPS
    if before <= target * (1 + FIT_TRIGGER) + _EPS:
        report["reason"] = "within_band" if before >= target * (1 - FIT_BAND) - _EPS else "undershoot_not_extended"
        return plan, report

    moments = {str(m.get("id")).lower(): m for m in (inputs.moments or []) if isinstance(m, dict)}
    protected = {x.lower() for x in (protected_ids or set())}
    segs = [copy.deepcopy(s) for s in segs_in]
    aim, band = target, target * (1 + FIT_BAND)

    full_story = (getattr(inputs, "editorial_type", None) or "") == "full_story"

    def mom(s):
        return moments.get(str(s.get("asset_id")).lower())

    def core(s):
        return _core(s, mom(s), whole_event=full_story)

    def droppable(i: int, s: dict) -> bool:
        return (0 < i < len(segs) - 1 and len(segs) > 2 and not _anchored(s)
                and str(s.get("asset_id")).lower() not in protected)

    def drop(i: int, why: str) -> None:
        s = segs.pop(i)
        report["dropped"].append({"asset_id": str(s.get("asset_id")).lower(), "why": why,
                                  "out_s": float(s.get("output_duration_seconds") or 0)})

    # A. redundant re-cut of a Moment already in the edit: a later occurrence goes when it holds no payoff of its
    # own, or when at least half of it REPEATS footage an earlier kept segment of that Moment already shows.
    kept_ranges: dict[str, list[tuple[float, float]]] = {}
    i = 0
    while i < len(segs) and delivered_total_seconds(segs) > aim + _EPS:
        s = segs[i]
        aid = str(s.get("asset_id")).lower()
        a, b = float(s["source_start_seconds"]), float(s["source_end_seconds"])
        if aid in kept_ranges and droppable(i, s):
            rep = max((min(b, y) - max(a, x) for x, y in kept_ranges[aid]), default=0.0)
            if rep >= 0.5 * (b - a):
                drop(i, "repeats_footage")
                continue
            if _payoff(s, mom(s)) is None:
                drop(i, "repeat_moment_no_payoff")
                continue
        kept_ranges.setdefault(aid, []).append((a, b))
        i += 1

    # B. proportional slack trim away from the payoff.
    excess = delivered_total_seconds(segs) - aim
    if excess > _EPS:
        slack = []
        for s in segs:
            if _anchored(s):
                slack.append(0.0)
                continue
            lo, hi = core(s)
            slack.append(max(0.0, float(s["output_duration_seconds"]) - (hi - lo) / _speed(s)))
        total_slack = sum(slack)
        if total_slack > _EPS:
            frac = min(1.0, excess / total_slack)
            for s, sl in zip(segs, slack):
                if sl <= _EPS:
                    continue
                cut_src = sl * frac * _speed(s)
                a, b = float(s["source_start_seconds"]), float(s["source_end_seconds"])
                lo, hi = core(s)
                lead, tail = lo - a, b - hi
                room = lead + tail
                if room <= _EPS:
                    continue
                ca = min(lead, cut_src * lead / room)
                cb = min(tail, cut_src - ca)
                _set_range(s, a + ca, b - cb)
                report["trimmed"] += 1

    # C. still over the band: drop optional segments without an AU payoff, lowest value first.
    while delivered_total_seconds(segs) > band + _EPS:
        cands = [(i, s) for i, s in enumerate(segs) if droppable(i, s) and _payoff(s, mom(s)) is None]
        if not cands:
            break
        # lowest value: no visual-candidate overlap first, then the shortest (least screen-time lost per drop).
        def _cand_overlap(s):
            ed = (mom(s) or {}).get("editorial") or {}
            a, b = float(s["source_start_seconds"]), float(s["source_end_seconds"])
            return any(isinstance(v, dict) and isinstance(v.get("start_time"), (int, float))
                       and isinstance(v.get("end_time"), (int, float)) and v["start_time"] < b and v["end_time"] > a
                       for v in ed.get("visual_candidates") or [])
        i, _ = min(cands, key=lambda t: (_cand_overlap(t[1]), float(t[1]["output_duration_seconds"])))
        drop(i, "optional_no_payoff")

    for k, s in enumerate(segs):
        s["order"] = k
    after = delivered_total_seconds(segs)
    fitted = dict(plan)
    fitted["segments"] = segs
    report.update(applied=after < before - _EPS, after_s=after, within_band=after <= band + _EPS,
                  reason="fitted" if after <= band + _EPS else "over_band_after_fit")
    return fitted, report
