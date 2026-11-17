# Editorial vNext M1 — first matched evaluation (EditPlan 5.3 vs 5.5, development) — results

**Status: RESULTS RECORDED 2026-11-16. Inconclusive; NOT a promotion decision.** Four live planner jobs on **development** (the only environment that ran 5.5): no beta call, no
beta deploy, no further regeneration. Companion to [milestone-editorial-vnext-m1-editplan-v55](./milestone-editorial-vnext-m1-editplan-v55.md) (design, §I dev-only pin) and the
[Phase A report](./milestone-editorial-vnext-phase-a-report.md). Numbers come from the job records (`diagnostics`, `plan`), the dev AU table, the dev Story docs and the dev
worker logs, through `scripts/editorial_eval.py compare`. Moment references are the first 8 characters of an opaque id; no media or prompts are stored here.

## 1. Setup

| Run | Planner | Type | Operation | Job | Created (UTC) |
|---|---|---|---|---|---|
| A | `edit_plan/5.3` | Highlights, Custom 90 s | Original | `4e2a32c1` | 2026-11-16 05:52 |
| B | `edit_plan/5.5` | Highlights, Custom 90 s | Original | `eb7f0c67` | 2026-11-16 07:57 |
| C | `edit_plan/5.3` | Full Story, Custom 155 s | Original | `5285af1c` | 2026-11-16 06:03 |
| D | `edit_plan/5.5` | Full Story, Custom 155 s | Original | `d4807732` | 2026-11-16 07:51 |

- Highlights pair on Story `8b029b4f`, Full Story pair on Story `00453d86`; each pair on the same Story, 38 Moments, same Moment/sheet order, same music asset, Balanced sound, no
  Creative Direction, no directives. All four: `critique_requested=false`, one planned call, `evidence_accounting` 38/38 sheeted, `multimodal`.
