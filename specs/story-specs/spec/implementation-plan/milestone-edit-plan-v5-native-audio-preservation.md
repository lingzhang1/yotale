# Native-audio preservation v5 + Customize Your Story — staged plan

Status: 🟡 STAGE 1 done (edit_plan/5 authored + v4-vs-v5 regression). **AT THE v5 FREEZE GATE — awaiting owner.**
Stages 3–7 (persistence, wiring, UX screen, renderer verify, device accept) NOT started. No frozen v4 edit.
Not pushed. Date 2026-10-11.

## 1. v5 prompt delta (the ONLY change vs frozen v4)
New file `prompts/edit_plan/5/system.md` = v4 VERBATIM except the **NATIVE AUDIO** clause. No schema change
(segments still carry keep|duck|mute). Selected by env `STORY_EDIT_PLAN_VERSION=5`; default stays `4`
(production untouched); unknown value falls back to `4`. `packages/edit_planner/__init__.py` resolves the
version/path from that env.

v4 (frozen): "If a Moment's own sound is the emotional payoff (a real guitar performance, birthday singing,
meaningful dialogue), native_audio=keep. **Otherwise duck or mute.**" → a fixed category list; everything else
reduced. This is why the hike (no "performance"/"dialogue") went duck×12/mute×6 → music-only.

v5 (the 7 owner principles):
- **DEFAULT TO keep.** Original captured sound is first-class material: environmental/atmosphere (wind, water,
  footsteps, street, crowd), human sound (performance, singing, laughter, meaningful conversation), texture.
- **NO fixed category list** — judge each segment's own audio on whether it serves THIS Story; do not reduce
  merely because it is "not dialogue or performance".
- **Reduce only for a specific EDITORIAL reason** (unusable audio; it masks something more important in the
  same stretch; the stretch is deliberately music-forward; the user asked). duck = present-but-under; mute =
  genuinely should not be heard.
- **Respect explicit preference** — music-led/only intent MAY duck/mute broadly (valid result); immersion/
  ambience biases hard to keep; priority important/selective → keep, low → broader duck/mute permitted.
- **Do NOT force every sound audible** — a stretch may legitimately be music-only; keep is the starting point,
  each duck/mute is deliberate.

## 2. Regression — v4 vs v5 (real Opus planner, synthetic inputs; local)
| Scenario | v4 native_audio | v5 native_audio | Read |
|---|---|---|---|
| TMB hike (immersive) | keep×6 | keep×6 | both keep* |
| Guitar performance | keep×3 | keep×3 | preserved ✓ |
| Birthday singing | duck×2 keep×2 | **keep×4** | v5 stops ducking the singing/laughter ✓ |
| SF montage (music-fwd) | duck×1 mute×5 | duck×2 mute×4 | music-forward honored by BOTH ✓ |
| Solitude quiet | keep×3 | keep×3 | ambience preserved ✓ |
| Explicit music-only | mute×4 | **mute×4** | v5 STILL allows intentional music-only ✓ |

GATE CHECKS: (a) v5 lifts meaningful ambience/human sound to keep where v4 ducked it (Birthday). (b) v5 does
NOT break intentional music-only (Explicit mute×4) or music-forward montage (SF mostly mute/duck). (c) feasible
for all; schema unchanged; renderer-compatible (same keep/duck/mute values the mixer already consumes).
LIMITATION (honest): with rich synthetic summaries even v4 kept TMB — the DEVICE TMB sent THINNER moment
summaries/events, which is why it got duck×12/mute×6. So this harness validates v5's DIRECTION and the
music-only safeguards; it does NOT reproduce the device duck/mute. True proof needs a DEVICE re-render on v5.

## 3–7. Remaining stages (NOT started — owner sequence, each independently testable)
3. **Sound-preference data model (Part C):** add `intentSoundPreference: String?` (enum immersive|balanced|
   music_led; nil = infer) to StoryModel — the SMALLEST change. Threads into MusicPlan.audio_strategy
   (role/priority) and is passed to the planner as an explicit-preference input (v5 already honors it). NOT a
   frozen-contract change if carried as an existing CreativeIntent field; if the music_plan/edit_plan request
   DTOs cannot carry it, propose a minor additive request-field extension (no response/schema change). Must NOT
   be silently overridden on regenerate — persist on the Story, re-read each run.
4. **Input wiring:** resolver/coordinator pass the preference into /v1/music-plan and /v1/edit-plan.
5. **Customize Your Story screen (Part B):** replace the duration sheet with Length (Highlights/Full/Custom via
   Duration Intelligence, no hardcoded durations, whole-row clickable) + Sound (Immersive/Balanced/Music-led,
   default Balanced unless CreativeIntent is clear). Figma visual language; no mixer/sliders.
