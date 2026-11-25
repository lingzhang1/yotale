# Production release readiness and plan

Status: **IN PROGRESS (updated 2026-11-25). Production account, secrets and auth stack are live. The production API
is BLOCKED: App Runner refuses new services in the new account.** Owner: Ling. Each code step lands as its own PR
with owner approval; each "Ling" step needs credentials or a decision only the owner can make.

## 1. Current state

| Area | State | Source |
|---|---|---|
| Environments | development (989088054552), beta (224033508028); production (854689494157) partly provisioned | `deploy-dev.yml`, `deploy-beta.yml` |
| Production account | `YoTale-Production` 854689494157, root `prod@yotale.ai`, OU Workloads (region-lock + protect-security SCPs, same as beta), Ling's SSO user AdministratorAccess, profile `yotale-prod`. CDK bootstrapped (default template, qualifier `hnb659fds`, same as beta) | Organizations, Identity Center |
| Production secrets | `YoTale-OpenAI-API-Key`, `YoTale-Gemini-API-Key`: dedicated production keys (from dev `*-Prod`). `Unsplash-API-Key`, `story-epidemic-key`, `epidemic-mcp-api-key`: copies of dev. `YoTale-Apple-SignIn-Prod` (key F3U2QUUC66, Services ID `com.lingzhang.story.signin.prod`), `YoTale-Google-SignIn-Prod` (separate Google client). `verify-required-secrets.sh production` passes | Secrets Manager |
| Apple keys | Apple allows two Sign in with Apple keys per team. Slots: beta key 2J5M246W2G (now used by beta **and dev**; dev key J77ZNM2X3V revoked), production key F3U2QUUC66. Both verified against Apple's token endpoint. Rotating either key requires revoking one first | Apple Developer, dev Cognito IdP |
| Production auth | `story-production-auth` deployed: pool `us-east-1_m9HoNhR7M`, iOS client `4oesvialvc5i8g3cuv1b7vg3to`, domain `story-production-auth`, Apple + Google IdPs, deletion protection, termination protection. Email codes use Cognito's default sender until SES production access is granted | CloudFormation |
| SES | Identity `yotale.ai` verified (DKIM SUCCESS). Production access request DENIED pending more information (case 179556209600146); reply drafted for Ling | SES |
| Production image | `story-production-api:git-a1fd33f1114b` (`sha256:73e6d31fb662…`), built by the one-time CodeBuild project `story-production-image-build` | ECR |
| Production API | **Failed 2026-11-25:** `CREATE_FAILED AWS::AppRunner::Service: Account 854689494157 can't create new App Runner services`. AWS closed App Runner to new customers on 2026-04-30. Stack `story-production-api` is `ROLLBACK_COMPLETE`; retained empty resources: tables `story-production-media`, `-stories`, `-understanding`, `-account-deletions` and bucket `story-production-media-854689494157-us-east-1` | CloudFormation |
| Code on master | Stage parity (#170), OIDC trust (#84), production deploy role + termination protection (#173), account deletion in production (#174), production auth protections + Apple Services ID (#175) | GitHub |
| Billing | beta `observe`; development, gamma, production `off`. Production accepts only Production Apple receipts | `release/release.json`, `packages/billing/apple.py` |

## 2. Plan, step by step

### Phase 0: land what is ready (DONE)
1. ~~PR #170 stage parity~~ merged `a13717a`.
2. ~~PR #84 OIDC trust~~ merged `f216d1d`.

### Phase 1: production AWS account (DONE except item 7)
3. ~~Account~~ 854689494157.
4. ~~SSO profile~~ `yotale-prod`.
5. ~~Secrets~~ all present, verified by hash and length, never printed.
6. ~~ECR repository~~ `story-production-api` (IMMUTABLE, scan on push). ~~CDK bootstrap~~ done.
7. Ling: confirm OpenAI and Gemini rate limits on the production keys.

### Phase 2: production code
8. ~~Deploy role~~ PR #173 (`97dcde8`).
9. ~~Apple Services ID~~ PR #175 (`a1fd33f`); Services ID created by Ling.
10. ~~Account deletion~~ PR #174 (`69df18f`).
11. ~~Auth stack~~ PR #175; deployed 2026-11-25.
12. **Blocking: replace App Runner.** Decided 2026-11-25: standard ECS Fargate with a CDK-owned ALB in every stage,
    dev replaced directly, beta overlap with App Runner, production ECS only with two tasks
    (`ecs-fargate-migration-plan.md`). Stable hostnames `api-dev`, `api-beta` and `api.yotale.ai`.
13. `deploy-production.yml`: manual dispatch, protected `production` GitHub Environment with a required reviewer,
    confirm token `deploy-production`, digest-pinned image, pre- and post-deploy gate,
    `-c observability=true -c alarmDestination=alerts@yotale.ai`. Written for ECS.
14. WAF and budget. WAF is associated with each stage's ALB in the ECS construct. The org
    budget `yotale-prod-monthly` is not filtered to the production account (it tracks the whole org); scope it.
15. CI gate: add gamma and production to the CI release-gate job.

### Phase 3: owner decisions (Ling)
16. Billing at launch: `off`, or `observe`/`enforce` after the beta grandfather dry run. How App Review tests purchases.
17. Quota numbers for production (`user_monthly_usd`, global breaker).
18. Epidemic commercial terms (`STORY_EPIDEMIC_MODE` is `prototyping` everywhere).
19. SES: Ling pastes the drafted reply into case 179556209600146. After approval, redeploy production auth with
    `-c sesFromEmail=no-reply@yotale.ai -c sesAccountId=854689494157` and a YoTale OTP email template.

### Phase 4: first production API deploy
20. Clean up the rolled-back stack (Ling's go: turn off termination protection, delete `story-production-api` in
    `ROLLBACK_COMPLETE`, delete the empty retained tables and bucket), or import them into the new stack.
21. `cdk diff` against production with the exact pipeline inputs; must be purely additive. First deploy with Ling's SSO
    admin (the GitHub deploy role is created by this stack); later deploys through `deploy-production.yml`.
22. Verify: post-deploy gate, `/health` 200, authenticated routes 401, routes in `openapi.json`, running digest equals
    the ECR digest, account deletion end to end on a test account.
23. Give Ling the Apple notification endpoint `https://api.yotale.ai/v1/auth/apple-signin-notifications`.
    One endpoint per App ID: switching it to production stops beta's Apple notifications.

### Phase 5: iOS and App Store
24. `Production.xcconfig` (`https://api.yotale.ai`, pool `us-east-1_m9HoNhR7M`, client `4oesvialvc5i8g3cuv1b7vg3to`,
    domain prefix `story-production-auth`), a `Story (Production)` scheme and `verify_prod_archive.sh`. The scheme
    touches `project.pbxproj`, so Ling makes that change in Xcode.
25. Ling: Cmd-U and a device run of master against production.
26. Ling: App Store Connect record, metadata, screenshots, privacy labels, review notes with a demo account,
    subscription products.
27. Archive, TestFlight, submit for review.

## 3. Rollback

- Bad build: redeploy the previous image digest through the workflow.
- Planner: `planner.emergency_override` plus a matching `approved_overrides` entry in one reviewed PR.
- Evidence persistence: `-c evidencePersist=0` with an `approved_degradations` entry.
- Data: never `cdk destroy` the data tables; infrastructure rollback never reverses data.

## 4. Critical path

Step 12 (ECS migration, dev then beta) blocks steps 13, 14 and 20-27. In parallel: step 19 (SES reply), steps 16-18 (decisions).

## 5. App Runner blocker

AWS stopped accepting new App Runner customers on 2026-04-30
([availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)). Existing
customers keep full use, which is why development and beta still deploy. The new production account is treated as a new
customer. Decision (Ling, 2026-11-25): move every stage to **standard ECS Fargate with a CDK-owned ALB** (not Express Mode:
WAF, the idle timeout, the certificate and the hostname must be in our code). Dev is replaced directly, beta runs App
Runner and ECS side by side until its retirement criteria are met, production runs ECS only with two tasks. Plan:
`ecs-fargate-migration-plan.md`. An AWS App Runner exception would not change this.
