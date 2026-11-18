# YoTale Billing V1: architecture, specification and phase report (B0 + B1)

Status: **B1 IMPLEMENTED and offline-tested on `feat/billing-v1-backend` (stacked on the B0 branch). Not merged. Not deployed.
`STORY_BILLING_MODE` is `off` in every environment (release manifest). No App Store Connect, AWS or live-data change.**
Cost inputs: `billing-b0-cost-attribution-and-unit-economics.md`, `billing-measured-cost-dev-beta.md`.
B2 (Apple), B3 (iOS), B4 (trial hardening, account deletion), B5 (rollout) are designed in section 14 and blocked on the owner actions in section 15.

## 0. Status by evidence level (what is and is not proven)

| Level | B0 (PR 1) | B1 (PR 2) |
|---|---|---|
| Implemented | yes | yes |
| Offline-tested (in-memory doubles, full backend suite) | yes | yes |
| DynamoDB Local-tested (real expressions, conditions, transactions) | n/a (no DynamoDB code) | **yes**: every ledger test runs on both the double and DynamoDB Local; job-store denial/recovery tests and the grandfather script run on DynamoDB Local |
| CI-tested | **pending**: CI runs on PR 1 after it is opened (base `master`) | **pending**: CI triggers only for PRs whose base is `master` (`ci.yml`: `pull_request: branches: [master]`), so the stacked PR 2 gets no CI run until PR 1 merges and PR 2 is re-based on `master`. The same checks were run locally (section 13). |
| Merged | no | no |
| Deployed | no | no |
| Live-verified | no | no (no deploy; the live dry-run in section 10 only READS the dev users table) |

Not done and not claimable from this environment: Apple purchase verification, real-device (Xcode) behaviour, App Store sandbox, music licensing, account deletion, beta-account live reads (the beta SSO session had expired).

## 1. Current-state inventory (verified in code on 2026-11-18, not from older milestone text)

