# YoTale P0 — Restore AI via Direct OpenAI + Gemini APIs (Phase A: read-only assessment)

**Status:** PHASE A ONLY (2026-10-23). Read-only inspection + implementation plan. No code changed, no
live API calls, no deploy, no secret values read. STOP for owner approval before Phase B.
**Scope:** dev account `989088054552` only. Independent-provider integration (NOT an Anthropic bypass);
Anthropic stays explicitly disabled.

---

## A1. Credentials & environment (inspected, no values exposed)

Both secrets exist in dev Secrets Manager, created today:
- `YoTale-Gemini-API-Key` — ARN `…:secret:YoTale-Gemini-API-Key-UGZgdS`, rotation off.
- `YoTale-OpenAI-API-Key` — ARN `…:secret:YoTale-OpenAI-API-Key-k2a12E`, rotation off.

**Format (key names only, values masked):** each is a JSON object with a single self-named key —
`{"YoTale-Gemini-API-Key": "<redacted>"}` and `{"YoTale-OpenAI-API-Key": "<redacted>"}`. This is the
**same shape as `Unsplash-API-Key`**, so the existing separator/case-insensitive single-key extractor in
`packages/scene_image` is directly reusable (handles bare-string AND single-key-object).

**IAM (gap found):** the App Runner instance role
(`story-development-api-StoryApiInstanceRole…`) has `GetSecretValue` for Epidemic + Unsplash only — it
does **NOT** cover the two new secrets. The **async EditPlan Lambda**
(`story-development-edit-plan-worker`, role `…EditPlanWorkerServiceRole…`) also needs read on the OpenAI
secret (EditPlan runs there). → Two scoped inline grants required, mirroring the existing `UnsplashKeyRead`
policy (one per role, resource = the two secret ARNs with the `-*` suffix).

**Network egress (no NAT needed):** App Runner `EgressType: DEFAULT` (public egress) and the Lambda has
**no VPC config** (`VpcConfig.SubnetIds: []`), so both already reach `api.openai.com` and
`generativelanguage.googleapis.com` directly over the internet. **No NAT Gateway / VPC change required**
(honors the "no significant infra cost" constraint). Lambda timeout is 900s (ample for a provider call).

---

## A2. ModelGateway & engine integration (the seam)

Confirmed from the audit (carried from the contingency assessment): `ModelGateway` is a one-method
`Protocol`; `StructuredRequest`/`StructuredResult` are provider-neutral; only `BedrockModelGateway` knows
a vendor; `FallbackModelGateway` already does primary→secondary on `ProviderError`. Engines depend on the
Protocol, never a vendor SDK. **No engine, prompt, or frozen contract needs to change.**

**Gateway construction points (the only files to touch for routing)** — all in `apps/api/app/deps.py`,
in two patterns:
- direct `BedrockModelGateway(model_id=…)`: scene-understanding, story-director, asset-understanding,
  (+ `get_model_gateway()` default used by creative-intent);
- `_gateway_with_fallback(model)`: story-coverage, story-guide (v1/v2/refine), edit-planner, music-plan,
  coverage-v2.

Both patterns funnel through **one place** if I add a factory — so routing is a single chokepoint, not
scattered edits.

### Structured-output translation (the one real adapter risk)
Bedrock forces schema-valid output via **Converse tool-use** (`toolChoice: {tool: emit_structured}`), and
`BedrockModelGateway._extract_tool_input` pulls the tool input. The adapters must reproduce "the output is
ALWAYS a schema-valid JSON object":
- **OpenAI:** Chat Completions / Responses with **Structured Outputs** (`response_format` =
  `json_schema`, `strict: true`) OR a forced tool/function call whose parameters = `req.schema`. Both
  guarantee schema-valid JSON → map to `StructuredResult.data`.
- **Gemini:** `generationConfig.responseSchema` + `responseMimeType: application/json`, OR a forced
  function call. Gemini's schema dialect is a subset of JSON Schema — the adapter must **down-convert**
  `req.schema` (e.g. drop/translate unsupported keywords) or fall back to function-calling. This is the
  main implementation unknown and gets a dedicated test.
