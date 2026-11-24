# Proposal (READ-ONLY): Backend-Owned Asset Understanding

Status: DESIGN ONLY. Nothing here is implemented, deployed, or approved. Companion to `milestone-au-background-continuity-and-honest-progress.md`.

## 1. Why

On-device AU depends on iOS execution (even with continued processing, completion is best-effort). A durable server job would finish regardless of app state. Cost: video bytes must reach the server first.

## 2. Audit of the current system

- Request: `POST /v1/asset-understanding` carries 24 device-extracted JPEG frames (<= 12 MB, 1 MB each). The server never sees the video. Frames are ephemeral inference input, except the P1-F evidence pack (`evidence/{owner}/{cmid}/frames.pack` in the media bucket) written only when a `content_sha256` claim is supplied and the persist gate is on (dev + beta). Retention policy is unchanged by this proposal.
- Limits: throttle class `ai_sync` 20/min per user; process-wide admission semaphore of 4 on the API; quota gate (daily gens / monthly USD / global) returns 429 `quota_exceeded`.
- Cloud-restorable coverage: original media upload is the Auto Backup multipart pipeline (default OFF per account), private SSE-S3 bucket, account-scoped keys, verified sha256. Videos only; stills are not analyzed. Local-only Moments (Auto Backup off, or not yet uploaded) have nothing server-side to analyze.
- Existing worker: EditPlan SQS (`story-<env>-edit-plan-jobs`, visibility 960 s, DLQ maxReceive 2) + Lambda (900 s, 2 GB, unreserved concurrency on beta because the account limit is 10). It is tuned for one long planning job per request and shares Lambda concurrency with user-facing creation.

## 3. Design

1. Prerequisite: the Moment's original is in durable storage (verified upload). A pending-AU Moment that is not uploaded stays on-device AU (hybrid).
2. `POST /v1/au-jobs {moment_id, content_sha256}` creates an idempotent job keyed `(owner, moment_id, schema_version)`; authz = bearer principal owns the media record whose verified sha256 matches. Duplicate request returns the existing job.
3. Worker: reads the original from S3, extracts 24 frames server-side (needs ffmpeg in a Lambda layer or container; must reproduce `au_frames/1` exactly so results are comparable to device frames), calls the existing `AssetUnderstandingEngine`, writes the MomentUnderstanding to the account store (existing UnderstandingSync records) and the evidence pack under the existing retention rules.
4. iOS sync: the app already pulls understandings on foreground/reconcile; add `GET /v1/au-jobs?since=` (or reuse reconcile) so rows become MomentUnderstandingModel without local analysis. The local job is marked complete when a verified server result lands, which preserves the existing "never re-analyze a Moment that has a current understanding" rule.
5. Idempotency: one result per (owner, moment, schema); worker uses a conditional write; SQS redelivery is harmless. Quota: charged at job execution through the same quota gate; a spent allowance parks the job until reset exactly like the on-device path.

## 4. Workload isolation (do not reuse the EditPlan worker queue as-is)

AU bursts (19-30 jobs at once, ~15 s each) would compete with EditPlan jobs for the same Lambda pool, which has no reserved concurrency on beta. Use a **separate** queue + DLQ + Lambda function with its own reserved concurrency (e.g. 2-4, subject to account limit raised), batch size 1, visibility > worker timeout. Share the code package and `ModelGateway`, not the queue. Needs a workload-isolation review before any reuse decision.

## 5. Costs and risks

Model cost is unchanged per Moment (same engine). New: S3 reads (original download per job, ~20-200 MB per clip), Lambda compute for frame extraction (~seconds), SQS (negligible), ffmpeg packaging/maintenance, egress none. Risks: frame-extraction parity with iOS (AVFoundation vs ffmpeg timestamps), large downloads in Lambda, the 10-concurrency account limit, and the dependency on Auto Backup being enabled (privacy/consent: today users choose whether originals leave the device).

## 6. Recovery

SQS retries + DLQ (maxReceive 2); job table TTL; a stuck-job sweeper; iOS falls back to on-device AU if a job is not done in N hours and the app is open.

## 7. Smallest staged migration (hybrid is required)

1. Stage 0 (this branch): on-device AU with continued processing and honest status.
2. Stage 1: make backup-on-import default-eligible (consent decision, owner call), so originals reach S3 quickly.
3. Stage 2: job table + `POST /v1/au-jobs` + separate worker for cloud-backed videos only; iOS sync of results. Local-only Moments stay on-device.
4. Stage 3: stills, once product wants photo AU.
Hybrid is unavoidable as long as Auto Backup is optional.

## 8. Open questions for the owner

Consent model for automatic upload; ffmpeg vs a managed transcoder; whether a Lambda concurrency increase is available in the beta account; whether server-extracted frames may differ from `au_frames/1` device frames.
