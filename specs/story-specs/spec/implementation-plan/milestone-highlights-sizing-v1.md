# Highlights sizing v1 (`highlights_sizing/1`): rule-based, no model call

**Status:** implemented on `feat/sizing-v2` (draft PR). Offline tests green. **Not merged or deployed.** iOS change is parse-checked and its extraction logic was run in isolation, but it is **not Xcode-built or XCTest-run**.

## Problem
The Create screen showed "about 80 s" for Highlights on the 38-Moment TMB Story. Cause (verified in code): `compute_duration_evidence` hands the model a feasible-band floor of `2 s x Moment count` (76 s), and the frozen `duration_recommendation/1` call anchored its Highlights range on it (observed 80-100 s). Highlights length therefore followed how many clips were imported, not how many attractive opportunities exist. At the v5.6 pace (1-2.5 s shots) 80 s means 30-80 shots, the montage the product is trying to avoid.

## Change
Only the **Highlights range** is replaced. The frozen prompt, `compute_duration_evidence` (including the 2 s x N floor, which still feeds the model for Full Story), the endpoint contract and Custom duration are unchanged.

`packages/duration_planner/highlights.py`:
- opportunities = distinct AU `payoff` windows (merged per Moment, at most 2 per Moment, windows under 0.5 s ignored)
- raw seconds = opportunities x 2.2 s (typical shot) x 0.7 (share of windows a selective cut uses)
- point = raw rounded to 5 s, clamped to [15 s, 60 s], then capped by the useful-footage ceiling
- range = point +- 15% (the Create screen shows the midpoint, which stays equal to the point)
- No visual evidence in the request (older client or AU without editorial candidates): footage-only estimate of 0.5 opportunities per Moment with at least 1.5 s of useful footage, flagged `uncertain`. It never reintroduces a per-Moment floor.
- Response gains an additive `recommendation.sizing.highlights` block (source, version, opportunities, uncertain, and the model's original Highlights range for diagnosis). The existing keys are untouched, so older apps still decode it.
- Failure mode unchanged: if the model call fails the endpoint still returns `recommendation: null` and the app falls back to manual duration.

iOS (`RenderSupport.swift`, `DurationService.swift`): `momentsPayload` adds `payoff_windows: [[s,e],...]` per Moment from `editorial.visual_candidates` with role `payoff` (omitted, not `[]`, when the AU has no editorial candidates). The recommendation cache key now includes `highlights_sizing/1` and the new field, so a stored 80 s recommendation is not reused.

## Results on the owner's real dev Stories (AU read from DynamoDB; plan-independent)
| Story | Moments | Useful s | Payoff windows | Old floor given to model | New Highlights range | Source |
|---|---|---|---|---|---|---|
| TMB Hiking (the 38-Moment Story) | 38 | 537 | 22 | 76 | **30-40 s** | payoff windows |
| TMB Hiking (39) | 39 | 546 | 23 | 78 | 30-40 s | payoff windows |
| TMB Hiking (25) | 25 | 270 | 13 | 50 | 17-23 s | payoff windows |
| Girl with Dress | 21 | 324 | 13 | 42 | 17-23 s | payoff windows |
| Iceland | 68 | 1392 | 29 | 136 | 38-52 s | payoff windows |
| Mission Peak | 9 | 70 | 2 | 18 | 13-17 s | payoff windows |
| TMB (14, older AU) | 14 | 312 | 0 evidence | 28 | 13-17 s | footage only (uncertain) |
For the TMB Story the result (35 s) matches the owner-tested Custom 35 s, whose B2/B3/B4 plans used 18-20 shots at about 1.9 s. This is arithmetic on counts, not a quality claim: an AU `payoff` tag says where the analysis saw an action, not how appealing it is (the earlier opening review found a tiny distant figure tagged `payoff`).

## What is not changed
Full Story sizing (still one model call, still anchored by the old floor), the frozen `duration_recommendation/1` prompt, the shared evidence function, Custom durations (always authoritative), the edit planner and the fitter. Because one model call still serves both cards, **the call is not removed yet**; it is only no longer used for Highlights. Removing it needs a rule-based or cheaper Full Story sizing (owner decision).

## Tests
Backend `apps/api/tests/test_highlights_sizing.py` (14 tests): the real-story cases above, length follows payoffs not Moment count, clamps and material cap, per-clip cap and overlap merging, both wire shapes, footage-only fallback, midpoint equals point, only the Highlights range is replaced, never raises, endpoint keeps one model call and the DTO keys, model-failure fallback and Custom precedence. iOS `StoryTests/HighlightsSizingPayoffWindowsTests.swift` (5 tests, **written but not run**).

## Risks / owner decisions
1. Constants (2.2 s, 0.7, 15 s, 60 s, +-15%) are tuned on three Stories; adjust after device review.
2. Until the app update ships, an older client sends no `payoff_windows` and gets the footage-only estimate (flagged uncertain).
3. The app must be built in Xcode and the five XCTests run before relying on the client half.
4. Full Story sizing remains model-based; a rule-based Full Story version is a separate decision.
5. Deploying backend only (without the app) is safe: it degrades to the footage-only estimate.
