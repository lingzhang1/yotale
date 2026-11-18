# P0 — Large-Story EditPlan reliability: output-truncation recovery

Status: **IMPLEMENTED offline on `fix/planner-truncation-escalation`; NOT merged, NOT deployed, no live model call.**
Scope: backend provider/error contract and observability only. No creative strategy, prompt, validator, fitter,
renderer, iOS, routing, music, auth or release-config change.

## 1. Failure path (dev jobs, read from the jobs table and CloudWatch)

| | `f5350ca4` | `ad458f5b` | successful 66-Moment job |
|---|---|---|---|
| Moments / target | 68 / 290 s | 68 / 135 s | 66 / 135 s |
| Type / operation | Highlights / Original (`visual_first`) | same | Highlights / Original |
| Prompt version | not stored on failed jobs | not stored on failed jobs | `edit_plan/5.6` (stored) |
| Outcome | `invalid_after_repair`, "output truncated at maxOutputTokens" | same | completed |
| Worker time | ~419 s | ~354 s | ~215 s |
| Model calls | not stored | not stored | 2 (plan + one executability repair), both `gpt-5.1`, no fallback |

**Verified**
- Routing `edit_plan` = OpenAI `gpt-5.1` primary, Gemini fallback (`model_gateway/provider.py`). Initial cap 8,192, one escalation to 16,384 (`edit_planner._call`, `deps.py`).
- The words "maxOutputTokens" exist only in the Gemini adapter, so Gemini served the call that raised the final error, so the OpenAI primary failed first.
- Both adapters **raised** `StructuredOutputError` on truncation, after re-sending the identical request at the same cap (`max_repair_attempts=2` gives 3 generations). The planner's escalation only triggers on a *returned* `stop_reason == "max_tokens"`, so the 16,384 retry could never run on either provider. The OpenAI truncation error was also not a `ProviderError`, so it never failed over.
- The adapters' default timeout is 60 s with up to 2 same-provider retries on a timeout; nothing configures it otherwise. Worker deadline 840 s, Lambda 900 s, lease 900 s, and no provider call looked at the deadline.
- Failed jobs stored no `diagnostics`, so the failing job's model, error and token usage were not recorded.

**Successful job's 10,529 output tokens.** `diagnostics.model_calls = 2`, `output_tokens` is the sum across both calls (first plan, then a repair for one mistyped Moment id). That is about 5.3k per 56-segment plan, below the 8,192 cap. It does not show a response exceeding its cap.

**Not verified (instrumentation gap, hypotheses only).**
- Why OpenAI failed on the two failing jobs. Timing fits a 60 s timeout on the primary (3 × 60 s + backoff ≈ 183 s) followed by Gemini attempts (≈ 354 s total), but nothing recorded it.
- Whether Gemini hit 8,192 because the plan was long (290 s) or because hidden thinking tokens count against `maxOutputTokens` (they do on Gemini 3 models; `thoughtsTokenCount` was not recorded).

## 2. Changes

**Truncation contract.** New `OutputTruncatedError(StructuredOutputError)` (same message text) raised immediately by the OpenAI (`finish_reason=length`), Gemini (`MAX_TOKENS`) and Bedrock (`max_tokens`) adapters, with `provider`, `finish_reason`, `max_tokens`, `usage`. No same-cap re-send. Safety blocks, 4xx, malformed bodies, timeouts and "no tool call" keep their own classes. The planner catches it and retries once at `min(ceiling, max(2 × initial, 16,384))`; a second truncation raises the typed error. The result's `stop_reason` of `length`/`MAX_TOKENS` is also treated as truncated. Incomplete JSON is never accepted.

**Provider limits.** `gpt-5.1` documents 128,000 output tokens and `gemini-3.8-flash` 65,536 (secondary sources, to confirm against the provider consoles before relying on values above 16,384). The default ceiling is 32,768, a code constant.

**Initial output budget.** `estimate_output_budget(target_s, type)` = `(400 + 100 × ceil(target / typical_shot) × 1.25) × 1.25`, rounded to 256, floored at 8,192, capped at 16,384. Typical shot 2.5 s (Highlights), 6 s (Full Story). It depends on the requested duration and type, never on the Moment count, and it sizes the allowance only; it asks the model for no extra shots.

| Request | Initial budget |
|---|---|
| Highlights 35 s | 8,192 |
| Highlights 135 s | 9,216 |
| Highlights 290 s | 16,384 (escalation to 32,768) |
| Full Story 155 s | 8,192 |

The 100 tokens/segment figure comes from one stored job (about 94). Treat it as a starting point and re-fit it from the new `provider_attempts` data.

