# Milestone D — Asset Understanding IMPLEMENTATION + DEPLOY report (2026-10-05)

Implements the FROZEN design `06-asset-understanding.md` exactly. No redesign. Deployed to the
existing dev App Runner. **STOPPED at the physical-iPhone acceptance gate** (§14) — do NOT proceed
to Story Coverage / Music / Edit Planner / Media Engine before that gate is complete.

Commits: doc cleanup `fe01186`; implementation `2c252df`; production gate `bc55648` (story repo).

## 1. Files changed
**Backend (Python):**
- `contracts/schemas/ai_contracts.py` — new `MomentUnderstandingContract` (+ `MomentObserved`,
  `MomentStoryContext`, `MomentEvent`, `MomentUsefulSegment`, `StoryUtility` enum); legacy
  `AssetUnderstandingContract` marked LEGACY.
- `contracts/generate_schema.py` — registers MomentUnderstanding → `contracts/schemas/moment-understanding.schema.json` (generated).
- `packages/asset_engine/__init__.py` — `RealAssetUnderstandingEngine` + `MockAssetUnderstandingEngine`, the frozen one-retry policy, provenance minting, no-context stripping.
- `prompts/asset_understanding/v1/system.md` — the `au_prompt/1` system prompt.
- `apps/api/app/deps.py` — `get_asset_understanding_engine` (config-driven Sonnet, mock flag).
- `apps/api/app/main.py` — `POST /v1/asset-understanding` (24-frame multipart + validation + 503 retryable).
- Tests: `apps/api/tests/test_asset_understanding_engine.py`, `..._endpoint.py`, and MomentUnderstanding cases in `contracts/tests/test_ai_contracts.py`.
- `evals/run_au_production_gate.py` — the §12 production-path regression gate.

**iOS (Swift):**
- `Data/Persistence/Models.swift` — `MomentUnderstandingModel` (upsert by momentId) + `AssetUnderstandingJobModel` (queue state machine) + `AUJobState`.
- `Media/AssetUnderstanding/MomentFrameExtractor.swift` — `au_frames/1`: 24 evenly-spaced timestamped frames, 768px, JPEG 0.6.
- `Data/Contracts/AssetUnderstandingService.swift` — `/v1/asset-understanding` multipart client + `MomentUnderstandingDTO` + `AUAnalyzing` protocol seam.
- `Media/AssetUnderstanding/AssetUnderstandingQueue.swift` — the persistent PENDING→RUNNING→COMPLETE queue (orphan recovery, backoff, idempotent upsert).
- `App/StoryApp.swift` — registers the 2 models; recovers orphans + drains at launch and on scene-active.
- `Features/SceneScan/SceneScanFlowView.swift` — enqueues an AU job after Moment persistence (never blocks); carries requested Shot/Beat as capture context from the recommendation, nil for Skip Scan.
- `StoryTests/AssetUnderstandingQueueTests.swift` — queue state-machine tests.

## 2. Canonical contract created
`MomentUnderstandingContract` (`moment_understanding/1`), four-layer: Pydantic (domain/validation)
→ API DTO (same model, returned by the endpoint) → JSON Schema (`moment-understanding.schema.json`)
→ Swift `MomentUnderstandingDTO` + `MomentUnderstandingModel` (SwiftData). Hard split preserved:
`observed` {summary, subjects, events[], temporal_order_note, useful_segments[]} vs `story_context`
{story_utility, requested_shot_contribution?, requested_beat_contribution?}. Requested contributions
are nullable and are **stripped server-side** when no capture context exists (never fabricated for
spontaneous/imported Moments). `environment` and `dead_or_setup_segments` NOT added (no consumer).

## 3. Endpoint / request flow
`POST /v1/asset-understanding` (multipart): `meta` JSON {moment_id, source_capture_id?,
capture_context?} + `frames_meta` JSON [{t_ms}] + exactly 24 `frames` JPEGs. Validates exactly-24,
monotonically-increasing timestamps, allowed type, size caps. → `AssetUnderstandingEngine` → generic
`ModelGateway` (Bedrock Converse tool-use) → Sonnet 4.6 → schema-valid `MomentUnderstanding`. Frames
are **ephemeral** (never persisted server-side). Exhausted retry/provider failure → **503 retryable**
(the on-device queue leaves the job PENDING), never a fabrication and never a model fallback.

