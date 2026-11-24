# Proposal — AI Chinese Writing Quality (zh-Hans) milestone

Status: **PROPOSAL ONLY (read-only).** No prompt, routing, contract or code change has been made. Needs owner review before any implementation, and owner approval before any live model evaluation run.
Related: [copy quality pass v2](./i18n-zh-hans-copy-quality-v2.md) (UI copy, PR #116) · [AI language policy](./i18n-zh-hans-ai-language-policy.md).

## 1. Problem

When `content_language=zh-Hans`, the only Chinese-specific instruction the models get is the runtime line from `packages/language_policy` (`content_language_instruction`):

> OUTPUT LANGUAGE (runtime directive): write every human-readable string value … in Simplified Chinese (简体中文). Keep every JSON key, id, enum value … EXCEPTION: `visual_reference_query` … ALWAYS short English keywords.

It says *which* language but nothing about *how* to write it, and nothing about product vocabulary. The underlying prompts were written and tuned in English (e.g. `prompts/story_guide/v2/system.md` asks for "emotional beats", "warm, encouraging director", "calm voice"). Result, as seen on device:

> 「用几个安静的小片段，记录一个穿裙子的女孩在风里的独自行走与内心变化。」

| Issue | Example | Cause |
|---|---|---|
| Translated-English phrasing | "用几个…来记录…" calque, stacked modifiers | model translates its English-shaped plan |
| Wrong product noun | 片段 for Moments | no vocabulary given; the app now says 瞬间 |
| Invented inner state | 「内心变化」 | English prompt invites "emotional progression"; nothing forbids inventing it |
| Literary instead of useful | framing sentence reads like ad copy | "calm voice" rendered as poetic Chinese |
| Long instructions | how_to_shoot runs 3–4 clauses | English "one or two sentences" ≠ Chinese brevity |

## 2. Surfaces in scope

| Surface | Endpoint / package | Prompt | zh suffix today |
|---|---|---|---|
| Creative Intent summary ("我是这样理解的") | `/v1/creative-intent`, `packages/creative_intent` | `prompts/creative_intent/v1` | yes (`content_language`) |
| Story Guide v2 (framing_summary, scenes) | `/v1/story-guide-v2`, `packages/story_guide` | `prompts/story_guide/v2` | yes |
| Update Guide (refine) | `/v1/story-guide-refine` | `prompts/story_guide/refine-v1` | yes |
| Shooting Ideas (Director) | `/v1/director/initialize`, `/next`, `packages/story_director` | `prompts/story_director/v2` | yes |
| Coverage / Story Idea rationale | `/v1/story-coverage/v2[/jobs]` | `prompts/story_coverage/v2` | yes |
| Duration rationale | `/v1/duration-recommendation` | `prompts/duration_recommendation/v1` | yes |
| Edit-instruction interpretation | `/v1/interpret-revision`, `packages/edit_planner/revision_interpreter.py` | `revision_interpret/2` + runtime `CHINESE_GUIDANCE` | understanding only; no output text |

Out of scope: AU (`asset_understanding`), EditPlan, music plan, scene understanding (no user-facing Chinese prose), model routing, frozen contracts/schemas.

## 3. Proposed changes (smallest, versioned)

### 3.1 `zh_style/1` — one runtime style block, Chinese only
Add to `packages/language_policy` a constant `ZH_STYLE_VERSION = "zh_style/1"` and a style block appended **after** the existing output-language line **only when** the normalized language is `zh-Hans`. English requests and `en` requests are byte-identical to today (enforced by the existing byte-identity tests plus a new one). No prompt file is edited; no prompt_version string of a frozen contract changes.

Draft text (English, so it binds the model regardless of output language):

```
CHINESE STYLE (zh_style/1):
- Write natural, native Simplified Chinese as a Chinese creator would say it. Do not translate English phrasing word by word.
- Describe only what can be seen or what the user said. Never invent feelings, inner thoughts, relationships or dialogue.
- Shooting instructions: one or two short imperative sentences (where to stand, move or hold, how long to roll).
- Warm and cinematic, but concrete. No empty poetic phrases, no marketing slogans.
- Vocabulary: the user's clips are 「瞬间」; use 「片段」 only for a short excerpt of a clip; a scene is 「场景」, a shot 「镜头」, the finished video 「影片」.
- Keep the user's Story title, people's names and place names exactly as written.
- Never translate ids, Moment numbers, JSON keys or enum values.
```

Cache/idempotency: today the only server key that includes the language is the coverage-job body/fingerprint (`content_language`), and the iOS coverage `operation_id` hashes the request body; `language_policy.effective_language_key` exists but no caller uses it yet. For zh only, add the style version to those keys (`zh-Hans;zh_style/1`) so a result produced under the old wording is not returned as if it used the new one; English keys unchanged. Existing persisted Guides are **not** regenerated; new style applies to new generations and to Update Guide.

Observability: log `language_style_version` alongside `prompt_version` on each affected call (no payload text).

### 3.2 Interpreter vocabulary — `revision_zh_guidance/2`
`CHINESE_GUIDANCE` (runtime, Han-input only) lists 片段N / 第N个片段 / 第N段 / 镜头N. Add 瞬间N / 瞬间 N / 第N个瞬间 / 第 N 个瞬间 and state that 「那一瞬间」-style prose is not a Moment reference (matches the iOS parser in PR #116). Version the string (`revision_zh_guidance/2`) and log it. Schema, directive model, grounding guard and English path unchanged. The iOS deterministic parser already resolves chip and typed 瞬间 forms, so this only affects instructions that need the server.

### 3.3 Explicitly not proposed
No new model call (no translation or "polish" pass), no model/provider/routing change, no change to `prompts/**/system.md` of frozen versions, no schema change, no AU/EditPlan change, no change to `visual_reference_query` (stays English keywords).

## 4. Evaluation plan (~10 Chinese + 10 English Stories)

Reuse `evals/story_guide/` (fixtures.json + run_experiment.py), `evals/creative_intent/`, `evals/story_director/`, and `evals/harness`.

**Chinese fixtures (new):** 京都三日游（清水寺、锦市场、鸭川）· 妈妈的六十岁生日 · 成都周末吃货之旅 · 带娃去三亚海边 · 女儿的幼儿园毕业典礼 · 表姐的婚礼 · 家里猫咪的日常 · 川西自驾 318 · 北京胡同骑行一下午 · 年夜饭和守岁. Include 1 thin input (「周末」) and 1 mixed-language input (「Tokyo 迪士尼两天」), plus one user title with names (「小雨和阿杰的旅行」) to test name preservation.
**English fixtures:** the existing Story Guide fixtures (Japan trip, San Francisco, TMB, Indian wedding, birthday, …) up to 10 — regression only.
**Director fixtures:** 4 zh + 4 en scene-understanding fixtures from `evals/story_director` (zh run with `content_language=zh-Hans`).
**Interpreter fixtures:** 12 Chinese / mixed instructions with expected directives, e.g. 「从第 3 个瞬间开始，不要用瞬间 7」→ opening 3, exclude 7; 「瞬间 6 紧接在瞬间 2 后面」; 「只用瞬间 1、2、5」; 「那一瞬间很美，节奏慢一点」→ soft only; 「把最后一个放到最前面」→ unsupported/clarify.

Arms: baseline (current suffix) vs candidate (`zh_style/1`) on the same model routing; temperature as configured.

Scoring:
| Metric | How | Pass bar |
|---|---|---|
| Naturalness 1–5 | blind native-speaker review (owner + 1), baseline vs candidate shuffled | candidate ≥ baseline on ≥ 8/10 zh Stories, mean ≥ 4 |
| Invented mental states / dialogue | reviewer flag + deterministic word list (内心、心情、感受到、想起、说道、“…”) as a screen | 0 flagged in candidate |
| Vocabulary | deterministic: Moments referred to as 瞬间; 片段 only with an excerpt meaning | 100% |
| User text / ids preserved | deterministic: title, names, places, ids byte-identical in output where echoed | 100% |
| Instruction length | how_to_shoot ≤ 2 sentences and ≤ 60 Han chars | ≥ 90% |
| English regression | prompt bytes identical (unit test); outputs sampled for sanity | identical prompts |
| Interpreter accuracy | directives equal expected | 12/12, no invented exclude |
| Contract validity | every output validates against the existing schema | 100% |

Cost: about 20 Stories × (Creative Intent + Guide) + 8 Director + 12 interpreter ≈ 60 calls per arm, ~120 total, on dev only, after owner approval. No beta/prod calls.

## 5. Delivery steps (after approval)
1. Implement 3.1 + 3.2 offline with unit tests (byte-identical English, zh suffix present, cache key, logging). No deploy.
2. Owner approves the live eval budget; run both arms on dev; write results into this doc.
3. Owner decides: ship (dev deploy → device check → beta), iterate once, or drop.

## 6. Decisions needed
1. Approve the `zh_style/1` text (or edit it).
2. Approve versioning zh cache keys (`zh-Hans;zh_style/1`): Chinese coverage jobs miss their idempotency key once for Chinese requests after the change; persisted Guides on devices are never regenerated automatically (only a new Story or Update Guide uses the new style).
3. Approve the ~120-call dev evaluation budget and who reviews naturalness.
