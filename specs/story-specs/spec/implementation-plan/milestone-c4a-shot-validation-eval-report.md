# Milestone C4A — Shot Validation: corpus + harness + offline model evaluation (REPORT)

> **Gate: C4A complete. STOPPED for approval before C4B.** Nothing proceeds to the
> backend without sign-off. All numbers below are from LIVE Bedrock runs on account
> 989088054552, us-east-1, this session (2026-10-04). No production contract changed;
> no raw/derived media committed.

## 1. Fixture count & category coverage
- **68 committed fixtures** (request.json + expectations.json each), referencing the
  gitignored corpus by path via `evals/shot_validation/media-map.json`. `IMG_8712.MOV`
  excluded (unclassified). Retakes (`_2`) are distinct fixtures; S05/S06 prefix
  collisions split into distinct IDs with **no raw-file renames**; shared-source pairs
  (A01↔A06, A05↔S02_G) reference one physical file each (media not duplicated).
- Ground-truth distribution (expected): **user_state** 41 got_it / 19 keep_plus_one_more
  / 8 try_again. **shot_purpose** 21 fulfilled / 27 unfulfilled / 10 partial /
  10 alternative_fulfilled. Tag coverage: 22 temporal, 16 technical, 10 alternative_success,
  6 adversarial, 5 contradiction, 2 wrong_subject, 1 focus, 1 long_clip. All 10 categories.
