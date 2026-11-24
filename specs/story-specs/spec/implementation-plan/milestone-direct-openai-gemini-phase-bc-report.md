# YoTale P0 — Direct OpenAI/Gemini Integration: Phase B+C Report

**Status:** Phase B (implementation) + Phase C (offline verification) COMPLETE. Dev only. **No deploy, no
live model/API call, no real user media.** STOP for owner review before Phase D.
**Commit:** `eac8f6b` on `feat/yotale-shooting-script-guide`.

---

## 1. What was built (implemented)

Additive provider portability on the existing `ModelGateway` seam — **no engine, prompt, or frozen
contract changed.**

**New files (`packages/model_gateway/`):**
- `openai_gateway.py` — `OpenAIModelGateway`: thin urllib HTTP client, Chat Completions with a FORCED
  tool call (`tool_choice`) whose parameters are `req.schema` → always a schema-valid JSON object;
  ordered multimodal frames as `image_url` data-URIs (each preceded by `[frame N]`); usage mapped;
  bounded retry + Retry-After.
- `gemini_gateway.py` — `GeminiModelGateway`: `generateContent` with a forced function call
  (`function_calling_config.mode=ANY`); `translate_schema()` conservatively down-converts JSON Schema →
  Gemini's dialect and **raises `SchemaTranslationError` on inexpressible constructs ($ref/allOf/anyOf)**
  rather than silently weakening the contract; Gemini SAFETY/PROHIBITED finish → policy error.
- `provider.py` — `make_gateway(capability)`: config-driven routing table + `FallbackModelGateway` wrap;
  `active_routes()` for diagnostics.
- `_secret.py` — shared Secrets Manager extractor (reuses the proven `scene_image` pattern; handles a
  bare string or a single-key JSON object — the shape of both new secrets).

**Edited:**
- `model_gateway/__init__.py` — new `ProviderPolicyError` (subclass of `ProviderError`);
  `FallbackModelGateway` now catches `ProviderPolicyError` FIRST and re-raises (never fails over).
- `apps/api/app/deps.py` — `routed_gateway(capability, bedrock_model)` honoring `STORY_MODEL_PROVIDER`
  (`bedrock` default = unchanged legacy path; `direct` = OpenAI/Gemini). All 9 engine construction points
  routed.
- `apps/api/app/worker.py` — the async EditPlan Lambda's two builders routed identically.
- CDK `story-api-stack.ts` — `DirectProviderKeyRead` least-privilege `GetSecretValue` on the two named
  secrets for BOTH the App Runner instance role and the EditPlan worker role; worker
  `STORY_MODEL_PROVIDER`/model env, context-driven (off by default).

## 2. Configured routing (approved Phase A table)

| Capability | Primary | Fallback |
|---|---|---|
| asset_understanding, scene_understanding | Gemini | OpenAI |
| creative_intent, story_guide (v1/v2/refine), story_coverage, edit_plan, music | OpenAI | Gemini |

All routes + model IDs env-configurable (`STORY_ROUTE_<CAP>="primary:fallback"`, `STORY_OPENAI_MODEL`,
`STORY_GEMINI_MODEL`). Music **Direction** is deterministic (no model) and needs no adapter; music
**Plan** routes to `music`. **No capability routes to Anthropic** — the router refuses an `anthropic`
provider token AND a `bedrock` route whose model id looks Anthropic (defense in depth). Legacy Bedrock
adapter retained but unused while `STORY_MODEL_PROVIDER=direct`.

## 3. Model IDs (provisional — verified in Phase D, NOT hardcoded blindly)

Defaults are env placeholders chosen as capable GA vision + structured-output families:
`STORY_OPENAI_MODEL=gpt-4o`, `STORY_GEMINI_MODEL=gemini-1.5-pro`. **Exact account-available GA IDs MUST be
confirmed against each provider's live catalog in Phase D** (the task forbids live model-list calls in
B/C). A missing/empty id raises — never a silent wrong-model call.

## 4. Fallback & error classification (verified by tests)

- Fail over ONLY on recoverable `ProviderError`: transport, timeout, 429 (after bounded Retry-After
  backoff), 5xx (bounded).
