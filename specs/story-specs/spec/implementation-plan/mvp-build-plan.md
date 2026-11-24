# Story --- MVP Build Plan

**Status:** Milestone A (walking skeleton) **built, deployed, and verified
on a real iPhone**. Next work: expand the skeleton to full UX coverage,
then begin real AI engines.\
**Last reconciled:** 2026-10-01 against the shipped repo
(`lingzhang1/story`).\
**Product goal:** Build the smallest real iPhone product that proves
Story can **plan, guide, manage, and create visual stories** for
ordinary users.

> **⛔ C4 Shot Validation plan update (2026-10-05).** Inline semantic Shot Validation
> (the old C4 "real ValidationResult from captured video → BeatProgress" path) is
> **REJECTED for the MVP** per the GO/NO-GO audit (`milestone-c4-go-no-go-audit.md`,
> evidence in `milestone-c4a*` reports). The active plan is **C4-LITE: a local-only
> capture-integrity checker** (`milestone-c4-lite-capture-integrity-design.md`) — no
> AI/AWS/network, neutral "Saved/Moment added", integrity-only negatives, **no semantic
> shot/beat success claim**. The external `ValidationResult` schema object below still
> exists; what changed is that **no inline semantic validation engine is built** and the
> semantic Shot/Beat judgment moves to the future **asynchronous Asset Understanding**.
> Mentions of `ValidationResult` in the mock/inventory sections below are unaffected
> (they describe the schema object, not an inline engine).

------------------------------------------------------------------------

# 0. Progress Snapshot (what is actually built)

The walking skeleton exists and runs end-to-end. The implemented slice is
a **deliberate subset** of the full Milestone A spec below (§7): the
Start-a-Story vertical was built first to prove architecture, persistence,
and real device media before widening UX.

## Done and verified ✅

