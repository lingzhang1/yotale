# Milestone M-c — MusicDirection inference + Figma MUSIC integration (IMPLEMENTED)

**Status: IMPLEMENTED (backend + iOS), not yet device-verified.** No track provider, no catalog,
no MusicAnalysis, no audio infrastructure, no Edit Planner. Create My Story stays disabled.

## What M-c does
Makes the frozen Figma MUSIC experience real as *intelligence only*: the "♫ Music" line on
"Here's what I understood" (Creative Direction summary) now shows a REAL inferred MusicDirection
(intended soundtrack feel), with the Figma "Change →" sheet to edit it. The actual-track surfaces
(Choose music / preview / playback) remain visibly disabled — that is M-d.

## Inference decision — DETERMINISTIC, no model call
MusicDirection is inferred by `DeterministicMusicDirectionEngine` (`packages/music_direction`), a cheap
categorical projection of the already-resolved CreativeIntent (`desired_feeling`, `style_tags`, `pace`,
`summary`) plus `StoryGuide.framing_summary` as lightweight creative context:
- `pace` → `energy` (slow→low, moderate→medium, fast→high; absent → no energy, never fabricated).
- `desired_feeling` + `style_tags` → `mood_tags` (keyword map, dedup, order-stable; falls back to the
  intent's own feeling words; never invents a generic feel).
- framing (or summary) → one-line `summary`.

**Why no new model call:** CreativeIntent is already the product of the (Opus) resolver; MusicDirection
is a lightweight feel, and a second model call would add cost + latency + a second place for the feel to
drift from CreativeIntent, with no evidenced quality gain. This matches the owner directive ("simplest
inference; do not assume another expensive Opus call") and mirrors the frozen Figma's own deterministic
`inferMusicLabel`. Does NOT consume StoryCoverage; not regenerated as Moments arrive.

## Endpoint
`POST /v1/music-direction` → `MusicDirectionContract` (music_direction/1). Body: `{creative_intent,
guide_framing_summary?}`. 422 on invalid intent (never fabricates). Deterministic dep provider
`get_music_direction_engine` (no `STORY_*_MODEL`, no gateway).

## iOS
- `StoryMusicDirectionModel` (SwiftData, `@Attribute(.unique) storyId`, `directionJSON`, `userAuthored`,
  `fingerprint`), registered in the ModelContainer (additive — SwiftData lightweight migration).
- `MusicDirectionService` (POST), `MusicDirectionCoordinator` (infer-once / user-override / reset / clear).
- Creative Direction `MusicDirectionRow` + `MusicDirectionSheet` (feel chips + free-text + "Let Story
  choose"), replacing the old disabled placeholder. Track selection stays a disabled section in-place.

## Behavior guarantees (tested)
- **Override precedence:** a user edit sets `userAuthored=true` and is NEVER overwritten by inference on
  relaunch / migration / Coverage recompute (`ensure()` returns it untouched, no infer call).
- **Legacy migration:** a Story created before M-c gets a default inferred ONCE on Story Home open
  (non-blocking, no recreation); a valid user-authored direction is preserved.
- **Regenerates nothing:** changing MusicDirection does not touch CreativeIntent / StoryGuide /
  StoryCoverage / MomentUnderstanding. It only bumps `fingerprint`, which a FUTURE MusicPlan cache
  compares to invalidate itself (MusicPlan is not persisted yet — M-b froze the contract only).

## Tests
- Backend: `apps/api/tests/test_music_direction.py` — 7 tests (pace→energy, feeling/style→mood_tags,
  Guide framing as context, graceful fallback, determinism, endpoint round-trip, 422). Full suite 156 pass.
- iOS: `apps/ios/Story/StoryTests/MusicDirectionTests.swift` — 8 tests (infer-once, persistence/relaunch,
  user override not lost, legacy migration, fingerprint staleness, inference-failure safety, DTO decode).
  `swiftc -parse` clean on all 7 iOS files. NOT verified: Xcode build, XCTest run, on-device render.

## Deployment
Backend adds `/v1/music-direction`. **Deploy required** for the device to exercise inference (the live
App Runner lacks the route until redeployed). See the device checklist in the session report.

## Commits
- app `61d6448` (backend engine + endpoint), `c395f4e` (iOS layer).
- specs: this file.

## NOT started
M-d (track sourcing — research brief only), Edit Planner, Media Engine.