- NEVER fail over (→ `ProviderPolicyError`, stop + surface + record): 400/401/403, content-policy denial
  (incl. Gemini SAFETY), auth. Malformed JSON / no tool call / truncation → `StructuredOutputError`
  (not failed over — the model answered).
- Bounded retries + hard cap; no retry amplification (adapter retries transport/429/5xx; router does the
  single provider failover). Request correlation preserved via the existing per-op `correlation_id`.

## 5. Offline verification (Phase C) — all green, nothing weakened

`packages/model_gateway/test_direct_providers.py` (23 tests) covers the 18 required cases: OpenAI +
Gemini text-only structured; ordered 24-frame multimodal (order asserted); schema translation + $ref
rejection; missing/malformed credentials; timeout→ProviderError; 429-retry-then-OK + 5xx-exhausted;
400/401/403→ProviderPolicyError; Gemini SAFETY→ProviderPolicyError; malformed tool args→StructuredOutput
Error; **secret-value never surfaced in the result**; routing-by-capability + Anthropic refusal (×2);
App Runner (deps) + Lambda (worker) direct-mode construction; fallback fails-over-on-ProviderError and
does-NOT on ProviderPolicyError.

**Full suites:** backend + contracts + packages **663 passed** (was 636; +23 new, +4 pre-existing
`tests_fallback.py` that CI's `python_files=test_*.py` discovery was silently SKIPPING — fixed by
renaming `tests_*.py`→`test_*.py`, so the fallback guardrail now actually runs in CI). CDK **67 passed**
(incl. the new `DirectProviderKeyRead` name-scoped grant assertion). Existing Story Guide / AU / EditPlan
v2 / Revise-vs-Explore suites unchanged and green — no test weakened.

## 6. CDK diff (prepared, NOT deployed)

`cdk diff story-development-api` is **ADDITIVE ONLY — no destroy/replace**:
- `[+]` `DirectProviderKeyRead` statement on the App Runner instance role AND the EditPlan worker role
  (GetSecretValue on the two named secrets, `-??????` suffix match; NOT a `:secret:*` wildcard).
- `[+]` `STORY_MODEL_PROVIDER` on the worker env; `[~]` worker Code S3Key (asset rebuilt with routing code).
- **Note / pre-existing drift (flag for Phase D):** the diff shows `[-]` removal of
  `STORY_EDITPLAN_APPROX_DURATION_SOFT / _BEST_VALID_RETENTION / _OBJECTIVE_DIRECTIVES / _USEFUL_RANGE_SOFT`
  from the worker env. These were set on the DEPLOYED worker but are not in committed CDK source — this is
  deployed-vs-source drift from an earlier experiment, **NOT introduced by this change**. Reconcile or
  intentionally carry them at the Phase-D deploy; do not let the deploy silently drop them if still wanted.
- No NAT/VPC change (App Runner `EgressType: DEFAULT` + no-VPC Lambda already reach the provider APIs).

## 7. Secrets & IAM

Existing secrets reused unchanged: `YoTale-OpenAI-API-Key`, `YoTale-Gemini-API-Key` (JSON single-key
objects). Least-privilege GetSecretValue on both roles, name-scoped. Keys read server-side in-process
only; never in the iOS client, logs, exceptions, build output, or commits (redaction test enforces it).
Lambda bundle: the adapters live in `packages/model_gateway/` which is already on the worker's
`PYTHONPATH` (`/var/task/packages`); urllib is stdlib, so **no new dependency** to bundle.

## 8. Provider policy & privacy review (req 9) — a real Gemini blocker found

Reviewed official docs (2026-10-23):

