# Per-Video Cost & $10 Plan Inputs — measured from live beta

Status: **MEASURED (2026-11-02)** from live beta. Direct-provider pricing is live
(PR [#76](https://github.com/lingzhang1/yotale/pull/76), `pricing_version = beta-pricing/2026-11-01-direct-providers`).

This is the **cost-of-goods** input for a billing strategy. It is **not** a pricing decision — it is the measured
cost to produce the AI outputs, so a plan can be priced with a chosen margin on top.

---

## 1. Why this exists / how we got here

Before 2026-11-01 the cost accounting could not see the models we actually ship on: the pipeline runs
`STORY_MODEL_PROVIDER=direct` (OpenAI `gpt-5.1` + Google `gemini-3.8-flash`), but `_DEFAULT_PRICING` only had
Bedrock Anthropic entries. Every direct-provider generation priced to **$0.0** with a `MissingModelPricing`
flag, so settled-cost data understated real spend and could not inform pricing.

PR #76 added the direct-provider prices and AI-Idea token logging. This doc is the first measurement after that
fix, taken from an owner beta session (imports + create/original + revise + explore).

---

## 2. Prices used (live `_DEFAULT_PRICING`, USD per 1M tokens)

Defined in `packages/observability/__init__.py`:

| Model | Input $/Mtok | Output $/Mtok | Used by |
|---|---|---|---|
| gpt-5.1 | 1.25 | 10.00 | EditPlan (worker), AI Idea (director), most sync AI |
| gpt-4o | 2.50 | 10.00 | legacy direct default (older jobs) |
| gemini-3.8-flash | 0.30 | 2.50 | Asset Understanding (AU) |
| gemini-1.5-pro | 1.25 | 5.00 | legacy routing default |
| opus-4 / sonnet-4 / haiku | 15/75 · 3/15 · 0.80/4 | — | Bedrock fallback / legacy |

> ⚠️ **These are list-price ESTIMATES.** The pricing table's own comment flags drift as an accepted limitation.
> Re-confirm `gpt-5.1` and `gemini-3.8-flash` against the providers' current published pricing before committing
> a plan to these numbers.

---

## 3. Data sources (how each number was measured)

All figures are from live beta (`account 224033508028`, `us-east-1`) on 2026-11-02, read from CloudWatch:

| Capability | Log group | Marker | Fields read |
|---|---|---|---|
| EditPlan | `/aws/lambda/story-beta-edit-plan-worker` | `bedrock_usage` | `op_type`, `model_id`, `model_calls`, `input_tokens`, `output_tokens`, `estimated_cost_usd` |
| AU | `/aws/apprunner/story-beta-api/<rev>/application` | `asset_understanding_resolved` | `model`, `input_tokens`, `output_tokens` |
| AI Idea | same (API app log) | `director_resolved` | `operation`, `model`, `input_tokens`, `output_tokens` |

`estimated_cost_usd` is computed by the worker via `observability.price_lookup` against the **actual served
model** (`calls[].served_by`), summing all billable attempts (retries, repairs, critiques, fallback).

---

## 4. Raw measured samples

### 4.1 EditPlan (worker `bedrock_usage`, gpt-5.1) — this session

| Time (UTC) | op | model_calls | input tok | output tok | cost |
|---|---|---|---|---|---|
| 08:12:14 | revise | 1 | 26,786 | 561 | $0.0391 |
| 08:14:58 | explore | 1 | 38,648 | 1,731 | $0.0656 |
| 08:19:49 | revise | 3 | 121,635 | 3,819 | $0.1902 |
| 09:24:47 | revise | 1 | 26,720 | 525 | $0.0387 |
| 09:30:59 | explore | 1 | 69,769 | 1,907 | $0.1063 |
| 09:34:07 | revise | 1 | 50,424 | 1,610 | $0.0791 |
| 09:38:47 | revise | 1 | 50,711 | 1,610 | $0.0795 |

Observations:
- A **1-call** EditPlan ranges ~$0.039 (small story) → ~$0.106 (explore on a larger story); cost scales with
  input tokens (= number of Moments × contact-sheet size).
- The **3-call** op ($0.1902, 121,635 input) is the reflection loop (plan → critique → revise), the most
  expensive single generation observed. A full **create/original** behaves like this multi-call pass.

### 4.2 Asset Understanding (`asset_understanding_resolved`, gemini-3.8-flash) — 24h, n=56

| input tokens | output tokens |
|---|---|
| median 30,243 (min 30,213 / max 30,254) | median ~663 |

AU input is **near-constant** — it is the 24-frame contact sheet, independent of clip content. One AU call per
imported clip.

### 4.3 AI Idea (`director_resolved`, gpt-5.1 initialize) — 24h

| operation | model | input | output |
|---|---|---|---|
| initialize | gpt-5.1 | 5,462 | 2,130 |

(Low call volume — AI Idea is only invoked when the user uses the Shooting-Idea/Director flow.)

---

## 5. Per-capability unit cost (tokens × live prices)

| Capability | Model | Tokens (in / out) | **Unit cost** | Billed |
|---|---|---|---|---|
| AU (per imported clip) | gemini-3.8-flash | 30,243 / 663 | **$0.0107** | once per imported clip |
| AI Idea (director init) | gpt-5.1 | 5,462 / 2,130 | **$0.0281** | per AI-Idea call (optional) |
| EditPlan — simple revise | gpt-5.1 | ~26,700 / ~525 | **$0.039** | per revise |
| EditPlan — larger revise | gpt-5.1 | ~50,500 / ~1,610 | **$0.079** | per revise |
| EditPlan — explore | gpt-5.1 | ~69,800 / ~1,907 | **$0.106** | per new version |
| EditPlan — create/original (full, up to 3-call) | gpt-5.1 | ~121,600 / ~3,819 | **$0.190** | per create |

Worked example (AU): `30243/1e6 × 0.30 + 663/1e6 × 2.50 = 0.00907 + 0.00166 = $0.0107`.

---

## 6. Per-video cost

A **video** = one EditPlan generation (create). AU is paid once per *imported clip* and amortized across every
video made from that footage — **not** per video.

| Scenario | Cost |
|---|---|
| Deliver one video (1 create) | ~**$0.19** |
| One video + 2 simple revises | ~**$0.27** |
| AU for a 15-clip Story (one-time) | ~**$0.16** |
| AU for a 37-clip import (one-time) | ~**$0.40** |

---

## 7. $10/month plan math (EditPlan cost; AU + AI-Idea on top)

| Target margin | AI cost budget | Full video creates | or simple revises |
|---|---|---|---|
| Break-even | $10.00 | ~52 | ~258 |
| 50% margin | $5.00 | ~26 | ~129 |
| **70% margin (recommended)** | $3.00 | **~15** | ~77 |

**Recommendation:** a $10/mo plan at ~70% gross margin leaves ~$3/mo of AI cost budget, which covers roughly
**15 full video creates** plus generous revises/explores (4–5× cheaper than a create) and the AU for their
source footage. A reasonable consumer entitlement is **~15–20 finished videos/month** with liberal revises,
keeping margin for AU, AI-Idea, storage, egress, and provider price drift. Tune against the real usage mix once
there is a wider sample.

---

## 8. Caveats (read before pricing)

1. **Prices are estimates** (§2) — re-confirm with OpenAI/Google before committing.
2. **Non-AI infra excluded** — storage (S3 media + evidence), egress, App Runner, Lambda, DynamoDB. Small per
   user but real; fold in before final pricing.
3. **Single-session sample** — EditPlan samples are from one owner beta session (n=7 ops); AU is n=56. Widen the
   sample across more users/stories before locking a plan.
4. **Cost scales with story size** — EditPlan input tokens grow with Moment count (contact sheets). A power user
   with 30+ Moment stories costs more per create than the ~$0.19 median here.
5. **"Gens" quota ≠ videos** — the per-user daily `gens` cap counts EVERY paid AI op (AU included), not finished
   videos, so a bulk import spends a user's daily allowance. Cap currently 500/day across all stages
   (PR [#77](https://github.com/lingzhang1/yotale/pull/77)). Decoupling AU ops from "video generations" in the
   quota/entitlement model is a prerequisite for a clean consumer plan.
6. **Failed/retry spend still bills** — `settled_usd` includes failed/repair/critique/fallback attempts; a user
   allowance refund does not erase incurred cost (by design). Budget for a real-world failure rate.

---

## 9. Provenance
Measured by Kiro from live beta CloudWatch logs on 2026-11-02; prices from the deployed
`beta-pricing/2026-11-01-direct-providers` table. Supersedes the "no cost data (all $0)" state that existed
before PR #76.
