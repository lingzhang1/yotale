# Milestone R-d.1 — Editorial Timing Quality (edit_plan/4) + Duration Intelligence

Status: **edit_plan/4 FROZEN + DEPLOYED to dev**, at physical-iPhone gate. Duration Intelligence =
**design + bounded experiment DONE, awaiting owner go for implementation**. Follows R-d (Music Integration).

Repos: app `/Users/lingzhang/Workplace/story` (GitHub lingzhang1/story, branch `master`, commit `fc065c9`,
**not pushed**); specs this repo. Dev backend: App Runner `story-development-api`, acct 989088054552
us-east-1, https://ydmju5wdps.us-east-1.awsapprunner.com.

Primary evaluation dataset: **real** `evals/scenarios/guitar_practice_001/` — six source videos
(`string_first_touch` 7.4s, `guitar_overview` 5.1s, `first_practicing_a_song` 29.7s,
`first_song_but_not_familar` 41.2s, `familar_with_song` 18.1s, `final_song` 39.3s). Filenames preserved
verbatim (incl. the existing `familar` spelling). Experiment artifacts (gitignored, on disk under
`evals/results/`): `au_guitar_practice_001_audit.json`, `edit_planner_editorial_timing_ab.json`,
`edit_planner_editorial_timing_ab_v2.json`, `duration_intelligence_evidence.json`,
`duration_intelligence_semantic.json`. Owner-approved editorial reference (committed):
`evals/scenarios/guitar_practice_001/editorial_reference.APPROVED.json`.

---

## 1. Problem

Owner flagged an editorial-quality failure: in a Guitar Practice Story, the final full-performance Moment
received ~2s, like routine practice footage. The Edit Planner concatenated roughly-equal-length clips and
did not weight screen time by narrative significance.

## 2. Diagnosis (Phases A–F, evidence-grounded)

- **Source ground truth (AVFoundation probe).** `final_song` is a 39.3s continuous performance — the payoff
  genuinely exists in the source; not truncated at the file level. ~141s usable across 6 Moments.