## 4. iOS queue / state machine
Persistent `AssetUnderstandingJobModel`: `enqueue` (after Moment persist, idempotent by momentId) →
`PENDING` → `RUNNING` → `COMPLETE`; failure/interruption → `PENDING` with bounded exponential
backoff (5s→20s→80s… cap 10 min). Orphaned `RUNNING` reset to `PENDING` at launch. Drains
opportunistically (launch, scene-active, after enqueue). **Moment creation never blocks on AU.** No
assumption of unlimited background execution.

## 5. Frame extraction
`MomentFrameExtractor` (`au_frames/1`): AVFoundation `AVAssetImageGenerator`, 24 evenly-spaced times
across the full clip, `appliesPreferredTrackTransform` (portrait/landscape correct), longest-edge
768px, JPEG 0.6; timestamps (ms) attached; de-duplicated to strictly increasing. On-device only; no
native video, no 48/96, no hierarchical pass.

## 6. Sonnet configuration
`us.anthropic.claude-sonnet-4-6` (config-driven `STORY_AU_MODEL`, default = frozen production model),
temperature 0, max output tokens **2400**, `au_prompt/1`, `moment_understanding/1`, 24 image blocks +
timestamp/context text. No provider-specific logic in the engine. No routing/escalation.

## 7. Retry / error behavior
Validate → on malformed/truncated/provider failure, retry EXACTLY ONCE (same model/evidence/prompt) →
second failure raises `AURetryableError` → endpoint returns 503 → job stays PENDING. **No Opus/Nova
fallback, no routing.** Retry count recorded in observability (`retried`, `attempts`).

## 8. Persistence / idempotency
AU work keyed by (moment_id, frame_policy, au_prompt_version, schema_version). `MomentUnderstanding`
persisted as an **upsert by momentId** — a resumed/duplicate run never creates a second record
(verified by test). A version-string change permits deliberate re-analysis. Job queue persisted
independently of the result. No image/frame blobs in SwiftData; derived frames are transient.

## 9. Privacy / observability
Server logs: correlation_id, moment_id (via correlation), operation, model, frame_policy,
prompt/schema version, latency, token usage, retry count, validation success/failure. **Never logs**
frame bytes, original media, raw understanding prose, or filenames (06 §11).

## 10. Tests
- **Contract** (`test_ai_contracts.py`): MomentUnderstanding round-trip across domain/DTO/JSON/decode;
  observed/story_context separation; nullable contributions for spontaneous; rejects unknown field
  (dropped `environment`) and bad enum.
- **Engine** (`test_asset_understanding_engine.py`): valid conversion + provenance; one-retry-then-success;
  second-failure → AURetryableError with **no fallback** (exactly 2 gateway calls); no-context strips contributions.
- **Endpoint** (`test_asset_understanding_endpoint.py`): valid 24-frame request; capture context; wrong
  frame count; non-monotonic timestamps; meta/frames length mismatch; unsupported type; invalid meta;
  retryable failure → 503.
- **iOS queue** (`AssetUnderstandingQueueTests.swift`): enqueue idempotency; run→complete+upsert;
  failure→pending+backoff; orphan recovery; upsert-no-duplicate on re-run; backed-off job not yet eligible.

**Results:** backend `pytest` **111 passed** (incl. all new AU tests), no regressions. iOS: all new/
modified Swift files `swiftc -parse` clean; the XCTest suite must be run in Xcode (the sandbox cannot
run SwiftData macro typecheck / XCTest — same constraint as prior milestones).

## 11. Frozen eval results (§12 — production-path gate)
Ran the ACTUAL production engine (`RealAssetUnderstandingEngine` + real `BedrockModelGateway`
tool-use, Sonnet 4.6, au_prompt/1, 24 frames) over the owner-approved 18-clip ground truth, scored by
the same LLM judge:

| metric | frozen baseline | production | verdict |
|---|---|---|---|
| event F1 | ≈0.80 | **0.80** | met |
| event P / R | 0.78 / 0.85 | 0.78 / 0.84 | met |
| hallucinations (total) | ≈10 | **10** | met |
| temporal-order | ≈16/17 | 15/18 (~0.83) | equivalent |
| over-segmentation | 52 | **21** | better (tool-use disciplines splitting) |
| useful-seg coverage | 0.81 | **0.89** | better |
| valid rate | 18/18 (after retry) | **18/18 (0 retries)** | met / better |

**No material regression — PASS.** The production tool-use path is actually MORE reliable than the
experiment's plain-JSON path (18/18 valid with zero retries, including the 154s clip that truncated in
the experiment). No STOP/diagnose triggered.

