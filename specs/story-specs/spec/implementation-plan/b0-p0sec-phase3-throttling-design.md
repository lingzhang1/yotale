# B0 / P0 Beta Security — Phase 3: Authenticated Per-User API Throttling (DESIGN)

Status: **DESIGN — awaiting approval before any AWS change or deploy.** Nothing provisioned.
Scope: per-user rate limiting ONLY. No subscriptions, no billing, no AI monthly quotas (Phase 4), no WAF Count→Block.

## 1. Audit of existing mechanisms (req 1)

| Mechanism | State | Reuse for Phase 3 |
|---|---|---|
| **Canonical identity** | `require_user`/`optional_user` → `Principal.story_user_id` (verified Cognito sub → immutable story_user_id, resolved ONCE at the central `auth_boundary` middleware, cached on `request.state.principal`). | The throttle key is `principal.story_user_id` — already server-derived, never client-supplied (req 9). |
| **UserUsage table** | `story-beta-user-usage`, PK `story_user_id`, SK `quota_period`, PAY_PER_REQUEST, PITR, RETAIN. Built for Phase 4 quotas. | Reuse the SAME table for rate windows with a distinct SK shape (`rl#<class>#<window-epoch>`), so no new table is strictly required — but see §8 for a dedicated-table option with TTL. |
| **Job idempotency** | `job_id = UUIDv5(operation_id)` — a duplicate submit maps to the SAME job; lease (`lease_until`) fences redelivery; payload-conflict → 409. | A retry/duplicate with the same `operation_id`/`mutation_id` must NOT consume a second token (req 6). |
| **Rate limiting today** | NONE (the only "throttle" code is Bedrock provider-throttle handling). | Net-new. |
| **API routing** | FastAPI, single central `auth_boundary` middleware already runs per request. | Add throttle as a dependency/second middleware AFTER auth, so it has the resolved principal and runs on every non-public route. |

## 2. Smallest atomic limiter keyed by story_user_id (req 2, 8)

**Fixed-window counter in DynamoDB, incremented atomically.** One `UpdateItem` with `ADD count :1` and a `ConditionExpression` that rejects when the post-increment would exceed the window limit — atomic and consistent across all App Runner instances (req 8), because DynamoDB is the single shared store. No per-process counters (explicitly disallowed).

- **Key:** PK `story_user_id`, SK `rl#<class>#<window_start_epoch>` where `<class>` is the throttle class (below) and `<window_start_epoch>` is the fixed window bucket (e.g. `floor(now/60)` for a per-minute window).
- **Increment:** `UpdateItem ADD count :1, SET ttl = :ttl` with `ConditionExpression attribute_not_exists(count) OR count < :limit`. On `ConditionalCheckFailed` → over limit → 429.
- **TTL:** each item sets a DynamoDB TTL a few windows out, so counters self-expire — the table never grows unbounded and costs stay near-zero.
- Fixed-window (not sliding/token-bucket) is deliberate: one conditional `UpdateItem` per request, simplest atomic primitive, good enough for abuse protection in a small beta. A burst at a window boundary is acceptable for beta; revisit if needed.

## 3. Throttle classes & coverage (req 3, 4)

Separate counters per class so an expensive-AI limit doesn't starve cheap reads:

| Class | Routes | Why |
|---|---|---|
| `ai_sync` | `/v1/creative-intent` (det., still gated), `/v1/story-guide`, `/v1/story-coverage(+v2)`, `/v1/scene-understanding`, `/v1/asset-understanding`, `/v1/director/*`, `/v1/duration-recommendation`, `/v1/music-plan`, `/v1/music-direction`, `/v1/interpret-revision`, `/v1/edit-plan(+mm)` | Expensive Bedrock calls — the primary cost-abuse surface. |
| `ai_job_submit` | `POST /v1/edit-plan-jobs`, `POST /v1/story-coverage/v2/jobs` | Async AI submissions; one check at submit (idempotent — see §4). |
| `writes` | `POST /v1/stories`, `PUT /v1/stories/{id}`, `PUT /v1/understanding`, `POST /v1/stories/{id}/outputs/backup`, `POST /v1/understanding/batch-get` | Story/media writes. |
| `presign` | `POST /v1/media/initiate`, `/v1/media/multipart/initiate`, `/v1/media/{id}/parts`, `/v1/media/{id}/complete`, `/v1/media/multipart/complete` | Presigned-URL issuance (the issuance is throttled; the actual S3 byte transfer is direct-to-S3 and NOT throttled — correct, large uploads unaffected). |
| `poll` | `GET /v1/edit-plan-jobs/{id}`, `GET /v1/story-coverage/v2/jobs/{id}`, `GET /v1/media`, `GET /v1/stories` | Excessive polling — a high but finite per-minute cap. |

**`/health` is public and OUTSIDE throttling** (req 4) — it's on the auth public allowlist, and the throttle dependency is skipped for allowlisted paths. Docs likewise.

## 4. Idempotency-safe accounting (req 6, 7)

- **Async job submit:** consume a token ONLY when the submit creates a NEW job. Because `job_id = UUIDv5(operation_id)`, a duplicate submit is detected (conditional create fails / same job returned) → on that path we SKIP the token consume. A genuine new submission consumes one. This preserves job ownership, lease fencing, and payload-conflict 409 semantics untouched (req 7) — the throttle wraps the handler, it does not change job logic.
- **Sync retries:** the limiter keys on the window only; a client retry of a failed sync call is a new request and does consume (sync has no idempotency key). Mitigation: generous `ai_sync` window so a couple of retries never trips a legitimate user; 429 carries `Retry-After` so clients back off rather than hammer.