6. **Renderer verify:** confirm keep/duck/mute + role map to the intended audibility; the duck-under-continuous
   observation stays flagged, not changed (owner: no global duck/role reinterpretation).
7. **Device acceptance:** the Part E checklist on real footage, comparing rendered AUDIO not JSON.

## 6. Contract implications
edit_plan/5: prompt-only, additive, env-gated — EditPlan/2 schema UNCHANGED. Sound preference (stage 3): aim to
carry inside CreativeIntent (no frozen change); only if impossible, a minimal additive request field. No frozen
EditPlan/2 or music_plan/1 semantic change. mute is never globally turned into duck.

## STAGE 1b — Real-TMB confirmation A/B (owner freeze condition) — 2026-10-11

### 1. Exact evidence used (Phase 1)
Source: `evals/story_coverage/real_moment_understanding.json` — REAL asset-understanding (MomentUnderstanding)
output for the TMB hiking domain: 15 narrative scenes (backpack, departure, scenic reveal, trail, human-scale,
river crossing, companionship/conversation 95s, end-of-day). Summaries + useful_segments used VERBATIM; NOT
enriched. Intent/MusicPlan set to an immersive hike (role=supportive, priority=important), guide/coverage {}.
LIMITATION (explicit): this is the closest available representation, NOT the exact failed device request. The
device's own CreativeIntent/Guide/Coverage/MomentUnderstanding for the specific TMB render that produced
duck×12/mute×6 live only on the phone and could not be recovered here. Consequently v4 on THESE records already
scores 76% keep — i.e. these records do NOT reproduce the device music-only failure. See Remaining risks.

KEY FINDING (Phase 3 root signal): **13 of 15 real TMB moment summaries contain NO audio description at all** —
including the 95s "natural conversation" scene and the 38s river crossing. MomentUnderstanding describes what is
SEEN, not HEARD. So the planner decides native_audio with essentially no audio evidence.

### 2–3. v4 vs v5, timeline-WEIGHTED (not counts) — real thin TMB inputs
| | v4 | v5 |
|---|---|---|
| TMB real moments | keep 76% / duck 24% / mute 0% (12 segs, 72.5s) | **keep 100%** (11 segs, 74.2s) |
Both feasible/executable. v5 lifts the remaining ducked ambience (incl. the no-audio-description trail/pack
shots) to keep; v4 ducked 24% of the timeline for lack of a stated reason.

### Missing-audio-evidence test (Phase 3) — mixed clip set
v5 on [cliff: no audio desc | waves: meaningful natural | wind-roar: unusable | silent beach]:
`duck 10s (cliff, no desc) · keep 14s+14s (waves) · mute 5s (wind-roar overload)`.
→ Missing description did NOT auto-duck/mute (cliff ducked but present, not muted); meaningful natural sound
KEPT; explicitly-unusable audio MUTED for a stated reason. v4 blindly kept 100% incl. the overloaded clip
(editorially worse). Exactly the owner's intended behavior.

### Regression / protection (Phase 4 criteria 2–4)
| Case | v4 | v5 | Gate |
|---|---|---|---|
| Explicit music-only | mute 100% | **mute 100%** | ✓ intentional music-only preserved |
| Guitar performance | keep 100% | keep 100% | ✓ protected |
| Birthday singing | duck 16% / keep 84% | **keep 100%** | ✓ v5 stops ducking the singing |
No cross-domain regression; all plans executable (feasible=True).

### 4. Freeze verdict (Phase 4)
v5 clears criteria 2 (guitar/birthday protected), 3 (music-only preserved), 4 (no regression), 5 (executable).
Criterion 1 (realistic TMB material improvement): v5 moves TMB from 76%→100% keep timeline-weighted and fixes
the no-audio-description and unusable-audio cases editorially — a MATERIAL improvement on the best real evidence
available. BUT because the exact device request could not be recovered and v4 did not reproduce the device
music-only failure on these records, the device-level fix is NOT yet proven on the real failing input.

RECOMMENDATION: v5 is correct and safe to freeze as the candidate, BUT the owner's condition "reproduce AND
improve the real TMB failure" is only PARTIALLY met — improved on realistic data, not reproduced on the exact
device request. The decisive remaining test is a DEVICE re-render on v5 (deploy v5 to dev backend, regenerate
TMB, read the on-screen native_audio histogram). If that device render stays effectively music-only, Phase 4
says STOP and diagnose whether the cause is inadequate AU audio evidence (likely — summaries carry no audio),
prompt behavior, or mixing. Current evidence points at **inadequate audio evidence feeding the planner**, which
a prompt alone cannot fully fix.

