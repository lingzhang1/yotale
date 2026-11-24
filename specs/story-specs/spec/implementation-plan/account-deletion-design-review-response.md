# Response to the review of the YoTale account deletion design

Design (revised in place): `/Users/lingzhang/Workplace/story/specs/story-specs/spec/implementation-plan/account-deletion-design.md`
Review: `/Users/lingzhang/Workplace/story/specs/story-specs/spec/implementation-plan/account-deletion-design-review.md`
Date: 2026-11-21. Design only: no code, no branch, no git write, no AWS call. Billing files read with `git show master:<path>`; V2-dependent items are marked "pending Billing V2" in the design.

Re-verified against the working tree before applying (file:line):
- F3 confirmed: the `active`-only check is in `IdentityStore.resolve` -> `_enforce_status` (`apps/api/app/auth.py:212-222,251-261`), called from `_principal_from_token` (`:296-300`) by the `auth_boundary` middleware (`:384-405`); `require_user` reuses `request.state.principal` (`:303-320`).
- F5 confirmed: `_account_status` returns `("active","eligible")` for a missing users row (`auth.py:205-206`).
- F-C3 confirmed on master: `entitlement_payload` calls `get_or_create_apple_account_token` at `billing_gate.py:344-347` (and `:356`); that writes `billing#account` and the token index (`ledger.py:212-232`).
- F-C4 confirmed: `edit_plan_jobs/__init__.py:392-394` ("reaped within ~48h"); scans by `owner` exist at `:495,543`.
- F9 confirmed: `user_quota/__init__.py:258` uses `attribute_not_exists(#r)` on the reservation marker only, no row-existence condition.
- F10 confirmed: schema of 22 model types at `StoryApp.swift:28-41`, container opened at `:44`, no-delete rule at `:51-54`.
- F-S4 confirmed: `AuthStore.swift:134` `prefersEphemeralWebBrowserSession = false`; `finishSignIn` at `:190`.
- F11 confirmed: `accountDisabled` maps `NotAuthorized` at `CognitoAuthClient.swift:111,132` with a generic message at `:49`.
- Not re-verified by me (taken from the review, whose citations I spot-checked): the remaining V-series paths (iOS Caches/UserDefaults call sites), F-S2 grant gaps, F-S3 sign-up flow.

No finding was rejected. Where the review left a choice to the owner (F4, F8, F-V7) the design recommends one option and moves the choice into section 8.

## Findings

