# Milestone — Async Edit Planning + Production Rollout Plan

Status: **Backend+iOS done & accepted on DEV. Production rollout ON HOLD — awaiting owner's prod account id/profile and explicit deploy authorization.**
Owner: lingzhang · Date: 2026-10-13 · Repo: Workplace/story (app) + specs/story-specs (this doc)

> This doc satisfies two owner rules at once: (1) the async milestone needed a committed
> implementation-plan doc; (2) a production deploy is a design/scope change that must be
> written down and registered before it happens. **Nothing in here has been deployed to
> production.** The dev environment (account `989088054552`, us-east-1) is unchanged by this doc.

---

## 1. What shipped (DEV only, accepted)

**Durable async Edit Planning** — removes App Runner's ~120s HTTP ceiling (which caused 502s on
long multimodal+critique plans). The backend returns a job id instantly; a Lambda worker runs the
SAME frozen plan→critique→validate core (edit_plan/5.2) for up to 15 min.

- Backend Phase 1: job store (`packages/edit_plan_jobs`), endpoints `POST/GET /v1/edit-plan-jobs[/{id}]`,
  `.../cancel`, `.../_reconcile` in `apps/api/app/main.py` (dev-gated by `STORY_JOBS_API_ENABLED`),
  Lambda worker `apps/api/app/worker.py`. 186 backend + 7 CDK tests pass.
- Infra (CDK, environment-parameterized): DynamoDB `story-<env>-edit-plan-jobs`, SQS+DLQ,
  S3 `story-<env>-edit-plan-staging-<account>-<region>`, Lambda `story-<env>-edit-plan-worker`
  (900s/2GB/reserved-conc 2), EventBridge 1-min reconcile, scoped IAM, App Runner env wiring.
- iOS Phase 2: `EditPlanJobClient` (submit/poll/cancel), coordinator rewired sync→async with
  idempotency+recovery, honest Creating-screen UX (patience layer + real backend-status sub-line).

**Dev acceptance PASSED live:** text-only, multimodal+critique (32 sheets), 180s(~193s) & 300s(~311s)
jobs past the 120s ceiling, idempotency, 409 conflict, running-job cancel→cancelled, staging cleanup,
reconcile tick, device recovery cases.

## 2. iOS "defaults" state (the 2026-10-13 flag-flip request)

The owner asked to "flip async creation ON by default (iOS only, no backend prod deploy)." Audit found
**nothing left to flip** — the intended default state is already shipped:

| Toggle | Mechanism | Default | Action |
|---|---|---|---|
| Async creation path | None — the sync `EditPlannerService` path is no longer reachable from creation; `EditPlanJobClient` is the sole path | always async | already done |
| Multimodal planning | `StoryMultimodalPlanning.enabled` (`_enabledDefault = true`; kill-switch via env/UserDefaults) | **ON** | already done |
| Editing approach | `EditingApproach` default | **visual_first** | already done |
| Critique/revision | `StoryMultimodalPlanning.critiqueRevisionEnabled` | **ON** (2026-10-13, owner "best results") | flipped ON — Arm D is the largest quality lever; kill-switch `STORY_CRITIQUE_REVISION=0`. Tradeoff: 2 extra model calls re-sending ~3MB images, quota-fragile → more Sonnet fallback under the Opus daily cap |
| Post-plan refinement | `StoryCreativeRefinement.enabled` | **ON** (2026-10-13, owner "best results") | flipped ON — deterministic pre-pass, no-op when nothing to improve; gained a kill-switch `STORY_CREATIVE_REFINEMENT=0` |

So the flag-flip request required **no code change**. The device screenshots showing `critique=true`
were a per-device UserDefaults override; as of app `5126b08` critique + refinement are the shipping default.

### Product decision (owner, 2026-10-13): full quality ON for Visual-first in production
The Customize screen already makes the user choose the path explicitly:
- **Storytelling** → text-only (`/v1/edit-plan`), cheap, 1 model call, no images.
- **Visual-first** → the full premium path (multimodal + critique/revision + refinement), ~3 model calls
  each carrying the contact sheets.
Decision: ship Visual-first with everything ON in production. The user opts into the premium path, so if
the output quality justifies the cost, that is a tradeoff the customer is choosing. No code change needed.

**Honest caveat (capacity, not billing):** "the customer pays for the quota" is a product INTENT, not a
current mechanism. There is NO per-customer token metering or billing passthrough today — every create
draws on the single shared Bedrock daily token quota of the Story AWS account. So a burst of Visual-first
+ critique creates drains the ACCOUNT-WIDE Opus daily cap, and once exhausted the fallback (Sonnet, then
`provider_exhausted`) affects ALL users, including cheap Storytelling creates. Treat prod Opus quota
headroom as a launch-blocking capacity item (see Preconditions). If/when real per-user cost control is
wanted, that is a separate billing/metering milestone, not part of this rollout.

