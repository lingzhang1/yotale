# Milestone — Capture: AI-Ideas Persistence + Unified Story Creation

**Status:** ACCEPTED — physically verified on iPhone 2026-10-14; Capture Anywhere UX milestone CLOSED.
**Nothing pushed/deployed; local commits only.** Follows `milestone-capture-anywhere-ux-corrections.md`.

## Scope

Five bounded fixes before final Capture Anywhere acceptance. No Home redesign, no change to global
Moments ownership, no new creation pipeline.

## Root causes & fixes

1. **AI ideas disappeared when recording began.** Root cause: the record-start handler *cleared*
   `ideas/ideasOutput/ideaIndex`. Fix (Phase 1): ideas now live in session state and SURVIVE record/stop.
   Record-start **collapses** the full card (`ideasCollapsed = true`) instead of clearing; a monotonic
   `aiGeneration` token still cancels in-flight scans and drops stale Director responses so they never
   replace newer ideas or reopen an overlay over a live recording. A top-right **"✦ Ideas" chip** reopens
   the cached ideas with **no new inference** (`reopenIdeas()`); **Next idea** cycles cached suggestions;
   **Rescan** is the only path that refreshes scene evidence — so old ideas are never silently presented
   as a newly-scanned scene. Session-only; no schema change.
2. **Camera controls cluttered.** Fix (Phase 2): removed **"Let's shoot"** and the redundant Cancel from
   the idea-ready card; the red record/stop button is always authoritative. States: idle (Record + AI
   Ideas) · scanning/thinking (Record + "Cancel AI request") · idea ready (Record + Next idea + Rescan +
   Dismiss) · recording (Stop + REC/mm:ss timer + optional one-line idea reminder; full card hidden).
3. **Create Story from Moments bypassed setup.** Root cause: `createStoryFromSelection()` minted a generic
   "New Story" and jumped to its detail. Fix (Phase 3): Library → Select → **existing Start-a-Story setup**
   (`CreativeDirectionView(seedMoments:)`) → Story detail. Same wizard as Home (one pipeline). The Story is
   created **once** on confirm; seeded Moments are linked in order (no media dup). Cancelling the wizard
   before confirmation deletes the unconfirmed Story (`deleteStory`, which cascades links/outputs but leaves
   independent Moments + media intact) — **no orphan Story**.
4. **User intent could be overwritten.** Fix (Phase 4): verified + tested that adding/importing Moments
   (`addExistingMoments`, `addExistingMedia`, `shootMoment`) never touches `title`/`intentRawText`/
   `intentSummary`. AI StoryGuide/suggestions may still update from new evidence; user-authored fields are
   left as the user wrote them.
5. **Import feedback ambiguous.** Fix (Phase 5): `ImportProgress.Phase` (preparing / importing / analyzing)
   drives operation-specific banner copy ("Preparing selected media…", "Importing… (k of N)", "Analyzing
   moments…"). No fabricated percentages; never reports success until files + records are persisted;
   partial-failure copy preserved.

## Phase 6 — tests (`CaptureUXCorrectionsTests`, extended)

`deleteStory` keeps independent Moments + media; seed→setup→confirm creates exactly one Story and links
without media dup; adding Moments preserves user-authored title/description/summary; import-copy phase
strings (honest, no %, no false success); AI `nextIdea`/`hasCachedIdeas` guards. Camera/AVFoundation and
SwiftUI-presentation items are device-only (Phase 7).

## Commits (local, on the UX-corrections base)

- `a2cd04b` — Phases 1–6 (AI persistence, control simplification, unified creation, intent preservation,
  import feedback, tests).

Frozen prompts/contracts untouched. Nothing pushed or deployed.

## Phase 7 — device acceptance (owner-gated)

A generate ideas · B record · C reopen same ideas (no scan) · D record again, ideas remain · E Rescan →
ideas update · F no "Let's shoot", record always available · G–K Moments→Create Story opens setup, custom
name/description, confirm links selected, cancel leaves no orphan · L add Moments to a Story keeps
title/description · M generation/music/native-audio/save/share intact.

## Closure (2026-10-14)

Owner confirmed Capture Anywhere is complete and physically verified on iPhone across: standalone +
Story-associated continuous capture; AI shot ideas (scan progress + proactive end) persisting across
record/stop and reopening without re-inference; unified Add Moments (From Story Moments | From iPhone
Photos); context-aware Moments Library; and unified Story creation routed through the existing Start-a-Story
setup (one pipeline, no orphan, user intent preserved). Final small fixes verified: Ideas chip bottom-right,
determinate scan progress bar + "Done scanning", clearer scanning state, Story-Home back fixed (commits
9a75cf1, 499951c). **Milestone CLOSED.** Automated `StoryTests` (CaptureAnywherePersistenceTests +
CaptureUXCorrectionsTests) are written to run in Xcode. Nothing pushed or deployed — all work is local
commits awaiting the owner's push decision.
