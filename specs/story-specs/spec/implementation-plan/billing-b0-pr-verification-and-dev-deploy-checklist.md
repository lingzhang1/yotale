# Billing V1 B0: PR verification report and dev-only deployment checklist

Status: **VERIFIED OFFLINE on `feat/cost-logging-all-ai-handlers` (2026-11-18). Not merged. Not deployed.** Nothing here authorises a merge or a
deploy; both need the owner's separate approval. Scope of this PR: cost instrumentation and cost documentation only (no billing, no entitlements).

## 1. Verification matrix

| Requirement | Evidence | Result |
|---|---|---|
| Captures every known AI capability | Every model call goes through `generate_structured`; `test_every_model_call_site_is_a_known_capability_that_goes_through_the_gateway` inventories all call sites (AU, creative intent, duration, edit plan incl. repairs/revise, interpret revision, music plan, scene understanding, coverage v1/v2, AI Ideas, guide v1/v2/refine) and fails when a new one appears; both adapters log every billed attempt (`test_only_adapters_reach_a_provider_and_both_log_each_attempt`); Bedrock/Anthropic is not routable | Pass |
| Attributes user, operation, job, attempt | `story_user_id`, `operation`, `job_id`, `correlation_id`, `call_index`, `attempt`; API middleware and per-job worker context (`test_worker_job_context_is_set_during_the_run_and_cleared_after_success_and_failure`, `test_request_middleware_sets_context_for_sync_handlers`) | Pass |
| Actual served provider/model | `provider`, `model_id` come from the adapter that served the attempt, including the fallback adapter | Pass |
| Thinking tokens where reported | OpenAI reasoning is inside `completion_tokens` (not added twice); Gemini `thoughtsTokenCount` is added to `billed_output_tokens` (`test_gemini_thinking_tokens_are_billed_as_output`) | Pass |
| Estimated vs invoiced | every line carries `cost_basis="estimated_list_price"`, `pricing_version`, `pricing_known`; there is **no** invoiced figure in the logs. Reconciliation against OpenAI/Google billing exports is a manual step (checklist step 7) | Pass (labelled) |
| No double counting of retries or legacy telemetry | one line per provider attempt; aggregate by `job_id`/`correlation_id`. `bedrock_usage`, `asset_understanding_resolved`, `director_resolved` describe the same calls and **must not be added** to `model_call_usage` totals (see query in the B0 report) | Pass (documented) |
| No prompts, media, emails, secrets, payment details | context keys are allow-listed and values bounded (`test_attribution_context_drops_unknown_fields_and_bounds_values`); lines contain counts, ids, model and route names only (`test_no_prompt_media_or_user_fields_are_logged`, `test_log_line_has_estimated_cost_basis_and_no_free_text_fields`); `scrub_log_fields` leaves the attribution ids intact | Pass |
| Context resets on exception and cancellation | `test_context_resets_when_the_block_raises`, `test_context_resets_when_the_task_is_cancelled`, `test_concurrent_requests_do_not_see_each_others_attribution`, `test_two_consecutive_jobs_never_share_a_call_counter_or_attribution` | Pass |
| Logging failure never breaks a model call | `test_logging_failure_never_breaks_the_call` | Pass |
| No `story_id` added to AU for reporting | not added; documented as optional/absent (Moments belong to several Stories; per-account Moment cost is authoritative) | Pass |
| Documentation reflects current beta configuration | new section 0 in `billing-measured-cost-dev-beta.md` (planner 5.6, providers, quota posture, evidence persistence ON, self sign-up); corrected "persist flag is off" in the B0 report | Pass |

Test results on this branch: `apps/api/tests`, `packages`, `contracts/tests`, `evals/harness` = **1337 passed**. No CDK file is changed by B0.

## 2. Final diff summary (B0 only)

Code: `packages/model_gateway/__init__.py` (call context + `log_model_call`), `openai_gateway.py` and `gemini_gateway.py` (one call each at the
`make_attempt` seam), `apps/api/app/cost_context.py` (new innermost middleware), `apps/api/app/main.py` (register middleware; `story_id` set in
six handlers whose request has one), `apps/api/app/worker.py` (per-job context). Tests: `test_model_call_usage.py`, `test_cost_attribution.py`.
Docs: `billing-measured-cost-dev-beta.md`, `billing-b0-cost-attribution-and-unit-economics.md`, this file, index entry. Script:
`scripts/billing_unit_economics.py`. No billing logic, no entitlement, no IAM, no env var.

