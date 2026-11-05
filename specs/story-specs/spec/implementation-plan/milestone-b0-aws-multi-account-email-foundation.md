# YoTale B0 — AWS Multi-Account & Official Email Foundation (PLAN + AUDIT)

**Status:** PLAN / PROPOSAL — read-only audit complete. NOTHING provisioned, NO DNS changed, NO account
created, NO mailbox created, NO beta deployed. STOP at owner approval. Date: 2026-10-21. Domain: `yotale.ai`
(Namecheap). Account under audit: `989088054552`.

---

## Phase 0 — Read-only audit (verified facts)

### Accounts & Organization
- The current dev account **`989088054552` IS ALREADY an Organization MANAGEMENT (master) account** —
  org `o-hwquoahv3t`, FeatureSet **ALL**, master email **`dearlingzhang@gmail.com`**, SCPs ENABLED.
- The org is **flat**: **no OUs**, only the AWS-managed `FullAWSAccess` SCP (no custom guardrails).
- It is the **ONLY account** in the org (no beta/gamma/prod exist yet).
- **IAM Identity Center is ACTIVE** (instance `ssoins-72234f2ceb354089`, identity store `d-906627f3b6`) in
  this account — a centralized-access foundation already exists.
- **This management account also runs WORKLOADS for MULTIPLE projects** — not only Story
  (`story-development-*`) but a second app `ainigama-backend-dev-*` (its own DynamoDB tables + Cognito user
  pool `us-east-1_s7Sb0KzOc`). This is the anti-pattern the owner flagged: the management account hosts
  application workloads, and two unrelated projects share one account.

### Dev resources (Story, us-east-1)
- DynamoDB: `story-development-stories`, `story-development-understanding`, `story-development-media`,
  `story-development-edit-plan-jobs`, identity/claims/users tables.
- S3: `story-development-media-…`, `story-development-edit-plan-staging-…`, `story-codebuild-src-…`,
  `story-assetunderstanding-exp-…`.
- Lambda: `story-development-edit-plan-worker` (+ CDK custom-resource lambdas). App Runner
  `story-development-api`. SQS `…-edit-plan-jobs` + `…-edit-plan-jobs-dlq`. Cognito `us-east-1_AzfHOEdA5`.

### Email — DNS & SES (authoritative via live `dig` + SES API)
- **Nameservers: `dns1/dns2.registrar-servers.com`** → DNS is **Namecheap BasicDNS** (NOT Route 53). All DNS
  changes happen in the Namecheap dashboard.
- **SES SENDING is fully working and MUST be preserved:**
  - `yotale.ai` domain identity **verified**, **SendingEnabled**.
  - **DKIM Success** — 3 CNAMEs confirmed LIVE in Namecheap
    (`{qlfked64…,kmlu75uj…,nljlpzwc…}._domainkey.yotale.ai` → `*.dkim.amazonses.com`).
  - **Custom MAIL FROM `mail.yotale.ai` Success** — live `MX 10 feedback-smtp.us-east-1.amazonses.com` +
    `TXT v=spf1 include:amazonses.com ~all` on that subdomain.
  - **Cognito OTP send policy** bound to user pool `us-east-1_AzfHOEdA5` (`AllowCognitoToSendFromYoTaleIdentity`).
  - **DMARC present at apex:** `_dmarc.yotale.ai TXT v=DMARC1; p=none`.
- **THE GAP (what blocks account registration):** the **apex `yotale.ai` has NO MX record and no apex SPF**,
  so **inbound mail to any `@yotale.ai` address is NOT received anywhere today** — every proposed address
  (aws@, beta@, …) would currently **bounce**. This is exactly what must be fixed + verified BEFORE creating
  any AWS account (AWS sends verification/recovery mail to the registration address).

### Deployment pipeline & release artifacts (already sanctioned)
- `.github/workflows/deploy-dev.yml`: **keyless GitHub OIDC** (`DEV_DEPLOY_ROLE_ARN`), protected
  `development` GitHub Environment, manual-dispatch only, concurrency-guarded, **dev account only**.
- **Immutable artifacts are ALREADY the release authority:** API image tagged `git-<sha>` and **deployed by
  DIGEST** (`cdk deploy -c imageDigest=…`); worker built by `scripts/build_worker_asset.sh` into a hashed
  zip; a release manifest is written per deploy. CFN driven through a **scoped cfn-exec role**
  (`CFN_EXEC_ROLE_ARN`), not admin. → The owner's "no mutable `:latest` as release authority" is **already
  satisfied by the sanctioned path**; the `:latest`/CodeBuild route used for dev iteration is the documented
  out-of-band deviation, NOT the beta release path.
