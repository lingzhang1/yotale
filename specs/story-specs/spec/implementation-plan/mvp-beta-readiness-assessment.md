# MVP Release Candidate Stabilization & Beta Readiness — Assessment

**Status:** ASSESSMENT + ARCHITECTURE PROPOSAL (Phases 0–5). No code changed; no infrastructure
provisioned; no authentication contract changed; nothing deployed or pushed. STOP at owner architecture
approval.
**Date:** 2026-10-18
**Owner decision on entry:** Camera Metadata milestone CLOSED. Camera Package B, camera metadata, Capture
Anywhere, and core AI editing are feature-complete for current MVP scope. No new camera/creative-editing
milestone. Next objective = prepare Story for a controlled external beta.
**Method:** code-grounded audit via 3 parallel read-only tracks (roadmap status, beta security,
latency/cost/reliability) + git/deploy state. Classifications are taken from each milestone row's OWN
status text — a feature is NOT assumed accepted merely because code was committed.

---

## Phase 0 — Roadmap status

Counts: ~15 DEVICE-ACCEPTED, ~30 IMPLEMENTED-BUT-UNVERIFIED, 7 KNOWN ISSUES, ~10 DEFERRED/design-gate.
The index uses no "required-for-beta" label; that class is synthesized in Phase 5.

**Device-accepted (core MVP path proven on device):** Capture Anywhere + UX corrections; AI-Ideas
persistence; Camera Package B; Camera Metadata Part A; Story Director (C3); C3.5 Figma UX; Story Guide
(E2-a/E2-c); Media Engine V1 / Case G render (R-b); Consumer Create→Result (R-c); Music integration
(R-d); Edit Planner v5 (frozen dev default); Customize UX + sound preference; Unified NL Interpretation
(headline pass).

**Known issues (class c) — release-relevant:**
- Async Story Coverage / "Guide no longer marks done" (120s App Runner wall severs the response) — in progress.
- P0 renderer "segment 0 speed 4.0 out of range [0.5–2.0]" crash — fix implemented, device-gate.
- P0 "recover completed AI jobs" (completed plan never fetched → silent no-version) — fix implemented, device-gate.
- P0 "shorten each clip re-picks all clips" — fix deployed to dev, device-gate.
- R-d.1 15s short-finale; native-audio disappearance (guitar); C4 Shot Validation blocked (Bedrock AccessDenied for account).

**Git / deploy state (concrete):**
- Feature branch `fix/p0-recover-jobs-explore-latency` (1 ahead). **`master` is 227 commits ahead of its
  upstream — the entire product history is unpushed.**
- Undeployed / dev-only backend: Async Edit Planning **prod rollout ON HOLD** (needs prod account id +
  deploy authorization + git-push decision); `prompts/edit_plan/5.3-cand/` not wired live; MusicAnalysis
  production planner "deploy-ready," not deployed.
- Unrelated uncommitted working-tree changes (pbxproj/scheme/UITests) intentionally left untouched.

## Phase 1 — End-to-end regression (status, NOT executed)

The 12 cases are device + dev-backend flows; they cannot run in the build sandbox (SwiftData `@Model`
macro blocked; render/export is device-only). Derived readiness from Phase 0:
- Cases 1–3, 10 (capture→library, AI ideas, create-from-moments, change music) rest on device-accepted
  milestones — expected green, confirm on device.
- Cases 6–9, 11 (storytelling/visual-first create, another-version, NL revise, restart recovery) sit on
  class-c P0 fixes still at device-gate — these REQUIRE a device pass before beta.
- Run on Girl-with-Dress, Hiking, and real captured footage. This doc records the gate checklist, not a pass.

## Phase 2 — Latency / reliability / cost

| Metric | Measured today? | Recorded number |
|---|---|---|
| Planning model-calls / generation | ✅ `worker_plan_diag` CloudWatch | 1 clean · 3 compound revise · 4 w/ 1 repair |
| Repair (bounded) | ✅ per-job | cap 2 attempts (worker), +35–45s each |
| Worker wall time | sample (not p50/p95) | 36–46s clean → 76s / 172s with extra sequential calls |
| Throttle / fallback | ✅ implemented + audited | 152 Bedrock throttles/2h, ALL on Opus, 0 on Sonnet; Opus→Sonnet fallback exists |
| Tap-to-playable (e2e) | ❌ not stitched (per-endpoint `latency_ms` only) | device-only |
| Queue wait | ❌ no timestamp field | 2 worker slots (reservedConcurrency=2, batchSize=1) |
| On-device render/export | ❌ zero instrumentation in MediaEngineV1 | "seconds" (prose only) |
| Model cost / generation | ❌ never computed; tokens captured in-engine but not even logged out | AU ~21k input tok/call proxy only |

