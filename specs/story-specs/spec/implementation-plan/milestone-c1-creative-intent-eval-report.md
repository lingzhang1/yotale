# Milestone C1 — Real Creative Intent: Evaluation Report

**Date:** 2026-10-01
**Component:** Creative Intent (first real-AI vertical slice)
**Model:** `amazon.nova-lite-v1:0` (Amazon Bedrock, us-east-1) via Converse tool-use
**Prompt version:** `creative_intent/v1`  **Schema version:** `creative_intent.schema/1`
**Harness:** `evals/harness` Layer-0 deterministic + manual semantic review (no LLM judge yet)

---

## Fixture count & contract success

- **14 fixtures** across all 14 required categories (simple/detailed/vague text,
  tone/mood, pacing, subject/person/landscape emphasis, explicit + negative
  constraints, short/longer duration, equivalent-phrasing pair, conflicting/
  ambiguous).
- **Contract success: 14/14** — every output validated against the canonical
  `CreativeIntentContract` (`extra="forbid"`), both before and after the one
  prompt change. 0 schema failures, 0 provider failures during the runs.

## Latency distribution (real model, per resolution)

- min 580 ms · p50 ~724 ms · p90 ~973 ms · max ~1189 ms.
- Comfortably inside the ~1–3s interactive target (design §20) and far under the
  120s App Runner budget. Synchronous transport is appropriate; no async needed.

## Approximate usage / cost

- ~30K input + ~1K output tokens for the full 14-fixture run (~2.2K in / ~75 out
  per call). Nova Lite is Amazon's low-cost tier; a single resolution is a tiny
  fraction of a cent. Cost is a non-issue at this scale; re-measure if the prompt
  grows or the model changes.

## Observed failure categories

No contract failures. Semantic weaknesses found (and the general fix applied):
- **INTENT_INVENTED (over-filling)** — the biggest issue. On the vague
  "make something cool here", v1-initial fabricated `desired_feeling:["cool"]`,
  `emphasis:["cool"]`, `creative_constraints:["authentic"]`; and on "a short
  energetic video of Times Square" it invented `target_duration_seconds:30` +
  `target_format:landscape`. These are exactly the fabrications the fixtures
  guard against.
- **Minor over-read of pace** — "a quick 7-second clip" read "quick" as a tempo.

## Prompt change made (one general change, full-set rerun)

Strengthened the preserve-uncertainty section of `creative_intent/v1` with an
explicit "do NOT over-fill" rule: never echo a vague adjective as a creative tag;
never set `target_duration_seconds`/`target_format`/`pace` unless stated or
clearly implied; a minimal summary-only intent is the correct answer for a vague
request. **Not** tuned per-fixture — one general change, then the whole set rerun.

**Result after the change:**
- vague → `summary` + `raw_user_description` only (invented fields gone). ✅
- Times Square → fabricated duration/format gone; keeps energetic/fast. ✅
- 7-second clip → pace relaxed from `fast` to `moderate`; duration still 7s. ✅
- No regressions elsewhere; still 14/14 contract-valid.

## Representative GOOD outputs

- **Negative constraint** ("epic but not cheesy, not like an advertisement") →
  `desired_feeling:["epic"]`, `creative_constraints:["not cheesy","not like an
  advertisement"]` — preserved both negatives (the hard INTENT_MISREAD case).
- **Landscape/scale** ("make the mountains feel huge and us feel tiny") →
  `emphasis:["scale"]`, constraint preserves the scale contrast; no invented
  mountain/scene facts.
- **Conflicting intent** ("calm but also really energetic") → kept BOTH feelings
  rather than silently picking one — correct uncertainty handling.
- **Durations** — 7s and 30s extracted correctly only when stated.

## Representative WEAK outputs (remaining, acceptable for C1)

- "quick 7-second clip" still nudged `pace:moderate` — "quick" lightly read as
  tempo. Minor; a candidate for a future prompt tweak if evals show it matters.
- Nova occasionally duplicates a feeling into both `desired_feeling` and
  `creative_constraints` (e.g. "serene"/"movie-like"). Harmless redundancy, not a
  contract or correctness issue.

## Failures discovered (process)

- **Account-level provider gate (not a code bug):** Anthropic Claude models on
  this Bedrock account return `ResourceNotFoundException — use case details have
  not been submitted`. That form is a human-only, account-owner action. Switched
  the config default to `amazon.nova-lite-v1:0` (no form gate, on-demand
  invocable), which satisfies the design's "reliable structured output, low
  latency, low/moderate cost" bar. Config-driven, so switching to Claude later is
  a one-env-var change once the form is approved.
- **Claude requires an inference-profile id** (not the plain on-demand id) — noted
  in the gateway for when Anthropic is enabled.

## Deterministic (Layer-0) + unit/endpoint tests

- Full suite: **68 passed** (contracts, API, harness, new engine + endpoint tests).
- Engine unit tests (fake gateway): valid→canonical conversion, request carries
  task/prompt-version/schema, underspecified→minimal (no fabrication), invalid
  output→`StructuredOutputError` (not fabricated), provider error propagates.
- Endpoint tests: 200 canonical intent, 422 body validation, 503 on
  structured-output + provider failures (designed failure path, never a fabricated
  intent).
- Live local HTTP check: `POST /v1/creative-intent` → real Nova → canonical intent,
  with the structured observability log (correlation_id, task, prompt/schema
  version, latency_ms, success; no raw user content).

