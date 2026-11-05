# Milestone — MVP Customize UX: Editing Approach Selection

Status: **IMPLEMENTED (iOS-only), physical-device acceptance pending.** No backend/contract/prompt change.
Nothing pushed or deployed.

## Owner decision
Expose a user-visible **Editing Approach** choice on the existing *Customize Your Story* screen, surfacing the
two creative approaches from the editing experiments. MVP UX + wiring — not a model experiment.

## What shipped (iOS)

### Phase 1 — UX
New **Editing approach** section on `CustomizeYourStoryView`, after *Story Length* and *Sound* — subtitle
"How should Story choose and arrange your footage?". Two whole-row cards (dark theme, gold selected
border/checkmark, icon + description + a gold supporting line), matching the Figma mock:
- **Storytelling** — "Build a meaningful story from your moments, with a clear beginning, progression, and
  ending." · *Faster · Uses video descriptions*
- **Visual-first** — "Look across your footage to find striking visuals, expressive moments, and compelling
  sequences." · *More visual analysis · May take longer*

Footer line: "Both approaches preserve your chosen length, music, and original sounds." No third option, no
model/endpoint/token jargon (unit-tested), no new onboarding flow.

### Phase 2 — Persistence
`StoryModel.editingApproachExplicit: String?` — additive, optional, defaulted nil (SwiftData migration-safe;
existing Stories decode to the default via `EditingApproach.fromRaw`). Independent of Length + Sound. Set
ONLY by `acceptCustomize`, so retries / recreation / version generation never overwrite it. Allowed values
`storytelling` | `visual_first`.

### Phase 3 — Routing
`StoryCreationCoordinator.run` routes on the REQUESTED approach **gated by the deployment flag**:
`wantMultimodal = requested.requiresMultimodal && StoryMultimodalPlanning.enabled`.
- Storytelling → frozen text-only `/v1/edit-plan`.
- Visual-first → `/v1/edit-plan-mm` (reusing the existing visual budget + graceful text-only fallback).
Frozen prompts, EditPlan/2, MusicPlan, audio mixing, Media Engine all unchanged.

The flag stays the safety gate on BOTH ends: the Customize UI only OFFERS Visual-first when the flag is on
(`visualFirstAvailable: StoryMultimodalPlanning.enabled`), AND the coordinator defends again (a `visual_first`
persisted from a prior enabled build will NOT force multimodal if the flag is now off).

### Phase 4 — Fallback transparency
`StoryPlanningDiagnostics` now carries `requestedApproach` vs `actualApproach`. When Visual-first falls back to
text-only (image-input failure, or flag off), `requested` stays `.visualFirst` but `actual` becomes
`.storytelling` and `usedMultimodal=false` — we never claim visual analysis that did not happen. The create is
never failed when the safe text-only fallback can still produce a valid edit. The on-device beacon emits
`editplan: req=… actual=… mm=… …` for CloudWatch verification without an attached debugger.

### Phase 5 — Tests
`EditingApproachTests` (pure logic): wire values, default, migration-safe decode (nil/empty/unknown → default),
routing flag, non-technical-copy invariant, spec-exact copy. Backend suite unaffected (40/40, no backend
change). SwiftData `@Model` + full UI type-check remain Xcode-only (sandbox blocks the macro plugin); all
changed files are `swiftc -parse` clean.

## Phase 6 — physical-device acceptance (PENDING, owner)
On iPhone: create girl_with_dress with Storytelling, then Visual-first (same footage/duration); confirm the two
planning paths from diagnostics (`editplan:` beacon req/actual + `planning_mode`), both playable, Visual-first
sheets actually transmitted (`sheet_count>0`), music/native-audio/orientation preserved, and the selected
approach persists after reopening.

## Files
- `apps/ios/Story/Story/Domain/Creation/EditingApproach.swift` (new)
- `apps/ios/Story/Story/Domain/Creation/StoryMultimodalPlanning.swift` (diagnostics req/actual)
- `apps/ios/Story/Story/Features/Create/CustomizeYourStoryView.swift` (Section C)
- `apps/ios/Story/Story/Features/StoryHome/CreateStoryPreviewView.swift` (acceptCustomize + call site)
- `apps/ios/Story/Story/Domain/Creation/StoryCreationCoordinator.swift` (routing + transparency)
- `apps/ios/Story/Story/Data/Persistence/Models.swift` (persisted field + accessor)
- `apps/ios/Story/StoryTests/EditingApproachTests.swift` (new)

## Remaining MVP blockers
- Physical-device acceptance (Phase 6).
- The multimodal flag default is still OFF — Visual-first is only offered once the flag is enabled (its own
  default-ON decision is tracked in the integration milestone).
- Bedrock daily-token-quota pressure makes Visual-first (image-heavy) latency spike / fall back under load — an
  operational limit, not a code blocker.
