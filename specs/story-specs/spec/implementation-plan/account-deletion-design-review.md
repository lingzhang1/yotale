# Review: YoTale account deletion design

Reviewed: `/Users/lingzhang/Workplace/story/specs/story-specs/spec/implementation-plan/account-deletion-design.md` (uncommitted, 2026-11-20)
Reviewer: independent worker. Report only; no decisions. No AWS calls. Billing V2 files read with `git show master:<path>`; the checkout is on `feat/billing-v2-unlimited-plus` (`git branch --show-current`).
Method: spot-checked the doc's citations against the code, searched `infrastructure/cdk/lib`, `apps/api`, `packages`, and `apps/ios` for stores the doc did not list, then walked the state machine for failure and race cases.

Severity: **blocker** = the design cannot work or leaves undeletable or resurrectable data as written; **should-fix** = a real gap with a concrete fix; **nit** = wording or precision.

## Summary

Most citations hold, and the store inventory is mostly complete (no extra DynamoDB table, S3 prefix, queue or Secrets Manager entry exists in CDK beyond the doc's list). Four blockers:

- F1: an accepted deletion can be stranded forever.
- F2: billing global bindings are located after their source rows are destroyed.
- F3: the `deleting`-tolerant route cannot be built the way section 5.2 describes.
- F10: the local wipe cannot be done as written on iOS.

The remaining findings are should-fix or nit.

---

## 1. Correctness of citations

I checked every `path:line` the deletion steps rely on. Wrong, stale or imprecise ones:

**F-C1 (nit). `packages/user_quota/__init__.py:44-62` does not show the per-user row shape.**
Line 44 is `GLOBAL_PK`; lines 48-62 are `reservation_id`, `quota_mode`, `_period`. The per-user key shape is at `:192-193` (`_key`), which the doc also cites. Cite `:192-193` and `_period` (`:57-59`) only.

**F-C2 (nit). `story-api-stack.ts:61-75,582` for the pool id.**
The release-input guard is at `:60-76`. The env var for the pool id is `STORY_COGNITO_USER_POOL_ID` at `:579-582`. The note that dev falls back to a hard-coded pool id (`us-east-1_AzfHOEdA5`, `:582`) is missing and matters: the deletion Lambda's Cognito ARN must be built from the same context value, not a fallback (see F-S3).

**F-C3 (should-fix). `billing_gate.py:335-337` / `billing-v1-spec.md:90` are cited for "off does no billing read or write" (section 6 and section 2.2).**
On master, `entitlement_payload` in `off` mode still calls `svc.ledger.get_or_create_apple_account_token(uid)` when `apple_service(request)` is not None (`git show master:apps/api/app/billing_gate.py`, the `if led is None:` branch of `entitlement_payload`). That call writes `billing#account` and the global `__apple_token__` row (`master:packages/billing/ledger.py:212-232,640-651`). The apple service exists whenever the usage table is configured, which is the case on dev and beta.
Effect: in `off` mode an account that opened the app has an account row and a global token binding. The doc partly hedges ("may have ... only the account/token row") but section 6's first bullet and decision 8.6 ("Settled by design") imply nothing global exists in `off`. Change: say so in section 6, and put "token binding exists in every mode" into the test list.

**F-C4 (should-fix). "rows expire (6 h job TTL, 24 h staging)" (section 3, rows 11-12, and section 5.3 "In-flight work") overstates the guarantee.**
`edit_plan_jobs/__init__.py:392-394` states that DynamoDB TTL is not immediate and rows are reaped "within ~48h"; `:79` sets 6 h only as `expires_at`. Reads treat the row as expired but the data stays in the table. The staging bucket's lifecycle rule (`story-api-stack.ts:213`, 1 day) also removes objects on a delayed schedule. Terminal job rows hold results and, for coverage jobs, the inline request body (`:278`, `body_json`). Change: restate the residual window as up to about 48 h for rows and 24-48 h for staging, and carry that figure into the privacy text and decision text.

**Citations verified as correct** (no change needed): `auth.py:212-240`, `:251-261`, `:296-300`, `:140-172`; `evidence_store/__init__.py:33-36,93-96,273-309`; `media_store/__init__.py:83,112-114,181-187` (no pagination confirmed); `story_store/__init__.py:125` (paginates); `story-api-stack.ts:187-215,224-234,239-282,334,416-441,449-474,540-552`; `story-auth-stack.ts:50-59,117-135,184-221`; `observability.ts:55-64,93-103`; `story-beta-waf-stack.ts:120-125`; `master:packages/billing/apple.py:237-256,263-276,296-306`; `master:packages/billing/ledger.py:584-601,627-665`; `model_gateway/__init__.py:226-262`; `main.py` evidence route `master:1044`; `HomeView.swift:108-118,134-138`; `AuthStore.swift` sign-out (`signOut` comment "Phase 5: local content survives logout"); `KeychainStore.swift:38`; `StoryApp.swift:44-62`.

---

## 2. Coverage: stores the doc missed or understated

I searched every `new dynamodb.Table`, `new s3.Bucket`, `new sqs.Queue`, `LogGroup`, `boto3.client(...)` call in `apps` and `packages`, and the iOS tree. Server-side, the doc's list matches the code. Gaps:

**F-V1 (should-fix). iOS Caches directory holds user footage derivatives and is not in section 2.3 or 5.6.**
`Domain/Creation/PendingOperationRecovery.swift:131-150` (`PendingJobSubmitStore`) writes the prepared multipart body, which "holds the same contact sheets the planner receives", under `Caches/pending-edit-plan-submits/`. Also not listed: `Features/StoryHome/PhotoImportRunner.swift:240`, `Media/Camera/*:129,367`, `Media/Sync/AIArtifactStore.swift:84,109`, `Media/SceneScan/SceneScanStore.swift:17`, `Data/Contracts/MusicService.swift:271` (all `temporaryDirectory`), and `Features/SceneScan/DirectorDebugPanel.swift:99` (Documents). Change: add a "wipe `Caches/`, `tmp/`, `Documents/` entirely, plus `Application Support/`" step. This is simpler and safer than enumerating folders.

**F-V2 (should-fix). UserDefaults is described as "three call sites"; there are more keys.**
Found: `story_mode`, the app-language key (`AppLanguage.swift`), `story.location.explainerShown` (`ContinuousCaptureView.swift:42`), the critique override, the reference-media mode (`StoryGuideFeatures.swift:21,30`), and the AU diagnostics ring buffer, last 80 events (`AUStepDeadline.swift:52-74`). The AU diagnostics are the only likely personal one. Change: the wipe should remove the app's whole defaults domain (`removePersistentDomain(forName:)`) except an explicit allow-list (language), instead of "account-scoped keys". The doc's open "Assumption" can then be closed.

**F-V3 (nit). No App Group, shared Keychain access group or CloudKit use exists.**
`grep` for `kSecAttrAccessGroup`, `AppGroup`, `CloudKit` and `NSUbiquitousKeyValueStore` finds nothing. The doc does not say so. Add one line to section 2.5. Mention device backups (iCloud or Finder backups of `Documents/`): deleting the account does not reach those. One sentence in the confirmation copy covers it.

**F-V4 (nit). Providers outside our systems: Unsplash and Bedrock are missing from section 2.4.**
`scene_image` queries Unsplash (the policy text should name it if it names the other providers), and `model_gateway/__init__.py:337` still builds a `bedrock-runtime` client. The retention of any Bedrock invocation logging cannot be known from the repo. List both in 2.4 and in the 8.9 verification list.

**F-V5 (nit). SES and Cognito mail.**
In beta, Cognito sends OTP mail through SES (`story-auth-stack.ts:63-89`). SES keeps no message bodies by default, but its account-level suppression list can hold an address after a bounce or complaint. Not controllable from here; one line in 2.4 is enough.

**F-V6 (should-fix). The doc's `model_call_usage` finding is right but incomplete.**
`log_model_call` writes `story_user_id` (and `story_id`, `job_id`) into CloudWatch on every billed call (`model_gateway/__init__.py:262` via `current_call_context`). The docstring at `:238` says "never ... user ids", and `edit_plan_job_submitted` / `coverage_job_submitted` (`main.py:2208,2305`) log `job_id`. The doc already notes the docstring contradiction. Add: fix the docstring (it is in a module Ling's privacy claims quote), and make the privacy text say logs hold a pseudonymous account id, not "do not contain your email" alone (see F-P4).

**F-V7 (should-fix). PITR is not the only restore risk. A table restore resurrects deleted accounts.**
The doc says PITR rows age out (35 days assumed), and that is true for reading. The operational consequence is missing: restoring `users`, `identity-claims` or `user-usage` from PITR re-creates the deleted account's rows and its `active` status. The content tables (4, 7, 8) have no PITR, so only the auth-stack tables can be restored. A restore could bring back an account and its billing rows while its content stays deleted. Change: add a short runbook rule "after any PITR restore, replay deletions" and keep a deletion ledger (account id, request id, completed_at, no personal data) outside the restorable tables, or accept that a restore must re-run the worker over the ledger. This is the standard GDPR backup-restore obligation; the design is silent on it.

Stores I looked for and did not find: any AWS Backup plan, S3 replication, S3 server-access logs, CloudTrail data events, Firehose/Kinesis/Athena/Glue, SNS topics holding user data (grep of `infrastructure/cdk/lib`, `bin`, `scripts`, `.github`). I cannot rule these out in the live accounts (no AWS calls).

---

## 3. Ordering and failure

**F1 (blocker). An accepted deletion can be stranded with nothing that will ever finish it.**
Section 5.2 flips the users row `active -> deleting` and then enqueues, and says a repeat POST "returns the same 202". If the SQS send fails after the conditional update (App Runner crash, throttling, the queue URL env var missing), the account is permanently blocked with 403 (`auth.py:260-261`), no message exists, and a repeat POST does nothing new. The same happens when the message reaches the DLQ after its (5) receives: the doc's only remedy is an alert that depends on the Observability thread. Also, the Lambda "re-enqueues itself with a delay when it nears its deadline", but SQS `DelaySeconds` caps at 900 s, and the verification phase must wait at least 3600 s, so a single delayed message cannot do it.
Change to the design:
1. On a repeat POST while `deleting`, re-send the message if `last_enqueued_at` is older than a short interval (SQS send is idempotent for this worker because every phase is). Write `last_enqueued_at` in the same update.
2. Add a resume trigger that does not depend on the user: an EventBridge schedule (the existing reconcile rule at `story-api-stack.ts:405-407` is the pattern) that finds rows with `account_status="deleting"` and re-enqueues them. The users table has no status index and a Scan is acceptable at current volume (the repo already scans jobs for reconcile); a sparse GSI on `deletion_state` is the scalable alternative. This resumes a user-requested deletion; it is not an expiry, so it does not conflict with the no-auto-cleanup rule, but say so in the doc.
3. Store `quiesced_at` and a `not_before` for the sweep on the users row, and have the worker re-enqueue with `DelaySeconds <= 900` until `now >= not_before`.
4. Define the manual path for a DLQ'd account (operator CLI `resume --uid`), and what the user sees (403 forever versus a message).

**F2 (blocker). The billing step deletes the source of the global bindings before it uses it.**
Section 2.2 says the global `__apple_token__` and `__apple_txn__` rows are found from `b_apple_token` (in `billing#account`) and `b_orig_txn` (in `billing#entitlement`). Section 5.3 phase 4 deletes the whole `<uid>` partition first and "then" the global rows. A crash or retry between those two steps leaves global rows with `b_uid=<uid>` and no way to find them (the retry sees an empty partition and "treats no rows as success"). Under decision 8.2(a) they are meant to be deleted; they would live forever. The fallback (Query `__apple_txn__` filtered on `b_uid`) is described as a "safety net", but nothing makes the worker use it.
Change: phase 4 order is: (1) read the identifiers, (2) write them onto the users row (or a `deletion` item) as `pending_global_keys`, (3) delete/convert the global rows, (4) delete the partition. On every re-run, step 1 reads from the users row first. In the verification sweep, repeat the identifier read before deleting a re-appeared `billing#account`, because a request in flight at the flip can recreate `billing#account` and `bind_apple_transaction` rows after phase 4 (`apple.py:243-250`, `get_or_create_apple_account_token` creates on demand), and those global rows are outside the partition the sweep counts. The sweep's "counts for tables 4,7,8,9" (5.3 phase 6) must also include the two global partitions filtered to this uid, or the `Query` fallback.

**F3 (blocker). The `deleting`-tolerant route cannot be a "dependency" as section 5.2 describes.**
Section 5.2: "Needs a dependency that accepts `account_status` in `{active, deleting}`. The default `_enforce_status` rejects everything except `active`". The status check is inside `IdentityStore.resolve` (`auth.py:212-222,251-261`), called from the central `auth_boundary` middleware (`auth.py` `auth_boundary` -> `_principal_from_token` -> `resolve`) for every non-public path before any route dependency runs. A second POST or any GET while `deleting` is therefore rejected with 403 before the route sees it, so the idempotent 202 and the status poll are impossible as written, and `require_user` reuses the already-resolved principal (`request.state.principal`).
Change: specify a path-scoped bypass in the boundary (for example `resolve(sub, allow_status={"active","deleting"})` when `(method, path)` is in a small `DELETION_ROUTES` set), with a test that only these two routes use it, and that a `deleted` tombstone is still refused. Also note this touches `auth.py`/`main.py` (`main.py` is also in Billing V2's working tree, which already shows `M apps/api/app/main.py`).

**F4 (should-fix). Claim deletion is only safe because of an unstated timing invariant.**
Section 3 deletes the `identity-claims` row at finalise because "the Cognito `sub` can never reappear, so no tombstone value". But access tokens are verified offline against the JWKS (`auth.py:140-172`) and live 60 minutes (`story-auth-stack.ts:167`); `AdminUserGlobalSignOut` revokes refresh tokens, not already-issued access tokens. `resolve()` with no claim creates a brand-new account (`auth.py:212-241`). So a token issued just before phase 1 can mint a fresh empty account if the claim row is gone before it expires. The design's phase 6 wait ("at least 60 minutes after phase 1") equals the token lifetime with zero margin and it is not written as an invariant, and an operator `--force` or a resumed run that skips the wait would break it.
Change: either keep the claim row (it holds only `cognito#<sub>` -> uid, no personal data) pointing at the tombstone, which removes the dependency entirely, or record `quiesced_at` and require `now >= quiesced_at + 60 min + margin` before deleting the claim, with a test. Recommending the first option is within the reviewer's remit only as an observation; the choice is the owner's.

**F5 (should-fix). The tombstone relies on a fail-open read; protect it.**
`_account_status` returns `("active","eligible")` when the users row is missing (`auth.py:205-206`). The tombstone row is therefore the only thing blocking a deleted uid; if finalise, a restore (F-V7), or an operator script ever drops it, the account becomes active again. Add a test "claim present, users row absent => 403" or make `_account_status` fail closed for a claim with no row, and state that tombstone rows are never deleted.

**F6 (should-fix). The Apple notification "tombstone guard" has no detection mechanism.**
Section 4.4: "if the resolved uid is a tombstone, return `account_deleted`". The notification route is public and `AppleBilling` only has the usage-table ledger (`master:packages/billing/apple.py:278-306`); it has no handle on the users table. Options that keep the guard inside the billing package: retain the binding rows with a marker (`b_deleted=1`, uid replaced by a constant), so `apple_txn_owner`/`uid_for_apple_token` return a sentinel the service recognises. That also removes the need to retain the deleted uid. Say which mechanism, and that it is pending Billing V2.

**F7 (should-fix). Idempotence and the "sweep" are not defined for the media phase.**
Phase 2 deletes each S3 object then its row. Resumable, but: (a) the worker needs `s3:ListBucketMultipartUploads` and `AbortMultipartUpload` to find and abort multipart uploads whose row is already gone (presigned part URLs stay valid 1 h, `media_store/__init__.py:83`; the doc mentions aborting but the IAM list in 5.4 does not grant listing); (b) a presigned single PUT can land after the row was deleted, which the final prefix `ListObjectsV2` catches only if it runs 60 min after quiesce; the doc covers this, but also needs `s3:ListBucket`, which 5.4 lists once under a single bullet, good. (c) `delete_for_moment` swallows S3 errors after deleting the manifest (`evidence_store/__init__.py:288-293`), leaving an orphan blob that nothing but the prefix listing finds; the doc notes this. Confirm the worker's evidence deletion goes through the prefix listing, not the manifest.
Also state explicitly that this sweep is scoped to a user-initiated account deletion, so it does not contradict the evidence store's "DELIBERATELY NO ... orphan sweep" docstring (`evidence_store/__init__.py:33-36`).

**F8 (should-fix). Edit-plan jobs: a one-time owner scan is feasible and the doc rules it out too quickly.**
Section 5.3 says there is "no query path by user" and recommends accepting a residual window. The repo already runs `scan` with an `owner` filter for reconcile (`edit_plan_jobs/__init__.py:495,543`). A scan-and-cancel at deletion time covers in-flight jobs and their staging prefix `jobs/<job_id>/` at current volume. Present this as the alternative in a decision, with the cost (a Scan per deletion) and the account-gate-plus-TTL option the doc picked, instead of choosing silently. Given F-C4 (up to ~48 h), the residual window is longer than the doc says.

**F9 (nit). Rate-limit rows and quota settle.**
`user_quota` settle/release use conditions on the marker state (`user_quota/__init__.py:398,453`), so a worker settling after the partition delete fails the condition rather than recreating a row. `reserve` uses `ADD`/`SET` without an existence condition (`:258`), so a request that passed the middleware before the flip could recreate a row; the verification sweep covers it. Fine as designed; say that the sweep exists for this reason.

---

## 4. Security

**F-S1 (should-fix). The worker is a confused deputy; it must re-validate the request.**
The new Lambda holds `AdminDeleteUser` on the whole pool, `DeleteObject` on `media/*` and `evidence/*`, and delete on the usage table. Anything that can send to its queue can delete any user. Section 5.5 covers the API side (uid from token) but not the worker. Change: (1) only the API role gets `sqs:SendMessage` on the queue; (2) the worker ignores the message's uid claim and requires the users row to be in `deleting` with matching `deletion_request_id`, otherwise acks and drops; (3) the operator CLI path does the same check or uses a separate break-glass role.

**F-S2 (should-fix). The grant list in 5.4 is incomplete and not actually least-privilege.**
Missing for the worker: `dynamodb:Query`/`DeleteItem`/`BatchWriteItem` on `story-<env>-media`, `-stories`, `-understanding`, `-rate-limits` (the API role gets those through `grantReadWriteData`, `story-api-stack.ts:418-421`; the new role needs its own), `GetItem`/`UpdateItem` on the users table for phase checkpoints, `sqs:ReceiveMessage`/`DeleteMessage` on its queue, `s3:ListBucketMultipartUploads`, and CloudWatch Logs for its own group. On the usage table, DynamoDB IAM cannot restrict `DeleteItem` to one uid without `dynamodb:LeadingKeys`, which needs a per-request value; say that the role can delete any user's usage rows and the `__global__` aggregate partition and compensate with F-S1. State that the Cognito ARN uses the pool id from the same context key as the API (no dev fallback, F-C2).

**F-S3 (should-fix). Cognito `Username` for admin calls is unverified.**
The users row stores `cognito_sub`, not the Cognito username (email, or `SignInWithApple_<id>` for federated users). The doc flags `sub` as an assumption and offers "store the username at sign-up" as the fallback, but sign-up is performed by the iOS client directly against Cognito (`CognitoAuthClient.swift:94-111`, `SignUp` with the email as username), so the backend never sees the username at sign-up. If `sub` is not accepted, the worker can do `ListUsers` with `Filter: sub = "<sub>"` instead. Put that fallback in the design, and make the verification a D1 exit criterion on dev, since F1's recovery path depends on it.

**F-S4 (should-fix). Re-authentication for Apple users is weaker than the doc implies.**
`AuthStore.swift:134` sets `prefersEphemeralWebBrowserSession = false`, so the hosted-UI session cookie persists and a "re-auth" through `signInWithApple()` can complete with no prompt, giving a fresh `auth_time` without a fresh credential. The doc marks `prompt=login` as an assumption. Add: use an ephemeral session or `prompt=login`/`max_age` for this flow only, confirm on dev that `auth_time` actually advances, and say what happens if the IdP cannot force it (fall back to blocking the in-app Apple path, which then collides with F-P1).
For email users the design is sound: a fresh OTP needs the inbox. One check: `verifyCode` runs `finishSignIn`, which adopts local content and re-keys it (`AuthStore.swift` `finishSignIn`); the re-auth call must not re-run adoption.

**F-S5 (nit). `auth_time` is not read today.**
`verify_access_token` requires only `exp, iat, iss, token_use` (`auth.py:155-157`). Adding an `auth_time` check needs a new claim read, a test for a refreshed token (its `auth_time` stays at the original sign-in, which is the desired behavior and should be stated), and a defined response when the claim is absent (reject).

**No cross-user path found.** Both new routes take the uid from the verified token only (`auth.py:296-300`); the doc's isolation test (two accounts with identical content) is the right test and `cloud_media_id_for` folds the owner into the id (`media_store/__init__.py:106-109`).

---

## 5. Policy fit

**F-P1 (should-fix). Sign in with Apple token revocation can gate the whole release, not only "the Apple-user path".**
Apple's rule that apps offering Sign in with Apple revoke the user's tokens on deletion applies once Apple sign-in is available to users. The doc says D7 "gates the Apple-user path of D5", but an app version that has Apple sign-in and a deletion path that skips revocation is what App Review looks at. The doc does not establish whether the beta/prod pools have the Apple IdP (`story-auth-stack.ts:117-135`, `appleEnabled`); the iOS app only shows the button when `StoryAuthConfig.appleSignInAvailable`. Change: record the result as a precondition in D5/D8: either Apple sign-in stays off in any build that ships deletion until D7 is resolved, or D7 ships first. Also note that Cognito holds the Apple refresh token, so revocation likely needs the authorization code captured server-side, which is a new contract (the doc already says "research").

**F-P2 (nit). Guideline 5.1.1(v) wording is recalled, not fetched.**
The doc says so itself. The in-app initiation, confirmation step, and subscription messaging match what I know of the guideline. Fetch the current text before D8 and quote the requirement in the doc; I did not verify it either.

**F-P3 (should-fix). Rule "AU evidence is never auto-expired" conflicts with two parts of the doc if read literally.**
(1) Decision 8.3 says "a bounded retention period is allowed" for the trial marker, which implies an automatic expiry mechanism (TTL or sweep). Ling's rule is about AU evidence, and the marker is not AU evidence, but the same rule drives her "no TTL, no lifecycle, no sweeps" preference; frame the retention period as a decision with that tension named. (2) The verification sweep and the Lambda's self-re-enqueue are not expiry, but the doc should say so (F7).
The doc's own handling of AU evidence is consistent with the rule: evidence is removed only through this user-initiated path (section 3), and nothing in D1-D8 adds a TTL.

**F-P4 (should-fix). Proposed privacy text makes claims the code does not support.**
- "Operational logs do not contain your email": `model_call_usage` carries `story_user_id` (F-V6) and WAF logs (beta) carry request metadata (`story-beta-waf-stack.ts:120-125`). The email claim may be literally true (the backend never receives the email; `grep` finds no logging of it), but the sentence invites the wrong reading. Say "logs identify you only by a random account id and expire after 30-90 days".
- "usually it takes minutes": the design includes a 60-minute wait before the final sweep and Cognito deletion (5.3 phase 6), so completion is about 1-2 hours. Say "within a day".
- Provider list: add Unsplash (F-V4) if the section names providers.
- Retained identifiers: see F-D2.
- The text keeps "[35]-day backups" for all tables; only the three auth tables have PITR (`story-auth-stack.ts:188,199,219`). Say which.

**F-P5 (nit). Flags.** The doc adds none, which fits Ling's preference. Two items to confirm: the API needs the queue URL/name as an env var (wiring, not a flag, but it must fail closed with 503 when unset, and that behavior is unspecified), and section 7's optional "kill switch for the first prod week" is a flag in all but name; leave it out unless Ling asks.

---

## 6. Decisions for Ling

**F-D1 (should-fix). Missing decision: ordering relative to the evidence-persistence gate.**
`STORY_EVIDENCE_PERSIST_ENABLED` is ON for dev and beta and OFF for gamma/prod "until a retention/account-deletion policy is approved" (`story-api-stack.ts:540-552`), and beta already stores testers' frames. The doc never says that this design is what unlocks prod persistence, or that persistence must stay OFF in prod until D1-D5 are deployed there. Add a decision (or a stated dependency).

**F-D2 (should-fix). Decision 8.2 states a fact that is not true, and the recommendation depends on it.**
Option (b) is justified as "retains only random ids". The `__apple_txn__` key is `original_transaction_id`, an Apple-issued identifier that links to a purchaser in App Store Connect reports, and `__apple_token__` is a per-account UUID that is linked to the account only while the account exists. Retaining the transaction id is retention of a purchase identifier; the privacy text must disclose it. Also, the doc says under (a) that the same Apple ID "can buy again, creating a second subscription". I did not verify StoreKit behavior; Apple generally does not sell an already-active subscription in the same subscription group twice to the same Apple ID, so the more likely effect is that a re-signed-up paying user is locked out of Plus until expiry (`AccountTokenMismatch`, `master:apple.py:245-247`), not a duplicate charge. Reword, and mark it as unverified.

**F-D3 (should-fix). Decisions 8.3 and 8.4 are recommended without one clear pick.**
8.3 recommends (b) but adds "if V2 ties the trial to a device-held item, then (a)", and says the legal question is for counsel; 8.4 recommends "(a) or (c)". Both are defensible, but give Ling one default and the condition that flips it, and say what happens if she gives no answer (the doc says 8.4 "does not block building the rest"; say the same for 8.3).

**F-D4 (should-fix). Missing decisions.**
1. How the 30-day email promise in the live privacy policy is met until the in-app path ships: who runs the operator CLI, on what environment, with what proof of identity (the doc proposes the CLI but not the identity check for email requests). This is live exposure for beta testers whose frames are already stored.
2. Whether to scan for in-flight edit-plan jobs (F8).
3. Whether to keep the identity-claim row as a tombstone (F4) and whether to keep a deletion ledger for restores (F-V7).
4. Approval items listed only in section 7 ("Needs Ling's approval") are not in section 8: new queue, Lambda and IAM role, and the cross-thread change in `packages/billing/apple.py`. Put them in section 8 so she sees them in one list.
5. Whether Apple sign-in may stay enabled in a build that ships deletion before D7 is done (F-P1).

**F-D5 (nit). Decision 8.11 (no grace period) is well reasoned**, but the stated reason ("a grace period means retained personal data") is true of the design's own tombstone too. Say the real trade-off: no undo versus no extra retention.

**F-D6 (nit). Decision 8.6 "Settled by design" is premature.** See F-C3: `off` mode does write account and token rows.

---

## 7. iOS flow and local wipe

**F10 (blocker). The local wipe cannot be done as written.**
Section 5.6 deletes the SwiftData store files and "relaunch[es] to the signed-out first-run state". An iOS app cannot relaunch itself, and deleting `default.store`/`-wal`/`-shm` while the `ModelContainer` created at launch (`StoryApp.swift:44-62`) is open can corrupt it and crash the session. The existing code comment (`:51-54`) records the owner rule "never delete user data to recover", so this must be explicit. Change: either (a) write a "wipe on next launch" marker, show a completion screen, and perform the file deletion before the container is created at the next cold start (and tell the user to close the app), or (b) delete every model through the context (`modelContext.delete(model:)` for each type in the schema at `StoryApp.swift:28-41`), then reset in-memory stores and navigate to the signed-out state. Also cancel in-flight uploads and downloads before deleting files: `MediaUploadJobModel` and `StorySyncJobModel` queues must be stopped (the doc lists this) and any `URLSession` transfer cancelled; I did not find a background `URLSessionConfiguration`, so foreground cancellation is enough.
Device-only: this is SwiftData-touching and cannot be validated in the sandbox; Ling's device Xcode build is the gate (her standing rule).

**F11 (nit). The "accepted" success point.**
Sign-out happens on `202`, but deletion completes 1-2 hours later and the user can no longer poll (their Cognito session is gone). Say in the confirmation copy that deletion completes within a day, and what the user sees if they sign in again with the same email in that window (a new, empty account or a block: after Cognito deletion a fresh sign-up with that email creates a new user, which is the intended outcome; before it, Cognito is disabled and OTP fails with `accountDisabled`, `CognitoAuthClient.swift:112-124`; make sure that message is not the generic error).

---

## 8. Things I could not verify

- Live data and live configuration in any AWS account (no AWS calls): whether the Apple IdP exists on the beta/prod pools; actual PITR windows; presence of Bedrock invocation logging, AWS Backup, S3 versioning or access logging outside CDK; WAF log contents.
- Whether Cognito admin APIs accept `sub` as `Username`, and whether Cognito access tokens carry `auth_time` and keep it across refresh (standard behavior as I know it, not checked on a dev token).
- Whether Cognito hosted UI honors `prompt=login` / `max_age` for a federated Apple login.
- Apple's current text of guideline 5.1.1(v) and the Sign in with Apple revocation requirements; StoreKit behavior for re-purchasing an active subscription.
- Billing V2's changes (not read, by instruction); the working tree has `M apps/api/app/main.py`, `M apps/api/tests/test_billing_apple_api.py`, `M apps/ios/Story/Story/Data/Auth/AuthStore.swift`, which will move some cited line numbers.
- iOS behavior on a 403 `account deleted` response from `StoryBackend` and the exact set of SwiftData model types to wipe (read from the schema list only).
- Any behavior that depends on the device (wipe, re-auth, Keychain) is untested; the Xcode device build is the authoritative gate.


---

## Round 2 review (2026-11-21)

Sources: an external review Ling forwarded (ChatGPT), checked against the code by kirocrew, plus findings kirocrew found while checking. The round-1 findings above are unchanged. Accepting every round-1 finding did not make the design complete; these are the gaps that remained in revision 1.

| ID | Severity | Failure sequence in revision 1 | Source |
|---|---|---|---|
| R2-1 | blocker | Deletion accepted; in-session model delete runs; the `wipe-pending` marker waits for the next cold start; the user keeps using the signed-out app, creates anonymous Moments or signs into another account; next launch deletes `default.store` holding that new content. Also: no rule for writer shutdown, force-quit between stages, the recovery-fallback store, or which files belong to the open container. | external, confirmed (`StoryApp.swift:44-66`) |
| R2-2 | blocker | 5.3 has the Lambda re-enqueue itself and the resume rule re-enqueue stuck requests, but 5.4 grants `sqs:SendMessage` only to the API and operator roles. The first `DelaySeconds` hop fails with AccessDenied. | external, confirmed |
| R2-3 | blocker | Phase 8 sets `account_status="deleted"`, then writes the ledger object. A crash between them: the next run sees a non-`deleting` row, drops the message, and the ledger object is never written. A later restore cannot replay this account. | external, confirmed |
| R2-4 | blocker | After a PITR restore the users row is `active`; the worker only processes `deleting` rows, so "replay the ledger through the worker" cannot run. Nothing stops restored tables from serving traffic before replay. | external, confirmed |
| R2-5 | blocker | Repeat POST re-send, SQS redelivery, delayed self-messages and the resume rule can run two workers on one account. Both write `deletion_phase` and `pending_global_keys` with plain updates; a stale worker can overwrite progress or drop discovered keys, or finalize early. Waits and failures share one `deletion_attempts` counter, so the resume rule can trip the failure threshold by waiting. | external, confirmed |
| R2-6 | blocker | The API flips `deleting`, the send fails, it returns 503; the client is told "nothing happened" while the resume rule later deletes the account. A lost 202 has the same effect. After Cognito disables the user, the client has no way to ask what happened. | external, confirmed |
| R2-7 | should-fix | Other devices map "403 account deleting/deleted" to wipe, but iOS handles 401/403 generically (`AssetUnderstandingService.swift:276-277`), the auth 403 body has no stable code, and billing already returns 403 `app_account_token_mismatch` (`master:packages/billing/apple.py:69-70`). A generic auth failure could erase unrelated local data. | external + kirocrew |
| R2-8 | blocker | The phase-1 owner scan deletes job rows; a job created by a request in flight at the flip, or a running worker, writes afterwards; verification does not look at jobs or staging; once a job row is deleted its `jobs/<job_id>/` staging prefix cannot be found. | external, confirmed |
| R2-9 | should-fix | The 70-minute wait is treated as proof uploads stopped. A presigned single PUT is valid 60 minutes and S3 checks expiry when the request starts, and `initiate_upload` has no size cap (`media_store/__init__.py:190-233`), so a large single PUT started before expiry can land later. | external + kirocrew |
| R2-10 | should-fix | The design states job rows are reaped "within ~48 h". AWS describes TTL deletion as typically within a few days; TTL and lifecycle are not proof of deletion. | external, confirmed |
| R2-11 | should-fix | Phase 4 deletes global bindings in no stated order. `_resolve_uid` re-binds a transaction from the token index (`master:packages/billing/apple.py:278-292`); if `__apple_txn__` is deleted first and a notification arrives before `__apple_token__` is deleted, the transaction is re-bound to the deleted uid. | kirocrew |
| R2-12 | should-fix | 8.2(a) consequences were not checked against merged Billing V2: binding discovery, in-flight notifications, and the Restore Purchases outcome for a user who deletes and re-registers with an active subscription (`AccountTokenMismatch`, `apple.py:245-247`). | Ling's request; kirocrew |
| R2-13 | should-fix | 8.10/8.18 assume turning Apple sign-in off is the alternative to revocation. Apple TN3194 documents a fallback (delete the data, direct the user to revoke manually, handle the revocation notification). Hiding the button does not help existing Apple users. Also: Apple sign-in is already off in every build and dev has no Apple IdP (verified live), which the design did not state. | external + kirocrew |
| R2-14 | should-fix | Re-authentication can complete as a different account (a different email in the OTP field), whose fresh token is then used for the deletion request. | external, confirmed |
| R2-15 | should-fix | "Request accepted" is presented as success; there is no completion confirmation for an asynchronous deletion. | external, confirmed |
| R2-16 | nit | `reconcile_lost_enqueue` updates a job row without a condition (`edit_plan_jobs/__init__.py:511-516`); racing a delete, it recreates a partial row. | kirocrew |
| R2-17 | should-fix | Privacy text says retained ids "no longer link to your email" and logs identify a person "only by a random account id", while identity claims, backups and unverified WAF logs remain. Section 6 says off-mode accounts have no Apple bindings, contradicting 2.2. | external, confirmed |
