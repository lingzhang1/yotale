# Milestone M-e — My Music + Change Music, on a Shared Versioning Foundation

Status: **DESIGN + IMPLEMENTATION (M-e only).** Create Another Version (V2-b) and
Natural-Language Refinement (V2-c) are DESIGN-ONLY here (Phase 6). Owner gate:
STOP at the M-e physical-device acceptance. Do not push automatically. Do not
change frozen contracts without explicit owner approval.

Preceding accepted milestone: Customize Your Story + sound preference
(`milestone-customize-your-story-sound-preference.md`), device-accepted on build
`b6c0237-guidewire+ensure` (keep15/duck6/mute0 on TMB, owner listened + confirmed
the native/music balance). That milestone is **CLOSED** by this document (Phase 0).

---

## Phase 0 — Customize Your Story closure

Verified at HEAD `b4befdf`:
- `af5ae11` froze `edit_plan/5` as the development default (v4 preserved + reachable via `STORY_EDIT_PLAN_VERSION=4`); EditPlan/2 output schema and renderer gains untouched.
- `9a9d8a8` wired `sound_preference` (immersive|balanced|music_led) through `/v1/music-plan` + `/v1/edit-plan` (additive request field, default None) and shipped `CustomizeYourStoryView`.
- `6e61587` compacted the Full Story row; `b4befdf` removed the DEBUG audio diagnostics readout.
- Backend suite: 224 passing. iOS: parse-clean (device build is the real gate, and it passed).
- **Owner physical-device acceptance recorded.** The native-audio regression is accepted as resolved; renderer gain table and audio prompts are frozen for this milestone (owner: do not tune further).

Working tree: clean except untracked `evals/scenarios/guitar_practice_001/*.mov` fixtures (unrelated media — preserved, never committed).

---

## Phase 1 — Persistence / contract reconciliation (THE load-bearing finding)

### What is persisted today for a generated video (`GeneratedOutputModel`)
`id`, `story`, `title`, `durationSeconds`, `momentIds` (legacy) + `sourceMomentIds`
(ordered), `sourceFingerprint`, `editPlanProvenance` (a SHORT string:
`schema_version; model=none|music; planned=Ns`), `relativeFilePath` (the rendered
MP4 under `<Documents>/rendered/`), `outputFormat`, `renderWidth/Height`,
`isStale`, `soundtrackTitle`, `createdAt`.

### Can the exact visual edit be reconstructed today? **NO.**
The executable plan (`EditPlanV2`: per-segment `order`, `assetId`, source in/out,
`outputDurationSeconds`, `speed`, `transition`, `nativeAudio`, `musicAlignment`)
is **not persisted anywhere**. The raw backend plan JSON is decoded at
`EditPlannerService.swift:107` and discarded; `EditPlanV2` is `Decodable`-only
(cannot even round-trip). The plan is also potentially mutated post-decode by the
opt-in `CreativeRefinementV2b` source-nudge pass, so even re-calling the Edit
Planner would NOT reproduce the same timeline. `editPlanProvenance` is a human
breadcrumb, not an executable artifact.

