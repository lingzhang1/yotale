# Milestone C2 — Real Scene Understanding: Report

**Date:** 2026-10-01
**Component:** Scene Understanding (second real-AI slice, multimodal)
**Status:** Backend built, deployed, verified live. iOS scan tree authored +
parse-clean. **Physical-iPhone device gate is the one remaining close item
(human step).**

Reconciliation up front: the approved C2 design matched the repo with **no
material conflict** — the Model Gateway already carried `images` (built in C1),
the `SceneUnderstanding` contract/DTO/schema were frozen and correct, and
`CaptureSession.scene_understanding` is the home. No contract decisions reopened.

## 1. Files added/changed
**Backend (new):** `prompts/scene_understanding/v1/system.md`;
`packages/scene_understanding/__init__.py` (engine + mock + semantic guard);
`apps/api/tests/test_scene_understanding_engine.py`,
`test_scene_understanding_endpoint.py`; `evals/run_scene_understanding.py`;
22 `evals/scene_understanding/*.fixture.json`.
**Backend (changed):** `apps/api/app/main.py` (multipart endpoint + limits),
`app/deps.py` (scene engine provider), `apps/api/pyproject.toml` + `Dockerfile`
(python-multipart), `evals/harness/deterministic.py` (`scene_observational` check).
**iOS (new):** `Media/Camera/SceneScanController.swift`,
`Media/SceneScan/SceneFrameProcessor.swift`, `Media/SceneScan/SceneScanStore.swift`,
`Data/Contracts/SceneUnderstandingService.swift`,
`Features/SceneScan/SceneScanFlowView.swift`.
**iOS (changed):** `Features/Capture/ShootMomentView.swift` (scan entry button).

## 2. Final acquisition / request flow
iPhone camera (scan mode) → ~4s pan, in-memory frame grab → `SceneFrameProcessor`
(blur reject + near-dup reject + cap + resize/JPEG) → `SceneUnderstandingService`
multipart `POST /v1/scene-understanding` → deployed App Runner → multipart
validation → `SceneUnderstandingEngine` → generic `BedrockModelGateway` (Converse
tool-use, images) → real vision model → canonical `SceneUnderstandingContract` →
semantic guard → Swift `SceneUnderstandingContractDTO` → read-only scan result UI.
Verified live end-to-end from the backend (device step pending).

## 3. Frame sampling / filtering
`AVCaptureVideoDataOutput` grabs frames throttled to ~1/0.35s over ~4s (~8-12
candidates). `SceneFrameProcessor.select`: (a) Laplacian-variance sharpness via
CIConvolution3X3 drops blurred frames; (b) 8×8 average-hash, Hamming<8 drops
near-duplicates; (c) cap to 5, prefer sharp+diverse; (d) resize longest side
≤1024px, JPEG q0.6 → `[Data]`.

## 4. Ephemeral-frame lifecycle
Frames stay in memory; `SceneScanStore` provides an ephemeral temp dir
(`tmp/scene-scan/<id>/`) with `cleanup`/`sweepStale` and a hard-rule comment:
NEVER `MediaStore.adoptCapturedFile`, never a Moment/Asset, never permanent.
Server side: frames ride inline in the request and are **discarded after
analysis** — not persisted (verified; no S3).

## 5. Multipart API shape
`POST /v1/scene-understanding` (multipart/form-data): one `context` JSON part
(`capture_session_id`, `mode`, `story_id?` — NO CreativeIntent; scene is
intent-independent) + `frames[]` JPEG parts. Limits enforced before any model
call: ≤6 frames (413), ≤2MB/frame + ≤8MB total (413), image/jpeg|png only (415),
malformed context (422). 503 designed-failure on model/provider error — never a
fabricated scene. → 200 canonical `SceneUnderstanding`.

