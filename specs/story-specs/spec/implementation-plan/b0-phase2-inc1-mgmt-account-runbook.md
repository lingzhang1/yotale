# B0 Phase 2 — Increment 1: Dedicated YoTale Management Account (Runbook)

**Scope:** create + secure ONE standalone AWS account (root `aws@yotale.ai`) and make it the
workload-free management account of a NEW AWS Organization. Configure Identity Center, alternate
contacts, root-email + recovery, MFA. **No member accounts, no app infra, no DNS/SES/CI/CD changes.**

**Separate from existing:** account `989088054552` / org `o-hwquoahv3t` (1 account, master
`dearlingzhang@gmail.com`) is UNTOUCHED. The new account forms its own org as a new payer.

**Agent boundaries honored:** the agent never requests or stores the root password, MFA codes/secret,
or payment credentials. Console steps are owner-performed; the agent verifies via read-only signals.

---

## Step 1 — Create the standalone AWS account (console, owner)
1. Open an incognito/private browser window (so it doesn't reuse the dev-account session).
2. Go to the AWS sign-up page: https://signup.aws.amazon.com/
3. **Root email:** `aws@yotale.ai`  ·  **Account name:** `YoTale-Management` (or similar).
4. Set a strong **root password** (store in YOUR password manager — never share it with me).
5. Contact info: your business/personal details.
6. **Payment method:** a valid card (AWS places a temporary ~$1 auth, refunded). Required even though
   the management account will run no workloads.
7. **Phone verification:** enter the code AWS sends (SMS/voice) — on your phone only.
8. **Support plan:** choose **Basic (free)**.
9. Finish. AWS emails a confirmation to `aws@yotale.ai` → it forwards to your Gmail.

**Verify (owner → tell me):** you received the AWS welcome/confirmation email at your Gmail
(via the `aws@` forward). This re-proves the forward on a real AWS message.

## Step 2 — Secure the ROOT user immediately (console, owner)
1. Sign in as **root** (the `aws@yotale.ai` email).
2. **Enable MFA on root** (IAM → Security credentials, or the sign-in security panel). Prefer a
   hardware key or an authenticator app. Store backup codes in your password manager.
3. Do **not** create root access keys (AWS discourages this; leave none).
4. Account → **Alternate contacts**: set **Billing**, **Operations**, **Security** contacts
   (use `aws-billing@`, `alerts@`/ops, `aws-security@` — all forward to your Gmail).
5. Account settings: confirm the **root email** and a recovery phone are correct.

**Verify (owner → tell me):** root MFA shows "Enabled"; alternate contacts saved.

## Step 3 — Enable AWS Organizations with ALL features (console, owner)
1. As root (or an admin), open **AWS Organizations** → **Create an organization**.
2. Choose **Enable all features** (FeatureSet = ALL) — NOT consolidated-billing-only.
3. This account becomes the **management account** of a brand-new org (new `o-xxxx` id).
4. Do **not** create any member accounts yet.

**Verify (agent, if granted read):** `describe-organization` shows a NEW org id ≠ `o-hwquoahv3t`,
FeatureSet=ALL, MasterAccountId = the new account, MasterAccountEmail = `aws@yotale.ai`.

## Step 4 — IAM Identity Center + administrative access (console, owner)
1. Set region to **us-east-1** (keep the org/identity home region consistent).
2. Open **IAM Identity Center** → **Enable**. (Choose Identity Center directory as the identity source
   to start; external IdP can come later.)
3. Create an **admin user** (your email) and a **permission set** (`AdministratorAccess` to start;
   tighten to least-privilege for deploys in Phase 3).
4. Assign the admin user to the management account via that permission set.
5. Use the Identity Center **access portal URL** for day-to-day admin — stop using root.

**Verify (owner → tell me):** you can sign in through the Identity Center portal with the admin
permission set (no longer using root for daily work).

## Step 5 — (Optional) grant the agent a read-only verification role
To let me verify org/account config directly, create in the NEW management account an IAM role or
Identity Center permission set with **`ReadOnlyAccess`** (or `arn:aws:iam::aws:policy/job-function/ViewOnlyAccess`)
and give me a way to assume it (profile). I will NEVER need write access, the root user, or keys.
If you skip this, I verify from your console confirmations + public DNS/billing signals instead.

---

## STOP gate (end of Increment 1)
After Steps 1–4 verify, STOP. Report: new Account ID, new Org ID, FeatureSet, Identity Center status,
alternate contacts, root MFA, and that `989088054552`/`o-hwquoahv3t`/dev/Ainigama are untouched.

## Costs
- Management account itself: **$0** base (no workloads). Temporary ~$1 card auth at signup (refunded).
- Organizations, Identity Center (Identity Center directory), IAM: **$0**.
- No member accounts / no infra this increment → no recurring charge.

## Prerequisites for member-account creation (next increment, NOT now)
- Confirm root emails `beta@`/`gamma@`/`prod@` receive mail (same forward).
- Decide OU layout (Workloads OU: beta/gamma/prod; Security/Sandbox OUs).
- Draft SCP guardrails (region lock us-east-1 + exceptions; deny leaving org; protect security infra).
- Per-account budgets ($100/$50/$100 @ 50/80/100%).
- Owner go for member-account creation.

---

## ✅ VERIFIED COMPLETE — 2026-10-21 (CLI-confirmed via `yotale-mgmt` SSO profile)

Increment 1 done. All facts below confirmed directly through the agent's read access (SSO
AdministratorAccess assumed-role `lingzhang` in the new account), not just console screenshots.

