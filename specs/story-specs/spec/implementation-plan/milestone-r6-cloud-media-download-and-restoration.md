# R6 — Cloud Media Download & Restoration

Status: 🟡 design done, implementing. Owner-ordered after R4-B (closed, device-accepted); R4-C deferred.
Scope: **iOS-only** (the backend download endpoint already exists). Separate acceptance gate — STOP at R6
device acceptance before R5.

App repo `/Users/lingzhang/Workplace/story`. All iOS work is on branch `feat/r1-account-ownership-isolation`
(the `backend/*` branches carry NO iOS tree — confirm `git branch --show-current` before every iOS edit).

---

## Phase 0 — Audit findings

### The smallest shared media-resolution seam
Every consumer that needs the **original bytes** resolves a Moment the same way: take `asset.relativePath`,
ask `MediaStore.shared.fileExists(relativePath:)`, then `MediaStore.shared.absoluteURL(for:)`.

- **Rendering** — `MomentResolver.resolve(moments:)` (`Media/Render/RenderSupport.swift`) is the single choke
  point; it *skips* any Moment whose file is missing and feeds `urlResolver(for:)`, which the Media Engine uses
  to turn `EditSegmentV2.assetId` → local URL. A missing local file today = the Moment silently drops.
- **Playback** — `StoryResultView` (`.playable(relativePath:)`), `MomentThumbnailCache`.
- **Editing / creation / revision** — `StoryCreationCoordinator.momentsPayload` resolves source URLs via
  `MediaStore` from the Moment's `relativePath`.

