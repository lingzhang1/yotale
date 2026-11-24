# YoTale R2/R3 — Server-Authoritative Media Ownership & Private Cloud Storage (Gate A)

Status: **GATE A — CODE REVIEW. Implemented + all tests green. NO AWS resources provisioned. STOP before
provisioning (owner approval required for Gate B).**
Date: 2026-10-20
Branch: `feat/r1-account-ownership-isolation` (commit `386ef49`).
Depends on: R1 (account ownership) + R1.1 (canonical `story_user_id` via `/v1/me`, live on dev).

Scope delivered: Phases 0–5. Explicitly NOT in this increment: iOS background upload, local eviction,
download-on-demand in the renderer, cloud Story-metadata sync, media deletion, billing, production infra,
CI/CD changes, frozen-contract changes.

---

## Phase 0 — Integration boundaries confirmed (reused, not redesigned)

| Existing asset | How R2/R3 reuses it |
|---|---|
| `app.auth.require_user` / `Principal` | Every media endpoint depends on `require_user` (auth required even in dev; legacy `dev` can't reach them). |
| Canonical `story_user_id` (R1.1) | The ONE owner identity — derived from the verified token, never client-supplied. |
| `edit_plan_jobs.JobStore` patterns | `media_store.MediaStore` mirrors them: lazy boto3, conditional `put_item`/`update_item`, idempotent create-or-get, injectable clients for tests. |
| Private SSE `BLOCK_ALL` staging bucket (CDK) | The media bucket copies the hardening, but is a **separate** durable bucket (no 24h TTL). |
| DynamoDB conditional-write identity claims | Same conditional-write discipline for the media ownership table. |
| Job ownership 404 rule | Media reads/writes for a non-owner return 404 (never reveal another account's media). |

Current Story/Moment cloud identity fields (R1): `MomentModel.cloudStateRaw`/`cloudMediaId`, `AssetModel`/
Moment `ownerAccountId` already exist (additive, nil in R1). R2/R3 is the **server** side those fields will
point at; **no SwiftData or iOS change in this increment.**

---

## Phase 1 — Server-authoritative ownership (`packages/media_store/__init__.py`)

- **Identity:** `cloud_media_id = uuid5(owner + content_sha256)` — deterministic, so a re-initiate of the same
  content by the same owner is idempotent and never duplicates bytes. Owner folded in → two accounts with
  identical bytes get **distinct** ids (no cross-account dedup / no leak).
- **Record key:** DynamoDB composite `(story_user_id HASH, cloud_media_id RANGE)`. `list_for_owner` is a
  **Query on the PK** (never a Scan) → inherently account-scoped. A wrong-owner `get` finds nothing.
- **Ownership is server-derived only.** `owner` is always `principal.story_user_id`; no client field is trusted
  (requirements 1–3, 9).
- **State machine (cloud side):** `uploading → cloud_verified` (+ `upload_failed`). Conditional `update_item`
  guards `uploading → cloud_verified` (no skip/backward). Idempotent: a re-complete of a verified record is a
  no-op; a race re-reads the winner.
- **No automatic ownership transfer on account switch** (requirement 7): records are immutable-owner; switching
  accounts just changes which owner the API queries. **Local-only Moments carry no cloud record** until upload
  (requirement 8).

---

## Phase 2 — Private S3 + DynamoDB (CDK, `infrastructure/cdk/lib/story-api-stack.ts`) — NOT provisioned

**Exact resource changes (synth-verified; 2 new resources + IAM + env):**

1. **S3 `story-<env>-media-<acct>-<region>`** — `BlockPublicAccess.BLOCK_ALL`, `encryption=S3_MANAGED`
   (SSE-S3), `enforceSSL=true`, lifecycle **`abortIncompleteMultipartUploadAfter: 7 days`** and **NO expiration
   on completed originals**, `removalPolicy: RETAIN`. Separate from the 24h edit-plan staging bucket.
2. **DynamoDB `story-<env>-media`** — PK `story_user_id`, SK `cloud_media_id`, `PAY_PER_REQUEST`, **no TTL**
   (originals are durable), `removalPolicy: RETAIN`.
3. **App Runner instance-role IAM (least privilege):** media table RW; `s3:PutObject, s3:GetObject,
   s3:AbortMultipartUpload, s3:ListMultipartUploadParts` scoped to `arn:…:<media-bucket>/media/*`. **No
   `s3:DeleteObject`** (no deletion this increment), no bucket-level admin.
4. **App Runner env:** `STORY_MEDIA_TABLE`, `STORY_MEDIA_BUCKET` added to the (full-replace) runtime env list.

No production resources. No reuse of the staging bucket for originals.

---

## Phase 3 — Media API (`apps/api/app/main.py`) — direct-to-S3, never proxied

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /v1/media/initiate` | `require_user` | Idempotent create of an `uploading` record + a bounded presigned **PUT** (device uploads bytes direct to S3). 409 on a same-id/different-content conflict. |
| `POST /v1/media/{id}/complete` | `require_user` | Durable verification → `cloud_verified`. 404 if not the caller's; 422 on verification failure (record stays recoverable). |
| `GET /v1/media/{id}` | `require_user` | Status/recovery for the caller's own record; 404 otherwise. |
| `GET /v1/media/{id}/download` | `require_user` | Short-lived presigned **GET** for the caller's own verified object; 409 if unverified. |
| `GET /v1/media` | `require_user` | List the caller's own records (owner-PK Query). |

Resumable transfer (honest): this increment is a **single presigned PUT of the whole file**. An interrupted
upload leaves the record `uploading`; recovery is **whole-file** — re-initiate (idempotent, same record) and
re-PUT the entire file. **Part-level multipart resume is NOT implemented; it is deferred to R4.** The bucket's
`AbortIncompleteMultipartUpload` rule is only a cost-hygiene backstop, not evidence of part-level resume.
Presigned TTLs bounded: upload 60 min, download 15 min. **No deletion endpoint exists** (reference-safe
deletion is a later increment).

---

## Phase 4 — Integrity & idempotency (the checksum design)

- The device computes a **full-file sha256 (hex)** and declares it + size at initiate. The presigned PUT
  **requires the `ChecksumSHA256` header**, so S3 records a verifiable per-object checksum.
- `complete` does a server `HeadObject(ChecksumMode=ENABLED)` and verifies: **object exists ∧ `ContentLength`
  == declared size ∧ S3 `ChecksumSHA256` (base64 of the raw digest) == base64(declared hex sha256)**. Only then
  `cloud_verified`.
- **A multipart ETag is NEVER treated as a sha256** (it isn't one for multipart). The S3 `ChecksumSHA256`
  object attribute is the integrity anchor.
- **No client input marks an object verified** — only the server HeadObject result does. An upload response
  alone authorizes nothing. Interrupted uploads stay `uploading` (recoverable). **No eviction authorized.**

---

## Phase 5 — Security tests (all green)

- **Backend media API** (`apps/api/tests/test_media_api.py`, 16): authenticated initiate; missing/invalid token
  → 401; cross-user listing isolation; cross-user download → 404; cross-user completion → 404; presigned URL
  scoped to the owner's key; duplicate initiate idempotent; duplicate complete idempotent; interruption + resume;
  wrong checksum → 422; wrong size → 422; missing object → 422; ownership-record conflict → 409; bounded
  presigned TTL; **no DELETE endpoint**; **legacy `dev` cannot reach any media API** (401).
- **`media_store` unit** (`packages/media_store/tests/`, 8, **CI-collected**): id determinism + owner-scoping;
  account-scoped key; sha256-hex→b64 S3 contract; verify happy-path; verify rejects bad checksum/size/missing;
  initiate idempotent + conflict; download-requires-verified; list owner-scoped.
- **CDK** (`infrastructure/cdk/test/story-api-stack.test.ts`, 6 new, 28 total): private bucket (block-all +
  SSE-S3 + TLS); abort-multipart-7d + no-expiration-on-originals; bucket RETAIN; media table composite-key +
  no-TTL; App Runner media env; least-privilege media IAM with **no `s3:DeleteObject`**.

Totals: `apps/api/tests` **313 passed**; CI-scope `packages contracts` **130 passed**; CDK jest **28 passed**.
(Public-S3-access test #15 is the CDK `BLOCK_ALL` assertion; destructive-deletion test #16 is the "no DELETE
endpoint" + "no s3:DeleteObject" assertions.)

---

## Estimated dev cost (beta scale: 2 testers, low volume)

Order-of-magnitude, us-east-1, SSE-S3:
- **S3 storage:** originals retained. ~a few GB of beta footage → **< $0.25/mo** ($0.023/GB-mo). 100 GB would
  be ~$2.30/mo.
- **S3 requests:** PUT/GET/HEAD per upload+verify+download. Thousands of requests/mo → **< $0.05/mo**
  ($0.005/1k PUT, $0.0004/1k GET). Presigned GETs are direct-to-S3 (no App Runner egress).
- **Data transfer out:** download-on-demand is deferred (no renderer downloads yet); device re-downloads during
  testing → a few GB → **< $0.20/mo** (first 100 GB/mo ~$0.09/GB; 100 GB free tier often applies).
- **DynamoDB:** PAY_PER_REQUEST, a few thousand ops/mo → **< $0.01/mo**.
- **Total dev: well under $1/mo at beta scale**, dominated by storage as footage accumulates. No NAT, no
  always-on compute added (App Runner already runs). Billing/quota policy is a separate excluded milestone.

---

## Gate B (after owner approval) — do NOT run yet

1. Provision **dev only** via the approved digest-pinned `deploy-dev.yml` (CDK deploy adds the 2 resources +
   IAM + env; App Runner redeploys with the new env).
2. Verify exact CDK changes (`cdk diff` shows only the media bucket/table/IAM/env).
3. Small real upload→verify→download round-trip with a test account; confirm cross-account 404 isolation,
   object integrity (checksum), and private access (no anonymous GET).
4. STOP at dev acceptance.

---

## Files

- `packages/media_store/__init__.py`, `packages/media_store/tests/test_media_store.py`
- `apps/api/app/main.py` (media endpoints + `MediaInitiateRequest`), `apps/api/tests/test_media_api.py`
- `infrastructure/cdk/lib/story-api-stack.ts` (media bucket/table/IAM/env), `infrastructure/cdk/test/story-api-stack.test.ts`