- **Frozen AU audit** (Sonnet 4.6, 24 frames `au_frames/1`, `au_prompt/1`, $0.31). AU recognizes `final_song`
  as ONE continuous 39.3s useful span ("complete sustained performance take … usable as a full continuous
  performance"). **NOT fragmented, NOT truncated, semantic recognition PASS.** One minor quirk: AU tags the
  finale `story_utility=useful_elsewhere` while practice clips get `strong_elsewhere` — per owner this is NOT
  an AU defect and NOT an absolute cross-Moment ranking; narrative significance is the Edit Planner's job.
- **Production MomentUnderstanding from device: NOT accessible** (on-device SwiftData, no export) — reported;
  fresh AU used.
- **Root-cause attribution (owner's 5 categories):** A source-limitation ❌, B AU-recognition ❌,
  C AU-fragmentation ❌, **D significance-weighting ✅ (primary)**, **E duration-budget ✅ (co-cause)**.

## 3. The amendment — edit_plan/4 (FROZEN, owner-approved)

`prompts/edit_plan/4/system.md` = `edit_plan/3` body **verbatim** + exactly ONE added paragraph inside
YOUR JOB: **"SIGNIFICANCE-WEIGHTED SCREEN TIME"** — allocate time by narrative significance (payoff holds
longer; routine footage brief or dropped), fewer well-chosen Moments over many equal short clips, keep
native audio when it is the point. Explicitly: NO quotas, NO fixed per-segment duration, NO forced arc,
CreativeIntent authoritative, and DURATION DISCIPLINE + EXECUTABILITY INVARIANTS still bind.

Preserved for reproducibility: `edit_plan/2` (pre-R-c) and `edit_plan/3` (R-c executability) unchanged on
disk. **EditPlan/2 schema, model (`us.anthropic.claude-opus-4-6-v1`), `DURATION_TOLERANCE=0.20`, and the
bounded executability repair are UNCHANGED.** Engine wiring: `packages/edit_planner/__init__.py`
`PROMPT_VERSION="edit_plan/4"`, `_PROMPT_PATH → prompts/edit_plan/4/system.md`.

## 4. Bounded A/B (baseline edit_plan/3 vs amended edit_plan/4)

Real engine + validator + 1 repair, Opus temp 0, identical inputs. Real guitar fixture (Phase B AU
useful_segments) at 3 targets + cross-domain regression (TMB / sf / solitude / energetic). Authoritative
full-fidelity re-run (`..._ab_v2.json`):

| Scenario | Baseline v3 | Amended v4 | Note |
|---|---|---|---|
| guitar 12s teaser | payoff 7.0s/49% | 7.8s/57% | v4 picks a mid-performance highlight excerpt |
| guitar 60s full | 24–27s/36–45% | **39.3s/59% one continuous span**, first-pass valid 67.1s | the fix |
| guitar 72s long | 25.5s/36% | 30–34s/40–47% | both in-tol |
| TMB / sf / solitude / energetic | all exec, in-tol | all exec, in-tol; solitude identical+all-native | no forced arcs, native preserved |

Bounded repair demonstrated: v3@60s raw 79.0s invalid → 1 repair → 59.7s (0.5% err), payoff preserved.

**Measurement-error note (do not conflate):** an earlier harness reported guitar v4@60s as "72.2s,
tol=False, executable=True" — self-contradictory. Root cause was a **save-fidelity bug**: the first harness
saved segments WITHOUT their `transition` objects, so a separate raw-sum `in_tol` check over-counted
(crossfades shorten the timeline via overlap). Re-running `validate_plan` on the exact transition-stripped
saved plan DOES fail (`total output 72.2s is >20% off target`); the original FULL-transition live plan was
accepted. The corrected full-fidelity harness (`..._ab_v2.json`) shows v4@60s first-pass valid at 67.1s.

## 5. Freeze gate + deploy

Owner-approved freeze. 222 backend tests pass (incl. 28 edit_planner). Deployed via CodeBuild
`story-rb-caseg-build` (env `ACCOUNT`/`REPO_NAME`/`AWS_REGION`) → ECR `:latest` (pushed 21:19 PT 2026-10-09)
→ App Runner `start-deployment` SUCCEEDED. Live-verified: `/health` 200; `/v1/edit-plan` returns valid plans;
bounded repair fired live (`edit_plan_generated model_calls=2 repaired=true`). Epidemic export OFF
(`STORY_EPIDEMIC_MODE=prototyping`) preserved. **Nothing pushed to GitHub.**

## 6. Device finding → Duration Intelligence

Owner's device render came back 15.0s with a short finale. **Root cause: not a planner failure** — the
Story target defaults to **15s** (`MusicSelectionResolver.swift:47` `story.intentTargetDurationSeconds ?? 15.0`)
and there is NO duration-selection UI. At a 15s target the full-song payoff cannot fit; v4 correctly gives
it the largest proportional slice (~50%). This is exactly the duration-budget conflict (category E) + the
deferred duration-UX gap. The 39.3s continuous finale requires a ~60s target the app never sets.

### Duration Intelligence — design + bounded experiment (DONE, awaiting owner go)

- **Responsibility:** a minimal UPSTREAM Story Duration Planning recommender (inputs CreativeIntent /
  StoryGuide / StoryCoverage / MomentUnderstanding / useful segments / user preference → recommended target
  + rationale + alternatives). It does NOT choose cuts/order; the Edit Planner keeps target as an
  authoritative input (v4 unchanged). Grounded fact: `target_duration_seconds` is a universal INPUT today;
  nothing PRODUCES it (originates only from CreativeIntent). StoryGuide/StoryCoverage are already
  scope-sensitive, so the recommender reuses existing inputs — no new infra.
- **Deterministic evidence layer** (zero model cost; merges useful-segment intervals w/o double-counting,
  longest continuous span, feasible band): guitar useful=137.2s longest_cont=39.3s band[12,137]; TMB
  useful=30.7s (its authored 60s target EXCEEDS material!); sf 25.5s; solitude 13.5s; energetic 7.5s.
- **Deterministic (A) vs semantic (B)** recommendation experiment ($0.16): A≈B on minimal cases
  (solitude/energetic near-identical) — deterministic suffices; A vs B diverge on the narrative-payoff case
  (guitar Complete A 33.7–47.6s vs B 55–75s, B recognizing "the 39s span is the payoff the whole arc builds
  toward"). **Conclusion: HYBRID** — deterministic evidence/feasibility always (local, free) + one small
  semantic call for the scope-aware recommendation point.
- **Modes:** Highlights / Complete Story / Custom — NO universal seconds. Recommend only when evidence
  supports it; user accepts or overrides; never silently change explicit CreativeIntent; reuse existing
  duration-recovery UX. Proposed `duration_recommendation/1` is computed-at-create (not a persisted
  Blueprint); EditPlan/2 unchanged.
- **Status:** design + experiment complete, **STOP for owner review**; no production duration selection
  implemented. The live `?? 15.0` default is the bug this design fixes.

## 7. Cost

Editorial Timing experiment ≈ $5.6 (AU audit $0.31 + A/B runs ~$4.2 + corrected re-run $1.4). Duration
Intelligence ≈ $0.16. Total this milestone ≈ **$5.8 of the $20 gate.**

## 8. Open items / next

- **At physical-iPhone gate for edit_plan/4** (owner runs guitar Story: continuous payoff screen time, native
  guitar audio, same-clip transition seamless, within tolerance, coherent progression, music supports, no
  fabricated footage, MP4 save/reopen; + light TMB regression). To see the long finale on device the Story
  must use a ~60s target.
- **Duration Intelligence implementation** awaits owner go (sequence: deterministic helper → small semantic
  call → three-mode Create UX replacing the `?? 15.0` default → device acceptance).
- Watch on device: the finale may be two same-clip segments joined by crossfade/fade — a seam there would be
  a Media Engine concat matter, not a planner issue.
- Creative Editing V2 (natural-language re-cut) = deferred next milestone, NOT started.
- Nothing pushed; do not auto-push.
