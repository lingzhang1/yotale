# Milestone C — Scene Understanding: Implementation Design

**Status:** Approved for implementation design (design only — no real AI built).
**Date:** 2026-10-01
**Component:** Scene Understanding (scan → analyzer)
**Owner:** Asset / Scene Understanding (backend) — consumer: Story Director
**Output contract:** `SceneUnderstanding`
(`contracts/schemas/scene-understanding.schema.json`)
**Complements:** the product/semantics draft `04-scene-understanding.md` (kept as
rationale). Where the two differ, THIS doc + the frozen schema win.

This is a repo-aware plan for how Scene Understanding plugs into the existing
Milestone-A system. It does not implement real analysis — the analyzer stays
mock/unwired until the model work is green-lit.

---

## 0. Contract reconciliation — DONE

The canonical `SceneUnderstanding` contract was reconciled this milestone
(`ai_contracts.py`, `scene-understanding.schema.json`, Swift
`SceneUnderstandingContractDTO`, contract tests — 41 passed). Approved field set:

| Field | Type | Note |
|---|---|---|
| `id` | UUID | |
| `summary` | string (required) | observable scene characteristics, not direction |
| `environment_tags[]` | string[] | semantic scene classification (replaces `scene_type`) |
| `subjects[]` | `{label, note?, prominence?}` | `prominence` = `high\|medium\|low` (**added**) |
| `lighting?` | string | concise scalar (NOT an array yet) |
| `operator_space?` | `very_limited\|limited\|moderate\|open\|unknown` | **added**; visibility, not safety |
| `motion_opportunities[]` | string[] | observable movement possibilities (also holds "action" ones) |
| `composition_opportunities[]` | string[] | observable composition possibilities |
| `constraints[]` | string[] | visible limitations (crowded, low light, narrow, …) |
| `created_at` | datetime | ISO-8601 UTC |

`extra="forbid"` — unknown keys rejected. **Deliberately deferred** (experiments,
not yet fields): `scene_type`, `visual_opportunities`, `spatial_structure`
(fg/mg/bg/depth), array `lighting`, separate `action_opportunities`.

---

## 1. Where it plugs in (scan UX integration point)

Today `ShootMomentView.onAppear` calls `useCases.directNextMoment(for:)` (mock)
then opens `CameraCaptureView` to record a Moment. Scene Understanding inserts a
**scan step before direction**, and only when a scan is useful (draft §29):

```
ShootMomentView / Create Now
   │
   ▼
[optional] Scene Scan  "Show me what's around you"
   │   reuse AVCaptureSession (sample frames, do NOT record a Moment)
   ▼
local frame sampling + blur/dedup  → 3–5 representative frames (resized/compressed)
   ▼
POST /v1/scene-understanding  (multipart: frames + context)   ← NEW endpoint
   ▼
SceneUnderstanding  (schema-valid)   → attach to the CaptureSession
   ▼
Story Director (CreativeIntent + SceneUnderstanding)  ← real Director later
   ▼
Shot guidance → existing CameraCaptureView RECORD path (unchanged) → Moment
```

`CaptureSessionContract` already has `scene_understanding: SceneUnderstanding | None`
and `creative_intent` — so the scan result has a home with no contract change
(draft §28). Scanning is **optional**: skip it when the user follows a known shot
or recent scene context is sufficient (draft §29); the first implementation uses a
simple predictable flow, not scan-reuse heuristics.

**UX copy** (draft §9): "Show me what's around you" → camera → "Slowly move your
phone around the scene". Do not expose frame sampling, model terminology, or
upload architecture.

---

## 2. Reuse of existing AVCaptureSession infrastructure

`CameraCaptureController` (`Media/Camera/CameraCaptureView.swift`) already owns an
`AVCaptureSession` (preset `.high`), back wide-angle input, mic input, preview
layer, and is device-only. Reuse it in a **scan mode** that differs from record
mode:

- **Record mode (existing):** `AVCaptureMovieFileOutput` → temp `.mov` →
  `onFinish(url, duration)` → `MediaStore.adoptCapturedFile` (permanent Moment).
- **Scan mode (new):** add an `AVCaptureVideoDataOutput` (frame grabber) OR take
  periodic still images during a 3–5s pan; collect candidate `CGImage`/`CVPixelBuffer`
  frames in memory, never writing a `.mov` Moment. Expose a distinct callback,
  e.g. `onScanFrames([ScanFrame]) ` — NOT `onFinish`.

Keep the preview/record UI untouched; scan is a separate entry mode on the same
controller to avoid a second camera stack.

---

## 3. Temporary scan-frame lifecycle (ephemeral — NOT Moments)

**Hard rule:** scan frames must never use `MediaStore.adoptCapturedFile` and must
never become a `Moment`/`Asset`/permanent Story media (draft §28, §33).

