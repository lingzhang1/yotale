# AU Evidence & Visual Distinctness — Information-Flow Audit + A/B/C (girl_with_dress)

Status: **Investigation + bounded experiment complete. STOP at the architecture/freeze gate.**
No production change, no v5.2, no contract change made. Dataset + evidence preserved.

## 1. AU audit (Phase 3) — what the frozen pipeline captures
Frozen `asset_understanding/v1` + `moment_understanding/1` capture, per Moment, ONLY:
`observed.{summary, subjects, events[], temporal_order_note, useful_segments[]}` + a
`story_context` block. All are **free-text / event-level**. There is **NO structured field
for outfit, color, accessory, setting-type, or composition.** The prompt's job is "what
useful material exists," explicitly NOT ranking/coverage. So a distinction like "green dress
vs paisley dress" or "red tote" is captured only **incidentally**, if the model happens to
mention it in `summary`/`subjects` — not systematically.
(I did not run AU on all 36 clips: the information-flow audit below is decisive without it,
and AU is an async on-device queue needing frame extraction. The A/B/C experiment substitutes
the planner-side measurement, which is where the loss bites.)

## 2. Information-loss boundary (Phase 4) — TWO layers, both proven from code
| stage | carries distinctness? |
|---|---|
| 1. Video reality | YES — 2 outfits, red bag, ~10 locations, framing (Phase-2 ground truth) |
| 2. Frozen AU output | PARTIAL — only if it lands in free-text summary/subjects/events (no structured field) |
| 3. Persisted MomentUnderstanding | same as AU (stored as the wire JSON verbatim) |
| 4. **Edit-Plan request** | **summary STRING ONLY** — `understandingSummary()` forwards `observed.summary` and **drops subjects, events, temporal_order_note** |
| 5. Used by planner | the single summary string + duration + useful_segments |

**The loss boundary is stage 3→4 (forwarding), compounded by a thin stage-2 summary.** The
planner never sees `subjects`/`events` even though AU produced them.

## 3. A/B/C results (Phase 5) — live v5.1, 36 real-grounded moments, mode=full, 100s
| arm | evidence to planner | unique | timeline | green-dress | paisley-dress | distinct locations |
|---|---|---|---|---|---|---|
| **A** baseline | thin summary ("a woman walking") | 16 | 103s | 7 | 9 | 16 |
| **B** forward existing | summary + subjects + events + setting (AU already produces these) | **22** | 112s | 12 | 9 | **22** |
| **C** new field | B + a new `visual_distinctness` object | 16 | 96s | 7 | 8 | 16 |