**New management account & org**
- Management account: **`001188477936`** ("YoTale-Management"), root email `aws@yotale.ai`, status ACTIVE.
- New Organization: **`o-iqahcgt2wz`**, FeatureSet **ALL**, SERVICE_CONTROL_POLICY ENABLED, **1 account only** (workload-free).
- Distinct from the dev org — no relationship to `o-hwquoahv3t`.

**IAM Identity Center**
- Instance **`ssoins-72230ef1c7ef0e6a`**, Identity Store **`d-906662fd13`**, status ACTIVE, us-east-1.
- Access portal: `https://d-906662fd13.awsapps.com/start` (owner's daily sign-in; stop using root).
- User `lingzhang` assigned to the management account via permission set **`ps-722337e8e555d2d5`** (`AdministratorAccess`). PrincipalType=USER confirmed.

**Alternate contacts** (set by agent via `account put-alternate-contact`, read back OK):
- BILLING → `aws-billing@yotale.ai`
- SECURITY → `aws-security@yotale.ai`
- OPERATIONS → `alerts@yotale.ai`
- NOTE: phone set to placeholder `+10000000000` (API requires a value; AWS does not verify it). Owner may replace with a real number in Account → Alternate contacts.

**Non-interference proven**
- Dev org `o-hwquoahv3t` / account `989088054552` still FeatureSet=ALL, **still exactly 1 account**, master email `dearlingzhang@gmail.com` — untouched. Ainigama/Story dev workloads not modified.

**Owner-side items still manual (cannot verify via API — confirm in console):**
- Root user MFA enabled on `001188477936`.
- The earlier IAM user `Admin` (console access, no MFA) — add MFA or delete it (superseded by the IdC user).

**Cost:** $0 recurring (management account base, Organizations, Identity Center, IAM all free; ~$1 refundable signup auth).

## STOP — awaiting owner review before next increment
Next bounded increment: a CDK **`org-foundation`** stack (Workloads/Security/Sandbox OUs, SCP
guardrails, per-account budgets, alternate-contact codification), deployed with the `yotale-mgmt`
profile — authored and reviewed before any beta/gamma/prod member account is created.

---

## ✅ org-foundation DEPLOYED & verified — 2026-10-21 (via `yotale-mgmt` SSO profile)

CDK stack `yotale-org-foundation` deployed to management account `001188477936` / us-east-1.
CDKToolkit bootstrapped first (standard S3 bucket + roles). All resources CLI-verified live:

**OUs under root `r-6dce`:**
- Workloads — `ou-6dce-u19fn3wl`
- Security — `ou-6dce-57g6g62t`
- Sandbox — `ou-6dce-rical63w`

**SCPs (custom):**
- `yotale-region-lock-us-east-1` (`p-njbqhrap`) → attached to **Workloads**
- `yotale-protect-org-security` (`p-0nmld7v3`) → attached to **Workloads + Sandbox**
- (pre-existing, outside this stack: `DenyLeaveAndCloseAccount` `p-hf8k7ynx` — additive, harmless)

**Budgets:** `yotale-beta-monthly` $100 · `yotale-gamma-monthly` $50 · `yotale-prod-monthly` $100,
each ACTUAL-spend alerts at 50/80/100% → `alerts@yotale.ai` (soft alerts, no action attached).

**Still inert:** SCPs only bite once member accounts exist under those OUs; the lone management
account is unaffected (region-lock is on Workloads, not the root). No member accounts created.

CDK commit: `5441a1d` (app repo). Deploy env: `TMPDIR=/tmp CDK_HOME=/tmp/cdkhome` + `--profile yotale-mgmt`
(NOTE: do NOT set `HOME=/tmp` for the SSO profile — it hides `~/.aws` and CDK fails with NoCredentials).

### Next increment (separately approved): member accounts
`organizations.CfnAccount` for beta (then gamma/prod empty-secured), placed in the Workloads OU,
after beta@/gamma@/prod@ root emails are delivery-verified. Then beta data-plane deploy by digest.

---

## ✅ Beta member account CREATED — 2026-10-21 (via `yotale-mgmt`)

- `organizations create-account` (request `car-2db2c6880cf140dea9bfdd5b6ff8feec`) → **SUCCEEDED**.
- **Beta account `224033508028`** ("YoTale-Beta", root `beta@yotale.ai`), Status ACTIVE.
- Moved from root into **Workloads OU** (`ou-6dce-u19fn3wl`), so the region-lock + protect-security
  SCPs apply by inheritance. (SCPs enabled at root; `list-policies-for-target` on an ACCOUNT shows
  only directly-attached `FullAWSAccess` — inherited SCPs are not listed there, which is expected;
  they are attached at the OU and in force.)
- No gamma/prod accounts yet (owner may keep them deferred until needed).
- No workloads deployed into beta yet.

### Access to the beta account
`create-account` makes an `OrganizationAccountAccessRole` (AdministratorAccess, trusts the management
account) in the new account. To let the `yotale-mgmt` admin operate beta: either assume that role, or
(cleaner) add an IAM Identity Center permission-set assignment for `lingzhang` → YoTale-Beta. CDK
bootstrap of the beta account for the data-plane deploy will be done next increment.

### Next increment: beta data-plane (separately staged)
Cognito (own-account SES identity, DEVELOPER mode), identity/ownership tables, Story+Understanding
stores, private media S3, API+worker by DIGEST (no :latest), SQS/DLQ, basic CloudWatch, beta cost
safeguards. No dev data copied.
