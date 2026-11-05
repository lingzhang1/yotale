# Story — Core Domain Schema

**Status:** MVP v0.1 — **Milestone B frozen (2026-10-01).** This is the
canonical design. The shared implementation schemas are frozen; real AI
(Milestone C) must conform to them.
**UX Status:** Frozen  
**Purpose:** Canonical domain model shared by the Story iOS app, backend, and AI/media engines.

---

# 0. Milestone B Status — Frozen Schemas

Milestone B froze the shared implementation schemas before any real
intelligence. See `milestone-b-reconciliation.md` for the full comparison of
this document against the Milestone A code.

**Realized in code today (Milestone A slice):** `Story`, `StoryStatus`,
`CreativeIntent` (flattened), `Moment`, `Asset`, `GeneratedOutput`,
`LocalIdentity`. Mock engines only; backend store in-memory; iOS SwiftData is
the source of truth.

**Frozen as contracts in Milestone B (code wiring stays mock — no real AI):**
machine-readable JSON Schema under `contracts/schemas/*.schema.json`, Pydantic
models in `contracts/schemas/ai_contracts.py`, and Swift Codable DTOs in
`apps/ios/.../Data/Contracts/StoryContracts.swift` for: `CreativeIntent`,
`SceneUnderstanding`, `StoryConcept`, `StoryPlan`, `Shot`, `ValidationResult`,
`CaptureSession`, `MusicDirection`, `AssetUnderstanding`, `EditPlan`.

**Frozen naming decisions (deviations from earlier drafts, with reasons):**
- `MomentSource` values are `directed` / `spontaneous` / `existing_media` /
  `camera_import` — the `_capture` suffix from an earlier draft was dropped
  because both platforms already persist these values on-device; renaming would
  force a device migration for a cosmetic change (reconciliation §4.1).
- The directed-shot element is named **`Shot`** (nested in `StoryPlan.shots[]`);
  an earlier draft called it `ShotPlan`. The field set is unchanged
  (reconciliation §4.2).

---

# 0a. The Four Model Layers (authoritative)

One concept is represented in up to four distinct layers. **Do not use one
model for everything** (03-system-architecture.md §7, §2 principle 4).

| Layer | Lives in | Role | Rule |
|---|---|---|---|
| **Canonical domain** | `contracts/schemas/domain.py` (Python); `Domain/Engines/*.swift` value types (Swift) | What a concept *means* | No transport, persistence, AWS, or provider/model fields. |
| **API DTO** | `contracts/schemas/dto.py` (Python); `Data/Contracts/*.swift` (Swift) | What crosses the network | snake_case JSON, ISO-8601 UTC, UUID ids. No SwiftData concerns. |
| **SwiftData persistence** | `apps/ios/.../Data/Persistence/Models.swift` | How it is stored on device | Device-authoritative. Originals never stored as blobs; media is a relative path. May denormalize (e.g. flattened CreativeIntent). |
| **AI structured-output** | `contracts/schemas/ai_contracts.py` + JSON Schema | Strict shapes AI must *produce/consume* | `extra="forbid"` — reject unknown keys. No provider/model fields. Validated at the boundary so AI can't silently drift the contract. |

**Mapping is explicit, never implicit.** Documented edges:
- Domain `CreativeIntent {raw_text, theme, tone, summary}` ↔ full AI contract
  `CreativeIntent` (raw_text→`raw_user_description`, summary→`summary`,
  theme/tone seed `style_tags`/`desired_feeling`).
- SwiftData `AssetModel.relativePath` ↔ domain/DTO `Asset.local_uri` (device-local
  resolution via `MediaStore`).
- SwiftData `StoryModel.intent*` columns ↔ `CreativeIntentContract` (flattened ↔ structured).
- SwiftData relationships (`MomentModel.story`) ↔ domain `Moment.story_id`.

