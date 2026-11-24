# Story — Dev Deployment & Rollback Runbook (Gate 2)

> **STATUS: Gate 2 CLOSED & ACCEPTED (2026-10-18, owner).** This is the accepted single dev deploy
> authority. **Two acceptance cases remain unverified and are accepted as known limitations** (CI/CD
> not to be reopened absent a release-blocking defect):
> 1. A successful *valid-plan* async smoke was NOT independently demonstrated — two attempts ended as
>    clean structured failures (`invalid_after_repair`, `internal`) from non-production-shaped fixtures.
>    The async pipeline (202 → SQS → Lambda → DynamoDB → GET) IS proven end-to-end and the DLQ stayed clean.
> 2. An A→B→A in-flight deployment + rollback was NOT exercised. The worker's `_test_delay_s` hook sleeps
>    *before* `engine.generate()`, so it does NOT bypass Bedrock; a true no-inference in-flight test would
>    require a dev-only worker synthetic short-circuit (out of scope at closure).

The SINGLE authoritative development deployment path. Immutable, keyless, pipeline-controlled.
No production in scope. Dev account `989088054552`, region `us-east-1`.

## Authoritative path (the ONLY way to change the dev service)

1. Merge to `master` (branch-protected, CI required: *Python tests + contract compatibility*, *CDK synth + jest*).
2. Run the **`Deploy (dev)`** GitHub Actions workflow — **manual `workflow_dispatch`**, type `deploy-dev` to confirm.
   - Protected **`development` Environment**, restricted to `master`, concurrency `deploy-development` (no overlap).
   - Keyless **OIDC** → `story-development-github-deploy` (trust: `repo:lingzhang1*/story*:environment:development`).
   - Builds + pushes an **immutable `git-<sha>` image**, captures its **digest**, builds the worker + **sha256**,
     writes the **release manifest**, then `cdk deploy --role-arn <story-development-cfn-exec>`
     `-c imageDigest=<digest>`.
   - App Runner is pinned to `repo@sha256:<digest>` with **AutoDeploymentsEnabled = false**.

CloudFormation is driven through the scoped **`story-development-cfn-exec`** role (NO AdministratorAccess);
the shared CDK bootstrap admin exec role is not used by this path.

## Legacy deployment status (retired as an active authority)

- `buildspec.yml` and `infrastructure/cdk/buildspec.yml` still build/push `:latest`, BUT **App Runner no
  longer tracks `:latest`** (pinned to a digest, auto-deploy off) — a legacy `:latest` push **cannot
  change the active release**. They are left in place only until the pipeline is fully accepted; do not
  use them to deploy.
- **No second deployment authority exists.** Auto-deploy is OFF (verified: `AutoDeploymentsEnabled=false`).

## Emergency rollback (immutable-artifact based)

Rollback restores CODE+CONFIG, never persistent DATA (DynamoDB/S3 are untouched by a rollback).

1. Find the target image digest: `aws ecr describe-images --repository-name story-development-api`
   (images are retained — 63 at time of writing; no lifecycle expiration applied).
2. Re-pin App Runner to the previous digest, through the scoped exec role:
   `cd infrastructure/cdk && cdk deploy -c environment=development -c imageDigest=sha256:<previous> \
     --role-arn arn:aws:iam::989088054552:role/story-development-cfn-exec --require-approval never`
   (or re-run the `Deploy (dev)` workflow from the commit whose image you want).
3. Verify: `aws apprunner describe-service ... ImageIdentifier` == the target digest; `/health` == 200.
4. The worker rolls back with its CDK asset (content-hashed = immutable); a worker rollback is a `cdk
   deploy` of the previous commit's `.worker-asset`.

Previous release manifests are retained as GitHub Actions run artifacts (`release-manifest-<sha>`).

## Verified state (2026-10-18)

- Stack `UPDATE_COMPLETE`. Drift: only `StoryApiService`, and ONLY cosmetic (App Runner reports
  `Memory "2 GB"` vs `"2048"`, `Cpu "1 vCPU"` vs `"1024"` — same values, different units — and omits
  service Tags in drift; a known App Runner drift-detector false positive). **No drift on the image
  digest or auto-deploy.**
- API: `story-development-api@sha256:591e660b…`, `AutoDeploy=false`, `/health` 200.
- Worker: `story-development-edit-plan-worker`, `CodeSha256 8ti9ylbbpuWt9abggqLlvF6q40N2e5sygerRE2O1DdY=`,
  python3.12.
- Async job API live + validating (submit → 422 on bad body = handler ran, no model call; fetch → 404).

## Explicitly NOT done (safeguards 5/6)

- ECR tag mutability unchanged (still MUTABLE — switching to IMMUTABLE deferred until the legacy `:latest`
  pushers are retired, per owner).
- No ECR lifecycle / expiration policy applied — ALL images retained.