**Conclusion:** Operation A (Change Music — "same visual edit, same moment
selection/order, same source in/out, same speed/crop/transitions, same final
duration, different soundtrack") is **impossible on existing persistence.** This
is the architecture gap Phase 1 asked me to find.

### Is it a "significant" gap requiring a full STOP? No — it is bounded and additive.
The owner's Phase 1 explicitly asks: "Investigate whether existing
GeneratedOutput/SwiftData structures can be **extended rather than replaced**." The
answer is **yes, extend.** No frozen contract changes: EditPlan/2's *wire schema*
is untouched; we persist a local *instance* of a plan the backend already emits.
So I proceed to implement M-e on the extension below, rather than stopping — the
gap's fix IS the shared-versioning deliverable.

### Shared versioning foundation — EXTEND `GeneratedOutputModel` (do not replace)
A `GeneratedOutputModel` row already IS a version (a Story has many, additively,
never overwritten). I add version lineage + the executable plan to it. All new
fields optional/defaulted → SwiftData lightweight migration, existing rows stay
valid (legacy rows read as v1-of-their-story, operation `original`, with no stored
plan — correctly NOT eligible for Change Music, which needs the plan).

New fields on `GeneratedOutputModel`:
- `versionId: UUID` (default = `id`; the stable version handle)
- `parentVersionId: UUID?` (nil for an original render; set to the source output's `versionId` for a derived version)
- `operationType: String` = `original` | `change_music` (future: `another_version`, `edit_ai`)
- `editPlanJSON: String?` — the **exact executable `EditPlanV2`** this output rendered from, as canonical snake_case JSON (the post-refinement plan). nil on legacy rows. This is what makes the visual edit reconstructable.
- `soundtrackRole: String?`, `nativeAudioPriority: String?` — the mix knobs used, so a re-render reproduces the same native-audio treatment.
- `soundPreferenceRaw: String?` — the effective sound preference at render time (provenance).
- `musicAssetRef: String?` — identity of the soundtrack: `provider:<trackId>` | `mymusic:<MyMusicAsset.id>` | `none`. (`soundtrackTitle` is kept for display.)

`EditPlanV2`/`EditSegmentV2`/`Transition`/`MusicAlignment` become **`Codable`**
(add `Encodable`) so the post-refinement plan can be serialized at persist time and
re-decoded for a re-render. Round-trip stability is unit-tested.

Reconstruction for Change Music (Operation A): decode `editPlanJSON` → `EditPlanV2`,
resolve each `assetId` → on-device URL via `MomentResolver` (Moments/assets still
live under the Story; **no duplicate source video is stored** — versions share the
originals), swap only the soundtrack + mix knobs, re-render through the EXISTING
`MediaEngineV1`. The Edit Planner is **never invoked**. Visual timing is byte-for-byte
the same plan.

### Does `MusicAsset` exist? No — introduce `MyMusicAssetModel` (Phase 2)
Provider tracks are resolved transiently per-create (`MusicSelection`), never
persisted as a library. My Music needs a new persisted `@Model`.

---

## Phase 2 — My Music library (`MyMusicAssetModel` + `MyMusicStore` + import)

`@Model MyMusicAssetModel`: `id: UUID` (stable identity), `displayName`,
`relativePath` (under `<Documents>/mymusic/`, LOCAL-first — bytes never leave the
device, never uploaded), `originalFilename`, `durationSeconds`,
`contentHash` (sha256 of bytes — dedup + corruption detection), `energyCurveJSON`
(coarse amplitude, locally derived), `bpm: Double?` (ONLY if validated locally;
never fabricated), `createdAt`, `lastUsedAt?`.

Import: SwiftUI `.fileImporter` (iOS Files), unprotected audio UTTypes
(mp3/m4a/wav/aiff/caf). Copy bytes into managed storage, hash for dedup (same hash
→ reuse existing asset, no second copy), reject DRM/unreadable with a clean error.
Preview (AVPlayer, `.playback` category per the known AVAudioSession lesson),
rename, reuse across Stories, remove (deletes managed bytes + row; a Story version
referencing a removed asset degrades gracefully to no-music on re-open, never
crashes).

Local analysis (`LocalMusicAnalysis`): duration via `AVURLAsset.load(.duration)`;
coarse energy curve by RMS-windowing decoded samples (`AVAudioFile`), normalized
0..1 (reuses the frozen `normalize_energy` contract shape); beats/bpm ONLY if a
validated local estimate is available, else honestly empty. **No fabricated
BPM/beats/downbeats/highlights.** Produces a `MusicAnalysisV1`-shaped object so the
existing mix path consumes it unchanged.

My Music is clearly labelled distinct from provider tracks in the picker. Provider
favorites are NOT turned into permanent local copies (licensing) — only
user-imported bytes are stored.

---

## Phase 3 — Change Music (new version, no Edit Planner)

On the Result screen, a "Change Music" action opens a chooser (reuse the Music
Picker visual language + a My Music section): pick another provider track, a saved
My Music track, a newly imported track, or **no music**. On confirm:
1. Load the source output's `editPlanJSON` → `EditPlanV2` (the exact visual edit).
2. Resolve the new soundtrack: provider → temporary authorized download; My Music → managed local file; none → nil.
3. Fit music to the EXISTING video duration with a bounded trim + fade policy (no visual cut changes to chase the beat — that is a future op).
4. Re-render via `MediaEngineV1` with the SAME plan, preserving native audio + the stored sound preference / role / priority.
5. Persist a NEW `GeneratedOutputModel` version: `parentVersionId` = source, `operationType=change_music`, copy `editPlanJSON`, set the new `musicAssetRef`/`soundtrackTitle`. **Previous version is preserved** (never overwritten).

---

## Phases 4–5 — Regression + device acceptance
Regression (Phase 4) and the physical-device checklist (Phase 5) per the owner's
enumerated lists. Soundtrack-only revisions are verified to preserve the EXACT
visual timeline (same plan JSON), not merely a similar edit. STOP at device gate.

## Phase 6 — V2-b / V2-c roadmap (design only; see end of this doc after M-e lands)
`another_version` and `edit_ai` reuse the SAME version lineage
(`operationType`, `parentVersionId`, `editPlanJSON`). V2-b reads prior
`editPlanJSON`(s) to steer AWAY from used moments/ranges/openings; V2-c resolves
NL references against ALL MomentUnderstanding (incl. omitted footage) and edits the
stored plan minimally. Neither is implemented in M-e.

---

## Contract implications
- No frozen wire-contract change. EditPlan/2, MusicPlan/1, MusicAnalysis/1 schemas untouched.
- `EditPlanV2` renderer DTO gains `Encodable` (local round-trip only).
- `GeneratedOutputModel` + new `MyMusicAssetModel`: additive SwiftData migration, all new fields optional/defaulted.
- Change Music is a CLIENT-side re-render — no new backend endpoint.

## Risks / limitations
- My Music local BPM/beat estimation is best-effort; absence is honest-empty, mix degrades to energy-only (same graceful path as provider tracks lacking beats).
- A My Music asset removed after a version referenced it → that version re-opens as no-music (bytes gone); documented, not a crash.
- Licensing: provider tracks are never permanently stored; only user-owned imports are.

---

## IMPLEMENTATION RESULTS (M-e)

Commits (app repo, not pushed):
- `65eac50` — foundation: `EditPlanV2`/`EditSegmentV2`/`Transition`/`MusicAlignment` → `Codable`; `GeneratedOutputModel` + `versionId`/`parentVersionId`/`operationType`/`editPlanJSON`/`soundtrackRole`/`nativeAudioPriority`/`soundPreferenceRaw`/`musicAssetRef` (all defaulted = migration-safe); `MyMusicAssetModel` + schema registration; `persist()` writes the post-refinement executable plan JSON on every original render.
- `5d7ed7a` — engine: `MyMusicStore` (fileImporter import → managed `<Documents>/mymusic/`, sha256 dedup, corruption/DRM rejection, remove); `LocalMusicAnalysis` (duration + coarse normalized energy curve from decoded PCM; bpm/beats honestly empty, never fabricated); `SoundtrackReplacer` (Change Music engine — reuse persisted plan verbatim, swap soundtrack + mix knobs, re-render, save new version); `ChangeMusicVersioningTests` (round-trip + lineage + legacy-refusal).
- `a06b01f` — UI: `ChangeMusicSheet` (My Music list, import-from-Files, preview via `.playback` session, rename, remove, no-music; dark editorial, no sliders/BPM) + Result-screen "Change music" wired, gated on a persisted plan, lands on the new version via `fullScreenCover` while the previous output stays in the version list.

Spec doc: `a3cece8`.

### Correctness proof (sandbox-runnable)
A standalone Swift round-trip (encode→decode→decode) of a representative EditPlan/2
asserted that EVERY visual field survives: segment count, target duration, output
format, per-segment `asset_id`, source in/out, `output_duration`, `speed`,
`native_audio`, and `transition` (dissolve+duration / cut), plus `music_alignment`.
This is the guarantee behind "same visual edit, different soundtrack." Mirrored as
`ChangeMusicVersioningTests` for the device/Xcode run.

### Regression (Phase 4) — status
- Backend suite: **224 passed** (backend untouched by M-e).
- iOS: all touched + new files parse-clean; `ChangeMusicVersioningTests` added. Items 1-13 and the "exact timeline, not similar" check are exercised by the engine + tests at the logic level; the ones that require real AVFoundation export (actual MP4 re-render, audible native-audio, Save/Share) are device-gate items (Phase 5), by design — AVAssetExportSession does not run in the sandbox.

### Phase 5 — physical-device acceptance checklist (owner)
Build on the phone, then verify:
1. Import a local audio file via Files → it appears under From your music.
2. Preview it (audible with the mute switch on) and it shows name + length (no BPM).
3. It persists after force-quit + relaunch, and is reusable in a DIFFERENT Story.
4. Re-import the same file → no duplicate row (dedup).
5. On an existing Story: Change music → pick a My Music track → new video renders; the VISUAL edit (cuts/timing/pacing) is unchanged; only the soundtrack differs.
6. Change music → No background music → native audio is preserved and audible.
7. The previous version still opens (not overwritten); the new one is a separate version.
8. Remove a My Music track that a version used → that version re-opens as no-music, no crash.
9. A legacy video (made before this build) shows "Change music" disabled with the honest reason.
10. Save/Share the re-soundtracked MP4 works.

**STOP for owner acceptance here.** No push; frozen contracts unchanged.

### Contract implications (final)
No frozen wire-contract change. `EditPlanV2` renderer DTO gained `Encodable`
(local round-trip only). `GeneratedOutputModel` + `MyMusicAssetModel`: additive
SwiftData migration, every new field optional/defaulted. Change Music is a
client-side re-render — no new backend endpoint, Edit Planner never invoked.

---

## Phase 6 — V2-b / V2-c roadmap (DESIGN ONLY — not implemented in M-e)

The version lineage built here is the shared substrate for both future ops; neither
needs a schema change beyond new `operationType` values.

**V2-b — Create Another Version** (`operationType="another_version"`):
reads the parent chain's `editPlanJSON`(s) to steer AWAY from already-used moments,
source ranges and openings — variation is EVIDENCE-driven (alternative strong
moments, omitted footage, different source ranges/pacing/emphasis), never random,
never forced when footage is thin, never at the cost of narrative coherence or
native audio. Diversity is measured SEPARATELY from editorial quality (two metrics:
a timeline-overlap/opening-difference score vs the existing quality eval). This DOES
invoke a variation-aware planner (unlike Change Music).

**V2-c — Natural-Language Refinement** (`operationType="edit_ai"`):
uses the existing Figma feedback UX. An instruction ("start with the girl",
"include the blue dress", "keep the ending, change the opening") resolves references
against ALL MomentUnderstanding (incl. omitted footage), applies a MINIMAL edit to
the stored plan, and preserves unaffected segments. Reuses `editPlanJSON` as the
base to diff against.

Architecture implication: both read prior `editPlanJSON`; V2-b/V2-c persist as new
versions exactly like Change Music, so the Result-screen version list and the
"never overwrite" invariant already cover them.

---

## UX UNIFICATION (post-device-video feedback, commit `a552c67`)

Owner device video surfaced three gaps, all converging on one fix:
1. My Music was not visible at create time.
2. Import should be offered in the create-time music list.
3. Change Music should also show the provider recommendation list.

Resolution — ONE shared music chooser. `MusicPickerView` (the create-time picker,
which already had provider recommendations + search + pagination + preview) now ALSO
renders a **"Your music"** section: the imported `MyMusicAssetModel` library + an
**Import from Files…** row. Its `Choice` gained `.myMusic(assetId)`. The Change
Music sheet was rebuilt to **present the same `MusicPickerView`** (fetching a
recommendation for the Story), so both surfaces now offer the identical set:
provider recommendations · My Music · Import · No music. #2 and #3 are literally the
same component.

Supporting pieces:
- `SoundPreference.localMixKnobs` — deterministic (role, priority) per preference
  (immersive→sparse/important, balanced→supportive/selective, music_led→continuous/low),
  used for imported music which has no backend MusicPlan. Matches the verified live A/B.
- Create-time My Music resolves LOCALLY into a `MusicSelection` (no backend); the
  Edit Planner is called with a nil music plan (parity path) and the imported track
  is a render-time overlay. `musicAssetRef` distinguishes `provider:` vs `mymusic:`.
- "Use this music" is hidden when there is no selectable provider track (My-Music-only).

Device video review found NO other defects: Change Music → No music produced a new
version correctly labelled "Created without music", and the visual edit was unchanged.

### Round 2 fixes (device video, commit `f4c7465`)
1. **"Save to My Music" from the list** — each provider track row has a ★ that saves it as a LICENSING-SAFE favorite: a reference by `providerTrackId` on `MyMusicAssetModel` with NO stored bytes (`relativePath==""`), re-resolved live from the provider on use. It appears in the same "Your music" list (labelled "Saved", preview disabled). Imported files remain byte copies; favorites never are.
2. **"Create a new version" landed on Home** — `StoryCreatingView.onRecreate` called its own `dismiss()` AND `onRequestRecreate()`, which raced and dropped the Customize sheet. Now it only calls `onRequestRecreate()`; the parent's `showCreating=false` pops the Creating screen and `promptDuration()` presents Customize. Also replaced the Change-Music `fullScreenCover` (which broke the recreate closure chain) with an in-place `swappedOutput`.
3. **"Still didn't see My Music"** — the section was at the BOTTOM of the picker (below the provider list + pager). Moved "Your music" to the TOP (above "Story's picks"), and added a temporary build stamp on the picker so a stale build is immediately visible.
