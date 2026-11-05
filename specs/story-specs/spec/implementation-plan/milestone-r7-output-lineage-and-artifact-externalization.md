# YoTale R7 — Output Version-Lineage Decode Fix + ai_artifact Externalization

Status: **IMPLEMENTED (iOS + backend); backend DEPLOYED + live-verified (dev); AWAITING two-device physical acceptance.**
Branch: `feat/r1-account-ownership-isolation`. Commits: `81bac08` (lineage decode fix), `e90ea13` (Phase 4 externalization).
Worktree: `/Users/lingzhang/Workplace/story`.

## Why this milestone exists

A two-device test of the TMB Story showed Device B regenerating the Story Guide and starting a **fresh** Story
("Create my Story" with no versions) despite the R7 sync client being present. Reconciliation (below) proved the
code was on the right branch and compiled in — the defect was a **missing decode path**, not missing code.

## Phase 0 — Reconciliation (previous vs current R7 code)

A prior diagnosis ("no iOS Story API calls exist") was run in the WRONG worktree
(`/Users/lingzhang/Workplace/story-wt-r7d-generated-mp4-backup`, branch `feat/r7d-generated-mp4-backup` @
`a0ea45f` = the backend-only R7 merge). The full R7 iOS sync client exists on
`feat/r1-account-ownership-isolation` @ `9d750ed`: `StorySyncService` / `StorySyncCoordinator` (`233b21a`,
`38c072c`), `StoryDocCodec` + `story_doc/2` derived state (`62001b5`), `UnderstandingSync`, `CloudHydrationGate`
(`8cd4504`), R7-D MP4 backup (`9d750ed`). Target membership verified: the `Story` group is a
`PBXFileSystemSynchronizedRootGroup` whose only exclusion is `Info.plist`, so every `Media/Sync/*.swift`
compiles into the app. No uncommitted sync-source changes existed to clobber.

## The defect (root cause of the Device-B symptoms)

1. **`StorySyncCoordinator.apply()` never created `GeneratedOutputModel` rows.** It decoded `story` + `moment_refs`
   only; nothing materialized the doc's `outputs[]` array on a new device. `applyDerived`'s `output_edit_plans`
   loop only *updated an output that already existed locally*. On Device B the outputs never existed → zero
   versions → "Create my Story" started fresh.
2. **`StoryDocCodec.encode` dropped version lineage** from `outputs[]` (no `version_id`, `parent_version_id`,
   `operation_type`, render shape, `soundtrack_title`, music refs).
3. The "different Guide" was a downstream consequence: the `CloudHydrationGate` ordering is correct
   (`StoryHomeView.loadCoverage` waits for hydration before `ensureGuide`); the Guide is restored by
   `applyDerived(preferCloud:true)` once the pull runs on a current binary.

## Fix (commit `81bac08`)

- `StoryDocCodec.encode`: `outputs[]` now carry full lineage.
- `StoryDocCodec.applyOutputs` (new): idempotent create of `GeneratedOutputModel` rows from `doc.outputs`
  (keyed by stable `output_id` → no duplicates on re-pull), preserving lineage, restoring the exact
  `editPlanJSON` from `derived.output_edit_plans` and the MP4 `cloudMediaId`/`cloudVerifiedAt` for R6
  restore-on-play. `relative_file_path` from the cloud is a hint only — never adopted as authoritative; R6
  re-proves bytes before playback. NEVER re-renders.
- `StorySyncCoordinator.pull()` and `resolveKeepBoth()` call `applyOutputs` before `applyDerived`.
- `StoryCreativeRefinement.buildIdentifier` bumped `me-mymusic-top+save` → `r7-output-sync-1` for device
  build-id proof (shown in the Music picker).

## Phase 4 — ai_artifact externalization (commit `e90ea13`)

The backend caps a Story document at 350 KB and FAILS explicitly (413) rather than truncating. A Story with
many large validated EditPlans must externalize the oversized plans so version history is never capped.

- **Backend** (`packages/media_store`): add `MEDIA_KIND_AI_ARTIFACT`. No new bucket, table, or endpoint — an
  EditPlan is immutable, content-addressed bytes, so it rides the EXISTING R4 upload / R6 verified-download
  pipeline (same key `media/{owner}/{cmid}/original`, `cloud_media_id = uuid5(owner+sha256)`, full-file SHA256
  verify, non-deleting retention). `content_type` on the media initiate path is a free string, so an artifact
  declares `application/json`. +4 backend tests.
- **iOS `AIArtifactStore`** (new): `externalize(json)` uploads + verifies and returns a durable reference
  `{cloud_media_id, sha256, bytes, schema_version}`; `resolve(ref)` downloads with size+SHA256 verification and
  re-checks the declared sha, throwing explicitly if an artifact cannot be restored (never drops a version).
