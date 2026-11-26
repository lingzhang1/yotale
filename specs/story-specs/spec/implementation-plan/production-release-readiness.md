# Production release readiness and plan

Status: **PRODUCTION BACKEND LIVE (2026-11-26), not yet serving users.** `story-production-api` runs on ECS Fargate in
account 854689494157 (2 tasks, both healthy), post-deploy release gate ACCEPTED. Remaining before launch: DNS for
`api.yotale.ai`, the Apple notification cutover, the iOS Production build, SES production access, the open owner
decisions in section 3, and App Store submission. Owner: Ling.

## 1. Current state

| Area | State | Source |
|---|---|---|
| Accounts | development 989088054552, beta 224033508028, production 854689494157 (`YoTale-Production`, root `prod@yotale.ai`, OU Workloads with the region-lock and protect-security SCPs, CDK bootstrapped, profile `yotale-prod`) | Organizations |
| API compute | ECS Fargate behind a CDK-owned ALB in every stage (`ecs-fargate-migration-plan.md`). Dev: App Runner removed. Beta: ECS plus App Runner (overlap). Production: ECS only, 2 tasks | CloudFormation |
| Hostnames | `api-dev.yotale.ai` (live), `api-beta.yotale.ai`, `api.yotale.ai`; ACM certificates ISSUED in each account; DNS CNAMEs at Namecheap (Ling) | ACM, Namecheap |
| Production deploy | 2026-11-26, master `d7edbeb`, image `git-d7edbebc6d31` (`sha256:f10183454fda…`), first deploy by Ling's SSO admin (the GitHub deploy role is created by this stack). Pre-deploy gate ACCEPTED, diff additions only, post-deploy gate ACCEPTED, 2/2 targets healthy (us-east-1a, us-east-1b), termination protection on | `deploy-production.yml` for later deploys |
| Production checks | `/health` 200 over TLS for `api.yotale.ai`; HTTP 301 to HTTPS; signed-in routes 401 without a token; WAF blocks a Log4j-style probe (403); `/openapi.json` requires sign-in in production | curl through the ALB |
| Production secrets | `YoTale-OpenAI-API-Key`, `YoTale-Gemini-API-Key`: dedicated production keys. `Unsplash-API-Key`, `story-epidemic-key`, `epidemic-mcp-api-key`: same values as dev. `YoTale-Apple-SignIn-Prod` (key F3U2QUUC66), `YoTale-Google-SignIn-Prod` (separate client) | Secrets Manager |
| Apple keys | Two-key team limit: beta key 2J5M246W2G serves beta and dev (dev key J77ZNM2X3V revoked), production key F3U2QUUC66. Both verified against Apple's token endpoint. Rotating a key means revoking one first | Apple Developer |
| Production auth | `story-production-auth`: pool `us-east-1_m9HoNhR7M`, client `4oesvialvc5i8g3cuv1b7vg3to`, Apple + Google, deletion and termination protection. Cognito's default email sender until SES production access | CloudFormation |
| SES | `yotale.ai` verified (DKIM). Production access DENIED pending the case reply (179556209600146, Ling replied 2026-11-26) | SES |
| GitHub `production` Environment | Required reviewer Ling, master only, variables `PROD_DEPLOY_ROLE_ARN`, `CFN_EXEC_ROLE_ARN`, `PROD_COGNITO_USER_POOL_ID`, `PROD_COGNITO_APP_CLIENT_ID` | GitHub |
| Budgets (management account) | `yotale-prod-monthly` $250, `yotale-beta-monthly` $150, each filtered to its own account, alerts at 50/80/100% | AWS Budgets |
| iOS | `Production.xcconfig` (api.yotale.ai, production pool/client, Apple + Google) and `verify_prod_archive.sh` on master; not yet referenced by the Xcode project. `Development.xcconfig` uses `api-dev.yotale.ai` | `apps/ios/Story/Config` |

## 2. Production decisions (owner)

