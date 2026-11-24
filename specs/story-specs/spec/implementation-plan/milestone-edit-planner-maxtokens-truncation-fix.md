# Edit Planner — large-library 'no segments' 503 ROOT-CAUSED + fixed (output-token truncation)

Status: 🟢 fixed + deployed + log-verified. Date: 2026-10-11. App commit: see git. No contract/prompt change.

## Symptom
On a 24-Moment Story, `/v1/edit-plan` intermittently returned 503 "Edit Planner temporarily unavailable"
(`['no segments']` after 3 repair attempts). Same Story sometimes succeeded (7–17 segments) — intermittent.

## Root cause — PROVEN from logs (not inferred)
Added observability (gateway `stopReason` + token/size logging), then the next real failure logged:
```
last_stop_reason=max_tokens  last_output_tokens=2600  max_tokens=2600
raw_feasible=true  raw_segment_count=0  n_moments=24  input_tokens=25518  request_bytes=13133  model_calls=3
```
The Edit Planner's output cap was **max_tokens=2600**. A 24-Moment plan's JSON exceeds that, so Bedrock stops
at the ceiling (`stop_reason=max_tokens`), the truncated tool-call yields an **empty segments[]** with
`feasible` still true → validator `['no segments']` → 503. Intermittent because a compact plan (6–8 segments)
fits under 2600 while a fuller plan overflows. INPUT size was never the issue (25.5k input tokens is fine) —
it was **output truncation**.

## Fix (two parts, owner-approved)
1. **Raised the output cap** 2600 → **8192** (default), env-tunable `STORY_EDIT_PLANNER_MAX_TOKENS`. Fits a
   full ~17-segment plan with headroom.
2. **Retry-with-higher-cap on truncation**: `_call` detects `stop_reason=max_tokens` and retries ONCE at a
   ceiling (16384, env `STORY_EDIT_PLANNER_MAX_TOKENS_CEILING`) before failing. Bounded (one escalation).
3. Gateway now captures `stopReason` on `StructuredResult` and flags a truncated empty result explicitly.
4. Logs: `last_stop_reason`, `last_output_tokens`, `last_max_tokens_used`, `truncation_escalations`,
   `max_tokens`, `input_tokens`, `n_moments`, `request_bytes` on both success + failure paths.

## Verification
- 223 backend tests (+2: escalation-recovers-on-truncation, no-escalation-when-clean).
- Deployed (CodeBuild → ECR → App Runner RUNNING, health 200). Live 24-Moment call → 200, 6 segments,
  log shows `last_max_tokens_used=8192, truncation_escalations=0` (fit in one call under the raised cap).
- Frozen EditPlan/2 + v4 prompt + model + ±20% tolerance all untouched.

## Follow-up (not needed now)
Moment pre-selection remains available if a library ever outgrows even the 16384 ceiling; not required —
8192 already fits 24 Moments. Cost: marginally more output tokens on large plans only.