```
camera (scan mode)
   → in-memory candidate frames
   → select 3–5 representative, resize/compress to JPEG
   → temporary cache dir  (e.g. NSTemporaryDirectory()/scene-scan/<sessionId>/)
   → multipart upload for analysis
   → on response (success OR failure): DELETE the cache dir
```

- Add a `SceneScanStore` (sibling to `MediaStore`, NOT a method on it) owning the
  temp dir, write, and guaranteed cleanup (defer/try-finally on both success and
  error paths, and a best-effort sweep of stale scan dirs on launch).
- Frames live only long enough to upload. No SwiftData model, no `AssetModel`.
- Original scan is not retained even if used for analysis (draft §28).

---

## 4. Representative frame sampling + blur/dedup strategy

Keep it lightweight (draft §10, §31) — no heavy CV:

1. **Sample candidates:** during the 3–5s pan, grab ~1 frame per ~0.3–0.5s
   (or N evenly-spaced stills) → ~8–12 candidates.
2. **Blur filter:** variance-of-Laplacian (or Core Image sharpness proxy) per
   candidate; drop the clearly-blurred.
3. **Near-duplicate filter:** cheap perceptual hash (downscale to small gray
   thumbnail, average/difference hash) → drop frames within a small Hamming
   distance of a kept frame.
4. **Diversity preserve:** keep visually distinct viewpoints.
5. **Cap:** final 3–5 frames (first experiment uses this range; measure).
6. **Resize/compress:** downscale (e.g. longest side ~768–1024px) + JPEG quality
   tuned for payload; the model does not need full-res (draft §32).

Thresholds (frame interval, blur cutoff, hash distance, count, resolution) are
**measured, not frozen** (draft §45, §51). Record them in observability (§9).

---

## 5. Multipart endpoint

```
POST /v1/scene-understanding
Content-Type: multipart/form-data
  - context  (application/json):
      { "capture_session_id": "...", "mode": "shoot_moment" | "create_now",
        "story_id": "..."?  }      // NO CreativeIntent fields — scene is intent-independent
  - frames[] (image/jpeg)          // 3–5 compressed representative frames

→ 200: SceneUnderstanding   (scene-understanding.schema.json)
```

- FastAPI handler validates **content type and total size** (04-infra §32/§44 —
  hard requirement) and rejects unsupported types / oversized payloads before
  touching a model.
- The handler calls the Scene Understanding engine → Model Gateway (§6) → parses
  + validates structured output (§7) → returns the canonical contract.
- **Intent-independence:** the endpoint does NOT accept CreativeIntent. Same scene
  yields the same SceneUnderstanding regardless of intent (draft §3.2); the
  Director combines them later.
- **No scene bytes persisted server-side** on this path — frames ride inline in
  the request and are discarded after analysis (privacy, §8).

---

## 6. Multimodal Model Gateway extension (generic, not scene-specific)

The gateway is currently text-shaped (`generate_structured(dict)->dict`, stub).
Extend it as a **generic multimodal capability**, usable by any engine — not a
Scene-Understanding-specific API:

```python
# packages/model_gateway — proposed generic multimodal surface (design only)
class ImageInput:
    data: bytes | str        # inline bytes or a reference the gateway can fetch
    media_type: str          # e.g. "image/jpeg"

class StructuredRequest:
    task: str                # domain task, e.g. "scene_understanding.analyze" (NOT a model id)
    schema: dict             # JSON Schema the output MUST satisfy
    prompt_version: str      # e.g. "scene_understanding/v1"
    context: dict            # structured/text context (capture context, etc.)
    images: list[ImageInput] # zero or more image inputs   ← the multimodal extension
    options: dict | None     # operational options (max_repair_attempts, etc.)

class StructuredResult:
    data: dict               # schema-valid payload
    usage: Usage | None
    attempts: int
    repaired: bool
```

Guarantees (shared with the Creative Intent gateway contract): enforce the schema;
bounded structured-output repair/retry; typed `StructuredOutputError` on
persistent failure (no silent fabrication); model chosen from **configuration**
keyed by `task` (no provider id in domain code — 03 §15, §34); emit observability.
`CreativeIntent` resolution uses the same surface with `images=[]`.

---

## 7. Structured-output validation

```
multimodal model → structured response → parse → Pydantic
   (SceneUnderstandingContract) → semantic validation → SceneUnderstanding
```
- `extra="forbid"` rejects unknown keys; enums (`operator_space`, `prominence`)
  reject bad values.
- Semantic checks beyond the schema: no shot/edit/intent language, no unsupported
  physical claims (draft §23) — a lightweight post-validator the analyzer applies.
- On invalid output: bounded gateway repair (§6); if still invalid →
  `StructuredOutputError` → retry/rescan behavior (§8). **Never manufacture
  observations** (draft §35, §39).