| Area | State |
|---|---|
| **Monorepo** | `/Users/lingzhang/Workplace/story`, pushed to [`lingzhang1/story`](https://github.com/lingzhang1/story) (private). Nested `specs/`, `prototypes/` stay independent. |
| **Contracts package** | `contracts/schemas/domain.py` (pure domain), `dto.py` (wire DTOs), generated `story.schema.json` + `openapi/openapi.json`. Domain / DTO / persistence kept distinct. |
| **Backend (`apps/api`)** | FastAPI. Endpoints: `GET /health`, `POST /v1/stories` (mock StoryEngine derives CreativeIntent), `POST /v1/stories/{id}/outputs` (mock EditEngine; asserts Create ≠ Complete). In-memory store (stateless MVP). |
| **Engine packages** | 7 packages wired as **Protocol + deterministic mock**: `story_engine`, `director_engine`, `edit_engine`, `asset_engine`, `music_engine`, `model_gateway`, `observability`. No real AI. |
| **iOS app (`apps/ios`)** | SwiftUI + SwiftData + AVFoundation, feature-oriented layout. Models (media stored as **relative path**, never blob/cloud URL), protocol-based engine clients + mocks, real-camera capture, local persistence with cascade delete, playback. |
| **Container** | Multi-stage `Dockerfile`, port 8080. |
| **Infra (`infrastructure/cdk`)** | TypeScript CDK, L1 `CfnService` App Runner + ECR (referenced by stable name), least-privilege roles, **zero** DynamoDB/SQS/Lambda/S3/API Gateway (jest-asserted). |
| **Tests** | Backend `pytest` 12, contracts `pytest` 3, CDK jest 5 — all green. |
| **Deploy** | Live dev backend on App Runner at `https://ydmju5wdps.us-east-1.awsapprunner.com` (account 989088054552, us-east-1). Image built in-cloud via throwaway CodeBuild (no local Docker), torn down after. `/health` 200 and `POST /v1/stories` 201 verified against the live URL. |
| **Device acceptance** | Full slice verified on a real iPhone (free personal signing, 7-day profile): Start a Story → capture a real video Moment → Create My Story (status stays `active`) → kill → relaunch → everything (incl. playable video) survives. |

## Implemented UX slice (subset of frozen UX)

``` text
HOME (minimal)
└── Start a Story
        ↓
   Creative Direction  (mock CreativeIntent)
        ↓
   Story Home ── Moments
        ├── Shoot a Moment  (mock direction → real camera → Moment)
        └── Create My Story (mock GeneratedOutput; status unchanged)
```

## NOT yet built (remaining Milestone A scope, see §7)

- Home entry points **Create Now** and **Use Existing Photos / Videos**
- **Story Guide**, **Story Idea / Show Me**
- **Complete / Reopen** Story lifecycle
- Photo-library **picker** / existing-media import
- `CaptureSession`, `SceneUnderstanding`, `StoryConcept`/`StoryPlan`/
  `ValidationResult` objects (schema-defined but not realized in code yet)
- Visual design pass to match the frozen Figma UX (current UI is a plain
  functional skeleton; design is a separate view-layer step)

## Known divergences to reconcile

- **MomentSource values** differ between schema and code. Schema (`02`):
  `directed_capture` / `spontaneous_capture` / `existing_media` /
  `camera_import`. Code: `directed` / `spontaneous` / `existing_media` /
  `camera_import`. Align in Milestone B when contracts are frozen.
- Backend persistence is **in-memory** (`InMemoryStoryStore`) — the
  source of truth for Milestone A is the **iOS SwiftData store**; the
  backend is intentionally stateless for the slice.

------------------------------------------------------------------------

# 1. Original State (pre-build, retained for context)

Product definition and UX are sufficiently frozen to begin
implementation.

The MVP has three connected entry points:

``` text
HOME
├── Create Now
├── Start a Story
└── Use Existing Photos / Videos
```

The persistent Story experience includes:

``` text
Story Home
├── Moments
├── Shoot a Moment
├── Story Guide
├── Story Idea / Show Me
├── Create My Story
└── Complete / Reopen Story
```

The next work is not more broad UX invention.

The next work is:

``` text
CORE DOMAIN SCHEMA        ← done (02-core-story-schema.md)
      ↓
SYSTEM ARCHITECTURE       ← done (03-system-architecture.md)
      ↓
WALKING SKELETON          ← Start-a-Story slice done + on real iPhone;
      ↓                      remaining UX paths pending (§7)
REAL AI ENGINES           ← next after skeleton is widened
      ↓
MEDIA CREATION
      ↓
FIELD EVALUATION
```

------------------------------------------------------------------------

# 2. Repository Structure

Use one monorepo.

**As built** (reconciled 2026-10-01) — the shipped layout differs from the
original sketch below in a few ways, noted inline:

``` text
story/
├── apps/
│   ├── ios/                         # SwiftUI app (Xcode project at apps/ios/Story/)
│   └── api/                         # FastAPI backend (app/, Dockerfile, tests/)
│
├── contracts/                       # [moved to ROOT, not packages/] domain + DTO + schemas
│   ├── schemas/ (domain.py, dto.py, story.schema.json)
│   └── openapi/ (openapi.json)
│
├── packages/                        # engine packages (Python, underscore names)
│   ├── story_engine/                # Protocol + deterministic mock
│   ├── director_engine/
│   ├── asset_engine/
│   ├── edit_engine/
│   ├── music_engine/
│   ├── model_gateway/
│   └── observability/
│   # NOTE: no media-engine package yet (rendering is a later milestone)
│
├── infrastructure/
│   └── cdk/                         # [NEW] TypeScript CDK: App Runner + ECR
│
├── scripts/                         # dev.sh, export_openapi.py, build spec
├── evals/                           # placeholder (empty for now)
│
├── conftest.py  pyproject.toml  .dockerignore  .gitignore
│
└── specs/, prototypes/              # nested INDEPENDENT git repos
    ├── specs/story-specs            # this document lives here
    └── prototypes/story-figma       # frozen Figma reference prototype
```

Differences from the original sketch (not problems — just the as-built
reality to keep this doc honest):

- `contracts/` is at the repo **root**, not under `packages/`.
- Engine packages use **underscore** names (`story_engine`) for Python
  import ergonomics, not hyphens.
- Infra added under `infrastructure/cdk/` (not in the original tree).
- No `services/worker/` and no `media-engine` package yet — rendering is a
  later milestone (§17), split only when needed.
- `specs/` and `prototypes/` are **separate git repos** nested in the
  tree, not plain folders of the monorepo.

**Original sketch (target reference):**

``` text
story/
├── apps/
│   ├── ios/                         # Production iPhone app
│   └── api/                         # Story backend/API
│
├── packages/
│   ├── contracts/                   # Shared API/domain contracts
│   ├── story-engine/                # Persistent Story reasoning
│   ├── director-engine/             # Scene → concept → shot plan
│   ├── asset-engine/                # Photo/video understanding
│   ├── edit-engine/                 # Moments → EditPlan
│   ├── music-engine/                # Music recommendation/analysis
│   ├── media-engine/                # Deterministic rendering
│   ├── model-gateway/               # AI provider abstraction
│   └── observability/               # Logs/evals/traces
│
├── services/
│   └── worker/                      # Async rendering/heavy jobs when needed
│
├── prototypes/
│   └── figma/                       # Frozen Figma HTML/reference prototype
│       └── README.md
│
├── specs/
│   ├── story-production.md
│   ├── mvp-build-plan.md
│   ├── 02-core-story-schema.md
│   └── 03-system-architecture.md
│
├── evals/
│   ├── director/
│   ├── scene-understanding/
│   ├── asset-selection/
│   └── editing/
│
└── scripts/
```

The Figma HTML is reference code only.

Production code must not depend on `prototypes/figma`.

------------------------------------------------------------------------

# 3. Architecture Decisions to Freeze Before Coding Deeply

Before the walking skeleton expands, create `03-system-architecture.md`
and lock the following decisions:

-   iOS technology and application layering
-   backend language/framework
-   monorepo tooling
-   local persistence technology
-   API protocol
-   local vs cloud ownership
-   temporary media upload strategy
-   background job strategy
-   package dependency rules
-   model gateway interface
-   rendering approach
-   development/staging configuration
-   secrets management
-   observability
-   mock vs production engine interfaces

Do not design production microservices, Kubernetes, or large-scale
infrastructure.

For MVP, use one backend deployment with logical package boundaries.

The render worker can be split later if necessary.

------------------------------------------------------------------------

# 4. Core Domain Contract

`02-core-story-schema.md` is the canonical product-domain contract.

The implementation must preserve:

``` text
Story
├── CreativeIntent
├── MusicDirection
├── StoryBlueprint
├── StoryState
├── Moments[]
├── CaptureSessions[]
└── GeneratedOutputs[]
```

Important invariants:

``` text
Story != GeneratedOutput

Create My Story != Complete Story

Story-level guidance != Scene-specific direction
```

A Story can generate multiple outputs.

Original user media is local-first.

Do not let individual agents invent conflicting Story models.

------------------------------------------------------------------------

# 5. Logical Runtime Architecture

``` text
                    iPHONE
        ┌───────────────────────────┐
        │ SwiftUI                   │
        │ Camera / Photos           │
        │ Local Story persistence   │
        │ Local media references    │
        │ Playback                  │
        └─────────────┬─────────────┘
                      │ HTTPS
                      ▼
               ┌─────────────┐
               │  Story API  │
               └──────┬──────┘
                      │
       ┌──────────────┼─────────────────┐
       ▼              ▼                 ▼
 Story Engine   Director Engine     Edit Engine
       │              │                 │
       ├──────────────┼──────────┐      │
       ▼              ▼          ▼      ▼
 Asset Engine    Music Engine   Model Gateway
                                     │
                                  AI models

 EditPlan
    ↓
 Media Engine
    ↓
 GeneratedOutput
```

These are logical modules, not separate MVP services.

------------------------------------------------------------------------

# 6. Ownership Boundaries

## iOS owns

-   UI and navigation
-   camera capture
-   Photos integration
-   original local media
-   local Story persistence
-   Moment references
-   thumbnails/proxies
-   permissions
-   playback
-   lightweight client state

## Backend owns

-   orchestration
-   structured AI requests
-   model-provider access
-   Story/Director reasoning that requires server AI
-   temporary processing
-   async job coordination
-   edit planning
-   server-side rendering if selected

## Story Engine owns

-   StoryBlueprint
-   StoryState
-   Story Guide
-   Story Ideas
-   long-horizon Story reasoning

## Director Engine owns

-   current-scene reasoning
-   StoryConcept
-   StoryPlan
-   shot instructions
-   capture feasibility

## Asset Engine owns

-   semantic media understanding
-   quality/usability metadata
-   usable segments
-   future indexing foundation

## Music Engine owns

-   MusicDirection interpretation
-   candidate tracks
-   beat/section analysis

## Edit Engine owns

-   asset selection
-   narrative ordering
-   trim decisions
-   pacing
-   music-aware EditPlan

## Media Engine owns

-   deterministic execution of EditPlan
-   trim
-   concatenate
-   crop/reframe
-   speed
-   transitions
-   audio
-   export

## Model Gateway owns

-   provider abstraction
-   structured generation
-   vision calls
-   future embeddings/model routing

------------------------------------------------------------------------

# 7. Milestone A --- Walking Skeleton on a Real iPhone

This is the immediate implementation milestone.

**STATUS (2026-10-01): PARTIALLY COMPLETE.** The Start-a-Story vertical
slice is built, deployed, and verified on a real iPhone (A1, A2, A5, A6-
subset, A7, and A8-subset all pass). Remaining: the Home entry points,
Story Guide / Story Idea / Show Me, Complete/Reopen, and the existing-
media picker (A3, A4-remainder). Per-task status is marked below.

The goal is not AI quality.

The goal is:

> **Every frozen product path works end-to-end on a real iPhone with
> mock intelligence and real local media/persistence.**

## A1. Project foundation  — ✅ DONE

Build:

-   monorepo structure
-   iOS app
-   API skeleton
-   environment configuration
-   contracts package
-   mock engine interfaces
-   logging
-   basic error handling

## A2. Local identity and persistence  — ✅ DONE (verified: kill/relaunch survives)

Implement:

-   anonymous local identity
-   Story creation
-   Story status
-   local Story persistence
-   Moments
-   CaptureSessions
-   GeneratedOutputs metadata

Test:

``` text
Create Story
→ add Moment
→ kill app
→ relaunch
→ Story and Moment still exist
```

## A3. Home  — ⏳ PENDING (only a minimal Home + Start a Story exists)

Implement frozen Home:

-   Create Now
-   Start a Story
-   Use Existing Photos / Videos
-   Continue
-   Your Stories

Active/completed organization must work.

## A4. Persistent Story  — 🟡 PARTIAL

Done: Creative Direction, Story Home, Moments, Shoot a Moment, Create My
Story. Pending: add existing photos/videos, remove/preview Moment, Story
Guide, Story Idea, Show Me, Complete Story, Reopen Story.

Implement:

-   Creative Direction
-   Story Home
-   Moments
-   add existing photos/videos
-   remove/preview Moment
-   Story Guide with mock content
-   Story Idea with mock content
-   Show Me
-   Shoot a Moment
-   Create My Story
-   Complete Story
-   Reopen Story

## A5. Real media plumbing  — 🟡 PARTIAL

Done: camera permission, video capture, local asset references,
thumbnails/playback, local persistence. Pending: photo-library permission
+ photo/video picker.

Implement real:

-   camera permission
-   photo-library permission
-   video capture
-   photo/video picker
-   local asset references
-   thumbnails
-   playback
-   local persistence

Do not upload originals by default.

## A6. Mock DIRECT  — 🟡 PARTIAL

Done: a deterministic MockDirectorEngine returns per-Moment shot guidance.
Pending as structured objects: SceneUnderstanding, StoryConcept,
StoryPlan, ValidationResult (not yet modeled in code).

Use deterministic mock data for:

-   SceneUnderstanding
-   StoryConcept
-   StoryPlan
-   ValidationResult

Example:

``` text
Concept: Walk Into the Scale

Shot 1:
Keep the camera still.
Walk toward the ridge.
6 seconds.
```

## A7. Mock Create My Story  — 🟡 PARTIAL

Done: mock GeneratedOutput created via MockEditEngine; Story status stays
unchanged (Create ≠ Complete, asserted). Pending: music selection UI, an
explicit "fake processing" state, Moments preview before create.

Implement:

-   preview available Moments
-   music selection UI
-   fake processing state
-   placeholder/mock GeneratedOutput

The Story status must remain unchanged.

## A8. Walking-skeleton acceptance test  — 🟡 PARTIAL (core slice ✅)

The core slice below is **verified on a real iPhone** (Start a Story →
Creative Direction → Story Home → Shoot a Moment → record real clip → save
→ inspect → Create My Story → mock result → kill → relaunch → state
intact). The full frozen-UX acceptance (Create Now, existing-media, Story
Idea/Show Me, Complete/Reopen) remains to be exercised once A3/A4 land.

A complete vertical slice must work:

``` text
Launch
→ Start a Story
→ define Creative Direction
→ Story Home
→ Shoot a Moment
→ mock idea
→ record real clip
→ save as Moment
→ Story Home
→ inspect Moments
→ Create My Story
→ mock result
→ return Home
→ kill app
→ relaunch
→ resume Story with state intact
```

Do not proceed to broad AI implementation until this works reliably.

------------------------------------------------------------------------

# 8. Milestone B --- Contracts and API Stabilization

Once the skeleton proves the object relationships, stabilize concrete
contracts.

Deliverables:

-   Swift models
-   backend models
-   API request/response schemas
-   package interfaces
-   serialization rules
-   error contracts
-   job-state contracts

Key objects:

-   Story
-   CreativeIntent
-   MusicDirection
-   StoryBlueprint
-   StoryState
-   Moment
-   Asset
-   AssetUnderstanding
-   CaptureSession
-   SceneUnderstanding
-   StoryConcept
-   StoryPlan
-   ShotPlan
-   ValidationResult
-   MusicAsset
-   MusicAnalysis
-   EditPlan
-   GeneratedOutput

Do not pass arbitrary prose between components where a structured
contract is appropriate.

------------------------------------------------------------------------

# 9. Milestone C --- Creative Intent

Replace mock intent handling with real AI.

Inputs:

``` text
template
+
user description
+
optional reference
+
context
+
desired duration
```

Output:

``` text
CreativeIntent
```

The output must be structured.

For reference media, MVP understanding can focus on:

-   mood
-   energy
-   pacing
-   average shot length
-   camera movement
-   subject/environment balance
-   general story grammar

Do not attempt perfect cinematic decomposition.

------------------------------------------------------------------------

# 10. Milestone D --- Scene Understanding

For scene-aware DIRECT:

``` text
3–5 second scan
      ↓
sample representative frames
      ↓
Vision model
      ↓
SceneUnderstanding
```

Extract only information needed for direction:

-   environment
-   subjects
-   lighting
-   motion opportunities
-   composition opportunities
-   constraints

Do not build full 3D scene reconstruction.

Latency matters. Avoid repeated expensive model calls during active
capture.

------------------------------------------------------------------------

# 11. Milestone E --- Director Engine

This is one of the highest-value MVP components.

Input:

``` text
CreativeIntent
+
optional Story context
+
SceneUnderstanding
+
Capture constraints
```

Output:

``` text
StoryConcept
+
StoryPlan
```

Optimize for:

``` text
creative quality
+
scene specificity
+
physical feasibility
+
low capture effort
```

MVP constraints:

``` text
max shots: 3
preferred shots: 1–2
capture time: roughly <= 30 seconds for short DIRECT
```

Recommend one strong default.

Alternatives are secondary.

------------------------------------------------------------------------

# 12. Milestone F --- Capture Guidance and Validation

Convert structured ShotPlans into simple sequential instructions.

Example:

``` text
Walk toward the signs.
↓
Ready?
↓
3... 2... 1...
↓
Go.
```

Validation should detect gross failure only:

-   clip too short
-   subject missing
-   catastrophic obstruction
-   severe shake
-   severe exposure problem
-   requested movement clearly missing

Output:

``` text
accept
```

or:

``` text
retake + simple reason
```

No aesthetic scores.

No "best take" ranking in MVP.

------------------------------------------------------------------------

# 13. Milestone G --- Persistent Story Intelligence

Replace mock Story Guide and Story Idea with real Story Engine behavior.

Input:

``` text
CreativeIntent
+
StoryBlueprint
+
StoryState
+
Moments / AssetUnderstanding
```

Output may include:

-   updated lightweight narrative coverage
-   Story Guide content
-   one useful Story Idea
-   recommendation to do nothing

The engine must understand that no intervention is often correct.

It should never require users to satisfy suggestions before creating.

------------------------------------------------------------------------

# 14. Milestone H --- Asset Understanding

> **DESIGN FROZEN 2026-10-05 — see `06-asset-understanding.md` (implementation-ready).**
> MVP AU is **Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6`) over 24 ordered timestamped
> frames**, one model, no routing/escalation, no native video, retry-once (no Opus/Nova
> fallback). Architecture: **on-device persistent AU job queue → local 24-frame extraction →
> small (~1–3 MB) request → EXISTING App Runner → `AssetUnderstandingEngine` → generic
> `ModelGateway` → Sonnet → `MomentUnderstanding` persisted locally**. **No** temp-S3 /
> presigned upload / SQS / Lambda-Fargate worker / Bedrock async (they did not earn their
> complexity — see the three Milestone-D experiment reports). Moment creation never blocks on
> AU. Build NOT started; bring the frozen design to review before implementation.

Build media analysis shared by persistent Story and existing-media
creation.

The frozen **MomentUnderstanding** contract (minimum, consumer-justified) keeps, in two
conceptually separated groups:

- **observed / asset-grounded:** `summary`, `subjects[]`, `events[]` (start_time, end_time,
  description), `temporal_order_note`, `useful_segments[]` (start_time, end_time, why_useful —
  asset-grounded candidate material, NOT final cuts);
- **Story-context interpretation:** `story_utility`, `requested_shot_contribution`,
  `requested_beat_contribution`.

Dropped for MVP: `environment`, `dead_or_setup_segments` (no distinct consumer in the final
experiment). `useful_segments` stays asset-grounded; final selection/ordering belongs to the
future Edit Planner. For video, identify useful ranges where practical.

This package should be designed so it can later grow into large-library
indexing without building that system now.

------------------------------------------------------------------------

# 15. Milestone I --- Music Engine

Start with a small curated, licensing-safe catalog.

Implement:

-   MusicDirection
-   track metadata
-   mood matching
-   preview
-   small alternative set
-   BPM/beat analysis
-   basic section/energy analysis

Music is an input to edit planning, not merely an audio track added
after editing.

## Music / Create Story Gate

Music is a first-class input to Story creation, not a post-render audio
overlay.

Before implementing the real Edit Planner / Create Story pipeline, complete
the dedicated Music design covering:

- MusicDirection contract
- MusicAsset contract
- curated MVP catalog
- recommendation
- preview / user override UX
- beat / section analysis
- music-aware EditPlan integration
- track-change → replan behavior
- storage / delivery
- licensing constraints
- evaluation

MVP may begin with approximately 5–10 curated tracks.

Do not implement the final Edit Planner assuming music can simply be added
after editing.

Music selection remains outside Story Director v1 / DIRECT capture.

------------------------------------------------------------------------

# 16. Milestone J --- Edit Engine

Inputs:

``` text
CreativeIntent
+
StoryState
+
Moments / AssetUnderstanding
+
MusicAsset / MusicAnalysis
```

Output:

``` text
EditPlan
```

EditPlan should specify:

-   selected assets
-   usable ranges
-   ordering
-   output duration
-   speed
-   crop/reframe
-   transitions
-   music
-   cut timing

The AI chooses the edit.

It does not perform media operations itself.

------------------------------------------------------------------------

# 17. Milestone K --- Deterministic Media Engine

Implement only operations required by MVP:

-   trim
-   concatenate
-   crop/reframe
-   speed adjustment
-   simple transitions
-   music
-   basic beat alignment
-   export vertical MP4

No timeline editor.

No effect library.

No professional editing UI.

No proprietary generative video.

Acceptance criterion:

``` text
EditPlan
→ deterministic renderer
→ playable/exportable MP4
```

------------------------------------------------------------------------

# 18. Milestone L --- Existing Media Path

Once Asset + Edit + Music engines work, complete:

``` text
Use Existing Photos / Videos
→ select small set of assets
→ CreativeIntent
→ AssetUnderstanding
→ achievable Story direction
→ Music
→ EditPlan
→ GeneratedOutput
```

For MVP, keep selection intentionally small.

Do not solve thousands-of-assets ingestion yet.

------------------------------------------------------------------------

# 19. Evaluation Dataset

Start this before the Director Engine is considered finished.

Create a small scenario library such as:

-   busy city square at night
-   scenic overlook
-   beach sunset
-   mountain viewpoint
-   forest trail
-   café
-   restaurant
-   hotel room
-   downtown street
-   park
-   museum exterior
-   snow landscape
-   birthday dinner
-   family event

For each, test multiple intents:

-   cinematic
-   energetic
-   romantic
-   landscape-focused
-   playful
-   calm

Human evaluation questions:

-   Is the recommendation scene-specific?
-   Is it physically possible?
-   Would I actually shoot it?
-   Does it match the requested style?
-   Is it meaningfully different from repetitive defaults?
-   Is the capture effort justified?

Keep evaluation artifacts under `evals/`.

### Evaluation requirement

Before significant prompt/model tuning, establish the milestone's curated
evaluation fixture set.

Before closing the milestone, every meaningful newly observed failure must
either:

- become a regression fixture; or
- be explicitly documented as intentionally unsupported/deferred.

Run the complete relevant evaluation suite before advancing to the next
intelligence milestone.

------------------------------------------------------------------------

# 20. Field Testing

Once real DIRECT works, test outside the office.

Test:

-   city street
-   scenic viewpoint
-   restaurant
-   park
-   beach
-   mountain/trail
-   indoor event

Record every moment where a tester says:

> "Why is it asking me to do this?"

or:

> "I would just use Camera."

Those are product failures even when the software technically works.

------------------------------------------------------------------------

# 21. Persistent Story Testing

Use one realistic multi-day scenario, such as TMB, to test the
persistent model.

Test:

``` text
create Story
→ inspect Story Guide
→ add existing Moment
→ shoot directed Moment
→ leave app
→ resume later
→ Story Idea
→ Show Me
→ capture
→ Create My Story
→ add more Moments
→ create another output
→ Complete Story
→ reopen Story
```

Verify that Create and Complete remain independent.

------------------------------------------------------------------------

# 22. Real User Test

Target users who:

-   travel or go out
-   care about good photos/videos
-   sometimes post Reels/short videos
-   are not professional videographers
-   do not enjoy serious editing

Test the three entry points separately and together.

For DIRECT, compare:

``` text
user's normal capture
vs
Story-directed capture
```

For persistent Story, evaluate:

-   whether Story Guide was useful before/during the experience
-   whether Story Ideas felt helpful or annoying
-   whether Moments made the experience easier to manage
-   whether users understood Create vs Complete
-   whether they created more than one output
-   whether they would use it on another trip/event

For existing media, compare time and output quality against the user's
normal workflow.

------------------------------------------------------------------------

# 23. Team / Agent Ownership

For a small human team using Kiro Crew, divide ownership by product
capability rather than "frontend vs backend."

## Product / AI owner

Own:

-   product decisions
-   CreativeIntent
-   Story Engine
-   Director quality
-   model selection/prompts
-   evaluation datasets
-   Figma/UX
-   user research

## Client / media owner

Own:

-   iOS
-   camera
-   Photos integration
-   local persistence
-   media ingestion
-   playback
-   deterministic video rendering

## Shared

Own:

-   core schema
-   system architecture
-   API contracts
-   field testing
-   metrics
-   major product decisions

Kiro can provide engineering bandwidth beneath these ownership
boundaries.

------------------------------------------------------------------------

# 24. Kiro Work Breakdown

Do not give Kiro a single prompt such as:

> "Build Story MVP."

Give it bounded tasks aligned with the architecture.

Suggested work areas:

``` text
01-project-foundation
02-core-story-schema
03-system-architecture
04-ios-shell-and-navigation
05-local-persistence
06-media-capture-and-picker
07-api-skeleton
08-creative-intent
09-scene-understanding
10-director-engine
11-capture-guidance
12-shot-validation
13-persistent-story
14-asset-understanding
15-music-engine
16-edit-engine
17-media-engine
18-existing-media-flow
19-evaluation
```

Each task should define:

-   objective
-   dependencies
-   owned files/packages
-   interfaces
-   acceptance criteria
-   tests
-   explicitly excluded work

Do not allow multiple agents to independently redefine shared domain
contracts.

------------------------------------------------------------------------

# 25. What to Fake First

For the walking skeleton, fake:

-   Story Guide intelligence
-   Story Idea intelligence
-   SceneUnderstanding
-   StoryConcept
-   StoryPlan
-   ValidationResult
-   EditPlan
-   GeneratedOutput
-   music recommendation

Use real:

-   iPhone navigation
-   camera
-   photo picker
-   local persistence
-   Moment storage
-   playback
-   Story lifecycle
-   permissions
-   real device behavior

This isolates architecture/UX failures before model quality becomes
involved.

------------------------------------------------------------------------

# 26. What Not to Build Yet

Do not add:

-   generative missing drone shots
-   thousands-of-photo indexing
-   automatic deduplication
-   deep personalization
-   AI avatars
-   AR overlays
-   full timeline editing
-   cloud photo library
-   mandatory accounts
-   social features
-   complex collaboration
-   third-party music catalogs
-   production microservices
-   sophisticated infrastructure

A feature enters MVP only if it helps test:

> **Can Story meaningfully plan, guide, manage, or create a user's
> visual story better than their normal camera + photo library + editing
> workflow?**

------------------------------------------------------------------------

# 27. Immediate Next Steps

**Original plan (steps 1-8 complete):**

``` text
1. Finalize 02-core-story-schema.md          ✅ done
2. Write 03-system-architecture.md           ✅ done
3. Create monorepo/package skeleton          ✅ done
4. Move Figma HTML under prototypes/figma/    ✅ done (prototypes/story-figma)
5. Add prototypes/figma/README.md             ✅ done
6. Build Milestone A walking skeleton         🟡 Start-a-Story slice done
7. Run it on a real iPhone                     ✅ done + full acceptance passed
8. Fix architecture/state/persistence issues   ✅ none blocking
9. Stabilize concrete API/contracts            ⏳ next (Milestone B)
10. Begin CreativeIntent + SceneUnderstanding + Director Engine
```

**Actual next work, in order:**

``` text
1. (Optional, high visual payoff) DesignSystem pass — match the frozen
   Figma UX in the SwiftUI view layer only. Low risk: views already
   depend on protocols; domain/persistence/engine code is untouched.
2. Widen Milestone A to full frozen UX (A3/A4 remainder):
   Home (Create Now, Use Existing Photos), Story Guide, Story Idea /
   Show Me, Complete / Reopen, photo-library picker.
3. Reconcile MomentSource naming (schema vs code) and freeze contracts
   (Milestone B): add CaptureSession, SceneUnderstanding, StoryConcept,
   StoryPlan, ValidationResult, Asset/AssetUnderstanding to the shared
   contract and the Swift/backend models.
4. Only then begin real AI (Milestone C onward).
```

The walking skeleton should start only after the core schema and
lightweight architecture decisions are clear enough that Kiro does not
invent them during implementation.

Do not wait for a perfect production architecture.

The goal is to define stable boundaries, then learn by building.

**Operational note:** the dev App Runner service bills while running
(~$5-15/mo at 1 vCPU / 2 GB). Pause or tear it down between test sessions
when the API is not being exercised.

------------------------------------------------------------------------

# 28. First Major Acceptance Milestone

The first meaningful engineering milestone is:

> **A real iPhone can create a persistent Story, capture/import real
> media into Moments, leave and resume the Story, invoke a mock directed
> capture, preview current material, create a mock output,
> complete/reopen the Story, and retain everything after app restart.**

Once that works, the product architecture is real enough to begin
replacing mocks with intelligence.

The next major product milestone is:

> **Story gives a real scene-specific recommendation that makes the team
> say, "I genuinely would not have thought to shoot it this way."**

If that does not happen, improve the Director before expanding scope.

------------------------------------------------------------------------

# 29. MVP Success Definition

The MVP succeeds if evidence suggests that Story can provide value
across four connected jobs:

1.  **Plan** --- translate vague creative intent into useful Story
    direction.
2.  **Guide** --- help users capture better material when direction is
    worth the friction.
3.  **Manage** --- remember Moments and evolving Story state across an
    experience.
4.  **Create** --- turn available material into a music-aware finished
    visual story with little manual editing.

The product should feel like one AI Story Director across these jobs,
not four disconnected tools.



