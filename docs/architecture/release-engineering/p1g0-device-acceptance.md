# P1-G0 — iOS build + device acceptance checklist (owner-run)

**Status: NOT RUN. iOS is not verified until the owner confirms every row.** The sandbox cannot compile the project
(`xcodebuild` fails on the Swift macro plugin; `swiftc -parse` is clean but is not a build). The authoritative gate is
your Xcode build + ⌘U.

## 0. Setup
1. Main worktree is on `fix/prebeta-release-config-gates` (the branch Xcode builds). Your uncommitted `project.pbxproj`,
   `Story.xcscheme`, `StoryHomeView.swift` whitespace are untouched and still local.
2. Because the *committed* `Story` scheme no longer carries identity/flags, your **local** scheme (still has beta rows) will
   keep working as before. For the clean path use scheme **Story** (dev) and **Story (Beta)** (beta) with NO env rows.
3. Product ▸ Clean Build Folder. Confirm the build id/branch (`git branch --show-current`, `git log -1 --oneline`).

## 1. ⌘U (unit tests) — expect green
New/changed: `ReleaseConfigDefaultsTests` (4), `EditorialTypeSemanticsTests`, `CreateUXP1DTests`, `SceneVideoTests`,
`StoryCreationCoordinatorTests` (v5.3 request still carries editorial_type + rich AU fields **with no flag**).
If the pre-existing `MediaStore.shared.fileExists` P1-D failure appears, it is unrelated (byte-identical files).

## 2. Device scenarios (Run via Xcode, then ALSO relaunch from the home screen — detached)
| # | Scenario | Pass criteria |
|---|---|---|
| 1 | Upgrade-in-place: install over an existing build with Stories/Moments | All Stories and Moments load; no migration error |
| 2 | Existing video versions | Old versions open and play; version history intact |
| 3 | Highlights Create, **no scheme env rows** | Succeeds; output stamped Highlights; plan has editorial evidence |
| 4 | Full Story Create, no env rows | Succeeds; stamped Full Story |
| 5 | Cached AU evidence | Second create on same Moments shows cache hits (`evidence prep: … cacheHit>0` in Console subsystem `ai.yotale.story`) |
| 6 | Cache-miss fallback | Fresh Moment / cleared cache still produces a plan (no failure) |
| 7 | Guide v2 + Scene Images | Shooting-script scene cards render with reference images |
| 8 | Revise and Create Another Version | Both complete; Explore is a single planning call (no critique) |
| 9 | Detached launch | Kill app, launch from home screen: all of 3–8 behave identically |
| 10 | Beta build (Story (Beta)) | Signs in against pool `us-east-1_3cPNfbrUl`, API `asxtxgjiis…`; no Xcode attachment needed |
| 11 | Dev build (Story) | Signs in against `us-east-1_AzfHOEdA5`, API `ydmju5wdps…` |
| 12 | Apple Sign In | Button NOT shown (baked `0`, no Apple IdP on either pool) |

Diagnostics: Console.app ▸ filter `subsystem:ai.yotale.story` (breadcrumbs are private/redacted off-device). A missing
line is not proof a feature is off.

## 3. Owner acceptance record (fill in)
Build/commit tested: ______  ⌘U result: ______  Rows 1–12: ______  Signed off by/date: ______
