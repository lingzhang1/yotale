# Milestone R7 — Four-Regression Stabilization (P0)

Status: implemented + automated/parse-verified; **awaiting two-device physical acceptance**.
iOS commit: `e9bfbc5` (branch `feat/r1-account-ownership-isolation`). iOS-only — no backend, CDK, or
frozen-contract change.

R7 is NOT accepted until the four-regression device acceptance below passes.

## Context

Four device regressions were reported against the R7-F/C build during cross-device testing. The owner
authorized fixing all four in one bounded increment; prior per-increment STOP gates superseded for this scope.
No `invalid_after_repair` planner investigation, no capacity/observability/billing work.

## Root-cause → fix map

### Issue 1 — Customize sheet skipped; "moments not enough" dead-end
- **Root cause:** `CreateStoryPreviewView.beginCreateFlow()` did `if story.intentTargetDurationSeconds != nil {
  beginMusicFlow(); return }`. Any Story with a saved target jumped straight to the music picker, so the
  Customize sheet (duration/sound/creative-direction) was unreachable. The saved target (240s) exceeded the
  current usable footage (~187s), so `DurationFeasibility` returned `insufficientMaterial` and dead-ended — with
  no way to lower the length because Customize was skipped.
- **Fix:** `beginCreateFlow` ALWAYS routes through `promptDuration()` → `CustomizeYourStoryView`.
  `CustomizeYourStoryView` gained `initialExplicitTargetSeconds` + `initialEditorialMode` and prefills the
  length selection from the Story's prior choice (explicit "custom" seconds vs editorial mode), preserving
  explicit-vs-inferred provenance. Pure seed logic extracted to `seedLength` / `seedCustomSeconds` (unit-tested).

### Issue 2 — Repeated "I couldn't finish your Story", retry → same error
- **Root cause:** the coordinator mapped ALL backend `invalid_after_repair` → `directivesUnsatisfiable`, and the
  Creating view's `FailureRecovery` routed everything non-insufficient to `.technical` (plain **Try again**) — so
  a deterministic directive conflict resubmitted an identical failing request, and a planner-side failure with
  no directives was still labeled as the user's instruction error.
- **Fix:** split `invalid_after_repair` by whether the request carried HARD directives
  (`revisionHasHardDirectives`): WITH directives → `directivesUnsatisfiable` → new `.adjustInstructions`
  recovery (Adjust Instructions, **no plain retry**, instruction preserved, host re-opens Customize via
  `onAdjustInstructions`); WITHOUT directives → new `invalidPlanOutput` → honest technical message that does NOT
  blame the instruction, bounded retry allowed.

### Issue 3 — "Return" during create → stuck "Preparing your Story…" spinner
- **Root cause:** the create host's DEFAULT body was a `ProgressView` + "Preparing your Story…". Backing out of
  the music picker (`.cancel` just returned) or the Customize sheet left the user resting on that perpetual
  placeholder.
- **Fix:** explicit navigation state. The backdrop shows "Preparing…" only while a step is genuinely in flight
  (`isFlowActive`). A genuine back-out (picker cancel, Customize cancel, no-material OK) sets an explicit
  `userBackedOut` flag that pops the host to Story Home — distinct from a picker→Creating handoff, so the
  transition never triggers a spurious dismiss. Navigating away never cancels the backend job; pending
  generation stays recoverable via the existing `PendingOperationRecovery`.

### Issue 4 — Same Story, two devices, different Guide + Coverage (highest priority)
- **Root cause:** a race. `StoryHomeView.loadCoverage()` runs on view appear and `StoryGuideCoordinator.
  ensureGuide` generates a fresh Guide when none exists locally; the cloud pull (carrying the derived block)
  runs on a separate foreground/sign-in trigger. On Device B the view often generated its own Guide/Coverage
  BEFORE the pull delivered A's derived block, and `applyDerived`'s keep-local-if-present policy then refused to
  adopt A's. `ensureGuide` was never gated by `CloudHydrationGate`, and the gate was only held during the
  in-flight pull window (not durably), so a view that opened before/after the pull raced in.
- **Fix:**
  1. **Durable barrier:** `StorySyncJobModel.hydrationPending` + `cloudRevisionSeen` (additive, defaulted →
     lightweight SwiftData migration). The pull sets `hydrationPending=true` the moment the index shows a newer
     clean revision, and clears it only after the derived block + understandings are restored.
  2. **Seeded gate:** `CloudHydrationGate.seedFromDurable` / `isHydratingAfterSeed` re-establish the in-memory
     barrier from the durable rows on first access — so a view recreation or relaunch that races ahead of the
     pull still holds.
  3. **Gated generation:** `ensureGuide`, the coverage engine recompute, the MusicDirection ensure, and the AU
     backfill/drain all check the seeded gate before inferring.
  4. **Prefer-cloud during hydration:** `applyDerived(preferCloud:)` overwrites a PROVISIONAL local cache
     generated during the race with the verified cloud copy — EXCEPT a user-authored music direction (never
     clobbered) and a dirty record (raised as a conflict, never overwritten).
  5. **Safety:** offline/timeout leaves `hydrationPending` durable so the next pull retries the restore before
     any regeneration (no auto-inference on timeout); unsupported-schema clears it to avoid a permanent block;
     the account-switch guard (`j_ownerStable`) releases the gate and never applies a cross-account callback.

## Automated tests (XCTest — run in Xcode/device, parse-clean in sandbox)
- `StoryResultFlowTests`: Customize seed (explicit mode/seconds win; fallback); FailureRecovery mapping
  (directive conflict → adjust; invalidPlanOutput → technical; insufficient → duration choice; technical →
  retry); invalid-output message does not blame the user.
- `StorySyncTests`: derived round-trip (guide/coverage + provenance); understanding restore reuse-gate;
  hydration gate blocks AU; applyDerived default keeps local; preferCloud overwrites provisional; preferCloud
  preserves user-authored music; durable-seed re-holds the barrier; pull hydrates derived + clears pending +
  releases gate; dirty-local not hydrated.

## Device acceptance checklist (Gate 4 — owner runs on two iPhones)
1. Create My Story shows Customize with the existing values prefilled.
2. The stale/infeasible duration can be adjusted down.
3. A deterministic directive conflict shows Adjust Instructions, not a retry loop.
4. Return from the music picker / during generation lands on Story Home or the Result page.
5. Device B restores the SAME Guide and Coverage as Device A (no divergence).
6. Compatible Moment Understanding is reused (no re-analysis).
7. **Bedrock calls caused solely by Device B restoration = 0** for compatible data.
8. Both devices preserve the same creative state and version lineage.
9. Existing creation / revision / music / rendering still work.

## Known limitations
- The "prefer-cloud during hydration" window only overwrites PROVISIONAL (non-user-authored, non-dirty) caches;
  a stale-but-present local cache outside hydration still invalidates by its own fingerprint, not by cloud.
- `UnderstandingSync.restore` reuse gate accepts a cloud understanding when the Moment is cloud-backed
  (`cloudMediaId`) or the content sha matches; a Moment with neither is not reused cross-device (by design).
- Zero-Bedrock-on-B is enforced by the gate + restore path but the measured value is pending the device test.