## 3. Production rollout plan (HOLD — do not execute without owner go)

### Blockers (owner-only)
1. **Prod AWS account id + profile** — all work so far is dev `989088054552`. Owner will provide.
2. **Explicit deploy authorization** — crosses the standing "dev only / never deploy publicly" rule.
3. **Git push decision** — prod deploys normally go through a pushed branch/CI; pushing is blocked by
   default. Owner chose "Hold — prepare & show the plan" (this doc). No branch pushed.

### Preconditions to verify before prod
- Bedrock model access (Opus 4.6 primary + Sonnet 4.6 fallback) enabled in the prod account/region.
- **Bedrock daily token quota** in prod sized for real traffic — the Opus per-day cap is what triggers
  the Opus→Sonnet fallback on dev. A prod cap too low means most creates silently run on Sonnet.
- Secrets present in prod Secrets Manager: `story-epidemic-key` (REST) and, if MCP music is used,
  `epidemic-mcp-api-key`. The instance-role policy must grant `GetSecretValue` on BOTH (dev drifted here
  once; the CDK `EpidemicKeyRead` statement now name-scopes both — re-verify in prod).
- CodeBuild project + ECR repo + source bucket provisioned for the prod account (dev uses
  `story-rb-caseg-build` → `s3://story-codebuild-src-989088054552-.../rb-caseg/source.zip`).

### Steps (once authorized, per environment=production)
1. `cd infrastructure/cdk && TMPDIR=/tmp CDK_HOME=/tmp/cdkhome npx tsc` (lib/*.js is gitignored+stale — always compile first).
2. `CDK_DEFAULT_ACCOUNT=<PROD_ACCT> CDK_DEFAULT_REGION=us-east-1 AWS_PROFILE=<prod> npx cdk deploy --context environment=production --require-approval never`
   → synthesizes `story-production-*` (DynamoDB/SQS/S3/Lambda/EventBridge/App Runner) in the prod account.
3. Build the backend image via the prod CodeBuild (source zip MUST contain `buildspec.yml` using `$ECR_URI`
   AND the `prompts/` dir), wait SUCCEEDED, then `aws apprunner start-deployment`.
4. **Set the FULL App Runner env set** (runtimeEnvironmentVariables is a FULL REPLACE — omitting one drops it):
   `STORY_JOBS_API_ENABLED=1`, `STORY_JOBS_TABLE`, `STORY_JOBS_QUEUE_URL`, `STORY_STAGING_BUCKET`,
   `STORY_EPIDEMIC_MODE=prototyping`, `STORY_MUSIC_PROVIDER=mcp` (or unset for REST), `STORY_EDIT_PLAN_VERSION=5.2`,
   `STORY_LLM_FALLBACK_MODEL=us.anthropic.claude-sonnet-4-6`.
5. Verify: `/openapi.json` has the job routes, `/health` 200, a real `POST /v1/edit-plan-jobs` completes,
   `/v1/music/candidates` returns tracks (not 404 → provider env is live).
6. Point the iOS prod build's API base URL at the prod App Runner URL (keep dev build on dev URL).

### Rollback
- Backend: `aws apprunner start-deployment` against the prior ECR image tag (image deploys are revertible);
  env regressions revert by re-running step 4 with the known-good full set.
- Infra: `cdk deploy` is idempotent; a bad change reverts by redeploying the prior stack revision.
  Do NOT `cdk destroy` the prod data table (DynamoDB holds live jobs).
- iOS: ship a build pointing back at the prior backend, or use the `STORY_MULTIMODAL_PLANNING=0`
  kill-switch to force text-only if multimodal misbehaves in prod.

### Risks
- Opus daily quota in prod → silent Sonnet fallback (gateway swallows the error reason; see §4).
- Music provider env missing → `/v1/music/candidates` 404 → "created without music" (the dev regression
  this workstream already hit and fixed).
- Reserved concurrency 2 on the worker — size for prod load before launch.

## 4. Known gap (diagnosability)
`FallbackModelGateway` catches ANY `ProviderError` and stores `last_error` but does NOT log it, so logs
cannot distinguish "Opus daily cap" from another provider error. Recommend adding one log line of
`last_error` when `last_fallback` flips true, so prod fallback cause is visible in CloudWatch. (Not yet done.)
