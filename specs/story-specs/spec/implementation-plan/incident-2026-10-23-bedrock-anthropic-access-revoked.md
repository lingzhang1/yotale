# Incident Report — Anthropic Model Access Revoked on Bedrock (dev account 989088054552)

**Severity:** P0 (dev AI pipeline blocked)
**Status:** OPEN — owner appeal submitted to Anthropic; awaiting provider determination.
**Audit type:** READ-ONLY. No live inference run. No IAM / SCP / model-routing / quota / infra change.
**Date of audit:** 2026-10-23.

---

## 1. Summary (factual)

AWS Trust & Safety, acting on **Anthropic's** direction, **revoked account `989088054552`'s access
to Anthropic models on Bedrock**, effective **2026-10-23 19:20 UTC**, following an automated
abuse-detection determination (AWS Abuse Report `P01M5N3AWFGGC3BPTD7R2RDV28G`). The notice directs the
owner to appeal **directly with the model provider (Anthropic)**; AWS restores access only when
Anthropic directs it. The owner has submitted that appeal.

This is an **account-level, Anthropic-provider-specific** restriction. It is **not** an AWS infra,
IAM, SCP, billing, quota, or code/deploy issue, and it is **not** caused by the Guide v2.1 work.

---

## 2. What the evidence establishes

### 2.1 Affected account, access status, scope (req 1)
- Account confirmed: **`989088054552`** (caller `arn:aws:iam::989088054552:user/Admin`).
- **Anthropic models DENIED account-wide.** A metadata `GetFoundationModel` on
  `anthropic.claude-opus-4-6-v1:0` returns `ValidationException: invalid model identifier`, and the
  App Runner instance role's live `Converse` calls return
  `ValidationException: Access to Anthropic models is not allowed for this account.`
- **Scope is Anthropic-only.** Anthropic models still appear in the catalog
  (`ListFoundationModels` by provider anthropic = 15), and a **non-Anthropic** model
  (`amazon.nova-micro-v1:0`) reads `ACTIVE` and `Converse`s successfully. So Bedrock, IAM, the
  inference path, and cross-region profiles are all intact — only the Anthropic entitlement is revoked.
  (The denial message is the Bedrock marketplace-access signature, **distinct** from an SCP
  `explicit deny in a service control policy` message — this is not an SCP region-lock.)

### 2.2 Invocation patterns, model IDs, stages (req 2)
From CloudTrail (`bedrock.amazonaws.com`, last 24h) + App Runner application logs (last 6h):
- Event mix: `Converse` (34), `ListFoundationModels` (8), `ListInferenceProfiles` (4),
  `GetUseCaseForModelAccess` (2), `GetModelInvocationLoggingConfiguration` (1), `GetFoundationModel` (1).
- Model IDs invoked: `us.anthropic.claude-opus-4-6-v1` (12), `amazon.nova-lite-v1:0` (16),
  `amazon.nova-micro-v1:0` (1).
- App operations in the window: `scene_image` (19), `story_guide_v2` (10), `story_guide` (8),
  `resolve_creative_intent` (7), `music_direction` (7). This is **normal, low-volume product traffic**
  — no burst, no scripted flood in the captured window.
- **Retries / fallback:** the app's configured Opus→Sonnet quota fallback is present in code but NOT
  observed firing in this window (no provider-throttle events; the post-19:20 Anthropic failures are
  fast 400 `ValidationException` denials, ~505 ms, not throttles — the fallback does not catch an
  access-denial `ValidationException`, so each denied call surfaces as a clean 503 to the client).

### 2.3 Principals / workloads (req 3)
All three Bedrock-calling identities are **expected**:
- `arn:aws:iam::989088054552:user/Admin` — the owner's CLI (this audit + manual probes).
- `arn:aws:iam::989088054552:role/story-development-api-StoryApiInstanceRole...` — the App Runner
  service instance role (the YoTale dev backend).
- `arn:aws:.../AWSServiceRoleForSupport` — AWS Support service role (1 event; expected).
- **No unexpected principal, no foreign account, no unknown workload.** No evidence of credential
  compromise or third-party access.

