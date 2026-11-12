"""Deterministic DURATION FIT for a technically-valid EditPlan (no model call, no prompt change).

Why: since the owner's 2026-10-25 decision duration never blocks a plan (a playable cut always ships), but
nothing then pulled an over-long cut back toward the requested length. Runtime evidence (TMB Hiking, dev
2026-11-10): rendered length == sum of segment output durations (the EditPlan/2 contract drops transitions, so
the device renders straight cuts), and the planner's totals ran +15% / +21% / +46% over target.

Runs only when the DELIVERED total (Σ output durations) is more than FIT_TRIGGER over target; aims AT the target.
  A. drop a LITERAL repeat: a later segment whose source range is >= LITERAL_REPEAT_OVERLAP covered by an earlier
     kept segment of the same Moment (the same footage twice). A separate action from the same Moment, or a
     re-cut the planner labels as a deliberate callback/reprise, is NOT a literal repeat and stays;
  B. trim slack proportionally, cutting lead-in / tail AWAY from the protected core of each shot;
  C. if still over the band, drop optional shots with no AU payoff, least valuable first.

Protected core of a shot (never trimmed into): from the first to the last AU visual-candidate payoff peak inside
it (±PAYOFF_HALF_WINDOW_S) — every payoff, not only the strongest — widened to the whole containing AU events for
Full Story (complete actions) and for kept native audio; a kept-audio shot without a payoff keeps its main AU
event. A kept-audio shot's trimmed edges are also snapped to AU event boundaries, so its sound never starts or
stops mid-event. A trim never takes a shot below MIN_TRIM_OUT_S (the final shot below MIN_FINAL_OUT_S: the
renderer's 1 s soundtrack end fade must fit inside it — a 0.79 s trimmed ending crashed the iOS audio mix on beta,
2026-11-12), and never below RETAIN_FRACTION of the length the
planner chose for it. There is NO absolute minimum shot length: a short planner shot is never lengthened or
rejected, and the validator is unchanged.

Never changed: the opening and ending shots' presence; any segment of a directive-referenced Moment (trim only);
music-anchored segments and everything BEFORE the last music anchor (their cut times stay on the beat grid);
speed, native_audio, transition type, relative order, asset ids. Ranges only shrink (inside real footage and the
original useful range). Undershoot is never "fixed" (no footage is invented or extended). The caller adopts the
result only when it re-validates and creative-objective satisfaction does not drop; otherwise nothing changes.
"""
from __future__ import annotations

import copy
import re
from typing import Any

FIT_TRIGGER = 0.10            # fit only when delivered total > target * (1 + FIT_TRIGGER)
FIT_BAND = 0.10               # stage C stops dropping once total <= target * (1 + FIT_BAND)
RETAIN_FRACTION = 0.5         # a trim keeps at least this fraction of the shot the planner chose
MIN_TRIM_OUT_S = 1.0          # a trim never takes a shot below this (a shorter PLANNER shot is left as-is)
MIN_FINAL_OUT_S = 2.0         # ... nor the final shot below this (the soundtrack's 1 s end fade lives in it)
PAYOFF_HALF_WINDOW_S = 1.25   # protected source window around an AU visual-candidate peak
LITERAL_REPEAT_OVERLAP = 0.8  # a later same-Moment segment this much covered by earlier footage is a literal repeat
_CALLBACK_RE = re.compile(r"\b(callback|reprise|echo|bookend|recap|motif|mirror|refrain|again)\b", re.I)
_EPS = 1e-6


