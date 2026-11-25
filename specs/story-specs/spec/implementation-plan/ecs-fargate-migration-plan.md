# Migrating the Story API from App Runner to standard ECS Fargate

Status: **PLAN (2026-11-25), owner decisions made; nothing built.** Trigger: production account 854689494157 cannot
create App Runner services (`production-release-readiness.md` section 5).

Owner decisions (Ling, 2026-11-25):
- **Standard ECS Fargate with a CDK-owned Application Load Balancer** (not ECS Express Mode).
- **Dev: replace App Runner directly.** **Beta: time-boxed overlap** of App Runner and ECS. **Production: ECS only.**
- **Production runs two tasks** across two Availability Zones.

## 1. Why standard ECS instead of Express Mode

| | Standard ECS + CDK-owned ALB (chosen) | ECS Express Mode |
|---|---|---|
| Ownership | Our CDK defines cluster, task definition, service, ALB, listener, target group, certificate, security groups, scaling, alarms (`ecs_patterns.ApplicationLoadBalancedFargateService` in CDK 2.160) | AWS creates and manages them from an image and two roles |
| WAF | Associated with our ALB in code from the first deploy | Possible on the managed ALB, but outside the Express API |
| Idle timeout, custom domain, certificate | In code | Managed defaults; changes made directly on managed resources |
| Deployments | Rolling with the ECS deployment circuit breaker and automatic rollback | Canary only, cannot be changed |
| CDK support | Mature L2 constructs in our CDK 2.160 | No construct in 2.160 (raw `AWS::ECS::ExpressGatewayService`) |

Beta already runs WAF (IP reputation and known-bad-inputs in Block; OWASP and rate rules in Count), so the new ALB must
carry the same web ACL before any traffic moves.

## 2. Target design (same construct for dev, beta, production)

- **Image contract unchanged:** the same `apps/api/Dockerfile` image, pinned by digest in the task definition
  (`-c imageDigest`), built by the existing workflows.
- **Task:** 1 vCPU / 2 GB, Linux x86_64, the same size as today's App Runner instance. Container port and `/health`
  health check as today (interval 10 s, timeout 5 s).
- **Task count:** dev 1, beta 1, production **2** (min 2, across two AZs). Auto scaling on CPU, max set per stage.
- **Environment and secrets:** the exact env list App Runner gets today, from one shared array in
  `story-api-stack.ts`, so ECS and the beta App Runner overlap cannot drift.
- **Roles:** task role = today's App Runner instance role permissions; execution role = ECR pull + logs only;
  deploy and cfn-exec roles move from `apprunner:*` to scoped `ecs`, `elasticloadbalancing`, `ec2` (security groups,
  describe), `acm`, `application-autoscaling`, `wafv2:AssociateWebACL`, and `iam:PassRole` for the task and execution
  roles only.
- **Network:** each account's default VPC, public subnets, tasks with public IPs (outbound to OpenAI, Gemini, Unsplash,
  Epidemic). No NAT gateway (it would add about $33/month or more per stage). Task security group accepts traffic
  only from the ALB security group.
- **Load balancer:** internet-facing ALB, HTTPS 443 with an ACM certificate, HTTP 80 redirects to HTTPS.
  **Idle timeout 180 s**, so no request App Runner served today (120 s cap) fails at the ALB, and the iOS client's
  180 s request timeout (`CreativeIntentService.swift`) remains the outer limit.
- **Hostnames:** `api-dev.yotale.ai`, `api-beta.yotale.ai`, `api.yotale.ai`. DNS is at Namecheap: Ling adds the ACM
  validation CNAME and the hostname CNAME to the ALB for each stage. The hostname is stable across any future
  compute change.
- **WAF:** the existing rule set associated with each stage's ALB in code (beta and production), alarms reusing the
  observability SNS topic.
- **Observability:** ALB 5xx, target response time, unhealthy hosts, ECS CPU and memory, deployment failure; replaces
  the App Runner 5xx and latency alarms.
- **Deletion safety:** production keeps termination protection; the ALB and service carry no data.

### Recurring cost (us-east-1, before WAF requests, logs and data transfer)

| Stage | Tasks | Fargate | ALB | Public IPv4 (tasks + ALB, about $3.65 each) | Base per month |
|---|---|---|---|---|---|
| Dev | 1 | $36.04 | $16.43 | about $11 | about $64 |
| Beta | 1 | $36.04 | $16.43 | about $11 | about $64, plus App Runner during the overlap |
| Production | 2 | $72.08 | $16.43 | about $15 | about $104 |

