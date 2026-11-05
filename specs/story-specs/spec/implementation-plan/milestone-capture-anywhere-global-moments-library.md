# Milestone — Capture Anywhere + Global Moments Library: Architecture Gate

Status: **AUDIT + ARCHITECTURE PROPOSAL — awaiting owner approval. STOP before changing persistent models. Nothing pushed/deployed.**
Owner: lingzhang · Date: 2026-10-13 · Method: code-grounded (file:line verified against `apps/ios/Story/Story/Data/Persistence/Models.swift`).
Supersedes the "Create Now (C)" ephemeral-Story design in `milestone-mvp-reconciliation-createnow-versions-nlrevision.md` with a simpler, standalone-capture + global-library model.

---

## 1. Existing code-grounded architecture

**Ownership is a strict Story-owned tree, all `.cascade`:**
```
StoryModel
  ├─(.cascade, inverse MomentModel.story)──> [MomentModel]      (Models.swift:121)
  │                                              └─(.cascade)──> AssetModel  (media file)  (Models.swift:209)
  └─(.cascade, inverse GeneratedOutputModel.story)──> [GeneratedOutputModel] (Models.swift:124)
```
- **`MomentModel.story: StoryModel?` is SINGLE-VALUED** (`Models.swift:203`) — a Moment belongs to exactly ONE Story. No sharing possible today.
- **Deleting a Story deletes its Moments AND their media files** (cascade → MomentModel → AssetModel). This is exactly the behavior the owner wants to eliminate ("do not silently delete footage").
- **`AssetModel`** owns the real media as a RELATIVE path under Documents (`relativePath`, e.g. `media/<uuid>.mov`), resolved only via `MediaStore`. Bytes never in SwiftData. (`Models.swift:171+`)
- **`MomentUnderstandingModel` is ALREADY GLOBAL** — keyed by `@Attribute(.unique) momentId`, upsert-per-Moment, stores the `moment_understanding/1` wire JSON (`Models.swift:400-410`). It is NOT Story-scoped. ← major reuse win.
- **`GeneratedOutputModel`** persists each render (relative path under `rendered/`, `editPlanJSON`, version lineage `versionId/parentVersionId/operationType`), additive/migration-safe (`Models.swift:250+`).
- **Shoot-a-Moment** (`SceneScanFlowView.persistMoment`) captures → writes AssetModel → attaches MomentModel to the current Story → enqueues AU. Entry is only from inside a Story (`StoryHomeView`).
- **Home** "Create now" + "Use existing photos" cards are `enabled:false` (`HomeView.swift:55,97`); only "Start a Story" is wired.
- Store schema list + migration-failure recreate fallback in `StoryApp.swift`.