**OpenAI** ([usage policies](https://openai.com/policies/usage-policies/),
[enterprise privacy](https://openai.com/enterprise-privacy/)):
- API data is **NOT used to train models by default**; DPA available; SOC 2; encryption at rest/transit.
- Minor-safety rules prohibit **CSAM / sexualizing / endangering** minors — they do **NOT** prohibit
  ordinary footage that merely depicts children. **No "consumer-use" prohibition.**
- **Assessment: ordinary family/travel footage of children is permitted**; the prohibitions are about
  abuse/exploitation, which YoTale does not do. OpenAI is terms-eligible for YoTale's use (DPA
  recommended before production).

**Google Gemini API** ([additional terms](https://ai.google.dev/gemini-api/terms)):
- **Paid vs Unpaid data use is critical:** on **Unpaid** Services, Google **uses submitted content to
  improve products and HUMAN REVIEWERS may read it**. Only **Paid** (billing-enabled) Services get the
  no-training / no-human-review protection. → YoTale must use a **paid** Gemini project before ANY real
  user media.
- **⚠ TERMS-ELIGIBILITY BLOCKER:** the Additional Terms state use is *"for... professional or business
  purposes, **not for consumer use**,"* and *"you will not use the Services as part of a... service that
  is directed towards or is **likely to be accessed by individuals under the age of 18**."* YoTale is a
  **consumer** app whose content depicts (and may be used by) minors. This is a genuine eligibility
  question that is **uncertain enough to block even synthetic Gemini testing** under the task's own stop
  condition — it needs an owner/legal decision (or written Google clarification) before Gemini is used at
  all, paid or not.
- Google also runs **abuse monitoring** (same class as the Anthropic/Bedrock mechanism that caused this
  incident) — so Gemini carries a comparable auto-action risk on image content.

**Neither provider prohibits ordinary imagery of children** (the task's distinction holds): the
prohibited category is CSAM/exploitation, which is not what YoTale does. **No blanket minor
detection/filtering/blurring was added** (constraint honored).

## 9. Known limitations / open items

1. **Gemini consumer-use + under-18 terms** (above) — a **STOP-worthy eligibility concern** for the
   Gemini leg. OpenAI-primary capabilities are unaffected; but AU/Scene **primary is Gemini**, so if
   Gemini is disallowed, AU/Scene would run on their **OpenAI fallback** (owner decision — may want to
   flip those routes to OpenAI-primary).
2. **Model IDs provisional** — confirmed against live catalogs in Phase D.
3. **Gemini schema fidelity** — our tool schemas use `additionalProperties:false` (dropped in translate)
   and none currently use `$ref`; if a future schema adds `$ref`, `translate_schema` will raise and that
   capability must stay on OpenAI. Upstream validation still enforces the ORIGINAL schema, so no invalid
   object slips through.
4. **CDK env drift** (§6) — reconcile the four `STORY_EDITPLAN_*` flags at deploy.
5. **No live verification yet** — connectivity, real model behavior, usage/cost accounting are Phase D.

## 10. Phase D proposal (needs explicit owner approval + the Gemini decision)

1. Resolve the Gemini terms question: either (a) owner accepts/obtains written Google clarification for a
   consumer app, or (b) re-route AU/Scene to **OpenAI-primary** and drop Gemini (one env change:
   `STORY_ROUTE_ASSET_UNDERSTANDING=openai:` etc.). Until resolved, **do not call Gemini even with
   synthetic content.**
2. Ensure the OpenAI (and, if approved, paid Gemini) project billing + DPA are in place.
3. Confirm GA model IDs from each provider's catalog; set `STORY_OPENAI_MODEL`/`STORY_GEMINI_MODEL`.
4. Deploy to dev via the existing CodeBuild→App Runner pipeline (+ worker) with `STORY_MODEL_PROVIDER=direct`;
   reconcile the `STORY_EDITPLAN_*` env drift.
5. SMALL smoke tests with **synthetic/authorized** content only (no historical personal media): confirm
   OpenAI callable, (if approved) Gemini callable, usage accounting, error handling.
6. Phase E device E2E on approved fixtures: Create→Intent→Guide→Refine→AU→EditPlan→MP4→Revise→Explore,
   no Anthropic.

## 11. Constraints honored
Dev only; no deploy; no live model/API call; no real user media; no Anthropic routing or bypass; no
NAT/VPC; no frozen prompt/schema/contract or iOS change; no beta/gamma/prod change; secrets never exposed;
no test weakened; no blanket minor filtering. **Completion is NOT claimed on connectivity** — this is
implemented + offline-verified; live-functional acceptance is Phase D/E, gated on owner approval and the
Gemini terms decision.
