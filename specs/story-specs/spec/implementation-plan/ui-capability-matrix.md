# UI Capability Matrix — frozen Figma surfaces vs implemented capability

**Purpose:** every capability the frozen Figma UX (`prototypes/story-figma/src/App.tsx`)
presents, with its current backend status, why it is disabled if it is, the
dependency, and the milestone expected to enable it. A future milestone that
implements a capability MUST, in its Definition of Done, enable the corresponding
Figma UI here and flip the row.

**Frozen Figma artifact:** `prototypes/story-figma/src/App.tsx` (4730 lines, single
Figma Make export, git `ba88526`). No competing version.

**Phase 7 fidelity status (2026-10-02):** every row below was re-verified against
actual native iPhone renders (product-presentation mode) laid beside the actual
Figma renders — not "a view exists". Fonts (Fraunces + DM Sans) are now bundled
(SIL OFL), image-forward composition matches, and the DIRECT shot card is scene-
backed. The remaining non-MATCHED rows are all DISABLED-future capabilities whose
*surface* is present and faithful; their *capability* is future work (tracked).
See `c35-phase7-fidelity-audit.md` for the screen-by-screen side-by-side.

**Legend — Capability:** IMPLEMENTED · PARTIAL · NOT_IMPLEMENTED.
**UI treatment at C3.5:** WIRED (real) · DISABLED (visible, non-interactive) ·
DEBUG_ONLY · EMPTY_STATE.
**Figma parity:** MATCHED · PARTIAL · MISSING · REAL_SYSTEM_EXTENSION. C3.5
Definition of Done requires **zero unexplained MISSING rows** — every MISSING must
carry a dependency + target milestone.