**Migration risk headline:** the single-valued `MomentModel.story` + the two `.cascade` rules are the load-bearing change. Flipping to many-to-many and nullify-not-cascade is a RELATIONSHIP shape change — SwiftData lightweight migration handles added/optional/defaulted properties, but a to-one → to-many relationship inversion + delete-rule change is a heavier migration that needs explicit handling and device testing (the sandbox cannot run it; owner's device is the gate).

## 2. Proposed domain model

**Make the Moment independent; associate Stories many-to-many; nullify instead of cascade.**
```
MomentModel (independent identity + media owner)
  • id (unique), caption, sourceRaw, createdAt
  • asset: AssetModel?  (KEEP .cascade — the Moment owns its media; deleting the MOMENT deletes its file)
  • stories: [StoryModel]   ← NEW many-to-many (replaces single `story`)
StoryModel
  • moments: [MomentModel]  (deleteRule .nullify, inverse MomentModel.stories)  ← was .cascade
  • generatedOutputs: [GeneratedOutputModel]  (KEEP .cascade — outputs are Story-owned)
MomentUnderstandingModel  — UNCHANGED (already global, keyed by momentId)
```
- **Independent Moment identity + media ownership:** media lifetime follows the MOMENT, not the Story. Deleting a Story nullifies the association, never the media.
- **Reuse across Stories:** many-to-many `MomentModel.stories` ⇄ `StoryModel.moments`.
- **Global vs Story-specific AU:** the raw `MomentUnderstandingModel` stays GLOBAL (one per Moment, unchanged). Any Story-specific *interpretation* (how a Moment reads under this Story's intent) is DERIVED at plan time from the global AU + the Story's CreativeIntent — NOT a stored per-(Story,Moment) record. Keeps the model simple and avoids N×M storage.
- **Safe deletion:** delete Story → nullify links, keep Moments+media+AU. Delete Moment (explicit, from library) → cascade its AssetModel (its own media) + its MomentUnderstanding; and nullify it out of any Stories (warn if it's in use).
- **Backward-compatible migration:** every existing Story-scoped Moment becomes a global Moment associated with that one Story (1-element `stories`). Media + outputs preserved.

## 3. SwiftData migration strategy
- This is NOT a lightweight (additive/defaulted) migration — it changes a relationship arity (to-one→to-many) and two delete rules. Options, safest first:
  1. **Additive bridge (preferred, lowest risk):** ADD `MomentModel.stories: [StoryModel]` (new, defaulted empty) and ADD `StoryModel.moments2` many-to-many, KEEP the old `story`/`moments` for one release; a one-time boot migration copies each `moment.story` into `moment.stories`, then reads switch to the new relationship. Change the Story→Moment delete rule to `.nullify`. The old to-one stays as a nullable shadow until a later cleanup release. This keeps SwiftData in lightweight-migration territory for the ADD and isolates the delete-rule change.
  2. **Explicit VersionedSchema + MigrationPlan:** model V1→V2 with a custom stage that rebuilds the relationship. Cleaner end-state, but SwiftData custom migrations are fragile and CANNOT be dry-run in this sandbox — device-only verification, higher risk.
- Keep the existing `StoryApp.swift` migration-failure recreate-store fallback as the backstop, but a recreate would be data loss, so the bridge approach (which avoids a failing migration) is strongly preferred.
- **Owner's device is the migration gate** — no CI can prove it.

## 4. Media ownership / deletion policy
- **Media is owned by the Moment** (`MomentModel.asset`, `.cascade`), stored as a relative path under `Documents/media/`. Resolve only via `MediaStore`.
- **Deleting a Story:** nullify the Story↔Moment links, delete the Story's `generatedOutputs` (Story-owned rendered files), **never touch Moment media or AU.** ← satisfies "do not silently delete footage."
- **Deleting a Moment (explicit library action only):** delete its AssetModel file + its MomentUnderstanding; if it is associated with any Story, warn/confirm first (it will vanish from those Stories' material sets, though already-rendered outputs are unaffected since they're separate files).
- **Orphan safety:** a Moment with empty `stories` is valid (library-only, not yet used). No auto-delete of unused Moments.

## 5. UX changes
- **Home:** replace the two disabled cards. Add **Capture** (opens camera immediately, standalone) and **Moments** (library). Remove "Use existing photos" as a Home milestone; existing-media import stays a shared action inside Capture/Library and Story building.
- **Capture Anywhere:** reuse the EXISTING Shoot-a-Moment flow (`SceneScanFlowView`), NOT a new capture engine. Default: camera opens immediately; optional AI shot idea; save Moment to the GLOBAL library; AU runs async. If launched from inside a Story, also associate with that Story.
- **Moments Library:** chronological list, thumbnail preview, multi-select, safe delete, "Create Story from selected." No albums/search/indexing for MVP.
- **Create from Moments:** selected Moments → the EXISTING creation pipeline (CreativeIntent, Duration Intelligence, Storytelling/Visual-first, MusicPlan, async Edit Planning, Media Engine, version persistence). No media duplication, no second Edit Planner path.

## 6. Implementation complexity
- **High-risk / must-get-right:** the relationship + delete-rule migration (§3) — the only genuinely hard part; device-gated.
- **Medium:** decoupling `persistMoment` from a required Story (make the Story association optional); the Moments Library screen (new UI, but standard list/multi-select); Create-from-Moments wiring (builds a Story from a selected Moment set then runs the existing coordinator).
- **Low / pure reuse:** Capture flow (existing), AU (already global), creation pipeline (unchanged), rendering (unchanged).

## 7. MVP scope & risks
- **In scope:** independent Moments, many-to-many association, Capture from Home, Moments Library (browse/preview/multi-select/delete/create), Create-from-Moments via the existing pipeline, nullify-not-cascade deletion, backward-compatible migration.
- **Out of scope (MVP):** albums, advanced search, large-library indexing, per-(Story,Moment) stored AU interpretation.
- **Risks:** (1) the relationship migration is the single biggest risk — a bad migration = data loss; mitigate with the additive-bridge approach + device gate + keep the recreate-store backstop. (2) Changing the Story delete rule must be verified to NOT delete shared media (acceptance test 4). (3) Thumbnail/preview performance on a growing library (bounded by MVP's no-indexing scope). (4) An in-use Moment deleted from the library needs a clear warning path.

## 8. Acceptance tests (owner device-gated)
1. Capture from Home with NO existing Story → Moment lands in the global library, AU runs.
2. Capture from inside a Story → Moment in library AND associated with that Story.
3. Add the SAME Moment to two Stories → both reference it; one media file, no duplication.
4. Delete one Story → its outputs gone, but the shared Moment + its media + AU survive and the other Story is intact.
5. Select library Moments → create a new Story through the existing pipeline → renders.
6. Close/reopen app → all Moments + associations persist.
7. AU + rendering complete with NO regression vs today.
8. Migration: existing Story+GeneratedOutput+Moment records survive the upgrade; each old Story-scoped Moment becomes a global Moment linked to that Story; media + outputs preserved.

---

## ADDENDUM (2026-10-13) — Phase 1 corrected persistence design (owner-approved architecture, migration corrections)

Owner approved the product architecture and required a corrected, recoverable migration (no silent store recreation; preserve the existing store; smallest demonstrably safe design). Decisions, grounded in: iOS target **18.5** (full `VersionedSchema`/`SchemaMigrationPlan` available), **no migration plan exists today**, **~36 read sites use `story.moments`** (the inverse — stays a `[MomentModel]` under either design, so reads do NOT break), and the current destructive `catch` in `StoryApp.swift` that deletes `.store/-shm/-wal` on migration failure.

### Selected design: explicit `StoryMomentLink` association model (NOT direct many-to-many)
```
MomentModel  (independent; owns its media)
  • asset: AssetModel?            (KEEP .cascade — deleting a MOMENT deletes its own media)
  • links: [StoryMomentLink]      (.cascade, inverse StoryMomentLink.moment — deleting a Moment removes its links, never a Story)
StoryModel
  • links: [StoryMomentLink]      (.cascade, inverse StoryMomentLink.story — deleting a Story removes its LINKS, never Moments/media)
  • generatedOutputs              (KEEP .cascade — Story-owned renders)
StoryMomentLink  (NEW join entity)
  • id, story: StoryModel?, moment: MomentModel?, addedAt: Date, orderIndex: Int?
MomentUnderstandingModel          (UNCHANGED — already global, keyed by unique momentId)
```
**Rationale vs direct many-to-many:** (a) a link row carries per-association data (order within a Story, added-at) without a future migration; (b) link rows are COUNTABLE/inspectable — directly serves the "verify relationship counts" acceptance requirement, where SwiftData's implicit join table is opaque; (c) delete semantics are unambiguous — a Moment is NEVER on a Story's delete path, so acceptance test 4 (delete Story, shared media survives) holds by construction.

### 1.3 — additive bridge CANNOT coexist with the legacy cascade (verified reasoning)
The legacy `StoryModel.moments` is `deleteRule: .cascade`. Keeping it live during a bridge means a Story delete still cascade-deletes Moments — the exact bug we are removing. **Therefore the delete-rule change must happen IN the migration; this is not a safe additive-only coexistence.** The old `MomentModel.story` to-one is retped as a NULLABLE shadow for backfill verification only, with its cascade neutralized by moving ownership to `StoryMomentLink`.

### Migration strategy (recoverable, idempotent, non-destructive)
- Use an explicit **`SchemaMigrationPlan`** with a V1→V2 stage (iOS 18.5 supports it). V1 = current schema; V2 adds `StoryMomentLink`, changes Story↔Moment ownership to the link + `.nullify`/link-cascade.
- **Custom migration stage backfills**: for every V1 Moment with a non-nil `story`, create one `StoryMomentLink(story:moment:addedAt:moment.createdAt)`. Idempotent: skip if a link for that (story,moment) already exists.
- **Non-destructive guarantee**: REMOVE the recreate-store `catch` in `StoryApp.swift`. On migration failure, DO NOT delete the store — surface a recoverable error (keep the old store intact so a fixed build can retry). Never auto-destroy user data.
- **Verification pass** after migration (logged, non-fatal): count Stories/Moments/Outputs/links; assert every pre-migration Moment still exists; assert each Moment's `asset.relativePath` file exists on disk; assert link count == pre-migration (Story,Moment) pairs.
- **Test fixture**: a populated V1 store (Stories + Moments + AU + GeneratedOutputs + media files) migrated in a test to prove counts/paths preserved before the device gate.

### Media ownership — captured vs imported
- **Captured** (camera): the app wrote the file under `Documents/media/` → the Moment OWNS it → `MomentModel.asset` `.cascade` (deleting the Moment deletes the file).
- **Imported** (existing-media): same ownership model once copied into `Documents/media/` (the app already copies on import, so lifetime is identical). If a future import references a Photos asset WITHOUT copying, that Moment's asset is `external` and library deletion must NOT delete the user's original — tracked as a sourceRaw distinction, out of MVP scope unless import copies change.

### Safe library removal vs destructive deletion
- **Remove from a Story** = delete the `StoryMomentLink` only (Moment + media + AU untouched).
- **Delete from library** (explicit) = delete the Moment → cascade its `asset` file + its `MomentUnderstanding`, and cascade-remove its links from all Stories; WARN if it is still linked to any Story first.
- A Story delete = cascade its links + its `generatedOutputs`; Moments/media/AU survive.

### Preserve GeneratedOutputs + version lineage
`GeneratedOutputModel` is UNCHANGED (still Story-owned `.cascade`; `versionId/parentVersionId/operationType/editPlanJSON` intact). Migration does not touch it.

### Smallest demonstrably safe path
Link-model + explicit SchemaMigrationPlan + non-destructive failure + populated-fixture test + device gate. This is larger than a lightweight migration but is the smallest design that satisfies "never delete user data to recover" and "verify counts + file existence." STOP at the Phase 3 device migration gate before any Home/Library UX.

---

## ADDENDUM (2026-10-13) — Phase 1-3 implemented + a separated test-debt finding

**Global Moments schema is implemented and PROVEN correct on device.** A temporary diagnostic in test_happyPath confirmed in the owner's Xcode run: `story.moments.count == 2`, resolvable media == 2, AU fetch == 2 — i.e. the StoryMomentLink model, the computed `story.moments` accessor, and `StoryModel.attach(_:)` all resolve correctly. `GlobalMomentsPersistenceTests` (10 tests) cover standalone create, reuse across Stories, Story-delete-preserves-Moment+media, remove-from-one-Story, library delete, dup prevention, ordering, AU survival, output ownership.

Commits (app repo, NOT pushed): d2b178f (non-destructive migration failure), 77c4ab3 (schema + tests), 6a6578a / 8cdc992 / 9f981de / a4ef968 (compile fixes, incl. pre-existing stale tests), b49ee46 (attach() in-memory inverse), 2b2b58e (EditPlanJobClienting protocol + FakeJobClient + StoryCreationCoordinatorTests rewired).

**SEPARATED DEBT — async-rewrite test retrofit (NOT a global-Moments bug):** the earlier async-planning rewrite (c57e6d8, committed "device-acceptance pending") moved planning from the sync planner onto the network EditPlanJobClient but did not update the unit tests. Result: coordinator-driven tests injected a FakePlanner that is no longer on the path, so they stalled in .planning. Fixed in StoryCreationCoordinatorTests (via the new protocol + FakeJobClient). STILL TODO as separate async-rewrite debt:
- `StoryCreationFailureTests` — mechanical: inject FakeJobClient into ~8 constructions + the stateful retry case.
- `StoryDurationFeasibilityTests` — NOT mechanical: its premise ("count planner calls / inspect the target the planner received") is obsolete under async; the call-count + target assertions must move from the planner to the FakeJobClient (submitCount / lastRequest).
Owner decision 2026-10-13: STOP the test retrofit here, proceed to Phase 4 Capture + Library UX, track the above as separate debt.
