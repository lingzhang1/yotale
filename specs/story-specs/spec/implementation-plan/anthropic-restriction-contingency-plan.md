# YoTale — Anthropic Restriction Contingency Plan (read-only engineering assessment)

**Status:** ASSESSMENT ONLY (2026-10-23). No code changed, no live model calls, no provider/account
change, nothing deployed. All implementation items below carry explicit owner-approval gates.
**Context:** Anthropic model access on dev `989088054552` revoked 2026-10-23 19:20 UTC (AWS Trust &
Safety, on Anthropic's direction). Appeal submitted; outcome uncertain and possibly slow.
**Objective:** keep YoTale developing toward an invited beta without relying exclusively on Anthropic,
while fully respecting the existing restriction.

---

## 1. Incident evidence & appeal posture (preserve; req 1, 2)

- The incident report (`incident-2026-10-23-bedrock-anthropic-access-revoked.md`) and the owner's
  submitted appeal stand. **No Anthropic inference will be attempted through another account, region,
  credential, or inference profile.** A single read-only access probe on dev (2026-10-23 ~23:20 UTC)
  confirmed the restriction is still in force (`ValidationException: Access to Anthropic models is not
  allowed for this account`).
- **Hypothesis correction (req 2):** footage depicting **minors is confirmed present** in the "Life in
  Egypt" story — 3 of 15 Asset Understanding records for owner `854abd33…` carry minor descriptors
  ("young", "minor"), and the owner supplied clips of children (a girl by a camel, girls baking bread,
  a boy on a boat). **However, there is NO evidence identifying this — or any specific content — as the
  restriction trigger.** AWS does not disclose the flagged item, and model-invocation logging was off
  at incident time. "Minor footage was sent to the vision model" is established; "minor footage caused
  the revocation" is **not**. The assessment treats the trigger as unknown.

---

## 2. ModelGateway portability audit (req 3)

**Finding: the gateway is already a strong portability seam. Provider portability is a SMALL, additive
change — no frozen-contract edits required.**

The seam (`packages/model_gateway/__init__.py`):
- `ModelGateway` is a `Protocol` with one method `generate_structured(StructuredRequest) ->
  StructuredResult`. Engines depend on the Protocol, never a provider SDK (enforced by
  03-system-architecture §15).
- `StructuredRequest` is **provider-neutral**: `task`, `schema` (JSON Schema), `system`, `user_content`,
  `images: list[ImageInput]` (raw bytes + media_type), `max_tokens`, `temperature`, `max_repair_attempts`.
- `StructuredResult` is provider-neutral: `data` (schema-valid dict), `usage`, `model`, `provider`,
  `stop_reason`.
- Only `BedrockModelGateway` knows a vendor. It uses Bedrock Converse **tool-use** to force schema-valid
  output (`toolChoice: {tool: emit_structured}`), lazy-imports boto3, and maps images to Converse image
  blocks.
- `FallbackModelGateway` already wraps primary→secondary on `ProviderError` (transport/throttle/auth) —
  **but NOT on an access-denial that arrives as a different error class** (see §2.2).

### 2.1 What a new provider needs (the whole surface)
A `GeminiModelGateway` / `OpenAIModelGateway` must implement exactly one method and map three things:
1. **Schema-forced structured output** — Gemini `responseSchema`/function-calling; OpenAI
   structured-outputs (`response_format` json_schema) or tool-calling. Both can enforce a JSON Schema,
   so `StructuredResult.data` is satisfiable.
2. **Multimodal image input** — both accept inline base64 image parts; map `ImageInput.data`/`media_type`.
3. **Error taxonomy** — map transport/throttle/auth → `ProviderError`; schema-invalid-after-repair →
   `StructuredOutputError`. Preserve the existing bounded-repair loop semantics.

No change to `StructuredRequest`/`StructuredResult`, to any engine, to any prompt, or to any frozen
contract is required. This is the key result: **portability is a new adapter class + config, nothing more.**

### 2.2 Smallest changes required (additive, flag-gated)
1. **Provider-selectable gateway factory.** Today `deps.py` hardcodes `BedrockModelGateway(...)` per
   stage. Add a `make_gateway(model_id)` indirection keyed by a `STORY_MODEL_PROVIDER` (bedrock |
   gemini | openai) env, defaulting to `bedrock`. ~1 factory function; each `get_*_engine` calls it
   instead of `BedrockModelGateway(...)` directly.
2. **Make `FallbackModelGateway` cover access-denial.** The Anthropic revocation surfaces as a Bedrock
   `ValidationException` wrapped in `ProviderError` ("Access to Anthropic models is not allowed") — but
   `ValidationException` is also thrown for genuinely bad requests, which should NOT fall back. Add a
   narrow predicate: fall back only on access-denied / throttle / transport, never on schema/validation.
   This is the "degrade gracefully instead of hard-failing every AI stage" fix.
3. **Two new adapter classes** (`GeminiModelGateway`, `OpenAIModelGateway`) behind the factory.
4. **Secret plumbing** for a non-Bedrock provider key (Secrets Manager, same pattern as the Unsplash/
   Epidemic keys) — only if/when a non-Bedrock provider is approved.

**Per-stage model config already exists** (no new mechanism needed): `STORY_SCENE_MODEL`,
`STORY_DIRECTOR_MODEL`, `STORY_AU_MODEL`, `STORY_GUIDE_MODEL`, `STORY_COVERAGE_MODEL`,
`STORY_EDIT_PLANNER_MODEL`, `STORY_MUSIC_PLAN_MODEL`, `STORY_LLM_FALLBACK_MODEL`, plus `*_MOCK` flags.
So a provider swap is config-first; code is only the adapter + factory.

### 2.3 Image-bearing stages (the restriction-relevant ones)
Only two engines send images today: `asset_engine` (Asset Understanding, 24 frames/Moment) and
`scene_understanding` (live scene frames); the multimodal `edit_planner` path also carries
`inputs.images` (contact sheets). All text-only stages (Story Guide v1/v2/refine, Coverage, Creative
Intent, Music, text EditPlan) are unaffected by any image policy and already run on whatever model the
config names.

---

## 3. Offline evaluation design (req 4)

**Principle:** evaluate a candidate provider/model WITHOUT live Anthropic and WITHOUT new user data,
using fixtures. Runs against any gateway via dependency injection (the `FakeModelGateway` pattern
generalizes to a real candidate gateway behind a flag, owner-gated).

### 3.1 Harness
- Reuse the existing fixture datasets (girl_with_dress / hiking / guitar) already in the repo's evals,
  plus a small text-only Guide/Coverage fixture set. **No footage of minors in the eval set** (avoid
  re-introducing the exact content class under investigation; a deliberate exclusion, not a filter
  claim).
- Drive each stage through its engine with a candidate gateway; capture `StructuredResult` + `usage`.

### 3.2 Dimensions per stage
| Stage | What to score | How (deterministic where possible) |
|---|---|---|
| **Asset Understanding** | subjects/events/temporal-order correctness vs. a hand-tagged reference; useful-segment sanity | rubric diff vs. reference AU; count missing/extra events |
| **Temporal event comprehension** | ordering (first/then/last), departure-vs-arrival, progression | ordered-event match rate |
| **Story Guide gen + refine** | event-specificity (anti-generic), scene distinctness, reconciliation correctness | reconciler is already deterministic+tested; score guide text for generic-template rate + distinct scenes |
| **EditPlan gen/revise/explore** | **technical validity (hard gate)** + creative-intent satisfaction | the existing `validate_technical` + `assess_creative_intent` scorers (edit_plan amendment v2) run offline, no model self-cert |
| **Cross-cutting** | latency (p50/p95), cost/call (from `usage` tokens × provider price), structured-output adherence (schema-valid on first try vs. repair rate) | measured from `StructuredResult.usage` + wall clock |

### 3.3 Pass bar (proposed, owner-tunable)
A candidate model is acceptable for a stage if: technical-validity ≥ current Bedrock baseline on the
fixtures, creative/understanding rubric within an agreed delta of the Anthropic baseline, p95 latency
within budget, and cost/playable ≤ an agreed ceiling. The **EditPlan creative-freedom philosophy
(frozen v2) is unchanged** — only the model behind it varies.

---

## 4. Gemini & OpenAI provider assessment (req 5)

Both are **independent of Anthropic/Bedrock** (different vendor, different enforcement), so they are a
legitimate portability option — NOT a circumvention of the Anthropic restriction (we would not call
Anthropic at all). Each carries its OWN content policy on imagery of minors, so neither removes the
underlying "we send children's footage to a third party" exposure; it relocates it to a different
vendor's rules.

| Dimension | Google Gemini | OpenAI |
|---|---|---|
| **Capable vision+reasoning models** | Gemini 2.x Pro/Flash (strong multimodal, long context) | GPT-4o / o-series vision |
| **Structured output** | `responseSchema` (JSON schema) + function calling | native structured outputs (json_schema) + tools |
| **Multimodal input** | inline base64 image parts; also video/file APIs | inline base64 image parts |
| **Adapter effort** | one `GeminiModelGateway` (REST or google-genai SDK) mapping schema+images+errors | one `OpenAIModelGateway` (openai SDK) mapping same |
| **Data handling (MUST verify in writing before any use)** | enterprise/paid tier data-use + retention terms; region/residency; whether inputs train models | enterprise API data-use (no-training default on API) + retention; zero-retention options |
| **Minors-in-images policy** | has its own CSAM/minor-safety enforcement + automated detection | same class of enforcement; comparable auto-action risk |
| **Known limitations** | schema adherence occasionally looser than Bedrock tool-use; rate limits per project | cost at vision scale; rate limits; its own abuse review |
| **Key management** | API key in Secrets Manager (same pattern as Unsplash/Epidemic) | same |
| **Billing** | separate vendor billing, OUTSIDE AWS (owner cost decision) | separate vendor billing |

**Honest caveat:** switching the IMAGE-understanding stages to another frontier vendor trades Anthropic's
enforcement for that vendor's. For a family-memories app whose core content is footage of children, the
**durable** answer (see §7 risks) is reducing third-party exposure of that content — a design question,
not a vendor swap. A vendor swap is a legitimate interim for CAPABILITY, not a fix for the exposure.

---

## 5. TestFlight readiness WITHOUT live Anthropic (req 6)

**Can proceed now (no live Anthropic):**
- Guide v2.1 iOS device build + UI acceptance (Update Guide sheet, pins, event-context) — UI renders
  from persisted/mocked data; only the live refine call needs a model.
- All deterministic/mock backend + iOS tests (already green: 636 backend, Guide v2.1 suites).
- iOS app-store readiness non-AI work: auth/OTP flows, media capture/upload (R2–R7), sync, storage
  optimization, playback, account isolation, crash/perf, UI polish, accessibility.
- Offline model evaluation harness build (§3) against the `FakeModelGateway` / a candidate gateway.
- Provider adapter CODE (Gemini/OpenAI classes) written + unit-tested against recorded fixtures — no
  live key needed to write/test the mapping with a fake transport.
- Appeal follow-through + the data-handling/terms review for candidate providers (paperwork, no code).

**Blocked until a model path is authorized (Anthropic restored OR a new provider owner-approved):**
- Live end-to-end create → understand → guide → edit on device.
- Live before/after Guide refinement examples.
- Any real-device acceptance that exercises a model call.

---

## 6. Proposed release gate (req 7)

An invited-beta release MUST satisfy ALL of:
1. **Verified provider authorization** — either Anthropic access restored in writing, OR a non-Anthropic
   provider approved by the owner with its data-handling terms reviewed and accepted.
2. **Acceptable model quality** — the chosen model passes the §3 offline bar on every stage it serves.
3. **Successful real-device end-to-end testing** — create → AU → Guide (+refine) → EditPlan → render on a
   physical device, on the authorized provider, green.
4. **Content-exposure decision recorded** — an explicit owner decision on how footage of minors is
   handled (kept on the third-party vision path with accepted risk, OR an architecture that reduces it);
   NOT an automated filter imposed on an unproven hypothesis (per constraint).
5. **Graceful degradation verified** — a provider outage/denial degrades (fallback or honest error), not
   a hard failure of every AI stage (§2.2).

---

## 7. Risks

- **Vendor-swap does not remove the minor-imagery exposure** — it moves it to another enforcement regime
  with comparable auto-revoke risk. Highest-severity structural risk for this product.
- **Appeal may never be meaningfully reviewed** (low-ARR account); plan as if restoration is uncertain.
- **Schema-adherence variance** across providers could raise repair rates / cost; the offline harness
  must measure this before committing.
- **Data-residency / training-use terms** differ per vendor and must be accepted in writing before any
  user content flows — a legal/privacy gate, not just technical.
- **Creative-quality regression** vs. Anthropic-tuned prompts is likely on a different model; prompts may
  need per-provider tuning (NOT to evade detection — for quality).

---

## 8. Recommended implementation sequence (with owner-approval gates)

| # | Step | Live model? | Effort | Owner gate |
|---|---|---|---|---|
| 0 | Keep appeal open; do not touch Anthropic | no | — | — |
| 1 | `make_gateway` provider factory + `STORY_MODEL_PROVIDER` (bedrock default) | no (refactor) | ~0.5 d | review PR |
| 2 | `FallbackModelGateway` covers access-denial (narrow predicate) | no | ~0.5 d | review PR |
| 3 | Offline eval harness (§3) against FakeGateway + fixtures (no minors) | no | ~2–3 d | review results |
| 4 | Candidate adapter(s) `GeminiModelGateway`/`OpenAIModelGateway` + unit tests (recorded fixtures) | no | ~2–3 d each | **approve provider + review data terms BEFORE any live key** |
| 5 | Continue non-AI TestFlight readiness in parallel | no | ongoing | — |
| 6 | (gated) wire a live candidate key in Secrets Manager + run §3 live eval | **yes** | ~1 d | **explicit owner approval; provider + billing + data terms accepted** |
| 7 | (gated) real-device end-to-end on the authorized provider | **yes** | ~1–2 d | release-gate §6 |
| 8 | (decision) minor-imagery handling architecture | design | TBD | **owner decision; no automated filter on an unproven hypothesis** |

Steps 1–5 are all **no-live-model** and can start immediately under normal PR review. Steps 6–8 require
explicit owner approval and a verified provider path.

---

## 9. Constraints honored
- No live model calls beyond the single read-only access probe; no provider/account change.
- No circumvention of the restriction (no new account / region / credential / inference profile).
- No blanket filtering/blurring of children proposed — only a recorded owner DECISION point (§6.4, §8.8).
- No new infrastructure proposed beyond a secret entry, and only if a provider is approved.
- Frozen EditPlan v2 creative-freedom philosophy untouched.
- All work scoped to beta readiness. Nothing implemented or deployed.
