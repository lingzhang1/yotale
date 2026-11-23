# Milestone: AI Ideas latency (scene scan + Director)

Status: merged (PR #163, `ceb62e0`), deployed to dev and device-tested on dev (2026-11-23). Results in section 6.
Ling's device build ran the iOS changes on dev. Beta deploy follows this doc update.

## 1. Baseline (beta, 2026-11-23 04:42 UTC, one run)

Measured from the WAF log (request arrival), API handler logs (model time) and the access log (response sent).

| Step | Upload received | Model call | Server total |
|---|---|---|---|
| Scene scan `/v1/scene-understanding` (5 frames, 576 KB) | 20.2 s after arrival | gpt-5.1, 7.5 s | 27.8 s |
| Phone gap between the two calls | | | 0.9 s |
| Director `/v1/director/initialize` | under 0.1 s | gpt-5.1, 28.3 s (6.1k in, 2.0k out) | 28.6 s |
| **Total** | | | **57.3 s** |

The handler's `latency_ms` (7,551 ms for the scan) starts after the upload is fully received, so it hides the
upload wait. An AU upload (1.44 MB) was in flight on the same 2-connection `backgroundSession` when the scan
was sent. That the scan queued behind it is an inference, not proven.

## 2. Changes

### 2.1 Scene scan gets its own URLSession (iOS)

`StoryBackend.sceneScanSession` in
`apps/ios/Story/Story/Data/Contracts/CreativeIntentService.swift`, used by `SceneUnderstandingService`. Same
timeouts as before (180 s request, 300 s resource), own connection pool. `backgroundSession` (2 per host)
still carries AU, media upload and media download.

### 2.2 Background queues hold while AI Ideas waits (iOS)

`InteractiveAIHold` (`apps/ios/Story/Story/App/InteractiveAIHold.swift`). While a hold is active, the AU queue,
the media upload queue and the generated-output backup queue start no new job. A job already in flight always
finishes, so no billed AU request or part upload is cancelled. When the last hold ends, `onRelease` (wired in
`StoryApp`) re-drains all three queues. A hold expires on its own after 90 s.

- Camera AI Ideas (`ContinuousCaptureModel`): held while `aiState` is `.scanning` or `.thinking`.
- Scene scan flow (`SceneScanFlowView`): held while the state is scanning, analyzing or planning, and released
  on disappear.
- The AU continued-processing supervisor does not relaunch a drain during a hold, so a hold is not counted as
  a fruitless launch.
- A held drain burns no attempt and leaves the job PENDING (unit test `InteractiveAIHoldTests`).

The hold starts when the scan starts (about 4 s before the upload), which gives an in-flight job a little time
to finish. It cannot stop a job that started before the scan.

### 2.3 Smaller scan frames (iOS)

`SceneFrameProcessor` longest side 1024 px to 768 px, JPEG quality unchanged at 0.6. Expected about half the
bytes per frame (0.56x the pixels). Not yet measured on device. Scan quality at 768 px is unverified.

### 2.4 Shorter Director output (backend, `story_director/v3`)

The v2 output wrote the same shot up to four times: in `plan.shots`, in `decision.shot`, in `candidates[0]`
(a required copy of the decision) and in `director_state.last_decision`. v3 has the model write each thing once.
The server rebuilds the old wire shape, so `DirectorOutput` and iOS are unchanged.

| Model writes (v3) | Server rebuilds |
|---|---|
| `decision.plan_shot_id` instead of a repeated shot | `decision.shot` = copy of that plan shot (same UUID and reference query) |
| `alternatives` (up to 2, never the decision) | `candidates` = `[decision, *alternatives]`; empty when there are none |
| no `director_state.last_decision` | `last_decision` = the decision |
| no `concept.rationale` (not shown in the app) | absent |

The prompt also caps the internal `reason` and `purpose` fields at one short sentence. The user-facing
`instruction` is not shortened.

Safety and fallbacks:
- A legacy v2-shaped output (full decision shot, `candidates`, `last_decision`) still validates.
- A shot-bearing decision whose `plan_shot_id` does not resolve falls back to the plan shot for the current
  beat, else the first plan shot, instead of failing the request. With no plan shot it still fails integrity.
- An alternative whose reference does not resolve is dropped. The safety guard still checks every alternative.
- `max_tokens` stays 2200. Rollback: point `PROMPT_VERSION` and `_PROMPT_DIR` back at v2 (kept unchanged).

Expected effect: the duplicated decision, candidate and state copies were roughly a third of a typical output.
At about 10 s per 1k output tokens (the planner trend), that would be several seconds. This is an estimate;
it has not been measured.

## 3. Not changed

Director model, temperature, scene-understanding prompt and model, frame count (5), `next` request shape.

## 4. Tests

- Backend: `apps/api/tests/test_story_director_engine.py` adds lean-output tests (schema, rebuild, no
  alternatives, cap and drop, unsafe alternative, request text, legacy shape, fallback). Full API suite:
  1079 passed, 47 skipped.
- iOS: `apps/ios/Story/StoryTests/InteractiveAIHoldTests.swift` (hold toggles, single release, held AU drain
  makes no request and burns no attempt, runs after release). Not run; needs Xcode.

## 5. How to measure

Run AI Ideas on dev with the new build and backend. The Director handler logs output tokens and model time;
the WAF and access logs give scan arrival and response times. Compare with section 1. Record results here.

## 6. Results (dev, 2026-11-23, `ceb62e0`, Ling's device)

Server times from the dev API logs. Upload time is not measurable on dev (no WAF log), so each total starts
when the scan upload was fully received (`resolved` time minus handler `latency_ms`).

| Run (UTC) | Scan frames / bytes | Scan model | Director model | Director tokens in / out | Scan received → idea |
|---|---|---|---|---|---|
| Beta baseline 04:42 | 5 / 576 KB | 7.5 s | 28.3 s | 6.1k / 2.0k | 37.1 s |
| Dev 09:42 | 4 / 106 KB | 4.8 s | 6.9 s | 5.6k / 786 | 12.9 s |
| Dev 09:55:04 (AU running) | 3 / 74 KB | 4.1 s | 6.6 s | 5.5k / 731 | 11.7 s |
| Dev 09:55:52 (AU running) | 4 / 117 KB | 4.7 s | 5.8 s | 5.6k / 666 | 11.5 s |

Ling confirmed the idea card still offered alternatives ("Try another idea").

**Upload hold, checked against AU arrival times.** AU upload-complete time = response time minus handler
`latency_ms`; the AU queue ran two workers.

- Run at 09:55:04 (hold about 09:54:58 to 09:55:15.9): AU jobs already in flight finished (one at 09:55:09,
  inside the hold). No AU upload arrived between 09:54:47.8 and 09:55:35.5.
- Run at 09:55:52 (hold about 09:55:46 to 09:56:03.8): the in-flight AU job finished at 09:55:51.3. The next
  two AU uploads arrived at 09:56:06.9 and 09:56:07.3, about 3 s after the Director returned, and none arrived
  in between. Without the hold the queue would have picked the next job right after 09:55:51.3.

Conclusion: during the hold no new AU job started, in-flight jobs finished, and the release re-drained both
workers. Media upload and output backup holds were not exercised in these runs (no upload traffic).

Not measured: phone-side scan upload time, and the effect of 768 px frames on scan quality.
