# YoTale — Cloud-First Ownership, Local-First Capture & Media Storage Architecture Review

Status: **DIRECTION ACCEPTED by owner (specs `9509b90`), with the 8 corrections in §0.0 applied. R1 is approved
for implementation; all cloud provisioning/implementation remains behind the STOP gate.**
Date: 2026-10-20 (corrections applied same day)
Scope: iOS app (`apps/ios`), backend (`apps/api`), infra (`infrastructure/cdk`), specs.
Trigger bug: two beta testers signed into the same iPhone and **shared every Story and Moment**.

This review supersedes the prior "cloud media as post-MVP" framing. Cloud media storage is now a **core beta
requirement**. No code was changed and no AWS resource was created in producing this document (STOP gate).

---

## 0.0 Owner corrections applied (2026-10-20)

The owner accepted the overall direction and issued 8 corrections. Each is folded into the sections noted; the
original design text below is retained and amended rather than rewritten.

1. **Shared device-local Moments until cloud ownership begins** — a local-only Moment is **not ownerless**: it
   belongs to the **device-local library**, is visible to **every** account on that iPhone, is captured without
   login, and is **never auto-claimed** by the first account to sign in. Ownership begins only on verified cloud
   upload. (Amends §1, §3, §7; the account-switch table in Decision 1.C is authoritative: local-only = visible
   to A **and** B; cloud-owned/Story = visible only to its owner.)
2. **Account-owned Moments after verified upload** — unchanged from §1.2 (`cloud_verified` → account-scoped,
   hidden from other accounts, no transfer/re-upload on switch). Enforced server-side.
3. **Account-owned Stories from creation** — Stories are **always** account-owned: a persistent Story is created
   **only** after authentication and is stamped with the server-verified `story_user_id` at creation. No Story
   record is persisted pre-auth; client-supplied owner is never trusted for authorization. (Amends §7, Phase 4.)