| Feature / surface | Figma location | Capability | C3.5 UI treatment | Figma parity | Why | Dependency | Target milestone |
|---|---|---|---|---|---|---|---|
| Creative Intent (free text → resolved intent) | Screen1Intent / ScreenStoryDirection | IMPLEMENTED (C1) | WIRED | MATCHED | — | — | done |
| Scene scan → SceneUnderstanding | Screen3Scene / ScreenTMBShootScene | IMPLEMENTED (C2) | WIRED | MATCHED | — | — | done |
| Story Director idea/recommendation | Screen5Idea / ScreenTMBShootIdea | IMPLEMENTED (C3) | WIRED | MATCHED | — | — | done |
| Director thinking state | Screen4Thinking / ScreenTMBShootThinking | IMPLEMENTED | WIRED (real 12–16s) | REAL_SYSTEM_EXTENSION | staged copy for real latency | — | done |
| capture_shot → shot guidance → camera | ShotScreen + CaptureScreen | IMPLEMENTED | WIRED | MATCHED | — | — | done |
| rescan_scene (decline scene) | (not in Figma) | IMPLEMENTED (C3) | WIRED | REAL_SYSTEM_EXTENSION | real Director state | — | done |
| create_now (enough material) decision | (not in Figma) | PARTIAL (decision only) | WIRED decision + DISABLED downstream generate | REAL_SYSTEM_EXTENSION | real generation absent | Edit Planner + Media | later Create-Story milestone |
| Moment capture → persist | ShotScreen→Story | IMPLEMENTED (A) | WIRED | MATCHED | — | — | done |
| **"Try another idea"** (alternative ideas) | Screen5Idea / ScreenTMBShootIdea | IMPLEMENTED (C3C) | WIRED | MATCHED | ONE Director call returns up to 3 EPHEMERAL ranked alternatives for the current slot; "Try another idea" cycles #1→#2→#3 INSTANTLY (local, no new call), hidden on the last; alternatives are NOT persisted into StoryPlan and add no beats/shots/coverage | — | **done (C3C)** |
| **Skip scan** (shoot immediately) | Screen3Scene / ShotScreen skip | IMPLEMENTED (C3C) | WIRED | MATCHED | intro "Skip Scan" (secondary) → opens the camera DIRECTLY: no scene scan, no Director call, no ~10s wait, no recommendation/concept. Captured clip runs C4-Lite integrity → Moment. (Server still tolerates a null-scene Director call, but Skip Scan no longer uses it — avoids the 10s wait + any fabricated concept.) | — | **done (C3C)** |
| **Capture integrity check (C4-Lite)** | Screen8Validation (reused: Saved / Try again) | NOT_IMPLEMENTED | DISABLED | MISSING | local-only integrity gate (duration + file-readable; exposure/shake/focus only if they earn it on T01). Neutral "Saved/Moment added"; negative ONLY on high-confidence integrity failure. NO semantic Shot/Beat claim. | C4-Lite (`milestone-c4-lite-capture-integrity-design.md`) | **C4-Lite** |
| ~~Shot Validation (success/retry)~~ **semantic — REJECTED for inline MVP** | Screen8Validation | NOT_IMPLEMENTED | DISABLED | MISSING | inline semantic validation rejected by GO/NO-GO audit (latency/cost/trust); semantic Shot/Beat judgment moved to async Asset Understanding | Asset Understanding (async) | ~~C4~~ → deferred to Asset Understanding |
| ~~Validation-driven retry~~ **REJECTED for inline MVP** | Screen8Validation retry | NOT_IMPLEMENTED | DISABLED | MISSING | depended on inline semantic validation; retry on *integrity* failure only in C4-Lite, not on semantic shot-success | C4-Lite (integrity retry) / Asset Understanding (semantic) | ~~C4~~ |
| **Real Beat-progress feedback** | ScreenTMB Story Guide states | SUPERSEDED (E) | n/a | n/a | Beat-progress is NOT a persistent Story concept (Director beats are per-CaptureSession only); the Story Guide now reflects derived StoryCoverage, not beat checkmarks — by design, no live ✓ | — | superseded by Story Coverage (E) |
| **Capture original → Apple Photos (add-only)** | (no Figma surface — background safety) | IMPLEMENTED (complete) | n/a (silent background save) | REAL_SYSTEM_EXTENSION | successful Moment also saves the original to Photos (add-only, fire-and-forget, never blocks/fails Moment creation); migration-free. Auto target-included via `PBXFileSystemSynchronizedRootGroup` — **no pbxproj edit needed**. **Remaining:** physical-iPhone verification per `milestone-d-photos-persistence.md` | — | **D (Photos persistence)** |
| **Existing media — analyze path** (pre-shoot) | ScreenMediaPicker(analyze) + PreMediaResult A/B/C | NOT_IMPLEMENTED | DISABLED entry | MISSING | needs AssetUnderstanding; **design FROZEN 2026-10-05** (`06-asset-understanding.md`: Sonnet 4.6 @ 24fr, on-device queue) — build not started | Asset Understanding (D) — design frozen | **Asset Understanding (D)** |
| **Existing media — add-to-Moments path** | ScreenMediaPicker(add) from Moments/Preview | IMPLEMENTED (C3.5) | WIRED | MATCHED | PHPicker → MediaStore → existing-media Moments, no analysis | — | **done (C3.5)** |
| **Music direction (feeling)** | MusicDirectionRow/Sheet | NOT_IMPLEMENTED | DISABLED | MISSING | no music model | Music Engine | later Create-Story milestone |
| **Music track selection / re-edit** | ScreenTMBMusic | NOT_IMPLEMENTED | DISABLED | MISSING | no music model/engine | Music Engine | later |
| **Create My Story → real generation** | Screen10Creating → Screen11Result | NOT_IMPLEMENTED (mock output only, A) | DISABLED real-generate; mock DEBUG_ONLY | PARTIAL | no Edit Planner/Media Engine | Edit Planner + Media | later |
| **Generated Output result (play/save/share)** | Screen11Result | NOT_IMPLEMENTED (mock) | EMPTY_STATE + DISABLED actions | PARTIAL | no real output | Edit Planner + Media | later |
| **Create a new version / re-edit** | Screen11Result | NOT_IMPLEMENTED | DISABLED | MISSING | depends on generation | Edit Planner + Media | later |
| **Complete Story (lifecycle) + Reopen** | ScreenTMB menu → Complete/Reopen | IMPLEMENTED (C3.5) | WIRED | MATCHED | local status flip active↔completed + completed-sorts-below-active in Home | — | **done (C3.5)** |
| **Story Guide / arc (“what I’ll look for”)** | ScreenStoryBlueprint / ScreenTMB Guide | IMPLEMENTED (E) | WIRED (real StoryCoverage) | MATCHED | real `story_coverage/1` snapshot (Opus 4.6, full recompute): ordinary-language strengths + meaningful weak dimensions + sufficiency; ENOUGH state for `sufficient`; pending=unknown honesty; NO ids/scores/percentages/progress/required-shots/jargon; Figma TMB chapters remain demo-only | StoryBlueprint/Guide milestone | **done (E)** |
| **Story Idea passive suggestion** | ScreenTMB “✦ Story Idea” | IMPLEMENTED (E) | WIRED (real StoryCoverage.story_idea) | MATCHED | ONE optional high-level idea shown only when `story_idea != null`; card OMITTED entirely when null (no “no ideas” placeholder); “Show me” routes into the EXISTING SceneScan/Director flow (no Director change); TMB “A moment together” remains demo | Story Guide milestone | **done (E)** |
| **Show Me handoff (Story Idea → Director)** | ScreenTMB Story Idea → ScreenTMBShoot* | IMPLEMENTED (E) | WIRED (minimum existing path) | MATCHED | Story Idea stays high-level; “Show me” opens the existing SceneScanFlow where the existing Director turns the scene into executable guidance — NO canonical Director contract change | existing Director (C1–C3) | **done (E)** |
| **Reference media (vibe from a clip)** | Screen1Intent / ScreenStoryDirection reference | NOT_IMPLEMENTED | DISABLED | MISSING | reference transport not built (C1 is text-only) | reference-ingest | later |
| **Typography (Fraunces + DM Sans)** | all screens | IMPLEMENTED (C3.5) | WIRED | MATCHED | fonts bundled from Google's OSS repo (SIL OFL), resolved via Font.custom with system fallback | — | **done (C3.5)** |

