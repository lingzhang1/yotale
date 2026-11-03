# Quota Ledger — Phantom-429 Fix & Beta Cleanup Runbook

Status: **CODE FIX OFFLINE-COMPLETE on `fix/p0-quota-ledger-bounded`. NO live beta mutation performed or
authorized. This runbook is PREPARED, not executed.**

## 1. What was wrong (proven)
A beta Create returned HTTP 429 `quota_ai_job_submit` while the owner's ledger showed `active_jobs=0` and no
cap breached (global $8.88<$60, monthly $8.88<$50, daily 50<500). Root cause: `_is_conditional_failure()`
classified ANY `TransactionCanceledException` as a conditional (cap) failure, so a transient
`TransactionConflict` on the shared `__global__` item — or a validation/throughput error — was mapped to a
false `QuotaDenied`. NOT item-size (items are 57–64 KB, well under the 400 KB limit). Separately, released/
settled markers were never removed, so monthly items grow unbounded.

## 2. The code fix (this branch)
- Classify `TransactionCanceledException` by its `CancellationReasons`: genuine-conditional only if every leg
  is `ConditionalCheckFailed`/`None`; `TransactionConflict`/throughput → transient (retry); validation/size/
  other → `QuotaStoreError` → **503**, never a false 429.
- `reserve()` retries transient conflicts (same idempotent keys); exhaustion → `QuotaStoreError`.
- `reserve_conditional_recover()` raises `global_monthly_usd` only when the global spend ACTUALLY exceeds the
  cap; otherwise `QuotaStoreError` (no phantom global denial).
- `submit_reserve()` now RESERVES only when the job was newly `created` (the durable job row is the dedup
  authority) — so terminal-marker pruning can never cause a double reserve.
- `prune_terminal_markers()` removes only terminal `res#`/`gres#` (settled|released) and `slot#` (released),
  each conditionally guarded; never touches reserved/held markers or aggregates. Wired into the worker
  terminal path (`worker_settle`/`worker_release`) per-user — no extra global-item write, no cross-user scan.
- `_log_quota_store_error()` logs the raw exception + `CancellationReasons` (privacy-safe) so the exact cause
  is captured going forward.

## 3. Beta cleanup — PREPARED, requires separate approval; DO NOT run in this task
The code fix alone resolves the phantom 429 (misclassification). Cleanup is **optional** (items are below the
size limit) and would only reduce accumulated bookkeeping.

### Exact scope (owner account only; do NOT touch other users' `__global__` reservations)
Items (`story-beta-user-usage`, account 224033508028, us-east-1):
| PK | SK | terminal markers to prune | active markers to KEEP | aggregates (unchanged) |
|---|---|---|---|---|
| `61310227-0e51-4755-8f2d-5f1ac9f7a103` | `2026-10` | ~387 `res#` (settled/released) | any `reserved` | `settled_usd`, `gens#*` |
| `61310227-…` | `2026-11` | ~342 `res#` + 26 `slot#` (released) | any `reserved`/`held` | `settled_usd`, `gens#*`, `active_jobs=0` |
| `__global__` | `2026-10` | ~459 `gres#` (settled/released) | any `reserved` (**may belong to other users**) | `settled_usd` |
| `__global__` | `2026-11` | ~342 `gres#` (settled/released) | any `reserved` (**other users**) | `settled_usd` |

> ⚠️ The `__global__` items are SHARED across all users. Prune only `gres#` markers whose state is
> settled/released; NEVER remove a `reserved` gres# (it may be another user's in-flight reservation).

### Procedure (when approved)
1. **Snapshot** each of the 4 items to a file (read `get_item`, save JSON) for manual restore.
2. For each item, run `UserQuota.prune_terminal_markers(pk, period)` (the shipped, conditionally-guarded
   method) — or an equivalent guarded `REMOVE` per marker with `ConditionExpression: #m.#st = <terminal>`.
3. Bounded batches (≤100/call); repeat until it returns 0.
4. **Verify after:** item byte size dropped; `reserved_usd`/`settled_usd`/`gens#*`/`active_jobs` IDENTICAL to
   the snapshot; no `reserved`/`held` marker removed; a test Create succeeds.

### Concurrency precaution
Run during low traffic. The guarded REMOVE no-ops if a marker's state changed under it (a concurrent re-use),
so a race cannot corrupt an active reservation.

### Rollback / recovery
Restore any item from its pre-cleanup JSON snapshot via `put_item`. PITR exists on the table but is NOT an
instant item-level undo — the snapshot file is the primary recovery path.

## 4. Verification that the fix works (no cleanup needed to unblock)
Once the code deploys to beta, a Create submit that hits a transient conflict will **retry and succeed**, and a
genuine store failure returns a 503 "try again" — never a false "you already have videos being created".
The `quota_store_error` log line will record the exact `CancellationReasons` if it recurs.

## 5. Known limitations / open risks
- The exact historical `CancellationReasons` for the original 18:52 event were not logged (now captured going
  forward); the fix is correct for all three failure classes regardless.
- The shared `__global__` item is a contention hotspot that grows with traffic. Offline conflict tests pass
  with bounded retry, but **production TPS capacity is NOT established by mocked tests.** If beta traffic shows
  sustained global-item conflict, a follow-up (e.g. sharded global counters) is the mitigation — a separate,
  approval-gated change, not done here.