- CDK is **already environment-parameterized**: `bin/app.ts` reads `-c environment=` and
  `CDK_DEFAULT_ACCOUNT/REGION`; the auth stack is gated behind `-c deployAuth=true`. Beta/gamma/prod are a
  matter of context + a target account + a bootstrapped OIDC/exec role — not a rewrite.

---

## Phase 1 — Email-receiving proposal (smallest reliable setup)

**Recommendation: Namecheap Email Forwarding for inbound**, because (a) DNS already lives at Namecheap, (b) it
is free with the domain, (c) it adds ONLY an apex `MX` + does not touch any SES sending record, and (d) it
forwards AWS registration/verification/security/recovery mail to a mailbox the owner already controls. SES
*receipt* (the heavier alternative) is unnecessary for a handful of account addresses and would require
Route 53 or careful MX coexistence. Revisit SES-receipt/Workmail only if shared team inboxes are needed later.

### Exact DNS changes to make in Namecheap (apply only after approval — SHOWN, not applied)

PROCEDURE: in Namecheap → Domain List → Manage `yotale.ai` → **Advanced DNS → Mail Settings**, select
**"Email Forwarding"**. Namecheap then writes the MX records **AUTOMATICALLY** — you do NOT hand-enter MX
values. (Confirmed against Namecheap's official article + live DNS.) The auto-written records are:
```
Type  Host  Value                              Priority  TTL        (VERIFIED LIVE 2026-10-21)
MX    @     eforward1.registrar-servers.com    10        Automatic
MX    @     eforward2.registrar-servers.com    10        Automatic
MX    @     eforward3.registrar-servers.com    10        Automatic
MX    @     eforward4.registrar-servers.com    10        Automatic
MX    @     eforward5.registrar-servers.com    10        Automatic
TXT   @     v=spf1 include:spf.efwd.registrar-servers.com ~all        # apex SPF for forwarding (NEW; none today)
```
CORRECTION (owner item 1): an earlier draft guessed `mx1/mx2.privateemail.com` — that is WRONG. `privateemail.com`
is Namecheap's PAID **Private Email** product (distinct IPs `162.255.118.7/.8`). FREE Email Forwarding uses
`eforward1-5.registrar-servers.com` (all resolve to `162.255.118.51/52`), auto-written by the Mail-Settings
toggle. Verified by live `dig` + the Namecheap KB, not assumed.

DO NOT TOUCH (sending — leave exactly as-is, verified live):
```
CNAME  qlfked64yn7gvnozgzlvfylbldlje4ds._domainkey  → …dkim.amazonses.com
CNAME  kmlu75uj6qmy6iwkso5reeilhhvgfcx5._domainkey  → …dkim.amazonses.com
CNAME  nljlpzwcdfjkqjdk6fx6i3553tahg62u._domainkey  → …dkim.amazonses.com
MX     mail (mail.yotale.ai)  10 feedback-smtp.us-east-1.amazonses.com
TXT    mail (mail.yotale.ai)  v=spf1 include:amazonses.com ~all
TXT    _dmarc  v=DMARC1; p=none
```
CONFLICT CHECK: SES MAIL FROM uses the **`mail.` subdomain** MX; the new receiving MX is at the **apex** —
they do not collide. The apex SPF is NEW (none exists today). Keep DMARC `p=none` during setup; tighten later.

### Forwarding map (configure in Namecheap after the MX/SPF resolve)
| Address | Forward to (owner-controlled mailbox) |
|---|---|
| aws@yotale.ai (management) | owner inbox |
| beta@yotale.ai | owner inbox |
| gamma@yotale.ai | owner inbox |
| prod@yotale.ai | owner inbox |
| aws-security@yotale.ai | owner inbox |
| aws-billing@yotale.ai | owner inbox |
| alerts@yotale.ai | owner inbox (or the ops channel) |

**Owner input needed:** the destination mailbox each address forwards to (one address or several).

### Inbound verification gate (BEFORE any AWS account creation)
For each of aws@/beta@/gamma@/prod@/aws-security@/aws-billing@/alerts@: send a test message and confirm it
arrives at the forward target. AWS account creation proceeds ONLY after all seven deliver. (A distinct,
reliably-received address per account root is an AWS best practice and a recovery safeguard.)

---

## Phase 2 — AWS Organizations architecture (smallest secure structure)

**Key decision — do NOT reuse `989088054552` as management.** It already hosts Story + ainigama workloads.
The clean target is a **dedicated, workload-free YoTale management account**. Two viable paths:

- **Path A (preferred, cleanest):** create a NEW dedicated management account under a NEW org root, with a
  workload-free management account (email `aws@yotale.ai`), and create beta/gamma/prod (and a migrated dev)
  as member accounts. The current `989088054552` org is left as-is or retired later; Story dev either stays
  there transitionally or is migrated. Cleanest separation; most setup.
- **Path B (pragmatic):** KEEP the existing org `o-hwquoahv3t` but STOP treating `989088054552` as a
  workload account going forward — add OUs, create fresh beta/gamma/prod member accounts, and migrate Story
  workloads out of the management account over time. Less upfront churn; the management account stays
  "dirty" with legacy workloads until migration. **This is a real owner decision (A vs B); flagged below.**

Target structure (either path):
```
Root
├── Management account  (email aws@yotale.ai)  — billing, Identity Center, no workloads
├── OU: Workloads
│    ├── beta     (email beta@yotale.ai)
│    ├── gamma    (email gamma@yotale.ai)
│    └── prod     (email prod@yotale.ai)
└── OU: Sandbox/Dev   (dev — current Story dev, migrated or re-created)
```
Controls:
- **Centralized billing** at management; **per-account AWS Budgets** with alerts to `aws-billing@`/`alerts@`.
- **IAM Identity Center** (already active) as the single sign-in; permission sets per account/role
  (AdminAccess scoped to break-glass; a `StoryDeploy` least-privilege set for pipelines).
- **Root security:** each account root gets a unique strong password + hardware/virtual MFA; root used only
  for break-glass; security/billing/operations alternate contacts set to aws-security@/aws-billing@.
- **SCPs on the Workloads OU:** deny leaving the org, deny disabling CloudTrail/guardrails, region-restrict
  to us-east-1, deny root-access-key creation.
- **Least-privilege cross-account deploy:** GitHub OIDC role PER environment (no static keys — the dev
  pipeline already does this); a scoped CFN exec role per account; **no persistent deployment access keys**.
- **No cross-environment data sharing by default:** separate buckets/tables/pools per account; no bucket
  policy or KMS grant spanning environments.

**Owner input needed:** Path A vs Path B; and the management-account email (`aws@yotale.ai`) must receive mail
first (Phase 1 gate).

---

## Phase 3 — Beta environment deployment plan (smallest reproducible)

Deploy the SAME CDK (`story-<env>-api` + `story-<env>-auth`) into the **beta account** with
`-c environment=beta`, by **immutable digest** (the existing pipeline pattern), into a FRESH data plane:
- Cognito user pool (beta) + account-ownership/identity tables (fresh, empty).
- `story-beta-stories` / `-understanding` / `-media` (private S3, no public access) / `-edit-plan-jobs(+dlq)`.
- App Runner `story-beta-api` + Lambda `story-beta-edit-plan-worker` (digest/hash-pinned).
- **SES in the BETA account (item 5 — Cognito↔SES is SAME-ACCOUNT ONLY).** AWS does NOT support Cognito→SES
  cross-account, so beta Cognito CANNOT reuse the dev account's `yotale.ai` SES identity. Beta must have its
  OWN SES identity, same region (us-east-1): verify a **`beta.yotale.ai` subdomain** (recommended — isolates
  beta sending reputation and avoids colliding with the dev account's apex identity) OR re-verify `yotale.ai`
  in the beta account. Steps: (a) create the SES domain identity in the beta account → it issues 3 NEW DKIM
  CNAMEs + a MAIL FROM; (b) add those records at Namecheap (additive — they do NOT touch the dev account's
  existing sending records); (c) set the beta user pool `EmailConfiguration` to `EmailSendingAccount=DEVELOPER`
  with `SourceArn` = the beta-account SES identity ARN; (d) attach a Cognito-send authorization policy on the
  beta SES identity scoped to the beta user-pool ARN + beta account id (mirrors the dev policy, but in-account).
  Until the beta SES identity leaves the SES sandbox, OTP works only to verified recipients — request
  production access for the beta account before external beta testers. OTP works day one for the owner's own
  verified address.
- Secrets/config via SSM Parameter Store / Secrets Manager in the beta account (no secrets in the image).
- Basic CloudWatch: the free SQS/Lambda/App Runner/DynamoDB metrics + a beta budget alarm. (The full
  observability milestone — the approved next milestone — layers EMF metrics/dashboards/alarms on top.)
- **Beta cost safeguards:** per-account AWS Budget (owner amount) + Lambda reserved concurrency + Bedrock
  usage visibility (the worker now emits EstimatedModelCostUSD — commit `9d7ca94`).
- **Data isolation (hard rule):** NO copy of dev user data, personal media, or test identities into beta.
  Beta starts empty. Release authority is the **digest**, never `:latest`.

---

## Phase 4 — Deployment readiness

1. **Account-creation sequence:** (gate: Phase-1 inbound verified) → create management account (aws@) →
   enable Identity Center/OUs/SCPs → create beta (beta@), gamma (gamma@), prod (prod@) member accounts →
   set root MFA + alternate contacts on each → bootstrap CDK + OIDC deploy role in beta.
2. **Email verification actions:** enable Namecheap forwarding; add apex MX+SPF; verify all 7 addresses
   receive mail (Phase-1 gate) BEFORE step 1.
3. **Account/OU structure:** per Phase 2 (pending A/B decision).
4. **Resource inventory & cost:** beta mirrors dev (App Runner ~$5–25/mo idle-ish, DynamoDB on-demand, S3,
   Lambda, SQS, Bedrock usage-based) + CloudWatch; rough beta **< ~$50–150/mo** pre-traffic (refine on load).
5. **Beta CDK changes:** none structural — `-c environment=beta` + the beta account/region context + a
   beta Cognito-send SES policy; bootstrap the beta account.
6. **GitHub Environment/OIDC changes:** add a `beta` protected Environment with `BETA_DEPLOY_ROLE_ARN` +
   `CFN_EXEC_ROLE_ARN` vars; a `deploy-beta.yml` mirroring `deploy-dev.yml` (manual dispatch, digest-pinned).
7. **Deploy & rollback:** deploy by digest; rollback = redeploy the previous digest from the release manifest
   (immutable artifacts make this exact).
8. **Smoke test & security acceptance:** health + a real OTP sign-in in beta; private-bucket/no-public-access
   assertion; cross-account isolation check; no dev data present.
9. **Monitoring & budget:** free service metrics + beta budget alert to aws-billing@/alerts@.
10. **Remaining owner decisions:** see below.

---

## Remaining owner decisions (STOP gate — nothing proceeds without these)
1. **Org Path A (new dedicated management account/org) vs Path B (reuse org `o-hwquoahv3t`, stop using
   `989088054552` as a workload account, migrate Story out).**
2. **Forwarding destination mailbox(es)** for the 7 addresses.
3. **Confirm the 4 account root emails** (aws@/beta@/gamma@/prod@ — matches the proposal).
4. **Per-account budget amounts** (beta/gamma/prod) for the budget alarms.
5. **Region policy** (us-east-1 only, or add others) for the SCP region restriction.

Approve these and I will execute in bounded increments: Phase 1 DNS/forwarding + verification → Org/accounts →
beta bootstrap + deploy → smoke/security acceptance. The next milestone after beta acceptance is the existing

---

## OWNER DECISIONS LOCKED (2026-10-21)

- **Path A chosen:** create a NEW dedicated YoTale AWS Organization with a **workload-free management
  account**. Leave `989088054552` and org `o-hwquoahv3t` UNTOUCHED. Do NOT migrate YoTale dev; do NOT modify
  Ainigama. All current dev workloads preserved.
- **Root emails approved:** aws@ (management), beta@, gamma@, prod@ `yotale.ai`.
- **Forwarding:** one secure admin forwarding destination initially — **PENDING owner confirmation of the
  actual destination inbox** (the one value that gates starting the email setup).
- **Budgets (alert thresholds, NOT hard caps), alerts at 50/80/100%:** Beta **$100/mo**, Gamma **$50/mo**,
  Production **$100/mo**. No public production traffic authorized.
- **Region:** us-east-1 for application workloads; explicit exceptions for global AWS services (IAM,
  Organizations, CloudFront, Route 53, billing) and required security infrastructure.

### Pre-provisioning verification (owner items 1–6) — status

1. **Namecheap forwarding MX — VERIFIED (corrected):** free Email Forwarding = `eforward1-5.registrar-servers.com`
   (live `162.255.118.51/52`), auto-written by the Advanced-DNS → Mail-Settings → "Email Forwarding" toggle;
   apex SPF `v=spf1 include:spf.efwd.registrar-servers.com ~all`. NOT `privateemail.com` (that is the paid
   Private Email product). Confirmed by Namecheap KB + live `dig`.
2. **Preserve sending — VERIFIED present + untouched:** `yotale.ai` SES verified, DKIM (3 CNAMEs live), MAIL
   FROM `mail.yotale.ai`, apex DMARC `p=none`, Cognito OTP policy on `us-east-1_AzfHOEdA5`. The forwarding
   change is apex-MX + apex-SPF only; it touches NONE of these. (SES MAIL FROM uses the `mail.` subdomain MX,
   no apex collision.)
3. **Inbound verification — VERIFIED (2026-10-21):** forwarding destination = `lingzhang.ccny@gmail.com`
   (owner-confirmed). Namecheap Email Forwarding enabled; all 7 aliases (aws@/beta@/gamma@/prod@/aws-security@/
   aws-billing@/alerts@) configured → `lingzhang.ccny@gmail.com`. Apex MX (`eforward1-5`) + apex SPF live and
   propagated (Google 8.8.8.8 + Cloudflare 1.1.1.1). Owner ran the delivery test from a non-destination address
   (after Namecheap's ~1h mailbox activation) and **confirmed inbound receipt**. SES sending re-verified intact
   post-change via AWS API: domain verification Success, DKIM enabled+Success (3 tokens), MAIL FROM
   `mail.yotale.ai` Success (`BehaviorOnMXFailure=UseDefaultValue`). **Phase 1 COMPLETE.**
4. **Standalone management-account creation — CONFIRMED procedure:** sign up a brand-new standalone AWS
   account at the AWS sign-up page with root email `aws@yotale.ai` (needs a payment method + verified contact);
   from that account enable AWS Organizations (CreateOrganization, FeatureSet=ALL) → it becomes the management
   account; keep it workload-free; create beta/gamma/prod as member accounts inside the org (each with its own
   root email). This is a SEPARATE org from `o-hwquoahv3t`.
5. **Beta Cognito→SES — CONFIRMED design (same-account only):** Cognito cannot use SES cross-account, so beta
   gets its OWN SES identity in the beta account/us-east-1 (recommended `beta.yotale.ai` subdomain → new DKIM
   CNAMEs added at Namecheap, additive), user pool `EmailSendingAccount=DEVELOPER` + `SourceArn` = beta SES
   identity, + an in-account Cognito-send policy; request SES production access before external testers.
6. **Preserve dev account + workloads — HONORED:** nothing in this plan creates, modifies, or deletes anything
   in `989088054552`; the new org/accounts are entirely separate.

### Phase 1 status — COMPLETE (2026-10-21)
Email receiving is live and verified end-to-end. Destination `lingzhang.ccny@gmail.com`; all 7 admin aliases
deliver; sending (SES DKIM/MAIL FROM/Cognito OTP) preserved and re-verified intact; dev account untouched.

### Next action (STOP gate — owner go required)
Phase 1 clears the email prerequisite for AWS account creation. **STOP here per the B0 gate** — account
creation needs the owner's explicit go plus a payment method + verified phone (console action, owner-credentialed).
On go, in bounded increments:
1. Create the standalone **management** account (root `aws@yotale.ai`) → enable Organizations (FeatureSet=ALL),
   keep it workload-free; set org security contacts; enable IAM Identity Center.
2. Create the **beta** member account (root `beta@yotale.ai`); create gamma/prod as empty, secured accounts.
3. Beta SES identity (recommend `beta.yotale.ai`, additive DKIM CNAMEs) + Cognito DEVELOPER mode (same-account).
4. Beta CDK deploy **by digest** (no `:latest`), fresh data plane (no dev data copied), SQS/DLQ, private media.
5. Per-account budgets (beta $100 / gamma $50 / prod $100 @ 50/80/100%) + basic CloudWatch.
6. Smoke + security acceptance.
Then the next milestone: CloudWatch observability + Bedrock cost-accounting implementation.
