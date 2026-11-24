# P0 Safe CI/CD & Production Release Pipeline — Design

**Status:** DESIGN + PROPOSAL (Phases 0–6). No code changed; NO production resources provisioned;
unpushed history NOT pushed; deployment triggers NOT changed. STOP at owner approval.
**Date:** 2026-10-18
**Objective:** smallest production-grade, repeatable, safe release process before external beta.
Integrates with `mvp-beta-observability-design.md` (release gates) and the auth/quota milestone.

---

## Phase 0 — Audit (actual state)

| Area | Finding |
|---|---|
| CI | **NONE** — no `.github/workflows`, no GitHub Actions, no CodePipeline. All deploys are MANUAL. |
| Backend deploy | Manual: CodeBuild `story-rb-caseg-build` → ECR `story-<env>-api:latest` → `apprunner start-deployment`. |
| App Runner trigger | **`autoDeploymentsEnabled: true` on `:latest`** → App Runner auto-redeploys on every `:latest` push (no approval gate). |
| Artifact versioning | **NONE** — image is overwritten `:latest` (`fromRepositoryName` + `:latest`). No immutable, commit-pinned tag. (Known stale-digest hazard.) |
| Rollback | **NONE** — rolling back = rebuild the old commit. No tagged previous image, no CDK state rollback plan. |
| Worker packaging | Docker-free `lambda.Code.fromAsset(.worker-asset)` built by `scripts/build_worker_asset.sh` (Python 3.12, handler `app.worker.handler`, pydantic manylinux wheels; boto3 from runtime). |
| Dev/prod account separation | **NONE in code** — CDK uses `CDK_DEFAULT_ACCOUNT`/`REGION` + an `environment` context; everything has run in ONE account `989088054552`. |
| Git branch protection | Cannot verify locally (GitHub server setting) — **owner must confirm**. `master` is **227 commits ahead of upstream (unpushed)**; current branch `fix/p0-recover-jobs-explore-latency`. |
| Build/test automation | Tests exist (pytest packages/contracts; CDK jest; Swift device-only) but are **run manually**, not gated. |
| Secrets / IAM | Secrets Manager least-privilege reads already in CDK; deploy identity = broad `Admin` user (no scoped deploy role, no OIDC). |
| API/worker schema compat | Shared contracts in `contracts/` + versioned job payloads (`edit_plan_jobs`, EditPlan/2); worker + api built from the SAME source tree so they currently ship together. |
| Feature flags | Env-var flags exist (`STORY_JOBS_API_ENABLED`, `STORY_EPIDEMIC_MODE`, `STORY_MUSIC_PROVIDER`, `STORY_EDIT_PLAN_VERSION`) — process-env, not a flag service. |

**Headline:** greenfield pipeline — no CI, no immutable artifacts, no rollback, no release approval, one
account, and App Runner currently AUTO-deploys `:latest`. These are the gaps to close for beta.

## Phase 1 — CI/CD architecture: GitHub Actions + CDK vs CodePipeline

**Recommendation: GitHub Actions + CDK.** At Story's scale (one service + one Lambda + one stack),
CodePipeline/CodeBuild/CodeDeploy is more moving infrastructure to own than it saves. GH Actions keeps CI
next to the code, is cheaper to operate, and CDK already defines the infra.

- **OIDC, not access keys:** two GitHub→AWS OIDC roles (`story-deploy-dev`, `story-deploy-prod`), short-
  lived creds, no persistent keys in GitHub. Dev role scoped to the dev account/stack; prod role scoped to
  the prod account/stack — **separate permissions** (amendment: dev/prod split).
- **Pipeline shape:** PR → lint + unit tests (pytest + CDK jest) must pass. Merge to `main` → build an
  **immutable, commit-SHA-tagged** image (`:git-<sha>`), push to ECR, `cdk deploy` to **dev**, run smoke
  tests. **Production is a MANUAL approval** (GH Environments protection) → deploy the SAME SHA-tagged
  artifact to prod → post-deploy CloudWatch health check.
- Drop `:latest` auto-deploy; deploy by digest/SHA tag so a deploy is reproducible and rollback = redeploy
  the previous SHA.

## Phase 2 — Component release/rollback