---

## 8. Retry / rescan + privacy / cleanup behavior

**Failure (draft §39):** camera denied, scan interrupted, frames unusable, network
down, model unavailable, malformed output, model can't interpret the scene.
```
analysis failure
   → preserve the CaptureSession (CreativeIntent intact)
   → delete scan-frame cache
   → allow retry / rescan
```
Do **not** fabricate a scene and do **not** silently substitute generic scene data
in MVP. (A deterministic non-visual degraded Director path could be an explicit
product decision later — not now, and not a fabricated SceneUnderstanding.)

**Privacy / cleanup (draft §33) — architecture, not cleanup-later:**
1. minimize scan duration; 2. sample only required frames; 3. resize/compress;
4. no permanent cloud storage (frames inline, discarded post-analysis);
5. temp cache auto-deleted on both success and failure; 6. scan frames never
become Story assets; 7. do not log image contents; 8. no training on scans
without a separate explicit privacy decision.

---

## 9. Observability (outside the domain object)

Log per scan, never in `SceneUnderstanding`: `operation`, `model`, `provider`,
`prompt_version`, `latency_ms`, `frame_count`, `compressed_payload_bytes`,
`attempts`, `structured_output_ok`, `usage`/cost when available, `correlation_id`.
Do NOT log raw scene images. These metrics decide the open experiments
(frame count, resolution, model, sync-vs-async). Reuses the 03 §37a log shape.

---

## 10. Transport hypothesis (simplest first)

```
iPhone → 3–5 resized/compressed frames → multipart HTTPS → FastAPI
       → Model Gateway → multimodal model → structured SceneUnderstanding
```
Prefer this **ephemeral synchronous** path. Do **NOT** introduce S3, presigned
upload, polling, SQS, or async jobs unless **measured** payload/latency shows the
sync path is inadequate (03 §31, 04-infra §19; same discipline as Creative Intent).
Record payload size + latency during evaluation to make that call on evidence.
Watch the App Runner 120s timeout: a few compressed frames should be well inside
it, but it is a measured guardrail.

---

## 11. Prompts & evaluation hooks

- **Prompts** versioned/externalized: `prompts/scene_understanding/v1/{system.md,
  examples.json, schema.json}` + `current`. The prompt demands observable facts,
  meaningful spatial relationships, useful constraints, conservative uncertainty;
  it prohibits shot/story/edit recommendations, invented capabilities, and safety
  certification (draft §36).
- **Eval fixtures** `evals/scene-understanding/`: office, busy urban, mountain
  trail, cafe, birthday, landscape-without-person, and a **weak/boring**
  environment (must report limited opportunities, not invent cinematic features —
  draft §44).
- **Two-layer eval (draft §41–43):** Layer 1 = representation quality (accuracy,
  relevance, spatial usefulness, constraint awareness, hallucination,
  compactness). Layer 2 = **Director utility** — compare Director output on
  intent-only vs intent+object-labels vs intent+full SceneUnderstanding. If the
  full contract doesn't materially improve Director, it's over-designed.
- **Frame-count eval (draft §45):** 1 vs 3 vs 5–6 frames → coverage, hallucination,
  Director quality, latency, payload, cost. Find the smallest sufficient set.

---

## 12. Open experiments — KEEP MEASURABLE (do not silently resolve)

Per the user's explicit instruction, these stay experiments, decided by evidence:
1. **Does Story Director also receive raw frames?** (not assumed; §48/§49 of the
   draft keep pipelines A/B/C open.) The architecture preserves SceneUnderstanding
   regardless.
2. **Does explicit `spatial_structure` become necessary?** (added only if Director
   eval shows summary + subject notes + composition_opportunities + operator_space
   are insufficient.)
3. **Do more/fewer frames improve Director quality?**
4. **Does S3 / async transport become necessary?** (only on measured payload/latency.)
Also open (draft §51): minimum frame count, resolution, blur/dedup value,
facts-vs-opportunities, SceneUnderstanding reuse window within a CaptureSession,
best multimodal model tradeoff.

---

## 13. Definition of Done (implementation — draft §53)

- real iPhone performs the lightweight scan; representative frames generated
  locally; only task-appropriate compressed data leaves the device;
- backend invokes a real multimodal model via Model Gateway;
- output validates against `scene-understanding.schema.json`;
- failed analysis retried without losing CaptureSession state;
- scan frames never added to Story media (verified);
- eval fixtures cover the major scene classes; hallucination/grounding reviewed;
- latency, payload size, cost measured;
- Director eval shows SceneUnderstanding materially beats intent-only / basic-object
  baselines.

Then SceneUnderstanding becomes a real upstream dependency of Story Director.
**No real AI is implemented by this document.**
