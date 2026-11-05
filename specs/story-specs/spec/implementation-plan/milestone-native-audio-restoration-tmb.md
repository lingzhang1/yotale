# Native-audio restoration (TMB + guitar) + immersive-audio V2-b scope

Status: 🟢 minimum fix implemented (iOS wiring) · device listening acceptance PENDING · V2-b immersive scope
PROPOSED (STOP for owner before broader V2-b). Date: 2026-10-11. No frozen prompt/contract change. Not pushed.

## 1. Actual TMB root cause (evidence, each layer tested independently — NOT inferred from category)
- **Suspect 1 (missing source audio): RULED OUT.** TMB-type source clips carry audio tracks (verified 2 audio
  tracks on the dir_tmb MOVs). Source ambience exists.
- **Suspect 3 (Edit Planner mutes meaningful sound): RULED OUT.** A reproduced TMB-style hiking EditPlan with
  `native_audio_priority=important` returned `native_audio = keep×4, duck×2` — NO mute of ambience segments.
  The planner is correct GIVEN a correct MusicPlan.
- **Suspect 4 (renderer): RULED OUT.** keep=1.0 + supportive music recedes; the mix preserves keep correctly.
- **ROOT CAUSE = Suspect 2 driven by Suspect 5:** MusicPlan rates TMB native audio `low`/`continuous` because
  it is STARVED of context. Direct test: a hike intent describing "wind, footsteps, conversation, stream"
  → `priority=important, role=supportive` ("ambience is emotionally central"); a thin "a hike" intent →
  `priority=low, role=continuous`. The iOS resolver sent MusicPlan **empty StoryGuide/StoryCoverage** AND the
  picker call sites passed `guideFramingSummary: nil`, so MusicPlan judged from a thin CreativeIntent alone →
  `low` → continuous music drowns wind/footsteps/conversation. Same CLASS as guitar, confirmed independently.

## 2. Guitar wiring-fix status
The approved Part-A fix was **NOT previously implemented** (no commit; resolver still sent empty objects). The
guitar Story only sounded fixed because its CreativeIntent text happened to be rich enough. Now implemented.

## 3. Minimum corrective change (smallest responsible layer = iOS input wiring)
`MusicSelectionResolver.recommend()` now **loads the Story's persisted StoryGuide (story_guide/1) + Coverage
and passes them to the MusicPlan request** instead of empty objects (fetched from SwiftData by storyId, same
pattern as StoryGuideCoordinator; empty object when absent). This gives MusicPlan the evidence to rate native
audio (performance OR meaningful ambience) `important` and keep the soundtrack supportive. Fixes guitar AND
TMB from one root. keep/duck/mute semantics untouched; no global floor; no mute/duck reinterpretation.
NOTE: the two picker call sites still pass `guideFramingSummary: nil` to recommend() — the Guide JSON now
carries the signal regardless, but threading the framing summary too is a cheap follow-up.

### 3b. TMB device verification (after 3a) + second fix
After 3a, the TMB device render STILL logged MusicPlan `priority=low` while music resolved fine
(`built soundtrackTrack=YES`). Isolation test proved WHY: a thin intent + EMPTY story_guide → `low`, but a
thin intent + RICH story_guide → `important`. So the device's TMB Story had **NO persisted StoryGuide** — my
loader correctly passed `{}` because there was nothing to pass. TMB (older/imported) reached music without a
Guide ever being generated. **Second fix:** `recommend()` now calls `StoryGuideCoordinator.ensureGuide(for:)`
(generate-once-if-absent, migration-safe) BEFORE loading the Guide, so a guide-less Story gets one and MusicPlan
sees it. Existing Guides are returned untouched; failure is fire-and-forget (Story stays valid). Still no
prompt/contract change.

## 4. Model/contract implications
NONE. No frozen music_plan/1 prompt change, no contract change, no renderer change, EditPlan/2 untouched. If,
WITH Guide/Coverage passed, MusicPlan still under-rated a clear ambience/performance Story on device, THEN a
versioned music_plan/2 prompt amendment would be proposed + STOP — but evidence says the input gap is the cause.

## 5. Audio regression results (reproduced server-side; DEVICE listening still required)
| Story | MusicPlan priority (with context) | EditPlanner native_audio | Expected mix |
|---|---|---|---|
| Guitar performance | important/supportive | keep on final performance | guitar dominant on payoff ✓ |
| TMB hike (ambience) | important/supportive | keep×4, duck×2 | wind/steps/convo audible ✓ |
| Birthday singing | (expected important) | — | vocals preserved (device) |
| SF music-forward | low/continuous OK | — | music leads ✓ |
| Quiet solitude | (expected selective/important) | — | ambience preserved (device) |
| Explicit music-only | low (user intent) | mute/duck OK | native may drop ✓ |
A schema-valid plan is NOT proof of correct audio — items needing ears are marked (device).

