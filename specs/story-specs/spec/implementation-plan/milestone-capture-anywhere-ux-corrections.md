# Milestone — Capture Anywhere: UX Corrections & Unified Add Moments

**Status:** ACCEPTED — physically verified on iPhone 2026-10-14; milestone CLOSED.
**Nothing pushed/deployed; local commits only.** Builds on the Capture Anywhere V0.2.2 implementation
(`milestone-capture-anywhere-v0.2.2.md`).

## Scope

Four bounded UX corrections to the already-functioning continuous-capture flow, plus regression tests.
No Home redesign, no persistence-architecture rework.

## Root causes

1. **Camera thumbnail returned to Home.** `ContinuousCaptureView`'s bottom-left recent-Moment thumbnail
   button called `dismiss()`, which pops the camera's own `fullScreenCover` — so it unwound to Home instead
   of showing Moments.
2. **AI / recording states were visually ambiguous.** The model had a single `.scanning` state covering both
   frame-collection AND Director inference; there was no distinct "thinking" state, no on-screen REC
   indicator or elapsed timer, the AI overlay stayed visible during recording, and a late Director response
   from a cancelled/superseded scan could reopen an overlay over a live recording.
3. **"Add photos or videos" was Photos-only.** Inside a Story the only add entry opened the native Photos
   picker; there was no way to reuse Moments already in the library.
4. **Moments Library was single-purpose.** `MomentsLibraryView` hard-coded "Create Story / Delete" and could
   not adapt its primary action to the entry context (Home vs an existing Story vs the camera thumbnail).

## Implementation

**Phase 1 — thumbnail navigation.** Thumbnail now presents `MomentsLibraryView(libraryContext: .recentBrowse)`
as a `fullScreenCover` **over** the camera (the camera session beneath is preserved — no second session, no
teardown), so closing returns straight to a ready camera. The button is **disabled while recording** so an
in-flight clip is never interrupted; navigation is deferred until the user stops.

**Phase 2 — explicit states (`ContinuousCaptureModel` + `ContinuousCaptureView`).**
- `AIState` split into `.scanning` (collecting frames) and `.thinking` (Director generating) — distinct
  panels ("Scanning scene…" with the keep-recording hint + Cancel; "Finding a shot idea…" spinner + Cancel).
  Honest spinners — **no fabricated progress percentages.**
- A monotonic `aiGeneration` token invalidates any in-flight scan/Director response on dismiss, on a new
  scan, and **on recording start** — a stale response can never reopen an overlay (items 7, 8).
- Recording start **cancels/suspends** the scan, hides the AI overlay (`.off`), and starts a REC timer.
  The top bar shows a prominent pulsing-red **REC + mm:ss** indicator (reduced-motion aware); the ✕ close is
  disabled mid-recording. Idle shows the record button + optional "Get an AI shot idea"; "Idea ready" keeps
  Let's shoot / Next idea / Rescan. The red record button stays live in **every** AI state.

**Phase 3 — unified Add Moments.** New `AddMomentsSheet` chooser replaces the bare import entry in BOTH
`StoryHomeView` and `MomentsManageView`: **From Story Moments** opens `MomentsLibraryView(.story(story))` to
multi-select and link existing library Moments; **From iPhone Photos** opens the existing native Photos
import unchanged. New use-case `StoryUseCases.addExistingMoments(_:to:)` links existing Moments — idempotent
(repository `link` already prevents a duplicate `(story, moment)` link) and order-preserving (next
per-Story `orderIndex`), with **no media duplication** (the Moment + its AU are reused). No new import pipeline.

**Phase 4 — context-aware library.** New `LibraryContext` (`.home` / `.story(StoryModel)` / `.recentBrowse`)
drives one `MomentsLibraryView`: Home → "Create Story (N)"; Story → "Add to Story (N)" with already-linked
Moments badged "In Story" and excluded from re-add; camera thumbnail → browse-only (no Select/Create/Add),
closing returns to the camera.

**Phase 5 — tests (`CaptureUXCorrectionsTests`).** add-existing-Moment → one link; same Moment twice → no
duplicate link; order preserved; mixed batch links only the new; Home selection creates a Story; Story
selection adds to the current Story; `LibraryContext` affordances; standalone intent carries no stale Story.
Logic-only (no camera hardware); camera/AI-overlay/REC-timer items are device-only (Phase 6).

## Commits (local, on the V0.2.2 seam)

- `601e299` — Phases 1–4 (thumbnail→library, AI/REC states, Add Moments, LibraryContext).
- `357d86d` — Phase 5 regression tests.

Frozen prompts/contracts untouched. Nothing pushed or deployed.

## Phase 6 — device acceptance (owner-gated)

A Capture→thumbnail→Moments→close→camera · B/C clear Scanning/Thinking states · D record-while-AI-pending ·
E Add Moments → From Story Moments (association) · F Add Moments → From iPhone Photos (appears in Story +
global library) · no duplicate media/links · Create Story from library · save/playback/share.