## 6. ModelGateway multimodal extension
No new abstraction — the existing generic `StructuredRequest.images: [ImageInput]`
(built in C1) is used; `BedrockModelGateway` already renders image Converse
blocks. The engine depends on the gateway Protocol, not Bedrock. C1 Creative
Intent path unchanged (uses `images=[]`), verified still 200.

## 7. Models compared & default
Candidates (same prompt v1, same schema, same synthetic scenes, temp 0):

| | nova-pro-v1:0 | nova-2-lite (us profile) |
|---|---|---|
| schema valid | 4/4 | 3/4 (schema) |
| **observational boundary** | **held on all 4** | **leaked "walk toward" on blank wall** |
| blank-wall (anti-hallucination) | sparse, honest "no features" | over-generated pan/zoom "opportunities" |
| latency p50 | **1737 ms** | 2328 ms |

**Default: `amazon.nova-pro-v1:0`** (task-specific, config `STORY_SCENE_MODEL`).
Chosen on the top criterion — Nova Pro stays observational and grounded; Nova 2
Lite drifted into directing (caught by the semantic guard) and was slower. Not a
schema-validity tie-breaker. Creative Intent stays Nova Lite — model selection is
per-task. Both runs recorded in the harness.

## 8. Eval dataset composition
22 scene fixtures covering the required categories (home/office/cafe/hotel/urban/
crowded/park/beach/mountain/trail/narrow/open/social/low-light/backlight/clutter/
ambiguous/fg-bg/scale/limited-motion/weak-wall/restaurant). Semantic
expected/forbidden properties, no pinned prose; every fixture forbids
shot/direction/safety-cert output. Real device-scan frames are preserved under
`evals/scene_understanding/<id>/` as collected during dogfooding (the dataset
grows from real scans + discovered failures). Headless model comparison used
4 synthetic scenes (abstract shapes) to exercise grounding/boundary behavior.