| Area | Verified current behaviour |
|---|---|
| Identity and sign-up | Cognito email OTP. `selfSignUpEnabled: true` in CDK; the **development** pool (live check) has `AllowAdminCreateUserOnly=false` and no pre-sign-up trigger. The **beta** pool is built from the same CDK but was not live-checked (SSO expired). `IdentityStore.resolve` mints a random UUID4 `story_user_id` and sets `beta_access_status=invited` for EVERY first sign-in, and `invited` is admitted. **Effective behaviour: anyone who can complete email-OTP sign-up is admitted; there is no manual invite list in force.** The older "invite-only" milestone text is superseded. |
| Beta/dev posture | `release/release.json`: beta quota **enforce**, $50 per user per month, 500 gens per day, 2 active jobs, $60 global; throttle enforce; planner `edit_plan/5.6` time-boxed pin in development and beta until 2026-11-30; evidence persistence **on** (`evidence_persist: "1"`). |
| Reusable evidence | Server persistence is ON in dev and beta (`STORY_EVIDENCE_PERSIST_ENABLED=1`); no TTL or lifecycle (deliberate). Stored frames are a real, unmeasured storage cost and personal data. |
| Usage table | `story-<env>-user-usage`, PK `story_user_id`, SK `quota_period`, on-demand, PITR, RETAIN. API and worker roles hold `GetItem`, `UpdateItem`, `TransactWriteItems` on it (no `PutItem`, no `Query`, no `Scan`). |
| Quota module | Per-user USD, daily gens, slots and a global breaker via reserve/settle/release markers. Budget checks are read-then-write in application code (DynamoDB forbids arithmetic in conditions), so they are not atomic under concurrency; the active-job cap is atomic. It settles flat estimates, not actual cost. Unchanged except for the denial rollback in section 8. |
| Async jobs | `edit_plan_jobs`: `create_or_get` returns `created`; lease-fenced worker; `sweep_quota_orphans`; bounded `reconcile_lost_enqueue`. |
| Video routes | Async `POST /v1/edit-plan-jobs` (the app's Create / Another Version / Revise; `revision_context.mode`), plus sync `/v1/edit-plan` and `/v1/edit-plan-mm`. |
| AU | `POST /v1/asset-understanding`; 24 frames; server is stateless about results; the client PUTs results to `/v1/understanding` afterwards (client-supplied, so not usable as authority). `media_store` records are account-scoped and keyed `uuid5(owner + sha256)`; `cloud_verified` means S3 checked the full-file sha256. |
| Account deletion | **Not implemented.** No `DELETE /v1/account`, no Cognito deletion, no iOS screen. Only `evidence_store.delete_for_owner` (tested, unwired), per-Moment `DELETE /v1/evidence/{moment_id}`, and a debug-only local output delete. Media and generated MP4 backups are non-deleting. (Re-verified by code search; consistent with `milestone-p1f-reusable-au-evidence.md` section 5a and `i18n-zh-hans-launch-support.md`.) |
| iOS | No StoreKit, no entitlement model. |

## 2. Findings from the audit and the DynamoDB Local layer

1. **Latent production defect (fixed): coverage recovery could never run on a real table.** `_recover_failed_coverage` wrote `REMOVE ... diagnostics`, a DynamoDB reserved word; DynamoDB rejects the whole update. The in-memory double accepted it, so the "TMB after provider outage" recovery had never worked in production. Aliased (`#d`) and covered by a DynamoDB Local test.
2. **Latent defect (fixed): re-opened jobs could not re-take quota.** After the worker released a failed job, the `released` slot and allowance markers stayed, so a re-opened job found them and either 429'd (`active_jobs`) or counted as already reserved (spend never settled). The worker now drops terminal markers after release (spend totals untouched).
3. **Quota-denied jobs ran later with no authorization (fixed, all modes):** section 8.
4. **Sync planner routes had no per-video accounting.** Now gated.
5. **`sweep_quota_orphans` releases a COMPLETED job's quota hold.** For billing that would refund a delivered video, so the billing reconciler settles a completed job and releases every other terminal status.
6. **AU identity was client-chosen.** Fixed in section 7.
7. A denied submit that had already taken the allowance reservation (slot cap hit) leaked it into the per-user and global breaker totals until the orphan sweep. Now rolled back immediately.
8. The CI trigger gap for stacked PRs (section 0).

## 3. Product decisions and trial semantics (owner, 2026-11-18)

Free starter: no card; **30 unique new-Moment analyses and 2 video credits**; the 14-day clock starts at the **first successfully generated video**; reusing analysed Moments is free; guide and AI Ideas stay on fair-use limits; an upgrade is suggested after the first video and never blocks before the allowance or trial ends.
Plus (provisional, unchanged): $9.99 per month, 100 new Moments, 12 video credits per **Apple period**, no rollover. Allowances are reviewed code (`packages/billing/config.py`, stamped `billing-config/2`), not an environment setting. No Pro, annual, top-up, web checkout, family sharing or referral in V1.

Exact trial behaviour (all tested on both backends):

| Situation | Behaviour |
|---|---|
| Import and analyse Moments, no video yet | No clock. Bounded by the 30-analysis allowance only. |
| A video fails, is cancelled, or is denied | The clock never starts. |
| First video settles | `trial_end = settle time + 14 days`, set once (`if_not_exists`). |
| More Stories, retries, refunds, reinstall, re-login | Server-side per account; none of them moves or restarts the clock. |
| All 30 analyses used before the first video | `moment_allowance_exhausted` (402, action `subscribe`) for NEW Moments. The 2 video credits are untouched: the user can still create videos from already-analysed Moments; the clock then starts at the first video. Already-analysed Moments stay usable and free. |
| Trial ends | New analyses and videos return `trial_expired` (402). Delivered videos are untouched. |
| Pre-video allowance has no time limit | A free user who never makes a video keeps at most 30 analyses (about $0.34 of AI cost). Accepted, documented. |
| Another account | A new account is a new trial. Per-device and OTP abuse controls are B4. |

## 4. Data model and state machine

Same table, new sort-key namespaces. Live prefix `billing#`, observe-mode prefix `billing-shadow#`. Attributes are `b_`-prefixed.

| Item | PK / SK | Purpose |
|---|---|---|
| Entitlement | `uid` / `billing#entitlement` | plan, status, trial start/end, period id/start/end/grace, counters `b_v_*` and `b_m_*` (`total`, `avail`, `resv`, `used`), refunds, Apple original transaction id, `b_ver`, `b_evt_ts`, `b_gf_cutoff`, `b_cfg` |
| Video operation | `uid` / `billing#v#<uuid5(scoped operation id)>` | `b_state` (reserved / settled / released / refunded), `b_period`, timestamps, refund evidence |
| Analysis record | `uid` / `billing#m#<moment id>~<f or v><24 hex>` | `b_state`, `b_fp`, `b_bind`, `b_claim`, `b_ver`, `b_result` (cached analysis JSON, up to 300 KB), `b_fails`, `b_corr`, refresh claim `b_rf` |
| Account identity | `uid` / `billing#account` | `b_apple_token` (UUID, create-only). **Always live, in every mode where the entitlement endpoint is used.** |
| Apple binding | `__apple_txn__` / `billing#txn#<original transaction id>` | create-only owner binding |

Every state change is one `TransactWriteItems` over {operation record, entitlement}. Caps use `ADD avail -1` guarded by `avail >= 1`; no read-modify-write is relied on for consumption (mutation-tested: removing the guard fails the forced-interleaving tests on both backends). Statuses: `free_starter`, `plus_active`, `plus_grace`, `plus_expired`, `beta_grandfathered`, `admin_granted`; trial expiry and exhaustion are derived from timestamps and counters, not stored.

```
none -> reserved -> settled -> refunded (controlled)
           |  ^         ^
           v  |         '-- late settle: delivered work after a release
         released --reserve again (same operation retried)--> reserved
```
A reservation remembers its period; after a renewal, settling or releasing an old-period reservation moves only its record. Out-of-order Apple events are ordered by `event_ts`; all six arrival orders of a three-event sequence converge on the newest status and period.

## 5. API contracts (version 1)

`GET /v1/billing/entitlement`: `off` returns `{contract_version, billing_mode, enforced:false}` with **no billing read or write**. `observe` and `enforce` return plan, status, trial `{state, started_at, ends_at, days}`, period, `videos` and `moments` `{total, used, reserved, remaining}`, `refunds {used, allowed}`, `upgrade {eligible, suggest, blocking}`, `entitlement_version`, `apple_original_transaction_id`, `apple_app_account_token` (UUID).
HTTP 402 `{error: trial_expired | video_credits_exhausted | moment_allowance_exhausted | subscription_required, action: subscribe | wait_for_renewal | contact_support, contract_version, entitlement}`; 429 stays operational rate limiting; 503 `billing_unavailable` (enforce, store outage); 503 `analysis_in_progress` with `Retry-After: 5` (an identical analysis is still running; the on-device AU queue already treats 503 as "stay pending").
`POST /v1/billing/video-refund` (section 9).

## 6. Modes and the single configuration source

| Mode | Reads/writes | Customer effect |
|---|---|---|
| off (unset also means off) | **none**: the gate returns before any ledger access, including the identity token record (the earlier statement that the token exists "in every mode" meant only that it is never shadowed) | none |
| observe | shadow namespace, **plus the live `billing#account` token record when the entitlement endpoint is called** (identity, not usage; the only live write) | none: never denies, never reuses a cached result, always runs the model; would-deny/would-reuse decisions are logged. Proven by test: no live entitlement, counters, trial clock or reservation is ever written. |
| enforce | live ledger | typed 402 / 503, cached-result reuse, coalescing |

* Source of truth: `release/release.json` `environments.<env>.billing_mode` (all `off`). CDK emits it to the API and the worker (and fails the synth on any value outside `off|observe|enforce`); `release_config_gate.py` requires `STORY_BILLING_MODE` in both and verifies it equals the manifest; `enforce` additionally needs an owner-approved `approved_overrides` entry for that environment. No shell variable or CDK context can change it (tested).
* An **explicitly invalid value fails startup** (`create_app`) and the worker handler (`BillingConfigError`), so a typo can neither silently disable nor silently enable billing. Unset means off.
* `STORY_BILLING_PLANS_JSON` is **removed** (not merely audited): allowances are reviewed code. The release gate lists it in `REMOVED_SETTINGS`, startup rejects it, and an existing guard test already fails if any product code reads a removed switch.
* `STORY_QUOTA_MODE`, throttling, active-job slots and the global breaker are unchanged and independent.

## 7. AU source binding and inference idempotency

`packages/billing/analysis.py`. Identity is computed from facts the server holds, never from the client-chosen Moment id or a client sha:

* **Fingerprint:** sha256 over the accepted frame bytes and `t_ms` values, in order.
* **Verified source:** a client `content_sha256` is a CLAIM. It counts as an identity only when the SAME account owns a `cloud_verified` media record for exactly that sha (one `GetItem`, key `uuid5(owner+sha)`); another account's media, an uploading or failed record never verifies.
* **Record:** `(account, moment id, source)` where source is `v<verified sha>` or `f<fingerprint>`; with analysis version, bind level, claim, correlation id, cached result, failure count.

| Case | Result |
|---|---|
| Same id, same frames | completed result reused: no model call, no charge |
| Same id, different frames, no common verified source | a different source: new charged analysis (no free second analysis) |
| Same id, same verified original, different frames (reinstall, other device) | reused |
| Claim alone, or a claim naming another account's or an unverified upload | never reuses |
| AU before cloud verification | charged on the frames source; identical frames later still reuse after verification. A DIFFERENT device whose frames differ and whose claim is verified later pays one extra analysis (bounded; the normal R7 cross-device path restores from the understanding store and never calls AU) |
| Concurrent identical requests | one owns the work; the rest wait up to 25 s and return its result, else 503 `analysis_in_progress`; one model call, one charge (tested with 6 parallel requests) |
| Owner dies mid-analysis | reservation presumed dead after 300 s; the retry takes it over with no second charge |
| Failed analysis | allowance released; provider cost already in `model_call_usage` (same correlation id stored on the record, `b_fails` incremented); retry charges once |
| Analysis version upgrade | re-analyses with **no new charge** (already paid), result replaced; a failed refresh keeps the paid record |
| Same Moment used by several Stories | one analysis (AU carries no Story id) |
| Another account, same id and frames | analysed and charged separately; results never cross accounts |
| Unlimited (grandfathered) accounts | no records, no caching, no coalescing (not billed) |

Reuse, coalescing and the cached result exist only in `enforce`; `observe` records the shadow decision and still analyses. The existing understanding store was assessed and **not** used as authority: it is client-written after AU, keyed only by `(owner, moment_id)`, gated on a client sha, and cannot coalesce concurrent calls. No new table, no frozen-contract change; the cached result lives in the analysis record (deleted with the account partition). Residual risks: the 503 `analysis_in_progress` on the iOS AU queue and the 402 path are server-verified only, **device verification pending**; a hostile client can still force new charged analyses by altering frames (bounded by the allowance and existing throttle).

## 8. Quota-denied job recovery (all billing modes, including OFF)

A submit creates the job row before taking the quota hold. A denial returned 429 but left the row `queued`; the lost-enqueue reconciler would later enqueue and run it with no hold. Fix:
* A denied submit (edit-plan or coverage, quota or billing) calls `JobStore.deny`, which fails the row **only if still `queued`** (never a running job) with category `quota_denied` or `billing_denied`, and deletes staged inputs.
* The reconciler selects only `queued` rows and `claim_lease` only claims `queued` or expired-`running`, so a denied row can never run (tested on DynamoDB Local, including a stray SQS message).
* **Retry behaviour preserved:** the same client operation id after capacity frees is re-opened (reset to `queued`, `recovery_count` bumped, capped at 50) and reserves afresh; a denied submit returns its allowance immediately and drops the terminal marker so exactly one reservation results (tested). A different account with the same operation id is a different job.
* The allowed-duplicate path is untouched (still one enqueue). Quota enforcement itself is unchanged.
Residual: a process crash between `create_or_get` and the reservation still leaves a queued job with no hold; with billing enforced the worker would still settle a credit that was never reserved (a no-op), so the exposure is one unreserved job per crash. A pre-run authorization check in the worker is recommended for B5.

## 9. Refund safety review

| Requirement | Mechanism |
|---|---|
| Authenticated, owns the operation | `require_user`; the job must be the caller's COMPLETED job, else 404 (never confirms another account's job) |
| A real settled credit | the operation record must be `settled` under the caller's account; unbilled, unlimited, foreign or unknown operations are `not_eligible` |
| Idempotent | state guard: second claim is `noop`; 8 concurrent claims refund once |
| Evidence | closed `reason` (`render_failed`, `export_failed`, `playback_failed`; creative quality is not a reason), `render_attempts >= 2` (the stored plan is re-renderable with no new AI work, so a single failure is retried first), optional `client_build`; stored on the record for audit |
| Bounded | once per operation, 24 h window, same period, cap **Free starter 1, Plus 3 per period** (a free user can no longer loop their 2 credits) |
| Output untouched | refund never edits the job or plan; a re-submit of the same operation is recovered (`created=false`), queues no AI work and charges nothing (tested) |
| Residual | a false claim keeps the video and regains the credit, so the bounded cost is at most the cap (1 free, 3 Plus per period). The server cannot observe on-device rendering. The existing "never reject a technically playable video on creative grounds" policy is unchanged. |

