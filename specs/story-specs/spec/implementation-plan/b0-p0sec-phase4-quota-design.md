# B0 / P0 Beta Security — Phase 4: AI Quota & Spending Protection (DESIGN)

Status: **IMPLEMENTED on branch `b0/beta-security-phase4` — NOT provisioned, NOT PR'd (per owner).** Reuses
existing UserUsage + Bedrock cost accounting. Out of scope: subscriptions, paid billing, free-tier product
pricing (req 14).

## 1. Reuse of existing mechanisms (req 10)

| Existing | Reuse in Phase 4 |
|---|---|
| **UserUsage table** `story-<env>-user-usage` (PK `story_user_id`, SK `quota_period` e.g. "2026-10"/"intro", PAY_PER_REQUEST, PITR, RETAIN) | The durable per-user allowance ledger. Phase 4 writes reservation + settlement items here. Distinct from the ephemeral Phase-3 rate-limit table. |
| **Bedrock cost accounting** (`packages/observability` `estimated_cost_usd`, worker EMF `estimated_cost_usd`, `last_max_tokens_used`) | The per-generation USD estimate that each settlement records against the user's monthly spend. |
| **Job idempotency** `job_id = UUIDv5(operation_id)` + lease fencing | The idempotency key for reserve/settle so a retried submit neither double-reserves nor double-charges. |
| **Phase-3 throttle** (rate, per minute) | Orthogonal: throttle limits REQUEST RATE; quota limits CUMULATIVE AI USAGE/COST per period. Both key on story_user_id. |

## 2. Atomic usage reservation + idempotent settlement (req 11)

Two-phase, reservation-first (never charge after the fact only):

1. **RESERVE (before inference).** On an AI submit/call, atomically reserve an estimated cost/unit against the
   user's period budget: a conditional `UpdateItem` on `(story_user_id, quota_period)` — `ADD reserved :est`
   with `ConditionExpression reserved + settled + :est <= :budget`. Fail → **402-style quota-denied** (we use
   429 or a dedicated quota error, see §6), BEFORE any Bedrock call, so an over-budget user never spends.
   The reservation carries a `reservation_id = UUIDv5(operation_id)` so a retry of the SAME operation finds
   its existing reservation and does NOT reserve again (idempotent, req 11). The per-reservation marker
   `res#<rid>` is a MAP `{state, usd, gens}` recording EXACTLY what was reserved, so settle/release reverse
   precisely that amount (the earlier `-0.0` stub that never drained `reserved_usd` is fixed).
2. **SETTLE (after inference).** When the real token usage/cost is known, atomically move the amount from
   `reserved` to `settled` with the ACTUAL `estimated_cost_usd`: `SET res#<rid>.state=settled ADD settled
   :actual, reserved :-est` conditioned on `res#<rid>.state = 'reserved'`. Settling twice is a no-op (the
   condition fails) — **idempotent settlement**.
3. **RELEASE on terminal failure.** If inference fails/cancels, release the reservation: refund the user
   ALLOWANCE (`gens`), remove the reserved estimate, but KEEP any incurred spend. A failed job does not
   consume allowance but still records real money (req 3/4). Tied to the job's terminal-state transition.

### 2a. DynamoDB transactions evaluation (req 2) — WHAT IS AND IS NOT ATOMIC

- **Per-user item (reserved_usd / settled_usd / gens_used / markers):** ALL on ONE item → a single
  conditional `UpdateItem` is already fully atomic. No transaction needed; concurrent retries of the same
  `operation_id` cannot double-count (idempotency marker) and a budget breach is the conditional's own failure.
- **Per-user + GLOBAL breaker:** these are TWO items (`story_user_id` row and the `__global__` row). The
  reserve applies BOTH deltas in ONE **`TransactWriteItems`** when the client supports it (the common case) —
  so the per-user reserve and the global-breaker increment commit together or not at all. This is genuine
  two-item atomicity for the reservation accounting.
- **UserUsage ↔ job store (TWO TABLES):** NOT claimed atomic. We do not wrap the quota reservation and the
  job-store `create_or_get` in a cross-table transaction. Instead the flow is: reserve (UserUsage) → create
  job (job store) → enqueue; every step is idempotent on the deterministic ids.
- **TransactWriteItems FALLBACK (no transact support / transient):** per-user reserve first (atomic), then a
  best-effort idempotent global add (`gres#<rid>` marker). **Failure window:** if the process dies between the
  per-user reserve and the global add, the global breaker UNDER-counts by one estimate until reconciled — it
  never OVER-counts, so it can only trip slightly LATE, never early. **Recovery invariant:** the reconcile
  sweep (req 12) re-derives the global reserved total from the per-user `res#` markers and corrects drift; a
  settle/release always moves the global marker symmetrically so steady-state global = Σ per-user.

### 2b. Failure windows & recovery invariants (req 4) — the honest ledger

