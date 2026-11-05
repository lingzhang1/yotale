# Milestone D §13 — Photos Persistence (independent product-safety task)

**Status: IMPLEMENTED, isolated, migration-free.** This is independent of AU model
selection and was done in parallel with the AU ground-truth gate. iOS-only; no
backend, no canonical contract, no schema migration.

## Current behaviour (verified by reading the code)

- `MediaStore` (`apps/ios/Story/Story/Media/Playback/MediaStore.swift`) is the only
  media mapper. DIRECT captures are persisted at **`<App Documents>/media/<uuid>.mov`**
  via `adoptCapturedFile(tempURL:)`, called from `persistMoment(...)` in
  `SceneScanFlowView.swift`. Originals stay on device; nothing uploads or writes a
  cloud URL.
- **Do Story captures appear in Photos?** No — before this change, captures existed
  ONLY under the app's Documents container.
- **Could deleting Story/the app lose the only copy?** Yes — the `<Documents>/media`
  tree is inside the app sandbox; deleting the app deletes it. That was the trust risk.
- **Backup semantics of the chosen local directory:** `<Documents>` is included in
  iCloud/iTunes device backup (not excluded), so a restored device keeps the Story
  copy — but that is backup, not user-visible ownership, and it is gone if the app is
  deleted without a restore.

## Change implemented (smallest isolated form)

1. **New `PhotosSaver`** (`apps/ios/Story/Story/Media/Photos/PhotosSaver.swift`):
   add-only (`PHAccessLevel.addOnly`) save of a **copy** of the captured original into
   Apple Photos. Never requests read/full access. Returns a typed `PhotosSaveOutcome`
   (`saved` / `permissionDenied` / `failed` / `skipped`).
2. **Hook in `persistMoment`**: after the Moment is **already persisted**, fire-and-forget
   `PhotosSaver.saveVideoCopy(at: adoptedURL)`. Moment creation does NOT depend on it;
   denial/failure is logged and the Story working copy is untouched.
3. **`NSPhotoLibraryAddUsageDescription`** added to both build configs in `project.pbxproj`
   (the existing `NSPhotoLibraryUsageDescription` covers the separate import picker).

### Requirements check (§13)
- Moment creation independent of Photos permission — **yes** (save runs after persist). ✓
- Photos denial/failure degrades gracefully — **yes** (typed outcome, logged, no throw). ✓
- No full read permission — **yes** (`.addOnly` only). ✓
- Duplicate storage accepted for MVP — **yes** (Photos copy + Story working copy). ✓
- Story working copy never deleted — **yes** (untouched). ✓
- Imported media out of scope — **yes** (only the direct-capture `persistMoment` path calls it). ✓
- Not entangled with AU model selection — **yes** (separate module, separate commit). ✓

### Recording Photos-save state locally — deliberate deferral
§13 says record save state "where useful". Persisting a `savedToPhotos` flag on the
Moment is a **SwiftData schema migration**, which is outside "smallest isolated change"
and would couple to the persistence layer. For MVP the outcome is logged only. **Follow-up
(flagged, not done):** add an optional `photosSaveState` field when a consumer needs it
(e.g. a UI "saved to Photos" badge or a retry queue). Not required for the trust fix.

## Xcode wiring — RESOLVED (no manual edit needed)
**Correction (2026-10-05):** the earlier "add the new file to the Xcode project" open item (for
both `PhotosSaver.swift` and `StoryContracts.swift`) was based on the classic explicit-reference
project format. This project is actually **objectVersion 77 with
`PBXFileSystemSynchronizedRootGroup`** (the `Story/` folder is synchronized; the pbxproj has
**zero** explicit `.swift` references and the only membership exception is `Info.plist`). Every
`.swift` under `Story/` — including `Story/Media/Photos/PhotosSaver.swift` and
`Story/Data/Contracts/StoryContracts.swift` — is **auto-included in the target and compiles with
no pbxproj edit**. No manual Xcode file-graph change is required or should be made.
`swiftc -parse` is clean on the new file and the modified flow.

The only remaining step is the **physical-iPhone verification** (checklist below) — which only
the user can run.

## Recommended eventual Photos-save behaviour
Add-only auto-save of the original on successful capture is the right default (implemented).
When the user denies, keep working silently; optionally surface a one-time, dismissible
"Story isn't saving to your Photos" hint (not a blocking prompt). Do not mirror imported
media (it already lives in Photos). Duplicate-storage is acceptable; if storage pressure
becomes real later, offer an opt-in "keep only in Photos" mode — a bigger design, not MVP.

### Delete semantics (what the user can trust)
- Delete the **Photos copy** → Story copy remains; Story keeps working. (Independent copies.)
- Delete the **Story Moment / the app** → the Photos copy remains, user-owned. The footage
  is no longer "an invisible Story-only holder" — that is the whole point of the change.

## Physical-iPhone checklist
1. Capture a Moment (Start Scan → recommendation → Let's shoot → record; or Skip Scan → record).
2. Moment appears in Story (Story Home shows the new Moment).
3. The original appears in **Apple Photos** (Recents) shortly after.
4. Airplane / offline: capture still works, Moment saves, Photos save still works
   (Photos is local — no network needed).
5. Photos **add permission denied**: Moment still created; no crash; a "Photos copy not
   saved: permissionDenied" log line; no Photos copy.
6. Photos **save failure** (simulate by denying mid-flow / storage full): Moment still
   created; `failed(...)` logged; Story copy intact.
7. App **relaunch**: the Moment and its Story working copy are still present and playable.
8. Story copy remains usable after deleting the **Photos** copy.
9. Photos copy remains user-owned after deleting the **Story** Moment.
