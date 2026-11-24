# Async Edit Planning — SHARED CONTRACT (build against this; do not diverge)

All three workstreams (CDK infra / backend job API + worker / iOS client) depend ONLY on this contract.
Owner-approved 2026-10-13. Dev only. No push, no public deploy.

## Resource names (CDK owns; backend + worker reference by env)
- DynamoDB table:  `story-{env}-edit-plan-jobs`   (PK: `job_id` S).  TTL attr: `expires_at` (epoch s).
- SQS queue:       `story-{env}-edit-plan-jobs`     + DLQ `story-{env}-edit-plan-jobs-dlq` (maxReceiveCount 2).
- S3 staging:      `story-{env}-edit-plan-staging-{account}-{region}`  (private, SSE, lifecycle expire 24h).
- Lambda worker:   `story-{env}-edit-plan-worker`   (timeout 900s; reserved concurrency 5).
- Env wired into App Runner + Lambda: STORY_JOBS_TABLE, STORY_JOBS_QUEUE_URL, STORY_STAGING_BUCKET.

## Job states (DynamoDB `status`)
queued -> running -> completed | failed
queued|running + cancel_requested -> cancelled
any non-terminal past expires_at -> expired (TTL + reconcile)
Terminal: completed, failed, cancelled, expired. Transitions are CONDITIONAL writes (no backward moves).

## DynamoDB item schema
job_id (S, uuid)              operation_id (S, idempotency key — SAME op recovers SAME job)
owner (S)                     status (S)
created_at (N, epoch s)       updated_at (N)
expires_at (N, TTL)           attempt_count (N)
lease_until (N, worker exec lease; a redelivery past lease may re-run)
approach (S: storytelling|visual_first)   critique_requested (BOOL)
request_ref (M: {staging_prefix, sheet_order, has_body})   # body JSON stored in staging too (can be large)
failure_category (S, nullable: material_infeasible|planning_defect|provider_exhausted|invalid_after_repair|internal)
failure_detail (S, nullable, <=400)
plan (M, nullable: the validated EditPlan/2 contract JSON when completed)
diagnostics (M, nullable: planning_mode, sheet_count, critique_applied, model_calls, used_fallback)

## HTTP API (App Runner; new)
POST /v1/edit-plan-jobs    (multipart, SAME parts as /v1/edit-plan-mm + operation_id + owner)
  parts: operation_id(form,required), owner(form,required), body(form JSON), sheet_order(form JSON),
         creative_brief(form?), critique_revision(form bool?), approach(form), sheets[](files?)
  -> 202 {job_id, status:"queued"}      (idempotent: same operation_id returns the EXISTING job_id)
  App Runner work: validate+size-check sheets -> write them + body to S3 staging prefix -> conditional-put
     job (attribute_not_exists(operation_id) via a GSI OR a deterministic job_id = hash(operation_id)) ->
     enqueue SQS {job_id}. Returns FAST (<5s), no model call.
GET  /v1/edit-plan-jobs/{job_id}   -> {job_id,status,approach,failure_category?,failure_detail?,
                                        plan? (only when completed), diagnostics?}
POST /v1/edit-plan-jobs/{job_id}/cancel -> {status:"cancel_requested"|terminal}  (conditional)

## Idempotency + reliability
- job_id = deterministic UUIDv5(operation_id) so a duplicate POST maps to the SAME item (no dup job, no dup
  inference). "Create Another Version" => NEW operation_id => new job.
- Lost-enqueue recovery: a job stuck `queued` with no SQS progress past RECONCILE_AFTER (e.g. 60s) is re-enqueued
  by a reconcile sweep (EventBridge-scheduled Lambda tick OR worker self-heal). Minimal: a periodic reconcile.
- SQS at-least-once: worker takes a LEASE (conditional set lease_until); a redelivery while lease is live and
  status=running is dropped; after lease expiry a re-run is allowed (idempotent — overwrites result). We do
  NOT claim exactly-once inference; we claim no DUPLICATE completed-plan churn and bounded re-execution.
- Daily-token exhaustion: worker does NOT retry it as transient -> fail fast with failure_category=provider_exhausted
  (Opus->Sonnet fallback still applies first via the existing gateway).

## Worker (Lambda) — reuses the EXACT backend core
- Reads job -> loads body+sheets from S3 staging -> builds EditPlanInputs (images, creative_brief,
  image_moment_order, critique_revision) -> calls the SAME _execute_edit_plan / engine.generate path
  (frozen v5.2, EditPlan/2 validator, Opus->Sonnet fallback, bounded critique). Execution deadline 840s
  (< Lambda 900s).