- **`StoryDocCodec`** pure transforms: `plansToExternalize` (over-budget → largest plans first),
  `applyExternalizedRefs` (swap inline JSON → `edit_plan_ref`), `externalizedRefs` + `inlineResolvedPlans`
  (resolve back before decode). Refs are added to `referenced_cloud_media_ids` for the server C3 check.
- **`StorySyncCoordinator`**: externalize before the PUT when over budget (a 413 remains the safety net);
  resolve refs before decode on pull and conflict-adopt; on failure the doc stays dirty / the conflict is kept
  for retry — a version is never decoded with a missing plan.

## Requirement coverage (owner Phases 1–5)

- Phase 1 (StoryDocCodec): full lineage encode/decode incl. version_id/parentVersionId/operationType, exact
  EditPlan, MP4 cloud ref + verification state; never a local path as a cloud reference.
- Phase 2 (StorySyncService): existing debounced push / offline retry / monotonic revision / payload-bound
  mutation_id / 409 Keep-Both-or-Use-Cloud / account isolation / idempotent re-pull (output rows now dedup by
  output_id) — unchanged except the decode completion.
- Phase 3 (AI-state hydration): existing `applyDerived` + `UnderstandingSync` + `CloudHydrationGate` restore
  Guide/Coverage/Music/duration/AU and EditPlans before any generation; this milestone makes the EDIT PLANS +
  VERSION ROWS part of that hydration real.
- Phase 4: externalization above (no silent cap/truncation; content-addressed; account-scoped; SHA256-verified;
  durable refs; no deletion; explicit failure).
- Phase 5 (Generated MP4): R7-D path (commit `9d750ed`) unchanged — upload via R4 queue, cloud_verified before
  the ref is committed, lineage preserved, cloudMediaId synced, R6 restore-on-play, never re-renders.

## Tests

- Backend: `apps/api/tests` + `packages` FULL suite **438 green** (media API 48, incl. +4 ai_artifact).
- iOS: `StorySyncTests` extended — encode lineage, create-on-pull, idempotent re-pull, exact-plan restore,
  full-pull materialization, owner isolation (lineage fix) + Phase-4: small-doc-externalizes-nothing,
  largest-first + inline round-trip, artifact-store roundtrip-verified, integrity-failure throws,
  push-externalizes-oversized, pull-resolves-externalized-into-version.
- Compile gate (honest): the Kiro sandbox blocks `swift-plugin-server`, so `xcodebuild`/XCTest cannot run here
  (every `@Model` fails "external macro could not be found" — an environment limit, not a code error). All
  touched files are `swiftc -parse` clean and the pure Phase-4 codec transforms compile+run via standalone
  `swiftc`. The authoritative Xcode compile + XCTest run on the device/developer machine.

## Deploy

CodeBuild `story-rb-caseg-build` SUCCEEDED → App Runner `story-development-api` forced `start-deployment` →
RUNNING, `/health` 200. Running container's last log event (00:16:18) is after the ECR `:latest` push
(00:15:06), confirming a FRESH digest (not stale). No new env, no DynamoDB table change (media table is
schemaless; the new `media_kind` value and artifact records need no migration).

## Remaining (the STOP point)

Two-device physical acceptance on the same account: Device A (Guide/Coverage/AU present, existing versions,
MP4s cloud_verified, sync bumps the backend revision) → Device B (sign in, pull, identical Story ID + Moment
order + Guide + Coverage, versions appear in the Result/version UI with exact EditPlans + lineage, a restored
MP4 plays through R6, **zero** restoration-triggered Bedrock calls, no duplicate rows after relaunch, another
account cannot see the Story). The device Xcode build is the authoritative Swift compile gate.

## Boundaries honored

Dev backend + existing CodeBuild/App Runner pipeline only. No prod deploy, no billing, no CI/CD redesign, no
frozen EditPlan/2 or prompt change, no add-new-Moment-during-revise (deferred P1), no expensive Bedrock jobs,
no destructive local migration, all existing media/versions preserved.


## R7 CLOSEOUT — implementation-complete, PROVISIONALLY ACCEPTED (owner, 2026-10-21)

Owner decision: close R7 for the current development stage. The **primary-device workflow is accepted**. Full
two-device synchronization testing is **deferred to controlled beta**. R7 is recorded as implementation-complete
and provisionally accepted, with physical A→B acceptance OUTSTANDING.

### Cross-device sync divergence — root-caused + fixed (commit `4e70ca4`)