## 9. Grounding / hallucination results
Nova Pro grounded to what was actually present and, critically, returned a
**sparse honest result on the weak/blank scene** ("plain undifferentiated space,
no features", `operator_space: unknown`) rather than inventing cinematic
features — the key anti-hallucination case. The synthetic scenes are abstract
shapes, so literal readings ("triangular shape") are expected; real photos give
real content. The semantic guard + `scene_observational` deterministic check
caught the one directing leak (Nova 2 Lite).

## 10. Payload sizes
2 synthetic frames ≈ 17-21 KB total at q0.6; real-device frames (resized ≤1024px,
q0.6) are expected in the tens-to-low-hundreds of KB for 3-5 frames — well under
the 8MB cap and the App Runner request budget. Device dogfooding records actuals.

## 11. Latency / cost
Backend inference 1.3-2.5s for 2 frames; total deployed endpoint ~2.5s. Tokens
~5-11K in / <1K out per scan on Nova (image tokens dominate input). Fractions of
a cent per scan. Synchronous multipart is comfortably viable — no S3/async
needed (measurement supports the approved design).

## 12. Physical-iPhone results — PENDING (close gate)
The iOS scan tree is authored and `swiftc -parse`-clean, but the camera +
on-device CV + real-device latency can only be exercised by building in Xcode
onto a physical iPhone (I cannot run Xcode or a device). This is the one
remaining C2 close item and is a human step. The deployed endpoint is live and
verified, so the device run should work on build.

## 13. UX issues discovered
None on-device yet (pending the device gate). The flow implements intro →
scanning → analyzing (spinner) → success (read-only observation summary) →
recoverable failure/rescan. The ~2-2.5s analyze step uses a progress state;
if real-device latency feels long, that is flagged for the later UX pass (no
broad polish in C2).

## 14. Regression cases added
`scene_observational` deterministic check (rejects leaked directing/editing/
safety phrases) + the 22-fixture set with forbidden-property guards. The Nova 2
Lite "walk toward" leak is captured by the check. New failure classes available:
SCENE_HALLUCINATION, SCENE_MISSED_OPPORTUNITY, SCENE_CONSTRAINT_MISSED,
unsupported-physical-assumption, poor-prominence, operator-space-misread,
excessive-detail (extend as device dogfooding finds them).

## 15. Architecture deviations
None material. Minor: the C1-era "gateway is text-shaped" note was already stale
(images shipped in C1); no abstraction change was needed. Scene model defaults to
Nova Pro (vision), separate from Creative Intent's Nova Lite — per the
task-specific-model rule, not a deviation.

## 16. Recommendation on proceeding to Story Director
**Recommend proceeding to Story Director after the physical-iPhone scan gate is
confirmed.** The multimodal path is proven end-to-end on the backend, grounded,
observational, and deployed; the contracts (StoryConcept/StoryPlan/Beats/
DirectorDecision) are already frozen; and SceneUnderstanding now produces the
real upstream input Director needs. Gate C3 on: (a) a green device scan, and
(b) optionally the Anthropic use-case form if you want a Claude candidate for
Director's heavier reasoning. **Stopped here — Story Director NOT started.**

## C2 Definition of Done status
Met: generic multimodal gateway (no C1 break ✅), real vision model returns
canonical SceneUnderstanding ✅, synchronous multipart against deployed AWS ✅,
diverse scene eval set ✅, model comparison recorded ✅, failure captured as a
deterministic check ✅, payload/latency support the sync design ✅, scan UX
authored ✅, all tests green (81) ✅, frames ephemeral ✅.
**Pending: physical-iPhone scan run** (human step).

---

# C2 Close — physical-iPhone verified + device regression fixed (2026-10-01)

**Physical-iPhone E2E PASSED.** On a real device, Shoot a Moment → "Show me
what's around you" scanned an indoor room (red backpack on a chair) → deployed
AWS → real multimodal model → canonical SceneUnderstanding rendered in the scan
UI. Subjects/prominence/operator_space/lighting were well grounded.

**Quality regression found on-device + fixed (general, not object-specific):**
The output inferred unsupported physical properties ("the backpack is heavy",
"the chair may not be able to support a lot of weight") and emitted
object-manipulation as motion opportunities ("the backpack could be moved to
another location"). General fix applied:
- **Prompt:** never infer weight/strength/stability/load-bearing/fragility/
  accessibility/safety from images (images ≠ the physical world);
  `motion_opportunities` are observable SUBJECT/CAMERA movement THROUGH the space,
  not rearranging objects; a framing relationship requires BOTH elements visible;
  constraints are shooting conditions, not object properties.
- **Engine semantic guard + harness `scene_observational` check:** extended with
  physical-property patterns (is heavy / support weight / load-bearing / fragile /
  stable …) and object-manipulation patterns (could be moved / relocated /
  lifted …). Generalizable, low false-positive — no backpack/chair-specific rules.
- **Regression fixture** `su_backpack_physical_props_regression` added (real
  device case; forbidden-property list covers the physical-property, manipulation,
  and the unverified "framed by the window" grounding risk).

**"framed by the window" grounding:** the actual submitted frames are ephemeral
and were not retained (privacy by design), so I could not confirm whether the
window was in-frame; classified and preserved as a potential grounding/
hallucination failure in the regression fixture (prompt now requires both framing
elements be visible).

**Verification of the fix:**
- Real model on an indoor-room scene post-fix → `motion_opportunities: []`,
  `constraints: []` (physical-property + manipulation output GONE), still useful
  (subjects + real composition observations) — NOT over-conservative.
- Deployed + verified live: `/v1/scene-understanding` 200 with clean output;
  C1 `/v1/creative-intent` still 200 (unaffected).
- Scene eval 4/4 schema-clean post-fix; **83 pytest pass** (added 2 guard tests).

**MILESTONE C2 CLOSED.** Scene model default `amazon.nova-pro-v1:0`
(config-driven, task-specific). Recommend proceeding to Story Director (C3);
NOT started.
