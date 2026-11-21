# Billing V2: unlimited YoTale Plus and subscription UX fixes

Status: **IMPLEMENTED and offline-tested on `feat/billing-v2-unlimited-plus` (base `origin/master` `40a77f5`, 2026-11-20). Not merged, not
deployed, no App Store Connect change, no dev/beta AWS data read or written, no live inference.** iOS changes are parse-checked only
(`swiftc -parse`); the authoritative iOS gate is the owner's device Xcode build and Cmd-U.

Inputs: the owner brief (2026-11-20, Billing chat) and the independent plan review
(`~/.kiro/crew/workspace/reviews/yotale-billing-v2-plan-review.md`, findings B1-B6, S1-S9, N1-N2). This document supersedes the finite
Plus allowance (12 videos, 100 new Moments) described in `billing-v1-spec.md`, `billing-b2-apple-server.md`, `billing-b3-ios.md` and
`billing-b0-cost-attribution-and-unit-economics.md`.

## 1. Product decision (owner, final)

- **YoTale Plus = $9.99/month** (the app shows StoreKit's localized price).
- While the subscription is active or in Apple's grace period, Plus is **unlimited ordinary use**: Create, Highlights, Full Story,
  Create Another Version, natural-language and deterministic Revise, and Asset Understanding (AU) of new Moments.
- No numeric monthly limit, no hidden ceiling, no per-subscriber USD or daily cap that stops ordinary use, no credit balance.
- **Free starter unchanged**: 2 videos, 30 new Moments, 14-day trial clock that starts at the first settled video.
- Temporary capacity limits are a retryable "busy", never "out of credits".
- Unusual automated, abusive or compromised-account traffic is handled by the existing security and abuse policy, not by a disguised
  allowance.

## 2. Three different things (do not mix them up)

| Layer | What it decides | Where | Applies to Plus? |
|---|---|---|---|
| **Entitlement** | May this account start this kind of work at all? Typed HTTP 402 (`trial_expired`, `video_credits_exhausted`, `moment_allowance_exhausted`, `subscription_required`). | `packages/billing` (ledger), `apps/api/app/billing_gate.py` | Plus active/grace: always allowed. Lapsed Plus: `subscription_required` only. |
| **Metering** | One record per operation (video) and per analysed source (Moment): reservation state, cached AU result, coalescing, idempotency, cost attribution. Counters only for finite plans. | same | Records **kept**; counters **skipped** (`b_unmetered` on the record). |
| **Operational protection** | Keeps the service healthy: rate limits (throttle), active-job concurrency, the shared global spend breaker, WAF. HTTP 429 (or 503 for a store outage). | `apps/api/app/throttle.py`, `apps/api/app/quota_gate.py`, `packages/user_quota`, WAF in CDK | Yes, unchanged, except the two per-user caps below. Temporary limits answer `busy: true`. |

Per-user quota caps (`packages/user_quota`): `user_monthly_usd` and `user_daily_gens` are **not applied to a verified active Plus**
(read from the live ledger in every billing mode). For Plus, USD is still reserved and settled, so cost attribution and the global
breaker keep working. If the entitlement read fails, the normal caps apply (never uncapped). Free, grandfathered and admin accounts keep
both caps.

## 3. What changed

### Commit A: the observed "paid but still Subscribe / Sign in" bug
- `POST /v1/billing/transactions` returns `entitlement` in the same shape as `GET /v1/billing/entitlement` (the bare ledger view lacked
  `billing_mode`/`enforced`, which made the shipped client's decode fail) (S3).
- `AuthStore.fetchAccessToken(forceRefresh:)`: a network failure during refresh no longer signs the user out (B6).
- `BillingService`: refreshing token, exactly one refresh-and-retry on 401, decode failures surfaced, the purchase response is not
  decoded at all; after an accepted transaction the store reads `GET /v1/billing/entitlement` directly (the `refresh()` phase no-op,
  review item 5).
- `BillingStore`: stale notices cleared on success, one in-flight post per transaction, `recoverPendingTransactions()` on sign-in and
  foreground (re-posts `Transaction.unfinished`, and `currentEntitlements` while the server does not show Plus), and a `verifying`
  state that shows "Confirming your subscription" instead of Subscribe to someone who has paid.

### Commit B: backend unlimited Plus
- Unlimited is derived (`Entitlement.unlimited_at`), never stored for Plus; expiry is checked before any unlimited shortcut (B4).
- No Plus `PlanLimits`; `apply_subscription` writes no finite Plus totals; `config_version` = `billing-config/3` (S1). Legacy finite
  Plus records read as unlimited with no migration write. Apple identity and transaction history are untouched.
- Unlimited accounts take the same record transitions and skip only the counter leg; the counter leg is decided from the record, so a
  pre-V2 reservation settled after V2 does not leave `b_*_resv` stuck and an unmetered record never decrements a counter (B3).
  `Hold.owns` / `Gate.owns_operation` / `AnalysisPlan.owns` separate owning the operation from owning a charge, so failed unmetered work
  is released.
- A grandfathered (or admin) account that buys Plus gets the subscription recorded beside the plan (`b_sub_*`): it shows as active and
  `revoke_grandfather` converts it to Plus instead of dropping a paid subscription (S8).
- Observe mode shows a subscriber the live Plus view and never logs would-deny for one (S2).
- A job reserved at submit keeps its record, so a Plus that lapses while the job waits in the queue still runs it.
- Busy shape: the `active_jobs` and `global_monthly_usd` 429s and the throttle 429 add `busy: true` and a short Retry-After (30 s,
  300 s, the throttle window). `error`, `scope` and `retry_after_seconds` are unchanged for shipped clients.

### Contract (`contract_version` 2, additive, B5)

| Field | Contract 1 | Contract 2 |
|---|---|---|
| `videos`, `moments` | object | object for finite accounts, **null** for unlimited accounts |
| `unlimited` | stored flag | derived at read time |
| `offer.plus` | `product_id`, `videos`, `moments` | adds `unlimited: true`. `videos`/`moments` stay ONLY so contract-1 builds decode (they are non-optional Ints there); not a limit |
| `capabilities` | absent | `{version, video_generation, moment_analysis: unlimited|metered, subscription: {status: active|grace|expired|none, ends_at}}` |
| `refunds.allowed` | per plan | 0 for unlimited accounts |

Proof: `apps/api/tests/test_billing_v2_unlimited_plus.py::test_the_v2_payload_still_decodes_with_the_contract1_model` (Python mirror of
the required contract-1 fields) and `StoryTests/BillingModelsTests.swift::BillingV2ContractTests` (copies of the shipped Swift structs).

### Commit C: iOS
Paywall ("Create without overthinking."), five benefits, "YoTale Plus — <price>/month", the meaning of unlimited, auto-renew terms,
Restore, Terms and Privacy. Active screen: YoTale Plus / Active / Unlimited video creation and editing / verified renewal or expiry date
("Access until" when auto-renew is off) / Manage Subscription / Restore; no Subscribe. Counters only for Free starter and admin grants
(S6). Plus credit copy removed in EN and zh-Hans. Retryable busy in `EditPlanJobError` and `AssetUnderstandingServiceError` (footage is
never parked for a busy). No SwiftData migration; the billing screen makes no AI call.

## 4. Parked owner decisions (not changed by this PR)

1. **Per-user velocity valve** for a compromised Plus account (review B2.4). Not added. After the exemption, the only per-user brake is
   the throttle (`ai_sync` 20/min, `ai_job_submit` 10/min). The owner said to use the existing abuse policy.
2. **`STORY_QUOTA_GLOBAL_MONTHLY_USD`** (beta $60, shared by all users). With unlimited Plus a few heavy subscribers can trip it for
   everyone (it now answers busy with Retry-After 300 s). Resizing is a `C`-class release setting.
3. **`release/release.json` quota values** (`user_monthly_usd` 50, `user_daily_gens` 500, `max_active_jobs` 2, global 60): unchanged.
4. **Server-side auto-renew status** (`DID_CHANGE_RENEWAL_STATUS`): not tracked. "Access until" vs "Renews" wording comes from StoreKit's
   signed renewal info on the device; the date is the server's.
5. **`POST /v1/billing/video-refund`**: kept (finite plans only; unlimited accounts get `not_eligible:period_or_plan`). No iOS caller.
6. **Legacy `offer.plus.videos/moments`**: remove once no contract-1 build is in use.

## 5. Cost and abuse monitoring (documentation only; no CloudWatch or CDK resources in this PR, S9)

Source data: the B0 `model_call_usage` log lines (per call: operation, served model, tokens, estimated USD, correlation id), the billing
records (`billing#v#*`, `billing#m#*`, now kept for Plus too) and the quota items (`settled_usd`).

Metrics to build (dashboard owner: the observability thread):
- Active paying subscribers (plan `plus`, effective status active or grace, plus grandfathered accounts with an active side subscription).
- Total AI spend per month; AI spend per subscriber.
- Video operations per subscriber (Original / Explore / Revise split) and new Moments analysed per subscriber.
- Monthly serving cost per subscriber: mean, p50, p90, p95, p99.
- Retry and failed-operation cost (released records joined to their incurred cost).
- Heavy-user share: spend of the top 1% and top 10% of subscribers as a share of total.
- Estimated gross margin at 15% and 30% Apple commission (net = $9.99 x (1 - commission)), with unmeasured infrastructure and music
  expenses shown separately.
- AU reuse rate (cached results served / AU requests) and coalesced duplicates, to confirm reuse still works for unlimited accounts.

Proposed anomaly alerts (for review; NOT monthly caps and not to be converted into one):
- One subscriber's daily AI spend above 10x the p99 of subscribers (possible compromised account): page, then the support action in the
  abuse policy.
- Global month-to-date spend above 70% and 90% of `STORY_QUOTA_GLOBAL_MONTHLY_USD` (the breaker would start answering busy).
- Any `busy` 429 with scope `global_monthly_usd` (customers are being turned away).
- Retry cost above 30% of total AI spend for a day.
- `BillingStoreError` or `billing_live_plus_read_error` rate above baseline (subscribers falling back to normal caps).

## 6. Unit economics (SIMULATION, `scripts/billing_unit_economics.py`)

The Plus section is now a sensitivity over 10, 30, 60, 100 and 300 video operations per subscriber-month, for 30- and 90-sheet Stories
and 30 or 150 new Moments, at 15% and 30% commission. Per-operation cost comes from the measured token fits (labelled MEASURED in the
script); the operation mix (50% Original / 30% Explore / 20% Revise), the $0.10 per-operation unmeasured buffer and the import volumes
are ASSUMPTIONS. Under those assumptions break-even is about 18-31 operations per subscriber-month; the unmeasured buffer is the largest
single term. These numbers are for monitoring and planning. They do not authorize a quota.

## 7. Apple sandbox acceptance checklist (owner, device build)

Use the sandbox Apple ID and the beta or dev backend. Record the build SHA, account and time for each row.

| # | Case | Expected |
|---|---|---|
| 1 | Free user subscribes | Purchase sheet, then "Confirming your subscription" at most briefly, then the Active screen; no "Sign in" notice. |
| 2 | Already subscribed user opens the paywall | Active screen, no Subscribe. |
| 3 | Purchase while the access token is expired (leave the app idle > 1 h, then buy) | One 401, a silent refresh, retry succeeds; Active screen; no stale notice. |
| 4 | Purchase in airplane mode after the sheet completes | "Confirming your subscription"; the user stays signed in; turning the network on and foregrounding confirms it. |
| 5 | Kill the app right after the purchase sheet, relaunch | Recovery on launch/sign-in posts the unfinished transaction; Active screen. |
| 6 | Restore Purchases after reinstall | Active screen. |
| 7 | Second device, same Apple ID and same YoTale account | Active screen. |
| 8 | Sign out and sign in to a different YoTale account on the same Apple ID | No Plus for the other account; no lingering "Confirming". |
| 9 | Cancel in Settings (still inside the period) | Active screen with "Access until <date>". |
| 10 | Let the sandbox subscription expire | Paywall again; a new Create returns `subscription_required` copy, never credits copy. |
| 11 | Renewal and billing-retry grace (sandbox settings) | Renewal keeps Active; grace shows the payment-issue line and keeps access. |
| 12 | Refund or revoke from the sandbox | Access ends; paywall. |
| 13 | Grandfathered beta account buys Plus | Active screen (S8). |
| 14 | Plus: create more than 12, 30 and 60 videos (mix Create, Another Version, Revise) on a small Story | No credits or monthly-limit message. Space them out to stay under active-job concurrency (2); a third concurrent one shows the retryable busy screen with Try again. |
| 15 | Plus: import more than 100 new Moments | Analysis continues; nothing parks for an allowance. |
| 16 | Free starter: use 2 videos, then a third | The Free 402 upgrade screen. |
| 17 | Billing service unreachable (bad network) while opening the screen | No sign-out; the last known state stays. |

Note for beta: `STORY_BILLING_MODE` is `off` on beta, and beta quota is `enforce` with a $60 global breaker. Rows 14-15 burn real model
spend and must be run within the owner's approved test budget, not as a stress test.

## 8. Missing icon and "UNRATED" on the sandbox purchase sheet

Not verified. Two candidate causes; check both before attributing it:
- **Sandbox artifact**: development and TestFlight builds signed for sandbox commonly show placeholder app metadata on the payment sheet
  for an app that has never been released.
- **Missing App Store Connect metadata**: the age rating questionnaire not completed (the sheet then has no rating to show), no app icon
  in the uploaded build or App Store Connect record, or the subscription's localized display name and description missing.
Check in App Store Connect: App Information > Age Rating, the subscription's localization, and that the build carries the AppIcon asset.
If all three are complete, treat it as the sandbox artifact.

## 9. Remaining launch blockers

- Owner device Xcode build and Cmd-U of this branch (iOS is parse-checked only), then the sandbox checklist above.
- The parked decisions in section 4, especially the global breaker size for beta.
- `STORY_BILLING_MODE` is `off` everywhere; turning on observe/enforce is a separate approved rollout.
- App Store Connect metadata (section 8), the subscription review screenshot and submission.
- Account deletion (separate design in progress) must handle the subscription and the `b_sub_*` side record.
- Monitoring dashboards and alerts in section 5 are not built.
