# Billing V1 / B2: Apple server integration

> **Billing V2 (2026-11-20):** YoTale Plus is now UNLIMITED ordinary use while active or in grace; there is no 12-video / 100-Moment Plus allowance any more. The Free starter (2 videos, 30 new Moments, trial clock) is unchanged. Where this document describes finite Plus allowances, renewals that reset Plus counters, or Plus credit copy, it is superseded by [billing-v2-unlimited-plus](./billing-v2-unlimited-plus.md).

Status: implemented and tested offline on branch `feat/billing-b2-apple-server`. Not merged, not deployed. No App Store Connect or AWS change made.

## Identifiers (public, not secrets)
| Item | Value |
|---|---|
| Bundle ID | `com.lingzhang.story` |
| Apple app ID | `6826007175` |
| Subscription group | `22593497` |
| Product ID | `com.lingzhang.story.plus.monthly` |
| Team ID | `5V43ARGFF2` |

## Endpoints
### `POST /v1/billing/transactions` (authenticated)
Body `{"signed_transaction": "<StoreKit 2 JWS>"}`. The server:
1. verifies the JWS (x5c chain to the pinned Apple roots, signature, bundle id, app id, environment);
2. requires `productId` = the Plus product and type = auto-renewable subscription;
3. requires `appAccountToken` = THIS account's token (`apple_app_account_token` from `GET /v1/billing/entitlement`; the app passes it as `.appAccountToken(...)` in `Product.purchase`). A missing or foreign token is refused;
4. binds the original transaction to this account (create-only; a second account gets 409 `transaction_bound_elsewhere`);
5. grants Plus from Apple's signed purchase and expiry dates. Plan names, prices, credits, expiry in the request body are ignored.

An expired or revoked transaction never writes (result `not_active`), so replaying an old receipt cannot downgrade or upgrade. Errors: 422 `invalid_signed_data`, `wrong_environment`, `product_not_allowed`, `missing_app_account_token`; 403 `app_account_token_mismatch`; 409 `transaction_bound_elsewhere`; 503 `apple_not_configured` / `billing_unavailable`.

### `POST /v1/billing/apple-notifications` (public, signature only)
Body `{"signedPayload": "<JWS>"}` (App Store Server Notifications V2). It is on the auth boundary's public allowlist as the exact (POST, path) pair `auth.PUBLIC_ROUTES`; nothing else is public. Trust is the Apple signature. A bad signature gets 422. A store failure gets 503 so Apple retries. Duplicates are journalled by `notificationUUID` and acknowledged without effect.

| Notification | Effect |
|---|---|
| SUBSCRIBED, DID_RENEW, OFFER_REDEEMED, RENEWAL_EXTENDED, REFUND_REVERSED | `plus_active`; a new transaction id is a new billing period and resets the allowances at Apple's boundary |
| DID_FAIL_TO_RENEW + GRACE_PERIOD | `plus_grace` until Apple's grace expiry |
| DID_FAIL_TO_RENEW (no grace), EXPIRED, GRACE_PERIOD_EXPIRED, REFUND, REVOKE | `plus_expired` |
| DID_CHANGE_RENEWAL_STATUS/PREF, PRICE_INCREASE, REFUND_DECLINED, TEST, CONSUMPTION_REQUEST, others | recorded only |

Unattributable events (no bound account and no known token) are acknowledged as `unmatched`; the app's own `POST /transactions` or reconciliation converges them.

## Ordering and replay guards (ledger conditional writes)
* Event time: an event signed earlier than the last applied one is ignored.
* Period order: for a Plus account, a state whose period ends BEFORE the stored period is ignored, even with a fresher signature. A replayed old transaction cannot reset the allowances. A refund of last month's charge does not revoke this month's period.
* Grandfathered and admin-granted accounts are never changed by store events.

## Environments
`STORY_ENVIRONMENT` development or beta accepts only Apple **Sandbox** (TestFlight). gamma or production accepts only **Production**. Data for the other environment is refused as `wrong_environment`. Owner decision pending: App Review exercises purchases in Sandbox against the production server; accepting that in production would let any sandbox account obtain Plus for free, so it is OFF by default.

## Independence from `STORY_BILLING_MODE`
The Apple endpoints work in off, observe and enforce, always against the LIVE ledger. They change only plan state; the meters (credit and Moment allowances) stay gated by the mode. This is how a sandbox purchase can be tested on beta while billing stays `off`.

## Data written (all in the existing `story-<env>-user-usage` table)
| pk | sk | content |
|---|---|---|
| `__apple_txn__` | `billing#txn#<original_txn>` | owning account (one account per transaction) |
| `__apple_token__` | `billing#token#<appAccountToken>` | owning account (reverse index for early notifications) |
| `__apple_evt__` | `billing#evt#<notificationUUID>` | type and outcome only |

Never stored or logged: the signed JWS, prices, storefront, the Apple private key.

## Reconciliation
`scripts/yotale_billing_apple_reconcile.py` (dry run by default) reads one account's current status from the App Store Server API, verifies the signatures and applies it through the same guarded path. It needs the API key from Secrets Manager (`YoTale-Apple-Key`: `key_id`, `issuer_id`, `private_key`). It runs from the owner's machine, so the API service needs no Secrets Manager permission. A scheduled sweep is not built; it needs a scan permission and an approved schedule.

## Infrastructure review (no CDK change needed)
* **IAM:** the API role already has `GetItem`, `UpdateItem` and `TransactWriteItems` on the usage table. The Apple path uses `GetItem` and `UpdateItem` only. No new permission, no Secrets Manager grant.
* **Config:** `STORY_ENVIRONMENT` and `STORY_USER_USAGE_TABLE` already exist. No new variable, no new flag.
* **WAF:** the beta Web ACL has no rule that blocks a signed JSON POST (IP reputation and known-bad-inputs block; the Common Rule Set is Count; the per-IP rate rule is 600 per 5 minutes). Apple's traffic is a few requests per event, so no exemption is added. If a sandbox test shows Apple blocked, add a narrow rule scoped to the exact path, never a blanket bypass.
* **Dependency:** `app-store-server-library==3.1.2` in `apps/api/pyproject.toml`, the API Dockerfile and CI. The worker does not need it.

## App Store Connect configuration the owner must do
1. Sandbox Server URL (beta): `https://asxtxgjiis.us-east-1.awsapprunner.com/v1/billing/apple-notifications`, after the B2 deploy.
2. Production Server URL stays empty until a production backend exists.
3. Create sandbox testers; the TestFlight build buys with a sandbox Apple ID.
4. Copy the `YoTale-Apple-Key` secret into the beta account for the reconcile script.
5. Billing Grace Period on, Family Sharing off, no introductory offer.

## Tests
* `packages/billing/tests/test_apple.py`: policy (ownership, binding, mapping, ordering, idempotency, concurrency, reconciliation), run on the in-memory double and on DynamoDB Local.
* `packages/billing/tests/test_apple_verifier.py`: the REAL Apple library against a minted chain: valid data passes; untrusted root, tampered body, alg none, garbage, wrong bundle, wrong environment, and a leaf without Apple's marker are all rejected; the bundled Apple roots are pinned by SHA-256.
* `apps/api/tests/test_billing_apple_api.py`: HTTP routes with the real verifier.
* `apps/api/tests/test_central_auth_boundary.py`: the public allowlist is exactly the one webhook route.

## Not proven offline
Apple's real signatures (the library is Apple's, the chain here is a test chain), real sandbox purchases and notifications, and Apple's retry behavior. These need the deploy and a TestFlight sandbox purchase.
