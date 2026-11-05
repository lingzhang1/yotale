# YoTale P0 — Phase E: Async Worker Deploy + End-to-End Acceptance (dev)

**Status:** Steps 1–9 COMPLETE and verified live. **Step 10 (real-device acceptance) is the owner's** —
it needs the iOS app on a physical device with existing Moments, which cannot be driven from the agent
sandbox. **Dev only. No beta/gamma/prod.** Beta switch deferred to the GitHub pipeline (owner, separate).

**Deploy authority:** local `cdk deploy` (owner-approved for dev this round); beta will go through
`deploy-dev.yml`/`deploy-beta.yml` pipeline. Worker `CodeSha256 edSFzUVci86hXib9Hbc+HqQsuE0Ao5rcvZJB8DwRdmg=`,
HEAD `0e1a993`. App Runner digest `sha256:2d029c9…` (unchanged — digest-pinned).

---

## 1. Reconciliation (step 1)
Branch `feat/yotale-shooting-script-guide` is **11 ahead / 0 behind** origin/master — no conflicting
master changes, nothing to overwrite. Pre-existing WIP (pbxproj, xcscheme, beta-waf CDK) left untouched
and uncommitted. No merge needed.

## 2. Model IDs (step 2) — verified against LIVE catalogs
- OpenAI **`gpt-5.1`** ✅ present in the account's `/v1/models` (133 models).
- Gemini **`gemini-3.8-flash`** ✅ present in the account's generateContent model list (46).
Both match the deployed App Runner + worker env.

## 3. Worker build + tests (steps 3–4)
- `.worker-asset` rebuilt from HEAD via `scripts/build_worker_asset.sh` — contains the direct-provider
  routing code (`provider.py`, `openai_gateway.py`, `gemini_gateway.py`, `_secret.py`).
- **Backend + contracts + packages: 665 passed.** CDK unit: **67 passed.**

## 4. Authoritative CDK diff + §6 gate (steps 5–6) — PASSED
Full context supplied (`environment=development`, `modelProvider=direct`, `openaiModel=gpt-5.1`,
`geminiModel=gemini-3.8-flash`, `imageDigest=sha256:2d029c9…`). The diff touches **exactly 4 resources**:
- `AWS::IAM::Policy` instance role — `[+]` `DirectProviderKeyRead` only.
- `AWS::IAM::Policy` worker role — `[+]` `DirectProviderKeyRead` only.
- `AWS::Lambda::Function` worker — `[~]` Code (new asset) + `[+]` `STORY_MODEL_PROVIDER`/`STORY_OPENAI_MODEL`/
  `STORY_GEMINI_MODEL`. The four `STORY_EDITPLAN_*=1` v2 flags are **preserved** (drift reconciled; no
  longer dropped).
- `AWS::AppRunner::Service` — `[~]` ImageIdentifier reconciled from the stale template digest to the
  **current live digest** `2d029c9…` (a no-op; App Runner already serves it).

**NO changes to Cognito, SQS/DLQ, worker concurrency, storage (S3/DynamoDB), or observability
(LogGroup/Dashboard/Alarm/SNS). NO destroy/replace.** The §6 STOP gate did not trigger.

## 5. Deploy (step 7)
Local `cdk deploy story-development-api` with the verified context → `✅` in 186s (first) + 41s
(redeploy after the step-8 fix). Worker env confirmed: `STORY_MODEL_PROVIDER=direct`,
`STORY_OPENAI_MODEL=gpt-5.1`, `STORY_GEMINI_MODEL=gemini-3.8-flash`, all four `STORY_EDITPLAN_*=1`
preserved; worker role carries `DirectProviderKeyRead`; App Runner RUNNING, unchanged image.

## 6. Async create + revise verification (steps 8–9) — PASS

Submitted bounded **synthetic** jobs through the real `POST /v1/edit-plan-jobs` → SQS → Lambda worker:

| Job | Type | Result | served_by | model_id (logged) | mode |
|---|---|---|---|---|---|
| `1d1c4992` | create | completed, `edit_plan/2` feasible, 2 segments | **gpt-5.1** | **gpt-5.1** ✓ | — |
| `c477e4f3` | revise | completed, valid plan | **gpt-5.1** | **gpt-5.1** ✓ | revise ✓ |

- **Zero Anthropic/Bedrock calls for the tested ops.** The worker calls OpenAI over HTTPS (no Bedrock
  Converse emitted). The only Converse events in the window were `amazon.nova-lite-v1:0` by `user/Admin`
  (earlier agent diagnostics) — not Anthropic, not the worker.
- Technically valid `edit_plan/2` reaches the iOS rendering path shape (feasible, segments reference real
  Moment ids, duration within tolerance, passed the deterministic validator).
- Revise preserved its distinct semantics (`rev_diag.mode=revise`), separate from create.