**B is the clear winner** — richer forwarding of already-captured detail lifted distinct-moment
and distinct-location coverage 16→22 and represented both outfits well. **C gave NO benefit**:
the planner has no consumer for an unfamiliar field (it's not in the frozen prompt), so it
ignored it.

## 4. Distinctness vs editorial relevance (Phase 6)
Distinctness alone did not drive selection — the planner used the *described* content, not a
distinctness score. When the description was thin (A), distinct moments collapsed; when the
description carried the real facts (B), the planner naturally spread across outfits/locations.
This confirms distinctness must arrive as **grounded description the planner already knows how
to read**, not as a new labelled axis.

## 5. Selection/omission
Under A, the under-represented green-dress + specific locations were omitted because the planner
couldn't tell them apart from "a woman walking." Under B they were selected. No evidence the
planner *ignores* detail it is given — the problem is it isn't given.

## 6. Cross-domain regression (arm-B rich summaries, mode=full)
- Solitude (3 distinct): **3/3** — not artificially expanded. PASS.
- Redundant (12 near-identical): **12/12** — Full still packs genuine near-duplicates at a short duration. **Residual yellow flag** (unchanged from the mode experiment); a separate, smaller dedup concern, not the main lever, and the owner forbade forced dedup/min-count.
- Guitar / TMB: covered earlier (continuous performance preserved; TMB breadth works with real guide/coverage).

## 7. Architecture recommendation (Phase 8) — smallest evidence-supported change
**FORWARD EXISTING AU FIELDS (arm B). Do NOT add a new field / AU pass / contract.**
- Change: `EditPlanRequestBuilder` forwards a RICHER per-Moment payload built from the AU output already persisted — fold `observed.subjects` and the key `observed.events` descriptions (and any setting detail) into the Moment's forwarded `summary`, instead of only `observed.summary`.
- **Named consumer:** the Edit Planner's existing selection logic (v5/v5.1), which already reads the Moment summary — no prompt change needed; it simply receives more grounded detail.
- Reject **C** (new `visual_distinctness` field): no measured benefit, and it would need a prompt change to have a consumer → violates "every new field needs a named consumer; no unjustified fields."
- Reject a second AU model pass: the information already exists in the first pass.
- Residual: the near-duplicate-under-Full behavior is a separate future dedup question, not part of this minimum fix.

## 8. Contract implications
NONE required. The fix is iOS request-construction only (how much of the already-persisted AU
output is forwarded). `moment_understanding/1`, EditPlan/2, and the frozen prompts are untouched.
This is a strictly additive forwarding change on the client.

## 9. Cost & latency
A/B/C + regressions: a handful of edit-plan calls (~15-22s each), total spend well under the $20
gate (cents). No change to per-render latency.

## 10. Freeze readiness & owner decisions
- v5.1 NOT frozen; no v5.2 created (not needed — the fix is forwarding, not prompting).
- **Owner decision needed:** approve the arm-B forwarding change (iOS `EditPlanRequestBuilder`: forward subjects/events/setting in the Moment summary). It is additive, no contract/prompt change, with a measured 16→22 distinct-coverage improvement on the real dataset.
- Open follow-up (separate): whether to address Full's inclusion of genuine near-duplicates (a dedup heuristic), which the owner has so far scoped out.

## Device acceptance plan (after approval)
Re-import the real girl_with_dress set; render Full at ~100s; verify both the green and paisley
dress days appear, several distinct locations are represented, and no multi-minute wait — vs the
current 9-of-36.

---

## IMPLEMENTATION — Arm B (commit `9ddc6c2`)
`EditPlanRequestBuilder.understandingSummary` now builds a deterministic, bounded factual
description from the ALREADY-PERSISTED AU output: `summary · subjects: … · events: … · note`.
- Only real present fields used (graceful on absent); de-duplicated across summary/subjects/events; 600-char cap so a 36-Moment request stays measurable; original AU output untouched; Moment ids + useful_segments unchanged; no new field/model/prompt/contract.
- Tests (`EditPlannerCaseGTests`): rich evidence reaches the planner (red-tote in subjects + facade in events now forwarded); summary-only records still yield just the summary; bounded ≤601 chars; no fabricated outfit/colour; ids + useful_segments preserved. Backend suite 224 pass.

## PHASE 3 — real frozen-AU richness (decisive honesty check)
Ran the REAL frozen `/v1/asset-understanding` on two actual clips:
- **IMG_2273 (green):** summary + subjects captured "teal/green maxi dress + white lace overshirt", "cathedral/church facade (Seville)", "iron chain barrier", "cobblestone plaza".
- **IMG_2340 (paisley):** captured "white off-shoulder top, floral maxi skirt, **red tote bag**", "Moorish stucco / Arabic calligraphy", "zellige tilework", "colonnaded gallery".

**The real AU already produces the outfit / accessory / location distinctions.** The loss was
purely forwarding (summary-only). This confirms Arm B will deliver on real data and vindicates
rejecting a new AU pass / new field. (Caveat: AU summaries here are already rich, so for these two
clips forwarding subjects/events is incremental; the fix is decisive on clips that put a key fact
in subjects/events but not the summary — e.g. the red tote.)

## Freeze readiness
Arm B is additive and low-risk. v5.1 freeze still gated on the **device render** (Phase 4): confirm
both dress days + distinct settings represented at ~100s, near-duplicates not padded, pacing/native-
audio/duration intact — vs the prior 9-of-36. Recommend freezing v5.1 as the dev default only after
that device confirmation.