| ID | Severity | Verdict | What changed, and where in the design |
|---|---|---|---|
| F-C1 | nit | Accepted | Row 9 now cites `user_quota/__init__.py:192-193` and `:57-59` only (2.1). |
| F-C2 | nit | Accepted | 5.4 cites `story-api-stack.ts:579-582`, names the dev fallback pool id, and says the worker's Cognito ARN comes from the same context key, never the fallback; guard at `:60-76`. |
| F-C3 | should-fix | Accepted | New paragraph in 2.2 and rewritten first bullet in section 6: `off` still writes `billing#account` and the token binding (`master:billing_gate.py:344-347`). "Token binding exists in `off`" added to the test list (7). Marked pending Billing V2. |
| F-C4 | should-fix | Accepted | Rows 11-12 (2.1), section 3, and the in-flight paragraph (5.3) restate the residual window as up to ~48 h for job rows and 24-48 h for staging. Privacy text says "within a day" (9). |
| F-V1 | should-fix | Accepted | 2.3 lists the Caches, tmp and Documents users with citations; 5.6 step 3 wipes whole directories instead of enumerating folders. |
| F-V2 | should-fix | Accepted | 2.3 lists the extra UserDefaults keys; 5.6 step 5 removes the whole defaults domain and restores a language allow-list. The old "Assumption" is closed. |
| F-V3 | nit | Accepted | One line in 2.3: no App Group, shared Keychain group, CloudKit or iCloud KV; device backups stay and the confirmation copy says so (5.1 step 4). |
| F-V4 | nit | Accepted | Unsplash and Bedrock added to 2.4, to 8.9 and to the policy text (9). |
| F-V5 | nit | Accepted | SES suppression list noted in 2.4. |
| F-V6 | should-fix | Accepted | Row 14 (2.1): docstring correction is a D1 task (10); policy text says logs identify a person only by a pseudonymous account id (9). Also notes `edit_plan_job_submitted` and `coverage_job_submitted` log `job_id`. |
| F-V7 | should-fix | Accepted (mechanism chosen by me) | New "Restore resurrects deleted accounts" paragraph in 2.1; ledger row in section 3; new decision 8.15 (ledger object per deletion under a `deletion-ledger/` prefix in the media bucket, replay after any restore). The review also allowed "accept that a restore must re-run the worker"; I picked a ledger because the tombstone itself lives in a restorable table. |
| F1 | blocker | Accepted | 5.2: status flip then send, `503` on send failure, `last_enqueued_at` written in the flip, repeat POST re-sends when older than 5 minutes; 15-minute EventBridge resume rule that re-enqueues `deleting` rows (shortcut comment: Scan now, sparse GSI later); attempts cap, `failed_retrying`, operator `resume --uid`. 5.3: `quiesced_at` and `not_before`, re-enqueue with `DelaySeconds <= 900` in hops, resume rule makes DLQ loss non-fatal. Stated as completion of a user request, not expiry. D2/D3 updated. |
| F2 | blocker | Accepted | 5.3 phase 4 reordered: read identifiers (always including the `b_uid` Query on `__apple_txn__`), write `pending_global_keys` to the users row, delete or convert global rows, then delete the partition; every re-run reads `pending_global_keys` first. Phase 6 repeats the identifier read and counts the two global partitions. |
| F3 | blocker | Accepted | 5.2 rewritten: a path-scoped `allow_status` argument on `_principal_from_token`, passed by `auth_boundary` only for the two `DELETION_ROUTES`; tests that only those routes use it and that `deleted` is refused. Notes the `auth.py`/`main.py` overlap with Billing V2, so D3 runs after V2. |
| F4 | should-fix | Accepted, via the review's first option | Identity claim is kept (section 3, 5.3 tombstone guard 2, phase 8). `not_before` is also written as an invariant. New decision 8.13 (recommend keep). |
| F5 | should-fix | Accepted | 5.3 tombstone guard 3: `_account_status` fails closed for a claim with no users row; test "claim present, users row absent => 403"; tombstone rows are never deleted (section 3). |
| F6 | should-fix | Accepted | Section 4 item 4: the billing package cannot see the users table, so retained bindings are rewritten to `b_uid="__deleted__"`, `b_deleted=1` and `_apply` returns `account_deleted`. Pending Billing V2 (D4). 8.2 option (b) reworded to match. |
| F7 | should-fix | Accepted | 5.3 phase 2 uses the prefix listing for evidence (not the manifest) and aborts multipart uploads; phase 6 adds `ListMultipartUploads`; 5.4 grants `ListBucketMultipartUploads` and `AbortMultipartUpload`; section 3 states the sweep is user-initiated and does not contradict the evidence store's no-sweep note (`evidence_store/__init__.py:33-36`). |
| F8 | should-fix | Accepted as a decision | Phase 1 of 5.3 scans `edit-plan-jobs` by owner and cancels and deletes jobs and staging; new decision 8.14 with option (b) (gate plus TTL) and its residual window. Recommend (a). |
| F9 | nit | Accepted | Phase 6 text says the sweep exists because `user_quota.reserve` can recreate a row (`user_quota/__init__.py:258`) and `get_or_create_apple_account_token` creates on demand. |
| F-S1 | should-fix | Accepted | 5.3 opening: worker ignores the message's uid, proceeds only when the users row is `deleting` with a matching `deletion_request_id`; only the API role (and a break-glass role) can send. Operator CLI applies the same check (5.5). |
| F-S2 | should-fix | Accepted | 5.4 rewritten as a full worker-role grant list (S3, DynamoDB per table, SQS, Logs, Cognito), states the usage-table `DeleteItem` limit and the compensating control. |
| F-S3 | should-fix | Accepted | Phase 7: try `sub`, fall back to `ListUsers` with `Filter: sub = ...`; D1 exit criterion on dev. |
| F-S4 | should-fix | Accepted | 5.1 step 3: ephemeral session plus `prompt=login`/`max_age=0` for this flow only, confirm `auth_time` advances on dev, fall back to blocking the in-app Apple path (8.10); re-auth must not run `finishSignIn` adoption. |
| F-S5 | nit | Accepted | 5.2 first bullet: new claim read, required, refreshed token keeps its original `auth_time`, absent means `401`. Added to tests. |
| F-P1 | should-fix | Accepted | 8.10 reframed: revocation can gate the whole deletion release; precondition recorded in D5 and D7; 8.18 asks the question directly. Whether beta/prod pools have the Apple IdP stays unverified (no AWS call). |
| F-P2 | nit | Accepted, not done | Section 4 item 4 records "fetch and quote the current text of Guideline 5.1.1(v) before D8". I did not fetch it in this pass. |
| F-P3 | should-fix | Accepted | 8.3 now names the tension: a bounded trial-marker period implies an expiry mechanism, offered as (b1) none vs (b2) TTL. Section 3 states that resume and the verification sweep are completion of a user-requested deletion, not expiry. |
| F-P4 | should-fix | Accepted | Section 9 text: "within a day", logs identified by a random account id and expiring in 30-90 days, backups apply to the three auth tables only, Unsplash named, retained transaction identifier and tombstone disclosed. |
| F-P5 | nit | Accepted | Section 7: queue URL is wiring that fails closed with 503; the optional prod kill switch is dropped. |
| F-D1 | should-fix | Accepted | Section 7 states the dependency and new decision 8.16 (keep prod evidence persistence OFF until D1-D5 and the policy are live). |
| F-D2 | should-fix | Accepted | 8.2 rewritten: the transaction id is Apple-issued and linkable, not random; the duplicate-purchase claim is replaced with a likely lockout, marked unverified. Policy text discloses a retained transaction identifier. |
| F-D3 | should-fix | Accepted | 8.3 and 8.4 each end with one recommendation and a default if unanswered (8.3 default (a), 8.4 default (a)), and say they do not block the build. |
| F-D4 | should-fix | Accepted | Missing decisions added: 8.17 (email promise in the meantime, identity check), 8.14 (job scan), 8.13 and 8.15 (claim tombstone, ledger), 8.12 (approvals list moved from section 7), 8.18 (Apple sign-in in a deleting build). |
| F-D5 | nit | Accepted | 8.11 states the real trade-off, no undo versus extra retained data, and notes the tombstone also retains a small record. |
| F-D6 | nit | Accepted | 8.6 no longer "settled"; says an `off`-mode binding exists. |
| F10 | blocker | Accepted (hybrid) | 5.6 step 2: in session, delete every model through the context for the 22 schema types and reset in-memory stores; write a `wipe-pending` marker in `Library/`; at the next cold start, before the `ModelContainer` is created (`StoryApp.swift:44`), delete the store files and the marker. Default store location never relocated; the migration-failure path still never deletes (`:51-54`). Also cancels transfers. Device-only: marked as needing Ling's device build, not build-verified. I chose both options together because (b) alone leaves store files and (a) alone leaves the session open until a restart. |
| F11 | nit | Accepted | 5.1 step 4 copy says deletion completes within a day and describes the sign-in outcome before and after; D5 adds a distinct "deletion in progress" message for `accountDisabled`. |