4. **Simplified development-only migration** — NO migration-pending state, adoption UI, or framework. A one-time,
   **dev-only, idempotent, non-destructive** backfill assigns all pre-R1 Stories (and their GeneratedOutputs,
   edit plans, creative direction, links, music, pending records — i.e. Story-derived state) to the account
   resolved from `dearlingzhang@gmail.com` via the trusted backend identity mapping (**never** the email as the
   owner id). Local-only Moments are **left shared** (not assigned). Never overwrite an explicit owner; never in
   prod/public-beta. (Replaces §8's general back-fill with this designated-account rule.)
5. **Essential creative metadata sync for beta** (corrects §5.1, which proposed media+ownership+links only) —
   beta must also sync: stable Story identity, title/description, Moment references + ordering, creative
   direction, edit plans, generated-version metadata + lineage, music selection, and relevant job/recovery
   refs. Recomputable AI caches (coverage/guide/music-plan/duration) **may stay local** initially. **Rendered
   video backup policy (§5.3):** rendered outputs are **NOT** backed up during beta — a recovered Story restores
   its project state + original media and is **re-rendered on demand**; this is documented as a known limitation
   and metadata-only restore is never called "complete recovery".
6. **Strong cloud checksum verification** (hardens §2.1/§2.3) — a multipart S3 **ETag is NOT a full-file
   SHA256** and must never be treated as one. `cloud_verified` requires: object exists ∧ expected size ∧
   **verifiable full-file checksum (e.g. S3 `ChecksumSHA256` / composable part checksums, validated against the
   device-computed sha256)** ∧ object under the caller's own prefix ∧ ownership record durably persisted. An
   upload response alone never authorizes eviction.
7. **Reference-safe media deletion** (adds to §2/§5) — distinguish three operations: (a) remove a Moment from a
   Story (link only), (b) remove a Moment from the Moments Library, (c) permanently delete the cloud original.
   A cloud original is **never** permanently deleted while another Story depends on it without an explicit
   dependency-resolution policy.
8. **Cloud media storage is a core external-beta requirement** — affirmed; already reflected throughout.

**Scope lock:** the immediate implementation is **R1 — Account Ownership & Local Isolation** only. No cloud
infra, upload, eviction, download, or sync is implemented in R1. Frozen editing contracts unchanged.

---

## 0. Executive summary

The shared-content bug is **not** a UI filtering oversight that a predicate fixes. It is the direct symptom of
a deeper architectural fact:

> **Nothing in the app — local or cloud — has an owner.** Stories, Moments, Assets, GeneratedOutputs and every
> derived record carry **no `owner_id`**. The only account linkage that exists is a single device-global
> `LocalIdentityModel.accountId` stamp, which is written once on first sign-in and **never consulted on any
> read**. The two home-screen queries (`@Query private var stories`, `@Query private var moments`) have **no
> predicate**, so they return every row on the device regardless of which account is signed in.

So account B sees account A's content because the data was never partitioned by account in the first place, and
the backend — which *does* have a correct `story_user_id` identity seam — is never asked to store or enforce
ownership of Moments/Stories (only edit-plan **jobs** flow through it, and even those are not owner-scoped in
the job store today).

Fixing this correctly is the same work as building cloud-backed Moments, because both require the one thing
missing: a durable, server-authoritative ownership record keyed by `story_user_id`. This review designs that
record, the local↔cloud media lifecycle on top of it, and a roadmap that lands **account isolation + minimum
cloud backup** before external beta.

**The 12 deliverables requested are indexed in §15.**

---

## Phase 0 — Current architecture audit (what exists today)

### 0.1 SwiftData models (`apps/ios/.../Data/Persistence/Models.swift`)

| Model | Owner field? | Notes |
|---|---|---|
| `StoryModel` | **none** | `@Attribute(.unique) id: UUID`. Owns `momentLinks`, `generatedOutputs` by cascade. |
| `MomentModel` | **none** | Owns its `AssetModel` by cascade. Global: referenced by many Stories via `StoryMomentLink`. |
| `AssetModel` | **none** | `relativePath` under `Documents/media/<uuid>.mov`. The ORIGINAL. No cloud ref, no owner. |
| `StoryMomentLink` | **none** | Join row (story,moment,orderIndex). |
| `GeneratedOutputModel` | **none** | `relativeFilePath` under `rendered/`. Full version lineage lives here. |
| `LocalIdentityModel` | `accountId: String?` | **The only account field in the whole store.** One row per device. Written once by the adoption hook; **never read on any fetch.** |
| `MomentUnderstandingModel`, `AssetUnderstandingJobModel`, `StoryCoverageModel`, `StoryGuideModel`, `StoryMusicDirectionModel`, `MusicPlanCacheModel`, `DurationRecCacheModel` | **none** | All keyed by `storyId`/`momentId` only. |
| `MyMusicAssetModel` | **none** | User-imported audio under `Documents/mymusic/`. |
| `PendingOperationModel` | **none** | Durable in-flight AI operation, keyed by `storyId`. |

### 0.2 The ownership gap, exactly

- **Adoption hook** (`StoryApp.swift`): on first sign-in, `onFirstSignInAdopt` stamps `LocalIdentityModel.accountId`
  if it is `nil`. If it already belongs to a different account it **refuses to reassign** — correct intent, but
  there is no per-entity owner to enforce, so it only protects the device-global stamp, not the data.
- **Reads** (`HomeView.swift`, `StoryRepository.fetchStories()`, `allMoments()`): **no predicate**. Every row,
  every account.
- **Sign-out** (`AuthStore.signOut()`): clears tokens only; by design does not touch SwiftData. So after B signs
  out and A signs in, A sees everything B created (and vice versa).
- **Net effect**: the local store is a single shared pool. Account switching is cosmetic.

### 0.3 Media lifecycle today (local-only, no cloud)

- Capture → `ContinuousCaptureModel` → `MediaStore.adoptCapturedFile(tempURL:)` copies into
  `Documents/media/<uuid>.mov` and stores the **relative** path on `AssetModel`.
- Rendered outputs → `RenderOutputStore` under `Documents/rendered/`.
- My Music → `Documents/mymusic/`.
- **Originals never leave the device.** There is no upload, no cloud copy, no eviction, no download-on-demand.
  Spec 03 explicitly says "the captured original never goes to the cloud" — that is the premise this review
  reverses.
- SwiftData never stores bytes or absolute paths (good — the relative-path discipline is already correct and is
  the seam we extend with a cloud reference).

### 0.4 Backend identity seam (`apps/api/app/auth.py`) — the one correct part

- `require_user` / `optional_user` verify a Cognito **access** token (RS256, issuer, expiry, `token_use`,
  `client_id`) and resolve `cognito_sub → story_user_id` via an **atomic** conditional write on the
  `story-<env>-identity-claims` + `story-<env>-users` DynamoDB tables (race-safe first sign-in, no email merge).
- Dev runs **optional-auth** (`STORY_REQUIRE_AUTH=0`): missing token → legacy `"dev"` principal; present token
  must be valid. Production fails closed.
- **`story_user_id` is immutable, server-minted, and never client-supplied.** This is the identity we will hang
  all media/Story ownership off. It already exists and is trustworthy.

### 0.5 Existing AWS infra (`infrastructure/cdk`)

- **`story-auth-stack`**: `story-<env>-identity-claims` (PK `claim_key`), `story-<env>-users` (PK `story_user_id`,
  carries `account_status`, `beta_access_status`). Cognito pool.
- **`story-api-stack`**: App Runner service (`story-<env>-api`), `story-<env>-edit-plan-jobs` DynamoDB (PK
  `job_id`, TTL), SQS + DLQ, **`story-<env>-edit-plan-staging-<acct>-<region>` S3** — private, SSE-S3,
  `BLOCK_ALL` public access, `enforceSSL`, 24h lifecycle, **derived contact-sheet JPEGs + request JSON only,
  never source video**. Worker Lambda (15 min) for async edit planning.
- **Patterns we can reuse directly**: private-SSE-block-all S3 bucket; PAY_PER_REQUEST DynamoDB with TTL;
  UUIDv5 idempotency keys; conditional-write ownership claims; App Runner instance-role scoping; the existing
  job-store state machine (`submitted→planning→…`) is a good template for the upload state machine.
- **Gap**: the edit-plan job store is **not owner-scoped** (PK is `job_id` only). Owner scoping there is a
  small, separate hardening item (§11 risk) but out of this review's media scope.

### 0.6 Minimum changes identified (detail in later phases)

1. Add an **owner identity** to every top-level local model (`ownerAccountId: String?`) + migrate existing rows
   to the adopting account; filter all reads by the active owner (+ `nil` anonymous).
2. Add a **cloud media reference + upload-state** to `AssetModel` and a server-authoritative **media-ownership
   record** (DynamoDB) + **private per-account S3 prefix**.
3. Add an **async upload pipeline** (presigned multipart, verify, then allow eviction) that never blocks capture.
4. Add **download-on-demand + local optimization** with a hard safety invariant.
5. Keep all **frozen editing contracts** (EditPlan/2, music_plan/1, moment_understanding/1, story_coverage/2,
   story_guide/1) byte-identical — media resolution happens *before* the planner, so no contract changes.

---

## Phase 1 — Media identity & ownership model

### 1.1 Five distinct identities (never conflated)

| Identity | Lives | Stable key | Meaning |
|---|---|---|---|
| **Local Moment** | SwiftData `MomentModel.id` (UUID) | device-local | the user's editorial unit on this device |
| **Original media asset** | SwiftData `AssetModel.id` + `relativePath` | device-local | the full-resolution file on disk |
| **Cloud media copy** | DynamoDB media record + S3 object | server | the durable, account-owned backup of the original |
| **Story account** | `story_user_id` | server (immutable) | the authenticated owner |
| **Story↔Moment reference** | `StoryMomentLink` | device-local (mirrored to cloud metadata) | ordering/inclusion |

Key rule: the **cloud media id is distinct from the local asset id**. One logical original has: a device
`AssetModel.id`, and a `cloud_media_id` (server-minted UUIDv5 over `(story_user_id, content_sha256)` for
idempotency). This lets the same device asset be re-referenced after reinstall without duplicating cloud bytes.

### 1.2 Ownership state machine (per Asset's cloud lifecycle)

```
local_only ──upload──▶ uploading ──verify──▶ cloud_verified ──optimize──▶ local_optimized
                          │                        │                           │
                          │                        └──────────── download ─────┘ (downloaded_on_demand)
                          ▼
                       (interrupted / cancelled / failed / retrying) ──resume──▶ uploading
```

Full state set, with the invariant each guarantees:

| State | Local original? | Cloud original? | Invariant |
|---|---|---|---|
| `local_only` | ✅ present | ❌ none | The only copy is local. **Never evictable.** |
| `uploading` | ✅ present | partial | Upload in flight (multipart). Never evictable. |
| `upload_interrupted` | ✅ present | partial | App suspended/network lost mid-upload. Resumable from last part. Not evictable. |
| `upload_failed` | ✅ present | none/partial | Terminal failure after bounded retries; surfaced to user. Not evictable. |
| `cloud_verified` | ✅ present | ✅ verified (ETag/sha match) | Both copies valid. **Now eligible** for optimization. |
| `local_optimized` | ❌ evicted (preview only) | ✅ verified | Local original removed; preview + metadata + `cloud_media_id` remain. |
| `downloaded_on_demand` | ✅ restored | ✅ verified | Original re-fetched for edit/export; may be re-evicted later. |
| `upload_cancelled` | ✅ present | none | User cancelled; stays local_only semantics. |

- **Idempotent transitions**: keyed by `cloud_media_id` + content sha256. A retried upload reuses the same
  multipart upload id where possible; a re-verify is a no-op if already verified.
- **Account switching never transfers or duplicates cloud ownership**: ownership is decided server-side by
  `story_user_id`; a device-local asset owned by account A is simply **not visible** to account B and is never
  re-uploaded under B. (This is the fix for the trigger bug — see §7.)

### 1.3 Model additions (additive, SwiftData-lightweight-migration-safe)

All new fields optional/defaulted so existing on-device stores decode cleanly (matches the file's 60+ prior
additive fields; a heavy migration cannot run in the sandbox).

- `StoryModel`: `ownerAccountId: String?` (nil = anonymous/local-only).
- `MomentModel`: `ownerAccountId: String?`.
- `AssetModel`: `ownerAccountId: String?`, `cloudMediaId: String?`, `cloudStateRaw: String = "local_only"`,
  `contentSha256: String?`, `uploadId: String?` (multipart resume), `previewRelativePath: String?`,
  `keepDownloaded: Bool = false`, `lastVerifiedAt: Date?`, `cloudBytes: Int?`.
- `GeneratedOutputModel`: `ownerAccountId: String?` (+ optional later cloud backup — see roadmap "Public release").
- Every derived record (`StoryCoverageModel` etc.) inherits ownership **transitively** through its `storyId`;
  it is filtered by resolving the Story's owner, not by duplicating the field (keeps the frozen caches clean).

### 1.4 Stable IDs / idempotency summary

- `cloud_media_id = uuidv5(story_user_id + content_sha256)` → re-upload/reinstall never duplicates bytes.
- Upload multipart `uploadId` persisted → resume, not restart.
- Story/Moment cloud metadata keyed by their existing device UUIDs (already unique) + `owner`.

---

## Phase 2 — AWS media storage architecture (smallest secure)

Reuse the existing private-bucket + DynamoDB + App Runner patterns. **No large video ever transits App Runner.**

### 2.1 Components

1. **Private S3 media bucket** `story-<env>-media-<acct>-<region>`
   - `BlockPublicAccess.BLOCK_ALL`, `enforceSSL`, SSE (S3-managed for dev; SSE-KMS as a public-release hardening).
   - **Account-scoped keys**: `media/{story_user_id}/{cloud_media_id}/original.mov` and `.../preview.jpg`.
   - Lifecycle: originals **retained** (this is a backup, not staging — unlike the 24h edit-plan bucket).
     Incomplete-multipart-upload abort rule at 7 days (cost hygiene).
2. **DynamoDB media-ownership table** `story-<env>-media` (PK `story_user_id`, SK `cloud_media_id`)
   - Attributes: `content_sha256`, `s3_key`, `bytes`, `duration_s`, `state`, `etag`, `created_at`,
     `verified_at`, `device_asset_id`, `source_moment_id`. **Server is the authority on ownership.**
   - GSI optional later for cross-device listing by `story_user_id` (PK already serves this — Query by PK).
3. **App Runner endpoints** (small JSON only; presign, never proxy bytes):
   - `POST /v1/media/upload/initiate` → returns `cloud_media_id` + presigned **multipart** part URLs (or a
     single presigned PUT for small files) + `upload_id`. Writes the media record in `state=uploading`.
   - `POST /v1/media/upload/complete` → server calls S3 `CompleteMultipartUpload`, verifies the object
     (HeadObject ETag/size, optionally sha256 via checksum), flips record to `cloud_verified`. **This is the
     only thing that authorizes local eviction.**
   - `POST /v1/media/download/url` → presigned **GET** (short TTL) for one `cloud_media_id`, owner-checked.
   - `GET /v1/media` → list the caller's media records (recovery / cross-device).
   - `DELETE /v1/media/{cloud_media_id}` → owner-checked delete (S3 + record) for explicit media deletion.
   - All depend on `require_user` (prod) / `optional_user` (dev), and **every handler filters by the caller's
     `story_user_id`** — a presigned URL is only ever minted for an object under the caller's own prefix.
4. **Integrity**: S3 `ChecksumSHA256` on part uploads + a `HeadObject` size/ETag check at complete. The device
   computes `content_sha256` before upload and the server records it; verify = (object exists ∧ size matches ∧
   checksum matches). Only then `cloud_verified`.

### 2.2 Why presigned + direct-to-S3 (not through App Runner)

- App Runner request/response size + timeout make it unsuitable for multi-hundred-MB video; presigned multipart
  puts the bytes device→S3 directly, App Runner only mints URLs and records state. Matches the owner constraint
  "do not route large video uploads through App Runner".

### 2.3 Access control

- IAM: App Runner instance role gets `s3:PutObject/GetObject/AbortMultipartUpload/ListMultipartUploadParts` on
  `arn:…:story-<env>-media-*/media/*` and presign rights; DynamoDB RW on `story-<env>-media`.
- No client ever gets bucket credentials — only short-TTL presigned URLs scoped to one key under its own prefix.
- Account deletion (§5) cascades: delete all `media/{story_user_id}/*` objects + records.

---

## Phase 3 — Local storage optimization (iCloud-Photos-like)

### 3.1 The safety invariant (concrete, enforced in code)

> **A local original may be evicted only when ALL hold:** (1) a `cloud_verified` record exists for its
> `cloud_media_id` (verified = object present, size + checksum match); AND (2) no active operation holds the
> local file — not capturing, not uploading, not rendering, not exporting, not an in-flight edit plan whose
> render will need it; AND (3) `keepDownloaded == false`.
> **Never delete the only valid copy of an asset.** If verification is in any doubt, do not evict.

### 3.2 Policy

- **Capture never waits for network**: `adoptCapturedFile` stays synchronous-local; upload is enqueued async
  afterward (new `MediaUploadQueue`, same shape as `AssetUnderstandingQueue` — PENDING→RUNNING with bounded
  backoff, survives relaunch, gated on auth).
- **Preview retained on eviction**: generate a lightweight preview (poster JPEG + optional low-res proxy) at
  capture time; store `previewRelativePath`. Evicting the original keeps preview + metadata + `cloud_media_id`.
- **Automatic optimization** (public-release polish, but the invariant ships for beta): when device storage is
  low and assets are `cloud_verified`, evict oldest-unused originals first.
- **Keep Downloaded**: per-Moment and global toggle; pins the original (never evicted).
- **Download on demand**: when editing/playback/export needs an evicted original, fetch via presigned GET into
  `Documents/media/`, mark `downloaded_on_demand`; avoid repeat downloads by checking local presence first.
- **Offline honesty**: cloud-only Moments show a clear "needs download" state; editing that requires them
  prompts a download or blocks with an honest message rather than silently substituting the preview.
- **Active-operation protection**: a ref-count / "pinned for operation" set guards files held by capture,
  upload, render, export, or a `PendingOperationModel` whose render is unfinished.
- **Insufficient storage / interrupted transfer**: upload resumes from last part; download retries; eviction
  that can't free enough space surfaces honestly.

---

## Phase 4 — Cloud-backed Story creation & editing

### 4.1 Media resolution happens BEFORE the planner (no frozen-contract change)

The Edit Planner is text-only and receives `{id, duration_seconds, useful_segments, folded summary}` — it never
sees bytes. So cloud-only media changes **nothing** in the frozen contracts. What changes is a **resolution
step** before render:

1. Build the Story's required source set (included Moments → their Assets).
2. For each Asset: if `local` present → use it; if `local_optimized`/cloud-only → **download original** (presigned
   GET) and pin it for the operation.
3. Only when **all required originals are locally present** does `MediaEngineV1` run. Rendering/export always
   uses the **true original**, never the preview (owner rule: no silent quality substitution for final export).

### 4.2 Mixed-source Stories

A Story may mix `local_only`, `downloaded_on_demand`, and cloud-only Moments. The resolver handles all three
uniformly: resolve → (download if needed) → pin → render → unpin. Edit plans, source ranges, version lineage
(`GeneratedOutputModel`), and native-audio behavior are untouched.

### 4.3 What stays frozen

EditPlan/2, music_plan/1, moment_understanding/1, story_coverage/2, story_guide/1 — byte-identical. Any change
to these requires a **separate versioned proposal** (owner STOP gate).

---

## Phase 5 — Metadata synchronization & recovery

### 5.1 Account-owned sync surface

Server becomes authoritative for (per `story_user_id`): media records (§2), and a **metadata mirror** of
Stories, Moment links, creative direction, edit plans, generated versions, music refs, and generation/job state.

**Beta sync scope (per owner Correction 5 — expanded from the original "media + ownership + links only"):**
beta synchronizes **essential account-owned creative project state** — stable Story identity; title/description;
Moment references + ordering; creative direction; edit plans; generated-version **metadata + lineage**; music
selection; relevant job/recovery refs — **plus** media records + Story/Moment ownership. Recomputable AI
analysis caches (`StoryCoverageModel`, `StoryGuideModel`, `MusicPlanCacheModel`, `DurationRecCacheModel`) **may
remain local** initially and be recomputed after recovery. This is enough to (a) enforce isolation, (b) restore
the creative project after reinstall, and (c) re-render.

### 5.3 Rendered-video backup policy (beta)

**Rendered GeneratedOutput video files are NOT backed up to cloud during beta.** Rationale: originals + the
exact `editPlanJSON`/music/version lineage ARE synced (§5.1), so a recovered Story is **re-renderable on
demand** without the baked output. Limitation, documented honestly: after reinstall/device-replacement a
recovered Story shows its versions' **metadata** and can **re-render** from the restored originals + plan, but
the previously-rendered MP4 bytes are not restored until re-render. GeneratedOutput cloud backup is a
**public-release** item (§6). Metadata-only restore is **never** presented as complete recovery when the
rendered output or a required original is unavailable.


### 5.2 Scenarios

- **Offline creation + retries**: local-first; upload + metadata push queued, idempotent, resume on reconnect.
- **Cross-device**: a second device signs in → lists media records → shows cloud-only Moments (download on
  demand). Beta: media + links; richer creative sync later.
- **Conflict handling**: last-writer-wins on metadata with server `updated_at`; media is immutable once
  verified (no conflict possible on bytes).
- **Deleted/unavailable media**: a record without a retrievable object is surfaced honestly; never presented as
  recoverable.
- **Account switching**: filter by owner; no transfer, no re-upload (§7).
- **Device replacement / reinstall**: sign in → metadata + media records restore the **library shell**;
  originals are cloud-only until downloaded. **Metadata-only restore is NOT presented as complete recovery**
  unless the required media objects are also retrievable (owner rule).
- **Account deletion / export**: delete cascades S3 + all records; export produces the user's originals +
  metadata.

---

## Phase 6 — Updated roadmap, estimates, risks, acceptance

Estimates are engineer-days for one experienced iOS+backend engineer; ranges reflect test/QA. Dependencies are
hard unless noted.

### REQUIRED BEFORE EXTERNAL BETA

| # | Milestone | Est (d) | Depends on | Security / migration risk | Acceptance |
|---|---|---|---|---|---|
| R1 | **Account-owned Story creation + local isolation** (owner fields + filtered reads + auth-gated creation + **dev-only idempotent backfill of pre-R1 Stories to the designated `dearlingzhang@gmail.com` account**; fixes trigger bug) | 4–6 | — | Migration: dev-only, non-destructive, never overwrites an explicit owner, local-only Moments left shared. Risk: a wrong predicate hides a user's own content. | Two accounts on one device see **disjoint** Stories; **local-only Moments stay visible to both**; pre-R1 Stories appear only under the designated account; new Stories owned by their creator; sign-out destroys nothing. |
| R2 | **Server-side ownership enforcement** (media + Story/Moment records owner-scoped; edit-plan job store owner-scoped) | 3–5 | R1, auth seam (done) | A missing owner check = cross-account read. Fail closed in prod. | Every media/metadata endpoint rejects access to another `story_user_id` (403); job store rejects cross-owner poll. |
| R3 | **Cloud media storage infra** (S3 media bucket + DynamoDB media table + IAM + presign endpoints) | 4–6 | — (CDK) | Public-access misconfig; presign scope leak. Provisioning (owner-gated). | Bucket BLOCK_ALL + SSE + SSL-only; presigned URL only under caller's prefix; no object public. |
| R4 | **Safe async upload** (MediaUploadQueue, multipart, verify, non-blocking capture) | 5–7 | R3 | Interrupted upload corruption; verify bypass. | Capture never blocks on network; upload resumes after suspend/kill; `cloud_verified` only on checksum match. |
| R5 | **Verified local optimization** (invariant + preview retention + eviction guard) | 4–6 | R4 | **Data loss** if invariant is wrong — highest-severity item. | Never evict without `cloud_verified`; never evict a file held by an active op; Keep-Downloaded pins. |
| R6 | **On-demand media restoration** (download + pin + no-repeat) | 3–4 | R3, R4 | Download auth/scope; repeated downloads cost. | Cloud-only Moment downloads once, pins for op, re-evictable. |
| R7 | **Essential metadata sync** (media records + Story/Moment ownership + links + title/description + creative direction + edit plans + version metadata/lineage + music selection + job/recovery refs; recomputable AI caches stay local; **rendered MP4 not backed up** — §5.3) | 5–7 | R2, R3 | Metadata-without-media/output false "recovery". | Reinstall → project state restores; originals cloud-only until downloaded; Story **re-renderable**; honest states; rendered-output limitation documented. |
| R8 | **Cloud-only rendering resolution** (resolve→download→pin→render; no quality substitution) | 3–4 | R6 | Final export silently using preview. | Mixed-source Story renders from true originals; export never uses preview. |
| R9 | **Existing capture/editing regression acceptance** | 3–4 | R1–R8 | Regression in frozen pipeline. | All current device-acceptance scenarios still pass; frozen contracts byte-identical. |
| R10 | **Server-side beta usage protection + CloudWatch monitoring** (owner-scoped quotas hooks, upload/download/verify metrics + alarms) | 2–3 | R2, R3 | Unmonitored abuse/cost. | Dashboards for upload success/verify/download; alarms on failure spikes + bucket growth. |

**Beta subtotal: ~35–51 engineer-days.** Critical path: R3→R4→R5 (media safety) and R1→R2 (isolation), largely
parallelizable; R1 alone (~4–6d) stops the trigger bug and is the first increment.

### PUBLIC RELEASE
Robust automatic background upload (BGProcessingTask); storage-management UX; multi-device recovery polish;
upload/download perf (adaptive multipart, concurrency); improved offline behavior; GeneratedOutput cloud backup;
SSE-KMS; full creative-metadata sync (coverage/guide/plans). **Est: ~25–40d.**

### LATER
Advanced cross-device editing; collaborative/shared libraries; cloud rendering (only if justified); additional
media-intelligence features. **Est: not estimated (research-gated).**

---

## 7. Privacy & account-switching rules (the trigger-bug contract)

1. **Stories and uploaded Moments carry a server-authoritative owner (`story_user_id`); the device mirrors it
   as `ownerAccountId`. Local-only Moments carry NO owner (nil) and belong to the shared device-local library.**
2. **Reads filter by the active owner, EXCEPT local-only Moments which are always visible.** Signed-in account A
   sees Stories/uploaded-Moments with `ownerAccountId == A` **plus every local-only Moment (`ownerAccountId ==
   nil`)**. Account B sees B's owned content **plus the same shared local-only Moments**. (Per owner Correction
   1 / Decision 1.C — local-only Moments are deliberately shared across accounts on the device.)
