# YoTale Billing V1: architecture inventory, specification, and phase report (B0 + B1)

Status: **B1 IMPLEMENTED offline on `feat/billing-v1-backend` (stacked on `feat/cost-logging-all-ai-handlers`, 2026-11-18).
Not merged, not deployed, `STORY_BILLING_MODE` unset (= off). No App Store Connect, AWS, or live-data change.**
B2 (Apple), B3 (iOS), B4 (trial hardening), B5 (rollout) are designed here and blocked on the owner actions in section 10.
Cost inputs: `billing-b0-cost-attribution-and-unit-economics.md` and `billing-measured-cost-dev-beta.md`.

## 1. Current-state architecture inventory (verified in code, 2026-11-18)

| Area | What exists | Reusable for billing? |
|---|---|---|
| Identity | Cognito email OTP, invite-only. `IdentityStore.resolve` mints an immutable **random UUID4** `story_user_id` with an atomic claim. `/v1/me` returns it. Users row has `created_at`, `account_status`, `beta_access_status`. | Yes as the account key. Not as the Apple account token by contract (see 4.4). |
| Usage table | `story-<env>-user-usage`, PK `story_user_id`, SK `quota_period`, PAY_PER_REQUEST, PITR, RETAIN. `user_quota` stores USD ledger + daily gens + slots as attributes and `res#` markers on one item per month. IAM: `GetItem`, `UpdateItem`, `TransactWriteItems` only (no `PutItem`, no `Query`). | **Table and IAM: yes** (billing uses `UpdateItem` upserts and 2-item transactions). **Counters: no.** The quota "gens" counter counts every paid op (AU included), is monthly/daily calendar based, and is a spend guardrail, not an entitlement. |
| Atomic caps | `user_quota` enforces its budgets by **read then write in application code** (DynamoDB forbids arithmetic in conditions). Two concurrent reserves can both pass the read. | **No.** Billing needs a true compare-and-set. It stores `avail` and reserves with `ADD avail -1` guarded by `avail >= 1` (comparison, not arithmetic). |
| Paid route map | `throttle.ROUTE_CLASS` is the single route map; `quota_gate.PAID_CLASSES` derives from it; a test enforces coverage. | Yes. Billing adds its own explicit classification, also test-enforced. |
| Async jobs | `edit_plan_jobs` store: `create_or_get` returns `created`; worker leases with a fencing token; `complete` is conditional on running + lease; `sweep_quota_orphans` finalises crashed jobs. SQS redelivery is possible. | Yes: `created` is the dedup authority; the sweep is the reconciliation driver. |
| Edit-plan paths | Async `POST /v1/edit-plan-jobs` (the app's Create / Another Version / Revise; mode is `revision_context.mode` = original / explore / revise) and **sync** `POST /v1/edit-plan` and `/v1/edit-plan-mm` (reachable by any authenticated user). `/v1/story-coverage/v2/jobs` shares the `ai_job_submit` class but is analysis support, not a video. | Billing gates all three video routes. Coverage jobs are explicitly exempt. |
| AU | `POST /v1/asset-understanding` (async handler, `moment_id` in multipart meta, exactly 24 frames). Stateless on the server; the device calls it only for Moments lacking a local understanding. No server-side "already analysed" set. | Billing keeps the unique-Moment set (section 4). |
| Cost data | `packages/observability` price table; `model_call_usage` (B0). | Used for economics only; billing is not cost-based. |
| Release config | `scripts/release_config_gate.py` rejects any env setting not in its registry; posture is a reviewed edit (CDK + `release/release.json`). | Registering `STORY_BILLING_MODE` is part of the rollout PR (section 9). Code treats **unset as off**, so B1 needs no infra change. |
| iOS | No StoreKit, no entitlement model. `CloudAuthGate` gates paid flows behind sign-in. | B3. |

## 2. Gap assessment and findings (pre-existing issues surfaced by the audit)

1. **Sync planner routes bypass any per-video accounting** (`/v1/edit-plan`, `/v1/edit-plan-mm`). Now gated by `billing_middleware`.
2. **Quota-denied async job stays `queued` and un-enqueued**, so `reconcile_lost_enqueue` can later run it with no hold. The billing paths terminalise
   their own denials (`failed`, category `billing_denied` / `quota_denied`). The quota-only denial path (billing off) is unchanged: **recommended fix, not made**.
3. **`sweep_quota_orphans` releases the quota hold of a COMPLETED job** whose worker died before settling. For billing that would refund a delivered video, so the billing
   reconciler **settles** a `completed` job and releases every other terminal status (`reconcile_video_job`).
4. **`user_quota` budget checks are not atomic** under concurrency (read then write). Not changed; billing does not depend on them.
5. **No per-Moment idempotency exists server-side**, so retries, duplicate uploads and concurrent duplicate AU calls are all indistinguishable. Billing keys the charge on the Moment id.
6. **AU reuse can be abused (known limitation, B4 blocker candidate):** `moment_id` is client-supplied, so a hostile client could resend a previously analysed id with new frames and get free analyses.
   Bounded today by the existing throttle and per-user daily/USD quota (about $5/day at the beta caps). Options for B4: bind the free-reuse rule to the `content_sha256` claim, or cap free
   re-analyses per Moment. Needs an owner decision before public signup.
7. `/v1/me` returns only `story_user_id`; no entitlement. Added `GET /v1/billing/entitlement`.
8. The Apple `appAccountToken` must be a UUID. `story_user_id` happens to be UUID4 today, but that is an implementation detail; billing mints and persists a separate UUID.

## 3. V1 product decisions (as instructed)

Free starter: no card; 14 days from the **first successful billable operation**; 30 unique newly analysed Moments; 2 video credits; upgrade suggested after the first video, never blocking
until the allowance or trial ends; server-side so it survives reinstall. Plus (provisional): $9.99 per month, 100 unique new Moments, 12 video credits per **Apple period**, no rollover;
delivered videos stay after cancellation. Create, Another Version and Revise each cost one credit. Guide and AI Ideas stay on fair-use limits. Deferred: Pro, annual, top-ups, web checkout,
family sharing, referrals, weighted credits. Allowances are configuration (`BillingConfig`, one optional env `STORY_BILLING_PLANS_JSON`); the ledger has no plan-specific code.

## 4. Data model (same table, new sort-key namespaces)

Namespace prefix `billing#` (live) or `billing-shadow#` (observe mode). All attributes are `b_`-prefixed to avoid DynamoDB reserved words.

| Item | PK / SK | Purpose |
|---|---|---|
| Entitlement | `story_user_id` / `billing#entitlement` | plan, status, trial start/end, period id/start/end/grace, `b_v_*` and `b_m_*` counters (`total`, `avail`, `resv`, `used`), refunds, Apple original transaction id, `b_ver` (entitlement version), `b_evt_ts` (last applied Apple event time) |
| Video operation | `story_user_id` / `billing#v#<uuid5(scoped operation id)>` | `b_state` (reserved / settled / released / refunded), `b_period`, timestamps, refund reason. Durable audit record; never deleted. |
| Moment | `story_user_id` / `billing#m#<moment id lowercased>` | same states; one per account per Moment, forever |
| Account identity | `story_user_id` / `billing#account` | `b_apple_token` (UUID, create-only). Live namespace in every mode. |
| Apple binding | `__apple_txn__` / `billing#txn#<original transaction id>` | create-only owner binding, so one transaction can never grant two accounts |

Why this shape: every transition is one `TransactWriteItems` over {operation item, entitlement item}, so the counter and its record cannot disagree and a retry cannot double count.
Invariant (asserted in tests): `avail + reserved + used = total` per meter (overage after a late settle is the only documented exception).

Statuses: `free_starter`, `plus_active`, `plus_grace`, `plus_expired`, `beta_grandfathered` (unlimited), `admin_granted` (finite, optional expiry). Trial expiry and exhausted allowances are **derived**
from timestamps and counters, not stored as plan states, so no sweeper is needed and they are independent of plan status.

### State machine (all transitions idempotent and state-guarded)

```
none ──reserve──▶ reserved ──settle──▶ settled ──refund (controlled)──▶ refunded
                     │                    ▲
                     └──release──▶ released ─┘ (late settle: work was delivered after a release)
released ──reserve (same operation retried)──▶ reserved
```
A reservation remembers the period it was charged against. After a renewal the counters are new; settling or releasing an old-period reservation moves only its record.

### Failure and recovery matrix

| Situation | Result |
|---|---|
| Duplicate submit / client retry | `created=false` reserves nothing; same operation id returns the existing hold |
| Duplicate SQS delivery | settle/release are state-guarded no-ops |
| Two devices, one credit left | exactly one reserve wins (forced-interleaving test) |
| Worker timeout, then orphan sweep | job failed, credit released (a **late** completion cannot publish: lease fenced) |
| Worker crash after result recorded, before settle | sweep settles it (job status `completed`) |
| Release after settle (late failure path) | no-op: a delivered video is never silently un-charged |
| Concurrent duplicate AU of one Moment | one charge; duplicates ride in flight; only the charge owner releases |
| AU request crashes mid-flight | stale reservation (30 min) reclaimed on retry, or by the sweep (needs `dynamodb:Query`) |
| Backend success, device render fails | controlled refund endpoint (capped, windowed, once per operation) |
| Billing store outage | enforce: 503 `billing_unavailable` (fail closed); observe: ignored |

## 5. API contracts (version 1)

`GET /v1/billing/entitlement` (authenticated). `off` returns `{contract_version, billing_mode, enforced:false}`. Otherwise:

```json
{"contract_version":1,"billing_mode":"enforce","enforced":true,"plan":"free_starter","status":"free_starter","unlimited":false,
 "trial":{"state":"not_started|active|expired|not_applicable","started_at":null,"ends_at":null,"days":14},
 "period":{"id":"starter","start":null,"end":null},
 "videos":{"total":2,"used":0,"reserved":0,"remaining":2},"moments":{"total":30,"used":0,"reserved":0,"remaining":30},
 "refunds":{"used":0,"allowed":3},
 "upgrade":{"eligible":true,"suggest":false,"blocking":false},
 "entitlement_version":1,"apple_original_transaction_id":null,"apple_app_account_token":"<uuid>"}
```

HTTP 402 (entitlement or payment restriction; 429 stays operational rate limiting):

```json
{"error":"trial_expired|video_credits_exhausted|moment_allowance_exhausted|subscription_required",
 "action":"subscribe|wait_for_renewal|contact_support","contract_version":1,"entitlement":{ ...same snapshot... }}
```

503 `{"error":"billing_unavailable","retry_after_seconds":30}` (enforce, store outage). `POST /v1/billing/video-refund {operation_id, reason: render_failed|export_failed|playback_failed}`
returns `{result: refunded|noop|not_eligible:<why>, entitlement}`; 404 unless the caller owns a **completed** job for that operation. Route classes registered: entitlement `read`, refund `writes`.
B2 will add `POST /v1/billing/transactions` and `POST /v1/billing/apple-notifications` (section 8).

## 6. Modes (`STORY_BILLING_MODE`, independent of `STORY_QUOTA_MODE`)

| Mode | Reads/writes | Customer effect |
|---|---|---|
| off (default; also any invalid or unset value) | none | none: existing beta behaviour |
| observe | shadow ledger only (`billing-shadow#`) | none: never denies, nothing live debited; `billing_would_deny` logged and counted. Flipping to enforce starts from clean counters. |
| enforce | live ledger | 402 / 503 as above |

Rate limits, active-job slots and the global breaker are unchanged. There is **no hidden per-user dollar cap** in billing: an ordinary subscriber is never blocked before their advertised allowance.
Cost control is anomaly alerting on `model_call_usage` plus the existing global breaker; exceptional abuse is handled by `admin_grant` or account status.

## 7. Enforcement coverage (test-enforced)

`BILLED_ROUTES` (spend a unit): `POST /v1/edit-plan`, `/v1/edit-plan-mm`, `/v1/edit-plan-jobs` (video); `POST /v1/asset-understanding` (Moment).
`BILLING_EXEMPT` (paid class, deliberately unmetered, fair-use only): creative intent, interpret revision, scene understanding, coverage (v1, v2, v2 jobs), guide (v1, v2, refine), music plan,
duration recommendation, director, music provider routes, scene image/video. `test_every_paid_route_is_explicitly_billed_or_exempt` fails CI for any new paid route left unclassified.
Sync planner routes use middleware (inside quota, so a 402 is seen by quota as non-2xx and released). The async route reserves after `create_or_get` and before the quota hold, and a denied job is terminalised.

## 8. Phases B2 to B5 (designed, not built)

**B2 Apple server integration** (needs owner actions below): official App Store Server Python Library; `POST /v1/billing/transactions` verifies the signed JWS (bundle id, environment, product id, expiry,
revocation, `appAccountToken` equals this account's token), then `bind_apple_transaction` (one transaction, one account) and `apply_subscription` with Apple's period boundaries. `POST /v1/billing/apple-notifications`
verifies the V2 signed payload and applies it in `signedDate` order (`apply_subscription` already ignores older events and redeliveries); duplicates keyed by `notificationUUID`. Reconciliation job calls the
App Store Server API for each active subscriber to repair missed webhooks. Sandbox and production credentials, validation and records are separate (`environment` is part of the binding key).
No blanket WAF bypass: a narrow rule scoped to the one path plus cryptographic verification (a path allow rule, body size cap, and rate limit by source).

**B3 iOS:** StoreKit 2 paywall (localized price from the product, period, renewal and cancellation text), remaining credits on Create/Revise, remaining analysis on Import, Settings status with Restore Purchases and
Manage Subscription, 402 handling, English and Simplified Chinese. Server-driven entitlement state; no SwiftData migration. Clips beyond the Moment allowance import locally and are marked "waiting for AI analysis".
**Device Xcode build is the authoritative gate; this cannot be built or verified in the agent sandbox.**

**B4 Trial and public-launch:** the free trial is account-scoped and already survives reinstall. Open signup requires OTP abuse protection and WAF review, App Attest or DeviceCheck with a safe fallback,
bulk-import abuse limits (limitation 6), and in-app account deletion across Cognito, users/claims rows, media, analysis, evidence, and billing identity (financial and tax records retained as required).
**Music licensing gate:** commercial launch stays blocked until Epidemic Sound confirms production API rights, end-user sublicensing, rights in exported customer videos including social and commercial publishing,
download-based pricing and allowances, and safelisting. A personal Epidemic subscription does not license YoTale's customers.

**B5 Rollout:** register `STORY_BILLING_MODE` (class C) in `release_config_gate.py`, `release/release.json` and CDK with a CDK test; grant `dynamodb:Query` to the API role if stale-reservation sweeping is wanted;
run the grandfathering script; `observe` on dev, then beta; review shadow data; then `enforce` with explicit approval. Sandbox purchase and notification tests precede any TestFlight paid acceptance.

## 9. Provisional unit economics (from B0; assumptions flagged there)

| Plan | Full-allotment AI cost | Margin at 15% Apple | Margin at 30% Apple |
|---|---|---|---|
| Free starter (30 Moments + 2 videos) | $0.45 to $1.00 | n/a (no revenue) | n/a |
| Plus $9.99, 12 videos on 30-sheet stories | $3.73 | 54% | 45% |
| Plus $9.99, 12 videos on 90-sheet stories | $4.66 | 43% | 31% |

Negative only if unmeasured components cost $0.30 or more per video with heavy retries. Re-run `scripts/billing_unit_economics.py` after one week of `model_call_usage` data and before fixing prices.

## 10. Owner actions and blockers

| Needed | Who |
|---|---|
| Approve dev deploy of B0 logging, then one week of data | owner |
| Decide the AU-reuse abuse mitigation (limitation 6) before public signup | owner |
| Apple Developer: create the subscription group and Plus product in App Store Connect, set the Apple **App Store Server API key**, shared secret, and server notification URLs (sandbox and production), agree paid-apps terms and tax/banking | owner (agent must not invent product ids) |
| Provide Apple credentials into Secrets Manager from your own terminal (never pasted in chat) | owner |
| Epidemic Sound commercial agreement covering the items in B4 | owner / legal |
| Register `STORY_BILLING_MODE` in the release gate and CDK; optional `dynamodb:Query` IAM grant | rollout PR (needs approval) |
| Run `scripts/yotale_billing_grandfather.py --environment <env> --profile <sso profile>` (dry run first) before enforce | owner |
| Real-device Xcode build and tests of B3 | owner |

## 11. B1 verification

| Check | Result |
|---|---|
| `packages/billing` ledger tests | 50 passed (idempotency, concurrency, forced stale-snapshot interleaving, trial boundary, renewal, in-flight old-period settle, out-of-order webhook, grace, refund caps, shadow isolation, Apple binding, grandfathering) |
| `apps/api/tests/test_billing_gate.py` | 20 passed (three modes, typed 402, fail-closed 503, duplicate submit, quota-denial release, AU unique-Moment charging, sync routes, entitlement and refund endpoints, route coverage, worker settlement) |
| Full backend suite (`apps/api/tests`, `packages`) | all passing |
| Mutation check | removing the `avail >= 1` guard makes 3 race tests fail, so the guard is what prevents overspend, not timing |
| DynamoDB realism | in-memory double evaluates real condition/update expressions, rejects arithmetic in conditions and unused expression values; **not run against real DynamoDB** (no deploy) |
| iOS, Apple sandbox, real-device | **not done; cannot be done in this environment** |

Launch readiness is **not** claimed. Remaining gates: Apple purchase verification, real-device tests, music licensing, account deletion, and end-to-end sandbox acceptance.
