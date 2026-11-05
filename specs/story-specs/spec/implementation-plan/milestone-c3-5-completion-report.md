# Milestone C3.5 — Figma UX Convergence: Completion Report

**Date:** 2026-10-02
**Status:** Native build converged to the frozen Figma product shell for A–C
functionality; future surfaces present as intentional disabled/empty states.
**Physical-iPhone acceptance (Phase 6): PENDING — user runs the checklist below.**
No C4.

## 1. Exact Figma artifact used
`prototypes/story-figma/src/App.tsx` (4730 lines, single Figma Make export, git
`ba88526`). No competing version. Supporting: `11-direct-flow.md`,
`02-core-story-schema.md`, `story-production-latest.md`.

## 2. Final screen-by-screen reconciliation
Legend: **R**=MATCHED+REAL · **D**=MATCHED+DISABLED FUTURE · **E**=MATCHED+EMPTY
STATE · **X**=REAL_SYSTEM_EXTENSION.

| Frozen Figma screen/surface | Native SwiftUI | Verdict |
|---|---|---|
| ScreenHome — "What would you like to make?" | HomeView | R |
| Home · Start a Story | HomeView → CreativeDirectionView | R |
| Home · Create now | HomeView (disabled card) | D |
| Home · Use existing photos/videos (analyze) | HomeView (disabled link) | D |
| Home · Your Stories (active-first, completed-below) | HomeView sorted list | R |
| ScreenStoryIntent — describe experience | CreativeDirectionView .describe | R |
| ScreenStoryDirection — how should it feel | CreativeDirectionView .feel (presets) | R |
| …Direction · reference media | .feel (disabled section) | D |
| ScreenStoryContext — "Here's what I understood" | .context (reflects real C1) | R |
| …Context · music direction | .context (disabled section) | D |
| ScreenStoryBlueprint — "what I'll look for" (arc) | .blueprint (neutral unavailable Guide) | D |
| ScreenTMB — persistent Story Home | StoryHomeView | R |
| …Story Home · Shoot a moment | StoryHomeView → ShootMomentView | R |
| …Story Home · Moments list/mosaic | StoryHomeView moment cards | R |
| …Story Home · "+ Add photos or videos" | StoryPhotosPicker (PHPicker) | R |
| …Story Home · Story Guide | neutral StoryUnavailableSection (NOT TMB demo copy) | D |
| …Story Home · Story Idea suggestion | (folded into Guide unavailable) | D |
| …Story Home · Complete Story / Reopen | menu (wired lifecycle) | R |
| …Story Home · status (active/completed) | StoryStatusPill | R |
| Screen3Scene / ScreenTMBShootScene — scan | SceneScanFlowView intro+scanning | R |
| Screen4Thinking / ShootThinking — thinking | SceneScanFlowView planning (staged copy, real 12–16s) | X |
| Screen5Idea / ShootIdea — concept + storyboard | recommendation Concept Card ("Let's shoot") | R |
| …Idea · "Try another idea" | (disabled — Director enhancement/TBD) | D |
| ShotScreen — shot guidance | recommendation card guidance rows | R |
| …Shot · skip scan | (disabled — Director enhancement/TBD) | D |
| CaptureScreen — countdown + record | CameraCaptureView | R |
| (real) rescan_scene decline state | recommendation .rescanScene (Scan again, no camera) | X |
| (real) create_now state | recommendation .createNow (generate disabled) | X |
| Screen8Validation — success/retry | not reachable until C4 wires the loop; tracked DISABLED | D |
| ScreenFinalCapture — "that's everything" + Create | CreateStoryPreviewView entry | R (generate D) |
| ScreenMediaPicker (analyze) + PreMediaResult A/B/C | disabled entry at Home/idea | D |
| ScreenTMBPreview — create preview | CreateStoryPreviewView (grid R; music D) | R |
| Screen10Creating / Screen11Result — generate/output | CreateStoryPreviewView generate = disabled; result = empty | E / D |
| …Result · Save / Version / Change music | (disabled — Edit Planner/Media/Music) | D |
| ScreenTMBMusic + music rows/sheet | disabled sections | D |
| ScreenMoments — manage/remove/add | StoryHomeView moments + PHPicker (remove-from-Story: later) | R (partial) |

**No unexplained native UX omissions.** Every frozen surface is present as R, D, E,
or X and tracked in `ui-capability-matrix.md`.

## 3. Screens rebuilt / added
Rebuilt: HomeView, CreativeDirectionView (→ 4-step wizard), StoryHomeView,
SceneScanFlowView (staged thinking). Added: CreateStoryPreviewView,
StoryPhotosPicker, DesignSystem/{StoryTheme, StoryComponents}.

## 4. Reusable components / tokens added
`StoryTheme` (palette/type/spacing/radii) · StoryPrimaryButton ·
StorySecondaryButton · **StoryUnavailableButton** · **StoryUnavailableSection** ·
StoryCard · GuidanceCard · StoryStatusPill · StorySectionHeader · StoryEyebrow ·
StoryTextField · StoryEmptyState · StoryThinkingState · `storyBackground()`.

