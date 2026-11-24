# Production release readiness and plan

Status: **PLAN (2026-11-24). Nothing deployed to production; no production AWS account exists yet.** Audited against
master after PR #170 (stage parity) and PR #84 (OIDC trust). Owner: Ling. Each code step lands as its own PR with
owner approval; each "Ling" step needs credentials or a decision only the owner can make.

## 1. Current state

| Area | State | Source |
|---|---|---|
| Environments deployed | development (989088054552), beta (224033508028) | `deploy-dev.yml`, `deploy-beta.yml` |
| Production account / profile | **Created 2026-11-24:** `YoTale-Production` 854689494157 (root `prod@yotale.ai`), in OU Workloads (region-lock + protect-security SCPs, same as beta), Ling's SSO user has AdministratorAccess. ECR `story-production-api` created (IMMUTABLE tags, scan on push). Profile `yotale-prod` is added by Ling | Organizations, Identity Center |
| Production deploy workflow | None | `.github/workflows` |
| Production iOS config | None. Only `Development.xcconfig`, `Beta.xcconfig`; schemes `Story`, `Story (Beta)` | `apps/ios/Story/Config` |
| Stage parity | Every stage runs planner 5.6 (code default) with evidence persistence on. `check_stage_parity` rejects drift; a per-stage planner pin needs a time-boxed approval | PR #170, `scripts/release_config_gate.py` |
| Deploy-role trust | Code anchored to `repo:lingzhang1@*/yotale@*:environment:<env>`, matching the live dev and beta roles | PR #84 |
| Account deletion | Implemented: D2 (PR #156), D3 (#160), iOS D5 (#161), beta rollout (#164). The worker deletes the owner's media-table partition (incl. `evidence#` manifests) and `evidence/<uid>/` blobs. Not enabled for production | `packages/account_deletion`, `story-api-stack.ts` `ACCOUNT_DELETION_ENVIRONMENTS` |
| Billing | beta `observe`; development, gamma, production `off`. Production accepts only Production Apple receipts | `release/release.json`, `packages/billing/apple.py` |

## 2. Plan, step by step

### Phase 0: land what is ready
1. Merge PR #170 (stage parity). No behavior change on dev or beta.
2. Merge PR #84 (OIDC trust). Code now equals the live dev/beta roles, so a production role is born with the right trust.

### Phase 1: production AWS account (Ling)
3. ~~Create the production member account~~ DONE: 854689494157, OU Workloads, SSO assignment.
4. Create an SSO profile on Ling's machine (for example `yotale-prod`, via `aws configure sso`).
5. Provision secrets out of band, never through CI or chat: `YoTale-OpenAI-API-Key`, `YoTale-Gemini-API-Key`,
   `Unsplash-API-Key`, `story-epidemic-key`, `epidemic-mcp-api-key`. `scripts/verify-required-secrets.sh production`
   checks presence only and blocks a deploy on any missing key.
6. ~~Create ECR repository `story-production-api`~~ DONE (IMMUTABLE, scan on push).
7. Confirm OpenAI and Gemini rate limits on the production keys fit expected traffic.

### Phase 2: production code (Kiro, one PR each, owner approval)
8. **Deploy role and OIDC provider.** The stack skips them when `environment === "production"` ("production gets a
   separately-reviewed role"). Write that role with least privilege and the PR #84 trust pattern.
9. **Apple Services ID.** `APPLE_SIGNIN_SERVICES_ID` has only development and beta; without a production entry the
   D7 Apple notification route rejects every payload. Ling creates the ID in the Apple Developer portal.
10. **Account deletion.** Add `production` to `ACCOUNT_DELETION_ENVIRONMENTS`. Required by App Store guideline
    5.1.1(v) and because evidence persistence is on in production.
11. **Auth stack.** Production Cognito pool (`-c deployAuth=true`) with Apple and Google federation; Ling creates the
    production Google OAuth client and stores it as a same-account secret (`-c googleSecretName`).
12. **`deploy-production.yml`.** Modeled on `deploy-beta.yml`: manual dispatch, protected `production` GitHub
    Environment with a required reviewer, confirm token `deploy-production`, digest-pinned image, pre- and post-deploy
    gate, `-c observability=true -c alarmDestination=alerts@yotale.ai`.
13. **WAF and budget.** The WAF stack is beta-oriented today; add production WAF and an account budget, either in the
    org-foundation IaC (PR #44) or in this stack, not both.
14. **CI gate.** The CI release-gate job covers development and beta only; add gamma and production.

### Phase 3: owner decisions (Ling)
15. **Billing at launch.** `off` (free, uncapped by billing) or `observe`/`enforce` after the beta grandfather dry run.
    Decide how App Review tests purchases, since production accepts only Production receipts.
16. **Quota numbers.** Production declares no `user_monthly_usd` (CDK default $8) or global breaker; beta's $60
    global breaker is too low for unlimited Plus.
17. **Epidemic.** `STORY_EPIDEMIC_MODE` is `prototyping` in every stage; commercial terms are needed for production.

### Phase 4: first production deploy
18. `cdk diff` against production with the exact pipeline inputs; must be purely additive.
19. Deploy through `deploy-production.yml`; Ling approves the run in the GitHub Environment.
20. Verify: post-deploy gate passes, `/health` 200, authenticated routes 401 (not 404), routes present in
    `openapi.json`, running digest equals the ECR digest, account deletion end to end on a test account.

### Phase 5: iOS and App Store
21. `Production.xcconfig` (production API URL and Cognito ids), a `Story (Production)` scheme and
    `verify_prod_archive.sh` modeled on `scripts/verify_beta_archive.sh`. The scheme touches `project.pbxproj`, so
    Ling makes that change in Xcode.
22. Ling: Cmd-U and a device run of master against production.
23. Ling: App Store Connect app record, metadata, screenshots, privacy labels, review notes with a demo account,
    subscription products.
24. Archive, TestFlight, submit for review.

## 3. Rollback

- Bad build: redeploy the previous image digest through the workflow.
- Planner: `planner.emergency_override` plus a matching `approved_overrides` entry in one reviewed PR.
- Evidence persistence: `-c evidencePersist=0` with an `approved_degradations` entry.
- Data: never `cdk destroy` the data tables; infrastructure rollback never reverses data.

## 4. Critical path

Steps 3 to 6 (Ling) unblock Phase 2 deploy testing. Steps 8, 10, 11 and 12 are the minimum code for a first
production deploy. Steps 15 to 17 must be decided before App Store submission.