## Note — "MISSING" means a surface omission, not a future capability (review clarification)
Per the C3.5 acceptance clarification: a row may stay **capability = NOT_IMPLEMENTED**
and still satisfy the Definition of Done *as long as its frozen Figma surface is
present natively* (disabled or empty state), with dependency + target milestone
tracked here. The `MISSING` parity values above are **capability-level** notes for
the owning future milestone — the corresponding *surface* IS rendered natively in
C3.5 (e.g. Shot Validation has no screen because it has no trigger until C4 wires
the loop; Music/Create/Reference render as intentional disabled sections). No frozen
Figma surface is absent from the native product merely because its backend is future
work. The one deliberate structural omission — the post-capture Validation screen —
is documented in the fidelity audit as "no entry point until C4" rather than shipped
as a dead view.

## Note on Story Guide / Story Idea (review correction)
The frozen Figma Story Guide chapters (Departure / On the Trail / Scale / …) and the
"✦ Story Idea — A moment together" card are **TMB demonstration content**, not
production-generated personalized Story content. C3.5 preserves their Figma
structure and visual hierarchy but renders them in a **neutral, clearly
unavailable** state (e.g. a muted "Story Guide — coming soon" treatment), NEVER
pasting the TMB copy over an arbitrary Story as if it were real guidance.

## Rule
When a milestone implements any NOT_IMPLEMENTED/PARTIAL row, it must: (1) wire the
corresponding Figma surface, (2) flip the row here to IMPLEMENTED/WIRED, (3) note
the enabling milestone. This file is the single source of "what's intentionally
disabled and why" so no frozen capability is silently dropped.