- **Images:** both take inline base64 parts; map `ImageInput.data`/`media_type`. Ordered, timestamped
  frames are already encoded in `user_content` text + the image list order — no API-specific frame
  concept needed, so the existing AU/scene prompts carry over unchanged.

---

## A3. Model selection (GA, vision + structured-output capable; configurable)

**Do not hardcode — all via env, defaults documented.** Proposed initial defaults (capable over cheapest,
per the priority), each overridable:

| Env knob (new) | Proposed default | Why |
|---|---|---|
| `STORY_OPENAI_MODEL` | a current GA vision+structured-output GPT model (e.g. `gpt-4o`-class) | reasoning + strict Structured Outputs + vision; the text/creative + EditPlan primary |
| `STORY_GEMINI_MODEL` | a current GA vision Gemini Pro model (e.g. `gemini-2.x-pro`-class) | strong multimodal for 24-frame AU/scene; the image-understanding primary |
| `STORY_OPENAI_MODEL_FALLBACK` / `STORY_GEMINI_MODEL_FALLBACK` | a cheaper sibling | fallback leg |

**IMPORTANT (honesty):** exact model IDs MUST be confirmed against each provider's live model-list API /
docs at implementation time — I will NOT hardcode an unverified identifier. Phase B step 1 is "query each
provider's model catalog, pick the current GA vision+structured model, record the ID + reason." The
defaults above are placeholders pending that check.

**Per-capability routing** (from the task) is config-expressed, not hardcoded in engines:

| Capability | Primary | Fallback |
|---|---|---|
| Asset Understanding, Scene Understanding | Gemini | OpenAI |
| Story Guide v1/v2, Refinement, Creative Intent, EditPlan (create/revise/explore), Music Direction | OpenAI | Gemini |

Expressed as a routing table `STORY_PROVIDER_ROUTES` (task → {primary, fallback}) with per-task env
overrides, defaulting to the table above. Bedrock remains available for any task explicitly routed to it,
but **no task routes to a restricted Anthropic model**.

---

## A4. Proposed structure (additive; reuse interfaces)

```
packages/model_gateway/
  __init__.py            # existing: Protocol, StructuredRequest/Result, BedrockModelGateway, Fallback, Fake
  openai_gateway.py      # NEW  OpenAIModelGateway(ModelGateway)  — strict json_schema / tool-call
  gemini_gateway.py      # NEW  GeminiModelGateway(ModelGateway)  — responseSchema / function-call
  provider.py            # NEW  make_gateway(task) -> ModelGateway  (reads routes + secrets + builds Fallback)
  _secret.py             # NEW  reuse scene_image's single-key/bare-string extractor (shared)
```
- `make_gateway(task)` resolves the route, builds primary + fallback adapters, wraps them in the EXISTING
  `FallbackModelGateway`, and returns a `ModelGateway`. `deps.py` calls `make_gateway("story_guide.v2")`
  etc. instead of `BedrockModelGateway(...)`/`_gateway_with_fallback(...)`.
- **No second orchestration system, no engine rewrite, no new microservice.** Engines keep calling
  `generate_structured`. Adapters only translate request↔provider format.

---

## A5. Fallback & error handling (per §8 of the task)

Extend the error taxonomy so `FallbackModelGateway` fails over **only** on independently-recoverable
classes, and NEVER on the prohibited ones:
- **Fail over on:** transient transport, 429 rate-limit (after bounded backoff), 5xx, recoverable timeout,
  supported-model-temporarily-unavailable → raise `ProviderError`.
- **NEVER fail over on (stop + surface + record for owner):** content-policy denial, account/access
  denial, auth failure, malformed-request/4xx, schema-invalid-after-repair (`StructuredOutputError`).
  A policy/access denial throws a new typed `ProviderPolicyError` (subclass, NOT caught by fallback) so a
  denial on one provider is surfaced, not silently retried on the other.