## 10. Existing beta users (grandfathering)

`scripts/yotale_billing_grandfather.py`, owner-run per environment before `enforce`. **Dry run by default**; `--cutoff YYYY-MM-DD` required (UTC, no default); only accounts with `created_at` strictly before it, `active`, beta `invited`/`eligible`, not `--exclude`d. Later signups are never grandfathered (tested, including an account created exactly at the cutoff and accounts with no `created_at`). Prints environment, cutoff, counts per bucket, planned changes (create-and-grandfather, convert free starter, already in cohort, skipped other plan); ids hidden unless `--show-ids`. `--apply` needs `--confirm <environment>`; re-running changes nothing (`changed: 0`); a paid or admin account is never overwritten. **Rollback:** `--rollback` (dry run) then `--rollback --apply --confirm <env>` returns exactly the cohort grandfathered with this cutoff to a fresh Free starter (never another cohort, never an account that has since changed plan); idempotent.

Dry-run evidence (read-only; nothing written), 2026-11-18, illustrative cutoff `2026-11-19`:

| Environment | Result |
|---|---|
| development | 3 accounts scanned, 3 selected, `create_and_grandfather: 3`, would change 3, `skip_other_plan: 0` |
| beta | **not run**: the beta SSO session expired. Owner runs `aws sso login --profile yotale-beta`, then the dry run, and chooses the real cutoff. |

