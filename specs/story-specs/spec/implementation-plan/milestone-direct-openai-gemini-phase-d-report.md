# YoTale P0 — Phase D: Deploy + Live-Verify Direct OpenAI/Gemini (dev)

**Status:** Phase D COMPLETE for the App Runner surface (Tests A–F). **Dev only. No beta/gamma/prod.**
EditPlan verified LIVE through the real engine on OpenAI; the EditPlan **Lambda worker** still needs a
CDK deploy (see §7). STOP for owner review before Phase E (device acceptance).

**Deployed:** App Runner `story-development-api`, image digest
`sha256:2d029c9134312bc0c1754b1c5393bb4338d3c7f5e0b71394d161c3c0f5ecc95a` (pushed 2026-10-23 18:38 PDT),
`STORY_MODEL_PROVIDER=direct`. Code commits: `eac8f6b` (adapters) + `cda66c6` (OpenAI max_completion_tokens
fix) + `6153a7c` (Gemini $ref inliner fix).

---

## 1. Selected model IDs (verified against live provider catalogs)

| Provider | Model ID | Why |
|---|---|---|
| OpenAI | `gpt-5.1` | current GA flagship; vision + forced-tool structured output. Account catalog confirmed it available (133 models listed). `gpt-4o` retained as a documented fallback-capable alternative. |
| Gemini | `gemini-3.8-flash` | current **stable** multimodal flagship-class; `generateContent` + function calling; strong vision for the 24-frame AU/scene path. Account catalog confirmed (46 generateContent models; `gemini-4-argon`/`gemini-2.5-pro` also available). |

Both env-configurable (`STORY_OPENAI_MODEL` / `STORY_GEMINI_MODEL`). The Phase-A placeholders
(`gpt-4o`/`gemini-1.5-pro`) were stale — replaced with current GA ids per the "do not silently downgrade"
rule.

## 2. Pre-deploy checks
- Both secrets present + correct shape (JSON single-key); **both keys authenticate live** (model-list
  calls succeeded) — Secrets Manager + extractor verified end-to-end.
- IAM: `DirectProviderKeyRead` scoped grant applied to the App Runner instance role (CLI inline, matching
  the committed CDK; the worker-role grant is in CDK, pending the Lambda deploy).
- Egress: App Runner reaches `api.openai.com` + `generativelanguage.googleapis.com` directly (no NAT).
- Model IDs verified against live catalogs (§1).
- CDK diff reviewed: **additive only, no destroy/replace** (2 IAM `[+]` + worker env); pre-existing
  `STORY_EDITPLAN_*` env drift flagged for the Lambda deploy.

## 3. Deployment
- CodeBuild `story-rb-caseg-build` → ECR `:latest` → App Runner `start-deployment` → **RUNNING**,
  `/health` 200. (Two code fixes required a rebuild each — §5.)
- Auth/storage/monitoring/networking unchanged; Anthropic not invoked.

## 4. Test-by-test results (synthetic data only; no user media)

| Test | Result | Evidence |
|---|---|---|
| **A — OpenAI connectivity** | ✅ PASS | model-list + structured calls succeed on `gpt-5.1`; valid JSON; usage metadata present |
| **B — Gemini multimodal** | ✅ PASS | synthetic image accepted; schema-valid `{dominant_color, n_objects}`; usage recorded (`gemini-3.8-flash`) |
| **C — Asset Understanding (Gemini)** | ✅ PASS | real `RealAssetUnderstandingEngine` on 24 synthetic frames → valid `moment_understanding/1` (summary/events/useful_segments/story_utility), persisted schema validated |
| **D — Story Guide (OpenAI)** | ✅ PASS | live `/v1/story-guide-v2` (5 scenes), `/v1/story-guide` (5 dims), `/v1/story-guide-refine` (preserved + added a scene) — all `gpt-5.1` |
| **E — EditPlan (OpenAI)** | ✅ PASS (engine-live) | real `RealEditPlannerEngine` on a 2-Moment synthetic fixture → valid `edit_plan/2`, feasible=True, 2 segments, asset_ids valid, total=target (10s), passed the deterministic validator. Renderer-compatible. **Caveat:** run through the ENGINE directly, not yet through the deployed **Lambda worker** (§7). |
| **F — Controlled fallback** | ✅ PASS (offline, by design) | `test_direct_providers.py`: recoverable `ProviderError` → fails over; `ProviderPolicyError` (policy/access/auth/4xx) → NEVER fails over. Per the task, no real policy violation was generated. |

## 5. Errors found + fixed (bounded integration defects, live-caught)

1. **OpenAI `gpt-5.1` 400 `unsupported_parameter: max_tokens`** → GPT-5-era requires
   `max_completion_tokens`. Adapter fixed (`cda66c6`) + regression test. This is why the first live Guide
   call 503'd (correctly classified `ProviderPolicyError`, not failed over).
2. **Gemini `SchemaTranslationError: $defs`** on Asset Understanding → the MomentUnderstanding tool schema
   uses `$defs`/`$ref` (nested models) + `anyOf:[X,null]`. The adapter correctly REFUSED rather than
   weakening. Fixed (`6153a7c`) with a `$ref` inliner + nullable-`anyOf` collapse that PRESERVES semantics
   (inlining = expansion; upstream still validates the original schema); raises only on recursive `$ref`
   or multi-type unions. AU then passed.
