# Milestone: App-side video creation latency (iOS)

Status: **IMPLEMENTED on `perf/render-timing-logs` (draft PR #131), 2026-11-18. Offline only. NOT merged, NOT device-verified, NOT quality-accepted.**

## 1. Measured baseline (device, before this milestone)

Ling's iPhone 16 Pro, dev backend, `perf/render-timing-logs` at `012a36b`. 66 Moments, 56 shots, 138 s output, music on.

| Stage | ms | Where it runs |
|---|---|---|
| build_request | 470 | main actor |
| evidence_refs | 226 | main actor |
| evidence_prepare | 44,343 | main actor, awaiting network (62 cache hits, 4 misses, 66 sheets, 7.6 MB) |
| encode_request | 4 | main actor |
| submit_job | 3,846 | network |
| plan_poll | 171,037 | network (server: 2 model calls, 137k in / 10.5k out tokens, 1 repair) |
| pre_render_restore | 221 | 0 downloads |
| validate_plan | 3 | main actor |
| **creative_refine** | **282,798** | **main actor, synchronous** |
| soundtrack_preload | 9,079 | off main (0.4 s on earlier runs) |
| build_composition | 612 | off main |
| export | 24,580 | AVAssetExportSession |
| persist_output | 28 | main actor |
| **create_total** | **537,329** | |

A second Create (68 Moments, 290 s target) failed in the backend; see section 7.

## 2. P0: creative refinement

**Root cause of it running.** `CreativeRefinementV2b` was added opt-in OFF (`d9e6ab4`, 2026-10-11), defaulted ON with an env/UserDefaults kill switch (`5126b08`, 2026-10-13), and became unconditional when P1-G0 removed the switch (`23b1ee0`, 2026-11-12). The call-site comment still said "OFF by default".

**What it did.** For every shot in every Original, Revise and Explore: search ±0.5 s around both cut points in 0.05 s steps, opening the clip again, decoding two exact frames and reading 0.2 s of audio per probe (about 43 probes per shot, about 2,400 for 56 shots), synchronously on the main actor. Then it re-validated and kept the result only if the whole plan stayed valid.

**Problems found in code.**
- It blocked the main thread for the whole stage.
- It changed source in/out while keeping `output_duration_seconds`, and the renderer maps the inserted span to the output duration (`scaleTimeRange`), so a nudged shot played slower or faster (down to 0.6× with its audio stretched).
- In a Revise it could move preserved shots and explicitly requested cut points by up to 0.5 s.
- It is not needed for correctness: `validate()` runs before it.

**Change (`43f3c78`).** The standard path renders the validated planner plan unchanged. The engine and its unit tests stay as an optional experiment. No flag was added. New test: the renderer receives the planner cut points unchanged.

**Quality comparison: NOT DONE.** The refined plan of the measured video exists only on the phone (not in the synced Story doc), and the original planner plan is in the server job record (copied to scratch before TTL). Rendering both needs either the product renderer on device or downloading the source originals for an offline frame comparison. Both need an owner decision.

**Future fast refinement (only if a comparison shows value).** One asset and decoder per clip, about 5 probes per cut with frame tolerance, AU events first, off the main actor, cancellable, a hard total budget, and output duration adjusted so speed stays 1×. Never the existing 2,400-probe loop behind a timeout.

## 3. P1: evidence retrieval (`7f30719`)

Phase A now runs a bounded task group, at most `evidenceFetchConcurrency = 4` Moments in flight. Per Moment the manifest -> download -> SHA verify -> unpack order is unchanged. Results are keyed by Moment id and every later step iterates the caller's order, so sheets, sheet order, the miss list and the single budget pass are identical to the sequential version. The server-side account/SHA/extractor checks and the client SHA check are untouched.

New timings: `evidence_fetch_one` (manifest, download, unpack ms, bytes, error class), `evidence_fetch_all` (max concurrency), `evidence_restore_misses`, `evidence_extract_and_tile`.

Tests: the bound is respected and lookups overlap; out-of-order completion gives byte-identical sheets in the same order; one slow failing lookup only affects its own Moment.

Projection, not a measurement: if the 44 s is round-trip dominated, 4-way overlap gives roughly 11-15 s.

## 4. P2: polling (`6fd3b2e`)

Foreground and active: 2, 3, 4, 5 s, then 5 s. Otherwise the previous 2, 4, 8, 15 s. Same endpoint, cancellation, transport retry, terminal and timeout handling. Projection for a 171 s plan: about 37 status reads instead of about 14, and completion noticed within 5 s instead of within 15 s. Each read is one authenticated DynamoDB GET.

## 5. P3: soundtrack preload

Unchanged. The stage only loads a local file's audio track and duration, off the main actor. The 9 s outlier followed the 283 s main-thread refine stage; the cause is unknown. Re-measure with refine removed before changing anything.

## 6. Main-thread audit and timeline (`e21849e`)

On the main actor: `build_request` (0.47 s, synchronous duration probes and AU parsing), `evidence_refs` (0.23 s, AU JSON parsing and a second duration probe), cache-hit ranking (small), validation and persistence. These touch SwiftData models and are sub-second, so they are left in place; the stall probe will show whether they matter. Off the main actor: evidence network/SHA/unpack, frame extraction and tiling, composition, export.

Timeline: every line carries `op=<8>` (attempt operation id prefix), `t=<ms since op start>` (read overlapping stages from `t`), and `mem=<MB>`. `main_thread` reports the longest main-thread stall, stalls over 250 ms and peak footprint. `output_backup_verified` marks the cloud backup, which is not on the critical path.

## 7. Separate backend reliability milestone (recorded, not fixed here)

- Job `f5350ca4` (68 Moments, 290 s target) failed `invalid_after_repair: output truncated at maxOutputTokens`. That string exists only in `packages/model_gateway/gemini_gateway.py`, so the OpenAI `gpt-5.1` primary raised a provider error first and the Gemini fallback ran out of its 8,192-token output budget three times. The planner's 16,384-token escalation never ran, because the Gemini adapter raises instead of returning a truncated result. Why `gpt-5.1` failed is not logged (60 s default request timeout is a hypothesis).
- Job `2f65c9fb` (66 Moments) used 137k input / 10.5k output tokens and two model calls; the repair was caused by a mistyped Moment id.
- Runtime `prompt_version` on dev is `edit_plan/5.6`.
- Remedies to evaluate: log the provider error and served model per call; Moment-ID aliases; deterministic id resolution instead of a full-model repair; more compact plan output; consistent truncation handling across adapters; a planner-specific request timeout. Raising the token limit alone is not sufficient.

## 8. Verification status

| | Status |
|---|---|
| Offline: `swiftc -parse` on every touched file | done |
| Offline: `RenderTiming.swift` iOS type-check | done |
| Sandbox `xcodebuild` | cannot run SwiftData/Observation macros; the four macro-free files show no errors or warnings. This is not a build. |
| CI (#131) | 4/4 pass; CI has no iOS job |
| Xcode device build, XCTest | owner |
| Device acceptance (section 10 of the brief) | owner |
| Quality acceptance | not started |