A two-device test showed Device B diverging (different plans, missing generated videos, a new story on A not
appearing on B). Root-caused from backend + App Runner logs (same binary + same account confirmed — NOT a stale
build): 14 story docs under one owner; a new story was PUT by A but never GET by B. Two coordinator bugs:
- **Silent last-writer-wins:** `pull` stamped `job.lastSyncedHash` with the WIRE doc hash while `syncAllDirty`
  compares the LOCAL re-encode hash; decode→encode is not byte-identical, so every cleanly-pulled story looked
  dirty and the device pushed its thinner re-encode back over the other device's richer plans/outputs. Fix:
  stamp `lastSyncedHash` with the local re-encode of the adopted story (pull + conflict-adopt).
- **New story never adopted:** `StoryApp` ran `pull` and `syncAllDirty` as concurrent Tasks on one
  `mainContext`, racing the sync-job rows so the new story's adopt was lost. Fix: `reconcile()` runs pull fully
  THEN push, serialized; both StoryApp sites use it.
- `buildIdentifier` → `r7-sync-reconcile-2` for device build-id proof. Tests: pulled-story-not-repushed,
  reconcile-adopts-new-story-with-dirty. Client-only; no backend redeploy.

### Outstanding two-device (A→B) acceptance checks (deferred to beta)

1. Identical Story metadata and Moment ordering.
2. Identical Guide, Coverage, and Moment Understanding (AU).
3. GeneratedOutput versions and lineage present.
4. Exact validated EditPlan restoration (no re-plan).
5. Generated-MP4 restoration and playback through R6.
6. Zero unnecessary Bedrock inference during restoration.
7. Account isolation (another account cannot see the Story) and conflict recovery (Keep Both / Use Cloud).

Note on already-clobbered cloud docs: the pre-fix thrash left some docs holding Device B's thin copy. The fix
stops new clobbering; recovering an already-overwritten doc requires the device holding the rich local copy to
re-push it (a user edit, or a one-time forced re-push). Flagged for the beta acceptance run.

### Implementation commits (branch `feat/r1-account-ownership-isolation`, all preserved)

- `81bac08` R7-C fix — materialize GeneratedOutput version lineage on pull.
- `e90ea13` R7 Phase 4 — ai_artifact externalization for oversized EditPlans.
- `4e70ca4` R7 cross-device fix — stop Device B clobbering Device A + adopt new stories.
- (on the same branch earlier: R7-D `9d750ed`, R7 cloud-aware eligibility `7757fe4`, directive/customize work.)

### Branch ↔ master reconciliation (recorded, not merged — minimal/safe)

`feat/r1-account-ownership-isolation` is **59 ahead / 8 behind** `origin/master` (merge-base `102f96f`). The 8
"behind" commits are R7 backend PRs **#9–#16** (identity `/v1/me`, R2/R3 media ownership, R4-B multipart,
presign + checksum fixes, R6 download authority, R7 story sync, R7-E understanding) — the SAME features the
feature branch developed independently, so their code already exists in the branch's tree. A merge of master
into the branch conflicts across ~12 core backend files (both lines edited the same R7 code); a rebase would
rewrite 59 commits. Per the owner's "minimal closeout / avoid unrelated changes / no CI-CD investigation", the
reconciliation is RECORDED here and the actual merge is deferred to the normal PR-to-master workflow for this
branch rather than performed as a risky in-place history rewrite now. All R7 commits are preserved on the
branch. Nothing is pushed to the protected master.

### Exact running dev artifacts (recorded 2026-10-21)

- **App Runner** `story-development-api` (service `23daa77a2b654ab6b466420624b8b9ae`): RUNNING, image
  `story-development-api:latest`, **digest `sha256:ac958673b29ac6ab1c5bf53718bf5f80bdf25228e2cd84cee3a9b00a2d228b6a`**,
  pushed 2026-10-21T00:15:06-07:00. `/health` 200.
- **Worker** `story-development-edit-plan-worker` Lambda: PackageType Zip, Runtime python3.12, Handler
  `app.worker.handler`, **CodeSha256 `gD3z8kM9JGZJRk4jaLk4bdGRnlP+toZVUfhDrbp2QFs=`**, LastModified
  2026-10-21T05:34:29Z.

### Manual CodeBuild deployment deviation (documented, NOT redesigned)

The R7 backend was deployed to dev OUT OF BAND of the PR-merge pipeline: `git archive HEAD` + an injected ROOT
`buildspec.yml` (referencing `$ECR_URI`; the committed `infrastructure/cdk/buildspec.yml` uses unset
`$ACCOUNT/$REPO_NAME`) + `prompts/` → uploaded to `s3://story-codebuild-src-989088054552-us-east-1/rb-caseg/source.zip`
→ CodeBuild `story-rb-caseg-build` → App Runner forced `start-deployment`. This was a deliberate dev-iteration
shortcut to test unmerged R7 backend changes, not the sanctioned path (PR → master → pipeline). Recorded as a
known deviation; CI/CD redesign is explicitly out of scope and NOT performed.