## 6. Physical-iPhone listening checklist (after rebuild)
1. TMB hike: wind, footsteps, and conversation clearly audible; music supports, does not drown.
2. Guitar: final performance dominant.
3. Birthday: singing intelligible.
4. SF montage: music leads (native low acceptable).
5. Solitude: quiet natural ambience preserved.
6. Explicit music-only request: native intentionally dropped (not forced audible).
Report native:soundtrack balance + any masking for each.

## 7. Revised V2-b immersive-audio scope (PROPOSAL — not implemented)
Builds on the V2-b P0 audio-continuity work. Achievable with EXISTING contracts (no new fields):
- **Meaningful environmental-sound preservation** — honored today via the planner's per-segment keep/duck
  once MusicPlan priority is correct (this fix). No new contract.
- **Local RMS/onset event evidence** — already in the V2-b `AVFoundationEvidence` sampler (boundary-only,
  on-device). Extend to flag speech/transient-rich segments. No contract.
- **Audio bridges (J/L)** — already scaffolded in V2-b (deferred to device). No contract.
- **Safeguard against masking speech/performance** — a deterministic renderer rule: when a segment is `keep`
  AND evidence shows strong onsets/voice band, clamp soundtrack gain lower under it. Renderer-only, no contract.
REQUIRES a versioned extension ONLY IF time-varying (within-segment) soundtrack gain is wanted (e.g. duck music
just during a spoken line): that needs a per-segment `soundtrack_gain_envelope` → propose **EditPlan/3**, STOP
for approval. NOT in scope now. NOT building audio separation. NOT building the whole V2-b milestone.

## STOP

## 8. DEVICE-CONFIRMED ROOT CAUSE (supersedes the earlier inference) — 2026-10-11 13:24
On-device DEBUG readout from a regenerated TMB render (now shown on the completed screen):
`native_audio[duck×12 keep×7 mute×6] role=continuous priority=selective` (25 segments).
Gain table consequence: duck→native 0.25 under soundtrack 1.0 (role=continuous); mute→native 0.0; keep→native
1.0 under soundtrack 0.2. So **18 of 25 segments (72%) have native audio ducked-under-full-music or muted** —
that is why TMB plays music-only. This is NOT the MusicPlan priority I chased earlier (the Guide/ensureGuide
fixes correctly moved priority off `low` to `selective`); it is the **Edit Planner's per-segment native_audio
decision**.

Earlier "device sent an empty StoryGuide" was an INFERENCE and is withdrawn — the backend does not log guide
presence, so it was never evidence. The histogram above is the actual evidence.

### Primary fault — frozen Edit Planner v4 prompt has no concept of meaningful ENVIRONMENTAL sound
`prompts/edit_plan/4/system.md` native-audio clause ends:
> "If a Moment's own sound is the emotional payoff (a real guitar performance, birthday singing, meaningful
> dialogue), native_audio=keep. Otherwise duck or mute."
A hiking Story has no "performance" and no "dialogue" by that list, so the model dumps wind/footsteps/water/
ambient-conversation to duck/mute. Guitar works precisely because it matches "a real guitar performance" → keep.

### PROPOSED versioned amendment — edit_plan/5 (NOT applied; frozen prompt, owner gate)
Clone prompts/edit_plan/4 → prompts/edit_plan/5, change ONLY the native-audio clause's last two sentences to
add meaningful environmental sound as a keep trigger, e.g.:
> "native_audio=keep when the Moment's own sound carries meaning — a performance, singing, intelligible
> conversation, OR meaningful environmental/ambient sound the Story is partly about (wind, footsteps, water,
> a crowd, laughter). Use duck when the captured sound is minor but should still be present under the music;
> use mute only when the captured sound is noise or empty. When MusicPlan.native_audio_priority is important or
> selective, bias toward keep for ambience-driven Stories."
Nothing else in the prompt changes. Bump the handler/version pin to edit_plan/5 behind the existing env knob so
it is A/B-testable against v4. Contract (segments carry keep/duck/mute) is UNCHANGED — no schema change.

### Secondary candidate (do NOT change without owner go — owner forbade reinterpreting duck/role globally)
Renderer `soundtrackGainUnder`: under a `duck` segment with role=continuous the soundtrack stays at 1.0 while
native is 0.25 — so "duck" buries the native rather than lowering the music. This may be intended, but it means
`duck` can never yield audible ambience. NOT proposing a change; flagging it. If the prompt fix alone (more
`keep`) restores TMB audio on device, this needs no touch.

## STOP (updated)
Root cause CONFIRMED on device: Edit Planner marks meaningful ambience duck/mute (18/25). Smallest responsible
layer = the Edit Planner prompt, which is FROZEN → versioned edit_plan/5 amendment PROPOSED above, awaiting owner
approval before any prompt file is created. iOS wiring fixes (guide pass-through + ensureGuide) remain correct
and committed. Diagnostics (completed-screen readout + native_audio histogram) added, not yet committed. Not pushed.