## 11. DynamoDB Local verification

Run: DynamoDB Local 3.3.2 (Temurin 21), in-memory, loopback, isolated uniquely named tables per test; **never a real `story-*` table** (the harness refuses a non-loopback endpoint). Every ledger test and the AU-binding, job-recovery and grandfather-script tests run on both the double and DynamoDB Local.

| Required scenario | Test(s) | Result |
|---|---|---|
| Two concurrent reservations, one credit left | `test_two_devices_racing_for_the_last_credit_one_wins`, forced stale-snapshot barrier tests (12 threads) | pass; mutation (guard removed) fails both backends |
| Duplicate reservation | `test_duplicate_reserve_settle_release_are_idempotent` | pass |
| Failed conditional write | exhaustion tests (typed 402 with snapshot) | pass |
| Transaction cancellation | `test_reserve_is_all_or_nothing_when_the_credit_guard_fails` (no orphan record) | pass |
| Worker crash after completion; settlement after recovery | `test_reconcile_after_worker_crash_between_result_and_settle` | pass |
| Release after cancellation | `test_a_cancelled_job_releases_its_reservation_through_reconciliation` | pass |
| Reservation crossing an Apple renewal | `test_in_flight_reservation_from_the_old_period...` | pass |
| Out-of-order entitlement updates | delayed-webhook test and all 6 permutations | pass |
| Late settlement, historical-period attribution | `test_late_completion_after_release...`, `test_a_reservation_keeps_the_period...` | pass |
| Refund after settlement | refund suite (evidence, caps, concurrency) | pass |
| Idempotent replay | `test_idempotent_replay_of_the_whole_lifecycle...` | pass |
| Stale-reservation recovery | reclaim tests, owner-died AU test | pass |