| Date | Decision |
|---|---|
| 2026-11-24 | No stage drift: every stage runs the same planner (5.6, code default) and evidence persistence; the release gate rejects drift (`check_stage_parity`) |
| 2026-11-24 | Account deletion enabled in production (App Store 5.1.1(v); evidence persistence is on) |
| 2026-11-24 | Production account created in the YoTale org, OU Workloads, root `prod@yotale.ai` |
| 2026-11-24 | Unsplash and Epidemic keys shared with dev; OpenAI and Gemini get dedicated production keys (2026-11-25) |
| 2026-11-25 | Dev revokes its Apple key and uses the beta key; production gets its own Apple key |
| 2026-11-25 | API compute: standard ECS Fargate with a CDK-owned ALB in every stage, not ECS Express Mode and not an App Runner exception |
| 2026-11-25 | Dev replaced directly; beta keeps App Runner beside ECS for a time-boxed overlap; production ECS only |
| 2026-11-25 | Production runs two tasks across two Availability Zones |
| 2026-11-26 | AWS budgets: production $250/month, beta $150/month during the overlap (back to $100 after it) |

AWS budgets cover AWS only. OpenAI and Gemini bill directly: set monthly limits in their consoles.

## 3. Open owner decisions

1. **In-app AI limits for production** (`packages/user_quota`, values from `story-api-stack.ts`; production currently
   gets the code defaults). Two kinds of limit apply together:
   - **Per person** (each account): `STORY_QUOTA_USER_MONTHLY_USD` = **$8**/month of model spend,
     `STORY_QUOTA_USER_DAILY_GENS` = **500** AI operations/day, `STORY_QUOTA_MAX_ACTIVE_JOBS` = **2** video jobs at once.
     A YoTale Plus subscriber skips the $ and daily caps (Billing V2) but not the active-job cap.
   - **Across all of production**: `STORY_QUOTA_GLOBAL_MONTHLY_USD` = **$60**/month total model spend (one shared
     `__global__` counter). When it is reached, every user's AI requests get a retryable "busy" answer
     (Retry-After 300 s) until the next calendar month. Plus does not bypass it.
   - Scale (measured, `billing-measured-cost-dev-beta.md`): an edit plan costs about $0.10 and an Asset Understanding
     call about $0.011 per Moment, so one 30-Moment video is roughly $0.40-0.50. $60/month covers about 120-150 such
     videos for everyone together; $8 covers about 16-20 per person.
   - Decide the production global breaker (too low for launch at $60) and whether the per-person values stay. The
     values belong in `release/release.json` (`environments.production`) so the gate enforces them.
2. **Billing at launch:** `off`, or `observe`/`enforce` after the beta grandfather dry run. App Review purchases are
   Sandbox receipts, which production rejects; decide how App Review tests purchases.
3. **Epidemic commercial terms:** `STORY_EPIDEMIC_MODE` is `prototyping` everywhere.
4. **OpenAI and Gemini limits** on the production keys (rate and monthly spend).

## 4. Remaining steps

1. Ling: Namecheap CNAMEs `api-beta` -> `story-beta-api-749453594.us-east-1.elb.amazonaws.com` and `api` ->
   `story-production-api-1453135741.us-east-1.elb.amazonaws.com`.
2. Ling: device test of dev on `api-dev.yotale.ai` (sign-in, a slow Asset Understanding call, upload, Create/Revise,
   account deletion on a test account).
3. Beta: `Beta.xcconfig` to `https://api-beta.yotale.ai`, TestFlight build, then the overlap retirement criteria in
   `ecs-fargate-migration-plan.md` step 8.
4. Production test account: sign-in, one video, account deletion end to end.
5. Apple notification endpoint `https://api.yotale.ai/v1/auth/apple-signin-notifications` when production takes real
   users (one URL per App ID; beta stops receiving notifications).
6. SES: after approval, redeploy production auth with `-c sesFromEmail=no-reply@yotale.ai -c sesAccountId=854689494157`
   and a YoTale code email.
7. iOS: add the Production build configuration and `Story (Production)` scheme in Xcode (Ling; touches
   `project.pbxproj`), Cmd-U, `verify_prod_archive.sh` on the archive.
8. App Store Connect record, metadata, screenshots, privacy labels, review notes with a demo account, subscription
   products; TestFlight; submit.

## 5. Rollback

- Bad build: redeploy the previous image digest through `deploy-production.yml` (rehearsed in dev 2026-11-26: 159 s
  to the previous digest, 143 s back, `/health` 200 throughout).
- Failed ECS deployment: the circuit breaker rolls back automatically.
- Planner: `planner.emergency_override` plus a matching `approved_overrides` entry in one reviewed PR.
- Evidence persistence: `-c evidencePersist=0` with an `approved_degradations` entry.
- Data: never `cdk destroy`; the production stacks have termination protection and the pool has deletion protection.