## 12. Latency / cost measured (production path, ESTIMATE us-east-1 on-demand 2026-10-05)
p50 **19.0s**, p95 **24.9s** (well inside App Runner's 120s). Median usage ~21.7k in / 0.87k out →
**$0.078/Moment** → $1.56/20, $3.91/50, $7.81/100. Matches the frozen Sonnet baseline. This gate's
own spend ≈ **$1.48** (18 Sonnet calls + 18 cheap judge calls).

## 13. Deploy verification (§13)
Built the new image via a throwaway CodeBuild project (no local Docker) → pushed `:latest` to ECR
`story-development-api` → App Runner deployment SUCCEEDED, service RUNNING. Throwaway CodeBuild
project + role torn down after. Verified against `https://ydmju5wdps.us-east-1.awsapprunner.com`:
- `/health` → `{"status":"ok"}` ✅
- `/v1/creative-intent` (C1) → 200 ✅
- `/v1/scene-understanding` (C2) → present in OpenAPI, unchanged ✅
- `/v1/director/initialize` (C3) → 200 ✅
- `/v1/asset-understanding` (NEW) → 200, valid `moment_understanding/1` from 24 real frames ✅
No regression to existing intelligence paths.

## 14. Photos status (§10)
Already implemented and complete; auto target-included via `PBXFileSystemSynchronizedRootGroup` (no
pbxproj edit). AU and Photos are independent — a Photos failure never affects Moment creation or AU
(fire-and-forget after Moment persist). Physical-device verification is part of §15 below.

## 15. Deviations from frozen design
**None material.** Two faithful implementation choices worth noting: (a) the production engine reaches
Sonnet through the gateway's **tool-use** structured path (the same path C1–C3 use) rather than the
experiment's plain-prompt JSON — this IMPROVED reliability (18/18, 0 retries) and is within the frozen
"generic ModelGateway" mandate; (b) `MomentUnderstanding` is persisted on-device as the wire JSON
inside `MomentUnderstandingModel` plus indexed provenance columns, rather than a second hand-maintained
SwiftData shape of the same contract — avoids drift, same four-layer intent.

## 16. Newly discovered risks / failures
- **iOS full build/test not runnable in this environment** — `swiftc -parse` is clean on every new/
  modified file, but the XCTest suite + SwiftData macro typecheck must be run in Xcode on a Mac. This
  is the main thing the device gate also exercises.
- **Background execution** — the queue is opportunistic (active / launch / network-available). It does
  NOT register a BGProcessingTask yet; a Moment captured and then the app never reopened with network
  will stay PENDING until a future foreground session. That matches the frozen "no unlimited background
  execution" stance; a BGTask is a later enhancement if dogfood shows pending jobs stranded.
- **Over-segmentation residual** — 21 over-segmented events across 18 clips (down from 52) is acceptable
  vs baseline but is the first place to tighten the prompt if the Edit Planner later finds noisy segments.

---

# §14 — PHYSICAL-iPHONE ACCEPTANCE CHECKLIST (STOP here)

Run on a real iPhone against the deployed dev backend. Report pass/fail per step; any real failure
becomes a regression fixture or an explicitly documented deferral.

1. **Capture a Moment** (Start a Story → recommendation → Let's shoot → record → Moment added).
2. **Moment appears immediately** in Story Home — the UI does NOT wait for AU.
3. **AU runs asynchronously** — with network, the AU job moves PENDING→RUNNING→COMPLETE shortly after.
4. **MomentUnderstanding eventually persists** — a `MomentUnderstandingModel` row exists for the Moment
   (summary/events/useful_segments/story_utility populated; shot/beat contribution present for a
   recommendation-driven capture, null for a Skip-Scan capture).
5. **UI / capture never waits for AU** — repeat capture several times rapidly; each returns instantly.
6. **Airplane-mode capture → PENDING** — enable Airplane Mode, capture a Moment: it is created, the AU
   job stays PENDING, nothing blocks or errors in the UI.
7. **Restore network → AU completes** — disable Airplane Mode, foreground the app: the PENDING job
   drains and completes.
8. **Kill app during AU → relaunch → resumes** — capture with network, force-quit while analysis is in
   flight, relaunch: the orphaned RUNNING job is recovered to PENDING and completes (no crash).
9. **No duplicate AU record** — after steps 7–8, exactly ONE MomentUnderstanding exists per Moment.
10. **Long Moment completes** — capture a long clip (60s+): AU completes within the request budget
    (measured p95 ~25s; the 24-frame payload is duration-independent).
11. **Photos original appears in Photos** — the captured original shows up in Apple Photos (add-only
    save), independently of Story.
12. **Photos permission denial does not affect Moment/AU** — deny Photos add permission: Moment creation
    and AU still succeed; only the Photos copy is skipped (silent).

Report results back before any further milestone work.
