# EditPlan v5.4 prompt experiment — evaluation (P1-F editorial alignment)

> **Owner decision (2026-11-10): retain v5.3, do NOT promote v5.4.** This report is kept for reference only. The
> v5.4 prompt (`prompts/edit_plan/5.4/`) and its version-selection logic (`_v54_active`) are NOT on master;
> they exist only in commit `457dc65` on branch `fix/prebeta-p1f-editorial-alignment`. The offline replay
> harness used for this evaluation (`StoryTests/RuntimeEvidenceReplayTests.swift`, skipped unless
> `P1F_REPLAY_DIR` is set) is preserved because it is prompt-independent. Follow-ups from §7 are tracked in
> [milestone-duration-reliability-and-provenance](./milestone-duration-reliability-and-provenance.md) (duration + provenance) and [proposal-chronology-metadata](./proposal-chronology-metadata.md).

**Status: EXPERIMENT, NOT ADOPTED.** v5.3 remains the deployed version; the v5.4 code is not merged (see the note above).

Test case: Story "TMB Hiking" (25 Moments, target 50 s, Highlights, visual_first), the owner's device runs of
2026-11-10 (jobs `1408674a` and `7b59d7e1`).

## 1. Runtime evidence verified (before any prompt change)

| Check | Finding |
|---|---|
| iOS commit | Not recorded: `build_provenance.commit_sha = "unknown"` (the build does not stamp a SHA). The tested build contained the Auto Backup fix (owner-verified behavior), i.e. ≥ `5c6b87d` on `fix/prebeta-p1f-editorial-alignment`. |
| Dev API / worker | API image `git-7a53910` (P1-F id-case + lookup log); worker `STORY_EDIT_PLAN_VERSION=5.3`, `gpt-5.1` direct, creative-freedom flags on. |
| Prompt version | 5.3 on API and worker (env + CDK synth). |
| `planning_mode` / `sheet_count` | `multimodal` / 25 (both jobs); evidence funnel reconciles 25/25; 0 cut-without-sheet. |
| Moment ids submitted | Persisted `sheet_order` (25 ids, createdAt order). Exact per-sheet timestamps and request body are NOT retained: staging is deleted at job terminal (privacy design). |
| Mapper actually used | `build_provenance.frame_policy` is the AU *extraction* policy (`au_frames/1`), not the selection policy; `evidence_select/2` is only in the device beacon. Verified indirectly: the real Swift cache-hit path (`VisualEvidencePreparation` → `MultimodalVisualBudget` → sheet builder) replayed on the 25 cached packs gives **2,966,598 B** (v2 Highlights, 121 frames) vs runtime **2,901,143 B** (+2.3%, simulator vs device JPEG encoder). Alternatives: v2 Full Story 3,333,156 B (+14.9%); pre-v2 frame counts 2,511,084 B (−13.4%). → v2 Highlights selection ran. |
| Missing evidence | None: 25/25 cache hits, 73/73 events and 40/40 visual candidates represented, narrative 29/30. |
| Editorial type | Not logged server-side; Story `editorial_mode = highlights`, both runs Explore ("another version") ⇒ Highlights. No Full Story run exists for this set. |
| `7b59d7e1` directives | `opening/ending/must_include/order_after` were present: a Customize-directed Explore (owner directives), so its three red-jacket shots (#15, #23, #4) were directed, not planner redundancy. |

Gaps worth closing (not done here): stamp the git SHA into `build_provenance`, and report the selection policy
version (`evidence_select/2`) alongside `frame_policy`.

## 2. Method

Inputs were reconstructed from durable dev data (synced Story doc: intent, Guide, Coverage, MusicPlan, outputs;
AU JSON per Moment; the track's `music_analysis`) by a port of the iOS `EditPlanRequestBuilder` /
`RevisionContextBuilder`, and sheets from the Swift replay above. Fidelity: v5.3 Explore replay uses 54,298
input tokens vs runtime 53,894 (+0.7%). Each arm ran the worker's execution core (`RealEditPlannerEngine`,
2 executability repairs, gpt-5.1, same flags); only `STORY_EDIT_PLAN_VERSION` differed. 30 calls
(Original Highlights 4+4, Original Full Story 4+4, Explore Highlights 4+4, Explore→Full Story 3+3), all
first-pass executable, no fallback. Tooling: `StoryTests/RuntimeEvidenceReplayTests.swift` (skipped unless
`P1F_REPLAY_DIR` is set); the request/run/score scripts and personal frames stayed in session scratch.

## 3. Baseline v5.3 assessment

- **Highlights (runtime 1408674a, 10 shots, 57.6 s = +15%)**: distinct visual variety (stream, forest, smile
  payoff #2 14.5–21.2, valley, boulder celebration, orbit shot, one red-jacket V, glacier, church, street);
  every segment overlaps an AU visual candidate and contains its peak; #25 used 0.0–4.2 only (the rotation
  starts ≈4.2–4.5 s) — correct. No cross-Moment duplicate pose. Opening/ending framed as "trek start /
  return to town", which is not the real chronology (see §6).
- **Replays (v5.3)**: no red-jacket duplication in 15 runs (#15/#23, captured one minute apart, never paired);
  the same-ridge yellow-pack pair (#5+#6, 7 min apart) appears in 6/15 runs; 4–5 landscape pans per edit is
  common; Highlights often take #2's misty pan (0–6.5) and #1's walk-away (19.6–26.6) rather than their
  payoffs (smile 14.5–21.2, arms-wide 9–16.2). Full Story re-cuts the same Moment 1.75×/run on average.
- **Duration** is the largest observed problem: duration is advisory (owner decision 2026-10-25), and v5.3
  replays overshoot the 50 s target by +29% (Explore Highlights) to +58% (Explore→Full Story).

## 4. v5.4 change (user message only; version-scoped)

`packages/edit_planner`: `_v54_active()`; VISUAL EVIDENCE block replaced only when 5.4 is selected (sparse
samples near opening/closing, AU events and candidates; timestamps are evidence anchors, not cut boundaries;
no unsupported motion/audio inference; explicit cross-Moment distinctness; cautious text/visual conflict
handling) — removes the "precise source ranges" claim. One per-type sentence: Highlights uses events with
visual candidates to find action build + payoff (not every event); Full Story builds progression from
evidence and must not read chronology from input order. `prompts/edit_plan/5.4/system.md` = 5.3 body verbatim.
Under 5.3 the user message is byte-identical to before (tested).

## 5. A/B results (mean over runs)

| Variant | Ver | Shots | Distinct | Total s (vs 50) | Re-cut same Moment | #5+#6 pair | Peak in segment | In useful | Latency s | Out tok |
|---|---|---|---|---|---|---|---|---|---|---|
| Original Highlights | 5.3 | 12.0 | 11.0 | 70.9 (+42%) | 1.0 | 1/4 | 0.96 | 0.90 | 19.1 | 1240 |
| | 5.4 | 11.0 | 10.0 | 67.0 (+34%) | 1.0 | 1/4 | 0.84 | 0.88 | 16.5 | 1101 |
| Original Full Story | 5.3 | 11.3 | 9.5 | 73.5 (+47%) | 1.75 | 2/4 | 0.94 | 0.72 | 17.8 | 1179 |
| | 5.4 | 10.0 | 9.75 | 62.7 (+25%) | 0.25 | 0/4 | 0.75 | 0.72 | 15.0 | 1037 |
| Explore Highlights (owner case) | 5.3 | 11.3 | 11.3 | 64.6 (+29%) | 0 | 1/4 | 0.86 | 0.93 | 20.3 | 1116 |
| | 5.4 | 11.5 | 11.5 | 68.4 (+37%) | 0 | 2/4 | 0.85 | 0.87 | 15.9 | 1179 |
| Explore → Full Story | 5.3 | 10.7 | 10.3 | 78.8 (+58%) | 0.33 | 2/3 | 0.84 | 0.72 | 19.2 | 1128 |
| | 5.4 | 9.3 | 9.3 | 67.0 (+34%) | 0 | 1/3 | 0.86 | 0.60 | 23.9* | 975 |

\* one 37 s outlier; others 17.3–17.5 s. Input tokens +292–309 per call (+0.55%) for v5.4. All plans valid,
first-pass executable, 0 repairs. #25's rotated stretch: never selected by either version.

Side-by-side review (frame strips per segment): both versions build the same skeleton (town → forest → stream →
pans → boulder celebration → ridge portraits → glacier trail). Both pick the weaker #11 chalet shot (car roof in
foreground) in 3/4 Explore Highlights runs, and v5.4 does not reduce scenic-pan repetition. v5.4 Full
Story is tighter and avoids re-cutting the same Moment. No invented events were found in either version's
segment roles; one v5.3 role called a 07:14 local shot "evening".

## 6. Distinctness and source-range findings

- Redundancy is real but moderate under v5.3 and not reduced by v5.4: scenic pans (#2, #12, #13, #18, #19, #21)
  and the #5/#6 same-ridge pair recur; strict pose duplicates (#15/#23) are already avoided.
- Source ranges align with AU event boundaries in both versions (≥93% of segments overlap a visual candidate).
  v5.4 did not increase use of candidate peaks (Highlights 0.96 → 0.84) despite the payoff sentence.
- Chronology is not grounded in either version: the planner receives no capture time (`captured_at` exists on
  the device but is not in `moments[]`); input order is import order (Kendall τ vs capture order −0.13). Both
  versions frame edits as "town → trek → return to town" although the town shots are mid-trip (day 5–6). The
  v5.4 Full Story sentence cannot fix missing evidence (τ vs capture 0.18 → 0.15).

## 7. Recommendation

**Retain v5.3.** v5.4 does not meet the adoption criteria: no consistent visual-selection gain (Explore
Highlights — the owner's case — is not better: longer, slightly more same-ridge pairing, lower useful-range
compliance); payoff use did not improve; the Full Story gains (less re-cutting, smaller overshoot) come with
lower peak and useful-range use and are from 3–4 runs. Latency/cost impact is negligible either way.

The prompt-adjacent problems the evidence does show are outside v5.4's scope and need owner decisions:
1. Duration overshoot (+29…58%) now that duration is advisory — a duration-discipline experiment, or a soft
   validator band.
2. Ungrounded chronology — send a capture-order signal (e.g. `captured_at` or day index) in `moments[]`
   (request-contract change, iOS + backend).
3. Provenance — stamp commit SHA and selection-policy version in `build_provenance`.

No deployment or configuration change is required (v5.3 remains deployed). Adopting v5.4 later would need only
`-c editPlanVersion=5.4` (or the CDK default) for the API + worker, with owner approval.
