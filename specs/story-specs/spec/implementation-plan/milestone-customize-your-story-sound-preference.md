# Customize Your Story — v5 closure + sound preference (staged)

Status: 🟢 Phase 1 (v5 freeze) + Phase 2 (preference model) DONE. Phase 3 wiring = minimal additive request
change REPORTED, awaiting go (contract-touching). Phase 4 UX + 5/6 regression/device after. STOP at device
gate. Not pushed. Date 2026-10-11.

## 1. v5 closure commits
- Device acceptance: build `b6c0237-guidewire+ensure`, StoryGuide(4 dims)+Coverage reach MusicPlan,
  MusicPlan priority=selective, edit_plan/5, TMB keep15/duck6/mute0 — owner LISTENED and confirms native
  environmental audio + music are intelligently balanced. **Native-audio regression ACCEPTED as resolved.**
- `af5ae11` — edit_plan/5 frozen as the DEVELOPMENT default (`_EDIT_PLAN_DEFAULT="5"`). v4 preserved verbatim
  on disk and reachable via `STORY_EDIT_PLAN_VERSION=4`; EditPlan/2 output schema untouched; renderer gain
  table NOT changed (per owner). Dev default != production approval — a prod surface may still pin v4.
- Full suite: 224 passed.

## 2. Persisted preference design (Phase 2 — `af5ae11`)
StoryModel (additive, optional — existing Stories stay valid):
- `soundPreferenceExplicit: String?` — the user's chosen value; AUTHORITATIVE; survives relaunch, regeneration,
  repeated Create. Never overwritten by inference.
- `soundPreferenceInferred: String?` — advisory recommendation; recomputable.
- `effectiveSoundPreference` = explicit ?? inferred ?? **balanced** (fallback is a resolution default, NOT a
  forced selection). `hasExplicitSoundPreference` distinguishes a user choice from a recommendation in the UI.
- `enum SoundPreference { immersive, balanced, music_led }` (wire snake_case) + `infer(...)` that returns nil on
  a neutral intent (so "inferred" stays honest; music-video/montage → music_led, ambient/documentary →
  immersive).

## 3. Preference wiring — MINIMUM ADDITIVE REQUEST CHANGE (reported, awaiting go)
Both `/v1/music-plan` and `/v1/edit-plan` request bodies carry `creative_intent: dict`. Stuffing the preference
INTO creative_intent would be ambiguous overloading (the owner warned against this). The minimum clean change:
- Add `sound_preference: str | None = None` to `MusicPlanRequest` AND `EditPlanRequest` (Pydantic, additive,
  default None — existing callers unaffected; NOT a frozen output-schema/prompt change).
- iOS: add `soundPreference` to `MusicPlanRequestDTO` + `EditPlannerRequestDTO`, pass
  `story.effectiveSoundPreference.rawValue`.
- Backend: thread it to `MusicPlanInputs` / `EditPlanInputs` as a short request-context line the EXISTING
  prompts already act on via priority/role (music_plan) and the v5 preserve/respect-explicit clause (edit_plan).
  Mapping: immersive → bias priority=important/role=supportive-or-sparse; balanced → selective/supportive;
  music_led → low-ish/continuous BUT (v5 already) do not auto-mute important native. NO frozen prompt edit —
  the preference is passed as input; the frozen prompts already consume priority/role + explicit preference.
- Recompute: changing the preference must invalidate the MUSIC + EDIT planning outputs ONLY (re-run music-plan
  + edit-plan), NOT StoryGuide or Asset/Moment Understanding. Implement by folding sound_preference into the
  music/edit fingerprints (same pattern as the existing staleness fingerprints) — guide/coverage fingerprints
  untouched.

## 4. UX (Phase 4 — after wiring)
Replace the duration sheet with **Customize Your Story**: Section A Story Length (Highlights/Full Story/Custom
via Duration Intelligence, no fixed 15/60/120, whole-row tappable, clear selected state + concise explanation);
Section B Sound (Immersive/Balanced/Music-led, show inferred recommendation with a user override). Dark
editorial Figma language; no sliders/percentages/jargon. Music Picker flow preserved.

## STOP — report-before-implement gate on Phase 3
Phases 1–2 are done and committed. Phase 3 touches request contracts, so per the owner's instruction the
minimal additive change (`sound_preference` request field on both endpoints) is REPORTED above for approval
before I implement the wiring + UX. No frozen output schema or prompt changes; renderer untouched.

## UPDATE — Phases 3-5 IMPLEMENTED (owner approved the request field) — 2026-10-11
- Phase 3 wiring (approved + deployed): `sound_preference: str|None=None` added to MusicPlanRequest +
  EditPlanRequest (additive, extra=forbid-safe), threaded to engine inputs, injected as a one-line directive
  into BOTH prompt payloads (NO frozen prompt-file edit). iOS DTOs carry it; resolver refreshes the inferred
  pref (never clobbering explicit) and passes effective to music-plan AND edit-plan. Commit (app).
- Phase 4 UX: `CustomizeYourStoryView` replaces the duration sheet — Length (Highlights/Full/Custom via
  Duration Intelligence, no fixed defaults, whole-row tappable, selected states + concise explanation) + Sound
  (Immersive/Balanced/Music-led, inferred "Recommended" badge, user override). Explicit choice persisted
  (authoritative). Figma dark language, no sliders/jargon. Music Picker preserved. Parse-clean.
- Recompute: effective preference is read on each resolve + each build, so a changed preference re-runs
  music-plan + edit-plan WITHOUT regenerating StoryGuide/Coverage/Asset Understanding.
- Phase 5 (backend A/B, LIVE on dev): neutral Story, only preference varies →
  immersive: role=sparse priority=important · balanced: supportive/selective · music_led: continuous/low ·
  None: continuous/low. Meaningful, correctly-ordered spectrum; music_led != music-only (priority=low still
  preserves important native per the directive). 224 tests pass.

## Phase 6 — physical-iPhone acceptance (NOT done — STOP here)
Rebuild + test on device:
- selection rows clearly interactive (whole row taps; obvious selected ring/check);
- recommended duration appropriate to Story scope (Full Story shows the rec rationale);
- Sound options understandable; the inferred one shows "Recommended";
- selections persist across relaunch, regeneration, and repeated Create;
- the three Sound choices produce meaningful, sensible AUDIBLE differences (immersive clearly native-forward,
  music-led clearly soundtrack-forward but not silent native);
- TMB immersive + Guitar performance audio remain correct;
- generated videos save/share correctly.
STOP for owner at this device gate before Creative Editing V2-b / track adaptation / commercial music.
