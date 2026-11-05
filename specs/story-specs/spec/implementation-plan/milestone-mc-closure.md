# Milestone M-c — CLOSURE (MusicDirection inference + Figma MUSIC integration)

**Status: CLOSED — provisionally accepted on physical iPhone (2026-10-07).** No track provider, no
catalog, no MusicAnalysis, no audio infrastructure, no Edit Planner. Create My Story stays disabled.

## Device acceptance (owner, physical iPhone)
Observed working: music summary on the Creative Intent confirmation ("Here's what I understood"), the
Change interaction, mood-chip selection, custom description, and integration into the existing Story
wizard. Two UX issues found in the first recording were fixed and re-accepted:
- Row rendered a single lowercase tag ("intimate") → now title-cases the joined feel ("Emotional ·
  Intimate"), falls back to the inferred summary when no tags.
- Change sheet pre-selection didn't match the row (non-chip inferred tags dropped) → added
  `inferredToChip` so the sheet pre-selects the chips corresponding to the inferred feel. Row, sheet,
  and saved edit now share one vocabulary.
Fix commit: `69d7225`.

## Closure checks (each backed by code/test)
1. **Persist across relaunch** — `StoryMusicDirectionModel` (SwiftData, `@Attribute(.unique) storyId`);
   test `testPersistedDirectionReturnedWithoutInference` (fresh coordinator over same store returns it).
2. **Summary reflects authoritative selection** — the row reads the persisted direction via
   `MusicDirectionCoordinator.direction(for:)`; user edit (`save(userEdit:)`) is what the row shows.
3. **Override not silently replaced** — `testUserOverrideNeverOverwrittenByInference`: after a user edit,
   `ensure()` returns the user's choice and never calls infer (`userAuthored` guard; `fake.calls == 0`).
4. **Changing MusicDirection does NOT regenerate StoryGuide/StoryCoverage** — the coordinator provably
   touches neither (it only persists the direction + bumps `fingerprint`); CreativeIntent/Guide/Coverage/
   MomentUnderstanding are independent.
5. **Future MusicPlan consumes the current MusicDirection** — `fingerprint(for:)` is the staleness seam a
   future MusicPlan cache compares against; `testFingerprintChangesWithDirection` proves it changes on edit.
   (MusicPlan is not persisted yet — M-b froze the contract only — so this is the designed hook, not a live
   cache.)
6. **Unimplemented playback/catalog disabled** — the Change sheet shows a disabled "Choose a track —
   Track selection and preview aren't available yet." section in place.

## Tests
Backend 7 (`test_music_direction.py`), full backend suite 156 pass. iOS 8
(`MusicDirectionTests.swift`) + `swiftc -parse` clean. NOT verified: full Xcode build / XCTest run on CI
(owner verified on device instead).

## Commits
app `61d6448` (backend engine + endpoint), `c395f4e` (iOS layer), `69d7225` (UX fix). specs `5f184e9`
(impl record) + this closure note.

## Deployed
`/v1/music-direction` live on the dev App Runner (verified). No material M-c blocker remains → M-d proceeds.