Plus WAF on beta and production: $5 per web ACL, $1 per rule, $0.60 per million requests. Fargate prices: $0.04048
per vCPU-hour and $0.004445 per GB-hour; ALB $0.0225 per hour plus capacity units.

## 3. Release gate changes (`scripts/release_config_gate.py`)

- **Pre-deploy:** read the env from the ECS task definition in the synthesized template (today it reads
  `AWS::AppRunner::Service`). All existing rules, including stage parity, apply unchanged.
- **Post-deploy:** the running task definition's image digest equals the built digest; the service is stable
  (`runningCount == desiredCount`, no deployment in progress); all ALB targets healthy; the live env matches the
  release rules; the expected web ACL is associated with the ALB (beta, production).
- **Beta overlap only:** App Runner's running digest equals the ECS digest.
- Negative tests ported from the App Runner versions, plus new ones for an unhealthy target, a missing web ACL and a
  digest mismatch.

## 4. Verification before any traffic moves (each stage)

Through the ALB hostname with the current iOS client and a test account:
- Device sign-in (Email code, Apple, Google).
- **Slow synchronous model routes**, timed with representative inputs: `/v1/asset-understanding`,
  `/v1/scene-understanding`, `/v1/story-guide-v2`, `/v1/story-guide-refine`, `/v1/edit-plan`, `/v1/edit-plan-mm`,
  `/v1/music-plan`. Report p50 and max; none may return a 504.
- Media upload, async Create and Revise (`/v1/edit-plan-jobs`), account deletion end to end.
- **Rollback drill:** redeploy the previous image digest and confirm the service returns to it.

## 5. Steps

1. **Docs** (this plan).
2. **CDK PR (dev only in effect).** Shared env array; new ECS construct for every stage; App Runner removed for
   development; beta keeps App Runner in the template beside ECS (overlap); production gets ECS only. Roles,
   observability, WAF association, hostname certificate. Tests: synth per stage, env equality between ECS and the
   beta App Runner, no App Runner in development or production, role scope, idle timeout, task counts.
3. **Gate PR** (section 3).
4. **Dev cutover.** Ling adds the `api-dev.yotale.ai` CNAMEs. `cdk diff` must show only the ECS, ALB, certificate and
   role additions and the App Runner removal. Deploy, run section 4, update `Development.xcconfig`, Ling device-tests.
5. **Beta overlap start.** Ling adds the `api-beta.yotale.ai` CNAMEs. Deploy with
   `-c observability=true -c alarmDestination=alerts@yotale.ai`; diff must show only additions. Run section 4 with
   WAF in its current modes. New TestFlight build pointing at `api-beta.yotale.ai`.
6. **Production infrastructure** once beta's backend passes section 4 (it does not wait for testers to update):
   clean up or import the retained resources from the failed App Runner attempt (Ling's go), Ling adds the
   `api.yotale.ai` CNAMEs, first deploy with Ling's SSO admin, section 4 with a test account, then
   `deploy-production.yml` for later deploys.
7. **Apple notification endpoint**, a separate cutover: one URL per App ID, so moving it to
   `https://api.yotale.ai/v1/auth/apple-signin-notifications` stops beta's notifications. Done when production is
   ready to take real users.
8. **Beta overlap end** (one PR removing beta App Runner) when all of these hold: the `api-beta` TestFlight build has
   been available for 14 days; App Runner request count is near zero for 3 consecutive days; Ling has told testers to
   update. Old builds then stop working, which TestFlight expiry (90 days) forces anyway.

Rough effort: 4-6 working days of code and verification, plus Ling's DNS records, device tests and one TestFlight
cycle.

## 6. Retained production resources from the failed attempt

The rolled-back `story-production-api` stack left empty, retained resources: tables `story-production-media`,
`-stories`, `-understanding`, `-account-deletions` and bucket `story-production-media-854689494157-us-east-1`. Before
step 6, re-read their live state (item counts, object counts). If empty: Ling approves turning off the stack's
termination protection, deleting the `ROLLBACK_COMPLETE` stack and these resources, then a clean create. If anything is
not empty: import them into the new stack (`cdk import`) instead.

## 7. Risks

- **Dev ahead of beta for a few days:** dev on ECS while beta still serves from App Runner; parity is restored when
  beta's ECS service is verified.
- **Timeouts:** covered by the 180 s idle timeout and the section 4 timings; a 504 in testing blocks the cutover.
- **Old TestFlight builds:** keep working on App Runner until the overlap ends (step 8).
- **DNS:** each stage needs Ling's Namecheap records before HTTPS works on the hostname.
- **AWS App Runner exception:** if AWS later allows App Runner in 854689494157, the plan does not change; ECS stays.
