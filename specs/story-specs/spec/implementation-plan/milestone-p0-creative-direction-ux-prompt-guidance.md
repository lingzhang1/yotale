# P0 — Creative Direction UX: Prompt Guidance & Capability Awareness

**Status:** IMPLEMENTED (iOS-only) + tests, awaiting device acceptance. STOP at device gate.
**Owner decision date:** 2026-10-18
**Branch:** `fix/p0-recover-jobs-explore-latency` (nothing pushed/public). No backend/frozen-contract change.

## Objective

Users should understand what Story can edit before submitting NL instructions — reducing unsupported
requests, wasted model calls, and trial-and-error. Applies to the **Customize** (pre-creation Creative
Direction) and **Revise** (post-generation) screens only; the Start-a-Story description screen is
untouched.

## Phase 0 — audit (reusable components found)

`FlowLayout` (wrapping-chip layout), `StoryTextField`, `StoryTheme` tokens, `MomentReferenceChipRow`,
`MomentReferencePicker`, `InterpretationCoordinator`, `StoryMomentNumbering` (gap-free 1..N snapshot for
valid Moment references), and the backend `_classify_unsupported_ops` capability vocabulary. Both screens
share a near-identical instruction-field + chip-row + interpret-lifecycle structure.

## New reusable file — `PromptGuidance.swift`

- **`PromptSuggestionChips`** — compact "Try asking Story…" row. Tapping a chip **appends** editable text
  to the instruction field (never auto-submits) and invalidates any in-flight interpretation, exactly like
  a manual edit. Opening examples use a **real** Moment number from the numbering snapshot; when there are
  no referenceable Moments the opening example is omitted (never a hardcoded nonexistent N).
- **`CapabilityInfoButton` + `CapabilitySheet`** — a small (i) "Editing capabilities" affordance opening a
  concise "What can Story edit?" sheet: a supported list (trim/reorder/select, shot duration, speed within
  limits, supported transitions, change soundtrack, keep/duck/mute native audio, beat-aligned cuts) and a
  short unsupported list (color grading/filters, brightness/exposure, stabilization, text overlays, advanced
  zoom/reframe, background replacement). Kept concise so the main screen is not overwhelmed.
- **`CapabilityClassifier`** — a **small iOS mirror** of the backend `_classify_unsupported_ops` vocabulary
  for **instant** pre-submit feedback (no per-keystroke network). Not a second NLP parser and not the
  authority — the backend guard remains final. Verdicts mirror the backend: `.supported` / `.mixed` /
  `.allUnsupported`.

## Per-screen

- **Customize:** Try-asking chips (opening / include-exclude / visual selection / pacing / music + native
  audio) + capability button in the Creative Direction section.
- **Revise:** Try-asking chips (preserve footage / shorten shots / reorder / replace opening / pacing /
  change music) + capability button; a **"Editing V N"** header and *"Story keeps the existing edit unless
  you ask to change it"* (Phase 3 — the selected versionId is captured by the caller at op start, never
  defaulted to latest); **Phase 4 pre-submit**: a fully-unsupported ask is explained and **not planned**
  (version preserved, no replacement); a mixed ask **confirms partial execution** before planning; a
  supported ask proceeds.

## Reuse of backend capability classification (Phase 4 decision)

Owner: "reuse where feasible" + "do not expand the keyword list into another comprehensive NLP parser."
Chosen: a tiny iOS mirror of the **same** bounded vocabulary (instant, offline) rather than a per-keystroke
`/v1/classify` round-trip. The backend `_classify_unsupported_ops` remains the authoritative guard (it
still refuses an unsupported job and preserves the version even if the mirror misses). The two vocabularies
must be kept in sync; this is called out in the code. A reliable *semantic* classifier would require the
interpreter/schema — **deferred**, proposed separately (below).

## Tests

`PromptGuidanceTests`: classifier verdicts (supported / all-unsupported / mixed, phrase formatting),
suggestions use a real Moment number (and omit the opening example when none exist), Customize vs Revise
example sets differ, and the append join rule. Swift parse-clean (Xcode type-check + device acceptance is
the authoritative gate; the SwiftData macro is sandbox-blocked).

## Acceptance (device, owner STOP)

1. Suggestions insert editable text (no auto-submit). 2. Suggestions use valid Moment references.
3. Customize and Revise show different examples. 4. Revise shows "Editing V N". 5. Supported requests
proceed. 6. Unsupported requests explained (version preserved). 7. Mixed requests confirm before partial
execution. 8. No duplicate submissions. 9. No unintended full replan. 10. No stale text after reopening.
11. Accessibility + small-screen layout usable.

## Deferred — semantic pre-submit classification (proposal)

The keyword mirror catches the common unsupported asks but not novel phrasings ("give it a vintage look").
A reliable semantic classifier belongs in the interpreter: extend `/v1/interpret-revision` to return a
`capability_verdict` (supported/mixed/unsupported + reasons) as part of the single structured interpret
call it already makes. That is a **frozen-interpreter change** and is proposed separately, not built here.