## 5. Implemented capabilities wired
Creative Intent (C1), Scene scan (C2), Director recommendation (C3), thinking,
capture→Moment, rescan_scene, Complete/Reopen lifecycle, add-existing-media.

## 6. Disabled capabilities + dependencies
Create now path, Create-My-Story generation + Result (Edit Planner + Media), Music
surfaces (Music Engine), Story Guide/Idea + Blueprint arc (StoryBlueprint), existing-
media analyze (AssetUnderstanding), reference media (reference-ingest), Shot
Validation + retry (C4), Try-another-idea + Skip-scan (Director enhancement/TBD).
All in `ui-capability-matrix.md` with target milestones.

## 7. Real-system extensions added
Director thinking staged copy for real 12–16s latency; rescan_scene decline state;
create_now state with downstream generate disabled.

## 8. Debug surfaces moved
Raw CreativeIntent chips, DirectorDebugPanel (beats/shots/decision/latency/model,
good/bad feedback), and the mock Create output are all `#if DEBUG`. None appear in
the consumer flow.

## 9. Navigation / state fixes
NavigationStack root (Home) → wizard → Story Home → fullScreenCover capture →
Moment. Wizard uses a separate navigate trigger so the Context reflect-back doesn't
auto-advance. SwiftData persistence unchanged — Stories/Moments survive relaunch.

## 10. Physical-iPhone results
PENDING — see acceptance checklist (§ below).

## 11. Screenshots / recording
To be captured during the device run.

## 12. Remaining Figma differences
- **Fonts:** Figma uses Fraunces + DM Sans; the app uses system serif/sans (no
  bundled font files — bundling is a target-config step deferred; tracked).
- Figma's TMB-specific hero mosaic / "Day N of 8" / chapter content is demo
  content; native shows a generic structure (no fake personalized guidance).
- ScreenMoments dedicated manage screen is folded into Story Home for C3.5 (remove-
  from-Story deferred); add + view are present.
- Pixel-level spacing not matched to the micron (per instruction).

## 13. Tests
Backend: 98 pytest green (unchanged — no backend touched). iOS: new
`C35FlowTests` (Complete/Reopen, add-existing-media, decision→UI-state mapping,
Create≠Complete) + existing `DirectorDTOTests`, `StoryFoundationTests`. All changed
Swift files `swiftc -parse` clean. Full XCTest runs in Xcode on device/sim.

## 14. Architecture deviations
None. No change to C1–C3 intelligence, prompts, Director model (Opus 4.5),
contracts, ModelGateway, eval fixtures, or AWS. Pure presentation + two local/
mechanical capabilities (lifecycle status, media import).

## 15. Updated capability matrix
`ui-capability-matrix.md` — Complete Story + add-existing-media flipped to
IMPLEMENTED/WIRED/done (C3.5); Figma-parity column populated; zero unexplained
MISSING (every MISSING carries dependency + milestone).

## 16. Recommendation for C4
Proceed to C4 (Shot Validation + validation-driven Director loop) after the device
acceptance pass. C4 enables the Validation screen (currently tracked DISABLED,
unreachable), wires `/v1/director/next`, and turns Beat-progress live. Its DoD must
flip those matrix rows + enable the Figma surfaces. Keep the DEBUG feedback panel.

---

## Physical-iPhone acceptance checklist (run these; record a screen recording)
1. **Home** shows "What would you like to make?" with Start a Story (active),
   Create now (visibly disabled), Use-existing (disabled). Looks like the Figma
   product, not the old skeleton.
2. **Start a Story** runs the 4-step wizard: describe → feel (presets) →
   "Here's what I understood" (real resolved intent) → "what I'll look for"
   (Story Guide shown as a neutral coming-later state) → Start Story.
3. **Story Home** shows the Story summary (NOT raw intent chips), status pill,
   Moments, Shoot a moment, Create my Story, and a "•••" menu.
4. **Shoot a moment** → scan → "Looking at your scene…" → Director thinking that
   evolves through staged lines over the real ~12–16s.
5. **capture_shot** → Concept Card (title + description + "N shots · ~X sec" +
   instruction + Subject/You/Hold) with **"Let's shoot"**.
6. **Let's shoot → Open Camera → record → Moment** appears back in Story Home.
7. **rescan_scene** (scan an unrelated scene for a specific Story) → "This scene
   doesn't quite fit your Story" + **Scan again**, and **NO Open Camera**.
8. **Add photos or videos** on Story Home opens the system picker and the picked
   clips appear as Moments.
9. **••• → Complete Story** moves it to completed (status pill flips); it sorts
   below active Stories on Home; **Reopen** restores it.
10. **Create my Story** opens the preview with the media grid; the generate action
    is visibly disabled (not fake); music section visibly disabled.
11. **Back/cancel** at every step returns correctly; the Story persists.
12. **Background/relaunch** the app → the Story and its Moments are still there.
13. **Future surfaces** (Create now, music, Story Guide, generation, reference) are
    visible in their Figma locations but clearly disabled — no fake output anywhere.
14. **No raw AI/debug** (SceneUnderstanding fields, beats/shots, decision enum,
    latency, model) appears anywhere in the normal (Release) consumer flow.
15. **DEBUG build** still shows the Director feedback panel + diagnostics for eval.
