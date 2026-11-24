"""Regenerate `parity_v2.json` — the shared Swift/Python contract for evidence frame selection v2.

    python3 packages/evidence_mapper/fixtures/make_parity_fixture.py

The Python test suite fails if the committed fixture no longer matches this module's output, and the Swift
StoryTests suite (EvidenceSelectionParityTests) fails if the Swift port disagrees with the fixture. Change the
algorithm, the spec and this fixture together.

Cases are synthetic, plus six "real_*" timelines taken from a real six-Moment dev Story as anonymized numbers
only (frame timestamps and AU interval times; no ids, no text, no images).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import evidence_mapper as mp  # noqa: E402


def sampled(n: int = 24, dur_s: float = 10.0) -> list[int]:
    step = dur_s * 1000 / (n - 1)
    return [mp._round_half_away(i * step) for i in range(n)]


def iv(start, end, peak=None, conf=None):
    return {"start": start, "end": end, "peak": peak, "confidence": conf}


CASES = [
    {"name": "img9091_misplaced_peak", "sampled_frame_ms": sampled(24, 35.3),
     "events": [], "visual": [iv(12, 18, 12.5, 0.86)], "narrative": []},
    {"name": "no_events", "sampled_frame_ms": sampled(24, 20.0),
     "events": [], "visual": [iv(5, 9, 8.0, 0.8)], "narrative": [iv(0, 20)]},
    {"name": "no_visual_candidates", "sampled_frame_ms": sampled(24, 15.0),
     "events": [iv(0, 5), iv(5, 10), iv(10, 15)], "visual": [], "narrative": [iv(0, 15)]},
    {"name": "many_events_few_frames", "sampled_frame_ms": sampled(24, 6.0),
     "events": [iv(i * 0.75, (i + 1) * 0.75) for i in range(8)],
     "visual": [iv(0.5, 2.0, 1.2), iv(3.5, 5.5, 5.0)], "narrative": []},
    {"name": "overlapping_events_and_candidates", "sampled_frame_ms": sampled(24, 12.0),
     "events": [iv(2, 6), iv(4, 9)], "visual": [iv(3, 7, 5.0), iv(5, 8, 7.0)], "narrative": [iv(1, 10)]},
    {"name": "long_static_no_evidence", "sampled_frame_ms": sampled(24, 60.0),
     "events": [], "visual": [], "narrative": []},
    {"name": "fast_human_movement", "sampled_frame_ms": sampled(24, 5.0),
     "events": [iv(i, i + 1) for i in range(5)], "visual": [iv(1, 4, 3.0, 0.9)], "narrative": [iv(0, 5)]},
    {"name": "scenic_reveal", "sampled_frame_ms": sampled(24, 14.0),
     "events": [iv(0, 6), iv(6, 14)], "visual": [iv(8, 14, 12.5, 0.9)], "narrative": [iv(0, 14)]},
    {"name": "conversation_interaction", "sampled_frame_ms": sampled(24, 25.0),
     "events": [iv(0, 8), iv(8, 16), iv(16, 25)], "visual": [iv(9, 12, 10.0, 0.7)],
     "narrative": [iv(0, 25), iv(8, 16)]},
    {"name": "point_events_without_end", "sampled_frame_ms": sampled(24, 30.0),
     "events": [iv(4.0, None), iv(13.0, None), iv(22.5, None)], "visual": [], "narrative": []},
    {"name": "ungrounded_peak_outside_window", "sampled_frame_ms": sampled(24, 20.0),
     "events": [], "visual": [iv(4, 8, 17.0, 0.9)], "narrative": []},
    {"name": "tied_starts_confidence_order", "sampled_frame_ms": sampled(24, 18.0),
     "events": [], "visual": [iv(6, 9, None, 0.4), iv(6, 12, None, 0.9)], "narrative": []},
]

_REAL = os.path.join(HERE, "real_timelines.json")
if os.path.exists(_REAL):
    for i, (_, v) in enumerate(sorted(json.load(open(_REAL)).items()), start=1):
        CASES.append({"name": f"real_{i}", "sampled_frame_ms": v["sampled_frame_ms"], "events": v["events"],
                      "visual": v["visual"], "narrative": v["narrative"]})


def cands(lst):
    return [mp.Candidate(start=c["start"], end=c.get("end"), peak=c.get("peak"), confidence=c.get("confidence"))
            for c in lst]


def run_case(case: dict, video_type: str) -> dict:
    ms = case["sampled_frame_ms"]
    ev, vi, na = cands(case["events"]), cands(case["visual"]), cands(case["narrative"])
    r = mp.rank_frames(video_type=video_type, sampled_frame_ms=ms, events=ev, visual_candidates=vi,
                       narrative_candidates=na)
    sel = {str(k): mp.select_for_budget(r, k) for k in sorted({3, r.budget, mp.MAX_FRAMES})}
    cov = mp.coverage_report(sampled_frame_ms=ms, selected=mp.select_for_budget(r, r.budget), events=ev,
                             visual_candidates=vi, narrative_candidates=na)
    return {"ordered": r.ordered, "budget": r.budget, "core_count": r.core_count,
            "context_count": r.context_count, "uniform": r.uniform, "select": sel,
            "coverage": {k: [cov[k]["covered"], cov[k]["total"]] for k in ("events", "visual", "narrative")}}


def build() -> dict:
    return {"policy_version": mp.POLICY_VERSION, "max_frames": mp.MAX_FRAMES, "min_frames": mp.MIN_FRAMES,
            "cases": [dict(case, expected={"highlights": run_case(case, mp.HIGHLIGHTS),
                                           "full_story": run_case(case, mp.FULL_STORY)}) for case in CASES]}


if __name__ == "__main__":
    out = os.path.join(HERE, "parity_v2.json")
    with open(out, "w") as f:
        json.dump(build(), f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {out} ({len(CASES)} cases)")