def delivered_total_seconds(segs: list[dict]) -> float:
    """What the device renders for a planner plan: the EditPlan/2 contract drops transitions (_to_contract sets
    transition=None), so the timeline is straight cuts — the plain sum of output durations, with NO crossfade
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


def _range(s: dict) -> tuple[float, float]:
    return float(s["source_start_seconds"]), float(s["source_end_seconds"])


def _peaks(moment: dict | None) -> list[tuple[float, float]]:
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
    a, b = _range(seg)
    inside = [(p, c) for p, c in _peaks(moment) if a - _EPS <= p <= b + _EPS]
    return max(inside, key=lambda pc: (pc[1], -pc[0]))[0] if inside else None


def _core(seg: dict, moment: dict | None, whole_event: bool) -> tuple[float, float] | None:
    """Protected SOURCE window inside the segment, or None when nothing in it is protected.

    EVERY AU visual-candidate payoff peak inside the segment is protected, not only the strongest: a shot the
    planner chose that holds two payoffs (raise the poles, then turn to camera) keeps both, so the window spans
    from the first peak to the last (±PAYOFF_HALF_WINDOW_S). For Full Story and kept native audio it widens to
    the whole AU events containing those peaks."""
    a, b = _range(seg)
    keep_audio = (seg.get("native_audio") or "keep") == "keep"
    inside = [p for p, _c in _peaks(moment) if a - _EPS <= p <= b + _EPS]
    if inside:
        lo, hi = min(inside) - PAYOFF_HALF_WINDOW_S, max(inside) + PAYOFF_HALF_WINDOW_S
        if whole_event or keep_audio:
            for ea, eb in _events(moment):
                if any(ea - _EPS <= p <= eb + _EPS for p in inside):
                    lo, hi = min(lo, ea), max(hi, eb)
        return max(a, lo), min(b, hi)
    if keep_audio:   # kept sound with no visual payoff: keep its main AU event intact
        best = max(_events(moment), key=lambda e: min(b, e[1]) - max(a, e[0]), default=None)
        if best is not None and min(b, best[1]) - max(a, best[0]) > _EPS:
            return max(a, best[0]), min(b, best[1])
    return None


def _snap_to_events(new_a: float, new_b: float, a: float, b: float, lo: float, hi: float,
                    events: list[tuple[float, float]], min_src: float) -> tuple[float, float]:
    """Kept native audio: an edge that would fall INSIDE an AU event moves to the nearest event boundary, so the
    shot never starts or ends in the middle of a sound/action. Edges outside every event (or a Moment with no AU
    events) are left as trimmed. Candidate starts are the original start and every event boundary up to the
    protected core; candidate ends the original end and every boundary from the core on. The untrimmed original
    edge is always a candidate, so the shot never drops below `min_src` of source."""
    def inside(x: float) -> bool:
        return any(ea + _EPS < x < eb - _EPS for ea, eb in events)

    bounds = sorted({x for e in events for x in e})
    # Prefer CLEAN cut points (inside no event at all — AU events can overlap); the original edges always qualify.
    clean = [x for x in bounds if not inside(x)]
    sa, sb = new_a, new_b
    if inside(new_a):
        starts = [a] + [x for x in clean if a + _EPS < x <= lo + _EPS]
        sa = min((x for x in starts if sb - x >= min_src - _EPS), key=lambda x: abs(x - new_a), default=a)
    if inside(new_b):
        ends = [b] + [x for x in clean if hi - _EPS <= x < b - _EPS]
        sb = min((x for x in ends if x - sa >= min_src - _EPS), key=lambda x: abs(x - new_b), default=b)
    return sa, sb


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
                              "trimmed": 0, "dropped": [], "changes": [], "within_band": None}
    if target <= 0 or not segs_in:
        report["reason"] = "no_target"
        return plan, report
    report["within_band"] = before <= target * (1 + FIT_BAND) + _EPS
    if before <= target * (1 + FIT_TRIGGER) + _EPS:
        report["reason"] = "within_band" if before >= target * (1 - FIT_BAND) - _EPS else "undershoot_not_extended"
        return plan, report

    moments = {str(m.get("id")).lower(): m for m in (inputs.moments or []) if isinstance(m, dict)}
    protected = {x.lower() for x in (protected_ids or set())}
    full_story = (getattr(inputs, "editorial_type", None) or "") == "full_story"
    segs = [copy.deepcopy(s) for s in segs_in]
    for k, s in enumerate(segs):
        s["_orig"] = (k, *_range(s))
    last_anchor = max((k for k, s in enumerate(segs) if _anchored(s)), default=-1)
    aim, band = target, target * (1 + FIT_BAND)
    floor_total = target * (1 - FIT_BAND)   # a DROP never takes the video below this (trims stop at `aim`)

    def mom(s):
        return moments.get(str(s.get("asset_id")).lower())

    def editable(s) -> bool:
        # nothing at/before the last music anchor moves (that would shift the anchored cut off the beat grid)
        return s["_orig"][0] > last_anchor and not _anchored(s)

    def droppable(i: int, s: dict) -> bool:
        return (0 < i < len(segs) - 1 and len(segs) > 2 and editable(s)
                and str(s.get("asset_id")).lower() not in protected)

    def drop(i: int, why: str) -> None:
        s = segs.pop(i)
        report["dropped"].append({"order": s["_orig"][0], "asset_id": str(s.get("asset_id")).lower(), "why": why,
                                  "range": [s["_orig"][1], s["_orig"][2]],
                                  "planned_out_s": round((s["_orig"][2] - s["_orig"][1]) / _speed(s), 3),
                                  "out_s": float(s.get("output_duration_seconds") or 0)})

    # A. literal repeats of the same footage (a later, mostly-covered re-cut that is not a labelled callback).
    kept_ranges: dict[str, list[tuple[float, float]]] = {}
    i = 0
    while i < len(segs) and delivered_total_seconds(segs) > aim + _EPS:
        s = segs[i]
        aid = str(s.get("asset_id")).lower()
        a, b = _range(s)
        covered = sum(max(0.0, min(b, y) - max(a, x)) for x, y in kept_ranges.get(aid, []))
        if (aid in kept_ranges and droppable(i, s) and covered >= LITERAL_REPEAT_OVERLAP * (b - a)
                and not _CALLBACK_RE.search(str(s.get("narrative_role") or ""))
                and delivered_total_seconds(segs) - float(s["output_duration_seconds"]) >= floor_total - _EPS):
            drop(i, "literal_repeat")
            continue
        kept_ranges.setdefault(aid, []).append((a, b))
        i += 1

    # B. proportional slack trim away from each shot's protected core. Pass 1 trims only shots longer than the
    # plan's median shot (long holds absorb the cut; short punchy shots stay exactly as the planner cut them);
    # pass 2 shares any remaining excess across every trimmable shot.
    limits: dict[int, tuple[float, float, float]] = {}   # id(seg) -> (min_out, core_lo, core_hi)
    for s in segs:
        if not editable(s):
            continue
        a, b = _range(s)
        out = float(s["output_duration_seconds"])
        core = _core(s, mom(s), whole_event=full_story)
        floor_out = MIN_FINAL_OUT_S if s is segs[-1] else MIN_TRIM_OUT_S
        min_out = max(RETAIN_FRACTION * out, min(out, floor_out),
                      ((core[1] - core[0]) / _speed(s)) if core else 0.0)
        if out - min_out > _EPS:
            lo, hi = core if core else ((a + b) / 2, (a + b) / 2)
            limits[id(s)] = (min_out, lo, hi)
    outs = sorted(float(s["output_duration_seconds"]) for s in segs)
    n = len(outs)
    median = outs[n // 2] if n % 2 else (outs[n // 2 - 1] + outs[n // 2]) / 2
    trimmed_ids: set[int] = set()
    for only_long in (True, False):
        excess = delivered_total_seconds(segs) - aim
        if excess <= _EPS:
            break
        pool = []
        for s in segs:
            lim = limits.get(id(s))
            if not lim or (only_long and float(s["output_duration_seconds"]) <= median + _EPS):
                continue
            slack = float(s["output_duration_seconds"]) - lim[0]
            if slack > _EPS:
                pool.append((s, slack, lim))
        total_slack = sum(x[1] for x in pool)
        if total_slack <= _EPS:
            continue
        frac = min(1.0, excess / total_slack)
        for s, slack, (min_out, lo, hi) in pool:
            a, b = _range(s)
            cut_src = slack * frac * _speed(s)
            lead, tail = max(0.0, lo - a), max(0.0, b - hi)
            room = lead + tail
            if room <= _EPS:
                continue
            ca = min(lead, cut_src * lead / room)
            cb = min(tail, cut_src - ca)
            na, nb = a + ca, b - cb
            if (s.get("native_audio") or "keep") == "keep":
                na, nb = _snap_to_events(na, nb, a, b, lo, hi, _events(mom(s)), min_out * _speed(s))
            if (na, nb) == (a, b):
                continue
            _set_range(s, na, nb)
            trimmed_ids.add(id(s))
    report["trimmed"] = len(trimmed_ids)

    # C. still over the band: drop an optional shot with no AU payoff — the one whose removal lands CLOSEST to the
    # target, never one that would take the video more than FIT_BAND under it (if every option would, the video
    # stays a little long and is disclosed). Ties: no visual-candidate overlap first, then non-kept audio.
    # (Was "longest first": a 21 s drop took a 68 s Full Story to 55 s on beta, 2026-11-12.)
    def _cand_overlap(s):
        ed = (mom(s) or {}).get("editorial") or {}
        a, b = _range(s)
        return any(isinstance(v, dict) and isinstance(v.get("start_time"), (int, float))
                   and isinstance(v.get("end_time"), (int, float)) and v["start_time"] < b and v["end_time"] > a
                   for v in ed.get("visual_candidates") or [])

    while delivered_total_seconds(segs) > band + _EPS:
        # Full Story keeps annotated context (any AU visual-candidate overlap); only unannotated filler may go.
        total = delivered_total_seconds(segs)
        cands = [(i, s) for i, s in enumerate(segs) if droppable(i, s) and _payoff(s, mom(s)) is None
                 and not (full_story and _cand_overlap(s))
                 and total - float(s["output_duration_seconds"]) >= floor_total - _EPS]
        if not cands:
            break
        i, _ = min(cands, key=lambda t: (round(abs(total - float(t[1]["output_duration_seconds"]) - aim), 3),
                                         _cand_overlap(t[1]), (t[1].get("native_audio") or "keep") == "keep"))
        drop(i, "optional_no_payoff")

    for k, s in enumerate(segs):
        o_order, oa, ob = s.pop("_orig")
        if (round(oa, 3), round(ob, 3)) != (round(float(s["source_start_seconds"]), 3), round(float(s["source_end_seconds"]), 3)):
            report["changes"].append({"order": o_order, "asset_id": str(s.get("asset_id")).lower(),
                                      "from": [oa, ob], "to": [s["source_start_seconds"], s["source_end_seconds"]]})
        s["order"] = k
    after = delivered_total_seconds(segs)
    fitted = dict(plan)
    fitted["segments"] = segs
    report.update(applied=after < before - _EPS, after_s=after, within_band=after <= band + _EPS,
                  reason="fitted" if after <= band + _EPS else "over_band_after_fit")
    return fitted, report