- On success: conditional-put status=completed + plan + diagnostics, DELETE staging prefix.
- On terminal failure: status=failed + category/detail, DELETE staging prefix.
- Always deletes staged sheets on terminal (privacy); S3 lifecycle 24h is the backstop; a scheduled sweep
  deletes abandoned prefixes whose job is terminal/expired.

## Privacy / retention (the approved departure from ephemeral-only)
- ONLY derived JPEG contact sheets + the request body JSON are staged — NEVER original video.
- Private bucket, SSE (SSE-S3 or KMS), no public URLs, scoped IAM (App Runner put; worker get+delete only on
  the staging prefix). No image bytes in any log. Explicit delete on terminal + 24h lifecycle backstop + sweep.
- Retention: minutes in the normal case (deleted at job completion); 24h hard cap via lifecycle.

## iOS
- One creation path: submit job -> persist job_id (+ operation_id) locally -> poll GET with bounded backoff ->
  on completed, fetch plan -> render on-device (unchanged MediaEngineV1). Recover after restart via stored
  job_id. Try-Again reuses the SAME operation_id (no dup inference) unless it's a new version.
- Honest progress stages from status (queued/running/…); never show a raw 502 as a creative failure.

## CORRECTNESS AMENDMENTS (2026-10-13, before provisioning — smallest necessary changes)

1. **Ownership is NOT a client string.** The client-supplied `owner` is advisory only and MUST NOT be trusted
   as identity. Dev gate: App Runner derives the caller identity from the request context it already trusts
   (there is no end-user auth in dev yet), stores it as `owner`, and GET/cancel are scoped to the stored owner.
   The job_id is a UUIDv5 of operation_id — NOT guessable from a sequence — so it also acts as a capability
   token for status reads in dev. A client cannot read/cancel another job by guessing. (A real auth principal
   replaces this when auth lands; out of scope here.)

2. **Idempotency detects CONFLICTING payloads.** The same operation_id with a DIFFERENT request is a client
   bug, not a legitimate retry. On submit we compute `payload_fingerprint` = sha256(body JSON + sheet_order +
   critique flag + approach) and store it on create. A second submit with the same operation_id but a
   DIFFERENT fingerprint is REFUSED with 409 (conflict) rather than silently returning the old job. Same
   fingerprint -> idempotent recovery (200/202 with the existing job_id).

3. **Lease prevents duplicate active execution AND stale result publication.** claim_lease already blocks a
   second active runner. ADDITIONALLY, complete()/fail() are now conditional on BOTH status=running AND the
   SAME lease token the worker claimed: a stale worker whose lease expired (and whose job was re-claimed by a
   fresh worker) can no longer publish a result over the newer run. lease_token = uuid4 set at claim.

4. **Cancellation reaches terminal + cleans staging.** cancel on `queued` -> worker sees cancel_requested at
   lease time and goes straight to `cancelled` (no model call); cancel on `running` -> worker checks
   is_cancel_requested at each boundary (before critique, before result publish) and finalizes `cancelled`.
   BOTH terminal cancellations delete the staging prefix. If the worker already finished, cancel is a no-op
   on the completed job (returns terminal status).

5. **TTL is NOT immediate deletion.** DynamoDB TTL deletes within ~48h, not at the instant expires_at passes.
   So a job past expires_at that is still present is treated as `expired` by READS (GET returns status=expired
   when now > expires_at regardless of the stored status), and the reconcile sweep finalizes it. We never rely
   on the row being gone. Staging has its OWN 24h S3 lifecycle independent of the job row.

6. **Lost-enqueue reconciliation does NOT cause uncontrolled dup model calls.** The reconcile sweep re-enqueues
   ONLY jobs that are status=`queued` AND older than RECONCILE_AFTER (60s) AND have attempt_count=0 (never
   leased). Once a worker claims the lease (attempt_count>=1, status=running), reconcile ignores it. Re-enqueue
   is bounded: a job re-enqueued MAX 2 times then -> failed(category=enqueue_lost) to the DLQ path. SQS
   at-least-once can still deliver a message twice, but the lease (concern 3) makes the SECOND delivery a no-op,
   so redelivery never doubles inference. We explicitly do NOT claim exactly-once model invocation; we claim
   bounded, de-duplicated execution.