| Window | Effect | Recovery |
|---|---|---|
| Crash after reserve, before inference | reservation `reserved`, no spend | reconcile sweep `release_allowance` (orphan) — refunds allowance, 0 incurred |
| Crash after inference, before settle | reservation `reserved`, real spend happened but UNrecorded | worker retry (SQS redelivery) re-runs settle idempotently; if the job is terminal-failed, release records incurred spend from diag tokens |
| Duplicate submit / SQS redelivery | — | `res#<rid>` + `slot#<job_id>` markers make reserve/slot EXACTLY ONCE |
| Double settle / double release | — | state guard (`res#<rid>.state`) makes the second a no-op |
| Global add lost (fallback path) | global under-counts by one estimate | reconcile re-derives global from per-user markers |

## 3. Active-job concurrency + crash recovery (req 12) — the deferred Phase-3 item

- **Active jobs = queued + running** (owner correction 6). A per-job marker `slot#<job_id>` on the user item
  gates an `active_jobs` counter: `ADD active_jobs :1 SET slot#<job_id>=held` conditioned
  `attribute_not_exists(slot#<job_id>) AND active_jobs + 1 <= :max`. Reserved at SUBMIT (job enters queued),
  released on TERMINAL (completed/failed/cancelled/expired). EXACTLY ONCE in each direction regardless of
  duplicate submit, SQS redelivery, retry, cancel, or worker crash (the marker's `held→released` state guard).
- **Terminal-state release:** the worker decrements `active_jobs` + refunds/settles on the job's terminal
  transition; a redelivery of a finished job finds the slot already `released` → no double-decrement.
- **Crash recovery (IMPLEMENTED):** `JobStore.sweep_quota_orphans()` runs on the existing EventBridge
  reconcile tick. It finds (a) jobs stuck non-terminal past `expires_at` (a worker that crashed mid-run) and
  finalizes them `failed(orphaned)`, and (b) terminal jobs not yet `quota_released`; it stamps
  `quota_released=1` conditionally (EXACTLY-ONCE) and the worker releases each one's reservation + slot
  (refund allowance, free slot, 0 incurred — a crashed attempt's cost is an accepted under-count). A crash
  cannot permanently leak a slot or a reservation. `active_jobs` can never go negative (release is conditional
  on `held`).

## 4. Configurable beta allowances + global safeguards (req 13)

All env-configurable, NOT product pricing (req 14) — operational beta guardrails:

| Control | Proposed beta default | Env |
|---|---|---|
| Per-user monthly AI spend cap | **$5 / user / month** (estimated USD) | `STORY_QUOTA_USER_MONTHLY_USD` |
| Per-user daily AI generations | **40 / day** | `STORY_QUOTA_USER_DAILY_GENS` |
| Max active AI jobs / user | **5** | `STORY_QUOTA_MAX_ACTIVE_JOBS` |
| **Global** monthly Bedrock spend cap (all users) | **$60 / month** (circuit breaker, PROPOSAL — below the $100 AWS Budget alert) | `STORY_QUOTA_GLOBAL_MONTHLY_USD` |

- **Global cost safeguard (req 5):** a global item (`PK="__global__"`) tracks month-to-date estimated spend;
  when `reserved + settled + est` would cross `STORY_QUOTA_GLOBAL_MONTHLY_USD`, new AI reservations are denied
  (circuit breaker) with `scope=global_monthly_usd` + a `QuotaDenied` metric. **Reconciled with the beta AWS
  Budget:** the beta account has a `yotale-beta-monthly $100` AWS Budget at 50/80/100% → alerts@yotale.ai.
  **AWS Budgets are ALERTS, not spending caps** — they notify, they do not stop spend. So the breaker is set
  BELOW the budget ($60 < $100) to trip (deny new inference) BEFORE the first budget *alert* escalates, giving
  a real stop where the budget only warns. It is a PROPOSAL, tuned from observed traffic, NOT an enforced
  spending guarantee (estimate-based; actual Bedrock spend is the billing truth).
- Thresholds are starting points for observation (like Phase 3), tuned from real beta data before enforcing.

## 4a. No-bypass coverage (req 7/8)

The quota gate takes its paid-entry-point set from the SAME `throttle.ROUTE_CLASS` the Phase-3 throttle uses —
exactly one route map, so it cannot drift. The EXPENSIVE classes `{ai_sync, music_provider, ai_job_submit}`
are the quota-gated set (`quota_gate.PAID_CLASSES`). A route-coverage test asserts
`PAID_CLASSES == {classes marked expensive}`, so a NEW customer paid endpoint added as an expensive class is
automatically gated and an attempt to leave one ungated fails CI. Coverage:
- **sync Bedrock inference** (`ai_sync`): quota middleware reserves before the handler, settles actual / releases after.
- **paid Epidemic music** (`music_provider`): same middleware path.
- **async AI submissions** (`ai_job_submit`): the submit handler reserves + takes a slot exactly once; the
  **worker** settles/releases on terminal — covering **worker retries** (SQS redelivery is idempotent).

## 5. Observation vs enforcement

Mirror Phase 3: `STORY_QUOTA_MODE=observe|enforce`. Observe emits `QuotaWouldDeny` + usage metrics without
rejecting; enforce denies over-budget. Default `observe` for the beta rollout.

## 6. Denial response + metrics

- Quota denial: a distinct **429** (or 402-style) with `{"error":"quota_exceeded","scope":"user_monthly|user_daily|active_jobs|global","retry_after_seconds":N}`. Distinct from a rate-limit 429 (`error:"rate_limited"`) so clients and logs can tell them apart.
- Low-cardinality metrics (reuse Observability EMF, `op_type` dim): `QuotaReserved`, `QuotaSettled`,
  `QuotaDenied`, `QuotaWouldDeny`, `QuotaReleased`, `GlobalQuotaTripped`, `QuotaStoreError`. NEVER dimensioned
  by story_user_id. Per-user spend is reconstructable from the existing per-generation cost LOG (not a metric
  dimension), consistent with the observability design.
- Store-failure policy (consistent with Phase 3 amendment 1): a UserUsage outage on an EXPENSIVE op fails
  CLOSED (503) — we must not run unbounded inference when we cannot account for it; safe ops unaffected.

## 7. CDK / IAM / cost (IMPLEMENTED)

- **No new table** — reuse the auth-stack `story-<env>-user-usage` (PK story_user_id, SK quota_period,
  PAY_PER_REQUEST, PITR, RETAIN). Reservations + the `__global__` aggregate are extra items/attributes on it.
- **IAM (least-privilege, cross-stack by name):** the API **instance role** (`UserQuotaReserve`) and the
  **worker role** (`UserQuotaSettle`) each get `dynamodb:GetItem + UpdateItem + TransactWriteItems` on the
  single `story-<env>-user-usage` ARN. **No PutItem** (the module never creates a bare item), **no wildcard**.
  Asserted by a CDK test.
- **Env:** App Runner + worker carry `STORY_USER_USAGE_TABLE`, `STORY_QUOTA_MODE` (default **observe**), and
  the configurable thresholds (`STORY_QUOTA_USER_MONTHLY_USD=5`, `_USER_DAILY_GENS=40`, `_MAX_ACTIVE_JOBS=5`,
  `_GLOBAL_MONTHLY_USD=60`). Per-op estimate overridable via `STORY_QUOTA_ESTIMATE_<CLASS>_USD`.
- **Reconcile:** the orphan-reservation sweep rides the existing EventBridge reconcile rule (no new infra).
- **Cost:** a couple of extra DynamoDB `UpdateItem`/`TransactWriteItems` per AI op + a few EMF metrics ≈
  **< $1/month** beyond Phase 3 (PAY_PER_REQUEST, TTL-free durable rows amortized over the month).

## 7a. Estimates (reserve-before, settle-after — req 8)

Per-class reserve-time estimate (actual settled afterward; actual MAY exceed estimate → financial truth wins):
`ai_sync` $0.05, `music_provider` $0.01, `ai_job_submit` $0.15 (async plan/critique/coverage is multi-call).
The worker settles the ACTUAL Bedrock cost from the engine's summed billable tokens (all attempts — retries,
repairs, critiques, fallback) via the existing `observability.price_lookup`.

## 8. Tests (WRITTEN — 29 green)

`packages/user_quota/tests/test_user_quota.py` (19) + `apps/api/tests/test_quota_gate.py` (10):
atomic concurrent reserve (once); concurrent DISTINCT users isolated; per-user monthly-USD + daily-gens
boundaries; GLOBAL breaker boundary across users; transaction atomic user+global; transaction-failure
idempotent recovery; observe never denies (user/global/slot); settle actual (exceeds estimate) + drains
reserved + idempotent; partial settlement (one of many); failed-inference refunds allowance keeps spend; no
double settle/release; slot reserve/release exactly-once under duplicate + worker-crash double-release; slot
cap enforced + concurrent; orphan-reservation releasable; store-error → QuotaStoreError (fail-closed caller);
fallback path reserves user+global; NO-BYPASS route coverage; worker settle/release idempotent; legacy/dev
job no-op; gate inert when unprovisioned. Full suites: **579 backend + 64 CDK green**.

## STOP — Phase 4 provisioning / enforcement

IMPLEMENTED on branch `b0/beta-security-phase4`; integration + crash-recovery complete, so the PR may open.
**Authoritative live `cdk diff story-beta-api`** (with `-c observability=true -c
alarmDestination=alerts@yotale.ai` + live digest `sha256:52273f67…` + the beta cognito ids) ran against
deployed beta and is **PURELY ADDITIVE, zero destroy/replace**: instance role `+UserQuotaReserve`, worker
role `+UserQuotaSettle` (Get/Update/Transact on `story-beta-user-usage`), worker `+STORY_QUOTA_MODE
+STORY_USER_USAGE_TABLE` env + code-asset hash, App Runner `+6` quota env vars; observability PRESERVED
(no teardown), no table/Cognito/OIDC/WAF/queue drift (one omitted change is a cosmetic em-dash, Value
identical). **NOTHING deployed.** `STORY_QUOTA_MODE` stays **observe** (observe does NOT enforce cost limits
— correction 9). No subscriptions, billing, or free-tier pricing. No enforcement until separately approved.