- Builds: A/C on API+worker `0b365ec27901` (5.3 default); B/D on `929a0603e63a` (5.5 pinned on development via PR #125). B/D second Originals were made possible by the
  DEBUG-only "Delete this version" action (PR #124, branch `feat/debug-delete-version`, device-built by the owner).
- The released app brief was the client one for all four (`selection.brief=client` for A/C; `type_aware` for B/D, i.e. the 5.5 server brief replaced it as designed).

## 2. Matching status — NOT matched

| Check | Highlights A/B | Full Story C/D |
|---|---|---|
| Same Story, Moments, Moment/sheet order, music asset, target, type, sound, build provenance | yes | yes |
| Contact-sheet payload bytes (`selection.sheets.bytes`) | 4,507,823 = 4,507,823 | 4,922,277 = 4,922,277 |
| AU content | unchanged (485 records; only `revision` counters moved) | unchanged |
| `payload_fingerprint` | **differs** (`6d088c81e2` vs `38fbb3cbcc`) | **differs** (`84c65b1545` vs `198050876b`) |

The harness correctly reports `NOT MATCHED`. The images are identical, so the request body text differs. **Likely cause (inference):** Coverage is recomputed after each finished video
(Story Coverage `generated_at` 06:00:22Z and 06:05:10Z, i.e. after A and C), so B/D carried newer Coverage than A/C. The staged requests are deleted at job end, so this cannot be proven.
Consequently differences below may come from the prompt, the Coverage text, or ordinary model variation; there is one run per cell, so no variance estimate. **Do not claim a prompt-only effect.**

## 3. Highlights — A (5.3) vs B (5.5), target 90 s

| Metric | A | B |
|---|---|---|
| Model-planned length before the fitter | 140.6 s (+56%) | 124.0 s (+38%) |
| Delivered after fitter / exported | 97.8 s (+8.7%) / — | 91.8 s (+2.0%) / 91.9 s |
| Shots / distinct Moments | 24 / 22 | 23 / 22 |
| Mean / median / p25–p75 shot | 4.08 / 3.12 / 2.5–5.15 s | 3.99 / 2.93 / 2.2–4.97 s |
| Fitter changes / drops | 15 / 2 | 16 / 1 |
| AU payoff windows overlapped by a used range | 6 of 22 | 11 of 22 |
| AU narrative candidates overlapped | 27 of 52 | 29 of 52 |
| Opening shot (AU role at that range) | 12.0 s walking shot (`opening`) | 3.0 s high-angle pan (`opening`); not a payoff |
| Closing shot | boulder arms-raised clip (payoff) | red-jacket arms-outstretched clip `0bc5f375`, 2.5 s |
| Moments from the 5-clip red-jacket check set used | 0 genuine (1 town-street clip) | 2 genuine (`0bc5f375`, `c8b27de6`) + 2 others |
| Native audio keep / duck | 12 / 12 | 11 / 12 |
| Model calls (planner / repair) | 1 / 0 | 2 / 1 (first plan named a mistyped Moment id) |
| Worker duration | 26.1 s | 51.4 s (2 calls) |
| Completion | complete | complete |

Reading: duration discipline and payoff-window coverage improved; pacing is essentially unchanged; the payoff-first hook is **not** visible in the opening; the long-UUID repair failure recurred (the
M4 Moment-ID alias would remove it). The red-jacket "check set" was found by loose AU text search (it includes one town-street clip and one misty pan) and is not an appeal measure.

## 4. Full Story — C (5.3) vs D (5.5), target 155 s

| Metric | C | D |
|---|---|---|
| Model-planned length before the fitter | 207.3 s (+34%) | 218.3 s (+41%) |
| Delivered after fitter / exported | 181.6 s (+17%) / — | 197.5 s (+27%) / 197.6 s |
| Shots / distinct Moments | 32 / 27 | 29 / 26 |
| Mean / median / p25–p75 shot | 5.67 / 5.35 / 3.6–8.25 s | 6.81 / 5.15 / 4.1–8.43 s |
| Shots ≥ 8 s / longest shot | 8 / 10.5 s | 8 / **30.3 s** (one continuous hike, `4e9cc7f4` 1.7–32.0 s) |
| AU payoff windows overlapped | 13 of 22 | 12 of 22 |
| AU narrative candidates overlapped | 36 of 52 | 32 of 52 |
| Opening | 8.2 s walking shot (`opening`) | 11.0 s backpacks and poles (`establishing`); the same clip also closes the video |
| Native audio keep / duck | 13 / 19 | 15 / 14 |
| Model calls (planner / repair) | 1 / 0 | 1 / 0 |
| Worker duration | 116.0 s | 36.1 s |
| Completion | partial (disclosed) | partial (disclosed) |

Reading: D is **worse on length** (+27% delivered, the fitter cannot trim a protected 30 s action) and covers fewer narrative candidates; it keeps grounded openings and the same breadth of footage.
Latency differences (116 s vs 36 s for one call each) are model variance, not a prompt effect.

## 5. Type differentiation on this Story

| | 5.3: Highlights A / Full C | 5.5: Highlights B / Full D |
|---|---|---|
| Median shot | 3.12 / 5.35 s | 2.93 / 5.15 s |
| Mean shot | 4.08 / 5.67 s | 3.99 / 6.81 s |
| Shots ≥ 8 s | 3 / 8 | 4 / 8 |

Highlights is already briskly paced and Full Story longer on **5.3** for this Story and target (the near-identical 5.37 / 5.38 s means seen in the beta jobs are not reproduced here: different Story, 38 Moments,
different targets). The Phase A pacing-convergence claim is therefore not supported by this Story, and the B-vs-D gap cannot be credited to 5.5.

## 6. Diagnostics check

`diagnostics.selection` (deterministic) was present on all four jobs (A/C recorded it as `brief: client`; B/D as `type_aware`) and matched the harness numbers (shots, distinct, overshoot, opening, sheets,
fit). It reported `unused_payoff` lists (8 for B, 6 for D) as descriptions of the output, not of the model's reasons.

## 7. Conclusions and open items

1. The evidence is mixed and unmatched: Highlights moved the right way on duration discipline and payoff coverage; Full Story regressed on length; the hook policy did not visibly change the Highlights opening; one repair call recurred.
   **No basis to promote 5.5, and none to reject it either.** The owner's review of the four rendered videos is still the deciding evidence (opening appeal, strongest-clip selection and pacing for Highlights;
   thread, completeness and the 30 s hold for Full Story).
2. A cleaner test needs the same request body: either suppress the post-render Coverage recompute for the evaluation Story, or snapshot Coverage/Guide/MusicPlan before the baseline and restore them before the candidate.
   Not done; no further live calls without approval (owner limit: four planned generations).
3. Likely next code work, independent of this result: Moment-ID aliases (M4) to remove the repair-call typos; type-aware sizing (M2); chronology (M3).
4. **Operational state:** development still runs 5.5 on API and worker (`planner.environment_overrides.development`, approval expires 2026-11-30; beta unaffected). Every dev create uses 5.5 until reverted;
   after 2026-11-30 the gate rejects the expired approval and CI goes red until the pin is removed.

## 8. Not verified

Rendered quality (not judged by this document); the effect of Coverage on the plans; per-call token attribution (B's 147k input tokens include a repair call, so token totals are not comparable across A/B);
beta behaviour (no 5.5 run on beta); any statistical significance (one run per cell).
