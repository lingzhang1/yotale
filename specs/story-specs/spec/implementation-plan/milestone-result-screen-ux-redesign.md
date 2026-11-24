# Story Result Screen — UX Redesign Proposal (version progress, navigation, action hierarchy)

**Status:** DESIGN + ARCHITECTURE REVIEW ONLY. No production code changed. No backend/contract/prompt/job
changes. STOP at proposal + estimate (owner decision gate). File `StoryResultView.swift` and the aligned
mockups the owner provided (States A/B/C) are the reference.

---

## Phase 1 — Audit (code-grounded; behavior NOT inferred from labels)

All findings from `apps/ios/Story/Story/Features/Create/StoryResultView.swift` + `Media/Photos/PhotosSaver.swift`
+ `Data/Persistence/Models.swift` + `Domain/Creation/PendingOperationRecovery.swift`.

**Save vs Share — the decisive semantics (owner's explicit ask):**
- **Save** → `saveToPhotos()` → `PhotosSaver.saveVideoCopy(at:)` → `PHPhotoLibrary.performChanges {
  PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL:) }` with `.addOnly` auth. **It saves the
  finished video to Apple Photos.** Not a draft, not an internal version commit.
- **Share to Files** → `ShareSheet(items: [resolvedURL])` → the **system share sheet** (Files, AirDrop,
  Messages, Photos, etc.).
- **Conclusion:** both are **export destinations of the same finished MP4** — Photos vs the system sheet.
  They are safely consolidatable into one "Save or Share / Export" flow (the owner's conditional is satisfied).
  No hidden draft semantics to preserve.

**Current banner / progress (the confusion source):**
- `inFlightBanner`: binary. `newVersionReady != nil` → "Your new version is ready — View" (tappable, swaps the
  output); else `pendingInFlight` → spinner + "Finishing your new version…". No stage detail.
- `observePendingRecovery()` polls `hasRecoverablePendingOperation`; it only knows "a pending op exists" vs
  "a newer output appeared", NOT which phase.
- **Key finding:** the data layer ALREADY has the full state machine. `PendingOperationModel.phase` =
  `submitted | planning | plan_ready | rendering | saved | abandoned` (+ `failureCategory`). The UI throws
  this away and shows a binary banner. The redesign is mostly **surfacing state that already exists**, not new
  backend work.

**Version identity / navigation:**
- `output = swappedOutput ?? initialOutput`. The ready banner tap sets `swappedOutput = ready` (one-way swap).
- `story.generatedOutputs.sorted { $0.createdAt > $1.createdAt }` exists but is **not surfaced as a selector**.
- Lineage exists on `GeneratedOutputModel`: `versionId`, `parentVersionId`, `operationType`, `editPlanJSON`.
- **There is no version selector today** — the user cannot browse/switch versions or pick an older one to
  revise except via the one-shot "View" swap.

**Actions during a pending op (not inferred — read from the action panel):**
- Save (primary), Create a new version, Share to Files are always present.
- Change music / Revise are **disabled when `output.editPlanJSON == nil`** (a legacy/mock row), NOT disabled
  during a pending op — so today you CAN start a Revise while another version is still generating.
- `recreate()` (Create a new version) abandons pending ops then mints a new operationId (from the P0 recovery
  work) — so duplicate-tap is partly guarded at the coordinator, but the button itself is not disabled.

**Recovery (already implemented, P0):** `PendingOperationRecovery` runs on launch + scenePhase.active, resumes
by jobId (never re-submits); `plan_ready` renders directly from the saved plan; `isRecoverable = phase not in
{saved, abandoned}`. A recovered op is the SAME op, not a duplicate.

### Current UX problems (annotated)
1. **Weak progress visibility** — "Finishing…" is a thin line above the old video; no stage, easy to miss.
2. **Competing CTAs** — Save (large), Create a new version, Share, Change music, Revise all compete; nothing
   says what to do next. During generation the big **Save** out-weighs the "ready — View" line.
3. **Unclear version identity** — the screen never says "you're watching Version 1"; the new version appears
   only as a transient banner; no way back to the old one after swapping; no browse.
4. **Ready notice is fragile** — it can be missed, and (from the earlier bug) relied on a cached relationship.

---

## Phase 2 — Screen state machine (drives the UI from PERSISTED state)

Map `PendingOperationModel.phase` (+ newest-output presence) to explicit UI states:

| UI state | Driven by | Primary action |
|---|---|---|
| **A. Idle** | no recoverable pending op | Watch current; Save/Share secondary-prominent |
| **B. Queued/Planning** | phase `submitted`/`planning` | Status card "Planning your edit…"; current video playable |
| **C. Plan-ready/Rendering** | phase `plan_ready`/`rendering` | Status card "Rendering…"; current video playable |
| **D. New version ready** | a newer completed output exists, not yet viewed | **View New Version** |
| **E. Failed/recoverable** | phase failed + `failureCategory` | Honest message + Try again / adjust |
| **F. Cancelled** | op cancelled | Return to idle on current version |

Rules: never show "ready" before the playable file exists (gate on a persisted, resolvable output, not job
`completed`); no invented % or ETA (show the stage word only); leaving/returning preserves the op (recovery
already guarantees this); a completing version must NOT auto-interrupt playback of the one being watched.

---

## Phase 3/5 — Contextual primary action + hierarchy

One dominant action per state, grouped by intent:
- **Primary:** Watch current · **View New Version** (state D) · Save/Share (state A).
- **Editing:** Revise, Change Music — given first-class card prominence (central Story features).
- **Exploration:** Create Another Version (secondary), Browse previous versions.
- **Secondary/overflow:** export sub-options (Photos vs Files), stale re-render, etc.

Concrete fix for the screenshots: during generation, **demote Save** and replace the binary banner with a
first-class **status card**; when ready, the **single** dominant action is **View New Version** (the big
cream button moves INTO the ready card, not competing below).

---

## Phase 4 — Version navigation
- A simple inline **version chip row** (V1 · V2 ✓ …) under the player — not a project manager.
- Shows the currently-viewed version, marks the selected one, distinguishes pending (spinner chip) vs ready.
- Tapping a chip swaps the player (no auto-interrupt from a background completion).
- Selecting an older version is allowed as the base for Revise/Change-Music (lineage already supports
  `parentVersionId`). For N=1 show no selector; for small N the chip row; defer anything fancier.

---

## Phase 6 — Recovery & failure UX
- Backgrounded planning / app restart / recovered plan / resumed render: driven by the SAME `phase` →
  the status card shows the real stage; a recovered op shows as the SAME op (never a duplicate).
- Failed: honest message keyed off `failureCategory` (e.g. `directivesUnsatisfiable` → "adjust your
  instruction", `materialInfeasible` → duration, generic → Try again). Already partly wired.
- Expired backend job / cancellation → return to idle on the current version with a brief notice.
- Ready notice persists until the user Views or explicitly dismisses it (do not clear on completion alone).
- Duplicate-tap: disable the generate action while a create/revise op for this Story is in flight (today it's
  only guarded at the coordinator).

---

## Phase 7 — Deliverables summary

1. **Problems:** weak progress, competing CTAs, no version identity, fragile ready notice (above).
2. **Hierarchy:** status/primary → editing (Revise/Music) → exploration (Another Version/Browse) → export.
3. **Mockups:** align to the owner's A (Creating — first-class status card, current video below, demoted
   Revise/Music/Share), B (Ready — View New Version inside the ready card + V1/V2 chips), C (Normal — player,
   V1/V2✓ chips, Revise+Music cards, Create Another Version secondary, one "Save or Share").
4. **Version selector:** inline chip row, pending vs ready, no auto-swap.
5. **Save/Share:** consolidate into one **Save or Share** entry that offers Photos (PhotosSaver) + system
   sheet (ShareSheet) — same finished MP4, two destinations; no semantic change, just one entry point.
6. **Failure/recovery:** phase-driven status card + `failureCategory` messaging.
7. **Accessibility:** status card is a VoiceOver live-region announcing stage changes; chips have labels
   ("Version 2, ready, selected"); honest labels over icons; respect reduce-motion on the spinner.
8. **SwiftUI changes (scoped):**
   - Replace `inFlightBanner` (binary) with a `GenerationStatusCard` bound to `phase` (read `PendingOperation`
     instead of just `hasRecoverablePendingOperation`).
   - Add a `VersionChipRow` reading `story.generatedOutputs` + `swappedOutput`.
   - Refactor `actionPanel` into intent groups; fold Save+Share into one export sheet.
   - `observePendingRecovery()` returns the phase, not a bool.
   - No new SwiftData models (phase/lineage already exist); no backend calls added.
9. **Effort estimate:** ~2–3 dev-days. Status card + phase plumbing ~1d; version chip row + swap/lineage ~1d;
   action-panel regroup + Save/Share consolidation ~0.5d; a11y + failure polish ~0.5d. iOS-only.
10. **MVP vs deferred.**
    - **MVP:** phase-driven status card (A), View-New-Version-as-sole-primary (B), V1/V2 chip row, Save/Share
      consolidation, no auto-interrupt, persistent ready notice.
    - **Deferred:** thumbnails per version, diff/"what changed" between versions, rich export options, a
      full version manager, per-stage ETA (intentionally never).

---

## Phase 8 — Acceptance scenarios (how the design satisfies each)
1. Start another version, keep watching current → current video stays playable; status card shows Planning;
   generate is a separate op. ✅
2. Background & return while planning → recovery resumes the SAME op; status card reflects live phase. ✅
3. New version completes while elsewhere → ready notice persists; no auto-swap. ✅
4. Return & notice ready → first-class ready card (not a thin line). ✅
5. Open new version → View New Version swaps the player; card dismisses. ✅
6. Switch back to previous → V1 chip. ✅
7. Revise an older version → select its chip, then Revise (lineage carries parentVersionId). ✅
8. Change music on selected → Music card acts on the selected version (uses its soundtrack carry-over). ✅
9. Save/export selected → one Save-or-Share entry → Photos or system sheet. ✅
10. Failed generation & recover → phase=failed + failureCategory message + Try again; recovery never
    duplicates. ✅

---

## Decision gate
Proposal only. No code, no backend/contract/prompt/job changes. Recommended next step: approve the MVP scope
(status card + View-New primary + chip row + Save/Share consolidation) as a single iOS-only implementation
increment, device-gated. Risk is low because the state machine + lineage already exist in the data layer —
this is primarily a presentation refactor of `StoryResultView`.