### 2.4 Privacy-safe diagnostics available (req 4)
- **Bedrock model-invocation logging is NOT enabled** on this account (`get-model-invocation-
  logging-configuration` returns empty). Therefore **we have no stored prompt/response diagnostics**
  of our own to inspect. The only input/output retention that exists is **AWS's own abuse-detection
  store**, which per the official doc is **not shared with the customer** and (for the relevant model
  classes) may be human-reviewed by AWS — we cannot see what was flagged.
- No sensitive user content or secrets were read during this audit. Log review was restricted to
  operation/model/error **metadata**.

### 2.5 Timeline correlation (req 5)
| Time (UTC) | Event |
|---|---|
| ~17:14–18:47 | Normal Opus 4.6 `Converse` calls, all **OK** (12 successful; last **18:47:47Z**) |
| **19:20** | **Revocation effective** (per AWS email) |
| ~19:21 (12:21 PDT) | Owner receives AWS Trust & Safety email |
| post-19:20 | Every Anthropic `Converse` → `ValidationException` (denied); Amazon Nova still OK |
| ~20:10 | Guide v2.1 backend deployed to dev (CodeBuild → App Runner RUNNING); routes live |
| ~20:25 | v2 generate + v1 generate both fail with the Anthropic denial (deploy verification) |

- There were **no Anthropic calls in the 33-minute gap** between the last success (18:47) and the
  19:20 revocation — the revocation did **not** land on a specific in-flight request. Anthropic's
  offline detection reviews **retained traffic over up to 30 days** (per the doc), so the trigger is
  **historical**, not any single call today, and not the Guide v2.1 deploy (which came ~50 min after
  the revocation and merely surfaced it on the frozen v1 + v2 endpoints alike).

### 2.6 Unauthorized access / misuse / misconfiguration (req 6)
- **No evidence of unauthorized access or credential misuse** — all principals are the owner and the
  known dev App Runner role.
- **No evidence of a misconfigured workload** driving abusive volume — traffic is low and matches
  product use. The Opus→Sonnet fallback is a latent gap (it does not cover access-denial, only quota),
  but that is a resilience nit, not a cause.
- The determination originates from **Anthropic's content/policy classifier on retained traffic**, a
  layer we have no visibility into.

---

## 3. Most probable trigger (hypothesis, NOT established fact)

**Owner observation (2026-10-23, material):** today's testing created **no stories and uploaded no
personal videos/photos.** Confirmed in code: the stages that send image bytes to Anthropic
(`asset_engine` Asset Understanding, `scene_understanding`, multimodal `edit_planner`) run **only** on
story creation with uploaded media — so they **did not execute today**. Today's traffic was the
**text-only** StoryGuide path: `story_guide`/`story_guide_v2`/`story_guide_refine` build their
`StructuredRequest` with **no `images=`** (text-only), and the `scene_image` path makes **zero Bedrock
calls** — it calls the **Unsplash HTTP API** for image metadata/URLs that are hotlinked to the device;
**no Unsplash/online image byte ever passes through any Bedrock/Anthropic model.**

Consequence: **an online (Unsplash) image could not have triggered this** — online images never reach a
model. The flag therefore comes from **historical** image traffic, not today's work. The only
image-bearing Anthropic traffic in this account's history is **first-party user/test media** from
earlier sessions where videos *were* uploaded (e.g. the girl_with_dress / hiking / guitar test
datasets, device test runs, multimodal contact-sheet experiments). Anthropic's offline detection
reviews **retained traffic over up to 30 days** per the doc, which is consistent with a historical
trigger landing as a revocation today.

The official abuse-detection doc is explicit that (a) CSAM detection runs on **image inputs/outputs**
across models, and (b) for some Anthropic model classes **all traffic is retained up to 30 days and
classifier-flagged traffic is human-reviewed**. Given the restriction is Anthropic-specific and the
only Anthropic image traffic is first-party test media, the **most likely trigger class is Anthropic's
image/content classifier flagging ordinary personal-event imagery (people at weddings/trips/hikes) from
an EARLIER session — most plausibly a false positive**. A secondary candidate is historical
high-volume automated A/B/test traffic reading as rate-abuse.

**This is a hypothesis.** We **cannot establish which specific content or request was flagged**: AWS
does not share the flagged content, and model-invocation logging was not enabled at the time of the
incident (it has since been enabled metadata-only — see §6.1 — which helps only from now on, not
retroactively). The audit does **not** guess further, and recommends **no prompt change made solely to
evade detection**.

