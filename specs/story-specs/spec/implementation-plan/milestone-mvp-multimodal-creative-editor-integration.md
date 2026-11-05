# Milestone: MVP Multimodal Creative Editor Integration (+ Adaptive Visual Budget)

**Date:** 2026-10-13 · **Status:** implemented, parse-clean + backend-tested; **STOPPED at owner physical-device acceptance** · **Nothing pushed/deployed.**

Builds on the Creative-Objective experiments (A0/A1/B visual-evidence; Short-Form social). Owner decision: ship bounded multimodal visual planning for the MVP; product principle = *Story should be visually intelligent and artistically creative even when the footage has no strong chronology.* No new broad experiment.

## 1. Implementation commits
- **Backend** (app `924d22f`): `packages/edit_planner/__init__.py`, `apps/api/app/main.py`, `apps/api/tests/test_edit_planner.py`.
- **iOS** (this change): `MomentContactSheetBuilder.swift`, `MultimodalVisualBudget.swift`, `EditPlannerService.swift`, `StoryCreationCoordinator.swift`, `StoryMultimodalPlanning.swift`.

## 2. Exact multimodal request format
New endpoint **`POST /v1/edit-plan-mm`** (`multipart/form-data`), additive to the frozen `POST /v1/edit-plan` (unchanged):
- `body` (JSON) — the SAME `EditPlanRequest` shape as `/v1/edit-plan` (validated by the same Pydantic model).
- `sheet_order` (JSON array) — Moment ids, one per contact-sheet, in `sheets[]` order.
- `creative_brief` (text, optional) — the versioned app-level brief; injected into the Edit Planner **user message only**, never the frozen v5.2 system body.
- `sheets` (files) — one tiled Tier-1 contact-sheet JPEG per Moment (derived frames; never source video).

Backend builds `EditPlanInputs(images=[ImageInput], creative_brief=…, image_moment_order=…)` and runs the **shared `_execute_edit_plan` core** — the identical deterministic validator, infeasibility handling, and 200/422/503 semantics as the text-only path. The gateway attaches each JPEG as a Bedrock `image` block before the text (existing `StructuredRequest.images` surface — no new gateway code, no model swap). The frozen `edit_plan/5.2` body is byte-identical (asserted sha `d1116552`).

## 3. Image / token budget
Server backstop (`apps/api/app/main.py`): `_MM_EDIT_MAX_SHEETS=120`, `_MM_EDIT_MAX_SHEET_BYTES=1MB`, `_MM_EDIT_MAX_TOTAL_BYTES=20MB`, types `image/jpeg` only. Images are **ephemeral — never persisted** (same as the AU frames endpoint).

Device adaptive preflight (`MultimodalVisualBudget`) targets **below** the server ceiling: 16 MB total, 900 KB/sheet, so the server rarely has to reject. Tier-1 frames per Moment = `max(4, min(9, round(dur/8)))`, tiled 3-up at ~320px cells, JPEG 0.7. Degradation ladder (deterministic, no model call): **resize → compress → fewer frames → reduce whole-Moment visual coverage** (richest Moments keep images; the rest plan text-only). A1 structured text covers **every** Moment regardless; stable Moment IDs + burned-in source timestamps throughout.

## 4. Fallback behavior
- No sheets → text-only `/v1/edit-plan`.
- Image rejected (413/415) or transport error while sending images → **one** text-only fallback via `/v1/edit-plan` (never fabricates evidence, never drops a Moment).
- `503` (model) and **material** `422` (genuinely infeasible footage) propagate as-is — they are not image problems, so no silent retry.
- Image-mapping `422` (unknown Moment id / order mismatch) is treated as an image failure → text-only fallback.
- Daily-token-quota exhaustion is a provider condition, NOT an image-size problem — the preflight never retries it as if shrinking images would help.
- `StoryPlanningDiagnostics` records `usedMultimodal`, sheet count, image bytes, Moments-text-only, selected tier, applied steps, and fallback reason — so a device run can PROVE which path produced the plan. No image bytes/content are logged.

## 5. Test results
Backend: **40/40** edit-planner tests pass (6 new multimodal: engine attaches images+brief to the request; text-only request stays byte-clean; endpoint success with sheets; text-only fallback with no sheets; unknown-Moment-id 422; order/count-mismatch 422). Full API + edit_planner suite green (170+). iOS: all five files **parse-clean** (`swiftc -parse`).

## 6. Device acceptance — PENDING (owner wall)
Phases 4-5 (regression + physical-device acceptance) require the owner's iPhone and an Xcode build. The Kiro sandbox blocks the SwiftData macro plugin, so `swiftc -typecheck`/`xcodebuild` cannot run here — **the authoritative iOS compile is the owner's Xcode build.** Enable on-device with launch arg/env `STORY_MULTIMODAL_PLANNING=1` (flag default is OFF). Datasets to verify on device: Girl with Dress (visual variety, expressive opening, outfit/location coverage), Hiking (summit payoff preservation), Guitar (continuous performance + native audio), minimal/quiet footage (no forced cuts). Verify orientation/aspect, valid source ranges, opening quality, native-audio continuity, music playback, export/share, latency, and failure handling vs the current text-only MVP.

## 7. Observed latency / cost (experiment proxy, not device)
From the Short-Form experiment on the SAME transport: multimodal planner call ≈ 4–5 MB image payload, ~20–35 s latency, ≈ $0.4–0.5/call at 36–40 Moments; text-only ≈ $0.02/call. Device latency adds on-device frame extraction + tiling (bounded; measured in Phase 5).

## 8. Remaining limitations
- iOS type-check is owner-Xcode-only (sandbox limit); parse-clean ≠ Xcode-clean. Verify theme/member APIs on build.
- Multimodal planner call is heavier (image payload + latency); the preflight bounds it but a very large library degrades visual coverage before falling back.
- Phase 6 (critique/revision behind a flag) is NOT implemented here — deferred; MVP must not block on it.
- Backend not deployed to dev; no public prod deploy.

## 9. MVP release readiness
Backend + iOS integration are implemented, bounded, and reversible (feature flag OFF by default; text-only path untouched and still the default). **Release-blocked on owner device acceptance** (Phase 5) and an Xcode build. Recommended minimum to ship: enable the flag only after device acceptance passes on all four datasets, deploy the backend to dev first.

## STOP
No production prompt freeze, no contract change, no push, no deploy. No advanced effects, new creative modes, or unrelated work. Stops for owner device acceptance before the feature is declared complete.