3. **Switching accounts never uploads, transfers, or duplicates** the other account's Stories/owned Moments.
   Ownership is decided server-side; a non-owner cannot see or presign the object. A local-only Moment is never
   auto-claimed by switching.
4. **Signing out destroys nothing** (local media + cloud content survive); it only drops the session and hides
   owned content until re-auth. Local-only Moments stay visible.
5. **A persistent Story is created ONLY after authentication** and is stamped with the authenticated
   `story_user_id` at creation — there is no anonymous Story and no first-account adoption of Stories. Local-only
   Moments are **never** auto-assigned to any account.
6. **No enumeration**: cross-account access returns 403/absent, never "exists but denied" in a way that leaks
   another account's data.

---

## 8. Existing-data migration strategy

- **Local**: additive SwiftData fields only (no heavy migration — matches the sandbox constraint and the file's
  established additive pattern). **Owner fields default to `nil`** on existing rows.
- **Dev-only designated-account backfill (owner Correction 4 / Decision 3):** a one-time, idempotent,
  **development-only** routine assigns **all pre-R1 Stories** (and, transitively, their GeneratedOutputs, edit
  plans, creative direction, Story↔Moment links, music selection, and pending project records) to the account
  resolved from **`dearlingzhang@gmail.com`**. The owner id is the backend-resolved **immutable
  `story_user_id`**, never the email. It **never overwrites** a Story that already has an explicit owner, does
  **not** touch local-only Moments (they stay shared), does **not** move/duplicate/delete media files, and does
  **not** run in production or public-beta onboarding.