**Must NOT leak** (03 §7, §40; 04 §2 #11): SwiftData details into API/domain;
AWS/CDK types into domain engines; provider/model IDs into any domain or
contract field (model names are configuration, not domain — 03 §15).

---

# 1. Purpose

This document defines the core domain objects for Story.

These schemas are shared conceptually across:

- iOS application
- Story API
- Story Engine
- Director Engine
- Asset Engine
- Edit Engine
- Music Engine
- Media Engine
- Model Gateway

These are **domain contracts**, not database schemas or implementation-specific models.

Swift, backend, database, and API representations may differ, but their semantic meaning should remain consistent with this document.

---

# 2. Core Domain Model

The major domain objects are:

```text
LocalIdentity
│
├── Standalone CaptureSession
│       └── GeneratedOutput
│
├── ExistingMediaImport
│       └── GeneratedOutput
│
└── Stories[]
        │
        ├── CreativeIntent
        ├── MusicDirection
        ├── StoryBlueprint
        ├── StoryState
        │
        ├── Moments[]
        │       ├── Asset
        │       └── AssetUnderstanding
        │
        ├── CaptureSessions[]
        │       ├── SceneUnderstanding
        │       ├── StoryConcept
        │       ├── StoryPlan
        │       └── Captures[]
        │
        └── GeneratedOutputs[]
                └── EditPlan
```

The most important distinction is:

```text
Story ≠ GeneratedOutput
```

A Story is the persistent creative project/experience.

A GeneratedOutput is one video created from that Story.

A Story may have:

```text
0 outputs
1 output
many outputs
```

Creating an output does **not** complete a Story.

---

# 3. Story

A `Story` is a persistent creative container.

Examples:

- Tour du Mont Blanc
- Sarah's Birthday
- Weekend in New York
- Wedding Day
- Sunday at the Beach

```ts
interface Story {
  id: StoryId

  title: string

  status: StoryStatus

  creativeIntent: CreativeIntent
  musicDirection?: MusicDirection

  blueprint?: StoryBlueprint
  state: StoryState

  moments: MomentId[]
  captureSessions: CaptureSessionId[]
  generatedOutputs: GeneratedOutputId[]

  createdAt: Timestamp
  updatedAt: Timestamp
  completedAt?: Timestamp
}
```

## StoryStatus

```ts
type StoryStatus =
  | "active"
  | "completed"
```

### Active

The user is currently building the Story.

Story may provide:

- Story Ideas
- Shoot a Moment
- Story Guide
- scene-aware directing
- Create My Story

### Completed

The user has indicated that they are no longer actively building the Story.

The main purpose is organizational:

```text
ACTIVE
→ Home / Continue

COMPLETED
→ Home / Your Stories
```

Completion does **not**:

- generate a video
- freeze Moments
- delete Story Guide
- prevent Create My Story
- make the Story immutable

A completed Story can be reopened.

---

# 4. CreativeIntent

`CreativeIntent` is Story's normalized representation of what the user wants to create.

It may originate from:

- natural-language description
- template
- visual reference
- reference video
- preset vibe
- combinations of these inputs

```ts
interface CreativeIntent {
  id: CreativeIntentId

  sourceInputs: CreativeIntentSource[]

  summary: string

  subject?: string

  desiredFeeling?: string[]
  styleTags?: string[]
  pace?: "slow" | "moderate" | "fast"
  emphasis?: string[]
  creativeConstraints?: string[]

  targetDurationSeconds?: number
  targetFormat?: OutputFormat

  rawUserDescription?: string
}
```

> **Milestone C freeze note (2026-10-01).** Two refinements adopted from the
> Creative Intent tech design (`04-creative-intent.md`):
> - **`pace`** added as a categorical field (`slow | moderate | fast`) — Story
>   Director consumes an explicit pacing signal; inferring it from tone is
>   lossy. It is NOT exact edit timing (that belongs to StoryPlan/EditPlan).
> - **`avoid` was widened to `creativeConstraints`** — the earlier field held
>   only negative preferences, but important constraints are often phrased
>   positively ("authentic, not staged", "focus on the environment, not me")
>   or as a positive+negative pair ("epic but not cheesy"). `creativeConstraints`
>   holds both. Keep it concise — not a dump for model reasoning.
> The machine-readable contract is `contracts/schemas/creative-intent.schema.json`
> (generated from `CreativeIntentContract` in `contracts/schemas/ai_contracts.py`).

Example:

```json
{
  "summary": "A cinematic journey through the Alps emphasizing scale and movement.",
  "desiredFeeling": [
    "cinematic",
    "emotional",
    "adventurous"
  ],
  "styleTags": [
    "scenic",
    "natural",
    "slow-build"
  ],
  "emphasis": [
    "mountain scale",
    "journey",
    "natural couple moments"
  ],
  "targetDurationSeconds": 60,
  "targetFormat": "vertical"
}
```

CreativeIntent describes **what the user wants**.

It should not contain provider-specific prompts or LLM implementation details.

---

# 5. CreativeIntentSource

```ts
type CreativeIntentSource =
  | {
      type: "text"
      value: string
    }
  | {
      type: "template"
      templateId: string
    }
  | {
      type: "reference_asset"
      assetId: AssetId
    }
```

Multiple sources may contribute to one CreativeIntent.

---

# 6. MusicDirection

`MusicDirection` describes how the soundtrack should feel.

It is **not** the actual selected song.

```ts
interface MusicDirection {
  summary: string

  moodTags: string[]

  energy?: "low" | "medium" | "high" | "dynamic"

  progression?: string

  rawUserDescription?: string
}
```

Example:

```json
{
  "summary": "Emotional cinematic music with a gradual build.",
  "moodTags": [
    "cinematic",
    "emotional",
    "atmospheric"
  ],
  "energy": "dynamic",
  "progression": "quiet opening → gradual build → emotional climax"
}
```

Story may infer MusicDirection from CreativeIntent.

The user can optionally change it.

Exact music selection happens later during `Create My Story`.

---

# 7. StoryBlueprint

`StoryBlueprint` describes the narrative structure Story believes would work well.

It primarily powers:

- Story Guide
- Story Idea
- Story-level reasoning

```ts
interface StoryBlueprint {
  id: StoryBlueprintId

  storyId: StoryId

  narrativeNeeds: NarrativeNeed[]

  generatedAt: Timestamp
  updatedAt: Timestamp
}
```

Example:

```text
Tour du Mont Blanc

Opening
Journey
Scale
Human Moments
Challenge
Climax
Ending
```

These are narrative needs.

They are **not**:

- mandatory shots
- an itinerary
- a timeline
- day-by-day tasks
- completion requirements

---

# 8. NarrativeNeed

```ts
interface NarrativeNeed {
  id: string

  label: string

  purpose: string

  exampleIdeas?: StoryGuideIdea[]

  coverage?: NarrativeCoverage
}
```

```ts
type NarrativeCoverage =
  | "unknown"
  | "could_use_more"
  | "looking_good"
  | "strong"
```

Coverage is **advisory and internal**.

Do not expose percentage completion, required shot counts, or these labels directly in the UI in MVP.
`NarrativeCoverage` must never be rendered as a progress bar, completion gate, or score.
It informs Story Guide and Story Idea generation only.

---

# 9. StoryGuideIdea

`StoryGuideIdea` provides reusable inspiration without requiring knowledge of the user's current physical scene.

```ts
interface StoryGuideIdea {
  id: string

  title: string

  description: string

  worksBestWhen?: string[]

  guidance?: string[]

  exampleAssetId?: AssetId

  // Future: user can bookmark a guide idea for later reference.
  // Behavior (persistence scope, sync, removal) is not yet defined.
  // Do not implement for MVP.
  saved?: boolean
}
```

Example:

```json
{
  "title": "Tiny in the frame",
  "description": "Use a person to communicate the scale of the landscape.",
  "worksBestWhen": [
    "large open landscape",
    "camera can remain still",
    "person can move through the frame"
  ],
  "guidance": [
    "Keep most of the frame landscape.",
    "Place the person far from the camera.",
    "Record for 6–8 seconds."
  ]
}
```

---

# 10. StoryState

`StoryState` represents Story's current understanding of the material collected so far.

It is derived state.

```ts
interface StoryState {
  storyId: StoryId

  momentCount: number

  narrativeCoverage: Record<string, NarrativeCoverage>

  lastUpdatedAt: Timestamp
}
```

Keep StoryState lightweight for MVP.

Do not build a complex Story Graph yet.

---

# 11. Moment

`Moment` is the primary user-facing media unit inside a persistent Story.

```ts
interface Moment {
  id: MomentId

  storyId: StoryId

  assetId: AssetId

  source: MomentSource

  understanding?: AssetUnderstanding

  narrativeRoles?: string[]

  createdAt: Timestamp
}
```

```ts
type MomentSource =
  | "directed"
  | "existing_media"
  | "spontaneous"
  | "camera_import"
```

> **Milestone B freeze note.** Earlier drafts used `directed_capture` /
> `spontaneous_capture`. The frozen values drop the `_capture` suffix to match
> the shipped Swift + Python code, which already persists these values on
> device; see `milestone-b-reconciliation.md` §4.1.

A Moment may come from:

```text
Story-directed capture
existing phone media
spontaneous capture
camera-imported media
```

A Moment does **not** imply that the media must appear in the generated video.

Story chooses which Moments improve the output.

---

# 12. Asset

`Asset` represents a physical media item.

```ts
interface Asset {
  id: AssetId

  type: AssetType

  location: AssetLocation

  localReference?: string
  proxyReference?: string
  thumbnailReference?: string

  durationSeconds?: number

  width?: number
  height?: number

  createdAt?: Timestamp
}
```

```ts
type AssetType =
  | "photo"
  | "video"
  | "audio"
```

```ts
type AssetLocation =
  | "local"
  | "temporary_cloud"
  | "generated"
```

For MVP, original user media should normally remain **local**.

Do not assume that every Asset has a permanent cloud URL.

---

# 13. AssetUnderstanding

`AssetUnderstanding` contains machine-generated information describing an Asset.

```ts
interface AssetUnderstanding {
  assetId: AssetId

  semanticDescription?: string

  sceneTags?: string[]

  peopleCount?: number

  actions?: string[]

  quality?: AssetQuality

  // Future: aesthetic preference scoring for clip selection ranking.
  // Not required for MVP; do not implement until clip selection demands it.
  aestheticsScore?: number

  usableSegments?: TimeRange[]

  embeddingReference?: string
}
```

```ts
interface AssetQuality {
  sharpness?: number
  stability?: number
  exposure?: number
  motionQuality?: number
}
```

Example:

```json
{
  "semanticDescription": "Two hikers walking toward a mountain ridge.",
  "sceneTags": [
    "mountain",
    "trail",
    "snow"
  ],
  "peopleCount": 2,
  "actions": [
    "walking"
  ],
  "quality": {
    "sharpness": 0.91,
    "stability": 0.73,
    "exposure": 0.88
  }
}
```

Not every field needs to be populated during MVP.

This model intentionally leaves room for the future large-library indexing system.

---

# 14. CaptureSession

`CaptureSession` represents one directed shooting interaction.

It can originate from:

```text
Create Now
Shoot a Moment
Story Idea → Show Me
```

```ts
interface CaptureSession {
  id: CaptureSessionId

  storyId?: StoryId

  entryPoint: CaptureEntryPoint

  creativeIntent: CreativeIntent

  sceneUnderstanding?: SceneUnderstanding

  selectedConcept?: StoryConcept

  storyPlan?: StoryPlan

  captures: Capture[]

  createdAt: Timestamp
}
```

```ts
type CaptureEntryPoint =
  | "create_now"
  | "shoot_moment"
  | "story_idea"
```

If `storyId` is absent, the CaptureSession belongs to standalone `Create Now`.

---

# 15. SceneUnderstanding

`SceneUnderstanding` describes what Story understands about the user's current environment.

```ts
interface SceneUnderstanding {
  id: SceneUnderstandingId

  summary: string

  environmentTags?: string[]

  subjects?: SceneSubject[]        // each: { label, note?, prominence? }

  lighting?: string                 // concise scalar description

  operatorSpace?:
    | "very_limited" | "limited" | "moderate" | "open" | "unknown"

  motionOpportunities?: string[]

  compositionOpportunities?: string[]

  constraints?: string[]
}

interface SceneSubject {
  label: string
  note?: string
  prominence?: "high" | "medium" | "low"   // VISUAL prominence, not semantic importance
}
```

> **Milestone C freeze note (2026-10-01).** Reconciled against the Scene
> Understanding tech design (`04-scene-understanding.md`). Adopted:
> - **`operatorSpace`** (coarse enum) — visibly apparent room for the camera
>   operator; a Director feasibility signal, NOT a safety guarantee.
> - **`prominence`** on each subject (`high|medium|low`) — visual prominence.
>
> **Deliberately NOT added yet** (will be added only if Director evaluation
> shows need): `scene_type` (covered by `summary` + `environmentTags`), a generic
> `visual_opportunities` bag (kept split as `motionOpportunities` +
> `compositionOpportunities` so observations don't blur into directing), a full
> `spatialStructure` object (foreground/midground/background/depth), an array
> `lighting`, and a separate `actionOpportunities` field (folded into
> `motionOpportunities`). These remain measurable experiments.
> Opportunities are OBSERVATIONS; Story Director decides what to shoot. Safety is
> a Director constraint, never a SceneUnderstanding conclusion.
> Canonical machine-readable contract:
> `contracts/schemas/scene-understanding.schema.json`.

Example:

```json
{
  "summary": "Large mountain viewpoint with an open trail and two hikers.",
  "environmentTags": [
    "mountain",
    "ridge",
    "trail"
  ],
  "lighting": "soft overcast",
  "motionOpportunities": [
    "walk toward ridge",
    "cross frame"
  ],
  "compositionOpportunities": [
    "large negative space",
    "small person against mountains"
  ]
}
```

SceneUnderstanding describes **what is there**.

It should not contain the final directing decision.

---

# 16. StoryConcept

`StoryConcept` is a creative idea proposed by Director Engine.

```ts
interface StoryConcept {
  id: StoryConceptId

  title: string

  summary: string

  rationale?: string

  previewAssetId?: AssetId

  targetNarrativeNeedId?: string
}
```

Example:

```json
{
  "title": "Walk Into the Scale",
  "summary": "Walk away from the camera toward the ridge while the mountains dominate the frame.",
  "targetNarrativeNeedId": "scale"
}
```

---

# 17. StoryPlan

`StoryPlan` describes the directed capture needed for one concept — WHAT
material would create the Story. It is a PLANNING object and does NOT own
execution progress (that is `DirectorState`, §20a).

```ts
interface StoryPlan {
  id: StoryPlanId

  conceptId: StoryConceptId

  beats: StoryBeat[]       // the narrative purposes this plan expresses

  shots: Shot[]            // every shot serves a beat (shot.beatId)

  estimatedDurationSeconds?: number
}

// A creative/narrative purpose the Story must express. Minimal by design.
interface StoryBeat {
  id: string               // e.g. "beat_scale"
  purpose: string          // "Establish the human/landscape scale contrast."
}
```

MVP should generally use `1–3 shots`. Do not generate elaborate production
shot lists. **Every Beat serves the StoryConcept; every Shot serves a Beat**
(05-story-director.md §20). Deliberately NO `beat_type`, `emotion_curve`,
`importance_score`, etc. on `StoryBeat` — added only on demonstrated need.

---

# 18. Shot

(Named `Shot` — the element of `StoryPlan.shots[]`; earlier drafts called it
`ShotPlan`.) A Shot has two explicit layers (05 §12): `purpose` is the INTERNAL
semantic reason it exists (what Validation cares about); `instruction` is the
simple USER-FACING direction. Keep them distinct — do NOT collapse into one, and
do NOT introduce duplicate names like `camera_behavior`/`subject_behavior`.

```ts
interface Shot {
  id: ShotId

  order: number

  instruction: string         // user-facing direction

  beatId?: string             // the StoryBeat this shot serves

  purpose?: string            // internal semantic reason (for Validation)

  targetDurationSeconds?: number

  framing?: string

  cameraMotion?: string

  subjectAction?: string

  exampleAssetId?: AssetId
}
```

Example:

```json
{
  "order": 1,
  "beatId": "beat_scale",
  "purpose": "Establish scale by keeping the person small against the mountain.",
  "instruction": "Have your partner walk down the trail. Stay here and keep them small against the mountain. Hold still for about 3 seconds.",
  "targetDurationSeconds": 3,
  "framing": "wide",
  "cameraMotion": "static",
  "subjectAction": "walk away along trail"
}
```

---

# 18a. DirectorDecision and DirectorState (Director loop)

DIRECT is a **decision loop**, not only a static plan generator
(05-story-director.md §5, §7, §19). The Director returns ONE strongest next
action; fulfillment is tracked as Director state, separate from the plan.

```ts
// What the user/system should DO next (one strongest recommendation).
interface DirectorDecision {
  action: "capture_shot" | "create_now" | "rescan_scene" | "retry_shot"
  shot?: Shot              // present for capture_shot / retry_shot
  reason?: string          // internal rationale (not necessarily user-facing)
}

// How far one beat has been fulfilled — DIRECTOR state, categorical.
interface BeatProgress {
  beatId: string
  status: "unfulfilled" | "partial" | "fulfilled"
  supportingAssetIds?: AssetId[]   // optional; its need is an open experiment
}

// Mutable DIRECT execution state, owned by the CaptureSession (§20b).
interface DirectorState {
  currentBeatId?: string
  beatProgress: BeatProgress[]
  lastDecision?: DirectorDecision
}
```

Responsibility boundary (05 §6, §7):
- **Shot Validator** answers "did we capture the requested Shot?"
  (`ValidationResult`, shot-level — §20).
- **Director** answers "did what we captured sufficiently fulfill this Beat?"
  (`BeatProgress`). `ValidationResult` carries NO beat-fulfillment score.
- `StoryPlan` = the intent (stable); `DirectorState` = what actually happened
  (mutable). They are kept separate deliberately.

---

# 19. Capture

`Capture` represents actual media recorded for a ShotPlan.

```ts
interface Capture {
  id: CaptureId

  shotPlanId: ShotPlanId

  assetId: AssetId

  validation?: ValidationResult

  createdAt: Timestamp
}
```

---

# 20. ValidationResult

Validation answers:

> Is this shot usable?

It must **not** attempt to determine whether the shot is professionally perfect, aesthetically strong, or artistically well-executed.
The sole question is: did Story get a usable version of what it requested?
Retakes should remain rare.

```ts
interface ValidationResult {
  usable: boolean

  confidence?: number

  issues?: ValidationIssue[]

  recommendation:
    | "accept"
    | "retake"
}
```

```ts
type ValidationIssue =
  | "too_short"
  | "severe_shake"
  | "subject_missing"
  | "severe_underexposure"
  | "severe_overexposure"
  | "instruction_not_followed"
```

Retakes should remain rare.

---

# 21. StoryIdea

`StoryIdea` is a Story-level recommendation generated from:

```text
CreativeIntent
+
StoryBlueprint
+
StoryState
+
existing Moments
```

It does not require current scene understanding.

```ts
interface StoryIdea {
  id: StoryIdeaId

  storyId: StoryId

  title: string

  description: string

  targetNarrativeNeedId?: string

  createdAt: Timestamp
}
```

Example:

```json
{
  "title": "A moment together",
  "description": "You've captured the scale beautifully. A quiet moment together could add warmth.",
  "targetNarrativeNeedId": "human"
}
```

If the user chooses `Show Me`, the StoryIdea becomes input to a scene-aware CaptureSession.

---

# 22. MusicAsset

`MusicAsset` represents an actual soundtrack Story can use.

```ts
interface MusicAsset {
  id: MusicAssetId

  title: string

  durationSeconds: number

  moodTags: string[]

  source: MusicSource

  audioReference: string

  analysis?: MusicAnalysis
}
```

```ts
type MusicSource =
  | "story_catalog"
  | "user_import"
```

MVP should primarily use a small licensing-safe Story music catalog.

---

# 23. MusicAnalysis

```ts
interface MusicAnalysis {
  bpm?: number

  beats?: number[]

  sections?: MusicSection[]

  energyCurve?: EnergyPoint[]
}
```

```ts
interface MusicSection {
  type:
    | "intro"
    | "build"
    | "peak"
    | "break"
    | "outro"
    | "other"

  startSeconds: number
  endSeconds: number
}
```

MusicAnalysis becomes an input to Edit Engine.

---

# 24. EditPlan

`EditPlan` is the structured editing specification produced by Edit Engine.

```ts
interface EditPlan {
  id: EditPlanId

  creativeIntentId: CreativeIntentId

  musicAssetId?: MusicAssetId

  targetDurationSeconds: number

  outputFormat: OutputFormat

  segments: EditSegment[]

  createdAt: Timestamp
}
```

```ts
interface EditSegment {
  order: number

  assetId: AssetId

  sourceStartSeconds?: number
  sourceEndSeconds?: number

  outputDurationSeconds: number

  crop?: CropInstruction

  speed?: number

  transition?: TransitionInstruction

  narrativeRole?: string
}
```

```ts
// Minimal stub — Media Engine owns the final shape.
// Expand in coordination with Media Engine implementation.
interface CropInstruction {
  x: number        // normalized 0–1, left edge
  y: number        // normalized 0–1, top edge
  width: number    // normalized 0–1
  height: number   // normalized 0–1
  aspectRatio?: string  // e.g. "9:16", "1:1"
}
```

```ts
// Minimal stub — Media Engine owns the final shape.
interface TransitionInstruction {
  type: "cut" | "fade" | "dissolve"
  durationSeconds?: number
}
```

The architectural rule is:

```text
AI / Edit Engine
      ↓
   EditPlan
      ↓
Media Engine
      ↓
    MP4
```

AI decides **what the edit should be**.

Media Engine deterministically executes that plan.

Do not put creative reasoning inside Media Engine.

---

# 25. GeneratedOutput

`GeneratedOutput` represents one finished video.

```ts
interface GeneratedOutput {
  id: GeneratedOutputId

  storyId?: StoryId

  sourceMomentIds?: MomentId[]

  captureSessionId?: CaptureSessionId

  editPlanId: EditPlanId

  musicAssetId?: MusicAssetId

  outputAssetId: AssetId

  createdAt: Timestamp
}
```

A Story can have many outputs:

```text
Tour du Mont Blanc
│
├── Day 2 version
├── Day 5 version
├── Full trip version
└── Alternative music version
```

These are not separate Stories.

---

# 26. ExistingMediaImport

`ExistingMediaImport` represents the session when a user creates from media they already have (the "Use Existing Photos / Videos" entry point).

This flow skips directed capture entirely. It is distinct from `CaptureSession`.

```ts
interface ExistingMediaImport {
  id: ExistingMediaImportId

  storyId?: StoryId

  creativeIntent: CreativeIntent

  selectedAssetIds: AssetId[]

  // populated after Asset Engine processes the selected media
  assetUnderstandings?: Record<AssetId, AssetUnderstanding>

  editPlanId?: EditPlanId

  createdAt: Timestamp
}
```

Flow:

```text
CreativeIntent
      +
selectedAssetIds
      ↓
Asset Engine (AssetUnderstanding per asset)
      ↓
Story determines what is achievable
      ↓
EditPlan
      ↓
Music-aware assembly
      ↓
GeneratedOutput
```

For MVP, handle a small number of selected assets only.

Large-library indexing and thousands-of-photo workflows are explicitly postponed.

---

# 27. OutputFormat

```ts
type OutputFormat =
  | "vertical"
  | "square"
  | "landscape"
```

MVP default:

```text
vertical
```

---

# 28. Core Story Lifecycle

```text
Start a Story
      ↓
    ACTIVE
      │
      ├── Add Moments
      │
      ├── Shoot a Moment
      │
      ├── Story Guide
      │
      ├── Story Idea
      │
      ├── Create My Story
      │       ↓
      │   GeneratedOutput
      │       ↓
      │     ACTIVE
      │
      └── Complete Story
              ↓
          COMPLETED
              │
              ├── Create My Story
              ├── View Moments
              ├── View Outputs
              │
              └── Reopen Story
                       ↓
                     ACTIVE
```

Important:

```text
Create My Story ≠ Complete Story
```

`Create My Story` creates an output.

`Complete Story` changes organizational lifecycle state.

---

# 29. Create Now Flow

Create Now does not require a persistent Story.

```text
CreativeIntent
      ↓
CaptureSession
      ↓
SceneUnderstanding?
      ↓
StoryConcept
      ↓
StoryPlan
      ↓
Capture[]
      ↓
EditPlan
      ↓
GeneratedOutput
```

`storyId` is optional for this flow.

---

# 30. Shoot a Moment Flow

Persistent Story capture reuses DIRECT.

```text
Story
  ↓
Shoot a Moment
  ↓
CaptureSession(storyId)
  ↓
SceneUnderstanding?
  ↓
StoryConcept
  ↓
StoryPlan
  ↓
Capture
  ↓
Asset
  ↓
Moment
  ↓
StoryState update
```

Do not build a separate directing engine for persistent Stories.

---

# 31. Story Idea → Show Me Flow

```text
Story
  ↓
StoryIdea
  ↓
Show Me
  ↓
SceneUnderstanding
  ↓
Scene-specific StoryConcept
  ↓
StoryPlan
  ↓
Capture
  ↓
Moment
```

This separates:

```text
Story-level reasoning
```

from:

```text
scene-specific directing
```

---

# 32. Create My Story Flow

```text
Story
  ↓
Moments[]
  ↓
AssetUnderstanding[]
  ↓
CreativeIntent
  ↓
MusicDirection
  ↓
MusicAsset
  ↓
EditPlan
  ↓
Media Engine
  ↓
GeneratedOutput
```

The Story's active/completed status does not change.

---

# 33. Local-First Media Ownership

Original user media should remain local-first.

```text
iPhone

Original photo/video
        │
        ├── local Asset reference
        ├── thumbnail
        ├── proxy
        │
        └── derived AI input
                  │
                  ▼
              Story API
```

The backend should not require permanent upload of every original asset.

When AI needs visual information, send only what is needed whenever practical, such as:

- resized image
- thumbnail
- sampled video frames
- short proxy
- metadata
- embeddings

This is important for Story's future ability to handle large camera libraries.

---

# 34. Identity

MVP does not require registration.

```ts
interface LocalIdentity {
  id: string
  createdAt: Timestamp
}
```

Stories belong initially to a local anonymous identity.

Future authenticated accounts must be able to adopt the user's existing local Stories without changing their Story IDs.

Do not spread account assumptions throughout the domain model.

---

# 35. Core Domain Invariants

These rules must remain true regardless of implementation.

### 1. Story and output are different concepts.

A Story can exist without a GeneratedOutput.

### 2. A Story can have multiple GeneratedOutputs.

### 3. Creating an output does not complete a Story.

### 4. Completing a Story does not generate an output.

### 5. A completed Story can still create outputs.

### 6. A completed Story can be reopened.

### 7. A Moment belongs to exactly one persistent Story in MVP.

### 8. An Asset may exist without becoming a Moment.

### 9. Not every Moment must appear in a GeneratedOutput.

### 10. Story Guide is advisory.

The user never needs to satisfy Story Guide before creating.

### 11. Story-level reasoning does not require the current scene.

### 12. Scene-specific directing should use SceneUnderstanding.

### 13. Original media does not require permanent cloud upload.

### 14. AI creates structured creative decisions.

Media Engine executes them deterministically.

### 15. Authentication is not required for MVP Story creation.

---

# 36. Explicitly Postponed Complexity

Do not add the following to the MVP core model:

- social profiles
- followers
- comments
- collaboration
- Story sharing ACLs
- cloud-sync state machines
- project folders
- archive states
- complex output version trees
- timeline editor state
- multi-track editing
- user-created asset tagging
- asset star ratings
- thousands-of-assets indexing
- duplicate clusters
- photo-library search index
- itinerary graphs
- mandatory day-by-day Story plans
- background notification schedules
- generative-video prompt graphs
- Spotify integration
- Apple Music integration
- TikTok music integration
- Instagram music integration

These can be added later without changing the core Story abstraction.

---

# 37. Summary

The core product model is:

```text
                     STORY
                       │
       ┌───────────────┼─────────────────┐
       │               │                 │
       ▼               ▼                 ▼
CreativeIntent     StoryBlueprint      Moments
       │               │                 │
MusicDirection     Story Guide           │
                       │                 │
                   Story Idea             │
                       │                 │
                       └──── Show Me ─────┤
                                         │
                                  CaptureSession
                                         │
                                  Director Engine
                                         │
                                      Capture
                                         │
                                       Moment
                                         │
                                         ▼
                                CREATE MY STORY
                                         │
                        ┌────────────────┼───────────────┐
                        │                │               │
                        ▼                ▼               ▼
                 CreativeIntent      Moments          Music
                        │                │               │
                        └────────────────┼───────────────┘
                                         ▼
                                     EditPlan
                                         │
                                         ▼
                                   Media Engine
                                         │
                                         ▼
                                GeneratedOutput
```

Story lifecycle remains independent:

```text
ACTIVE
  │
  ├── Create output ───────────────→ ACTIVE
  │
  └── Complete Story ──────────────→ COMPLETED
                                         │
                                         └── Reopen ──→ ACTIVE
```

The central design principle is:

> **Story understands what the user wants to make, helps them recognize and capture useful moments when needed, remembers those moments across an experience, and can turn the available material into a finished Story at any time.**

The schema should enable that experience without turning Story into a traditional video editor, photo-management system, or project-management application.