- Bounded retries + exponential backoff; a hard cap prevents infinite fallback loops; record
  `{provider, model, request_id, duration, usage, fallback_used, error_category}` (no media/prompt bodies).
- **Anthropic stays explicitly disabled**: no route targets it; the restriction is never routed around.

---

## A6. Observability (per §11; minimal)

Each AI op already logs `operation`/`correlation_id`/`latency_ms`/`success`. Add (metadata only):
`provider`, `model_id`, `input/output tokens` (from `StructuredResult.usage`), `estimated_cost`
(tokens × a configured per-model price table), `error_category`, `fallback_occurred`. Reuse the existing
`observability` EMF/logger + the credential/URL scrubbers (already strip secrets, contact-sheet URLs,
auth headers). **No raw images/video/prompts logged.** Keep the Bedrock CloudWatch invocation-logging
(enabled earlier, metadata-only) as-is.

---

## A7. Exact files to modify (Phase B)

**New:** `packages/model_gateway/openai_gateway.py`, `gemini_gateway.py`, `provider.py`, `_secret.py`
(+ their unit tests under `packages/model_gateway/tests/`).
**Edit (small):** `apps/api/app/deps.py` (route via `make_gateway`); `packages/model_gateway/__init__.py`
(`__all__` + `ProviderPolicyError`). Add OpenAI + Gemini SDKs (or a thin `urllib`/`httpx` client — leaning
to a minimal direct-HTTP client to avoid heavy deps + supply-chain surface) to `apps/api` requirements and
the Lambda bundle.
**Infra (CDK, review diff first):** two scoped `GetSecretValue` statements (App Runner role + EditPlan
worker role) for the two secret ARNs — mirrors `UnsplashKeyRead`. New env vars (`STORY_MODEL_PROVIDER`
routes, model IDs, secret ids) on the App Runner service + Lambda. **No NAT, no new durable resource, no
monitoring/Cognito/storage change.**
**NOT touched:** engines, frozen prompts, frozen contracts (EditPlan v2, story_guide/*, moment_
understanding/1, story_coverage/2), iOS, beta/gamma/prod.

---

## A8. Incompatibilities / risks found

1. **Gemini JSON-Schema subset** — the biggest technical unknown; the schema down-converter (or
   function-calling fallback) needs a dedicated test against our real tool schemas (AU, Guide, EditPlan).
2. **EditPlan runs in the Lambda worker**, not just App Runner — the OpenAI adapter + secret read + egress
   must work there too (egress confirmed OK; IAM grant needed on the worker role; the Lambda bundle must
   include the new adapter code + any SDK).
3. **Structured-output fidelity varies** — repair-rate/cost may differ from Bedrock tool-use; measured in
   Phase C offline, not assumed.
4. **Provider content policy on minors** — BEFORE Phase D/E sends any real user media, the owner must
   confirm OpenAI's and Google's applicable policies + account eligibility (the task's §9 requirement).
   Phase D smoke tests use synthetic/authorized content only.
5. **Prompt portability** — frozen prompts are written for Claude/Converse; some may need technically-
   necessary (documented) tweaks for a provider's structured-output mode. Goal is functional parity, not
   quality tuning (deferred).

---

## A9. Phase plan & owner-approval gates

| Phase | Work | Live API? | Owner gate |
|---|---|---|---|
| **A (this doc)** | read-only assessment + plan | no | **approve plan → B** |
| **B** | adapters + `provider.py` router + `_secret.py` + wire `deps.py` + CDK (IAM+env) + unit/integration tests | no (mocked) | review PR + CDK diff |
| **C** | offline verification: text, multimodal frames, JSON parse, invalid JSON, provider errors, transient→fallback, policy-denial-no-failover, missing creds, timeout, EditPlan regression | no (mocked) | review results |
| **D** | dev deploy (existing CodeBuild→App Runner pipeline; Lambda update) + SMALL live smoke tests on synthetic/authorized content; confirm OpenAI + Gemini each callable + usage accounting | **yes, synthetic only** | **explicit approval; provider policy/eligibility confirmed** |
| **E** | device E2E on fixtures: Create→Intent→Guide→Refine→AU→EditPlan→MP4→Revise→Explore, no Anthropic | **yes, fixtures** | acceptance sign-off |

Phase B/C are no-live-model and can begin on plan approval. D/E need explicit approval + the minors-policy
confirmation before any real media.

---

## A10. Open decisions for the owner
1. **Approve this plan to start Phase B?**
2. **SDKs vs. thin HTTP client** for the adapters (I recommend a minimal direct-HTTP client — fewer deps,
   smaller Lambda bundle, less supply-chain surface).
3. **Provider content-policy + account eligibility for user media** — must be confirmed before Phase D/E
   (who confirms, and is synthetic-only smoke testing acceptable until then?).
4. Model-ID defaults will be set in Phase B **from the live provider catalogs**, then recorded here.

**Constraints honored:** dev only; no Anthropic routing/bypass; existing infra/egress reused (no NAT); no
engine/prompt/frozen-contract/iOS/beta-gamma-prod change; secrets never printed; nothing implemented or
deployed in Phase A.

---

## CLOSURE — DEV COMPLETE, BETA ROLLOUT PENDING (2026-10-24)

Owner accepted the direct OpenAI/Gemini migration for **development**. Live testing confirms all required AI
operations run through OpenAI/Gemini with **zero Anthropic inference**. Status: **DEV COMPLETE — BETA ROLLOUT
PENDING** (NOT fully released; beta deploy + device acceptance still required).

### 1. Final model routing (FROZEN for dev)

| Capability | Endpoint | Primary | Fallback |
|---|---|---|---|
| Creative Intent | `/v1/creative-intent` | OpenAI `gpt-5.1` | Gemini |
| Story Guide v1 | `/v1/story-guide` | OpenAI `gpt-5.1` | Gemini |
| Story Guide v2 | `/v1/story-guide-v2` | OpenAI `gpt-5.1` | Gemini |
| Story Guide refine | `/v1/story-guide-refine` | OpenAI `gpt-5.1` | Gemini |
| Story Coverage (v1/v2) | `/v1/story-coverage*` | OpenAI `gpt-5.1` | Gemini |
| **Scene Understanding** | `/v1/scene-understanding` | **OpenAI `gpt-5.1`** (moved from Gemini) | Gemini |
| Director / AI Ideas | `/v1/director/initialize` | OpenAI `gpt-5.1` | Gemini |
| Asset Understanding | `/v1/asset-understanding` | Gemini `gemini-3.8-flash` | OpenAI |
| EditPlan create/revise/explore | `/v1/edit-plan-jobs` (Lambda) | OpenAI `gpt-5.1` | Gemini |
| Music Plan | `/v1/music-plan` | OpenAI `gpt-5.1` | Gemini |
| Music Direction | `/v1/music-direction` | deterministic (no model) | — |

Anthropic is disabled at the router (`make_gateway` refuses `anthropic`/`bedrock-anthropic` and any
Anthropic-looking model id). Fallback policy unchanged: recoverable (transport/429/5xx) fails over;
`ProviderPolicyError` (policy/access/auth/4xx) **never** fails over.

### 2. Deployment evidence

- **Final commit:** `8ab2446` (branch `feat/r1-account-ownership-isolation`).
- **App Runner (story-development-api) running digest:** `sha256:ded7266a03d8a993f7e84e1e007941cc948abda56f1ac527addfbe322e44af43`
- **EditPlan Lambda (story-development-edit-plan-worker) CodeSha256:** `edSFzUVci86hXib9Hbc+HqQsuE0Ao5rcvZJB8DwRdmg=`
- **Live env (App Runner):** `STORY_MODEL_PROVIDER=direct`, `STORY_OPENAI_MODEL=gpt-5.1`,
  `STORY_GEMINI_MODEL=gemini-3.8-flash`, `STORY_GUIDE_V2=1`, `STORY_SCENE_IMAGES=1`. Scene route now carried
  by the **code default** (no `STORY_ROUTE_SCENE_UNDERSTANDING` env override needed — survives cdk deploy).
- Commit lineage: `eac8f6b` (adapters) → `cda66c6` (OpenAI max_completion_tokens) → `6153a7c` (Gemini $ref
  inliner) → `0e1a993` (worker served-model observability) → `cd33203` (durable App Runner env in CDK) →
  `4780da8` (director+duration routing) → `8ab2446` (scene_understanding → OpenAI).

### 3. Operation-level latency (observed in dev; small sample, NOT a statistical SLA)

| Operation | Provider | Calls (ok) | Latency min–max (avg) |
|---|---|---|---|
| Creative Intent | OpenAI | 3 (3) | 0.65–2.8s (1.9s) |
| Story Guide v1 | OpenAI | 1 (1) | 9.1s |
| Story Guide v2 | OpenAI | 14 (14) | 12.0–61.4s (23.0s) — one 61s cold outlier |
| Story Guide refine | OpenAI | 1 (1) | 10.3s |
| Duration (Sizing) | OpenAI | 2 (2) post-fix | 0.19–3.0s (≈1.1s) |
| Music Plan | OpenAI | 1 (1) | 3.9s |
| Asset Understanding (24 frames) | Gemini | 3 (3) | 12.2–22.9s (17.1s) |
| **Scene Understanding (Gemini, retired)** | Gemini | — | **49.9–132.2s** |
| **Scene Understanding (OpenAI, current)** | OpenAI | 4 (4) | **1.7–5.0s (≈3s)** |
| Director / AI Ideas | OpenAI | 4 (4) | 13.2–22.8s (16.1s) |
| EditPlan worker (create/revise/explore) | OpenAI | several (all) | ~8–15s/job; tokens 3.4k–121k in / 0.2k–6.0k out |

### 4. Scene Understanding routing change (recorded per owner request)

Gemini `gemini-3.8-flash` was **pathologically slow on scene_understanding specifically** — 49.9–132.2s for
1–3 frames, vs 12–23s for 24-frame asset_understanding on the same model — which timed out the on-device AI
Ideas flow (scene step precedes the Director call). Routed scene_understanding to **OpenAI primary / Gemini
fallback** (`8ab2446`). Measured improvement: **50–132s → 2–5s (~20–45×)**; full AI Ideas flow now ~17–23s.
Same `scene_understanding` contract; no engine/prompt/contract change; env-overridable via
`STORY_ROUTE_SCENE_UNDERSTANDING`. Owner directive: do NOT revert to Gemini.

### 5. Verification distinction

- **Implemented + dev-verified (live):** every capability above returned a valid structured response on
  OpenAI/Gemini; EditPlan async create + revise + explore verified through the real SQS → Lambda path
  (`served_by=gpt-5.1`); zero Anthropic Converse in CloudTrail for the tested window.
- **Tests:** full backend + CDK suites green (667 backend after the router fix; provider+deps suites green).
- **NOT verified:** beta environment (independent account/secrets — beta SSO token was expired at closure,
  so beta provider access is UNCONFIRMED), and real-device TestFlight acceptance.

### 6. Known limitations / unresolved acceptance gaps

- Story Guide v2 has a single 61.4s cold-start outlier (median ~23s) — deferred to the post-beta backlog.
- Direct-provider cost accounting reports `$0` + `MissingModelPricing=1` (gpt-5.1/gemini not in the Bedrock
  price table) — token counts ARE captured; a direct price table is deferred.
- Gemini scene_understanding slowness root cause not investigated (worked around by routing to OpenAI).
- Beta provider secrets/IAM/eligibility unverified (see beta handoff).

See `milestone-direct-openai-gemini-deferred-eval-backlog.md` for the full post-beta backlog.
