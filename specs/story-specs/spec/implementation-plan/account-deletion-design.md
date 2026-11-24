# YoTale account deletion: design

Status: DESIGN ONLY, for Ling's review. No code, branch or deploy is attached to this document.
Author: kirocrew-worker, 2026-11-20. Scope: iOS app, Python API, AWS (Cognito, DynamoDB, S3, CloudWatch).

**Revision 3 (2026-11-22, D1 implementation).** Ling approved D1 and accepted every recommendation in section 8 as the default (8.19: ask). Changed: section 1 and section 6 (Apple sign-in is live on dev, Google is in progress), 5.2 (discovered keys are child items, not string sets), 8, 10 (D1 built on `feat/account-deletion-d1`), appendix A (a Cognito-linked Apple account now exists on dev).

**Revision 2 (2026-11-21, round-2 review).** Orchestration is now a single scheduled Lambda driven by a durable deletion-request record (no SQS queue). Rewritten: 3, 4, 5 (all), 6, 7, 8, 9, 10, 11; new section 12 (failure-scenario matrix) and appendix A (Apple re-auth and revocation test). Round-2 findings R2-1 to R2-14 are appended to `account-deletion-design-review.md` and answered in `account-deletion-design-review-response.md`. Billing V2 merged to master as PR #141 (`2ea6a1b`, 2026-11-20 23:02 PST), so billing citations below are read from that master, not from a pending branch.

**Revision 1 (2026-11-21):** revised against the first independent review. Blockers F1, F2, F3, F10 fixed; table in the response doc.

## 0. How to read this document

* Every statement about current code carries `path:line` (or a function name where V2 moved lines). `master:` means read with `git show master:<path>` at `2ea6a1b`.
* **Verified in code**, **verified live (read-only)**, **Assumption** and **Unverified** are kept apart. Section 11 lists each.
* Section 8 holds every owner decision. A recommendation or a default-if-unanswered is not an authorization.
* No secret values were read or printed. One read-only AWS call set was made on dev (section 11).

## 1. Where things stand today (verified)