## 3. Residual risks (none block a dev deploy)

1. Log volume: about one extra line per billed model attempt (AU adds one per Moment). The Iceland beta session (90 Moments, 3 videos) produced roughly 130 such attempts in 45 minutes, so volume is small; CloudWatch ingestion cost is negligible at current usage.
2. `model_call_usage` has never run against live traffic. Checklist step 5 is the first real validation.
3. Prices are list-price estimates; Gemini AU history is a lower bound (thinking tokens were not logged before).
4. Failed attempts with no provider usage object (transport errors) log nothing because nothing billable is visible.

## 4. Dev-only deployment checklist (execute ONLY after the owner approves the merge AND the deployment)

All commands are read-only unless stated. No production, no beta, no CDK change is part of B0.

1. **Approvals recorded:** owner approval of PR 1 merge; owner approval of a dev deploy. CI is green on PR 1 (`python-tests`, `cdk-tests`, `release-config-gate`).
2. **Merge** PR 1 through the protected workflow (merge commit). Confirm `git fetch origin && git log -1 origin/master`.
3. **Pre-deploy gate (local, no AWS writes):**
   `bash scripts/build_worker_asset.sh` then `cd infrastructure/cdk && npx cdk synth -q -c environment=development --output /tmp/cdk-pre`
   then `python3 scripts/release_config_gate.py pre --environment development --template /tmp/cdk-pre/story-development-api.template.json --worker-asset infrastructure/cdk/.worker-asset --require-clean-asset`.
   Expected: exit 0; the synthesized diff versus the deployed stack contains **only** the new image digest and worker asset hash (B0 changes no CDK resource).
4. **Deploy:** GitHub Actions "Deploy (dev)" workflow, `workflow_dispatch`, input `confirm=deploy-dev`, run from `master`. (Same workflow that does the pre and post gates.)
5. **Post-deploy exercise (one real device session on dev, about 10 minutes):** import 3 Moments (AU), open a Story (guide v2, coverage), create a video
   (creative intent, duration, music plan, edit plan original), make another version (explore), revise once (interpret revision, edit plan revise), use one AI Idea (director).
6. **Verify (Logs Insights, read-only).** API log group `/aws/apprunner/story-development-api/<service-id>/application`, worker `/aws/lambda/story-development-edit-plan-worker`, last 30 minutes:
   ```
   filter message = "model_call_usage"
   | stats count(*) as attempts, sum(estimated_cost_usd) as usd by task, model_id
   ```
   Pass criteria: a row for each task exercised (`asset_understanding.analyze`, `story_guide.generate_v2`, `story_coverage.v2`, `creative_intent.*`,
   `duration.*`, `music_plan.generate`, `edit_plan.generate`, interpret revision, director); zero rows with `pricing_known=false`;
   `story_user_id` present on every API and worker line; `job_id` present on every worker line;
   ```
   filter message = "model_call_usage" and (strlen(story_user_id) = 0 or @message like /@/)
   | stats count(*)
   ```
   must return 0 (no missing user, no `@` anywhere in any line). Compare one edit-plan job: `sum(estimated_cost_usd)` for its `job_id` must equal the legacy `bedrock_usage` `estimated_cost_usd` within 5%.
7. **Reconcile cost (manual, optional for deploy):** after 7 days, export OpenAI and Google usage for the dev project, compare totals with `sum(estimated_cost_usd)`; record the ratio in the B0 report. Re-run `scripts/billing_unit_economics.py` with measured values.
8. **Rollback:** redeploy the previous master commit with the same workflow (image digest and worker asset only; no data or schema to undo). The new log field is purely additive, so dashboards and the `bedrock_usage` metrics are unaffected either way.
9. **Beta:** a separate approval and the same checklist with `environment=beta` and `-c observability=true -c alarmDestination=alerts@yotale.ai`; confirm the diff has zero destroy lines before deploy.
