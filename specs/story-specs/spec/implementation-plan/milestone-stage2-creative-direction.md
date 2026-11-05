# Milestone — Stage 2 Creative Direction (Final Customize screen)

Status: **IMPLEMENTED (iOS-only), awaiting iPhone device acceptance. STOP at device gate.**
Nothing pushed or deployed publicly. No frozen prompt / EditPlan/2 contract changes.

## Problem / correction

A prior interpretation put Moment-specific editing instructions on **Stage 1 (Start a Story)**. The owner
clarified there are THREE input stages:

- **Stage 1 — Start a Story**: general experience description → CreativeIntent. MUST NOT carry Moment-specific
  editing instructions or a Moment picker.
- **Stage 2 — Customize Your Story**: shown AFTER Moments are collected, BEFORE the first video. This is where
  optional **Creative Direction** belongs (NL + typed Moment refs + visual picker). Generates a NEW video from
  all eligible Moments as candidates, applying the directives during INITIAL planning — NOT via the Stage 3
  revise engine.
- **Stage 3 — Post-generation Revision**: starts from the selected version's exact EditPlan, targeted changes.

## What already existed (reused, not rebuilt)

- `MomentReferenceResolver` — the ONE deterministic interpreter: `StoryMomentNumbering` snapshot, `parseTyped`,
  `parseOrdering`, `parseImplicitFollow`, `resolve` → `ResolvedDirectives` keyed by STABLE Moment UUIDs.
- `MomentReferencePicker` + `MomentReferenceChipRow` — the ONE visual picker + chips.
- `StoryModel.creativeDirectivesJSON` — persisted resolved UUIDs.
- `composeRevisionContext` — folds directives into the initial create request.
- `beginRun` — sends `visual_first` + contact sheets + directives on the initial create (multimodal preserved).

## Changes (this milestone)

1. **Stage 1 stripped** (`CreativeDirectionView`): removed the Moment-reference picker, chips, resolver,
   clarification, and the four `@State` fields; `confirmStart()` no longer persists directives. Describe step is
   description + title only. Seeded Library Moments are still attached in `resolve()`. Applies to both
   Home→Start and Library→Start.
2. **Stage 2 Creative Direction** (`CustomizeYourStoryView`): optional section (shown when `numbering.count > 0`)
   — NL field + "Add Moment reference" picker + UUID-backed chips + inline clarification. Reuses the SAME
   resolver + picker. On Create, resolves typed + chip + ordering refs against the stable snapshot and
   **blocks submission on unresolved hard references** (never silently dropped).
3. **Hard + soft forwarding**: `onCreate` returns `ResolvedDirectives?` + soft text + chip ids + a parsed
   `ParsedMusicIntent`. `acceptCustomize` persists `creativeDirectivesJSON` (hard) + new `creativeDirectionText`
   (soft draft). `composeRevisionContext` now folds BOTH `directives` and `soft_direction`.
4. **One-time scoping** (`composeRevisionContext(operationType:)`): the persisted Stage 2 instructions fold ONLY
   for `operationType == "original"`. "Create Another Version" (explore) and "Revise" (own directives) never
   inherit them; a retry of the original correctly re-applies them.
5. **Draft persistence**: `StoryModel.creativeDirectionText` (optional, nil-default) + resolved chip ids survive
   navigation and failed generation; the sheet repopulates. Empty input ⇒ request byte-identical to today.
   `intentText` (factual description) is never overwritten.

## Narrowly-scoped music routing (Music-Routing amendment)

The iOS interpreter (`MomentReferenceResolver`) had **no music-intent output** — reported limitation. Smallest
additive extension: a deterministic `parseMusicIntent` in the same resolver (NOT a second parser system, NOT an
AI pass).

- Separates three disjoint concerns:
  - **music preference** (explicit genre/mood words + a required music CONTEXT word like "music"/"soundtrack")
    → routed to **MusicPlan** via `MusicDirectionCoordinator`.
  - **beat-sync** ("match the cuts to the music", "on the beat") → stays in `soft_direction` for the EDIT
    planner only; NEVER changes soundtrack selection.
  - everything else (pacing, Moment order) → edit planner only.
- **No fabrication**: a visual word ("faster", "striking", "energetic opening") never produces a music
  preference — a music-context word is required ("energetic *soundtrack*" yes; "energetic *opening*" no).
- **MusicDirection authority**: a user-authored direction is NEVER silently overwritten. A material conflict
  (requested moods not already covered) is surfaced as an advisory ("kept your earlier choice"); when no
  user-authored direction exists, the deliberate Stage 2 preference becomes the authored direction.
- **Cache**: setting MusicDirection regenerates nothing (AU/Guide/Coverage independent); it only bumps the
  fingerprint a future MusicPlan cache compares.

## Tests

`StoryTests/MomentReferenceResolverTests.swift` → new `MusicIntentRoutingTests` covering music-routing tests
1–5, 8, 10 at the classifier boundary (visual≠music, beat-sync≠preference, gentle-acoustic/energetic-electronic
preferences, mixed separation, empty/visual preserve behavior, beat-alignment variants, music-context-word
guard). SwiftData authority/cache (tests 6/9) enforced in `MusicDirectionCoordinator` (no overwrite of an
authored row; music-only change regenerates nothing). Resolver, view, coordinator, and call-site all
`swiftc -parse` clean.

## Files

- `apps/ios/Story/Story/Features/Create/CustomizeYourStoryView.swift`
- `apps/ios/Story/Story/Features/StoryHome/CreateStoryPreviewView.swift`
- `apps/ios/Story/Story/Domain/Creation/StoryCreationCoordinator.swift`
- `apps/ios/Story/Story/Features/StartStory/CreativeDirectionView.swift`
- `apps/ios/Story/Story/Domain/Creation/MomentReferenceResolver.swift`
- `apps/ios/Story/Story/Data/Persistence/Models.swift`
- `apps/ios/Story/StoryTests/MomentReferenceResolverTests.swift`

## Device acceptance (pending)

Both entry paths (Home→Start, Library→Start). Full flow: Start → Collect/Select → Customize → Create → Revise →
Save/Share. Confirm Stage 2 is the ONLY pre-generation screen with Moment-specific editorial instructions;
Library Moments stay attached; typed+chip refs resolve; unresolved blocks; hard+soft reach initial plan; a music
preference reaches MusicPlan while a user-authored direction is preserved; beat-sync doesn't change the track;
draft survives nav/failed gen; empty input unchanged; Create-Another-Version doesn't inherit; revision
unaffected.