- **No migration-pending state, adoption UI, or framework** — there are only two internal testers; the backfill
  is a single pass guarded by a dev flag + an already-stamped check (idempotent).
- **Cloud**: nothing to migrate (no cloud media exists yet). First upload is net-new.
- **No destructive migration** without explicit owner approval (STOP gate).

---

## 9. Device acceptance matrix (for the eventual implementation, not now)

| # | Scenario | Expected |
|---|---|---|
| 1 | Account A signs in, creates Story+Moments; sign out; account B signs in | B sees **none** of A's Stories/Moments |
| 2 | B creates content; switches back to A | A sees only A's; B's not re-uploaded under A |
| 3 | Capture while offline | Capture completes with no network wait; upload queued |
| 4 | Upload a Moment, kill app mid-upload, relaunch | Upload resumes from last part; reaches `cloud_verified` |
| 5 | After `cloud_verified`, storage optimization runs | Original evicted, preview+metadata remain; Moment still listed |
| 6 | Open an optimized (cloud-only) Moment for playback | Downloads on demand, plays true original |
| 7 | Render a Story mixing local + cloud-only Moments | Resolves/downloads all originals, renders from originals (not preview) |
| 8 | Keep Downloaded ON for a Moment | Never evicted even under storage pressure |
| 9 | Reinstall app, sign in | Library shell restores (media records); originals cloud-only until downloaded; honest states |
| 10 | Sign out | No local media or cloud content deleted |
| 11 | Delete a Moment from library | Cloud object + record deleted (owner-checked); other Stories' media untouched |
| 12 | Account deletion | All `media/{user}/*` + records removed; export available first |
| 13 | Never-evict invariant | No path evicts a `local_only`/active-op/Keep-Downloaded original |
| 14 | Cross-account API probe | Accessing another `story_user_id`'s media → 403 |
| 15 | Final export quality | Export uses true original, never the preview |