**Seam = `MediaStore` (relative→absolute + existence).** It is **synchronous**. R6 adds an async
`MediaResolver.ensureLocal(...)` that a caller `await`s *before* the existing sync path; once it returns, the
file is guaranteed present+verified on disk and the unchanged sync path resolves it normally. One async gate,
inserted ahead of the one seam, covers playback + editing + rendering (req #8).

### Cloud identity & checksum sources (already present — no model migration)
- `MomentModel.cloudMediaId: String?`, `cloudStateRaw` (`"local_only"` default), `isLocalOnly`,
  `ownerAccountId`. `cloudMediaId` is set when an upload verifies (R4 `MediaUploadQueue.finalize`).
- `AssetModel.relativePath`, `ownerAccountId`. (No cloud fields on the asset — identity lives on the Moment +
  the upload job.)
- `MediaUploadJobModel` (per account, immutable owner): `cloudMediaId`, `contentSha256` (full-file sha256 hex),
  `sizeBytes`, `ownerAccountId`, `state`. This is where R6 reads the **expected size + full-file SHA256** to
  verify a download (req #3). For a Moment uploaded on THIS device the job row is local; its `contentSha256`
  is the trusted expectation.

### Backend (already deployed — R6 needs no new endpoint)
- `GET /v1/media/{cloud_media_id}/download` → `presign_download(owner=principal.story_user_id, …)`:
  short-lived presigned GET, **account-scoped** (404 if not the caller's), **verified-only** (409 before
  `cloud_verified`). Enforces canonical ownership server-side (req #10).
- `presign_download` uses the unsigned-payload SigV4 client (R4-B fix), so a streamed GET to disk works.
- `GET /v1/media` lists the caller's own records incl. `source_moment_id` (reverse link cloud→Moment, used by
  the recovery scan). No client-supplied key or owner ever reaches S3.

### File & checksum utilities
- `MediaStore.adoptCapturedFile` = the atomic-move primitive to reuse for atomic install (req #4).
- iOS upload path already computes a **streamed** full-file sha256 (`MediaUploadService.makeMultipartPlan` /
  `fileSha256Hex`) — the same streaming hasher is reused for download verification, so no large video is ever
  held in memory (req #2, #3).
- `RenderOutputStore` shows the established relative-path-under-Documents pattern R6 mirrors for any temp
  download dir.

---

## Design

### New types (iOS)
1. **`MediaDownloadService`** (`Media/Download/MediaDownloadService.swift`) — protocol seam + concrete impl
   (mirrors `MediaUploadService`). Responsibilities:
   - `presignedDownloadURL(accessToken:cloudMediaId:)` → calls `GET /v1/media/{id}/download` with explicit
     token (owner isolation; A's download never runs under B's token — req #10).
   - `download(from:to:expectedSize:expectedSha256:progress:)` — **streams** the presigned GET to a temp file
     via `URLSession` bytes/stream (never into memory — req #2), hashing as it writes; verifies size + full-file
     SHA256 (req #3); refuses a thumbnail/preview substitution (only the `/download` original is ever installed —
     req #9).
2. **`MediaDownloadJobModel`** (`@Model`, persistent — req #7) — one row per `(ownerAccountId, cloudMediaId)`:
   `state` (pending|running|verified|failed), `expectedSha256`, `expectedSize`, `targetRelativePath`,
   `attempts`, `claimGeneration`, `updatedAt`. `@Attribute(.unique)` composite guards **duplicate concurrent
   downloads** (req #5); an in-process actor coalesces concurrent `ensureLocal` callers onto one task.
3. **`MediaResolver`** (`Media/Download/MediaResolver.swift`) — the async gate:
   `ensureLocal(moment:auth:) async throws -> URL`.
   - If `MediaStore.fileExists(asset.relativePath)` → return the local URL immediately (fast path, no network).
   - Else if `moment.cloudMediaId != nil` and `moment.ownerAccountId == auth.storyUserId` (canonical owner —
     req #10): presign → stream-download to a temp path → verify size+sha → **atomically install** into
     `asset.relativePath` via a move (req #4), refreshing the presigned URL once on 403/expiry (req #6).
   - Else → throw `.unavailable` (cloud-only but not this account's, or no cloud copy). Callers surface this,
     never silently drop (req #9/#12 honesty).
   - Preserves `asset.relativePath`, durations, source ranges, speed, native-audio, and version lineage —
     R6 only fills bytes back into the SAME relative path, touching no edit/lineage fields (req #11).

### Wiring the seam
- `MomentResolver.resolve(moments:)` gains an async sibling `resolveEnsuringLocal(moments:auth:)` that awaits
  `MediaResolver.ensureLocal` for each cloud-only Moment, then delegates to the existing sync `resolve`.
  Rendering/editing call the async sibling first; the synchronous `resolve` stays for already-local callers
  and tests.
- Playback (`StoryResultView`) awaits `ensureLocal` in its `.task` before constructing the `AVPlayer`.
- **Originals are never deleted in R6** (req #12) — eviction is R5.

### Crash-safety & relaunch (req #7)
- Download writes to a temp file under `Documents/downloads/` (relative-path persisted on the job row). On
  relaunch, a partial temp is discarded and restarted (R6 does whole-file retry on resume; byte-range resume is
  an R-later optional — multipart *upload* resume ≠ download resume, kept honest). Install is the atomic move,
  so a crash leaves either the old state or the fully-verified file, never a half-written original.

### Account isolation (req #10)
- Owner is read from `moment.ownerAccountId` (immutable binding) and the presign call uses the ACTIVE account's
  token; the backend scopes to `principal.story_user_id`. A Moment whose `ownerAccountId != activeAccount`
  throws `.unavailable` and never attempts a download. No cross-account bytes.

---

## Requirements traceability
1 presigned GET ✓ · 2 stream-to-disk ✓ · 3 size+full-file-sha verify ✓ · 4 atomic install ✓ ·
5 de-dupe concurrent (unique row + coalescing actor) ✓ · 6 refresh expired URL ✓ · 7 persistent job +
relaunch ✓ · 8 resolve before playback/edit/render (one seam) ✓ · 9 never substitute a preview ✓ ·
10 canonical ownership (immutable owner + token) ✓ · 11 preserve ranges/speed/audio/lineage (bytes-only
install) ✓ · 12 no original deletion ✓.

## Explicit exclusions (this milestone)
R4-C background uploads · permanent cloud deletion · local eviction (R5) · metadata sync (R7) · billing ·
production · CI/CD · frozen-contract changes.

## Acceptance (device)
Real cloud-backed video on iPhone; simulate cloud-only non-destructively (clear the local file, keep the
Moment + `cloudMediaId`). Verify: playback, Story creation, revision, rendering, downloaded-file checksum ==
upload checksum, interrupted-download recovery on relaunch, cross-account isolation. Measure download latency
(by size) + bytes written. STOP at R6 device acceptance.
