"""P1-F — deterministic AU evidence -> contact-sheet frame selection (shared policy v2).

Given the ACTUAL sampled-frame timestamps for one Moment and its AU understanding (events, visual
candidates, narrative candidates), choose WHICH sampled frames the Moment's contact sheet carries, and
how many. Pure + deterministic: no model call, no network, no randomness, no image analysis.

ONE rule for Highlights and Full Story (policy v2, owner decision 2026-11-10). Both types get visual
evidence for the opening, the closing, every AU event and every visual candidate; the editorial type only
changes PRIORITY when the frame budget cannot hold everything. The planner's editorial instructions — not
this module — decide how the evidence becomes a Highlights or Full Story video.

The Swift port (apps/ios/Story/Story/Media/AssetUnderstanding/EvidenceFrameMapper.swift) implements the
same algorithm; `fixtures/parity_v2.json` pins identical outputs for both. The written spec is
docs/architecture/editorial-pipeline-v2/evidence-frame-selection-v2.md. Change all three together.

TRUST MODEL (unchanged): AU intervals and peak_time are ADVISORY (IMG_9091: the true reveal at ~16.6s sat
4s after the labelled peak). A target is represented by a frame from the CENTRAL part of its interval,
never only by the peak; sampled timestamps are provenance, not semantic proof; the model `evidence`
string is never consulted.

ALGORITHM — rank_frames() returns an ORDERED priority list of sampled-frame indices (prefix-stable: the
selection for k frames is always the first k, so a degraded payload tier never re-shuffles evidence):
  1. opening (first frame), closing (last frame).
  2. CORE coverage, in type priority order. Highlights: visual candidates, then events. Full Story:
     events, then narrative candidates, then visual candidates. A target is COVERED when a chosen frame
     lies in its zone (the central half of its interval; short or point intervals get a +/- spacing
     window). An uncovered target gets the zone frame nearest the zone centre, preferring one at least
     MIN_GAP from every chosen frame (no near-duplicate timestamps while distinct evidence is uncovered).
  3. PRIMARY context, one per candidate. Highlights: each visual candidate's advisory peak (payoff).
     Full Story: one progression frame inside each narrative candidate / event, at the zone point
     farthest from chosen frames. Skipped when it would land within MIN_GAP (resp. 2*MIN_GAP) of a
     chosen frame.
  4. SECONDARY (not counted in the adaptive budget). Highlights: narrative candidate coverage.
     Full Story: visual-candidate peaks.
  5. GAP FILL: the frame nearest the middle of the widest remaining temporal gap, until MAX_FRAMES.
ADAPTIVE BUDGET = clamp(max(duration_floor, |opening+closing+core| + |primary context|), <= MAX_FRAMES,
<= frames available). duration_floor is the previous Tier-1 rule max(4, min(9, round(duration/8))), so a
static or evidence-poor Moment keeps its old frame count and an evidence-rich short Moment gets more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

HIGHLIGHTS = "highlights"
FULL_STORY = "full"

POLICY_VERSION = "evidence_select/2"
MIN_FRAMES = 4      # previous Tier-1 lower bound
MAX_FRAMES = 9      # previous Tier-1 upper bound (and the per-sheet layout limit)

# Kept for backward reference by older callers/tests; policy v2 uses MIN_GAP derived from frame spacing.
CONTEXT_PAD_S = 1.5


@dataclass(frozen=True)
class Candidate:
    """An AU interval (visual candidate, narrative candidate, or event). Times in SECONDS. `end` None or
    <= start means a point. `peak` is advisory and only used as payoff context."""
    start: float
    end: float | None = None
    peak: float | None = None
    confidence: float | None = None


@dataclass
class Ranking:
    ordered: list[int]                  # priority-ordered sampled-frame indices (<= MAX_FRAMES)
    budget: int                         # adaptive frame count for this Moment
    core_count: int                     # opening + closing + core picks
    context_count: int                  # primary context picks
    targets: list[dict] = field(default_factory=list)   # [{kind, start, end}] considered, in order
    uniform: bool = False               # no AU evidence: `ordered` is a time-ordered uniform overview


# ---- helpers (ms integers throughout; the Swift port mirrors these exactly) ------------------------

def _spacing_ms(ms: list[int]) -> int:
    """Typical frame spacing: the median gap between consecutive sampled timestamps (>= 1)."""
    if len(ms) < 2:
        return 1000
    gaps = sorted(b - a for a, b in zip(ms, ms[1:]))
    return max(1, gaps[(len(gaps) - 1) // 2])


def _zone(c: Candidate, spacing: int) -> tuple[int, int]:
    """The part of an interval a representative frame should come from: its central half, or a
    +/- spacing window around a short/point interval. Integer ms, inclusive."""
    a = _round_half_away(c.start * 1000)
    b = _round_half_away(c.end * 1000) if c.end is not None else a
    if b < a:
        b = a
    if b - a < 2 * spacing:
        mid = (a + b) // 2
        half = max(spacing, (b - a) // 2)
        return mid - half, mid + half
    q = (b - a) // 4
    return a + q, b - q


def _nearest(ms: list[int], t: int, allowed: list[int] | None = None) -> int:
    """Index of the sampled frame nearest t (ties -> lower index), optionally restricted to `allowed`."""
    pool = allowed if allowed is not None else range(len(ms))
    best, best_d = -1, None
    for i in pool:
        d = abs(ms[i] - t)
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def _dist_to_chosen(ms: list[int], i: int, chosen: list[int]) -> int:
    return min((abs(ms[i] - ms[j]) for j in chosen), default=10**12)


def _covered(ms: list[int], zone: tuple[int, int], chosen: list[int]) -> bool:
    return any(zone[0] <= ms[j] <= zone[1] for j in chosen)


def _pick_for_zone(ms: list[int], zone: tuple[int, int], chosen: list[int], min_gap: int) -> int:
    """Zone frame nearest the zone centre, preferring frames >= min_gap from every chosen frame. Falls
    back to any zone frame, then to the nearest frame overall. Never returns an already-chosen index
    unless every frame is chosen (caller checks)."""
    centre = (zone[0] + zone[1]) // 2
    inside = [i for i, t in enumerate(ms) if zone[0] <= t <= zone[1] and i not in chosen]
    distinct = [i for i in inside if _dist_to_chosen(ms, i, chosen) >= min_gap]
    if distinct:
        return _nearest(ms, centre, distinct)
    if inside:
        return _nearest(ms, centre, inside)
    free = [i for i in range(len(ms)) if i not in chosen]
    return _nearest(ms, centre, free) if free else -1


def _by_start(cands: list[Candidate]) -> list[Candidate]:
    # Temporal order is the stable axis; confidence only breaks exact-start ties (never the primary sort);
    # the original position breaks any remaining tie so Python and Swift (unstable sort) agree exactly.
    keyed = sorted(enumerate(cands),
                   key=lambda p: (_round_half_away(p[1].start * 1000), -(p[1].confidence or 0.0), p[0]))
    return [c for _, c in keyed]


def duration_floor(duration_s: float) -> int:
    """The previous Tier-1 frame count, kept as the lower bound: max(4, min(9, round(duration/8)))."""
    return max(MIN_FRAMES, min(MAX_FRAMES, int(_round_half_away(duration_s / 8.0))))


def _round_half_away(x: float) -> int:
    # Swift `.rounded()` is half-away-from-zero; Python round() is half-even. Use half-away so both agree.
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def rank_frames(*, video_type: str, sampled_frame_ms: list[int], events: list[Candidate],
                visual_candidates: list[Candidate], narrative_candidates: list[Candidate]) -> Ranking:
    ms = list(sampled_frame_ms)
    n = len(ms)
    if n == 0:
        return Ranking(ordered=[], budget=0, core_count=0, context_count=0)
    spacing = _spacing_ms(ms)
    min_gap = (3 * spacing) // 2                       # near-duplicate distance for core picks
    ctx_gap = max(min_gap, min(2 * min_gap, 1500))     # a context frame must be at least this distinct
    chosen: list[int] = []
    targets: list[dict] = []

    def add(i: int) -> bool:
        if i < 0 or i in chosen or len(chosen) >= MAX_FRAMES:
            return False
        chosen.append(i)
        return True

    vis = _by_start(visual_candidates)
    nar = _by_start(narrative_candidates)
    evs = _by_start(events)

    # No AU evidence at all -> the previous uniform overview, exactly (graceful fallback; nothing invented).
    if not (vis or nar or evs):
        budget = min(duration_floor(ms[-1] / 1000.0), n)
        return Ranking(ordered=list(range(n)), budget=budget, core_count=0, context_count=0, uniform=True)

    if video_type == FULL_STORY:
        core = [("event", c) for c in evs] + [("narrative", c) for c in nar] + [("visual", c) for c in vis]
    else:
        core = [("visual", c) for c in vis] + [("event", c) for c in evs]

    # 2) core coverage
    for kind, c in core:
        z = _zone(c, spacing)
        targets.append({"kind": kind, "start": c.start, "end": c.end if c.end is not None else c.start})
        if not _covered(ms, z, chosen):
            add(_pick_for_zone(ms, z, chosen, min_gap))

    # 1) opening + closing context: a frame in the first / last edge zone already serves; otherwise the
    #    first / last sampled frame is added. (Avoids a forced t=0 frame next to an early event frame.)
    edge = min(2000, max(spacing, (ms[-1] * 15) // 100))
    by_time = sorted(chosen, key=lambda j: (ms[j], j))
    opening = next((j for j in by_time if ms[j] <= edge), 0)
    closing = next((j for j in reversed(by_time) if ms[j] >= ms[-1] - edge), n - 1)
    # Opening and closing lead the priority list so a degraded payload tier keeps whole-Moment context.
    # If the core already used every slot, the last core pick yields to them (never exceeds MAX_FRAMES).
    lead = [opening] + ([closing] if closing != opening else [])
    chosen[:] = (lead + [j for j in chosen if j not in lead])[:MAX_FRAMES]
    core_count = len(chosen)

    # 3) primary context
    def add_context_near(t: int) -> None:
        i = _nearest(ms, t, [j for j in range(n) if j not in chosen])
        if i >= 0 and _dist_to_chosen(ms, i, chosen) >= ctx_gap:
            add(i)

    def peak_context(cands: list[Candidate], aftermath: bool) -> None:
        """Payoff context per candidate: its advisory peak (when grounded in its own window), then — for
        Highlights — an aftermath frame near the end of its zone, because a labelled peak can be early
        (IMG_9091). Each is added only when clearly distinct from frames already chosen."""
        for c in cands:
            a = _round_half_away(c.start * 1000)
            b = _round_half_away(c.end * 1000) if c.end is not None else a
            if c.peak is not None:
                p = _round_half_away(c.peak * 1000)
                if a - spacing <= p <= max(a, b) + spacing:     # an ungrounded peak is ignored
                    add_context_near(p)
            if aftermath and b - a >= 2 * spacing:
                add_context_near(_zone(c, spacing)[1])

    def progression_context(cands: list[Candidate]) -> None:
        for c in cands:
            z = _zone(c, spacing)
            inside = [i for i, t in enumerate(ms) if z[0] <= t <= z[1] and i not in chosen]
            if not inside:
                continue
            best = max(inside, key=lambda i: (_dist_to_chosen(ms, i, chosen), -i))
            if _dist_to_chosen(ms, best, chosen) >= ctx_gap:
                add(best)

    if video_type == FULL_STORY:
        progression_context(nar)      # events already have core coverage; progression is narrative-only
    else:
        peak_context(vis, aftermath=True)
    context_count = len(chosen) - core_count

    # 4) secondary (not counted in the budget)
    if video_type == FULL_STORY:
        peak_context(vis, aftermath=False)
    else:
        for c in nar:
            z = _zone(c, spacing)
            targets.append({"kind": "narrative", "start": c.start, "end": c.end if c.end is not None else c.start})
            if not _covered(ms, z, chosen):
                add(_pick_for_zone(ms, z, chosen, min_gap))

    # 5) gap fill up to MAX_FRAMES (prefix-stable whole-Moment coverage)
    while len(chosen) < min(MAX_FRAMES, n):
        pts = sorted(chosen, key=lambda j: ms[j])
        best_gap, best_mid = -1, 0
        for x, y in zip(pts, pts[1:]):
            g = ms[y] - ms[x]
            if g > best_gap:
                best_gap, best_mid = g, (ms[x] + ms[y]) // 2
        i = _nearest(ms, best_mid, [j for j in range(n) if j not in chosen])
        if not add(i):
            break

    duration_s = ms[-1] / 1000.0
    budget = max(duration_floor(duration_s), core_count + context_count)
    budget = min(budget, MAX_FRAMES, n)
    return Ranking(ordered=chosen, budget=budget, core_count=core_count, context_count=context_count,
                   targets=targets)


def _overview_indices(n_frames: int, k: int) -> list[int]:
    """k evenly spaced indices over [0, n_frames-1], first and last included (the previous uniform rule)."""
    if n_frames <= 0 or k <= 0:
        return []
    if k >= n_frames:
        return list(range(n_frames))
    if k == 1:
        return [0]
    return sorted({int(_round_half_away(i / (k - 1) * (n_frames - 1))) for i in range(k)})


def select_for_budget(ranking: Ranking, k: int) -> list[int]:
    """The k-frame selection in time order: the first k of the priority list, or for a uniform (no-evidence)
    Moment an even subsample of its uniform overview."""
    k = max(0, k)
    if ranking.uniform:
        pos = _overview_indices(len(ranking.ordered), k)
        return sorted(ranking.ordered[p] for p in pos)
    return sorted(ranking.ordered[:k])


def coverage_report(*, sampled_frame_ms: list[int], selected: list[int], events: list[Candidate],
                    visual_candidates: list[Candidate], narrative_candidates: list[Candidate]) -> dict:
    """Diagnostic only: which AU intervals have a selected frame in their zone. Not semantic proof."""
    ms = list(sampled_frame_ms)
    spacing = _spacing_ms(ms)

    def cov(cands: list[Candidate]) -> tuple[int, list[tuple[float, float]]]:
        hit, missed = 0, []
        for c in cands:
            if _covered(ms, _zone(c, spacing), selected):
                hit += 1
            else:
                missed.append((c.start, c.end if c.end is not None else c.start))
        return hit, missed

    out = {}
    for name, cands in (("events", events), ("visual", visual_candidates), ("narrative", narrative_candidates)):
        hit, missed = cov(cands)
        out[name] = {"covered": hit, "total": len(cands), "unrepresented": missed}
    return out


def select_frames(*, video_type: str, sampled_frame_ms: list[int], visual_candidates: list[Candidate],
                  narrative_candidates: list[Candidate], event_times_s: list[float] | None = None,
                  events: list[Candidate] | None = None, budget: int | None = None) -> list[int]:
    """Back-compatible entry point. Returns ascending sampled-frame indices. `events` (intervals) wins over
    `event_times_s` (points). With `budget` None the adaptive budget is used; with an explicit budget the
    first `budget` frames of the same priority list are returned."""
    evs = list(events) if events is not None else [Candidate(start=t) for t in (event_times_s or [])]
    r = rank_frames(video_type=video_type, sampled_frame_ms=sampled_frame_ms, events=evs,
                    visual_candidates=visual_candidates, narrative_candidates=narrative_candidates)
    if not r.ordered:
        return []
    k = r.budget if budget is None else budget
    if k <= 0:
        return []
    if k >= len(sampled_frame_ms):
        return list(range(len(sampled_frame_ms)))
    return select_for_budget(r, k)