3. **Stale-image after env-only `update-service`** → the env flip served the OLD digest (still Bedrock);
   forced a `start-deployment` to pull the fresh routing code. (Known App Runner behavior; documented.)

No engine or prompt was redesigned; no frozen contract changed.

## 6. Usage, cost, latency

- Live calls this phase: OpenAI ~12 small calls (guide v1/v2/refine, editplan incl. repairs, probes);
  Gemini ~4 (1 synthetic image, 2× 24-frame AU, model-list). Model-list calls are 0-token.
- Observed token magnitudes: guide ~1–4k out; AU ~1–2k; editplan ~2–4k; `gpt-5.1` adds ~150–2k reasoning
  tokens/call. Total < ~200k tokens across both providers.
- **Estimated cost ≈ $1**, well under the **$10** phase budget. No repeated expensive EditPlan loops (the
  engine's repair cap held). Latency: interactive (guide/editplan single-digit seconds; AU a few seconds).

## 7. EditPlan Lambda worker — remaining deploy step (honest gap)

EditPlan's ASYNC path runs in the Lambda `story-development-edit-plan-worker`, which deploys via **CDK**
(the worker asset + `STORY_MODEL_PROVIDER` env + the worker-role `DirectProviderKeyRead` grant), NOT the
CodeBuild App Runner path I used. I verified EditPlan **live through the engine** (Test E) — proving the
OpenAI integration produces valid renderable plans — but the **deployed worker is still on old code +
bedrock mode**, so an end-to-end async create via the worker would currently fail until a CDK deploy. I
did **not** run the full-stack `cdk deploy` in this phase because it is heavier than the App Runner update
and would reconcile the `STORY_EDITPLAN_*` env drift mid-deploy — I flag it for an explicit go-ahead
rather than bundling it in. **Recommendation:** `cdk deploy story-development-api -c modelProvider=direct
-c openaiModel=gpt-5.1 -c geminiModel=gemini-3.8-flash` (diff pre-verified additive), reconciling the four
`STORY_EDITPLAN_*` flags, then re-run Test E through the live worker.

## 8. Acceptance criteria status

| # | Criterion | Status |
|---|---|---|
| 1 | Dev deployment healthy | ✅ App Runner RUNNING, /health 200 |
| 2 | OpenAI direct calls succeed | ✅ |
| 3 | Gemini direct calls succeed | ✅ |
| 4 | Both return valid structured output | ✅ |
| 5 | Gemini synthetic AU | ✅ (Test C) |
| 6 | OpenAI Guide + EditPlan | ✅ Guide live; EditPlan engine-live |
| 7 | EditPlan Lambda works with OpenAI | ⏳ engine-verified; **Lambda deploy pending** (§7) |
| 8 | Synthetic E2E → playable MP4 | ⏳ not yet — needs the Lambda deploy + render; Phase E |
| 9 | Controlled fallback correct | ✅ (offline, by design) |
| 10 | No Anthropic requests | ✅ CloudTrail: zero Anthropic Converse after direct mode live |
| 11 | No unexpected infra change / secret exposure | ✅ additive IAM only; keys never logged/returned |

## 9. Status classification (per req 11)
- **Implemented:** adapters, router, fallback, schema inliner, CDK IAM/env.
- **Deployed (dev):** App Runner on direct mode (OpenAI/Gemini), IAM grant on the instance role.
- **Live-API verified:** OpenAI (guide v1/v2/refine, editplan engine) + Gemini (multimodal, AU) — valid
  structured outputs, usage metadata, correct error classification, no Anthropic.
- **End-to-end verified:** NOT yet — the async EditPlan Lambda + render → playable MP4 is pending the
  Lambda CDK deploy (§7) and is part of Phase E.
- **Not yet verified:** device real-device acceptance (Phase E); any real user media (never sent).

## 10. Remaining limitations
- EditPlan **Lambda** not yet on direct mode (§7) — the one gap to full Test E/E2E.
- `STORY_EDITPLAN_*` env drift to reconcile at the Lambda deploy.
- Gemini schema fidelity relies on the new inliner; a future schema with a *recursive* `$ref` or a
  multi-type union would raise `SchemaTranslationError` (that capability would stay on OpenAI). Upstream
  validation still enforces the original schema, so no invalid object can slip through.
- Model-quality vs the Anthropic-tuned prompts is NOT assessed (out of scope; smoke phase only).

## 11. Recommendation for Phase E
1. `cdk deploy story-development-api` with the direct-mode context to update the Lambda worker + IAM +
   env (reconcile `STORY_EDITPLAN_*`); re-run Test E through the live worker.
2. Then device real-device acceptance: Create→Intent→Guide→Refine→AU→EditPlan→MP4→Revise→Explore on
   approved fixtures, confirming a **playable MP4** and no Anthropic — gated on your approval.

## 12. Constraints honored
Dev only; existing pipeline; no beta/gamma/prod; no NAT/new infra; no engine/prompt/frozen-contract/iOS
change; Anthropic never invoked; synthetic data only (no user media); secrets never logged/returned/
committed; within the $10 budget; no broad benchmarking; fallback never routes to Anthropic.