## 5. 429 response (req 5)

On a throttle hit: HTTP **429** with a **`Retry-After`** header = seconds until the current window rolls over, body `{"error":"rate_limited","class":"<class>","retry_after_seconds":N}`. Consistent across all classes.

## 6. Fail-safe when the store is unavailable (req 12)

**Fail OPEN on limiter error.** If the DynamoDB `UpdateItem` throws (throttled, unavailable, timeout), the request is ALLOWED (not 500/429) and a `throttle_store_error` metric + WARNING log is emitted. Rationale: the limiter is an abuse-protection layer, not an auth gate — a limiter outage must never take down legitimate traffic or block a paying beta user. WAF (IP rate) + auth still protect the service. (Configurable: a `STORY_THROTTLE_FAIL_MODE=open|closed` env, default `open` for beta.)

## 7. No trust of client identity/IP (req 9)

Key is strictly `request.state.principal.story_user_id` (server-resolved from the verified JWT). No `X-Forwarded-For`, no client-supplied user id, no email. A legacy/unauthenticated principal (dev only) is not throttled per-user (there is no real user id); beta/prod never reach that path (fail-closed auth).

## 8. Metrics (req 10) + store choice

- **Low-cardinality metrics** via the existing Observability EMF path: `ThrottleAllowed` / `ThrottleBlocked` / `ThrottleStoreError`, dimensioned by `class` ONLY (5 classes) — NEVER by story_user_id (would explode cardinality). Wired to the existing Observability namespace; no new SNS/alarms created here (an alarm on `ThrottleBlocked` can be added to the existing Observability topic in a follow-up if desired).
- **Store:** reuse `story-beta-user-usage` (add the `ttl` attribute + enable TTL) OR a dedicated `story-beta-rate-limits` table. **Recommendation: a dedicated table** with TTL enabled — keeps the Phase-4 quota data (which must persist) cleanly separate from ephemeral rate-window counters (which self-expire), and lets the rate table be PAY_PER_REQUEST with aggressive TTL. Small, additive, its own gated CDK.

## 9. Proposed beta thresholds (req 11 — CONFIGURABLE, NOT FINAL, for review)

All per `story_user_id`, env-configurable (`STORY_THROTTLE_<CLASS>_PER_MIN`), fixed 60s window unless noted:

| Class | Proposed beta limit | Reasoning |
|---|---|---|
| `ai_sync` | **20 / min** | A real create flow fires several AI calls in bursts; 20/min absorbs a normal session, stops a script. |
| `ai_job_submit` | **10 / min**, and **5 concurrent active jobs** (a secondary check against active-job count) | Async jobs are the most expensive; keep it low. |
| `writes` | **60 / min** | Story/understanding writes are chatty during editing. |
| `presign` | **30 / min** | One per media item; a 20-clip Story bursts ~20. |
| `poll` | **120 / min** | Polling is frequent but cheap; high cap only stops pathological loops. |

These are starting points for the Count-like observation you prefer — recommend deploying with metrics first and tuning from real beta traffic before relying on them.

## 10. Cost estimate (req 14)

- **DynamoDB (dedicated rate table, PAY_PER_REQUEST):** one `UpdateItem` (1 WCU-equivalent) per throttled request. A small beta at, say, <100k requests/month ≈ <$0.15 writes + negligible storage (TTL keeps it tiny) + negligible reads. **< $1/month.**
- **CloudWatch:** 3 EMF metrics × 5 class dimensions = 15 custom metric streams ≈ 15 × $0.30 = **~$4.50/month** (or near-zero if folded into existing EMF with no new custom metrics). 
- **Total: ~$1–6/month.** Negligible.

## 11. Tests (req 13) — to be written with the implementation

- **Concurrency:** N parallel increments against one key → exactly `limit` allowed, rest 429 (atomic counter correctness).
- **Boundary:** request `#limit` allowed, `#limit+1` → 429; window rollover resets.
- **Account isolation:** user A's consumption never affects user B's counter (distinct PKs).
- **Retry/idempotency:** a duplicate `operation_id` job submit consumes no extra token.
- **Fail-open:** store-error path returns the handler result (not 429/500) + emits `ThrottleStoreError`.
- **Public bypass:** `/health` never throttled.

## 12. CDK / IAM / diff (to author on approval)

- Dedicated `story-beta-rate-limits` DynamoDB table (PAY_PER_REQUEST, PK `story_user_id`, SK `rl_key`, TTL on `ttl`), in the api stack behind the existing env parameterization.
- Instance-role grant: `dynamodb:UpdateItem/GetItem` scoped to that one table ARN (least privilege).
- Expected diff: +1 DynamoDB table, +1 IAM statement on the instance role. No change to App Runner config beyond the new env vars (thresholds), no change to auth/WAF/worker.

## STOP — Phase 3 architecture & provisioning approval

Awaiting owner review of: the fixed-window DynamoDB approach, the 5 throttle classes + routes, the proposed beta thresholds, fail-open default, dedicated-table choice, and the cost. On approval: author the limiter module + dependency + CDK table + tests, run the full suite, an authoritative beta diff, and STOP again before deploy.