* No account deletion exists. `evidence_store.delete_for_owner` is tested and has no caller (`packages/evidence_store/__init__.py:296-309`; docstring says "audit/design only — unwired", `:33-36`). The only deletion route is per-Moment evidence, `DELETE /v1/evidence/{moment_id}` (`apps/api/app/main.py:1044`).
* Media bucket has no expiry for completed objects (`infrastructure/cdk/lib/story-api-stack.ts:229-233`) and `removalPolicy: RETAIN` (`:234`). The API role may not delete `media/*` objects (`:424-428`); it may delete `evidence/*` (`:435-441`).
* The privacy policy (https://lingzhang1.github.io/yotale-legal/privacy.html, effective 2026-11-19) promises deletion by email to privacy@yotale.ai within 30 days (sections 1 and 7).
* Sign-in: email one-time code (Cognito `USER_AUTH` + `EMAIL_OTP`, `apps/ios/Story/Story/Data/Auth/CognitoAuthClient.swift:94-139`) and "Continue with Apple" through the Cognito hosted UI (`Features/Auth/SignInView.swift:35-38,142-144`, `Data/Auth/AuthStore.swift:110-117`). **Apple sign-in is live on dev only (2026-11-22):** `STORY_APPLE_SIGNIN_AVAILABLE = 1` in `apps/ios/Story/Config/Development.xcconfig`, `0` in `Beta.xcconfig` (PRs #147 and #149; #149 makes the hosted-UI Apple sign-in fresh after sign-out). **Verified live (read-only, 2026-11-22):** the dev pool `us-east-1_AzfHOEdA5` has the `SignInWithApple` provider and 1 user in `EXTERNAL_PROVIDER` status. Beta Apple sign-in is held by sign-in plan decision F4 until deletion handles Apple users. Google: an optional Google IdP is in CDK (PR #151, inert without `googleSecretName`); the iOS path is PR #152 (open). Beta and prod pools: **unverified** (needs `aws sso login --profile yotale-beta`). Same-email accounts across methods stay separate (sign-in plan F1), so deletion always removes exactly the account that is signed in.

## 2. Inventory of stores holding user data

One account = one `story_user_id` (random UUID, minted at first sign-in, `apps/api/app/auth.py:212-240`). Table names are `story-<env>-...`.

### 2.1 Cloud stores

| # | Store | Key shape | What it holds | Enumerate one user's rows | Evidence |
|---|---|---|---|---|---|
| 1 | Cognito user pool `story-<env>-users` | username = email (or federated Apple user), attribute `sub` | email, federated Apple identity, sessions/refresh tokens | `AdminGetUser`; the users row stores `cognito_sub` | `story-auth-stack.ts:50-59`; `auth.py:233` |
| 2 | DynamoDB `identity-claims` | PK `claim_key` = `cognito#<sub>` | `story_user_id`, provider, created_at | `GetItem cognito#<sub>`. Only `cognito#` claims have a writer (`auth.py:214,227`) | `story-auth-stack.ts:184-190`; PITR on |
| 3 | DynamoDB `users` | PK `story_user_id` | `cognito_sub`, `account_status`, `beta_access_status`, `created_at`, optional `verified_email` (`resolve(sub)` is called without it, `auth.py:299-300`) | `GetItem` by uid | `story-auth-stack.ts:195-212`; PITR on |
| 4 | DynamoDB `media` | PK `story_user_id`, SK `cloud_media_id` | cloud originals, generated MP4 backups, music, ai_artifacts, evidence manifests (SK `evidence#<moment_id>`) | paginated `Query PK=uid`. `MediaStore.list_for_owner` does not paginate (`packages/media_store/__init__.py:181-187`): fix before reuse | `story-api-stack.ts:239-245` |
| 5 | S3 media bucket `media/<uid>/<cloud_media_id>/original` | account-scoped | Moment originals, generated MP4s, music, ai_artifacts | `ListObjectsV2` prefix `media/<uid>/` | `media_store/__init__.py:112-114` |
| 6 | S3 media bucket `evidence/<uid>/<blob_cmid>/frames.pack` | account-scoped | packed JPEG frames of the user's footage | prefix `evidence/<uid>/` | `evidence_store/__init__.py:93-96`; `STORY_EVIDENCE_PERSIST_ENABLED` ON dev/beta, OFF gamma/prod (`story-api-stack.ts:540-552`) |
| 7 | DynamoDB `stories` | PK `story_user_id`, SK `story_id` | Story documents | paginated Query (`packages/story_store/__init__.py:125`) | `story-api-stack.ts:252-257` |
| 8 | DynamoDB `understanding` | PK `story_user_id`, SK `moment_id` | saved AU per Moment; music favourites under SK `__music_favorites__` | paginated Query | `understanding_store/__init__.py:3-16`; `music_favorites.py:9-29` |
| 9 | DynamoDB `user-usage` | PK `story_user_id`, SK `quota_period` | quota counters and billing rows (2.2) | paginated `Query PK=uid` | `story-auth-stack.ts:214-221`; PITR on |
| 10 | DynamoDB `rate-limits` | PK `story_user_id`, SK `rl_key`, `ttl` | throttle counters | Query | `throttle.py:195-198` |
| 11 | DynamoDB `edit-plan-jobs` | PK `job_id`; attribute `owner` | job rows (request refs, results, `_evidence_diag`), `expires_at` = 6 h (`packages/edit_plan_jobs/__init__.py:79`) | Scan filtered on `owner` (the code already scans, `:495,543`) | `story-api-stack.ts:187-193` |
| 12 | S3 staging bucket `jobs/<job_id>/body.json`, `jobs/<job_id>/sheets/<mid>.jpg` | per job, not per user | request body and contact-sheet JPEGs | only via job ids from row 11 (`edit_plan_jobs/__init__.py:188-199`) | 1-day lifecycle backstop (`story-api-stack.ts:208-215`) |
| 13 | SQS edit-plan queue + DLQ | job id | job ids (**Assumption:** no content) | n/a | DLQ 14 days (`story-api-stack.ts:196-198`) |
| 14 | CloudWatch Logs | log lines | `model_call_usage` carries `story_user_id`, `story_id`, `job_id` (`packages/model_gateway/__init__.py:226-262`; docstring at `:238` contradicts this, D1 fixes it) | not enumerable per user; 30/60/90-day retention (`infrastructure/cdk/lib/observability.ts:55-64,93-98,102-103`) | |
| 15 | WAF logs | request metadata, likely IP addresses (**Unverified**) | | 30-day retention (`story-beta-waf-stack.ts:120-125`) | |

PITR is on for tables 2, 3, 9 (`story-auth-stack.ts:188,199,219`) and not found for 4, 7, 8. A PITR restore always creates a **new** table; it never overwrites the live one. Restore handling is section 5.8.

TTL and lifecycle (rows 10-12) are **not** proof of deletion. AWS describes TTL deletion as typically happening within a few days, and S3 lifecycle runs on its own schedule. The worker deletes these explicitly and verifies (5.5); TTL and lifecycle are only backstops.

### 2.2 Billing rows (read from master `2ea6a1b`, Billing V2 merged)

Per-account rows in `user-usage` under PK = uid, SK prefix `billing#` (live) or `billing-shadow#` (observe) (`master:packages/billing/ledger.py:47,131`):

* `billing#entitlement`: plan, status, trial, period, counters, `b_orig_txn`, `b_gf_cutoff`, and new in V2 the `b_sub_*` fields that record an Apple subscription beside a beta/admin plan (`parse_entitlement`, `apply_subscription` at `:625`). Same row, same key.
* `billing#account`: `b_apple_token` (StoreKit `appAccountToken`), created on demand (`get_or_create_apple_account_token`, `:215-219`).
* `billing#<reservation>` / `billing#m#<moment>~...`: operation records, including cached analysis results derived from footage. V2 adds `b_unmetered` on the record; same keys.
* Quota rows from `user_quota` in the same partition.

The worker deletes the **whole partition**, whatever the SK, so V2's new attributes need no special handling.

**Every billing mode writes the token binding.** `entitlement_payload` calls `get_or_create_apple_account_token` in `off` mode when the Apple service exists (`master:apps/api/app/billing_gate.py:412`) and in observe/enforce (`:426`). That writes `billing#account` and the global `__apple_token__` row. So any account that opened the app has a global binding in any mode.

Global partitions (`master:packages/billing/ledger.py:48-50`):

* `__apple_txn__` / `billing#txn#<original_transaction_id>` -> `b_uid` (`bind_apple_transaction`, `:676-686`; read by `apple_txn_owner`, `:702-703`).
* `__apple_token__` / `billing#token#<appAccountToken>` -> `b_uid` (`index_apple_token`, `:689-697`; `uid_for_apple_token`, `:699-700`).
* `__apple_evt__` / `billing#evt#<uuid>` -> type, outcome, created. **No uid**; not per-user data.

**Binding discovery (verified in code on master `2ea6a1b`).** V2 did not change `packages/billing/apple.py`. `submit_transaction` still binds the transaction before checking it is live (`master:packages/billing/apple.py:237-256`), so an account can own an `__apple_txn__` row that `b_orig_txn` never mentions. Discovery is therefore: token from `billing#account`, `b_orig_txn` from the entitlement row, **and** a Query of `__apple_txn__` filtered on `b_uid = <uid>` (always run). Re-run this check at release if billing code changes again (R2-12).

**Rebinding hazard (new, R2-11).** `_resolve_uid` re-binds a transaction to the uid found through the token index when the transaction has no binding (`master:packages/billing/apple.py:278-292`). If the worker deleted the `__apple_txn__` row while the `__apple_token__` row still existed, a notification arriving in between would recreate the transaction binding for the deleted uid. The worker deletes the **token binding first**, then transaction bindings (5.4 phase `billing`).

### 2.3 Device (iOS)

* SwiftData: `Application Support/default.store` (+ `-shm`, `-wal`), opened at `apps/ios/Story/Story/App/StoryApp.swift:44-47`; on migration failure a separate `Application Support/recovery-fallback.store` (+ `-shm`, `-wal`) is opened instead and `default.store` is preserved untouched (`:48-66`). Schema of 22 model types at `:25-43`.
* Media under `Documents/media/` (`Media/Playback/MediaStore.swift:10-31`), rendered outputs, previews, My Music, render scratch; `Caches/pending-edit-plan-submits/` (`Domain/Creation/PendingOperationRecovery.swift:131-150`); `tmp/` users (`Features/StoryHome/PhotoImportRunner.swift:240`, `Media/Sync/AIArtifactStore.swift:84,109`, others in revision 1).
* Keychain token blob (`Data/Auth/KeychainStore.swift:38-`); `UserDefaults` keys including the AU diagnostics ring buffer (`AUStepDeadline.swift:52-74`).
* No App Group, shared Keychain group, CloudKit or iCloud KV. Device backups and Photos-library copies (`Media/Photos/PhotosSaver.swift:43-44`) are outside our reach; the copy says so.
* Sign-out today keeps local content (`Data/Auth/AuthStore.swift:164-176`).
* Upload writers: `MediaUploadQueue` and `GeneratedOutputBackupQueue` use a single presigned PUT up to 16 MiB and S3 multipart above it (`Media/Upload/MediaUploadQueue.swift:185-188`, `GeneratedOutputBackupQueue.swift:153-156`). The server does not enforce that split (`initiate_upload` accepts any size, `packages/media_store/__init__.py:190-233`); see 5.6.
* iOS treats 401 and 403 generically today (`Data/Contracts/AssetUnderstandingService.swift:276-277`; billing maps 403/409/422 to `.rejected(code)`, `Data/Billing/BillingService.swift:85-89`). The billing path already returns a 403 (`app_account_token_mismatch`, `master:packages/billing/apple.py:69-70`), so "403" alone must never mean "account deleted" (5.7).

### 2.4 Outside our systems

OpenAI and Google (frames/text for analysis), Unsplash (scene-image queries), the music provider (search terms), Bedrock (client still built at `model_gateway/__init__.py:337`; invocation logging unknown), Apple (purchases), SES (suppression list). Their retention is decision 8.9. Deleting on our side does not recall copies already sent.

## 3. What is deleted, what is retained, and why

Principle: delete everything we can attribute to the person; keep only pseudonymous records needed to keep the deletion from being undone. Ling's rule holds: no TTL, lifecycle or sweep is added for AU evidence. The worker's waits, verification passes and final check run only for an account whose owner asked for deletion; they complete that request and are not expiry.

| Data | Action | Notes |
|---|---|---|
| Cognito user | delete, after verification (phase `cognito`) | until then the account can be located |
| Tables 4, 7, 8 and S3 `media/<uid>/`, `evidence/<uid>/` | delete | no bucket versioning found |
| Table 9 partition `<uid>` | delete the whole partition | includes cached analysis results |
| Table 10 rows | delete | |
| Table 11 rows and table 12 staging for the user's jobs | delete during verification, by recorded job id | 5.5 |
| `__apple_token__`, `__apple_txn__` bindings | delete (8.2(a), provisional v1) | token first (2.2) |
| `__apple_evt__` | keep | no uid |
| Identity claim `cognito#<sub>` -> uid | **keep** (8.13) | pseudonymous; blocks a still-valid token from minting a new account |
| Users row | **keep as tombstone**: `story_user_id`, `account_status="deleted"`, `deleted_at`, `deletion_request_id`; `cognito_sub` and `verified_email` removed | never deleted |
| Deletion request record (5.2) | **keep** | the source of truth and the restore ledger; holds uid, request id, receipt hash, timestamps, phase, job ids, global keys; no email, no content |
| CloudWatch and WAF logs | not rewritten; expire at 30/60/90 and 30 days | |
| PITR backups of tables 2, 3, 9 | expire with the PITR window (**Assumption:** 35 days) | |
| Device data | deleted on the requesting device (5.7) | other devices: 5.7 |
| Photos library, device backups, provider copies | not deletable by us | stated in copy and policy |

All retained records are **pseudonymous**, not anonymous: a uid, `cognito_sub`, request id and job ids can be linked to the person by anyone who also holds a matching log line, WAF record, backup or provider record. Section 9 says this.

## 4. Active subscription handling

App Store Review Guideline 5.1.1(v) requires in-app account deletion; the exact current wording must be fetched and quoted before D8 (not re-fetched this pass). Apple subscriptions can only be cancelled by the user.

1. Detect an active or grace subscription on device from StoreKit current entitlements; also show V2's `capabilities.subscription.status` / `ends_at` when available (`master:packages/billing/ledger.py`, `entitlement_view`).
2. If active: a skippable step before the final confirmation: deletion does not cancel the subscription; Manage subscription (`Features/Billing/PlusSubscriptionView.swift:41`). Deletion is never blocked.
3. The entitlement is deleted with the account. The paid remainder is lost.
4. **Known v1 limitation under 8.2(a), to verify before release (R2-12):** a user who deletes and re-registers while the old subscription is still active gets a new account and a new `appAccountToken`. Restore Purchases posts the old transaction, whose token is the old account's, so `submit_transaction` raises `AccountTokenMismatch` (HTTP 403, `app_account_token_mismatch`, `master:packages/billing/apple.py:245-247`, `:69-70`). From code, the new account cannot use the old subscription until it expires. Whether StoreKit lets that Apple ID buy the same product again while it is active is **unverified** (Apple generally refuses a second active subscription in one group). The deletion copy tells the user to cancel first. Sandbox test in 7.3.
5. Notifications after deletion: with both bindings deleted, `_resolve_uid` returns `None` and `_apply` returns `unmatched`, acknowledged and journalled (`master:packages/billing/apple.py:278-306`). No code change needed for 8.2(a). A notification that resolved the uid before the bindings were deleted can recreate `billing#entitlement` (`apply_subscription` -> `ensure_entitlement`, `ledger.py:194,625`); verification catches it (5.5). Reconciliation (`apply_status`) checks `apple_txn_owner == uid` first (`apple.py:331-336`), so it cannot write once the binding is gone.

## 5. Flow

### 5.1 iOS UX

Entry: "Delete Account" in the Home header account menu (`Features/Home/HomeView.swift:108-118`).

1. **What will be deleted / what stays** (plain list, including other signed-in devices: 5.7).
2. **Subscription step** (section 4).
3. **Re-authentication, bound to the current account.** Email users: the email field is pre-filled with the current account's email and cannot be edited; a fresh code is requested through a new entry point that returns tokens only and never runs `finishSignIn` adoption or re-keying (`AuthStore.swift:190`). Before submitting, the client checks that the fresh token's `sub` equals the current session's `sub`; on mismatch it discards the fresh tokens and stops. Apple and Google users: a fresh hosted-UI sign-in with the same provider (ephemeral session, as PR #149 does for Apple), with the same `sub` check; if appendix A passes, Apple users use the native sheet instead, and the server checks the Apple `sub` against the Cognito user's linked identity. For federated users "fresh" is the access token's `auth_time`; whether the IdP reuses a live Apple or Google session without a prompt is a D5 device check.
4. **Final confirmation**: type DELETE (localised), destructive button. Copy: what stays; "deletion usually finishes within two hours; a final check runs a day later"; signing in with the same email during deletion shows "This account is being deleted"; afterwards the same email creates a new, empty account.
5. **Submission and lock** (5.7): once the server has accepted, the app enters the deletion lock screen and does not leave it in this process.

### 5.2 The deletion request record (source of truth)

New DynamoDB table `story-<env>-account-deletions`, PK `pk` (string), SK `sk` (string). PITR **on** (protection against accidental loss; a PITR restore creates a new table, so restoring the auth tables never rolls this table back), deletion protection on, `RETAIN`.

Three item types:

* **Request item**, `pk = <story_user_id>`. At most one per account, never deleted.
  * Identity: `request_id` (UUIDv4 chosen by the client), `receipt_hash` (SHA-256 of the client's receipt secret), `accepted_at`.
  * Progress: `state` (`active` | `completed` | `closed`), `phase` (5.4), `phase_seq` (integer, strictly increasing).
  * Timing: `quiesced_at`, `not_before`, `next_run_at`, `clean_passes`, `completed_at`, `final_check_at`.
  * Lease: `lease_owner`, `lease_until`.
  * Failure: `fail_count`, `last_error_code`, `stalled_alerted_at`.
  * Results: `late_found` (count from the final check).
* **Discovered-key items**, `pk = <story_user_id>`, `sk = job#<job_id>` or `gkey#token#<t>` / `gkey#txn#<id>`. Written with an idempotent `PutItem`, never deleted. Separate items make concurrent discovery a union by construction and keep the request item far below the 400 KB limit however many jobs an account has. (Revision 2 used string sets on the request item; changed in D1.) Below, `job_ids` and `global_keys` mean these items.
* **Receipt pointer**, `pk = receipt#<request_id>`, `sk = pointer` -> `uid`. Makes `request_id` unique (conditional put) and lets the status route find the request without a token or a GSI.

The users row `account_status` (`deleting` / `deleted`) is the request's projection onto the auth gate. If the two disagree, the request item wins.

### 5.3 API contract and the acceptance boundary

`POST /v1/account/deletion`, authenticated, uid from the token only. Body `{"confirm":"DELETE","request_id":"<uuidv4>","receipt_hash":"<hex sha256>"}`. The client generates `request_id` and a 256-bit `receipt_secret`, sends only its hash, and persists both before sending (5.7).

Checks, in order: rate limit (new class, e.g. 3 per hour); fresh login (email: access-token `auth_time` within 5 minutes, absent means `401 reauth_required`; Apple: appendix A); `confirm` value.

**Acceptance boundary = one `TransactWriteItems` commit** (API role):

1. Put request item `pk=<uid>`, `state="active"`, `phase="quiesce"`, `phase_seq=1`, `next_run_at=now`, condition `attribute_not_exists(pk)`.
2. Put receipt pointer `pk=receipt#<request_id>`, condition `attribute_not_exists(pk)`.
3. Update users row `account_status = "deleting"`, `deletion_request_id`, condition `attribute_exists(story_user_id) AND account_status = "active"`.

Outcomes:

| Situation | Response | Meaning to the client |
|---|---|---|
| Commit succeeded | `202 {"state":"accepted","request_id"}` | accepted |
| Condition 1 failed, existing request has the same `request_id` | `202` with its current state | accepted (idempotent retry) |
| Condition 1 failed, different `request_id` (another device asked first) | `409 {"error":"deletion_already_requested"}` | accepted (by another device); this receipt will not work |
| Validation, re-auth, rate-limit failure | `400` / `401` / `429` | nothing happened (no write attempted) |
| Transaction cancelled for another reason, or DynamoDB error | `503` | **unknown**: resolve through the status route |
| Timeout or lost connection | none | **unknown**: resolve through the status route |

The worker is never contacted from the API; there is no enqueue that can fail after acceptance.

**Status routes.**

* `GET /v1/account/deletion` (authenticated, `DELETION_ROUTES` bypass below) returns `{state, phase_group, completed_at}` for the caller's own request.
* `POST /v1/account/deletion/status` (**public**, added to `PUBLIC_ROUTES`, `auth.py:384-389`), body `{"request_id","receipt_secret"}`. Server reads the pointer, reads the request item, compares `SHA-256(secret)` to `receipt_hash` in constant time, and returns `{"state":"accepted"|"in_progress"|"completed", "completed_at"}`. Unknown id and wrong secret return the same `404 {"error":"not_found"}`. It reveals nothing about any account to anyone without the 256-bit secret; it needs no token, so it works after Cognito disables the user. Throttled per source IP (WAF rate rule or a public-route class). POST, so the secret never lands in a URL or access log.

**Status gate (revision-1 F3, unchanged).** `_principal_from_token` gets `allow_status` (default `{"active"}`); `auth_boundary` passes `{"active","deleting"}` only for `(POST|GET) /v1/account/deletion`. Every other route returns `403 {"detail":"account deleting","error":"account_deletion_in_progress"}` or `{"detail":"account deleted","error":"account_deleted"}`. Today the body is only `{"detail": f"account {status}"}` (`auth.py:255-261`); the stable `error` codes are new and are what the client keys on (5.7). `_account_status` fails closed for a claim with no users row (`auth.py:205-206` today returns active).

### 5.4 The scheduled worker

One Lambda `story-<env>-account-deletion`, triggered only by an EventBridge rule every 5 minutes (pattern: `story-api-stack.ts:400-407`). Target retry attempts 0 and maximum event age 5 minutes, so EventBridge does not stack retried invocations. No queue, no self-enqueue, no reserved concurrency (the beta account's concurrency quota of 10 made reserved concurrency fail once; the lease below is the mutual exclusion).

**Run.** Lambda timeout 300 s. Run budget 240 s: no new phase starts after 240 s of wall time. Each run:

1. Scan the request items with `state IN (active, completed) AND next_run_at <= now` (pointer items filtered out). The table holds one item per deletion ever, so a Scan is fine now. shortcut: add a sparse GSI on `next_run_at` when the table reaches thousands of items.
2. For each due request, oldest `next_run_at` first: acquire the lease, then run ready phases one after another until a phase asks to wait, a phase fails, or the budget is spent. Release the lease with the new `next_run_at`.
3. Emit metrics (5.9).

**Lease (conditional).** Acquire:

```
UpdateItem pk=<uid>
SET lease_owner = :run_id, lease_until = :now + 360
CONDITION state IN ("active","completed") AND next_run_at <= :now
          AND (attribute_not_exists(lease_until) OR lease_until < :now)
```

`run_id` is the Lambda request id. 360 s exceeds the 300 s Lambda timeout, so a live run never loses its lease; a crashed run's lease expires within 6 minutes and the next scheduled run takes over.

**Phase advance (monotonic, owner-checked).** Every state write after acquisition is:

```
CONDITION lease_owner = :run_id AND lease_until > :now AND phase_seq = :expected_seq
SET phase = :next, phase_seq = :expected_seq + 1, ...
```

A stale run (lease expired and taken over) fails its next conditional write and exits without further writes. Its earlier side effects are deletes only, which are idempotent and cannot recreate data. `job_ids` and `global_keys` are separate items written with an idempotent `PutItem`, so two runs cannot drop each other's discoveries. `quiesced_at` and `not_before` are set with `if_not_exists`, once. The finalize write to the users row carries `attribute_exists(story_user_id)`, so no write can create a users row (5.4 phase `finalize`).

**Phases.** Each phase is idempotent and safe to re-run from its start.

| seq | phase | Work | Next |
|---|---|---|---|
| 1 | `quiesce` | `AdminDisableUser`, `AdminUserGlobalSignOut`. Set `quiesced_at`, `not_before = quiesced_at + 70 min` (if not set). Scan `edit-plan-jobs` for `owner = uid`; record each `job_id`; call `request_cancel` on non-terminal jobs (`edit_plan_jobs/__init__.py:473-478`). Job rows and staging are **not** deleted here. | 2 |
| 2 | `content` | Paginated delete of table 4 rows; `ListObjectsV2` + `DeleteObjects` on `media/<uid>/` and `evidence/<uid>/` (prefix listing, not manifests, because `delete_for_moment` swallows S3 errors, `evidence_store/__init__.py:288-293`); `ListMultipartUploads` with those prefixes and `AbortMultipartUpload` each; paginated delete of tables 7 and 8. | 3 |
| 3 | `billing` | Read identifiers (2.2: token, `b_orig_txn`, `__apple_txn__` Query on `b_uid`); record their keys; delete `__apple_token__` rows, **then** `__apple_txn__` rows, for every key in `global_keys` (not only the ones just read); then delete the `<uid>` partition (paginated). Never imports `billing_gate`. | 4 |
| 4 | `ratelimit` | Delete table 10 rows. | 5 |
| 5 | `wait` | If `now < not_before`, set `next_run_at = not_before` and release (a wait, not a failure). | 6 |
| 6 | `verify` | One verification pass (5.5). If anything was found, delete it and set `clean_passes = 0`; else `clean_passes += 1`. Until `clean_passes = 2`, set `next_run_at = now + 10 min` and release (a wait). | 7 |
| 7 | `cognito` | `AdminDeleteUser`; `UserNotFoundException` is success. Username: try `sub`; fall back to `ListUsers` with `Filter: sub = "<sub>"` (D1 check). `cognito_sub` is read from the users row, which keeps it until phase 8. | 8 |
| 8 | `finalize` | (a) Users row -> tombstone, condition `attribute_exists(story_user_id) AND account_status IN ("deleting","deleted")`. (b) Request item `state="completed"`, `completed_at` (if not set), `final_check_at = completed_at + 24 h`, `next_run_at = final_check_at`. | 9 |
| 9 | `final_check` | At `final_check_at`: one more verification pass; delete anything found; record `late_found`; alert if > 0 (5.9); `state="closed"`. | done |

**Crash at each finalize boundary.** Before (a): re-run does (a) and (b). Between (a) and (b): the users row is already a tombstone, the condition accepts `deleted`, (a) is a no-op, (b) runs. After (b): the request is `completed`; nothing to recover. The request item is the ledger, so there is no separate ledger write that can be lost (revision-1 phase 8 wrote the users row first and an S3 ledger object second, and a crash between them lost the ledger, R2-3). If Cognito is already deleted when phase 7 re-runs, `UserNotFoundException` is success; if `cognito_sub` is somehow missing, the `ListUsers` fallback is skipped and phase 7 succeeds only when `AdminGetUser` by the recorded sub returns not-found.

**Retry schedule.** A phase that raises (AWS error, unexpected count) does `ADD fail_count 1`, `SET last_error_code`, `next_run_at = now + backoff(fail_count)` and releases the lease. Backoff: 5, 15, 30, 60, 120 minutes, then every 6 hours. Waits (phase 5, the spacing between verification passes, `final_check_at`) never touch `fail_count`. A phase that succeeds resets `fail_count` to 0. Automatic retries never stop: the request is the user's and every phase is idempotent. The alert below is how a person learns about it.

**Stall alert.** Two independent signals:

* `fail_count >= 5` (about 4 hours of failures): the run sets `stalled_alerted_at` once and emits `AccountDeletionStalled=1`.
* Every run emits `AccountDeletionOverdue` = number of `active` requests with `accepted_at` older than 6 hours. That catches a bug that never raises (for example a request that never becomes due).

Alarms: `AccountDeletionStalled >= 1`, `AccountDeletionOverdue >= 1`, and `AccountDeletionHeartbeat` missing for 30 minutes (each run emits 1; missing data is breaching), which catches a disabled rule or a Lambda that fails at import. The Observability thread owns the alarm stack; the request goes to it (D2). An operator can run `resume --uid` (5.10), which uses the same lease, so it cannot run at the same time as a scheduled run.

### 5.5 Verification of late writes (jobs, staging, uploads, billing)

The 70-minute `not_before` is a **delay before verification**, not proof. It is chosen so the known writers have stopped by the time verification starts:

| Writer | Why it can write after the flip | Bound or guard |
|---|---|---|
| Any API request | passed the status gate just before the flip | finishes in seconds; caught by the first verification pass |
| Access tokens | verify offline for up to 60 min (`story-auth-stack.ts:167`; `AdminUserGlobalSignOut` revokes refresh tokens only) | every route except the two deletion routes is refused by the status gate, so a valid token cannot write; the deletion routes write only the request item |
| Presigned single PUT (`UPLOAD_URL_TTL_SECONDS = 3600`, `media_store/__init__.py:83`) | S3 checks expiry when a request starts, so an upload started before expiry can finish later | release dependency **G1**: the API refuses (413) a single-PUT initiate above 16 MiB (`MULTIPART_THRESHOLD`) for Moment originals and generated videos, which the app already sends as multipart above it. My Music and ai_artifact uploads are single-PUT only in the app (`MyMusicCloudBackup.swift`, `AIArtifactStore.swift`), so they are NOT capped (a cap would break large My Music files); a late one is caught by the verification passes and the 24 h final check |
| Multipart upload | parts can be uploaded with presigned part URLs | the object exists only after `CompleteMultipartUpload`, which only the API calls (`complete_multipart`, `:429-457`), behind the gate. Verification aborts every multipart upload under the user's prefixes; parts sent after an abort fail |
| Edit-plan worker | a run that already held a lease at the flip | `claim_lease` only claims `queued` or expired `running` (`edit_plan_jobs/__init__.py:437-458`); phase 1 moved the user's jobs to `cancel_requested`, so no new run starts; a running lease lasts at most `LEASE_SECONDS = 900` (`:81`). Its `complete` write requires `running` and fails. It can still settle quota and billing (`worker.py` `_quota_settle_job`, `_billing_finish_job`), which recreates rows in the `<uid>` partition |
| A job created by an in-flight request at the flip | created after the phase-1 scan | found by the verification rescan; it is `queued`, so it can be claimed and run (≤ 2 receives × 960 s, `story-api-stack.ts:199-203`); cancelled by the rescan; 70 min exceeds that bound |
| Quota-orphan sweep and enqueue reconcile | run every minute over job rows (`edit_plan_jobs/__init__.py:487-581`) | `sweep_quota_orphans` can release quota into the `<uid>` partition while job rows exist; `reconcile_lost_enqueue` updates without a condition and can recreate a partial job row (`:511-516`). Guard **G2**: give that update `attribute_exists(job_id)`. Job rows are deleted in verification, and the second clean pass runs at least 10 minutes later |
| Apple notification or reconcile | resolved the uid before the bindings were deleted | seconds; caught by verification. After the bindings are gone, both paths stop (section 4 item 5) |
| Billing gate token creation | an in-flight entitlement request | seconds; verification re-reads identifiers |

**One verification pass** (phases 6 and 9):

1. Rescan `edit-plan-jobs` for `owner = uid`; record new ids; `request_cancel` any non-terminal job.
2. For every id in `job_ids`: delete `jobs/<id>/` from the staging bucket (prefix list + delete; the key shape is fixed, `edit_plan_jobs/__init__.py:191`, so the prefix stays derivable after the row is gone), then delete the job row.
3. Re-read billing identifiers; record them; delete token bindings, then transaction bindings, for all `global_keys`.
4. Count and delete: tables 4, 7, 8, 9 (partition `<uid>`), 10; `__apple_token__` and `__apple_txn__` rows with `b_uid = uid`; S3 `media/<uid>/`, `evidence/<uid>/`; multipart uploads under those prefixes (abort); job rows for `job_ids`; staging prefixes for `job_ids`.
5. The pass is **clean** only when every count in step 4 was zero before deletion.

**Release dependencies (writer guards).** G1 (single-PUT size cap in `media_store.initiate_upload` / `POST /v1/media/initiate`), G2 (conditional update in `reconcile_lost_enqueue`). Optional G3: the edit-plan worker re-checks the owner's `account_status` before settling quota and billing; not required because verification removes what it writes, but it shortens the residue. G1 and G2 ship before or with D3.

**Definition of completed.** The request is **completed** when phases 1-8 are done: two clean verification passes at least 10 minutes apart, both after `not_before`, then Cognito deletion and the tombstone. **Closed** is the final check 24 hours later. The UI and privacy text promise completion "usually within two hours" (70 min wait + two passes + scheduling slack) and say a final check runs a day later. A request that has not completed within 6 hours alerts (5.4).

### 5.6 Billing modes

Deletion works in `off`, `observe` and `enforce`. Every mode can hold a token binding (2.2). The worker addresses DynamoDB directly with the key shapes in 2.2 and never calls `billing_gate`, `apple_service` or the Apple verifier, so `None` services and modes are irrelevant. Zero rows is success.

### 5.7 Client protocol and local wipe

**Files** in `Library/AccountDeletion/` (not under `Documents/`, `Caches/`, `tmp/` or `Application Support/`, so the wipe never removes them; file protection `completeUntilFirstUserAuthentication`):

* `request.json` = `{request_id, receipt_secret, created_at, stage}`. A **pending network request record**. It does not authorize any wipe.
* `wipe-intent` = `{request_id, created_at}`. The **instruction to wipe**. Written only after acceptance is established, by write-to-temp then atomic rename.

**Submission.**

1. Write `request.json` (`stage="submitting"`). Then POST.
2. `202` or `409 deletion_already_requested`: acceptance established. Write `wipe-intent`, then start the lock (below).
3. `400`/`401`/`429`: nothing happened. Delete `request.json`; show the error.
4. `503`, timeout, lost connection, or the app was killed: outcome unknown. Show a blocking "Checking your deletion request" screen and call the public status route with the receipt (backoff 2, 5, 10, 30 s, then every minute while open):
   * `accepted` / `in_progress` / `completed`: acceptance established; go to 2.
   * `not_found` (a definitive server answer): the transaction did not commit. Offer "Try again" (same `request_id`, idempotent) or "Cancel" (delete `request.json`, account unchanged).
   * offline: stay on the screen with retry. The user cannot create content or sign in while the outcome is unknown, because creating content now and wiping later is the failure this protocol prevents.
5. On every launch, `StoryApp.init` checks `Library/AccountDeletion/` **before** creating the `ModelContainer`: `wipe-intent` present -> cold-start wipe; only `request.json` with `stage="submitting"` -> the checking screen in 4.

Token expiry or Cognito disablement does not affect recovery, because the status route uses the receipt, not a token. The same `request_id` can be retried any number of times.

**Wipe lifecycle on the requesting device.** It completes before any new content or sign-in is possible.

| Stage | Action | Force-quit or failure here |
|---|---|---|
| L1 | `wipe-intent` written | next launch runs the cold-start wipe |
| L2 | Root view replaced by `DeletionLockView`. Sign-in, capture, import, Story creation and settings are unreachable in this process; deep links and background-task handlers check `AccountDeletionGate.isLocked` (= `wipe-intent` exists) and return | same |
| L3 | Stop writers and **await** them: `MediaUploadQueue`, `GeneratedOutputBackupQueue`, download/restore, Story sync, AU queue, pending-operation recovery, render; `URLSession.invalidateAndCancel()` and wait for invalidation | same; nothing destructive has run yet |
| L4 | In-session: delete every row of the 22 model types through the context, save | next launch deletes the store files anyway |
| L5 | Delete `Documents/`, `Caches/`, `tmp/` and everything in `Application Support/` **except the files of the store that is open** (`default.store`/`-shm`/`-wal`, or `recovery-fallback.store`/`-shm`/`-wal` on the migration-failure path; the store that is *not* open is deleted now); Keychain clear; sign out; `BillingStore.reset()`; remove the `UserDefaults` domain, restore the language allow-list | each step is idempotent; next launch repeats all of them |
| L6 | Lock screen: "Your account is being deleted. Close YoTale to finish removing data from this iPhone." Polls the status route while open | same |
| Cold start | In `StoryApp.init`, **before** any `ModelContainer` exists: delete `default.store`, `default.store-shm`, `default.store-wal`, `recovery-fallback.store`, `-shm`, `-wal`; repeat L5 directory, Keychain and defaults deletion; check that none of the files exist | on any error, keep `wipe-intent`, create only an **in-memory** container (`ModelConfiguration(isStoredInMemoryOnly: true)`), show the lock view with "Try again"; nothing touches disk |
| Done | Delete `wipe-intent` (last). Then create the normal container: a new, empty store. Keep `request.json` until the status route returns `completed` | new content is safe from here: no destructive step remains pending |

A file that belongs to an open `ModelContainer` is never deleted. The migration-failure path's no-delete rule (`StoryApp.swift:48-55`) is unchanged; the marker-driven cold-start wipe is the only code that deletes a store file. **Device-only:** this is SwiftData-touching and must be tested on Ling's iPhone with real media, including a force-quit at each stage (7.4). Not build-verified.

**Completion confirmation.** After the wipe, while `request.json` exists, the app calls the status route on each launch and foreground (at most hourly). When it returns `completed`, the app shows once: "Your YoTale account and its cloud data were deleted on <date>", then deletes `request.json`. If the user removed the app, there is no in-app confirmation; the deletion still completes, and an email confirmation stays optional (8.8). Acceptance ("we've started") and completion ("deleted") are separate messages.

**Signing in during deletion.** Cognito returns `NotAuthorized` for the disabled user, which the app maps to `accountDisabled` (`CognitoAuthClient.swift:111,132`). If `request.json` exists, the app shows "This account is being deleted" instead of the generic message (`:49`). Without it (another device) the generic message stays; the app cannot learn more without authenticating.

**Other devices signed in to the account.**

* **Confirmed deletion** = an authenticated response whose body has `error` = `account_deletion_in_progress` or `account_deleted` (5.3). That requires a valid access token for this account, so it is proof. The app signs out and asks: "This account was deleted from another device. Remove its Stories and videos from this iPhone?" Remove runs the same lifecycle (from L1, with `request_id` unknown and no completion polling). Keep leaves local content in place, signed out, as sign-out does today.
* **Generic** 401, 403 (including billing's `app_account_token_mismatch`), refresh failure, `NotAuthorized` or `UserNotFoundException`: existing sign-out behaviour; local data is never deleted.
* A device offline for more than an hour after quiesce never sees a confirmation (its access token has expired); it sees a generic auth failure and keeps its local data. The confirmation copy on the requesting device says so.

### 5.8 Restore and replay

Risk: a PITR restore of `users`, `identity-claims` or `user-usage` brings back rows of deleted accounts (an `active` users row, billing rows, Apple bindings). Cognito users are not restored, so a deleted user still cannot sign in; the real hazard is restored Apple bindings receiving notifications and restored billing data.

Facts used: PITR restores only into a **new** table, and the API reads table names from its environment, so restored tables serve traffic only after a deliberate repoint (CDK change and deploy). The request table is not part of the restore.

Runbook (operator tooling, D1 CLI):

1. Restore into new tables. Do not repoint.
2. `replay-after-restore --restored-users <t> --restored-usage <t>` (dry run unless `--execute`): for every request item (any state) it lists the rows of that uid present in the restored tables and the Apple bindings whose `b_uid` is that uid or whose key is in `global_keys`.
3. Real run, against the restored tables only: for `completed`/`closed` requests, delete the restored `<uid>` usage partition and bindings (token first), and write the tombstone (the restored users row may say `active`; replay writes `deleted` with condition `attribute_exists`). For `active` requests, set the restored users row to `deleting`; the scheduled worker continues after the repoint, because the request item, not the users row, drives it.
4. Repeat the dry run; repoint only when it reports zero rows.

Replay does not use the ordinary worker's "phase must match" rules because it targets other tables. It uses the same delete functions and the same request items. Accepted requests whose phases ran before the restore point are re-run by the scheduled worker from their current phase after the repoint, and the next verification pass re-deletes anything the restore brought back (verification counts the live tables).

### 5.9 Observability

One structured log line per phase transition: `request_id`, phase, counts, durations, error code. No email, no content. Metrics (EMF, no new service): `AccountDeletionHeartbeat`, `AccountDeletionStalled`, `AccountDeletionOverdue`, `AccountDeletionLateFound`, `AccountDeletionCompleted`.

### 5.10 Security and abuse

* uid comes only from the verified token on authenticated routes; the public status route reveals state only to the holder of the receipt secret.
* Fresh login per 5.3; account binding of re-auth per 5.1.
* Request item and pointer are written only by the API role; the worker never trusts anything but the request item it leased.
* Operator CLI (`python -m account_deletion.cli`): `count --uid` (read-only dry run), `request --uid --identity-checked`, `resume --uid` (acquires the lease), `status --uid`, `replay-after-restore`. Every mutating command needs `--confirm-env` equal to `--env`, and for email requests (8.17) it requires the identity check. It creates request items through the same transaction as the API (with `request_id` generated by the operator), so an operator deletion follows the same state machine.

### 5.11 IAM: operation-to-permission matrix

Resource ARNs: tables `arn:aws:dynamodb:<region>:<acct>:table/story-<env>-<name>`; buckets `arn:aws:s3:::<bucket>` (bucket-level actions) and `arn:aws:s3:::<bucket>/<prefix>*` (object actions); pool `arn:aws:cognito-idp:<region>:<acct>:userpool/<pool-id>` built from the same context key as `STORY_COGNITO_USER_POOL_ID` (`story-api-stack.ts:579-582`), never from the dev fallback id.

| Operation | Action(s) | Resource | Worker | API | Operator / replay |
|---|---|---|---|---|---|
| Accept request (transaction) | `dynamodb:PutItem`, `dynamodb:UpdateItem` (both needed for `TransactWriteItems`) | `account-deletions`; `users` | - | yes | yes |
| Status reads | `dynamodb:GetItem` | `account-deletions` | yes | yes | yes |
| Scan due requests | `dynamodb:Scan` | `account-deletions` | yes | - | yes |
| Lease, phase advance | `dynamodb:UpdateItem` | `account-deletions` | yes | - | yes |
| Record and read discovered keys | `dynamodb:PutItem`, `dynamodb:Query` | `account-deletions` | yes | - | yes |
| Users read and tombstone | `dynamodb:GetItem`, `dynamodb:UpdateItem` | `users` | yes | (existing) | yes, plus restored `users` |
| Content rows | `dynamodb:Query`, `dynamodb:BatchWriteItem`, `dynamodb:DeleteItem` | `media`, `stories`, `understanding`, `rate-limits` | yes | (existing) | yes |
| Billing partition and bindings (8.2(a): delete) | `dynamodb:Query`, `dynamodb:GetItem`, `dynamodb:BatchWriteItem`, `dynamodb:DeleteItem` | `user-usage` | yes | (existing, no delete) | yes, plus restored `user-usage` |
| Jobs | `dynamodb:Scan`, `dynamodb:UpdateItem` (cancel), `dynamodb:DeleteItem` | `edit-plan-jobs` | yes | (existing) | yes |
| List media/evidence | `s3:ListBucket` with `s3:prefix` condition `media/*`, `evidence/*` | media bucket ARN | yes | - | yes |
| Delete media/evidence | `s3:DeleteObject` | `media/*`, `evidence/*` | yes | evidence only (existing) | yes |
| Multipart enumerate / abort | `s3:ListBucketMultipartUploads` (bucket ARN, no condition: see the D2 note below); `s3:AbortMultipartUpload` (object ARNs `media/*`, `evidence/*`) | media bucket | yes | (existing abort on `media/*`) | yes |
| Staging | `s3:ListBucket` (`s3:prefix` = `jobs/*`), `s3:DeleteObject` (`jobs/*`) | staging bucket | yes | - | yes |
| Cognito | `cognito-idp:AdminDisableUser`, `AdminUserGlobalSignOut`, `AdminGetUser`, `ListUsers`, `AdminDeleteUser` | pool ARN | yes | - | yes |
| Logs, metrics | `logs:CreateLogStream`, `logs:PutLogEvents` (EMF) | own log group | yes | - | - |
| Restore replay reads | `dynamodb:Scan`, `dynamodb:Query`, `dynamodb:GetItem` | restored table ARNs (passed at run time) | - | - | yes |

Not granted to anyone: `sqs:*` for deletion (no queue), `s3:PutObject` for a ledger (the ledger is the request table), `dynamodb:DeleteItem` on `account-deletions`, `users` or `identity-claims`. The worker's `DeleteItem` on `user-usage` cannot be limited to one uid (`dynamodb:LeadingKeys` needs a per-request value); the compensating control is that the worker acts only on uids that have a leased request item. Operator / replay is a separate break-glass role assumed by a human, not attached to any service. **Verification criterion (D2):** `cdk synth`, then inspect the synthesized worker policy: no `sqs:*`, no `s3:PutObject`, object actions only on the listed prefixes, `ListBucket` carries the `s3:prefix` condition (D2: `ListBucketMultipartUploads` is granted without it, because `s3:prefix` is documented for `ListBucket` and a condition key the action does not supply would deny every call; it lists upload keys only), Cognito actions only on the configured pool ARN. Confirm with the IAM policy simulator on dev. If S3 or DynamoDB use customer-managed KMS keys (**Unverified**; the code shows SSE-S3 for the staging bucket, `story-api-stack.ts:209`), add `kms:Decrypt`/`kms:GenerateDataKey` as needed.

## 6. Sign in with Apple

Four separate questions:

| Question | v1 status |
|---|---|
| New Apple sign-ups | dev only (section 1). Beta is held by sign-in plan F4 until this section's release rule is met |
| Existing Apple users | 1 on dev (Ling's test account, verified live 2026-11-22). Beta and prod: check before release (D5 precondition). They get in-app deletion like everyone else |
| Google | no Apple-style revocation requirement; deleting the Cognito user removes the link. Optional Google token revocation is not in v1. Re-auth per 5.1 step 3 |
| Account data deletion | identical for every sign-in method: the worker deletes by uid. Never blocked for Apple users |
| Apple authorization revocation | needed only for users who signed in with Apple. Preferred: automatic, below. Fallback: TN3194 manual revocation |

**Preferred: automatic revocation with native re-auth.** At deletion, an Apple-linked user re-authenticates with the native Sign in with Apple sheet (`ASAuthorizationAppleIDProvider`). The app sends the identity token and the one-time authorization code with the deletion request. The server verifies the identity token (Apple JWKS, `aud` = bundle id, `iat` within 5 minutes, `sub` equals the Apple identity linked to this Cognito user, read with `AdminGetUser`). It exchanges the code at Apple's token endpoint for a refresh token and calls Apple's revoke endpoint. This needs the Sign in with Apple capability on the App ID and a client secret signed with an Apple key held in Secrets Manager. Whether revoking under the app's bundle id also revokes the grant Cognito obtained under the Services ID is **unverified**: appendix A tests it.

**Fallback: TN3194 (Apple Technote, read 2026-11-21).** When the app holds no usable refresh token, access token or authorization code for the user, Apple's guidance is to still fulfil the deletion request: delete the user's data, direct the user to revoke the app's Sign in with Apple access manually in their Apple Account settings, and respond to the credential-revoked notification by returning the client to a signed-out state. If manual revocation is not done, the next Sign in with Apple does not show the first-time name/email sheet. For YoTale this means: deletion completes; the completion screen for an Apple-linked user adds a short instruction (Settings, your name, Sign-In & Security, Sign in with Apple, YoTale, Stop Using) and a note that we could not revoke it automatically; the app observes `ASAuthorizationAppleIDProvider.credentialRevokedNotification` and signs out; if a server-to-server notification endpoint is registered for Sign in with Apple, a `consent-revoked` or `account-delete` event for a deleted account is acknowledged and dropped. Cognito capabilities in this path are **unverified**.

**Release rule.** Deletion does not wait for Apple revocation on dev. Before Apple sign-in reaches beta or any App Store build, that build must include either working automatic revocation (appendix A passed) or the TN3194 fallback with the server-to-server notification endpoint (D7). Because a Google build must also offer Apple (Guideline 4.8), the same rule gates Google on beta. Hiding the button would not remove existing Apple users' deletion needs, so it is not the mechanism.

## 7. Testing and rollout

### 7.1 Backend (D1, fakes and `ddb_local`, no AWS)

* Every phase with fakes; pagination over more than one page.
* Crash at every phase boundary and at both finalize boundaries; re-run converges.
* Two runs at once: the second fails to acquire; a stale run whose lease was taken over fails its next write and makes no further writes; concurrent discovery of `job_ids` and `global_keys` keeps both.
* `quiesced_at`/`not_before` set once; `not_before` cannot be skipped by `resume`.
* Waits do not increase `fail_count`; backoff sequence; `stalled_alerted_at` set once at 5; retries continue after it; overdue metric counts only `active` older than 6 h.
* Acceptance transaction: commit, idempotent retry, `409` for a different id, users row not `active`, users row missing; status route returns identical 404 for unknown id and wrong secret.
* Verification: a quota row recreated after phase 3 is found; a job created after phase 1 is found, cancelled, its staging deleted; a token binding recreated after phase 3 is found; binding deletion order (token before txn) under a simulated notification between them.
* Finalize cannot create a users row (`attribute_exists`).
* Restore replay on fake restored tables: completed and active requests; repeat dry run reports zero.
* Billing modes `off`/`observe`/`enforce`; token binding present in `off`.
* Route gate: only the two deletion routes accept `deleting`; `deleted` refused everywhere; claim with no users row is 403; `error` codes present.

### 7.2 Dev AWS (D2/D3, needs Ling's approval per deploy)

Throwaway test account: counts before and after in every store of 2.1; same email re-signs-up with a new uid and empty data; late-write injection (start a 15 MiB single PUT just before submitting, confirm verification removes the object); `cdk synth` policy inspection (5.11).

### 7.3 Billing sandbox (before release, needs a device and a sandbox Apple ID)

1. Delete an account with an active sandbox subscription; after completion, a sandbox renewal notification gets outcome `unmatched` in `__apple_evt__` and no `<uid>` rows exist.
2. Re-register with the same email, tap Restore Purchases: confirm the response is `app_account_token_mismatch` and record what the app shows and whether StoreKit offers a new purchase. Write the observed outcome into section 4 item 4.
3. Binding discovery: an account whose `submit_transaction` returned `not_active` still has its `__apple_txn__` row found and deleted.

### 7.4 iPhone (D5, Ling's device build is the only gate)

Force-quit at L1, L3, L4, L5, L6 and during the cold-start wipe; each relaunch ends with no old data and an empty, usable app. Kill the app during submission with the network off, then relaunch online: the checking screen resolves. Lost 202 (airplane mode right after tapping): resolves through the status route. Another signed-in device sees the deletion prompt within the hour; after the hour it sees a generic sign-out and keeps its data. Migration-failure path: wipe removes both store sets. Sign-in during deletion shows "being deleted".

### 7.5 Rollout and flags

dev, then beta, then prod; each deploy needs Ling's explicit approval. Beta CDK diff and deploy must include `-c observability=true -c alarmDestination=alerts@yotale.ai` and show no destroys. Beta holds testers' evidence, so beta tests use a test account. **No new flags.** The route is inert without the client; rollback is redeploying the previous image. `STORY_EVIDENCE_PERSIST_ENABLED` stays OFF in prod until deletion and the privacy text are live there (8.16).

## 8. Decisions for Ling

**Ling, 2026-11-22: every recommendation below is accepted as the default.** Approval to build D1 does not cover D2, D3 or any deploy; those still need their own go (8.12).

* **8.1** Active subscription: allow, warn, link Manage Subscriptions. Recommended (a).
* **8.2** Apple identifiers: **(a) delete both bindings is the provisional v1 choice (Ling, 2026-11-21).** Consequence: no notification guard and no billing code change; the re-registration lockout in section 4 item 4 is a known v1 limitation, confirmed or corrected by 7.3 before release. (b)/(c) stay possible later.
* **8.3** Trial marker and **8.4** payment-record retention: **outside the first deletion release** (D6). Counsel and the accountant decide; nothing is retained in v1 beyond section 3.
* **8.5** Privacy text: publish only when the deleting build is in App Review.
* **8.6** Billing modes: verified against merged V2 (2.2); no action.
* **8.7** Local wipe: all local data on the requesting device. Recommended.
* **8.8** Confirmation email: none in v1; completion is confirmed in-app (5.7).
* **8.9** Provider copies: verify retention (OpenAI, Google, Unsplash, Bedrock logging) before publishing the policy text.
* **8.10 (changed)** Apple revocation: no longer gates the deletion release (section 6). Beta (2026-11-23) ships the TN3194 fallback with the notification endpoint; appendix A (automatic revocation) is deferred to before the App Store release.
* **8.11** Grace period: none.
* **8.12 (changed)** Approvals: D1 (inert code) through a normal PR. Separately: the new table, Lambda, role and rule (D2); the API routes and guards G1/G2 (D3); each environment deploy; the first run on a non-test account; privacy text.
* **8.13** Keep the identity claim as a tombstone. Recommended (a).
* **8.14 (changed)** Jobs: recorded at quiesce, cancelled, deleted during verification. No longer a choice.
* **8.15 (changed)** Ledger: the request table is the ledger (5.2, 5.8). Recommended; replaces the S3 ledger object.
* **8.16** Prod evidence persistence stays OFF until deletion and policy are live in prod.
* **8.17** Email requests before the in-app path: Ling runs the operator CLI after an identity check. Recommended.
* **8.18 (changed)** Merged into the release rule in section 6.
* **8.19 (decided 2026-11-22)** Other signed-in devices on confirmed deletion: ask before removing local data (5.7).

## 9. Proposed privacy-policy text (proposal only; counsel reviews)

Section 1: "You can delete your account and your data in the app: open the account menu and choose Delete Account. You can also email privacy@yotale.ai."

Section 6 (replace the last paragraph): "When you delete your account we delete your sign-in, your Stories, the AI analysis we saved, your cloud backups and your usage records. Deletion usually finishes within two hours, including a security wait of about an hour, and a final check runs one day later. Copies in our database backups expire on a rolling cycle of up to [35] days; this applies to our sign-in, account and billing tables. We keep a minimal pseudonymous record that the account was deleted: the random account identifier, the sign-in identifier and the deletion request details, with no email address or content, so the deletion cannot be undone by mistake. Our operational logs refer to accounts by the same pseudonymous identifier and expire after 30 to 90 days; our web firewall logs, which may include IP addresses, expire after 30 days. Copies saved in your Photos library and in device backups are yours and are not deleted. Other iPhones signed in to the account keep their local copies unless you remove them there. Information already sent to our AI, image and music providers (including Unsplash for image search) is handled under their policies, and we cannot recall it."

Section 7, access/deletion bullet: "Delete your account in the app, or email privacy@yotale.ai from the address on your account and we will help. We respond within 30 days."

Section 7, subscriptions bullet: "Deleting your account does not cancel an App Store subscription. Cancel it in your Apple Account settings (the app links to this) before deleting; we cannot cancel or refund it. A subscription bought on a deleted account cannot be moved to a new account."

Section 7, Sign in with Apple (only in the build that enables it, if automatic revocation is not available): "If you signed in with Apple, also remove YoTale under Sign in with Apple in your Apple Account settings."

Bracketed values are unverified. "Pseudonymous" replaces revision 1's "no longer link to your email" wording.

## 10. Implementation increments

**D1. Backend deletion core (no infra, no route).** Request-item model and the state machine of 5.4 (lease, `phase_seq`, waits, backoff, stall and overdue metrics), the phase functions, the verification pass of 5.5, finalize ordering, the operator CLI (`dry-run`, `resume`, `status`, `replay-after-restore --dry-run` and real), pagination fixes for `list_for_owner`/`delete_for_owner`, a failure-reporting evidence delete, the `model_call_usage` docstring correction. Tests 7.1 with fakes and `ddb_local`. Ships inert.
* **Status (2026-11-22): built** on `feat/account-deletion-d1` as `packages/account_deletion/` (`config.py`, `request_store.py`, `targets.py`, `worker.py`, `replay.py`, `cli.py`, `fakes.py`), plus pagination and failure reporting in `media_store.list_for_owner` and `evidence_store.delete_for_owner`, and the `model_call_usage` docstring. 39 tests in `packages/account_deletion/tests/` on a multi-table DynamoDB fake that evaluates real expression syntax (the billing fake's evaluator); DynamoDB Local tests are a follow-up. Not run against AWS.
* D1 checks that need AWS (dev, read-only, default profile): `AdminGetUser` with `sub` as `Username` on a test user; `ListUsers` with `Filter: sub = "<sub>"`; whether the access token carries `auth_time` and keeps it after a refresh (needs a fresh dev token from a test sign-in, which needs the test inbox: Ling or a test account she controls).
* No iPhone check in D1.

**D2. Infra.** CDK: `account-deletions` table (PITR on, deletion protection, RETAIN), Lambda (300 s), worker role per 5.11, EventBridge 5-minute rule (retries 0, max age 5 min), break-glass operator role, alarm request to the Observability thread. Synth policy inspection (5.11). Beta diff with observability flags, no destroys. Needs Ling's approval.
* **Status (2026-11-22): built** on `feat/account-deletion-d2`: `infrastructure/cdk/lib/account-deletion.ts` (table `story-<env>-account-deletions` pk/sk with PITR, deletion protection and RETAIN; Lambda `story-<env>-account-deletion`, handler `account_deletion.worker.handler`, 300 s, 512 MB, same zip asset as the edit-plan worker, own log group; 5-minute rule with retries 0 and max event age 300 s; worker role per 5.11; alarms stalled, overdue, late-found, heartbeat-missing and Lambda errors when the Observability topic exists). Created only for `development` (and `test` synth) until Ling approves beta: adding `beta` to `ACCOUNT_DELETION_ENVIRONMENTS` in `story-api-stack.ts` is that change. Synthesized-policy checks in `infrastructure/cdk/test/account-deletion.test.ts`. Dev `cdk diff` with the live image digest: 7 resources added, the edit-plan worker's code hash changes (same asset, new package), nothing destroyed or replaced, App Runner unchanged. Dev has no Observability construct deployed, so the alarms exist only where it is enabled (beta).
* **Deferred from D2:** the break-glass operator role. On dev the operator CLI runs under Ling's own admin session; a dedicated role is added with the beta rollout. The IAM policy simulator check is also not done; the synthesized-policy test is the D2 gate.
* **Beta rollout (2026-11-23, Ling: "rollout to beta").** `beta` added to `ACCOUNT_DELETION_ENVIRONMENTS` (CDK) and `AccountDeletionAvailability` (iOS); break-glass role `story-<env>-account-deletion-operator` added (assumable by this account's IAM principals only, 1 h sessions, the worker's grants plus replay on `story-<env>-*-restored*` tables); WAF rule `AccountDeletionStatusRatePerIp` (60 per 5 min per IP, Block, path `/v1/account/deletion/status` only). Read-only beta checks before rollout: 6 identity claims and 6 users rows (none would fail closed); no identity providers and 0 federated users on the beta pool; PITR enabled with a 35-day window on users, identity-claims and user-usage, not on media, stories, understanding; DynamoDB tables use the AWS-owned default key and the buckets SSE-S3 (AES256), so no KMS grants are needed. Beta `cdk diff story-beta-api` with the observability flags: 14 resources added (table, worker, rule, roles, 5 alarms), App Runner gains one env var, nothing destroyed or replaced. `cdk diff story-beta-waf`: one rule added.

**D3. API.** `POST/GET /v1/account/deletion`, public `POST /v1/account/deletion/status`, `DELETION_ROUTES` bypass, `error` codes on the 403, fail-closed `_account_status`, `auth_time` check, rate-limit classes, G1 and G2. Needs Ling's approval per deploy.
* **Status (2026-11-22): built** on `feat/account-deletion-d3`. `apps/api/app/auth.py`: `Principal.auth_time`; `resolve(..., allow_status=)` widened to `{active, deleting}` only for `DELETION_ROUTES`; `deleted` refused everywhere; `AccountStatusError` adds `error` = `account_deletion_in_progress` / `account_deleted` to the boundary's 403 (other statuses keep the generic body); a claim with no users row now fails closed (`account missing`; dev checked 2026-11-22: 5 claims, 5 rows, beta unchecked); the status route added to `PUBLIC_ROUTES`. `apps/api/app/main.py`: the three routes (POST returns 202, 409 `deletion_already_requested`, 401 `reauth_required` when `auth_time` is absent or older than 300 s, 400/422 validation, 403 `account_not_active`, 503 `deletion_unavailable` without the table and `deletion_outcome_unknown` on any other store error). `throttle.py`: class `account_deletion` at 3 per minute (the limiter is per minute, not per hour; not `expensive`, which marks paid AI classes, so a limiter outage fails open). G1 in `media_store.initiate_upload` (Moment and generated kinds only, above), G2 in `reconcile_lost_enqueue`. CDK: `STORY_ACCOUNT_DELETIONS_TABLE` on App Runner and an `AccountDeletionAccept` grant (GetItem, PutItem, ConditionCheckItem) only in `ACCOUNT_DELETION_ENVIRONMENTS`; the release gate allows the setting as optional infrastructure wiring. The public status route has no per-IP throttle on dev (no WAF there); beta's WAF needs a rate rule for it before beta.

**D4. Removed.** The Apple-notification guard is not needed under 8.2(a). Billing verification moved to 7.3.

**D5. iOS.** Menu entry, screens, account-bound re-auth, submission and status protocol, `Library/AccountDeletion/` files, `DeletionLockView`, staged and cold-start wipe, completion confirmation, other-device handling, en and zh-Hans strings. Ling's device build (SwiftData-touching). Preconditions: beta/prod pools checked for the Apple IdP and federated users.
* **Status (2026-11-22): built** on `feat/account-deletion-d5`, offered in Development builds only (`AccountDeletionAvailability`, add `.beta` with the beta rollout). Files: `Data/Account/AccountDeletionFiles.swift` (`Library/AccountDeletion/request.json` = pending request, `wipe-intent` = instruction to wipe, atomic writes), `Data/Account/AccountDeletionService.swift` (submit, receipt status, other-device probe), `Data/Account/LocalWipe.swift` (cold-start wipe), `Features/Account/AccountDeletionCoordinator.swift` (acceptance, lost-response recovery, lock, completion, other device), `Features/Account/DeleteAccountView.swift` (intro, subscription step, re-auth, typed confirmation), `Features/Account/AccountDeletionRootView.swift` (lock screen, alerts); `AuthStore` re-auth (`reauthStartEmail` / `reauthVerifyEmail` / `reauthFederated`, same-`sub` check, no adoption, session untouched), restore refuses while a wipe is pending, "being deleted" sign-in message; `StoryApp.init` runs the wipe before any `ModelContainer` and falls back to an in-memory store if it fails; 57 zh-Hans strings.
* **Change from 5.7 (in-session row deletion dropped).** After acceptance the app shows only the lock screen, signs out (every cloud writer needs a token) and deletes nothing until the next launch. Deleting SwiftData rows while the upload, AU and render queues hold live model references risks a crash on a deleted model, and the lock screen already hides all content. Consequence: local data stays on the device until YoTale is next opened (the lock screen says "Close YoTale to finish removing your data from this iPhone"). Everything is deleted before the next store opens.
* **Verified on the iOS simulator (2026-11-22):** the full app builds in Xcode 27.2 for the simulator; `AccountDeletionTests` (11) and `AuthLogicTests` (8) pass. End-to-end cold-start wipe on the simulator: with a planted `wipe-intent`, relaunch logged `ACCOUNT_DELETION local wipe: wiped`, removed the marker, `request.json`, seeded `Documents/media` and `Caches` files and the old store, created a new store, removed a test UserDefaults key and kept `story.appLanguage`. Three pre-existing test failures also fail on unmodified master (`ReleaseConfigDefaultsTests.test_appleSignIn_isBakedAndOffUntilTheIdpExists`, `AppLanguageTests.test_L10n_translatesGlossaryTerms_inBothLanguages`, `AuthGatingTests.test_au_resumes_when_authed`).
* **Device acceptance (Ling, 7.4) still required:** the flow on a real account for email, Apple and Google re-auth; lost response (airplane mode right after tapping Delete); kill during submission; force-quit while locked; the wipe on a device with real media; the other-device prompt; the subscription step with a sandbox subscription; Chinese text.

**D6.** Trial marker (8.3), payment record (8.4): only if chosen; not v1.

**D7.** Apple re-auth and revocation (appendix A), before or with the build that enables Apple sign-in.
* **Status (2026-11-23): done via the TN3194 fallback; Apple sign-in enabled on beta.** The section 6 release rule allows either automatic revocation (appendix A passed) or the TN3194 fallback with the server-to-server notification endpoint. Built the fallback:
  * `POST /v1/auth/apple-signin-notifications` (public, `apps/api/app/apple_signin_notifications.py`): verifies Apple's JWT (Apple JWKS, issuer `https://appleid.apple.com`, `aud` = the environment's Services ID from `STORY_APPLE_SIGNIN_AUDIENCE`); `consent-revoked` and `account-delete` run `AdminUserGlobalSignOut` on `SignInWithApple_<sub>` (refresh tokens revoked, the app signs out at its next refresh); `email-*` acknowledged; unknown user acknowledged; bad payload 400; Cognito failure 503 so Apple retries. No data is deleted by a notification. Logs carry the event type, outcome and a 12-hex hash of the Apple sub only. API role gets `cognito-idp:AdminUserGlobalSignOut` on its pool only.
  * In-app manual revocation step for Apple accounts (lock and completion screens) shipped in D5; the "being deleted" sign-in message now also covers Apple and Google sign-in.
  * Beta: `YoTale-Apple-SignIn-Beta` copied from dev into beta 224033508028 (Ling's 2026-11-22 decision; checked by shape: four fields, 10-character key and team ids, PEM header, copy equals source; never printed). `story-beta-auth` diff showed only `AppleIdp` added and the client gaining `SignInWithApple` (no drift otherwise); deployed 2026-11-23 19:20 JST; the hosted authorize redirects to Apple with `com.lingzhang.story.signin.beta`. Apple's authorize page accepts the beta return URL (`story-beta-auth.../oauth2/idpresponse`; a wrong URL gets 403). `Beta.xcconfig` `STORY_FEDERATED_PROVIDERS = SignInWithApple` (Google stays off on beta).
  * **Ling's step:** register `https://<beta API host>/v1/auth/apple-signin-notifications` as the Server-to-Server Notification Endpoint in the Sign in with Apple configuration of the primary App ID `com.lingzhang.story` (Apple Developer portal). One endpoint serves every Services ID grouped under that App ID; events whose `aud` is not this environment's Services ID are rejected (400), so dev events are not processed on beta.
  * **Automatic revocation (appendix A) deferred.** It needs the Sign in with Apple entitlement in a build and a device test (A3, A8). Revisit before the App Store release; it would replace the manual step for users who complete the native re-auth.

**D8.** Privacy text and guideline 5.1.1(v) quote, when D5 is in App Review.

Order: D1 -> D2 -> D3 -> D5 -> 7.3 -> D8. D7 is independent of the deletion release.

## 11. Verification summary

**Verified in code:** sections 2.1-2.3 citations; V2 key shapes and binding discovery on master `2ea6a1b` (2.2); `_resolve_uid` re-binding (2.2); token creation in `off` (2.2); `AccountTokenMismatch` status 403 (section 4); job lease, cancel and reconcile behaviour (5.5); upload TTL and the 16 MiB split, with no server cap (5.5, 2.3); Apple sign-in baked off in both builds (1); iOS 401/403 handling (2.3).

**Verified live (read-only, dev, 2026-11-21):** dev pool `us-east-1_AzfHOEdA5` has no identity providers and 0 `EXTERNAL_PROVIDER` users.

**Verified live (read-only, dev, 2026-11-22):** `AdminGetUser` accepts the `sub` as `Username` for email, Apple and Google users (email users' usernames are their sub; federated usernames are `SignInWithApple_…` / `Google_…`), and `ListUsers` with `sub = "…"` also finds them, so both paths in phase 7 work.

**Unverified, needs AWS:** beta/prod Apple IdP and federated users (SSO); `auth_time` in access tokens (needs a fresh dev sign-in token; D3 returns `reauth_required` if absent); WAF log contents. (Beta PITR window 35 days and default encryption verified 2026-11-23.)

**Unverified, needs an iPhone or sandbox:** the whole wipe lifecycle; Restore Purchases after re-registration; StoreKit re-purchase behaviour; native Sign in with Apple `sub` equality and revocation scope (appendix A).

**Unverified, external:** provider retention; current text of guideline 5.1.1(v) (not re-fetched); TN3194 was read 2026-11-21.

## 12. Failure-scenario matrix

| # | Scenario | What happens | Where |
|---|---|---|---|
| 1 | Two runs reach the same request (overlapping schedule, operator `resume`) | the second fails lease acquisition and skips it | 5.4 lease |
| 2 | A run crashes mid-phase | lease expires in ≤ 6 min; next run re-runs the phase from its start | 5.4 |
| 3 | A stale run wakes after takeover | its next conditional write fails; it stops; its earlier deletes are harmless | 5.4 |
| 4 | Concurrent discovery of job ids or global keys | one idempotent item per key keeps all | 5.2, 5.4 |
| 5 | POST commits, response lost | client resolves through the status route with the receipt | 5.3, 5.7 |
| 6 | POST returns 503 | unknown; status route decides; `not_found` means not committed | 5.3, 5.7 |
| 7 | App killed during submission | next launch shows the checking screen before any container exists | 5.7 |
| 8 | Token expired or user disabled before recovery | status route needs no token | 5.3 |
| 9 | Same `request_id` retried | idempotent 202 | 5.3 |
| 10 | Second device asks while the first is pending | 409, treated as accepted | 5.3 |
| 11 | Crash between tombstone and `completed` | re-run finalize; condition accepts `deleted` | 5.4 |
| 12 | Cognito already deleted on re-run | `UserNotFoundException` is success | 5.4 |
| 13 | Ledger lost | not possible: the request item is the ledger and is written before and during every phase | 5.2 |
| 14 | PITR restore of auth tables | restored into new tables; replay before repoint; request table untouched | 5.8 |
| 15 | Restore while a deletion is mid-flight | replay sets the restored users row to `deleting`; the worker continues from the request item | 5.8 |
| 16 | Late single PUT finishes after the flip | ≤ 16 MiB (G1); removed by verification; the final check at 24 h catches stragglers and alerts | 5.5 |
| 17 | Multipart parts uploaded after the flip | the object cannot complete; uploads aborted at verification | 5.5 |
| 18 | Edit-plan run settles quota or billing after phase 3 | rows found and deleted by verification; second pass ≥ 10 min later | 5.5 |
| 19 | Job created by an in-flight request after the phase-1 scan | found by the rescan, cancelled, staging and row deleted | 5.5 |
| 20 | Notification between token and txn binding deletes | not possible: token is deleted first, so the txn cannot be re-bound | 2.2, 5.4 |
| 21 | Repeated AWS failures | backoff to 6 h; alert at 5 failures; retries continue | 5.4 |
| 22 | Deletion never becomes due (bug) | overdue metric alarms after 6 h | 5.4 |
| 23 | Scheduler disabled or Lambda broken at import | heartbeat alarm after 30 min | 5.4 |
| 24 | User creates content before relaunch | impossible: the lock view blocks it, and the cold-start wipe runs before any container exists | 5.7 |
| 25 | User signs into another account before relaunch | impossible in this process; after relaunch the wipe has finished before sign-in is reachable | 5.7 |
| 26 | Force-quit during any wipe stage | `wipe-intent` stays until every step succeeded; relaunch repeats | 5.7 |
| 27 | Cold-start file deletion fails | in-memory container, lock view, retry; disk untouched | 5.7 |
| 28 | Other device gets a generic 401/403 | sign-out only; no local deletion | 5.7 |
| 29 | Other device gets the deletion `error` code | signs out and asks before removing local data | 5.7, 8.19 |
| 30 | Re-auth with a different email | prevented: email locked; `sub` mismatch stops submission | 5.1 |
| 31 | Re-registered user restores an active subscription | `app_account_token_mismatch`; known v1 limitation, verified in 7.3 | 4 |

## 13. Status at session close and open action items (2026-11-24)

**Done and live.** D1 to D3 (PRs #154, #156, #159, #160) and D5 (#161, menu fix #162) on dev and beta; beta rollout (#164: request table, worker, alarms, operator role, WAF rule for the status route); D7 TN3194 fallback and Apple sign-in on beta (#166). Device-accepted on dev by Ling (Apple account deleted 2026-11-23; request `completed`, 0 failures). Beta deploys `git-c4a0aca5ccbc` then `git-a8de3f92426b`, both with post-deploy verification passing.

**Not complete.** Each item names its owner and what blocks it.

| # | Item | Owner | Blocks |
|---|---|---|---|
| O1 | Register `https://asxtxgjiis.us-east-1.awsapprunner.com/v1/auth/apple-signin-notifications` as the Sign in with Apple Server-to-Server Notification Endpoint on App ID `com.lingzhang.story` (Apple Developer portal) | Ling | Revocation notices reaching beta |
| O2 | Upload a beta (TestFlight) build from master so testers get Delete Account and Apple sign-in | Ling | Beta testers using either feature |
| O3 | Automatic Apple token revocation (appendix A): Sign in with Apple entitlement in a dev build, steps A1-A9 on a device, then implement if A3 and A8 pass | Kiro + Ling (device) | App Store release (manual TN3194 step is the interim) |
| O4 | D8: verify provider retention (OpenAI, Google, Bedrock invocation logging, Unsplash) (8.9) | Kiro (research) | Publishing the privacy text |
| O5 | D8: fetch and quote the current App Store guideline 5.1.1(v) text in section 4 | Kiro | App Store review |
| O6 | D8: counsel review of the section 9 privacy text; publish when the deleting build is in App Review (8.5) | Ling / counsel | App Store release |
| O7 | Production rollout: add `production` to `ACCOUNT_DELETION_ENVIRONMENTS` (CDK) and `AccountDeletionAvailability` (iOS), prod Apple Services ID and secret, prod WAF rule, diffs, deploys | Ling (decision) + Kiro | Production |
| O8 | Keep `STORY_EVIDENCE_PERSIST_ENABLED` OFF in gamma/prod until O6 and O7 are live there (8.16) | Ling (decision) | — (standing rule) |
| O9 | Free-trial marker (8.3, counsel) and payment-record retention (8.4, accountant); outside v1 | Ling | — |
| O10 | DynamoDB Local tests for `packages/account_deletion` (today: expression-evaluating fake only) | Kiro | — |
| O11 | Three iOS tests that already fail on master: `ReleaseConfigDefaultsTests.test_appleSignIn_isBakedAndOffUntilTheIdpExists` (reads the renamed Info.plist key), `AppLanguageTests.test_L10n_translatesGlossaryTerms_inBothLanguages` (expects 片段, app says 瞬间), `AuthGatingTests.test_au_resumes_when_authed` | Kiro | — |
| O12 | Unverified on a device: `auth_time` presence for email, Apple and Google re-auth on beta (the route answers `reauth_required` without it) | Ling (device) | — (dev email/Apple path accepted) |

## Appendix A. Focused test: native Apple re-auth and revocation

**Finding first (updated 2026-11-22).** A Cognito-linked Apple account now exists on dev (Ling's, 1 federated user, `SignInWithApple` provider live). Preconditions 1-2 below are done (sign-in plan A1-A3). Still needed: precondition 3's Sign in with Apple entitlement for the native sheet (the hosted-UI flow does not need it), and precondition 4's key in Secrets Manager for the token exchange.

**Preconditions (Ling's Apple Developer and AWS actions, then approval):**

1. Services ID, Sign in with Apple key and Team ID; the Services ID grouped with the app's primary App ID.
2. Dev auth stack deployed with `-c applePrivateKey=...` and the Services ID, Team ID and key id (creates `SignInWithApple`, `story-auth-stack.ts:118-135`). Needs Ling's approval (auth-stack change on dev).
3. Sign in with Apple capability on the App ID and the entitlement in a dev build; `STORY_APPLE_SIGNIN_AVAILABLE = 1` in that dev build only.
4. The same key stored in Secrets Manager on dev for the client-secret JWT. Never printed; verify by length and header only.

**Steps (dev, Ling's iPhone, a test Apple ID):**

| Step | Action | Pass |
|---|---|---|
| A1 | Sign in through the hosted UI with Apple; complete onboarding | a Cognito user `SignInWithApple_<id>` exists |
| A2 | `AdminGetUser` (read-only): record the `identities` attribute `userId` | the Apple subject is present |
| A3 | In the dev build, run the native `ASAuthorizationAppleIDProvider` request (no scopes) | identity token and authorization code returned; token `aud` = bundle id; token `sub` equals A2's `userId` |
| A4 | Dev script: exchange the code at Apple's token endpoint with `client_id` = bundle id | a refresh token is returned |
| A5 | Revoke that refresh token | HTTP 200 |
| A6 | On device: `getCredentialState(forUserID:)` | `.revoked` |
| A7 | Settings, Sign in with Apple | YoTale is gone, or still listed (record which) |
| A8 | Hosted-UI Apple sign-in again | Apple shows the first-time name/email sheet. This is the proof that the Cognito (Services ID) grant was revoked too |
| A9 | Negative: a different Apple ID's token against this account | the server check rejects it |

**Outcomes.** A3 and A8 pass: automatic revocation works; D7 implements it. A3 passes and A8 fails: revocation under the bundle id does not cover Cognito's grant; ship the TN3194 fallback (section 6) and record the result. A3 `sub` mismatch: the native identity is not the Cognito-linked one; re-auth must use a forced hosted-UI login instead, and revocation falls back to TN3194.