## Final decisions for Ling (section 8)

8.1 Active subscription: allow, warn, link Manage Subscriptions (recommend a).
8.2 Apple identifiers: delete (a, default) or retain a marked row `__deleted__` (b, recommended, needs guard pending V2).
8.3 Trial marker: none (a, default) or keyed hash with a counsel-approved retention (b, recommended, built with V2).
8.4 Payment record: retain nothing beyond 8.2 (a, recommended and default) unless the accountant says otherwise.
8.5 Privacy text: publish only when the deleting build is in review.
8.6 Billing modes: no action now; re-check when V2 lands.
8.7 Local wipe: wipe all local data (a, recommended).
8.8 Confirmation email: none for the first release.
8.9 Provider copies: verify retention (including Bedrock logging, Unsplash) before publishing, then disclose.
8.10 Apple token revocation: research first, Apple sign-in off in the deleting build if not solved.
8.11 Grace period: none.
8.12 Approvals: approve D1 now; approve queue, Lambda, role, resume rule, billing change and each deploy separately.
8.13 Identity claim: keep as tombstone (recommended and default).
8.14 In-flight jobs: scan by owner and delete during quiesce (recommended and default).
8.15 Deletion ledger for restores: yes, object per deletion (recommended and default).
8.16 Prod evidence persistence: stay OFF until deletion and policy are live.
8.17 Email requests meanwhile: Ling runs the operator CLI after an identity check (recommended and default).
8.18 Apple sign-in in a deleting build: not before revocation works.