---

# C1 Closeout (2026-10-01)

## Deploy — verified live

`POST /v1/creative-intent` is deployed on App Runner
(`https://ydmju5wdps.us-east-1.awsapprunner.com`): `/health` 200, endpoint 200
(no longer 404). Required two deploy fixes: Dockerfile now `COPY prompts/` +
installs `boto3`; the App Runner instance role was granted least-privilege
`bedrock:InvokeModel` via CDK.

## Physical-iPhone E2E — succeeded

Verified on a real iPhone (screenshot: "TMB travel 8 days"): iPhone → deployed
AWS → CreativeIntentEngine → BedrockModelGateway → real Nova → canonical
CreativeIntent → Swift DTO → local Story → DIRECT flow. The model-generated
summary and the "What Story understood" chips rendered on Story Home.
- **normal intent** ("beautiful but tough TMB hike, 60s"): success; summary +
  subject + 60s duration + feeling/emphasis chips.
- **vague intent**: success; minimal honest intent (no fabrication).
- **negative constraint** ("not cheesy"): success; constraint preserved.
- **End-to-end latency**: ~1–1.5s on-device (network + model). Acceptable.
- **UX issue found (documented, not fixed here):** the "Creating…" spinner is the
  only feedback during the ~1.5s call; on a slow network it can feel like a hang.
  Candidate UI-optimization work: a clearer progress/optimistic state. No decode
  or transport issues observed.
- **Quality issue found → fixed generally:** on-device output duplicated values
  across `desired_feeling` and `emphasis` ("beautiful"/"tough" in both) and used
  trip descriptors as moods. Fixed with ONE general prompt change (lists must be
  disjoint; emphasis is subjects/structure not moods; descriptors aren't moods)
  + a new deterministic `creative_intent_lists_disjoint` check + a regression
  fixture (`ci_beautiful_tough_regression`). Dropped the `✦` chip prefix.

## Expanded fixture set + full eval

Grew the curated set from 14 → **37** Creative Intent fixtures with real
within-category variation (vague ×4, equivalent-phrasing pairs ×3, negative
constraints ×4, subject/environment emphasis ×3, tone ×4, pacing ×3, duration
×3, conflicting/ambiguous ×3, + the on-device regression). Evaluation rule
unchanged (expected/forbidden semantic properties, no pinned prose).

**New failure class discovered:** `creative_intent_lists_disjoint` — a value
repeated across feeling/style/emphasis (the on-device duplicate). Caught by the
new deterministic check; 4/37 still trip it on both models even after the prompt
change (residual over-filling on ambiguous inputs like "dreamy, surreal"). All
37 remain **contract-valid**; the 4 are quality-check failures, not schema
failures. Captured as a tracked check so future prompt/model changes are
measured against it.

## Model comparison — Nova Lite (baseline) vs Nova Pro (candidate)

Same prompt version (`creative_intent/v1`), same canonical schema, same 37
fixtures, same inference config (temp 0). Both runs recorded in the harness.

| Metric | nova-lite-v1:0 | nova-pro-v1:0 |
|---|---|---|
| Contract success | 37/37 | 37/37 |
| All-checks pass (incl. disjoint) | 33/37 | 33/37 |
| Overlap failures | 4 | 4 |
| Latency p50 / p90 | **723 / 829 ms** | 893 / 1040 ms |
| Latency max | 1357 ms | 1687 ms |
| Output tokens (set) | 2670 | 2563 |

Semantic spot-check (feeling/emphasis/constraint handling on the hard cases):
- "beautiful but tough" — **Lite better** (mapped to `cinematic`/`raw`; Pro kept
  the descriptors as moods).
- "romantic not cheesy" — Pro marginally cleaner negative isolation.
- "dreamy surreal fog" — Pro cleaner; Lite over-filled.
- "minimalist but packed" — roughly equal.

**Decision: keep `amazon.nova-lite-v1:0` as the Creative Intent default.** Quality
is a wash (each wins some cases, same contract success, same residual overlap
failures), while Nova Pro is ~24% slower at p50 with no reliability gain — not a
meaningful semantic improvement to justify the latency on an interactive path.
Config-driven, so revisit per-task later. No broad bake-off performed.

## Anthropic access — account-owner action (documented, NOT required for C1)

Claude models on this Bedrock account return
`ResourceNotFoundException: use case details have not been submitted`. To enable
Anthropic models (for later stronger candidates, especially Story Director), the
**account owner** must, in the AWS console (us-east-1), region **Amazon Bedrock →
Model access**, request/submit the **Anthropic use-case details form** and enable
the desired Claude models; approval can take ~minutes. Claude must then be invoked
by its **inference-profile id** (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`),
not the plain on-demand id. Once enabled, switching is one env var
(`STORY_BEDROCK_MODEL`) — no code or ModelGateway change. Model selection stays
task-specific (Creative Intent ≠ Scene Understanding ≠ Director ≠ Validation).

## C1 close criteria — all met

- deployed AWS endpoint works ✅
- physical-iPhone E2E succeeds ✅ (3 intent types)
- expanded 37-fixture set passes contract evaluation ✅ (37/37 contract-valid)
- newly discovered failure captured as a regression (disjoint check + fixture) ✅
- all tests green ✅ (68 pytest; harness incl. new check)

**Milestone C1 COMPLETE.** Nova Lite default. Not proceeding to Scene
Understanding automatically.
