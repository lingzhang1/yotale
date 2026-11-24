# Evidence frame selection — policy v2 (`evidence_select/2`)

Status: implemented on PR #102 (`fix/prebeta-p1f-editorial-alignment`), offline-tested, **not merged, not deployed,
not device-accepted**. Owner decision 2026-11-10.

Reference implementation: `packages/evidence_mapper/__init__.py` (`rank_frames`, `select_for_budget`).
Device port: `apps/ios/Story/Story/Media/AssetUnderstanding/EvidenceFrameMapper.swift`.
Contract: `packages/evidence_mapper/fixtures/parity_v2.json` (regenerate with `make_parity_fixture.py`). The Python
test `test_committed_parity_fixture_matches_the_reference_implementation` fails if the fixture is stale; the Swift
`EvidenceSelectionParityTests` fails if the port disagrees with it. Change the spec, both implementations and the
fixture together.

## Why

Policy v1 (the PR #102 mapper) chose frames by editorial type: Highlights used visual candidates only, Full Story
narrative candidates plus event start times, with a fixed 4-frame budget for short Moments. On the six real Moments
of dev job `0d4e959c` it represented 8/14 AU event intervals and 7/11 visual candidates, and spent slots on
near-identical frames (0.4 s apart). The planner received every AU event as text but often no picture of it.

## Inputs

Sampled frame timestamps (ms, the frames actually extracted / cached), AU `observed.events[]` (`start_time`,
optional `end_time`), `editorial.visual_candidates[]` and `narrative_candidates[]` (interval, advisory `peak_time`,
`confidence`), the attempt's editorial type. No image content is inspected. The model `evidence` string is never used.

## Definitions

* `spacing` = median gap between consecutive sampled timestamps.
* `zone(interval)` = where a representative frame should come from: the central half of the interval; for an
  interval shorter than `2*spacing` (or a point event) a `±max(spacing, len/2)` window around its middle.
* An interval is *covered* when a chosen frame lies in its zone.
* `min_gap = 1.5*spacing` (core near-duplicate distance); `ctx_gap = max(min_gap, min(2*min_gap, 1.5 s))`.
* Integer milliseconds throughout; rounding is half-away-from-zero; every sort has an explicit final tie-break
  (time, then confidence descending, then input position), so Python and Swift agree exactly.

## Algorithm (produces a priority-ordered list of at most 9 frames)

1. **No AU evidence at all** → the previous uniform overview, exactly (`uniform = true`). Nothing is invented.
2. **Core coverage**, in type priority order — Highlights: visual candidates, then events. Full Story: events,
   then narrative candidates, then visual candidates. For each uncovered interval add the zone frame nearest the
   zone centre, preferring frames `>= min_gap` from every chosen frame.
3. **Opening / closing**: a chosen frame within the first / last edge (`min(2 s, max(spacing, 15% of duration))`)
   already serves; otherwise the first / last sampled frame is added. Opening and closing lead the list.
4. **Primary context** — Highlights: for each visual candidate, its advisory peak (only if grounded inside its own
   window) and an aftermath frame at the end of its zone (a labelled peak can be early — IMG_9091). Full Story: one
   progression frame inside each narrative candidate, at the zone point farthest from chosen frames. A context frame
   is added only if `>= ctx_gap` from every chosen frame.
5. **Secondary** (not counted in the budget) — Highlights: narrative-candidate coverage. Full Story: visual peaks.
6. **Gap fill** up to 9: the frame nearest the middle of the widest remaining gap.

Both types therefore get visual evidence for every event and every visual candidate when room allows; the type
only decides what survives when it does not. The planner's editorial instructions decide how the evidence is used.
EditPlan prompts are unchanged.

## Adaptive budget

`budget = min(9, frames available, max(duration_floor, |opening + closing + core| + |primary context|))` with
`duration_floor = max(4, min(9, round(duration / 8)))` — the previous rule, kept as the lower bound. A static or
evidence-poor Moment keeps its old count; an evidence-rich short Moment gets more. The list is **prefix-stable**:
the selection for `k` frames is always the first `k`, so when the payload ladder reduces frames per Moment it drops
the lowest-priority evidence first and never reshuffles.

## Payload

Unchanged ceilings: 900 KB per sheet / 16 MB total on the device (server: 1 MB / 20 MB), counted as raw JPEG plus
512 B multipart framing per sheet. Cached AU frames, local extracted frames and cloud-restored extracted frames are
ranked by the same rule and go through the same `MultimodalVisualBudget` tier ladder; the ladder now scales each
Moment's adaptive count instead of the duration-only Tier-1 count. Frames are ranked once per Moment and only the
(at most 9) frames a sheet can use are held.

## Overflow / honesty

If the budget cannot cover everything, the lowest-priority intervals go unrepresented; `coverage_report` (Python) /
`EvidenceFrameMapper.coverage` (Swift) lists covered vs total per kind, and the device beacon `evidence prep:` reports
`eventsCovered` / `visualCovered` for the submitted sheets. All AU events stay in the EditPlan request as text.
Unmet coverage is never a failure.

## Results on the six real Moments (job `0d4e959c`, saved AU frames)

Zone coverage over all six Moments (diagnostic proxy, not semantic proof):

| Policy | Events | Visual candidates | Narrative | Frames / Moment | Sheet bytes |
|---|---|---|---|---|---|
| A uniform (master) | 5/14 | 3/11 | 6/8 | 4 | ~326 KB |
| B v1 mapper (PR #102 before) | 8/14 | 7/11 | 7/8 | 4 | ~328 KB |
| C v2, Highlights | 14/14 | 11/11 | 8/8 | 4–5 | ~337 KB |
| C v2, Full Story | 14/14 | 11/11 | 8/8 | 4–6 | ~418 KB |

The owner's earlier `start ± 0.8 s` metric scores v2 lower (Highlights 4/14) **by design**: v2 represents an event by
the middle of its interval, not its start, because a start timestamp is often a transition frame. The ±0.8 s metric
rewards exactly the behaviour the owner asked to stop. Visual review: v2 removes the 0.4 s duplicate pair v1
produced and gives each event its own frame; slow pans still yield some similar-looking frames ~1.5 s apart (no image
similarity is computed in this milestone).

## Known limitations

* Time-based only: near-duplicates in slow or static footage are reduced by spacing, not detected visually.
* Coverage is a time-zone proxy; it does not prove the chosen frame shows what the AU text describes.
* `peak_time` remains advisory; a peak outside its own candidate window is ignored.
