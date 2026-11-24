# C1–C3 DIRECT Flow Audit vs Frozen Figma + Production Spec

**Date:** 2026-10-02
**Scope:** the real iPhone C1→C3 DIRECT flow (CreativeDirectionView → StoryHomeView
→ ShootMomentView/SceneScanFlowView) vs `11-direct-flow.md` + the frozen Figma
(`prototypes/story-figma/src/App.tsx`). C1–C3 capabilities only — validation,
processing, and result screens are C4+ and out of scope.

## Discrepancy list

| # | Discrepancy | Spec / Figma | Current iOS | Category |
|---|---|---|---|---|
| D1 | Concept Card missing | Concept Card before shooting: title · description · "N shots · ~X sec" · [Let's shoot] · Try another idea | Jumped to "Here's your shot" + Open Camera; no concept preview / shots / duration | **Must-fix** |
| D2 | No "Skip scan" | "Show me where you are" → [Hold to scan] **or [Skip scan]**; scan optional | Scan mandatory | **Depends on C4** (needs an intent-only Director path) |
| D3 | "Try another idea" missing | Secondary on concept card → Director variation call, once | Absent | **Depends on C4** (needs a Director variation path) |
| D4 | Loading copy | "Got it, I'm thinking…" / "I have an idea…" | "Looking at your scene…" / "Finding the best way to capture this…" | **Polish later** |
| D5 | Intent input | Template + optional text (+ reference) | Title + free text only | **Polish later** |
| D6 | Raw intent chips in consumer UI | Consumer must not see raw CreativeIntent fields | "What Story understood" chips on Story Home | **Must-fix** |
| D7 | CTA wording | "Let's shoot" | "Open Camera" | **Polish later** (folded into D1 fix) |
| D8 | MomentRow raw source enum | consumer language | shows `moment.source.rawValue` | **Polish later** |
| D9 | rescan / create states | human-readable, never blank | dedicated branches (fixed earlier this session) | **Done** |
| D10 | error / loading / continuity | human error + retry; state survives | C1 retry alert, C2/C3 failed+retry, Story persists | **Done** |

## Implemented now (must-fix-before-C4 only)
- **D1 — Concept Card.** `SceneScanFlowView` capture/retry branch now renders a
  concept card: concept **title** (hero) + concept **summary** as the description +
  **"N shots · ~X sec"** (`conceptMeta`: plan estimated duration, falling back to
  summed shot durations) + the first shot's plain instruction and light guidance,
  with **"Let's shoot"** as the primary CTA (absorbs D7). Visual-first, no shot plan
  dump, no filmmaking terms — matches the spec card + frozen Figma vocabulary.
- **D6 — consumer/debug separation.** The raw "What Story understood" CreativeIntent
  chips on Story Home are now `#if DEBUG` only. The consumer sees the Story summary;
  the resolved-intent fields are a diagnostic, not consumer UX.

Both verified `swiftc -parse` clean. iOS-only; backend unchanged (no redeploy). 98
backend pytest unaffected.

## Deferred (with reasons)
- **D2 Skip-scan / D3 Try-another-idea → depend on C4.** Both require Director call
  paths that are not C3 capabilities: skip-scan needs an intent-only (no
  SceneUnderstanding) Director path; "try another idea" needs a variation re-call.
  Building either now would mean inventing Director behavior outside the frozen C3
  surface. Implement alongside the C4 Director loop.
- **D4/D5/D7(resolved)/D8 → polish later.** Loading copy is consumer-safe and
  intent-equivalent; template input is an input convenience (C1 handles free text);
  the source-enum leak in MomentRow is minor. None blocks C4.

## Not touched (per instruction)
No product redesign, no validation UX, no broad visual polish. Navigation/state
continuity was already correct (NavigationStack → StoryHome → fullScreenCover
capture; Story persists across relaunch via SwiftData).