**Retry and deadline policy.**
- Truncation: at most 2 generations per planner call, and escalation stays on the same provider (no fail-over loop).
- Timeouts: a timed-out request is not re-sent to the same provider (`ProviderTimeoutError`); the fallback takes over. Connection resets, 429 and 5xx keep their bounded retries.
- Deadline: the worker sets `engine.deadline_ts = start + 840 − 45`. Adapters refuse to start an attempt with under 15 s left, clamp the socket timeout to the time left, and `ProviderDeadlineError` never fails over.
- Worst case for one planner call: 2 truncation generations × (primary + fallback) = 4 generations, down from up to 3 same-cap generations per provider with no escalation.

**Diagnostics.** Each adapter records per attempt: provider, model, attempt number, `max_tokens`, latency, outcome category, finish reason, input/output/reasoning tokens, and a sanitized, 160-character error (URLs and key/token values stripped). `FallbackModelGateway` merges them with a `role`, and attaches `primary_failure` to the exception when the fallback also fails. The planner stores `provider_attempts` (≤24, tagged with the prompt version), `initial_max_tokens`, `truncation_escalations`, `truncation_recovery` (`recovered` | `failed`), and `last_error_category`. The worker now persists a small `diagnostics` map on **failed** jobs too, and appends the primary-provider category to `failure_detail`. No prompt, image, raw response or credential is recorded.

## 3. Not done on purpose
- **Timeout value.** Unchanged at 60 s. A 16k-token plan cannot finish in 60 s at ~90 tok/s, so 290 s Highlights may still time out on both providers. The right timeout needs the latencies this change now records; propose then a budget-scaled value (for example `30 s + budget / 80`, capped by the remaining deadline), not a flat 180 s.
- **Gemini thinking level.** Not set; thinking tokens are only recorded now.
- **Moment-ID aliases.** Separate change. Long UUIDs cost about 24 tokens per segment and caused the repair call on the 66-Moment job; short aliases would cut output size by roughly a quarter and remove copy errors. Needs a prompt, validator and diagnostics review.

## 4. Offline tests
`packages/model_gateway/test_truncation_contract.py` (14) and `apps/api/tests/test_planner_truncation_recovery.py` (22): OpenAI and Gemini truncation, success after escalation, escalated truncation, unrelated structured error, primary timeout with fallback success, both providers failing with primary cause kept, real validation failure, 68/135, 68/290 and 66/135 fixtures, budget policy, deadline plumbing, version routing (5.3/5.5/5.6), sanitized failed-job diagnostics, and the worker failure path end to end. All stub providers; a mocked pass does not prove a real 68-Moment Story now succeeds.

## 5. Rollout (needs separate approval)
1. Merge via PR after CI. 2. Dev only: `deploy-dev` (API and worker use the same package). Check no job is in flight. 3. One controlled 68-Moment validation with existing media, recording latency, `provider_attempts` and output tokens. 4. No beta or production until that run succeeds. **Rollback:** revert the merge commit and redeploy dev; no data migration, and the new `diagnostics` on failed items is additive.

## 6. Follow-up: planner timeout (branch `fix/planner-timeout`)

**Finding (dev job `fc92ea54`, 68 sheets, 7.9 MB, `edit_plan/5.6`, after PR #132 was deployed):** both providers timed out at exactly 60 s (`gpt-5.1` 60.26 s, then `gemini-3.8-flash` 60.28 s). No call completed and no truncation occurred. The job failed in 123 s instead of the earlier 354 to 419 s. The 60 s is our own adapter default (`timeout_seconds=60.0`, added in `eac8f6bf`, 2026-10-23) and the router never overrode it for any capability.

**Change.** `StructuredRequest.timeout_seconds` (per request; adapters still clamp it to the caller deadline). On the async worker path only (when a deadline is set), each planner generation gets `min(240, 90 + max_tokens / 75)` seconds: 8,192 tokens about 199 s, 8,960 about 209 s, 16,384 or more 240 s. The synchronous API path and every other capability keep 60 s. The value is recorded as `planner_timeout_s`. Worst case, primary plus fallback at 8,960 tokens is about 420 s, inside the 795 s provider deadline; the deadline guard stops an escalation that cannot fit.

**Diagnostics.** The `finish_reason: true` seen while reading job items was a reading error in my inspection script: the job store writes a Python `None` as DynamoDB `NULL: true`, and the API reads it back as `null`. The stored data was correct. Attempt records now omit absent values instead of storing nulls.

**Still unknown:** how long a 68-sheet generation actually takes. The next run's `latency_ms` gives it, and the constants should be re-fit from that.