## Not checked

No AWS state, Cognito behaviour (`sub` as `Username`, `auth_time`, `prompt=login`), StoreKit re-purchase behaviour or iOS runtime was verified; Billing V2's changes were not read beyond `master`. The iOS wipe is SwiftData-touching and untested; the device Xcode build is the gate. Apple guideline text was not re-fetched.


---

## Round 2 response (2026-11-21)

Design revised in place as revision 2. Orchestration changed to one scheduled Lambda driven by a durable request item (Ling's direction), which removes the queue and with it R2-2 and part of R2-5 and R2-6. Billing V2 is merged on master (`2ea6a1b`, PR #141), so billing checks were done against it. One read-only AWS check on dev (Cognito identity providers and federated user count). Docs only: no code, branch, commit or mutating AWS call.

| ID | Severity | Chosen correction | Design section | Implementation verification criterion |
|---|---|---|---|---|
| R2-1 | blocker | Two files: `request.json` (pending request, no wipe authority) and `wipe-intent` (written only after acceptance). Lock view for the rest of the process; writers stopped and awaited; in-session row delete; delete everything except the open store's files; cold-start wipe of both store sets before any `ModelContainer`; in-memory container on failure; marker removed last | 5.7 | iPhone: force-quit at each stage L1-L6 and during cold start; relaunch shows an empty, usable app; content created after relaunch survives the next launch; migration-failure path wipes both store sets |
| R2-2 | blocker | No queue. Worker triggered only by the 5-minute rule; no `sqs:*` anywhere in deletion; permission matrix | 5.4, 5.11 | `cdk synth`: worker policy has no `sqs:*`; matrix rows match the synthesized policy; IAM simulator on dev |
| R2-3 | blocker | The request item is the ledger; finalize writes the tombstone with a condition that accepts `deleted`, then marks the request `completed`; both idempotent | 5.2, 5.4 | test: crash before, between and after the two finalize writes; every case converges to tombstone + `completed` |
| R2-4 | blocker | PITR restores into new tables; replay runs against them before the API is repointed; replay is driven by request items, not users-row status; active requests continue after repoint | 5.8 | test on fake restored tables: completed and active requests; repeat dry run reports zero rows before repoint |
| R2-5 | blocker | Conditional lease (360 s > 300 s timeout) plus owner- and `phase_seq`-checked advances; `ADD` for discovered sets; `if_not_exists` for `quiesced_at`/`not_before`; `fail_count` separate from waits; backoff 5-15-30-60-120 min then 6 h; alert at 5; retries continue; overdue and heartbeat alarms | 5.4 | tests: concurrent acquire, stale-run takeover, concurrent `ADD`, waits do not count, backoff schedule, alert set once |
| R2-6 | blocker | Acceptance = one `TransactWriteItems` (request item + receipt pointer + users flip); no enqueue after it. Client persists `request_id` and receipt secret before POST; 503/timeout/kill resolve through a public, receipt-authenticated status route that needs no token | 5.3, 5.7 | tests: commit/idempotent/409/503 paths; status route returns identical 404 for unknown id and wrong secret; iPhone: lost 202 and kill-during-submit resolve |
| R2-7 | should-fix | Stable `error` codes `account_deletion_in_progress` / `account_deleted` on the 403; only those count as confirmation; other device asks before removing local data (8.19); generic auth failures only sign out | 5.3, 5.7 | API test: codes present on every gated route; iOS: billing 403 and refresh failure never trigger the prompt |
| R2-8 | blocker | Jobs recorded at quiesce (`job_ids`), cancelled, deleted in verification; staging prefix derived from the recorded id; rescan each pass | 5.5 | test: a job created after quiesce is found, cancelled, row and staging deleted; dev: staging prefix empty after completion |
| R2-9 | should-fix | 70 min is a delay before verification. G1 caps single-PUT initiate at 16 MiB; multipart cannot complete behind the gate and is aborted; two clean passes ≥ 10 min apart; final check at 24 h with a late-found alert | 5.5 | API test for G1; dev: a 15 MiB PUT started just before submit is removed; verification lists and aborts multipart uploads |
| R2-10 | should-fix | TTL and lifecycle described as backstops only; explicit deletion and verification for jobs and staging | 2.1, 5.5 | review: no completion claim depends on TTL or lifecycle |
| R2-11 | should-fix | Delete `__apple_token__` before `__apple_txn__`, for every key in `global_keys` | 2.2, 5.4 | test: notification injected between the two deletes does not create a binding |
| R2-12 | should-fix | Verified on master: key shapes unchanged, `b_sub_*` in the same row, `apple.py` unchanged, off-mode token creation still present, discovery needs the `b_uid` Query. Restore Purchases after re-registration returns `app_account_token_mismatch` from code; documented as a v1 limitation; sandbox test before release | 2.2, 4, 7.3 | sandbox: renewal after deletion is `unmatched`; restore on the new account records the real outcome; a `not_active` bound txn is found and deleted |
| R2-13 | should-fix | Four questions separated; deletion release no longer gated on revocation (no build offers Apple sign-in); automatic revocation via native re-auth preferred; TN3194 fallback documented; focused test with its own preconditions (no Apple-linked account exists on dev to test against) | 6, appendix A, 8.10 | appendix A steps A3 and A8 decide between automatic revocation and the fallback |
| R2-14 | should-fix | Email locked to the current account; fresh token `sub` must equal the session `sub`; re-auth never adopts or re-keys | 5.1 | iOS test: mismatched `sub` stops submission |
| R2-15 | should-fix | Completed = phases 1-8 (two clean passes after `not_before`, Cognito delete, tombstone); in-app confirmation via the status route; email stays optional | 5.5, 5.7 | iPhone: confirmation appears once after completion and `request.json` is removed |
| R2-16 | nit | G2: `attribute_exists(job_id)` on the reconcile update | 5.5 | unit test in `edit_plan_jobs` |
| R2-17 | should-fix | "Pseudonymous" wording; WAF and IP retention stated; backups named; off-mode contradiction removed (5.6) | 3, 5.6, 9 | counsel review of section 9 |

### What changed

Orchestration (queue removed; request table as source of truth and ledger; lease and retry schedule; alarms), acceptance and status protocol, iOS wipe lifecycle, late-write verification and two writer guards, restore replay, Apple section and test plan, billing checks against merged V2, permission matrix, failure matrix (section 12), D1-D8 (D4 removed).

### Genuinely unresolved decisions

* 8.19: other devices ask before removing local data (recommended) or remove automatically.
* 8.3 and 8.4 stay with counsel and the accountant; outside v1.
* 8.9 provider retention must be checked before the privacy text is published.

### Checks still needed

* AWS (dev, read-only): `sub` as admin `Username`; `ListUsers` by sub; `auth_time` in a fresh access token (needs a test sign-in).
* AWS (beta/prod, needs SSO): Apple IdP and federated users on those pools; PITR window; KMS keys.
* iPhone: the wipe lifecycle (7.4); Restore Purchases and renewal in the sandbox (7.3); appendix A when Apple sign-in is planned.
* External: current text of guideline 5.1.1(v).

### Ready for implementation?

D1 is ready: no design blocker remains for the inert backend core. It needs only the normal PR. Before D2: Ling's approval of the new table, Lambda, role and rule. Before D3 deploys: G1 and G2 included. Before release: 7.3 sandbox results and the beta/prod Apple check. The iOS increment (D5) carries the device gate.