Defects the real engine found that the double could not: the reserved word `diagnostics` (finding 1), and the missing-marker behaviour behind finding 2.

**Procedure** (nothing to approve; local only): `export DDB_LOCAL_DIR=<dir with DynamoDBLocal.jar>` and `JAVA_BIN=<java>` (or `DDB_LOCAL_ENDPOINT=http://127.0.0.1:<port>` for a running instance), then `pytest packages/billing apps/api/tests`. Without DynamoDB Local the "local" variants **skip with the reason shown**; `REQUIRE_DDB_LOCAL=1` (set in CI) turns that into a failure. CI downloads DynamoDB Local (`dynamodb_local_latest.tar.gz`, not version-pinned) with `setup-java`.
**Isolated dev integration procedure (needs approval, not run):** create a throwaway table `story-development-billing-it-<random>` with the usage-table key schema in the dev account, point `STORY_USER_USAGE_TABLE` at it for one test session, run the same suites, delete the table. Never run against `story-<env>-user-usage`.

**IAM review.** The whole billing lifecycle uses only `GetItem`, `UpdateItem`, `TransactWriteItems` (asserted by a test that records every client call); these are already granted to the API and worker roles on the usage table, so **B1 needs no IAM change**. The verified-media check uses `GetItem` on the media table, already held by the API role. `dynamodb:Query` is used only by `reclaim_stale_moments`, which is **not on any request path or sweep**: a stale reservation is reclaimed, without a second charge, the next time that Moment is retried, and an abandoned one costs the user at most one allowance unit held. **Recommendation: do not grant `Query`.** The sweep degrades to a silent no-op without it (tested). Revisit only with a measured stuck-reservation rate and a CDK diff.