1. **App Runner FastAPI:** build `:git-<sha>`, `update-service` to that tag + `start-deployment`; verify
   RUNNING + `/health` + a probe endpoint (lesson: CodeBuild SUCCESS ≠ live). **Rollback = redeploy the
   previous SHA tag** (kept in ECR; set a lifecycle policy to retain the last N). **Turn OFF
   `autoDeploymentsEnabled` for prod** so a push can't silently release.
2. **Lambda async worker:** `build_worker_asset.sh` → `cdk deploy` publishes a new version. **Lambda
   CodeDeploy aliases: NOT worth it here** — they provide canary/linear shift for SYNCHRONOUS traffic;
   our worker is SQS-driven (async, idempotent, retried via DLQ). A bad version is caught by the
   DLQ/alarm, and rollback = redeploy the previous asset. No canary infra (per owner's "no canary without
   concrete benefit"). Keep it a plain versioned function.
3. **CDK infrastructure:** `cdk diff` in CI on every PR (surface infra changes for review); `cdk deploy`
   dev automatically, prod behind approval. Rollback = redeploy the prior CDK revision — **but see
   Phase 3: infra rollback does NOT reverse data**.
4. **AI prompt/model config:** prompts ship IN the image/asset (versioned dirs e.g. `edit_plan/5.x`) +
   env flag `STORY_EDIT_PLAN_VERSION`. A prompt change is a normal SHA-tagged release; a fast "flip
   back" is the env flag (no rebuild). Verify live `prompt_version` with the dot-tolerant grep (lesson).
5. **iOS:** separate track — Xcode Cloud or `fastlane` → TestFlight (beta) → App Store. Build-number
   bumped per release; rollback = ship a new build (App Store cannot un-release). Keep it decoupled from
   the backend pipeline; the API must stay backward-compatible for installed clients (Phase 3).

## Phase 3 — Compatibility & safe rollout

- **API/worker compatibility:** today they ship from one tree. Rule: a deploy must tolerate an in-flight
  job enqueued by the PREVIOUS version → **versioned job payloads** (payload carries a schema version;
  worker handles current + previous). Additive-only payload changes within a beta; a breaking change is a
  new payload version with dual-read.
- **Deployment order:** deploy the WORKER first (can read old+new payloads), then the API (starts
  emitting new payloads) — never the reverse, or a new payload hits an old worker.
- **Long-running jobs during deploy:** SQS + Lambda — in-flight messages are picked up by the new version
  on next poll; a message mid-flight is retried (visibility timeout) so no job is lost. The idempotency
  key (payload fingerprint / operation_id) prevents a **duplicate inference** on retry across the deploy.
- **Additive DynamoDB only:** new attributes optional/defaulted (same discipline as the SwiftData models);
  never a destructive migration in a release.
- **Feature-flag rollout:** env-flag flips are instant and reversible (no rebuild); a risky flag defaults
  OFF and is flipped after the deploy is healthy.
- **Rollback boundaries (critical):** **infrastructure rollback NEVER reverses persistent data.** A
  redeploy of an older image does NOT undo DynamoDB writes, S3 objects, or completed jobs. So: schema
  changes stay additive + forward-compatible; a rollback restores CODE, not DATA. In-flight jobs are
  preserved by SQS, not by the deploy.

## Phase 4 — CloudWatch release gates (integrates with observability milestone)

**Pre-deploy smoke:** `/health` 200; a probe POST returns 422 (handler present, not 404/405); live
`prompt_version` matches the shipped one; DLQ empty.
**Post-deploy (watch window ~10–15 min):** API 5xx, GenerationFailed rate, SQS backlog + DLQ depth,
Lambda Errors/timeouts, Bedrock throttling, JobCompletionLatency, auth/quota errors.

| Gate | On breach |
|---|---|
| `/health` fail / 5xx spike post-deploy | **AUTO-HALT / auto-rollback** to previous SHA |
| DLQ non-empty appearing right after deploy | **AUTO-HALT** (likely a poison payload from the new version) |
| Lambda error/timeout surge | **AUTO-HALT / rollback** |
| GenerationFailed% over threshold (min-sample guarded) | **MANUAL** (could be upstream Bedrock, not the release) |
| Bedrock sustained throttling | **MANUAL** (shared-quota, not necessarily the release) |
| JobCompletionLatency regression | **MANUAL** (investigate, not auto-revert) |
| Auth/quota error anomaly | **MANUAL** |

Auto-rollback is limited to unambiguous release-caused signals (health/5xx/DLQ/Lambda); ambiguous
signals page a human.

## Phase 5 — App Runner lifecycle

AWS announced App Runner's wind-down. **Recommendation: STAY on App Runner for beta.** It works today,
migration is out of scope for this milestone (owner), and a beta should not absorb an ECS migration now.
**Mitigation = keep the container artifact PORTABLE:** the service is a plain Dockerfile image in ECR
with no App-Runner-specific coupling, so a later move to ECS Fargate / App Runner successor is a
deploy-target change, not a rebuild. Track the deprecation date; schedule the ECS migration as a
POST-beta milestone. Do not migrate here.

## Phase 6 — Implementation plan

1. **Recommended stack:** GitHub Actions (CI + deploy) + CDK (infra) + ECR SHA-tagged images + OIDC roles
   (dev/prod split) + GH Environments manual prod approval + CloudWatch release gates. No CodePipeline, no
   Lambda CodeDeploy, no canary.
2. **Architecture (text diagram):**
   `PR → GH Actions [lint+pytest+cdk jest+cdk diff] → merge main → build :git-<sha> → ECR → deploy DEV (cdk) → dev smoke → MANUAL APPROVAL → deploy PROD same sha → post-deploy CloudWatch gate → (auto-rollback on health/5xx/DLQ)`. iOS: `tag → fastlane/Xcode Cloud → TestFlight → App Store` (separate).
3. **Workflows + IAM:** `ci.yml` (PR tests), `deploy-dev.yml` (on main), `deploy-prod.yml` (manual/tag);
   OIDC roles `story-deploy-dev` (dev acct/stack) + `story-deploy-prod` (prod acct/stack), each scoped to
   ECR push + the one CDK stack + `start-deployment`; no long-lived keys.
4. **CDK changes:** turn OFF `autoDeploymentsEnabled` for prod; deploy by SHA tag not `:latest`; ECR
   lifecycle policy (retain last N images for rollback); the GH OIDC provider + two deploy roles; (prod
   account/env wiring when the prod account exists).
5. **Estimated effort:** CI workflows + OIDC roles ≈ **2 days**; SHA-tagged build + dev deploy + smoke
   ≈ **1.5 days**; prod approval + post-deploy gate + auto-rollback wiring ≈ **2 days**; versioned-payload
   + deploy-order discipline ≈ **1 day**; iOS fastlane/TestFlight ≈ **1–1.5 days**. **Total ≈ 7–8 engineering
   days.** (Prod half blocked on the prod account existing.)
6. **Release procedure:** merge → auto dev deploy + smoke → review dashboards → approve prod → SHA
   deploy → 10–15 min watch → mark released.
7. **Rollback procedure:** redeploy previous SHA tag (App Runner/Lambda) via a one-click re-run; env-flag
   flip for a prompt/feature; **data is never rolled back** — forward-fix additive schema issues.
8. **Acceptance tests:** PR with a failing test is blocked; dev deploy runs + smoke passes; a bad image
   auto-rolls-back on health gate (dev fault injection); a versioned-payload job enqueued pre-deploy
   completes on the new worker without duplicate inference; prod approval truly gates.
9. **Remaining production risks:** no prod account yet (dev-only today); branch protection on `master`
   unverified; the 227 unpushed commits must be pushed before any CI can run (owner decision); App Runner
   deprecation (mitigated, tracked); iOS release cadence is manual/App-Store-bound.

## Dependencies / decisions for the owner
- **Prod AWS account** (id + OIDC trust) — prod half can't be built without it.
- **Push `master` (227 commits)** + enable **branch protection** — CI is meaningless on an unpushed,
  unprotected branch. (Owner-gated; I will not push.)
- Confirm GitHub is the git host (OIDC assumes GitHub Actions).

## Decision gate

STOP after this proposal + estimate. No production resources provisioned, unpushed history not pushed,
deployment triggers unchanged. No unrelated infra redesign.
