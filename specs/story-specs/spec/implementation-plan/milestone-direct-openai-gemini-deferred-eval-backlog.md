# Milestone (DEFERRED — post-beta): Direct Provider Evaluation & Optimization Backlog

**Status:** NOT STARTED — deferred until after the invited TestFlight beta.
**Parent:** `milestone-direct-openai-gemini-provider-restore.md` (DEV COMPLETE — BETA ROLLOUT PENDING).

The direct OpenAI/Gemini migration is functionally complete for dev. The following are explicitly **out of
scope for the migration** and must NOT be implemented now. They are recorded so they are not lost. Existing
evaluation fixtures and benchmarks are retained for these.

## Backlog items

1. **OpenAI vs Gemini quality comparison by capability.** Head-to-head creative/structured quality per
   capability (intent, guide, coverage, scene, director, editplan, music) on identical Story inputs, frozen
   prompts. Human + automated scoring. Decide any per-capability provider swaps on evidence.

2. **Asset Understanding: native video vs 24 timestamped frames.** Evaluate whether native video
   understanding beats the current 24-evenly-spaced-frame sampling (which can miss fast action between
   samples). Currently Gemini-primary and fast (12–23s). Do not switch sampling without an eval.

3. **Story Guide v2 latency + outlier investigation.** Median ~23s with a 61.4s cold-start outlier observed
   in dev. Characterize the distribution, find the outlier cause (cold start vs large input vs reasoning
   depth), and reduce tail latency.

4. **EditPlan large-context token + cost optimization.** Observed up to ~121k input tokens on large revises.
   Investigate context trimming, moment-summary compression, and plan-size-aware max_tokens.

5. **Prompt caching + context compression.** Evaluate provider prompt caching (OpenAI/Gemini) and
   context-compression strategies to cut repeated-input cost/latency across the multi-stage create path.

6. **Model routing + pricing optimization.** Build a direct-provider price table (gpt-5.1/gemini are absent
   from the Bedrock table → cost currently logs `$0` + `MissingModelPricing=1`). Then optimize routing by
   cost/latency/quality per capability, including cheaper models where quality allows.

7. **Provider reliability + failover evaluation.** Measure real-world error rates, 429/5xx behavior, and the
   OpenAI↔Gemini failover path under fault injection; tune per-attempt timeouts (the Gemini adapter's 60s
   per-attempt timeout × retries produced the 132s scene-understanding tail before it was routed to OpenAI).

8. **Human evaluation of creative quality + user preference.** Structured human eval of end-to-end creative
   output (device-rendered Stories) and user-preference testing across providers.

## Guardrails

- Do NOT implement any of the above as part of closing the migration milestone.
- Retain existing fixtures/benchmarks under `evals/` for reuse.
- Any change here must go through its own plan + eval report per the repo's experiment-record rule.
