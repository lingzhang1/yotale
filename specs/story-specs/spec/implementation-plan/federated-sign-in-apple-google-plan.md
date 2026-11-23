# Federated sign-in plan: finish Apple on dev, then Google

Status (2026-11-24): **Apple: live on dev (device-accepted) and beta. Google: live on dev (device-accepted) and on the beta backend; Beta build turned on in PR #167 (019c4d9); beta device test pending.**

Apple record:
- A2 merged in PR #146 (7aedaac). A3: story-development-auth deployed from 7aedaac with `appleSecretName=YoTale-Apple-SignIn-Dev`; IdP live, client lists it, authorize redirects to Apple with the dev Services ID. A4 merged in PR #147 (87659cf; also fixed a release-gate test that assumed dev was 0).
- Device test found the in-app sign-out left Cognito's hosted-session cookie in the shared browser session, so the next Apple sign-in skipped Apple for about an hour. Fixed in PR #149 (388178b): ephemeral `ASWebAuthenticationSession`, plus Apple's standard `ASAuthorizationAppleIDButton`.
- Evidence: one Cognito user `SignInWithApple_000598…` (sub b4d834e8-…), created 01:51:27 UTC with a relay email; Story account ab38007c-0521-4611-8bd0-f21bfeaf67ca created 01:51:29 UTC. After Ling removed the app from her Apple account and signed in with Share My Email, the SAME Cognito user and Story account were reused (modified 02:16:01 UTC, email now the real address); no second user or claim. API logs since 01:50 UTC: 38 `GET /v1/me`, all 200; no 401/500/Traceback lines.
- **Apple on beta: enabled 2026-11-23.** F4 met: account deletion is live on beta and D7 ships the TN3194 fallback with the server-to-server notification endpoint `/v1/auth/apple-signin-notifications` (deletion design, D7 status). Secret copied to beta, `story-beta-auth` deployed with `appleSecretName=YoTale-Apple-SignIn-Beta`, `Beta.xcconfig` lists `SignInWithApple`. Open: register the endpoint on the App ID in the Apple Developer portal (Ling); a TestFlight build from master.
Google record:
- B2 PR #151 (3ffe53a), B3 PR #152 (c5cb458). Dev: secret `YoTale-Google-SignIn-Dev` (dev account), `story-development-auth` deployed with both secret names, `Development.xcconfig` lists `SignInWithApple,Google` (PR #155, e5ea07f). Device test 2026-11-22: Cognito user `Google_115251263561416055503` and a new Story account `f2345bb8-…`, `GET /v1/me` 200, no 5xx.
- Sign-in UI (PR #158, d2dc01e, device-accepted): providers first, then an "Or use your email" divider; custom HIG Apple button so the title follows the app language; Google Light-theme button with the official "G" (`Assets.xcassets/google_g`, cropped from Google's signin-assets.zip); one 50 pt height and 12 pt radius for all controls.
- Beta (2026-11-24): `YoTale-Google-SignIn-Beta` copied from dev into beta account 224033508028 (shape-checked). `story-beta-auth` deployed with `-c sesFromEmail=no-reply@beta.yotale.ai -c sesAccountId=224033508028 -c appleSecretName=YoTale-Apple-SignIn-Beta -c googleSecretName=YoTale-Google-SignIn-Beta` plus the API stack's required release inputs. **Omitting `sesFromEmail` would remove the pool's SES sender and break beta email codes**; the diff then shows `[-] EmailConfiguration`. Live: pool lists Google and SignInWithApple, client allows COGNITO/Google/SignInWithApple, authorize redirects (302) to accounts.google.com with the beta client. `Beta.xcconfig` lists `SignInWithApple,Google` (PR #167).
- Google Auth Platform: publishing status In production, External. Home page `https://lingzhang1.github.io/yotale-legal/`, privacy `…/privacy.html`, authorized domains: both Cognito domains and `lingzhang1.github.io`. Search Console HTML file `googlebad2e57f9180152b.html` added to `yotale-legal` gh-pages (fe03ca9); keep it. Brand verification (logo/name on the consent screen) pending; does not block sign-in.
- Open: beta device test; brand verification retry after 24 h (the Cognito domains may block it, fix = Cognito custom domain such as `auth.yotale.ai`); Google Sans font for the button; Google's policy prefers separate projects for test and production clients (prod should get its own project); about 8 rejected `POST /v1/billing/transactions` (403 `app_account_token_mismatch`) per sign-in on a phone whose sandbox purchases belong to another account.
Scope: dev first. Beta and prod are out of scope until the dev acceptance below passes and Ling approves.

A2 as built: `-c appleSecretName=<name>` (replaces `applePrivateKey`/`appleServicesId`/`appleTeamId`/`appleKeyId` and the unused stack props). Secret JSON fields: `services_id`, `team_id`, `key_id`, `private_key`. All four become `{{resolve:secretsmanager:<name>:SecretString:<field>::}}`; logical id `AppleIdp` unchanged. CDK's own `UserPoolIdentityProviderApple` (`privateKeyValue: SecretValue`) exists in 2.160, which indicates dynamic references are accepted here; the dev deploy (A3) is the real proof.

## 1. Current state (verified 2026-11-21)

| Area | State | Evidence |
|---|---|---|
| iOS Apple flow | Written: `AuthStore.signInWithApple()` opens Cognito `/oauth2/authorize?identity_provider=SignInWithApple` in `ASWebAuthenticationSession`, PKCE + state check, then `CognitoAuthClient.exchangeAuthCode` and the normal `finishSignIn` (GET /v1/me). | `apps/ios/Story/Story/Data/Auth/AuthStore.swift:111-145`, `StoryAuthConfig.swift:35-46` |
| iOS gate | `STORY_APPLE_SIGNIN_AVAILABLE = 0` baked in `Development.xcconfig` and `Beta.xcconfig`. `scripts/release_config_gate.py` requires an explicit 0/1 and, for 1, checks the pool has a `SignInWithApple` IdP. | xcconfigs, `release_config_gate.py:416-562` |
| URL scheme | `story://auth` registered in Info.plist and on the app client as callback + logout URL. | `Info.plist:53-62`, `story-auth-stack.ts:154` |
| Cognito domain (dev) | `story-development-auth`, ACTIVE, classic hosted UI (ManagedLoginVersion 1), pool `us-east-1_AzfHOEdA5`. | live read-only `describe-user-pool-domain` |
| Apple IdP (dev) | Absent. App client supports only `COGNITO`. No Apple users. | live read-only check, previous turn |
| CDK | Apple IdP created only when `-c applePrivateKey=...` is passed. The auth stack is only synthesized with `-c deployAuth=true`; no workflow deploys it (manual deploy). | `story-auth-stack.ts:118-135`, `bin/app.ts:50-59` |
| Backend | Provider-agnostic. `IdentityStore.resolve()` keys on `cognito#<sub>`, so an Apple or Google sign-in gets its own Cognito sub and therefore its own new Story account. No email auto-merge (owner decision 2026-10-18). | `apps/api/app/auth.py:212-250` |
| Entitlement | None. The Cognito web flow does not need the Sign in with Apple entitlement (Apple sees the Services ID). The native Apple sheet (deletion re-auth, design Appendix A) does need it. | |
| Bundle id | `com.lingzhang.story` | `project.pbxproj` |

## 2. Plan A: finish Apple sign-in on dev

### A1. Apple Developer setup (Ling, in the Apple Developer portal)

Kiro cannot do these steps. Kiro verifies afterwards from the AWS side only.

1. App ID `com.lingzhang.story`: enable the Sign in with Apple capability (primary App ID).
2. Create a Services ID for the web flow, for example `com.lingzhang.story.signin.dev`. Enable Sign in with Apple, primary App ID `com.lingzhang.story`.
   - Domain: `story-development-auth.auth.us-east-1.amazoncognito.com`
   - Return URL: `https://story-development-auth.auth.us-east-1.amazoncognito.com/oauth2/idpresponse`
3. Create a key with Sign in with Apple enabled, tied to the primary App ID. Download the `.p8` once. Note the Key ID and the Team ID.
4. Store the key in dev Secrets Manager from Ling's own terminal, never through chat, for example secret `YoTale-Apple-SignIn-Dev` with fields `services_id`, `team_id`, `key_id`, `private_key`. Kiro verifies by field names and key length/header only.
5. Server-to-server notification endpoint on the Services ID: leave empty on dev for now. It is needed for the TN3194 fallback in the account deletion design and is added with that work (D7), not here.

### A2. CDK change (Kiro, small PR)

Problem with the current code: `-c applePrivateKey=...` puts the private key in the synthesized template, `cdk.out` and shell history.

Change:
- Replace the `applePrivateKey` context value with a Secrets Manager dynamic reference (`cdk.SecretValue.secretsManager(<name>, { jsonField: "private_key" })`) for `private_key`, and read `client_id`, `team_id`, `key_id` from the same secret. The template then holds only `{{resolve:secretsmanager:...}}`.
- Gate on `-c appleSecretName=<name>` instead of a key value. No new env flag.
- Keep `attributeMapping` email + email_verified and `authorize_scopes: "email name"`.
- Update `story-auth-stack.test.ts`: IdP present only with the secret name, template contains a dynamic reference and no PEM text, client lists `SignInWithApple` + `COGNITO`.

Verify during implementation that CloudFormation accepts a dynamic reference inside `ProviderDetails` for `AWS::Cognito::UserPoolIdentityProvider` (synth + dev deploy). If it does not, fall back to a context value read from a file outside the repo and keep `cdk.out` out of git (it already is).

### A3. Dev deploy of the auth stack (needs Ling's go)

1. `cdk diff story-development-auth -c deployAuth=true -c appleSecretName=...` with the dev profile. The expected diff is only: add `AppleIdp`, update the app client `SupportedIdentityProviders`. Stop on any other change (pool, domain, tables, email config).
2. `cdk deploy` the same stack. Pool and tables are RETAIN, and the client update is in place, so existing email users and tokens are unaffected.
3. Read-only verify: `list-identity-providers` shows `SignInWithApple`; `describe-user-pool-client` lists it.

### A4. iOS change (Kiro, small PR; Ling builds)

- Set `STORY_APPLE_SIGNIN_AVAILABLE = 1` in `Development.xcconfig` only. Beta stays 0.
- No entitlement change is needed for the web flow. Ling's local `project.pbxproj` edits stay untouched.
- Check the sign-in screen button uses Apple's standard button style (HIG). Today's code path is a generic button; switch to `SignInWithAppleButton` styling if it is not already.

### A5. Dev acceptance on Ling's iPhone

| # | Check | Pass criterion |
|---|---|---|
| 1 | New Apple user, share email | Signs in; GET /v1/me returns a new story_user_id; Cognito user `SignInWithApple_...` exists |
| 2 | New Apple user, Hide My Email | Signs in; `verified_email` is the relay address |
| 3 | Sign out, sign in again with Apple | Same story_user_id, no second account |
| 4 | Cancel the Apple sheet | Returns to signed-out screen, no error loop |
| 5 | Same email via email code and via Apple | Two separate accounts (expected under the current no-merge rule; see decision F1) |
| 6 | Token refresh after 60 min | Session survives refresh |
| 7 | Billing: Apple user buys sandbox Plus | Entitlement attaches to the Apple-signed-in account |
| 8 | Account deletion interplay | Recorded as input to deletion design Appendix A; not a pass/fail gate here |

### A6. What remains after dev

- Beta: separate Services ID (or add the beta Cognito domain + return URL to it), beta secret, beta auth deploy, `Beta.xcconfig` = 1, release gate run. Needs Ling's go and `aws sso login`.
  - Secrets (2026-11-22): dev account 989088054552 holds `YoTale-Apple-SignIn-Dev` (Services ID `com.lingzhang.story.signin.dev`, key J77ZNM2X3V) and the staged beta key `YoTale-Apple-SignIn-Beta` (Services ID `com.lingzhang.story.signin.beta`, key 2J5M246W2G). Ling's decision: at beta deploy, copy `YoTale-Apple-SignIn-Beta` from dev into beta account 224033508028 (same name), verify by shape only, then deploy beta auth with `-c appleSecretName=YoTale-Apple-SignIn-Beta`.
- Account deletion with Apple users present: token revocation (Appendix A test) or the TN3194 fallback with the notification endpoint. Apple sign-in must not reach users on a build without one of the two.

## 3. Plan B: Google sign-in after Apple

App Store Guideline 4.8: a build that offers Google must also offer Sign in with Apple (or an equivalent private option). So Google ships only in builds where Apple is on.

### B1. Google Cloud setup (Ling)

1. Google Cloud project, OAuth consent screen: External, app name YoTale, support email, privacy policy URL, scopes `openid email profile` only (non-sensitive, so no Google security review; brand verification is needed to show the logo and to leave Testing mode).
2. While in Testing mode, add Ling's test Google accounts as test users.
3. OAuth client of type **Web application** (Cognito is the client, not the iOS app):
   - Authorized JavaScript origin: `https://story-development-auth.auth.us-east-1.amazoncognito.com`
   - Authorized redirect URI: `https://story-development-auth.auth.us-east-1.amazoncognito.com/oauth2/idpresponse`
4. Store client id and secret in dev Secrets Manager from Ling's terminal, for example `YoTale-Google-SignIn-Dev`.

### B2. CDK change

- Add `cognito.UserPoolIdentityProviderGoogle` (L2 exists in aws-cdk-lib 2.160) with `clientSecretValue: SecretValue.secretsManager(...)`, scopes `openid email profile`, attribute mapping email, email_verified, given_name, family_name.
- Gate on `-c googleSecretName=<name>`, same pattern as Apple.
- Add `UserPoolClientIdentityProvider.GOOGLE` to the client when present; add the dependency.
- Tests mirror A2.

### B3. iOS change

- Generalize `signInWithApple()` into `signInWithHostedProvider(_ provider: String)` and pass `identity_provider` through `StoryAuthConfig.authorizeURL`. Apple and Google share all the PKCE/state/exchange code.
- Add a "Continue with Google" button following Google's branding rules. `ASWebAuthenticationSession` is allowed by Google (embedded `WKWebView` is not).
- Flags: rather than adding `STORY_GOOGLE_SIGNIN_AVAILABLE`, replace the Apple flag with one baked list `STORY_FEDERATED_PROVIDERS` (for example `SignInWithApple,Google`), and have `release_config_gate.py` check each listed provider exists on the pool and reject Google without Apple (Guideline 4.8). This keeps one parameter instead of two. Decision F3.
- `L10n` strings for the new button (en + zh-Hans).
- Done in PR #158: Google Light-theme button with the official "G" mark. Remaining: Google Sans font.

### B4. Dev deploy and acceptance

Same shape as A3 and A5: diff shows only the Google IdP and client update; device checks for new user, repeat sign-in, cancel, refresh, billing, and the duplicate-account case.

### B5. Account deletion interplay

- Google has no Apple-style revocation requirement. Deleting the Cognito user removes the link. Optionally revoke the Google token; not required for v1.
- The deletion design's recent-sign-in check needs a Google path: re-auth through the hosted flow (Cognito/Google may reuse a live Google session, so check `auth_time` and document what "recent" means for federated users). Add this to the deletion design when Google is scheduled.

## 4. Decisions (accepted by Ling 2026-11-21, all as recommended)

| Id | Decision | Recommendation | Default if unanswered |
|---|---|---|---|
| F1 | Same email through email code and Apple/Google: separate accounts, or link to one account with a Cognito pre-sign-up Lambda (`AdminLinkProviderForUser`) | Keep separate accounts for v1, as decided 2026-10-18. Linking needs a Lambda, cannot match Hide My Email relay addresses, and has a known first-sign-in failure after linking that must be tested. Revisit if users complain. | Separate accounts |
| F2 | Apple Services ID per environment or one shared | One per environment (dev, beta, prod) so a dev key leak or misconfig cannot affect prod | Per environment |
| F3 | One `STORY_FEDERATED_PROVIDERS` list replacing `STORY_APPLE_SIGNIN_AVAILABLE` | Yes, when Google is built (fewer flags) | Keep the Apple flag until then |
| F4 | Ship Apple to beta before account deletion supports Apple users | No. Beta Apple needs deletion revocation or the TN3194 fallback first | No |

## 5. Approvals and blockers

- A1 and B1: Ling's console steps. Nothing else can start for that provider until its secret exists.
- A2/A4 and B2/B3: normal PRs to master, merge commit, after CI. A new branch per PR needs Ling's go.
- A3 and B4: dev auth-stack deploy needs Ling's go after the diff is reviewed.
- Device acceptance: Ling's iPhone, Xcode build from master.

## 6. Not verified

- CloudFormation dynamic reference inside Cognito `ProviderDetails` (A2).
- Hosted-flow UX on device (Face ID vs password prompt in the Apple web sheet; the system "wants to use amazoncognito.com to sign in" prompt).
- Cognito pre-sign-up linking behavior (only relevant if F1 changes).
- Google brand verification outcome with `amazoncognito.com` authorized domains.
