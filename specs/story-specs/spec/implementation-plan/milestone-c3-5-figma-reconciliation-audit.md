# C3.5 Phase 1 — Figma → SwiftUI Reconciliation Audit

**Frozen Figma artifact (identified, unambiguous):**
`prototypes/story-figma/src/App.tsx` — 4730 lines, single Figma Make export, one
git history (`ba88526`), `.figma/make/site.json` is a config stub only. **No
competing version → no STOP-for-ambiguity needed.**
Supporting frozen specs: `11-direct-flow.md`, `02-core-story-schema.md`,
`story-production-latest.md`.

**Current SwiftUI (engineering skeleton):** `CreativeDirectionView`,
`StoryHomeView`, `ShootMomentView`, `SceneScanFlowView`, `DirectorDebugPanel`,
`HomeView`, + domain/services (StoryUseCases, services, SwiftData). ~6 screens vs
the frozen product's ~25 consumer screens + lifecycle.

## Reconciliation table

| Figma screen/state/action | Current SwiftUI equivalent | Capability | UX status | Required action |
|---|---|---|---|---|
| ScreenHome (no-Story: Create now / Start a Story / Use existing) | HomeView (basic list) | PARTIAL | ENGINEERING_SCAFFOLD | REBUILD_TO_FIGMA |
| ScreenHome (active-Story: Continue hero, Your Stories, completed sort) | — | NOT_IMPLEMENTED | MISSING | ADD (Continue hero WIRED; completed-sort WIRE-if-cheap) |
| Screen1Intent (Create-now intent: vibe grid, reference, text, music row) | CreativeDirectionView (title+text only) | PARTIAL (text→C1 real) | ENGINEERING_SCAFFOLD | REBUILD_TO_FIGMA (vibe grid + text WIRED; reference/music DISABLE) |
| ScreenStoryIntent / Direction / Context / Blueprint (Start-a-Story wizard) | folded into CreativeDirectionView | PARTIAL (intent real; context reflect real; blueprint none) | MISSING | ADD (wizard; intent/context WIRED; blueprint arc DISABLED static) |
| Screen3Scene / ScreenTMBShootScene (scan) | SceneScanFlowView intro+scanning | IMPLEMENTED | PARTIAL | REBUILD_TO_FIGMA (viewfinder framing, copy) |
| Screen4Thinking / ScreenTMBShootThinking | SceneScanFlowView .analyzing/.planning | IMPLEMENTED | NEW_REAL_SYSTEM_STATE | REAL_SYSTEM_EXTENSION (staged copy for real 12–16s) |
| Screen5Idea / ScreenTMBShootIdea (concept + storyboard + Let's shoot / Try another) | SceneScanFlowView .recommendation (Concept Card) | IMPLEMENTED (Try-another NOT) | PARTIAL | REBUILD_TO_FIGMA (match card; Try another idea DISABLE) |
| ShotScreen (shot guidance, Ready, Skip) | folded into recommendation card | IMPLEMENTED (skip NOT) | PARTIAL | REBUILD_TO_FIGMA (skip DISABLE) |
| CaptureScreen (countdown + record) | CameraCaptureView | IMPLEMENTED | MATCHES (native camera) | KEEP (align chrome) |
| Screen8Validation (success/retry) | — | NOT_IMPLEMENTED | MISSING | ADD DISABLED (C4) |
| ScreenFinalCapture (Got it / Create my Story / music) | dismiss → StoryHome | PARTIAL | MISSING | ADD (Create wired-or-disabled; music DISABLE) |
| rescan_scene state | SceneScanFlowView .recommendation(rescan) | IMPLEMENTED | NEW_REAL_SYSTEM_STATE | KEEP (Scan again, no camera — already correct) |
| create_now state | SceneScanFlowView .recommendation(createNow) | PARTIAL | NEW_REAL_SYSTEM_STATE | KEEP + DISABLE downstream generate |
| ScreenTMB (persistent Story Home: status, mosaic, Shoot, Create, Story Idea, Guide, menu) | StoryHomeView (summary, chips, moments, Shoot, Create) | PARTIAL | ENGINEERING_SCAFFOLD | REBUILD_TO_FIGMA (Shoot/Create/Moments WIRED; Complete Story WIRED C3.5; Story Idea + Guide neutral-unavailable, NOT TMB copy) |
| ScreenTMBLooked / ScreenTMBReady (enough-captured prompts) | — | NOT_IMPLEMENTED | MISSING | ADD (map to create_now semantics; generation DISABLED) |
| ScreenMoments (manage, remove-from-Story, add) | inline MomentRow list | PARTIAL | ENGINEERING_SCAFFOLD | REBUILD_TO_FIGMA (grid, remove-from-Story WIRED; add-media per below) |
| ScreenMediaPicker (analyze mode) + PreMediaResult A/B/C | — | NOT_IMPLEMENTED | MISSING | ADD DISABLED entry (AssetUnderstanding) |
| ScreenMediaPicker (add mode) | — | PARTIAL | MISSING | ADD + WIRE (C3.5: PHPicker append to Moments) |
| ScreenTMBPreview (create preview: media grid, music, Create) | — | NOT_IMPLEMENTED | MISSING | ADD (grid WIRED; Create DISABLED; music DISABLE) |
| Screen10Creating / Screen11Result (generate + output) | createStoryOutput mock + outputs list | NOT_IMPLEMENTED (mock) | ENGINEERING_SCAFFOLD | REBUILD_TO_FIGMA EMPTY_STATE; mock → DEBUG_ONLY; Save/Version/Share DISABLE |
| ScreenTMBMusic + Music rows/sheet | — | NOT_IMPLEMENTED | MISSING | ADD DISABLED (Music Engine) |
| Complete Story / Reopen (menu) | status enum only | PARTIAL | MISSING | ADD + WIRE (C3.5: local status flip + completed-sort) |
| "What Story understood" raw chips | StoryHomeView IntentChips (#if DEBUG now) | IMPLEMENTED | ENGINEERING_SCAFFOLD | MOVE_TO_DEBUG (done) |
| Director debug panel (beats/shots/decision/latency/model, good/bad) | DirectorDebugPanel (#if DEBUG) | IMPLEMENTED | — | KEEP (DEBUG) + extend per §7 |

## Real-system extensions (not in frozen Figma — handle minimally, no redesign)
1. **Director thinking at real 12–16s** — staged copy ("Looking at your scene…" →
   "Finding what matters…" → "Finding a shot worth capturing…"), no fake %.
2. **rescan_scene** — first-class decline state, "This scene doesn't quite fit your
   Story" + Scan again, NO camera. (Already built.)
3. **create_now at C3** — Director may stop; downstream generation is not built, so
   present the Figma "enough captured" surface with the generate action DISABLED.

## Proposed SwiftUI component map (small Story design system — only reused patterns)
`StoryTheme` (colors: ink #0a0a0b, gold #d4a853, cream #f5f0e8; Fraunces/DM-Sans
type scale; spacing/radius tokens) · `PrimaryButton` · `SecondaryButton` ·
`DisabledActionButton` (consistent "coming soon" affordance) · `StoryCard` ·
`MomentCard` · `SectionHeader` · `StatusPill` (active/completed) · `InputField` ·
`MediaThumbnail` · `GuidanceCard` (concept/shot) · `ThinkingState` (staged copy) ·
`EmptyState` · `NavBar` treatment. (Not a generic framework — only these.)

## Files expected to change / be added
- CHANGE: `HomeView`, `CreativeDirectionView`, `StoryHomeView`, `SceneScanFlowView`,
  `ShootMomentView`, `DirectorDebugPanel`.
- ADD (views): StartStory wizard (Intent/Direction/Context/Blueprint), Moments,
  MediaPicker (disabled analyze), TMBPreview/Create, Creating/Result (empty),
  Music (disabled), Validation (disabled), FinalCapture.
- ADD (design system): `DesignSystem/StoryTheme.swift` + the components above.
- UNCHANGED (do not touch): all `packages/*`, `contracts/*`, prompts, model
  gateway, eval fixtures, AWS — presentation only.

## Findings to report BEFORE Phase 2 (per §18 stop conditions)
- **No ambiguous Figma version.** Single artifact. OK to proceed.
- **No frozen-contract change required.** The whole milestone is presentation +
  disabled-surface shells; domain/contracts/engines are untouched. OK to proceed.
- **Product-semantic note (not a blocker, confirm):** the Figma persistent-Story
  home is heavily TMB-hardcoded (chapters, guide categories, mosaic images). We
  implement the *structure* generically off the real StoryModel; the Story
  Guide/Story Idea are rendered in a **neutral, clearly unavailable state** (NOT
  the TMB demonstration copy, which is not production-generated content). Flagging
  so "Story Guide shows a coming-soon state" is understood as intended, not a miss.
- **Scope reality:** this is ~15–20 new/rebuilt SwiftUI screens. Large but
  mechanical; no AI/architecture work. Proposed to execute Phases 2→5 then the
  physical-iPhone pass (Phase 6, user-run).

Phases 2–6 proceed on approval of this audit.