## 12. Data retention and account deletion (policy proposal; implementation is B4)

Billing data is account data and must follow the account lifecycle; nothing is "retained forever".
* **Deleted with the account:** entitlement, operation and analysis records (including the cached analysis result, which is derived from personal footage), shadow records, the Apple app-account token, the grandfathering marker. All live under the account's partition key, so one partition delete covers them.
* **Retained only where a legal requirement exists:** the minimum financial record of a real payment (Apple original transaction id, product id, dates, amount, refund status) in a separate, pseudonymised ledger keyed by a one-way hash, not by `story_user_id`. **The retention period is a legal decision (tax/accounting counsel); I do not assert one.** Free-starter and admin-granted users have no financial record, so nothing is retained for them.
* **Operational cost telemetry** (`model_call_usage`) holds the opaque `story_user_id` and token counts in CloudWatch under its log-group retention (beta 60 days), and no content; it ages out and is not rewritten.
* Account deletion today deletes none of this (section 1); it is a launch gate.

## 13. Verification summary (local, 2026-11-18)

| Suite | Result |
|---|---|
| Backend (`apps/api/tests`, `packages`, `contracts/tests`, `evals/harness`) with DynamoDB Local (`REQUIRE_DDB_LOCAL=1`) | **1569 passed** |
| Same, DynamoDB Local unavailable | **1471 passed, 98 skipped** (every `local` variant skipped with the reason printed) |
| CDK jest (`infrastructure/cdk`, all suites) | 77 passed, including 5 new `STORY_BILLING_MODE` posture tests |
| Release gate `pre`, development and beta (synthesized templates, offline) | ACCEPTED |
| Worker asset | `billing` imports with the standard library only |

## 14. Phases B2 to B5 (designed, not built)

**B2 Apple:** official App Store Server Python Library; `POST /v1/billing/transactions` verifies the signed JWS (bundle id, environment, product id, expiry, revocation, `appAccountToken` equals this account's token), `bind_apple_transaction`, `apply_subscription` with Apple's period boundaries; `POST /v1/billing/apple-notifications` verifies V2 payloads, orders by `signedDate`, dedupes by `notificationUUID`; reconciliation via the App Store Server API; separate sandbox and production credentials and records; a narrow path-scoped WAF rule, no blanket bypass. **B3 iOS:** StoreKit 2 paywall, remaining-credit and remaining-analysis UI, Settings status with Restore and Manage Subscription, 402/503 handling, en and zh-Hans; server-driven state; clips beyond the allowance import locally and wait for analysis. Device Xcode build is the gate. **B4:** OTP abuse protection and WAF review, App Attest or DeviceCheck with fallback, bulk-import limits, in-app account deletion per section 12, music licensing gate (Epidemic production rights, end-user sublicensing, rights in exported customer videos, commercial and social publishing, download pricing, safelisting). **B5:** run the grandfather script, `observe` on dev then beta, review shadow data, then `enforce` only with the owner's explicit approval and an `approved_overrides` entry.

## 15. Remaining owner approvals and actions

| Item | Owner |
|---|---|
| Merge PR 1 then PR 2 (protected workflow); re-base PR 2 onto `master` after PR 1 so CI runs | owner |
| Dev deploy of B0, then of B1 in `off`/`observe` (separate approvals; checklist in the B0 verification doc) | owner |
| Choose the grandfathering cutoff; run `aws sso login --profile yotale-beta`; run the beta dry run and review counts | owner |
| Decide the pre-run authorization check for the post-`create_or_get` crash window (section 8) | owner |
| Confirm `dynamodb:Query` stays ungranted (section 11) | owner |
| Apple Developer configuration (products, API key, notification URLs, agreements) and secrets in Secrets Manager from your terminal, never in chat | owner |
| Epidemic Sound commercial terms; legal retention period for payment records | owner / counsel |
| Real-device Xcode verification of the 402/503 behaviour and B3 | owner |

Launch readiness is **not** claimed. Remaining gates: Apple purchase verification, real-device tests, music licensing, account deletion, end-to-end sandbox acceptance.