### 7. Remaining risks
- Exact device request unrecovered; device music-only not reproduced here → device re-render on v5 required.
- Root signal is MISSING AUDIO EVIDENCE (13/15 summaries silent on sound). v5 mitigates by keeping-by-default,
  but the real fix may need MomentUnderstanding to describe AUDIO (a separate, owner-gated evidence change) so
  the planner's duck/mute reasons are grounded — not a further prompt tweak.
- The renderer duck-under-continuous observation (duck buries native at role=continuous) remains flagged, not
  changed.

## STAGE 1c — DEVICE render on v5 (Phase 4 STOP+diagnose) — 2026-10-11 14:34
Device TMB re-rendered with v5 LIVE. On-screen 🎵: `native_audio[duck×17 keep×3 mute×9] role=continuous
priority=low` (29 segs). Still effectively music-only → Phase 4 requires STOP + diagnose. Diagnosis from logs
(NOT inferred):
- EDITPLAN 21:34:26 `prompt_version=edit_plan/5 segs=29` → **v5 WAS live and used.** Not a deploy miss.
- MUSICPLAN 21:32:55 `priority=low role=continuous` → **this is the cause.** v5's prompt says low permits
  broader duck/mute, so the planner correctly produced duck/mute. v5 behaved AS DESIGNED on a `low` input.
- Live isolation: MusicPlan with EMPTY guide → selective/continuous; with RICH TMB guide → important/supportive.
  So MusicPlan is STILL being starved of the StoryGuide on the device path → returns low/continuous.

ROOT CAUSE (two independent faults, neither is v5):
1. UPSTREAM MusicPlan input: TMB gets priority=low (+ role=continuous) because the device is NOT feeding
   MusicPlan a real StoryGuide. The earlier iOS fix (ensureGuide + pass guide/coverage) is either not in the
   device build or the guide is not generated/passed on this render path. This is the PRIMARY fault — an iOS
   wiring / audio-evidence problem, and v5 cannot (and must not) override a `low` input.
2. role=continuous persists in BOTH guide states → even kept native is buried at soundtrack 1.0. The
   owner-flagged renderer quirk; still not changed.

FREEZE VERDICT: v5 does NOT clear criterion 1 — but NOT because v5 is wrong. v5 is correct and safe (criteria
2–5 pass). The gate is blocked UPSTREAM: MusicPlan priority/role for TMB. Per Phase 4, STOP — the responsible
layer is the MusicPlan INPUT (StoryGuide evidence) + role, not another edit_plan prompt change. Do NOT stack
more prompt edits. Next: verify the iOS guide-passing fix is actually in the device build and that
ensureGuide runs on this render path; separately decide role=continuous handling.

## STAGE 1d — CLEAN-REBUILD device verification (resolved) — 2026-10-11 15:12
Clean Xcode rebuild + reinstall, re-rendered the existing TMB Story. On-screen + backend CORRELATED:
- `🧪 build b6c0237-guidewire+ensure` → installed binary now HAS the guide fixes (a4c6aa5+4391b42). The prior
  low result WAS a stale build — hypothesis confirmed.
- `🧭 build=b6c0237 ensureGuide=ok guide=yes(4dims) coverage=yes -> role=continuous priority=selective` → the
  SINGLE MusicPlan path now carries a real StoryGuide (4 dimensions) + Coverage. Input path works.
- Backend: MUSICPLAN priority=selective role=continuous; EDITPLAN prompt_version=edit_plan/5 segs=21.
- Plan FLIPPED: before (stale build) duck×17 keep×3 mute×9 (26/29 buried); NOW **duck×6 keep×15 mute×0**
  (15/21 keep, ZERO mute). v5 + real guide preserves native audio on the majority of the timeline.

Decision gate → branch 3: priority corrected (low→selective), native largely kept. Remaining item is the
owner-flagged renderer quirk ONLY: role=continuous. Under role=continuous the gain table gives keep segments
soundtrack 0.2 (native leads — good) but duck segments soundtrack 1.0 / native 0.25. With keep×15 the wind/
footsteps/conversation SHOULD now be clearly audible on most of the video — a LISTENING check decides whether
anything more is needed. NO renderer change made (owner: do not change renderer gains yet).

Root cause of the whole TMB saga (final): a STALE device build that predated the StoryGuide input-wiring fixes,
so MusicPlan was starved of the Guide and returned low → v5 (and v4) correctly duck/muted. Not a v5 fault, not
a prompt fault. Fixed by the committed iOS wiring once actually installed.

## STOP — v5 FREEZE GATE
Stage 1 complete and passing. Per Part D, STOP here for owner freeze approval before stages 3–7 and before any
production integration. On approval: freeze edit_plan/5 (flip the default or deploy with the env set) and
proceed to stage 3. Not pushed.
