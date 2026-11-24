# Milestone V2-b.1 — Creative Edit Planner v5.2 Candidate & Device Quality Gate

Status: **CANDIDATE promoted; freeze NOT recommended on backend metrics alone — awaiting a real on-device render.**
Owner approved the creative-freedom DIRECTION; the production/dev default remains `edit_plan/5.1`.

## 1. Candidate commit
- `1598949` — `feat(edit-plan): promote 5.2-exp -> edit_plan/5.2 versioned candidate (V2-b.1)` (app repo, NOT pushed).
- `prompts/edit_plan/5.2/system.md` is byte-identical in body to `5.2-exp`; header rewritten to mark it the
  owner-approved versioned candidate (default stays 5.1 until the device gate passes).
- v5 and v5.1 preserved verbatim on disk.

## 2. Prompt diff (vs v5.1 — the ONLY creative change)
One clause rebalanced: the SIGNIFICANCE-WEIGHTED SCREEN TIME paragraph.
- v5.1 tail (removed): "Prefer fewer well-chosen Moments held long enough to read over many equally short clips
  when the Story benefits…" (a default long-hold bias).
- v5.2 (added): "CREATIVE FREEDOM OVER PACING: … there is NO default bias toward long holds OR toward many
  short cuts. … favor BREADTH when footage is distinct and the intent is variety/journey; give continuous time
  when the footage centers on one performance/payoff … never pad with near-duplicate shots to inflate variety."
Verified unchanged: EDITORIAL MODE, DURATION DISCIPLINE, NATIVE-AUDIO policy, MUSIC ALIGNMENT, HARD RULES, all
EXECUTABILITY INVARIANTS. No fixed editing-style template, no minimum clip count, no unrelated edits.

## 3. Backend deployment verification
- Full regression suite: PASS (apps/api + packages, 100%).
- `editorial_mode` reaches the planner (`packages/edit_planner/__init__.py:374-379` payload + directive;
  `apps/api/app/main.py:694` forwards `body.editorial_mode`). Rich-AU moments
  (`id/duration_seconds/useful_segments` + summaries) forwarded.
- Deployed to dev App Runner (acct 989088054552, us-east-1) via CodeBuild `story-rb-caseg-build` ->
  ECR `story-development-api:latest`. **Stale-digest trap recurred**: first run logged a silent fallback to
  `edit_plan/5` (the 5.2 dir was absent from the still-served old digest); a fresh `start-deployment` fixed it.
  LIVE-VERIFIED (dot-tolerant grep) `prompt_version=edit_plan/5.2` for the v5.2 arm, `edit_plan/5.1` for the
  comparison arm. Env preserved `STORY_EPIDEMIC_MODE=prototyping` + `STORY_MUSIC_PROVIDER=mcp` throughout.
- Dev default RESTORED to `STORY_EDIT_PLAN_VERSION=5.1` after the gate (not frozen).

## 4. Device/backend comparison — real Girl-with-Dress dataset (36 clips grounded)
NOTE: a true device render needs on-device AU (not reproducible in sandbox). This is a live-planner comparison
on grounded, outfit/location-tagged summaries — faithful at the planner level, which is where v5.2 differs.

| Metric | v5.1 | v5.2 |
|---|---|---|
| 100s Full — moments | 21/36 | 22/36 |
| 100s Full — median shot | 6.0s | 5.0s |
| 100s Full — shot range | 2.1–7.0s | 2.1–7.0s |
| 100s Full — outfit coverage | A/B/C all | A/B/C all |
| 100s Full — location coverage | 10/9 | 10/9 |
| 60s Full — moments | 15/36 | **18/36** |
| 60s Full — median shot | 4.5s | **3.0s** |
| duplicate/invalid refs | 0 | 0 |
| feasible | true | true |

Decisive signal is NOT the 100s count (21 vs 22 is negligible on grounded data — v5.1 differentiates well when
summaries are rich). It is the **60s cut**: v5.2 fits 18 vs 15 distinct moments at a 3.0s vs 4.5s median — a
faster, broader montage when the budget is tight, i.e. the creative-freedom-over-pacing behavior, without
inflating with near-dups (reuse=0).

### Human-reference pacing (owner's 65.4s edit)
Frame-by-frame: ~10-11 distinct SCENES in 65s (~6s per location), with faster sub-cuts inside scenes — a busy,
energetic edit. v5.2@100s (5.0s median) is MORE patient than the human edit; v5.2@60s (3.0s median) is closer to
its energy. Per the owner's caution, 22 clips in 100s is NOT automatically equivalent to the human reference —
the human edit is faster/busier than either v5.2 setting at 100s and sits between them.

## 5. Cross-domain checks (Phase 4, on live v5.2)
- Guitar (45s): 6/6, longest continuous hold **20s** (final performance intact), native_audio keep 6/6. ✅
- Solitude (30s): 3/3, calm 8-12s holds, median 10s, native keep. ✅ (not fragmented)
- Hiking (100s, from the A/B): 20 -> 24 distinct, balanced across both treks. ✅
- No invalid/missing moment references in any arm. Native audio preserved (keep-by-default) everywhere.

## 6. Quality improvements
- Tighter, broader pacing available when the footage is distinct and the budget is tight (60s: +3 moments,
  faster median) — the editor now CHOOSES pacing instead of defaulting to long holds.
- 100s breadth parity-to-slightly-better with no loss of outfit/location coverage.
- Performance continuity and calm pacing demonstrably preserved (Guitar/Solitude unchanged).

## 7. Regressions
- None observed at the planner level: no invariant breakage, no invalid refs, no native-audio regression,
  no over-inclusion of near-dups on this dataset (reuse=0).
- UNRESOLVED (pre-existing, out of scope): genuine near-duplicate footage over-inclusion (redundant control
  fixture) is NOT fixed by v5.2 and is not in this milestone's scope.

## 8. Freeze recommendation
**DO NOT FREEZE on backend metrics alone.** The direction is sound and all seven gate criteria pass at the
planner level EXCEPT criterion 1 ("real device output demonstrates a meaningful editorial improvement"), which
requires an actual on-device render that this sandbox cannot produce. The 100s improvement is marginal on
grounded data (21->22); the real win shows at 60s. **Recommended: freeze v5.2 as the dev default ONLY after a
physical-device render of the real Girl-with-Dress Story at BOTH ~100s and ~60s confirms the pacing reads well
on screen and beats v5.1 by eye** — mirroring the v5 freeze process (owner confirmed v5 by listening on device).
If the device render is mixed, STOP and report rather than stacking another amendment.

## 9. Next: user-directives implementation scope (NOT started — owner gate)
When approved, build the `user_directives` + validator layer on top of v5.2:
- a `user_directives` input (natural-language editing asks: "more of the green dress", "slower", "keep the
  twirl", "shorter") threaded into the planner payload like `editorial_mode`;
- a server-side validator that still enforces every EXECUTABILITY INVARIANT and rejects invalid/invented refs;
- "Create Another Version" UX re-planning with the directive, versioned via the existing lineage.
NOT to be implemented in this milestone.