---

## 10. Decisions requiring owner approval

1. **Provision the media infra** (S3 media bucket + DynamoDB media table + IAM) in dev `989088054552` — gated by
   STOP; approve to begin R3.
2. **First increment = R1 (local isolation + owner back-fill)** shipped and device-accepted **before** any cloud
   work, so the trigger bug is fixed fastest. Approve ordering.
3. **Already-mixed devices**: accept that a device whose pool already mixes A+B back-fills to one account, with a
   clean reinstall as the clean-slate path for current testers. (§8 limitation.)
4. **Preview strategy**: poster-JPEG only vs poster + low-res proxy (proxy costs capture CPU + storage). Default
   proposal: poster-JPEG for beta, proxy later.
5. **Dev encryption**: SSE-S3 for beta, SSE-KMS as a public-release hardening. Confirm acceptable for beta.
6. **Metadata sync scope for beta**: media + ownership + links only (creative metadata stays recomputable/local
   until public release). Confirm.

---

## 11. Known risks (ranked)

1. **Eviction data loss (R5)** — a wrong invariant deletes an un-backed original. Mitigation: verify-before-evict
   + active-op guard + never-only-copy; extensive tests; ship optimization last.
2. **Cross-account leak (R1/R2)** — a missing owner filter re-exposes the bug. Mitigation: filter at repository
   AND server; fail-closed prod; dedicated isolation tests (matrix #1,#2,#14).
3. **Already-mixed-device migration (§8)** — cannot un-mix existing shared pools. Mitigation: owner-accepted
   limitation + reinstall path for current testers.
4. **Presign scope leak (R3)** — a URL minted for the wrong prefix. Mitigation: server derives key from the
   caller's `story_user_id` only; never client-supplied keys.
5. **Interrupted upload / suspend kill (R4)** — mirrors the known -1005/Operation-Interrupted suspend issue;
   reuse the idle-timer + background-task keep-alive lesson for the upload path.
6. **Edit-plan job store not owner-scoped** — pre-existing; a poll with a known `job_id` is not owner-checked.
   Hardening item folded into R2.
7. **Frozen-contract drift** — none expected (media resolved before planner); any change needs a separate
   versioned proposal.

---

## 12. Explicitly excluded (per owner)

Free-tier AI allowances, free generation counts, subscriptions, storage pricing tiers, billing, anonymous paid
inference, device promo credits — all belong to a future **Billing, Free Tier & Monetization** milestone. No
CI/CD investigation. No unrelated feature work.

---

## 13. STOP gate (honored)

No S3/DynamoDB provisioned. No destructive migration. No cloud media implemented. No frozen editing contract
changed. No production deployment. This document is the review; implementation begins only on owner approval of
§10.

---

## 14. Immediate recommended first step (on approval)

**R1 only**, as an isolated, device-acceptable increment: add `ownerAccountId` to `StoryModel`/`MomentModel`/
`AssetModel`/`GeneratedOutputModel`, back-fill to the device's adopting account, and filter the two home
`@Query`s + `StoryRepository.fetchStories()`/`allMoments()` by the active owner. This stops the trigger bug in
~4–6 days without any cloud dependency, and establishes the ownership field every later phase builds on.

---

## 15. Deliverable index (requested 12)

1. Updated ownership architecture — §0, §1, §7
2. Local-to-cloud Moment lifecycle — §1.2, §3
3. Story account-ownership design — §1, §7, §8
4. AWS storage & synchronization architecture — §2, §5
5. Local storage optimization policy — §3 (invariant §3.1)
6. Cloud-only rendering/download design — §4, §3 (download-on-demand)
7. Privacy & account-switching rules — §7
8. Existing-data migration strategy — §8
9. Updated beta roadmap — §6
10. Engineering effort & risks — §6, §11
11. Device acceptance matrix — §9
12. Decisions requiring owner approval — §10