Flags: 172s long-tail = extra sequential model calls (compound revise + repair), not a mystery; duplicate
inference is guarded by payload-fingerprint idempotency. Biggest gaps: no per-generation cost accounting,
no queue-wait metric, no device render timing.

## Phase 3 — Beta security audit (THE blocker)

| Area | Status |
|---|---|
| Authentication / identity | **ABSENT** — `FastAPI()` has no auth, no middleware, no CORS; `owner` is `Form(default="dev", "NOT trusted as identity")` |
| Job authorization / ownership | **ABSENT (capability-only)** — job fetch/cancel authorize on `job_id` alone, no owner check; gated only by a global env flag `STORY_JOBS_API_ENABLED` |
| job_id unguessability | **Weak** — `uuid5(hardcoded_ns, predictable operation_id)`, not a random token; code itself says "UUIDv5 secrecy is NOT authentication" |
| Per-user quotas / rate limits / concurrency | **ABSENT** — one user can exhaust the shared Bedrock daily quota for everyone |
| Per-user cost accounting | **ABSENT** |
| Contact-sheet retention | **PARTIAL** — staged to S3, SSE-AES256, deleted on terminal + 24h TTL; never source video |
| Data deletion / privacy | **PARTIAL** — staging TTL exists; no user-facing delete endpoint; Story state in-memory (lost on restart) |
| Crash / error monitoring | **ABSENT** — no Sentry / OpenTelemetry / Datadog |

**Decisive finding (exactly the owner's concern):** the async job endpoints rely on an unguessable-but-
deterministic job_id with NO authenticated ownership. In a public beta, anyone who holds or derives a
`job_id` can read another user's plan/coverage and cancel their job. The design was deliberately
local-first ("MVP has NO server database; ownership is LOCAL-FIRST on device") — acceptable for a private
build, not for public exposure. **Do not treat the unguessable job id as a substitute for authenticated
ownership.**

## Phase 4 — Minimum beta architecture (proposal, smallest viable)

1. **Identity:** Sign in with Apple (+ optional email OTP). Issue a short-lived app JWT; backend trusts
   the verified `sub` as principal. No account-management platform.
2. **Auth middleware:** one FastAPI dependency validating the JWT on every `/v1/*`; add CORS. Replace the
   untrusted `owner` form field with the token principal.
3. **Ownership:** persist `owner_sub` on each job at create; fetch/cancel assert `job.owner_sub ==
   principal` → 403 otherwise. (Closes the Phase-3 blocker.)
4. **Per-user quota + accounting:** small DynamoDB `usage(user, day) → {generations, input_tok,
   output_tok}`; enforce a daily generation cap; surface the already-captured engine tokens into the job
   record for cost math.
5. **Rate / concurrency:** per-user in-flight cap (reuse the existing single-flight) + a simple
   token-bucket; raise worker reservedConcurrency only with the cap in place.
6. **Idempotency:** already present (payload-fingerprint) — keep; key by `(owner_sub, operation_id)`.
7. **Admin / beta access:** an allowlist table of Apple `sub`s; reject non-allowlisted principals — this
   is the beta gate.
8. **Monitoring + privacy:** Sentry (or CloudWatch alarms on `any_fallback`/5xx/throttle count) + a
   user-facing delete endpoint.

Deferred (not needed for a controlled beta): billing/subscriptions, full profile management,
social/multi-device sync, SSE-KMS upgrade.

## Phase 5 — Release decision

**Release-blocking before external beta (ordered):**
1. Auth + per-job ownership + CORS (Phase-3 blocker) — ~3–4 days.
2. Beta allowlist + per-user quota/rate-limit + usage accounting — ~2–3 days.
3. Deploy the on-hold backend (prod account + push `master`) + device-regression the 7 class-c P0 fixes
   on Girl-with-Dress / Hiking / real footage — ~2–3 days incl. device run.
4. Monitoring + delete endpoint — ~1 day.

**Total minimum beta infra ≈ 8–11 engineering days**, auth first (everything else depends on a trusted
principal).

**Recommended order:** identity + middleware → ownership checks → allowlist → quota/accounting →
deploy + device regression → monitoring/delete.

**Deferred features:** billing, account management, and the remaining class-b creative-editing
experiments (v5.2/v5.3, multimodal A1, editorial modes) — none beta-blocking; freeze at current dev
defaults.

## Decision gate

STOP at owner architecture approval before provisioning new persistent infrastructure or changing
authentication contracts. No public deploy; no unrelated changes.