---

## 4. What can and cannot be established (req 7)

**Established:**
- Account, Anthropic-only scope, exact revocation time (19:20 UTC), and that non-Anthropic Bedrock works.
- All Bedrock principals are expected; no unauthorized access.
- Traffic in the captured window is normal product volume.
- The three image-bearing Anthropic stages exist and send user media.
- No model-invocation logging → no customer-side content diagnostics.
- The Guide v2.1 deploy did not cause the revocation (post-dates it; hits frozen v1 identically).

**Cannot be established:**
- The specific content, request, or policy clause Anthropic flagged.
- Whether the trigger was image content vs. volume vs. prompt/output text.
- Historical (pre-24h) traffic detail — CloudTrail management-event lookup is time-bounded and the
  deeper history is in AWS's non-shared abuse store.
- Whether the flag is a true or false positive.

---

## 5. Optional appeal supplement (factual, for Anthropic)

> On dev account 989088054552 we run YoTale, a consumer app that edits users' OWN personal photos and
> videos of real-life events (trips, birthdays, weddings) into short highlight videos. Anthropic
> image-capable models are used only to understand the user's own uploaded media and to generate/plan
> the edit; the only image inputs are first-party user media supplied for that purpose. CloudTrail
> shows all Bedrock calls originate solely from our own Admin user and our App Runner service role — no
> third-party, resale, or unknown principal. Traffic volume is low and consistent with product use. We
> believe any flagged image content is ordinary personal event imagery and a likely false positive;
> if the specific flagged item can be shared we will remediate immediately. We are adding pass-through
> of Anthropic's usage policies to end users and tightening rate/content controls.

---

## 6. Recommended safeguards (address evidenced risk only; req 9)

Evidenced gaps, not speculation:
1. **Enable Bedrock model-invocation logging** — **DONE (2026-10-23, owner-approved).** CloudWatch log
   group `/bedrock/model-invocation-logging` (90-day retention) + least-privilege service role
   `bedrock-logging-cw-role` (scoped to that one log stream). Configured **METADATA ONLY** —
   `textDataDeliveryEnabled`/`imageDataDeliveryEnabled`/`embeddingDataDeliveryEnabled`/
   `videoDataDeliveryEnabled` all **false**, so **no prompt/response/image bodies are stored** (no new
   store of user content). Gives invocation-level diagnostics from now on; does NOT help retroactively
   for this incident. This single IAM role was created under explicit owner approval, overriding the
   audit's no-IAM boundary for this action only.
2. **Pass Anthropic's usage policies through to end users** in the YoTale ToS/EULA (the Bedrock
   third-party-model agreement expects this).
3. **Rate-limit + de-duplicate experiment/test loops** against Bedrock (quota infra already exists; the
   A/B and device-rebuild loops are the likely volume source).
4. **Make the model fallback cover access-denial**, not only quota throttles, so a provider restriction
   degrades gracefully instead of hard-failing every AI stage. *(Code change — deferred to owner
   approval; out of scope for this audit, which must not alter model routing.)*
5. **Keep account contact email monitored** (the doc notes abuse requests go to the account email).
6. **Do NOT alter prompts solely to evade detection** (explicit owner instruction + good practice).

None of these were applied in this audit.

---

## 7. Guide v2.1 status under the restriction

Per the owner instruction, Guide v2.1 continues on **mocks + deterministic tests only** — no live
Anthropic inference in dev or beta. Verified offline this session:
- `test_story_guide_refine.py` + `test_story_guide_v2.py` → **15 passed** (no Bedrock).
- `MockStoryGuideV2Engine` / `MockStoryGuideRefineEngine` + `reconcile_refinement` run fully offline
  (deterministic identity/history reconciliation).
The deployed dev backend already carries the Guide v2.1 routes; they will function the moment Anthropic
access is restored, with no redeploy needed.

---

## 8. STOP

Per owner instruction, work STOPS after this incident report. No bypass via beta / another account /
region / credential / inference profile was attempted or will be. Awaiting owner review + Anthropic's
appeal determination before any further live-inference action.