- Derivation self-consistency: 68/68 (expectations' derived fields match `derive()`).
- Deterministic-derivation unit tests: **12 passing**, incl. the full 192-case axis
  cross-product and every approved worked example + contradiction/alternative split.

## 2. Model candidates & access record (9-A)
Discovered via `list-inference-profiles` + verified with a live Converse probe:

| Tier | Requested | Profile used | Access |
|---|---|---|---|
| 1 fast | nova-lite | `amazon.nova-lite-v1:0` | ON_DEMAND ✓ |
| 2 mid | nova-pro | `amazon.nova-pro-v1:0` | ON_DEMAND ✓ |
| 3 Sonnet 4.6 | Claude Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` | INFERENCE_PROFILE ✓ invocable |
| 4 Opus ceiling | strongest invocable Opus | `us.anthropic.claude-opus-4-6-v1` | INFERENCE_PROFILE ✓ invocable |

**Access limitation recorded:** the newer Opus profiles in the catalog —
`claude-opus-5-5`, `claude-opus-5`, `claude-opus-4-8`, `claude-opus-4-7` — are all
**AccessDeniedException ("not available")** for this account despite ACTIVE status.
`amazon.nova-2-lite-v1:0` is **not** on-demand (needs a profile). Per instruction, the
strongest *currently invocable* Opus (`opus-4-6-v1`) was used, not omitted.

## 3. Transport & method
8 fixed, ordered, evenly-spaced, timestamped frames across the full clip (long clips —
S07_A 95s, S08_D 154s — sample a centered 20s window). Device-side AVFoundation decode
(ffmpeg/pyav unavailable in sandbox) → long-edge ≤1024 JPEG q0.7 (~60–120KB/frame).
Identical frames/prompt/schema/derivation across all four models. `ShotValidationJudgment`
(4 axes only) via Converse tool-use; derived fields computed deterministically.

## 4. Stage 1 — four-tier comparison (68 fixtures, 8 frames, LIVE)

| Metric | nova-lite | nova-pro | **sonnet-4-6** | **opus-4-6** |
|---|---|---|---|---|
| four-axis exact acc | 0.235 | 0.235 | 0.191 | 0.152 |
| user_state acc (derived) | 0.603 | 0.603 | **0.691** | 0.682 |
| shot_purpose acc | 0.324 | 0.309 | 0.338 | **0.379** |
| technical_usability acc | 0.779 | 0.779 | 0.779 | 0.621 |
| execution_match acc | 0.559 | 0.559 | 0.426 | 0.485 |
| story_utility acc | 0.441 | 0.412 | **0.574** | 0.500 |
| **false-FULFILLMENT** | 0.529 | 0.544 | **0.221** | **0.212** |
| false-TRY-AGAIN | 0.015 | 0.000 | 0.000 | 0.015 |
| alt-success recognition | 0.0 | 0.0 | 0.2 | 0.0 |
| contradiction detection | 0.0 | 0.0 | **0.4** | 0.333 |
| adversarial catch-rate | 0.0 | 0.0 | 0.167 | 0.2 |
| temporal accuracy | 0.545 | 0.545 | **0.682** | 0.65 |
| technical-failure acc | 0.125 | 0.125 | 0.375 | **0.438** |
| p50 / p95 end-to-end (s) | **1.65 / 1.87** | 1.63 / 2.26 | 5.15 / 9.04 | 5.06 / 6.20 |
| approx cost (68 calls) | **$0.03** | $0.44 | $1.95 | $9.39 |
| parse errors | 0 | 0 | 0 | 2 |

(Model latency ≈ end-to-end here; the only non-model work is a local frame read, sub-ms.
Cost uses illustrative public per-token rates — reconcile with the account's actual
pricing before any threshold is set.)

## 5. Confusion & collapse analysis (the decisive view)
Aggregate accuracy is misleading because the eval demands exact 4-axis matches against
subtle human ground truth. The **collapse errors** the brief flagged are the real verdict:

**Nova lite & pro — semantic rubber stamp (disqualifying).**
- `execution_match`: collapse **contradicted → matched** (lite 5/5, pro 3/5) and everything
  else → matched. `absent → matched` 9/10.
- `shot_purpose`: **alternative_fulfilled → fulfilled 10/10**, `partial → fulfilled` 10/10,
  `unfulfilled → fulfilled` ~26/27. Essentially every clip is called "fulfilled."
- Consequence: **false-fulfillment ≈ 0.53**, contradiction/adversarial/alt-success all **0.0**.
  More frames cannot fix a model that semantically says "yes" to everything.

**Sonnet 4.6 — best discriminator at this setting.**
- Does NOT collapse contradiction to matched (0/5 contradicted→matched; splits
  contradicted→deviated 3, →contradicted 2). Only **1** contradiction leaked to a
  *fulfilled requested-shot*. Best temporal (0.68), best story_utility (0.57), lowest
  false-fulfillment (0.22). Still imperfect: `alternative_fulfilled→fulfilled` 6/10, and
  it over-uses `deviated` on genuinely matched clips.

**Opus 4.6 — strong but not a clear win here, and expensive/slow.**
- Best shot_purpose (0.38) and technical (0.44); contradiction detection 0.33; but
  `alternative_fulfilled→fulfilled` 7/10 (worse than Sonnet), lower technical_usability
  (0.62 — it was stricter and flagged usable clips), 2 parse errors, **~5× the cost** and
  comparable latency. The prior Director finding (Opus > Sonnet, and faster) **did NOT
  reproduce** for Shot Validation on this corpus: here Sonnet 4.6 ≥ Opus 4.6 on the
  distinctions that matter, at ⅕ the cost.

## 6. Stage 2 — frame-count sweep (temporal subset, n=22; finalists Sonnet 4.6 & Opus 4.6)

| model | frames | temporal | contradiction | alt-success | p50 / p95 (s) | cost |
|---|---|---|---|---|---|---|
| **sonnet-4-6** | **4** | **0.773** | **0.6** | 0.2 | 4.18 / 5.01 | $0.42 |
| sonnet-4-6 | 8 | 0.636 | 0.4 | 0.2 | 4.89 / 6.12 | $0.63 |
| sonnet-4-6 | 12 | 0.636 | 0.4 | 0.2 | 5.56 / 6.41 | $0.84 |
| opus-4-6 | 4 | 0.65 | 0.333 | 0.2 | 4.17 / 5.21 | $2.00 |
| opus-4-6 | 8 | 0.65 | 0.333 | 0.0 | 5.21 / 46.0* | $3.04 |
| opus-4-6 | 12 | **0.684** | **0.5** | 0.2 | 5.87 / 7.84 | $4.06 |

\* one 46s p95 outlier = a single slow Converse response, not representative.

**Counter-intuitive, important finding:** more frames did **not** monotonically help.
**Sonnet 4.6 was BEST at 4 frames** (temporal 0.77, contradiction 0.6) and *degraded* at
8/12 — extra stills appear to dilute the temporal signal rather than sharpen it. Opus
improved slightly at 12 but never beat Sonnet@4. This directly answers the Stage-2
question: additional temporal evidence did **not** let a model approach a higher ceiling;
if anything, fewer, well-spaced frames read the temporal story more cleanly.

## 7. Latency vs the <3s target
**No Claude configuration met the ~3s end-to-end target** (Sonnet/Opus p50 ≈ 5s). Only the
Nova tier was <3s (p50 ~1.6s) — but Nova is semantically disqualified. So there is a real
**quality↔latency tension**: the only models that can make the distinctions are ~5s, and
the only sub-3s models can't make them. This is the central open problem for C4B/C.

## 8. Technical-heuristic (deterministic Stage-1) results
The smoke + corpus confirm the approved caution: duration is the robust win. In the live
runs, models (even Opus) frequently **missed gross technical failures** (technical-failure
accuracy 0.13 Nova / 0.38 Sonnet / 0.44 Opus) — e.g. the 0.47s too-short clips were called
"usable/fulfilled" because 8 sampled frames hide duration. **Deterministic duration check
is clearly justified** (clip < shot.target×0.7 → unusable) and would have fixed the
too-short misses outright. Out-of-focus / motion heuristics are NOT yet justified — defer
to the model + earn empirically (per approval); no CV subsystem.

## 9. Selected model & frame policy (RECOMMENDATION — needs approval)
- **Production frontier: `us.anthropic.claude-sonnet-4-6` at 4 frames.** It is the best
  discriminator on every distinction that matters (contradiction 0.6, temporal 0.77, lowest
  false-fulfillment), at ⅕ Opus cost, and 4 frames was its best setting. Opus 4.6 is a
  legitimate *quality reference* but did not beat Sonnet here and costs 5× — not the frontier.
- **Nova tier rejected** for the semantic judgment (rubber-stamp collapse), though it is a
  candidate for the **deterministic/cheap pre-filter** role only.
- **Frame policy: 4 ordered frames** as the baseline (not 8) — the sweep says fewer, evenly
  spaced frames read temporal meaning better and are cheaper/faster. Fixed, not adaptive.

## 10. Recommended quality gates (proposed AFTER baseline, per instruction)
Observed, not preset. Proposed C4B acceptance bar on this corpus:
- **false-FULFILLMENT ≤ 0.15** (Sonnet@8 was 0.22; must improve via prompt + the duration gate).
- **contradiction NEVER leaks to a fulfilled requested-shot** (hard gate; Sonnet leaked 1 — fix).
- **false-TRY-AGAIN ≤ 0.05** (met).
- **temporal ≥ 0.75** (Sonnet@4 met at 0.77).
- **p95 end-to-end**: Claude will miss 3s; propose provisional **≤ 6s** with an async "we're
  checking…" UX, OR a Nova-deterministic fast path for the easy/technical cases (recorded as
  an opportunity, NOT built — see §12).

## 11. Failures / regressions discovered
1. All models over-trust framing: gross technical failures (too-short, severe exposure)
   slip through without the deterministic duration gate.
2. `alternative_fulfilled` is the hardest axis for every model (collapses to `fulfilled`),
   so the prompt needs sharper few-shot contrast on deviated-but-successful vs matched.
3. Opus 4.6 produced 2 structured-output parse errors (nested `{judgment:{…}}` envelope) —
   handled by tolerant unwrap in the runner; worth a schema/prompt tightening in C4B.
4. The prior Director "Opus > Sonnet and faster" result did NOT generalize to Shot Validation.

## 12. Recorded opportunity (NOT built in C4A, per instruction)
A **two-speed single-stage-plus-cascade** is attractive: deterministic duration/exposure
pre-filter + Nova for obvious technical rejects, Sonnet 4.6@4 for the semantic judgment,
Opus only as an offline quality reference. **No routing/cascading built now** — first
establish the single-model frontier (Sonnet 4.6@4). Recorded for a later milestone.

## Artifacts (committed unless noted)
- `packages/shot_validation/` — judgment model + derivation + tests.
- `evals/shot_validation/media-map.json`, `evals/shot_validation/scenarios/**` — 68 fixtures.
- `evals/shot_validation/tools/sample_frames.swift` — ordered-frame sampler.
- `prompts/shot_validation/v1/system.md` — versioned prompt.
- `evals/run_shot_validation.py`, `evals/author_shot_validation_fixtures.py` — runner + author.
- Raw run JSONs under `evals/results/` (gitignored, local): the Stage-1 and Stage-2 results.

## STOP — awaiting approval
Recommended for C4B: **Sonnet 4.6 @ 4 frames + deterministic duration gate**, with the §10
gates. Do you approve this frontier (and the gates), or want Opus kept as the C4B model
despite cost/latency, before I build `POST /v1/shot-validation`?
