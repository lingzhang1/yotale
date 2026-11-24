# Increment 4 — Corrections: Native Passwordless OTP + Complete Paid-AI Gating

Status: code-complete, parse-clean, backend suite green (293 passed, iOS-only change — no backend code
touched). Dev backend remains optional-auth (`STORY_REQUIRE_AUTH=0`, `STORY_ENVIRONMENT=development`,
RUNNING). STOP boundary: iOS **device acceptance** (owner's hands-on step). Commit: `02732ce` on
`feat/p0-auth-ios-increment4`.

This supersedes the OTP mechanism described in the original
[`increment4-ios-auth-device-acceptance-plan.md`](increment4-ios-auth-device-acceptance-plan.md).

## 1. Email OTP — native passwordless, no temporary password

**Owner question answered (verified against the live dev pool `us-east-1_AzfHOEdA5`, client
`5rnvp7oq6d7crbt01ldpe89tkh`):** yes — the temporary password is unnecessary and has been removed.

- The pool has `PreventUserExistenceErrors=ENABLED`, `EMAIL_OTP` as an allowed first-auth factor, self-signup
  enabled (`AllowAdminCreateUserOnly=false`), `EmailSendingAccount=COGNITO_DEFAULT`.
- Live probe: `InitiateAuth(AuthFlow=USER_AUTH, PREFERRED_CHALLENGE=EMAIL_OTP)` on an **unknown** email returns
  `ChallengeName=EMAIL_OTP` + `CODE_DELIVERY_DELIVERY_MEDIUM=EMAIL` and **dispatches a code** — for both new and
  returning emails. No `SignUp`, no client-generated password. A follow-up `list-users` confirmed the probe
  created **no phantom user**: Cognito creates/confirms the account atomically on the first successful code
  verification.
- The earlier `SELECT_CHALLENGE` (no code) was caused only by omitting `PREFERRED_CHALLENGE`.

**Implementation (`CognitoAuthClient`):**
- `startEmailOTP` → native `InitiateAuth(USER_AUTH, PREFERRED_CHALLENGE=EMAIL_OTP)`. Returns a challenge
  **only** when Cognito reports a dispatched code (`CODE_DELIVERY_DELIVERY_MEDIUM == EMAIL`); any other shape
  (incl. `SELECT_CHALLENGE`) raises an error so the UI never shows a dead code screen.
- New-user-signup vs existing-user-sign-in is a **single UX step** by design (anti-enumeration). The
  new-vs-returning distinction is resolved **after** verification by the backend identity claim (first verify
  mints a new StoryUser; returning verify resolves the existing one). No account is merged by email, and the
  email/Apple-relay is never the identity (`story_user_id` is authoritative).
- `verifyEmailOTP` branches via a typed service error: `ExpiredCodeException` → expired (UI returns to the
  email step for a fresh code), `CodeMismatchException` / a re-issued challenge → wrong code (clears the field,
  stays on the code step), `NotAuthorizedException` → attempts exhausted (returns to email step).
- **No OTP, token, password, or bearer value is ever logged** (audited across the auth layer and every gated
  view: zero matches).

**UX (`SignInView`):** the code screen shows Cognito's masked destination (e.g. `p***@s***`), uses
`.oneTimeCode` content type, 60s resend cooldown, loading/error states, and the expired/exhausted recovery
above.

## 2. Complete cloud-AI gating

Token attaches to every request at the single `StoryBackend.authorize()` seam once signed in. UX gates
(`AuthGate` / `.cloudAuthGate`, resume-once → no duplicate inference) now cover every **user-initiated** paid
action; background AU **defers silently**.

| Paid entry point | Endpoint(s) | Gate | Status |
|---|---|---|---|
| Start a Story → Continue | creative-intent, guide, music-direction | sign-in prompt | gated (prior) |
| Change Music | music plan/candidates/analysis | sign-in prompt | gated (prior) |
| Scene-scan → Start Scan | scene-understanding, director | sign-in prompt | gated (prior) |
| Create-a-video flow | duration, music, edit-plan | sign-in prompt | gated (prior) |
| **NL revision — Customize** | interpret (edit plan) | sign-in prompt | **gated (this change)** |
| **NL revision — Revise sheet** | interpret (edit plan) | sign-in prompt | **gated (this change)** |
| **Direct music search** | music/search | sign-in prompt (first search) | **gated (this change)** |
| **Capture AI Director (Get-idea/Rescan)** | scene-understanding, director | sign-in prompt | **gated (this change)** |
| **Background Asset Understanding** | asset-understanding | **DEFERRED until authed** | **this change** |

**Background AU defer (`AssetUnderstandingQueue`):** `enqueue` still persists the PENDING job on capture (the
Moment is never blocked or lost). `drain()` is a **silent no-op while signed out** — jobs stay PENDING, no
backoff is burned, no sign-in prompt. On sign-in (`StoryApp.onChange(auth.state == .signedIn)`) the queue
drains and the existing idempotent upsert + orphan recovery process each job **exactly once** — never a
duplicate understanding row. Auth is read via a shared predicate (`sharedIsAuthed`, same seam pattern as the
token provider) so all 7 construction sites defer without plumbing.

**Audit of remaining callers:** `coord.ensure` (music direction), `generateGuide`, `resolver.recommend`
(StoryCreatingView), `durationService.recommend`, `StoryUseCases.resolve` all run **downstream of an
already-gated entry** (they use `resolvedStory`/the create flow, reachable only after a gated Continue/create),
so a session exists by the time they fire. `PendingOperationRecovery.analysisBoth` resumes an operation that
was authorized when submitted. No paid path reaches the backend without first passing a gate or a deferred
drain.

## 3. Device acceptance plan (owner's hands-on step — 10 scenarios)

Build `Story` + `StoryTests` on a physical iPhone (synchronized-group project auto-includes the new files).
Dev stays optional-auth, so the gate is the app-side prompt.

1. **New email signup + OTP delivery** — tap a gated AI action signed out → sign-in sheet → enter a fresh
   email → "Email me a code" → a code arrives (to an SES-verified address; see §4) → the code screen shows the
   masked destination → Verify → action resumes once.
2. **Returning email sign-in** — repeat with the same email; identical flow, resolves to the same
   `story_user_id`.
3. **Incorrect / expired OTP** — wrong code → "incorrect", field clears, stays on code step; wait past expiry →
   "expired", returns to email step for a fresh code.
4. **Session restoration** — force-quit after sign-in → relaunch → still signed in (Keychain), no re-prompt.
5. **NL revision after sign-in** — signed out, open Customize/Revise, submit a natural-language change → sign-in
   prompt → after sign-in the interpret runs once.
6. **Direct music search** — signed out, open the music picker, type a query → sign-in prompt on the first
   search → after sign-in results load; subsequent queries do not re-prompt.
7. **Capture while signed out → pending AU → resume** — signed out, capture a Moment (succeeds, no prompt) →
   confirm no AU runs (no understanding) → sign in → AU drains and the Moment gets its understanding.
8. **No duplicate AU jobs** — capture several Moments signed out, sign in once → each Moment gets exactly one
   understanding row (idempotent).
9. **No unauthenticated paid requests** — signed out, exercise each gated action → each shows the prompt rather
   than silently calling the model.
10. **Existing local Stories/Moments preserved** — sign in then out → all prior Moments/Stories remain;
    SwiftData/media untouched; adopted content is not reassigned to a different account.

Plus: Apple button stays "unavailable in this build" until the Apple IdP is configured.

## 4. Remaining prerequisites

- **SES sandbox** — `COGNITO_DEFAULT` sender (~50/day) delivers to real inboxes for testing but beta needs SES
  production access or a verified domain; an unverified recipient may not receive the code.
- **Apple Developer creds** — Services ID / Team ID / Key ID / private key to configure the Apple IdP and set
  `STORY_APPLE_SIGNIN_AVAILABLE=1`; until then Apple sign-in is correctly disabled.
- **Enforcement cutover** — flip `STORY_REQUIRE_AUTH=1` only after a token-sending TestFlight build passes this
  device plan. Production is already fail-closed in code.

## 5. Readiness for the auth-required cutover

All paid user actions are gated; background AU defers and resumes under the authenticated account; identity is
`story_user_id` (never email/relay); no account auto-merge; no secret logging. The one remaining gate before
flipping enforcement is device acceptance of OTP delivery + resume on a real iPhone.