### Bug caught + fixed live (step 8 would have mis-passed otherwise)
The worker's observability **hardcoded `model_id` to the Bedrock env** (`_PRIMARY_MODEL`/`_FALLBACK_MODEL`),
so the first create job (`313c0336`) logged `model_id=us.anthropic.claude-opus-4-6-v1` in `worker_plan_diag`
/ EMF / `bedrock_usage` **even though `served_by=gpt-5.1`** (OpenAI did the work; no Anthropic call). Fixed
(`0e1a993`): `_served_model_id(diag)` reads `calls[].served_by` and is used in cost, metrics, and diag;
the env is a fallback only when the gateway reports no served model. Redeployed; the next job correctly
logged `model_id=gpt-5.1`. **This was a labeling defect, not an Anthropic invocation.**

## 7. Observability / cost / latency (step 11)
- **Model calls recorded:** per-job `worker_plan_diag` logs `served_by`, `model_id`, `calls`,
  input/output tokens, fallback, repairs. create ~3.4k in / ~210 out tokens; revise similar; 1 model call
  each, no fallback, 0 repairs.
- **Latency:** async jobs completed within one ~8–10s poll (queue + single OpenAI call).
- **Cost:** actual **token counts are recorded**; estimated-USD currently reports **$0 with
  `MissingModelPricing=1`** because `gpt-5.1`/`gemini-3.8-flash` are **not in the Bedrock price table**.
  This is correctly FLAGGED (not silently $0). A direct-provider price table is **deferred** (the milestone
  explicitly defers cost optimization). Phase-D + Phase-E live spend combined ≈ **$1–2** (well under any
  budget).
- **Failure codes:** none in the tested ops (`failure_category=None`).
- The `bedrock_usage` log-event NAME is now a slight misnomer in direct mode (the `model_id` value is
  correct); renaming it would break existing Logs-Insights/alarms, so it is left and noted.

## 8. Rollback procedure (step 12) — tested path
The previous provider configuration is preserved and reversible WITHOUT a code change:
- **Flip back to Bedrock mode:** `cdk deploy story-development-api -c environment=development
  -c modelProvider=bedrock -c imageDigest=sha256:2d029c9…` → the worker + App Runner revert to the
  Bedrock/Opus→Sonnet path (env `STORY_MODEL_PROVIDER` drops to `bedrock`; the routed_gateway helper then
  uses `_gateway_with_fallback`). **Caveat:** Bedrock Anthropic is still revoked, so that target is only
  usable once access is restored — it is the documented config toggle, not a currently-working fallback.
- **Instant App-Runner-only revert:** `aws apprunner update-service` setting `STORY_MODEL_PROVIDER=bedrock`
  (env-only, ~1 min) for the synchronous surface.
- The two `DirectProviderKeyRead` IAM grants are additive and harmless to leave; remove via the same CDK
  if desired. No data migration involved either way.

## 9. Step 10 — real-device acceptance (OWNER)
Create/revise acceptance using **existing Moments** on a physical device must be run by the owner: the app
(pointed at dev `ydmju5wdps`, build with the scheme env) exercises Create→AU→Guide→EditPlan→MP4 and
Revise/Explore with real device Moments. The sandbox cannot drive the device or send real user media.
Everything server-side it depends on is deployed + verified above. Please run it and report any failure
code; I'll fix bounded integration defects on the same branch.

## 10. Status classification
- **Implemented + tested (665):** adapters, router, fallback, worker observability fix.
- **Deployed (dev):** App Runner + EditPlan Lambda worker on `STORY_MODEL_PROVIDER=direct`.
- **Live-verified:** async create + revise through the real queue → worker → OpenAI `gpt-5.1`, valid
  `edit_plan/2`, zero Anthropic, correct served-model labeling; Gemini AU (Phase D).
- **End-to-end verified:** async EditPlan → valid plan reaching the render path shape ✓. Full
  **device** create→…→playable MP4 and Revise/Explore: **pending owner (step 10).**
- **Not yet:** device acceptance; any beta change.

## 11. Proposed follow-up (separate milestone, per the task)
After functional device acceptance: an **editorial-quality comparison** — same Story inputs run through
the previous provider (Anthropic, once restored) vs. the new OpenAI/Gemini routing, on the frozen prompts,
scoring Guide specificity, AU fidelity, and EditPlan creative satisfaction. This is a quality study, NOT
part of functional restoration, and would also motivate the direct-provider **price table** (to replace
the `MissingModelPricing` gap with real cost accounting).

## 12. Constraints honored
Dev only; §6 gate enforced (no Cognito/SQS/DLQ/concurrency/storage/observability resource change, no
destroy/replace); no frozen prompt/contract/iOS change; EditPlan v2 flags preserved; Anthropic never
invoked (served_by + CloudTrail confirm); synthetic data only (no user media); secrets never
logged/returned; within budget; previous config + rollback documented. STOPPED before any beta switch.
