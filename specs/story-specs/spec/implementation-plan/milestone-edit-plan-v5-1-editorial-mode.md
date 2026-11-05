# Edit Planner v5.1 — Editorial-Mode-Aware Selection (experiment)

Status: **Implemented + deployed to dev (env `STORY_EDIT_PLAN_VERSION=5.1`); A/B done.
STOP for owner freeze review.** v5 untouched; EditPlan/2 unchanged; not the production default.

## 1. Request-field change (Phase 1, additive, back-compat)
`editorial_mode: highlights | full | custom | null` added to:
- backend `EditPlanRequest` + `EditPlanInputs` (threaded into the prompt payload + a one-line directive);
- iOS `EditPlanRequestDTO` (snake_case `editorial_mode`, omitted when nil — older clients unaffected);
- `StoryModel.editorialMode` (persisted from the Customize screen's length choice);
- `CustomizeYourStoryView.onCreate` now carries the chosen `LengthChoice` → persisted → sent.
Null/absent ⇒ unchanged v5 behavior. No EditPlan/2 output-schema change.

## 2. Prompt delta (Phase 2)
`prompts/edit_plan/5.1/system.md` = `edit_plan/5` **verbatim** + exactly one addition: an
**EDITORIAL MODE** clause in the YOUR-JOB section. Highlights = strongest/concise; Full =
broader distinct meaningful representation *where footage AND duration support it* (no padding,
no near-duplicates, breadth earned by meaning); Custom = infer breadth from intent+material.
All modes keep: essential continuous actions preserved, no minimum clip count, no forced Guide
completion, native-audio policy from v5, target duration authoritative. Nothing else changed.

## 3. A/B methodology (Phase 3)
Live dev backend on v5.1. Identical Moments / CreativeIntent / Guide / Coverage; mode varied at
the SAME target duration to isolate mode from duration. Model: Sonnet 4.6 (gateway default/
fallback). Spend: a handful of calls, well under the $20 gate. **Synthetic fixtures** (device
footage was lost earlier in testing) — see limitations.

## 4. Per-fixture results (unique Moments selected)
| fixture | target | highlights | full | baseline(no mode) |
|---|---|---|---|---|
| TMB (24 moments) | 105s | 13 | 15 | 14 |
| **TMB (24 moments)** | **45s** | **7** | **13** | — |
| solitude (3 moments) | 30s | 3 | 3 | — |
| redundant (12 near-dupes) | 30s | 7 | 12 | — |
| guitar (6, continuous perf) | 45s | 6 | 6 | — |

All feasible/executable.

## 5. Meaningful-coverage assessment
- **Mode has a clear, appropriate effect beyond duration.** The cleanest isolation is TMB @ 45s: Highlights uses **7** moments held longer (concision); Full uses **13** distinct moments (breadth) at the same 45s. At the looser 105s the gap is smaller (13 vs 15) because the duration already affords breadth.
- **Minimal Story NOT artificially expanded:** solitude = 3/3 in both modes (nothing to broaden — correct).
- **Continuous performance preserved:** guitar = 6/6 both modes; the performance is not fragmented.

## 6. Clip-count & timeline stats
Timelines land near target (45-109s for the respective targets); no duration regression; no
truncation escalations observed; latency ~15-26s per plan (unchanged from v5).

## 7. Regression findings — one yellow flag
**Redundant fixture: Full selected all 12 near-duplicate clips (vs Highlights 7).** The v5.1
clause says to avoid redundant clips, but with **synthetic identical summaries** the model cannot
tell the clips apart, so "broaden" degenerated to "include all." This is the owner's exact failure
mode ("a Full Story padded with redundant clips is wrong") — but it is a **fixture artifact**:
real footage carries distinct useful_segments/summaries the model can discriminate. It CANNOT be
cleared on synthetic data; it needs a real-footage (device) check.

## 8. Latency & cost
~15-26s/plan (same as v5); total experiment spend a few cents, far under the $20 gate.

## 9. Freeze recommendation — MIXED-POSITIVE, do NOT freeze yet
Freeze criteria status:
- Full broader where supported — **PASS** (TMB 45s: 7→13).
- Highlights selective/impactful — **PASS**.
- Minimal not expanded — **PASS** (3/3).
- Guitar/meaningful audio protected — **PASS** (6/6; native-audio clause unchanged).
- No executability/duration regression — **PASS**.
- Observable mode effect beyond duration — **PASS**.
- Redundancy avoided — **UNPROVEN on synthetic data** (Full took all 12 near-dupes).

Recommendation: **do not flip the production default to v5.1 on synthetic evidence alone.** v5.1
is deployed on dev and clearly differentiates the modes; the one open risk (redundancy under
Full) must be checked on **real device footage** before a freeze. Keep v5 as the default; keep
v5.1 env-reachable for the device test.

## 10. Device acceptance plan (Phase 8-equivalent)
Re-import real TMB + guitar footage on device (dev backend already on v5.1), then:
- Full Story represents visibly more distinct parts than Highlights at a comparable duration.
- Highlights stays tight; **no redundant near-duplicate clips** (the key open check).
- Continuous conversation/performance preserved; native audio intact; plan executable; duration accurate.
- No forced inclusion of every moment or Guide dimension.

## Remaining risks
- Synthetic A/B ≠ device proof; redundancy-under-Full is unverified on real footage.
- "Breadth" is a model-mediated bias, not a guarantee.
- Deploy gotcha observed: `update-service` can race the ECR push and serve a stale `:latest` — always force a fresh `start-deployment` and verify via `/openapi.json` + `prompt_version` in logs.
