# Native-audio disappearance — root-cause audit (Guitar Practice)

Status: 🔵 DIAGNOSIS COMPLETE — minimum fix PROPOSED, STOP for owner gate (no code changed; the fix is iOS
input wiring, NOT an isolated renderer bug, so it waits for approval). Date: 2026-10-11. Not pushed.

## Symptom
Guitar Practice video has background music but the guitar performance is inaudible.

## Phase 1 — actual rendered decisions (evidence, not inference)
- **MusicPlan (live logs, every guitar create):** `native_audio_priority=low, soundtrack_role=continuous`.
- **EditPlan/2 (reproduced from the real AU audit, live /v1/edit-plan):** 7 segments,
  `native_audio = {mute×2, duck×4, keep×1}` — crucially **seg5 (the 18s final performance) = `keep`** (native
  1.0). The planner DID preserve the payoff's native audio. Practice clips ducked/muted (reasonable).
- **Renderer mix (NativeAudioPolicy):** on the `keep` performance with `priority=low` → soundtrack sits at
  0.35 under native 1.0; on duck/mute segments music plays at 1.0. So continuous music at 1.0 across the
  ducked segments + 0.35 over the kept performance is enough to mask a quietly-recorded guitar.

## Root cause — isolated by direct test, NOT guessed
Called /v1/music-plan twice:
- EXPLICIT guitar-performance intent → `priority=important, role=supportive`, guidance "native guitar must be
  fully audible." **Correct.**
- VAGUE intent ("a nice day") → `priority=low, role=continuous`. 
The MusicPlan **prompt and model are CORRECT** (the v1 prompt explicitly says protect performance native
audio). The defect is **E (missing evidence) → manifests as A**: the iOS resolver sends MusicPlan the
CreativeIntent + MusicDirection but **withholds StoryGuide/StoryCoverage** (`storyGuide: .object([:])`,
`storyCoverage: .object([:])` at MusicSelectionResolver.swift:62) — even though it already HAS a
`guideFramingSummary` in scope. Without the Story's richest "what this actually is" signal, MusicPlan can fall
to `low` for a performance Story → music drowns the kept guitar.

NOT the cause: B (Edit Planner — it correctly `keep`s the performance), C (renderer preserves keep correctly),
pure D (the gain imbalance is downstream of the wrong `low` priority).

## Phase 2 — correct behavior (agreed)
Performance Stories: native stays clearly audible, soundtrack supports/recedes, continuous performances not
interrupted, soundtrack may fade under the payoff. Other Stories: incidental noise may duck/mute, speech/
meaningful events stay intelligible. Explicit music-only request: native may be dropped. (No global floor.)

## Phase 3 — minimum fix (smallest responsible layer = iOS input wiring)
**Pass the real StoryGuide (+ StoryCoverage when available) into the MusicPlan request** so MusicPlan rates
native-audio priority on full evidence. One change in MusicSelectionResolver.recommend(): send the resolved
guide/coverage instead of empty objects (the `guideFramingSummary` is already in scope; thread the fuller
guide JSON through). **No prompt change, no contract change, no renderer change, EditPlan/2 untouched.** If,
with the guide passed, MusicPlan STILL under-rates a clear performance, THEN a versioned music_plan/2 prompt
tweak-performance-signal correction would be the next step — but evidence says the input gap is the cause.

## Phase 4 — regression plan (to run after the fix, device where noted)
1. Guitar learning + final continuous performance → native dominant on payoff. (device)
2. Birthday singing → vocals audible. (device)
3. Dialogue Story → speech intelligible.
4. TMB hiking (wind/footsteps) → meaningful ambient preserved, not drowned. (device)
5. SF music-forward montage → music leads (native low OK).
6. Quiet solitude ambient → ambient preserved.
7. Explicit music-only request → native may drop (not forced).
A schema-valid plan is NOT sufficient — verify actual audio on device for 1,2,4.

## Phase 5 — owner gate
Reported above. The fix is input wiring (not an isolated renderer bug) → STOP for approval before implementing.
No frozen prompt/contract touched. Not pushed. V2-b not resumed.
