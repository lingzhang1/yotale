# YoTale — SES Email + Cognito Email OTP + Invite-Only Auth (dev)

Status: dev OTP delivery working end-to-end; iOS invite-only sign-in implemented; admin provisioning
procedure shipped. STOP point: iOS authentication + invite-provisioning acceptance (no prod, no public signup).

## Domain / DNS (Phase 0)
- Domain `yotale.ai`, registrar **Namecheap**, NS `dns1/dns2.registrar-servers.com` (BasicDNS). No Route 53
  zone, no nameserver migration. Zone was empty; all records are additive.

## SES (dev acct 989088054552, us-east-1)
- Domain identity `yotale.ai`: **Verified**, Easy DKIM RSA-2048 **SUCCESS**.
- Custom MAIL FROM `mail.yotale.ai` (MX + SPF added; status PENDING — non-blocking for sending).
- DMARC `_dmarc` TXT `v=DMARC1; p=none;` (no `rua` until a monitored mailbox exists).
- Recipient `dearlingzhang@gmail.com` verified (sandbox). Account still in **sandbox** (200/day, 1/s).
- SES identity policy `AllowCognitoSend` authorizes principal `email.cognito-idp.amazonaws.com` to send from
  the identity, scoped to the pool + account.

### DNS records added at Namecheap
| Type | Host | Value |
|---|---|---|
| CNAME ×3 | `<token>._domainkey` | `<token>.dkim.amazonses.com` |
| TXT | `mail` | `v=spf1 include:amazonses.com ~all` |
| MX | `mail` | `10 feedback-smtp.us-east-1.amazonses.com` |
| TXT | `_dmarc` | `v=DMARC1; p=none;` |

## Cognito (pool us-east-1_AzfHOEdA5 = story-development-users)
- `EmailSendingAccount: COGNITO_DEFAULT -> DEVELOPER`, `From: YoTale <dev@yotale.ai>`,
  `SourceArn: arn:aws:ses:us-east-1:989088054552:identity/yotale.ai`.
- Native USER_AUTH / EMAIL_OTP preserved. No Lambda triggers. No password login added.

## The OTP root cause (why codes failed)
`PreventUserExistenceErrors=ENABLED`: for an **unknown** email, `InitiateAuth(EMAIL_OTP)` returns a **decoy**
`EMAIL_OTP` challenge (with a `CODE_DELIVERY_DESTINATION`) but **dispatches no code and creates no user** —
the client advanced to the code screen for a code that never existed. SignUp-first created an UNCONFIRMED user
and sent a *confirmation* code (wrong type) → "code not correct". SES delivery itself works (verified; the
CloudWatch Send counter lags minutes). Proven live: SignUp-free InitiateAuth for an unknown user never
increments SES Send; an `admin-create-user` CONFIRMED user yields a clean, deliverable EMAIL_OTP code.

## Decision — Option D (invite-only, pre-provisioned, confirmed users)
Beta is invite-only. Testers are pre-provisioned as CONFIRMED Cognito users, so only the clean existing-user
EMAIL_OTP path is ever exercised. No Lambda, no password, single code. This is a beta onboarding strategy, not
a permanent public-signup design.

## iOS changes (commits a8ee820, plus 7949b67/838e518 gate+signout)
- `CognitoAuthClient.startEmailOTP`: native USER_AUTH/EMAIL_OTP only; `inviteOnly` error for a no-delivery
  response; no SignUp/password.
- `CognitoAuthError.inviteOnly`: non-enumerating message; no "account exists/not found" wording.
- `SignInView`: invite-only hints on email + code steps (uninvited email never looks like an endless wait);
  expired/mismatch/exhausted handled; session restore / silent refresh / resume-once action preserved.
- Home header **Sign Out** control (so OTP can be re-tested and "logout keeps local content" is verifiable).
- Cloud-AI gate wiring fixed so the sign-in sheet reliably presents when signed out.

## Admin provisioning — `scripts/yotale_beta_invite.sh` (admin-only, never a public endpoint)
`invite|revoke|status|list`. Idempotent `AdminCreateUser` (email_verified=true, SUPPRESS) → CONFIRMED,
EMAIL_OTP-ready; ensures the SES identity. Beta eligibility is a separate allowlist file (gitignored PII),
independent of Cognito account existence; `revoke` removes eligibility and disables the Cognito login.
Verified idempotent against the live pool (no duplicate account on mixed-case re-invite).

## Deployment boundary
Dev App Runner `story-development-api` RUNNING, `STORY_REQUIRE_AUTH=0` (optional-auth) preserved. No gamma/prod,
no public signup, no domain transfer / NS migration / registrar purchase.

## Remaining limitations
- SES **sandbox**: codes deliver only to SES-verified recipients; ~3–5 min latency observed. Production-access
  request is drafted separately (Phase 4) and NOT submitted.
- Apple Sign In disabled until Apple Developer creds are provisioned (`STORY_APPLE_SIGNIN_AVAILABLE`).
- Device acceptance of the final OTP round-trip is the owner's hands-on step.
