# Migrating the Story API from App Runner to ECS Express Mode

Status: **PLAN (2026-11-25), awaiting Ling's decision.** Nothing built. Trigger: production account 854689494157
cannot create App Runner services (`production-release-readiness.md` section 5).

## 1. ECS Express Mode vs a normal ECS service

Both run the same container on Fargate inside an ECS cluster. The difference is who designs the surrounding
infrastructure.

| | ECS Express Mode | Normal ECS service (Fargate + ALB) |
|---|---|---|
| What you provide | Image, task execution role, infrastructure role; optionally CPU/memory, port, health path, env, scaling limits, subnets | Cluster, task definition, service, ALB, listener, target group, ACM certificate, security groups, scaling policy, log group, alarms |
| What AWS creates | All of the right-hand column, plus an HTTPS URL on `*.ecs.<region>.on.aws` and a deployment alarm ([resources created](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-work.html)) | Nothing; you define it (CDK `ecs_patterns.ApplicationLoadBalancedFargateService` does most of it in one construct) |
| Deployments | Canary, fixed (cannot be changed) | Rolling, blue/green or canary, your choice |
| Load balancer | Managed and shared by up to 25 Express services per VPC; its configuration cannot be changed through Express Mode | Your own ALB; any rules, timeouts, WAF, custom domain |
| CloudFormation | `AWS::ECS::ExpressGatewayService` (new resource; our CDK lib 2.160 has no construct, so a raw `CfnResource` or a CDK upgrade) | Mature L2 constructs in CDK 2.160 |
| Closest to App Runner | Yes; AWS recommends it to non-customers in the App Runner docs | No, more to own |

Cost for either (one always-on 1 vCPU / 2 GB task, the same size as today's App Runner instance): Fargate about
$36/month plus an ALB about $16-20/month per environment, versus App Runner's provisioned plus active instance pricing
today. Neither scales to zero.

**Recommendation: Express Mode**, because it keeps App Runner's "hand it an image" model and the least
infrastructure to own. The fixed canary deployment and fixed ALB are acceptable for this service. If WAF on the ALB
or a custom domain such as `api.yotale.ai` becomes a requirement Express Mode cannot meet, the same task definition
moves to a normal ECS service later.

## 2. What changes in the code (inventory)

| Area | Today (App Runner) | Change |
|---|---|---|
| `infrastructure/cdk/lib/story-api-stack.ts` | `apprunner.CfnService`, ECR access role, instance role (`tasks.apprunner.amazonaws.com`), env list, health check, `ServiceUrl` output | Express service (raw `CfnResource`) with a task definition carrying the same env list, task role = today's instance role permissions, execution role, infrastructure role; `ServiceUrl` output becomes the Express URL |
| Deploy role / cfn-exec role | `apprunner:*` actions scoped to `story-<env>-api` | `ecs:*` on the cluster/service, `elasticloadbalancing:*`, `ec2` security-group and describe actions, `acm`, `application-autoscaling`, `iam:PassRole` for the three ECS roles |
| `infrastructure/cdk/lib/observability.ts` | App Runner 5xx / latency metrics | ALB `HTTPCode_Target_5XX_Count`, `TargetResponseTime`, ECS CPU/memory |
| `infrastructure/cdk/lib/story-beta-waf-stack.ts` | Associates WAF with the App Runner ARN | Associate with the Express ALB (read from the service), or keep WAF off until a normal ECS service if Express does not allow it |
| `scripts/release_config_gate.py` | Pre-deploy reads `AWS::AppRunner::Service` env from the template; post-deploy calls `apprunner describe-service` | Read the task definition env from the template; post-deploy reads `ecs describe-services` and the running task definition (image digest, env) |
| `deploy-dev.yml`, `deploy-beta.yml` | Image by digest into App Runner | Same image by digest into the task definition; no other change |
| iOS `Development.xcconfig`, `Beta.xcconfig`, `StoryEnvironment.swift`, `StoryEnvironmentTests.swift`, `scripts/verify_beta_archive.sh` | `*.awsapprunner.com` hosts | New Express URLs; TestFlight builds already in testers' hands keep calling the old host until they update |
| Apple notification endpoint | Beta App Runner URL | New beta (later production) URL |
| Request limits | App Runner ~120 s request cap (long work is already async via the Lambda worker) | ALB idle timeout 60 s by default; confirm no synchronous route needs more, or raise it |
| Networking | App Runner public egress, no VPC | Default VPC public subnets, tasks with public IPs (Express default). Production account has a default VPC (`vpc-01256f32872aeef61`) |

Unchanged: DynamoDB, S3, SQS, the Lambda worker, Cognito, account deletion, secrets, the image itself.

## 3. Migration steps (dev, then beta, then production)

Each step is its own PR or operation with Ling's approval; the old App Runner service keeps serving until its
replacement is verified.

1. **Spike in dev (1 day).** Create one Express service by hand from the current dev image with the dev env, check
   `/health`, an authenticated call, an async job, media upload, and the ALB timeout. Delete it after. Settles the
   CloudFormation shape and whether WAF can attach.
2. **CDK change (1-2 days).** Replace `CfnService` with the Express service in `story-api-stack.ts` for every
   environment, with the IAM, observability and WAF changes above. Tests: synth per environment, env-list equality
   with today's App Runner list, no App Runner resource left, deploy-role scope.
3. **Gate change (1 day).** `release_config_gate.py` pre and post read ECS; negative tests ported.
4. **Dev cutover.** `cdk diff` must show only: add the Express service and its roles, remove the App Runner service
   and its two roles. Deploy dev, verify, update `Development.xcconfig`, Ling device-tests.
5. **Beta cutover.** Same diff rule with `-c observability=true -c alarmDestination=alerts@yotale.ai`. Keep the old
   beta App Runner URL alive until a TestFlight build with the new URL is out: deploy the Express service first in one
   release, remove App Runner in the next. Move the Apple notification endpoint to the new beta URL.
6. **Production first deploy.** Clean up the rolled-back stack (Ling's go), then deploy production on Express Mode
   (readiness plan Phase 4), then give Ling the production Apple notification endpoint.
7. **Docs.** Runbook and architecture doc updates; delete the App Runner deploy notes.

Rough effort: 4-6 working days of code and verification, plus Ling's device tests and a TestFlight cycle for beta.

## 4. Risks

- **Mixed stages during the move:** dev on ECS while beta is still on App Runner for a few days. Acceptable only
  while the migration is in flight; the stage-parity rule is restored when beta and production land.
- **Old TestFlight builds:** they point at the App Runner host; removing beta App Runner too early breaks them.
- **Express Mode limits:** canary deployment and ALB settings are fixed; if that blocks WAF or timeouts, use a
  normal ECS service with the same task definition.
- **CDK support:** no L2 construct in CDK 2.160; a raw resource avoids a library upgrade that would touch every stack.

## 5. Alternative kept open

An AWS Support request to allow App Runner for 854689494157 needs no code. If AWS grants it before step 2 lands,
Ling can choose to pause this migration.
