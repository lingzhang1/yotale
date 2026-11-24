# Increment 4 — iOS Auth Device Acceptance Plan (owner runs on a physical iPhone)

I implemented + compile-checked (swiftc -parse) + unit-tested the iOS auth layer. Phase 6 is a **physical-device
acceptance** that I cannot execute (real iPhone, Xcode build, interactive Apple/OTP, real Cognito). Run the
steps below on device; each maps to an owner-requested acceptance scenario.

## Build prerequisites (one-time, Xcode)
1. **Add the new files to the Xcode target** — the pre-existing uncommitted `project.pbxproj` was left
   untouched, so these are on disk but NOT yet in the build: `Story/Data/Auth/*.swift`,
   `Story/Features/Auth/*.swift`, and `StoryTests/AuthLogicTests.swift`. Add them to the `Story` /
   `StoryTests` targets in Xcode (drag into the groups, check target membership).
2. **Capabilities:** enable "Sign in with Apple" only once the Apple IdP is configured (see prerequisites).
   Email OTP needs no capability.
3. Point the build at dev: `STORY_API_BASE_URL` already defaults to the dev App Runner; the Cognito defaults
   match `story-development-auth`. Leave `STORY_APPLE_SIGNIN_AVAILABLE` unset (Apple button stays disabled)
   until Apple creds exist.

## Scenarios
| # | Step | Expected |
|---|------|----------|
| 1 | Email OTP on a real iPhone: enter email → "Email me a code" → enter code → Verify | Signed in; returns to the original action |
| 2 | Enter a wrong code, then an expired one (wait > code TTL) | Clear "incorrect or expired — request a new one"; no crash |
| 3 | Force-quit, relaunch | Session restored silently (no re-login); Home loads |
| 4 | Leave the app until the access token expires (~1h), then do a cloud action | Silent refresh; action succeeds without a login prompt |
| 5 | Signed out, tap a cloud-AI action (e.g. Start a Story → resolve) | Sign-in prompt; after success the SAME action resumes |
| 6 | Watch the backend during #5 | Exactly ONE model call (AuthGate resumes once; no duplicate) |
| 7 | Capture Moments + save a Story while signed out, then sign in, then sign out | All Moments/Stories still present after both transitions |
| 8 | Sign in as A, sign out, sign in as B (different email) | B sees its own cloud content; A's adopted local content is NOT shown as B's |
| 9 | Start an async edit-plan job, background the app, reopen signed in as the same user | Job recovery resumes under the same account |
| 10 | Configure Apple IdP + `STORY_APPLE_SIGNIN_AVAILABLE=1`; tap "Continue with Apple" | ASWebAuthenticationSession → Apple → returns signed in |
| 11 | Airplane mode mid-sign-in; wrong pool id | Actionable error messages, no silent failure/crash |
| 12 | Inspect device + CloudWatch logs during all flows | No OTP codes, access/id/refresh tokens, or raw credentials in logs |

## Known prerequisites before beta cutover
- **SES production access** — dev OTP uses Cognito's default sender (low rate limit); beta volume needs SES
  production access or a verified sending domain.
- **Apple Developer** — Services ID / Team ID / Key ID / private key → configure the Apple IdP on the pool
  (`cdk deploy story-development-auth -c applePrivateKey=... -c appleServicesId=... -c appleTeamId=... -c
  appleKeyId=...`) and set `STORY_APPLE_SIGNIN_AVAILABLE=1`. Until then the Apple button is disabled by design.
- **Auth-required cutover** — the dev backend stays in optional-auth; flip `STORY_REQUIRE_AUTH=1` (dev/staging)
  only AFTER a token-sending TestFlight build passes this plan. Production is already fail-closed in code.

## Readiness for the auth-required cutover
Ready when: scenarios 1–9 + 11–12 pass on device with Email OTP (Apple 10 optional until creds land), the
TestFlight build sends the bearer token on every cloud call, and SES delivery is adequate for the beta cohort.
