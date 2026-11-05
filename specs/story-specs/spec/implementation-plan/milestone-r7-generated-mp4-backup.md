# R7-D — Generated MP4 Backup & Cross-Device Restoration

Status: 🟢 IMPLEMENTED (iOS + backend), backend DEPLOYED + live-verified (dev), automated-test/parse verified.
AWAITING two-device physical acceptance (Device A render+backup → Device B restore-on-play, 0 re-render).

App repo `/Users/lingzhang/Workplace/story`, branch `feat/r1-account-ownership-isolation`
(the `backend/*` branches carry NO iOS tree — confirm `git branch --show-current` before every iOS edit).

Builds directly on the R2–R6 account-owned media infrastructure. R7-D wires a GENERATED (rendered) MP4 into
the SAME cloud-backup + restore pipeline the originals use — there is deliberately NO second uploader and NO
second downloader. A backed-up output is RESTORED on another device for playback/sharing, NEVER re-planned or
re-rendered.

---

## Foundations reused (status audit, pre-existing)

- `GeneratedOutputModel.cloudMediaId` + `cloudVerifiedAt` — additive, defaulted nil (R7 Gate A / R7-D models).
- `GeneratedOutputModel.relativeFilePath` (RenderOutputStore path) + `editPlanJSON` (exact validated plan).
- `StoryDocCodec` already emits per-output `cloud_media_id`/`cloud_verified` (nil until R7-D backs it up) and
  per-output `edit_plan_json` in the `story_doc/2` derived block — identity, version lineage, soundtrack
  (`soundtrackTitle`/`musicAssetRef`/`soundtrackRole`/`nativeAudioPriority`) and the EXACT `editPlanJSON`
  already travel in the doc, so restoration preserves them (safeguard #5).
- R4 `MediaUploadService` / `MediaUploadQueue` multipart pipeline (single-PUT ≤16 MiB, true S3 multipart above,
  part-level resume, whole-file + per-part sha256, account-scoped tokens).
- R6 `MediaDownloadService` (presign → stream → verify size + full-file sha256 → caller atomic install) and
  `MediaDownloadJobModel` (persistent, unique `owner#cloudMediaId`, survives relaunch).

---

## Backend (DEPLOYED)

The smallest additive change the Gate-A audit called for: a `media_kind` tag + a `source_output_id` provenance
field. Storage key, presign, upload and verification are IDENTICAL for a moment original and a generated video
— only provenance differs.

- `packages/media_store/__init__.py`:
  - `MEDIA_KIND_MOMENT` / `MEDIA_KIND_GENERATED` constants + `_normalize_media_kind` (unknown/blank → moment).
  - `initiate_upload` / `initiate_multipart` accept `media_kind` + `source_output_id`, stored on the record.
  - `_decode` defaults `media_kind`="moment" + `source_output_id`="" for pre-R7-D records (back-compat).
- `apps/api/app/main.py`:
  - `MediaInitiateRequest` / `MediaMultipartInitiateRequest` accept `media_kind` + `source_output_id`
    (defaulted); both endpoints thread them into the store.
  - `/v1/media/{id}` status and `/v1/media` list responses carry `media_kind` + `source_output_id` so Device B
    can tell a generated record from a moment record during restore/reconcile.
  - The existing `POST /v1/stories/{story_id}/outputs/{output_id}/backup` endpoint is REUSED unchanged — it is
    media-kind agnostic (verifies the asset is THIS account's AND cloud_verified; C3: a cloud_media_id is never
    authorization).
- No new env vars, no DynamoDB table change (schemaless — the new attributes land on the existing
  `story-development-media` table).

Deploy: `git archive`-equivalent working-tree zip (root `buildspec.yml` using `$ECR_URI`, `prompts/`, `packages/`,
`apps/api/`) → `s3://story-codebuild-src-989088054552-us-east-1/rb-caseg/source.zip` → CodeBuild
`story-rb-caseg-build` (SUCCEEDED) → App Runner `story-development-api` update-service (full-replace env
preserved) + forced `start-deployment`. Live-verified: `/openapi.json` shows `media_kind` + `source_output_id`
on both media request schemas; `/health` ok. (A live authenticated functional probe needs a Cognito token the
sandbox can't mint; round-trip is covered by the backend test suite with real RS256 tokens + fake store.)

## iOS

- `MediaUploadService` — `MediaUploading` protocol extended with `mediaKind` + `sourceOutputId` + `contentType`
  on `initiate` / `initiateMultipart` (and a `contentType` on `putToS3`/`putPart`). A protocol extension keeps
  the exact R4 moment call shape (default moment/quicktime) so existing callers + fakes are source-compatible.
  `CloudMediaKind.moment` / `.generated` constants mirror the backend.
- `GeneratedOutputBackupJobModel` (new @Model, registered in the schema) — persistent, per
  `(ownerAccountId, outputId)`, no Moment-reservation logic (a rendered output is owned by its Story's owner,
  there is no shared local-only claim to arbitrate).
- `GeneratedOutputBackupQueue` (`Media/Upload/`) — the output-scoped sibling of `MediaUploadQueue`. Enroll
  (idempotent, account-scoped, skips an already-verified output, refuses another account's output), drain
  (active-account only, token for THIS owner), upload via the R4 pipeline with `media_kind="generated"` +
  `source_output_id`, and on server cloud_verified STAMP `output.cloudMediaId` + `cloudVerifiedAt` (guarded by
  owner-match + current `claimGeneration`). The rendered MP4 is NEVER deleted by the queue (safeguard #8).
  Launch/foreground orphan recovery + bounded backoff.
- `RenderOutputStore` (`Media/Render/MediaEngineV1.swift`) — restore helpers: `newDownloadTempURL`,
  `purgeDownloadTemps` (launch), `newRelativePath` (Device B mint), `installDownloadedOutput` (atomic install).
- `GeneratedOutputResolver` (`Media/Download/`) — the restore-on-play gate, sibling of `MediaResolver`. Fast
  path if local (no network); else requires a VERIFIED `cloudMediaId` owned by the active account, then REUSES
  the R6 `MediaDownloadService` (verify size + full-file sha256 before install), installs atomically into the
  RenderOutputStore, and stamps `relativeFilePath` + cloud ref onto the output. Coalesces concurrent callers.
  NEVER re-renders.
- `StoryCreationCoordinator.persist(...)` — on render completion, fire-and-forget
  `GeneratedOutputBackupQueue.sharedAutoEnroll(output)` (a no-op unless Auto Backup is ON).
- `StoryApp` — builds the backup queue (`makeOutputBackupQueue`), sets the auto-enroll hook, recovers +
  drains on sign-in and foreground, purges rendered-download temps at launch.
- `StoryResultView` — `ResultPlayback` gains a `.restorable` case (local MP4 absent BUT a verified cloud backup
  exists). The view shows a "Restoring your video…" state, auto-attempts the restore (then a manual Restore
  button on failure), and on success re-resolves to `.playable` — no re-render. `.missing` remains ONLY when
  there is neither a local file NOR a verified cloud backup.

## Invariants honored

1. One pipeline — generated backup/restore reuse R4/R6; no second uploader/downloader (audit answer).
2. Verified before trust — upload marks `cloud_verified` only after server size + sha256 check; restore installs
   only after size + full-file sha256 match (verify before playback/sharing).
3. Preserve identity/lineage/soundtrack/exact EditPlan — carried by `story_doc/2`; restore touches bytes only.
4. Never re-render to restore — restore is a download; the resolver has no planning/render path.
5. Account isolation — immutable owner binding, THIS owner's token only, cross-account backup/restore refused.
6. Pending recovery — persistent job rows + orphan recovery on launch/sign-in/foreground (upload AND download).
7. Never delete the only local copy before cloud verification — the backup queue never deletes the MP4; the
   restore installer only replaces an absent/old file with a verified one.

## Tests

- Backend `apps/api/tests/test_media_api.py` (+9 R7-D): generated single + multipart initiate record
  `media_kind`/`source_output_id`; default is moment; generated appears in list; verify + download roundtrip
  returns server-authoritative size + sha; cross-account generated download denied; unknown kind normalizes;
  backup endpoint registers a verified generated output and refuses an unverified one. Full media suite 30 green;
  `apps/api` suite 346 green.
- iOS `GeneratedOutputBackupQueueTests` (enroll idempotency/refusals, generated-kind initiate, verified
  stamping, account-scoped scheduling, failure backoff, orphan recovery, MP4 never deleted),
  `GeneratedOutputResolverTests` (download+verify+install+stamp, checksum/size mismatch no-install,
  cross-account refusal, no-cloud-copy, fast path, expired-URL refresh, concurrent coalesce),
  `StoryResultFlowTests` (+5 restorable vs missing vs playable). Parse-clean (device Xcode is the authoritative
  compile gate; the sandbox blocks the SwiftData macro plugin).

## Explicitly out of scope (owner)

Add-new-Moment-during-revise (deferred P1); production deploy; billing/free-tier; CloudWatch; CI/CD redesign;
permanent cloud deletion; any frozen-contract change (only the additive `media_kind`/`source_output_id`).

STOP at R7-D device acceptance.
