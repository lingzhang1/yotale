# Story --- System Architecture

**Document:** `03-system-architecture.md`\
**Status:** MVP v0.2 --- AWS Architecture Baseline\
**Related specs:** `story-production.md`, `mvp-build-plan.md`,
`02-core-story-schema.md`, `04-aws-infrastructure.md`

## 1. Purpose

This document defines where Story code and state live, how components
communicate, how media is handled, and which boundaries Kiro must
preserve.

Story's product goal is to help users **plan, guide, manage, and create
visual stories**.

Product behavior belongs in `story-production.md`; domain semantics
belong in `02-core-story-schema.md`; implementation sequence belongs in
`mvp-build-plan.md`.

## 2. Core Architecture Principles

1.  **Cloud thinks; device owns media.** Cloud AI handles creative
    reasoning. Original media, playback, local Story state, and MVP
    rendering remain on-device.
2.  **Local-first, not offline-only.** Stories and media survive locally
    without an account; intelligence may require network access.
3.  **One modular backend.** Story Engine, Director Engine, Asset
    Engine, Music Engine, Edit Engine, and Model Gateway are modules,
    not MVP microservices.
4.  **Structured state over giant agents.** AI transforms explicit
    domain objects into explicit domain objects; persistent state is not
    hidden in model chat history.
5.  **AI decides; deterministic systems execute.** AI creates plans such
    as `StoryPlan` and `EditPlan`; deterministic code performs
    capture/media operations.
6.  **Interfaces before implementations.** Every intelligence component
    has mock and real implementations so Milestone A can work without
    production AI.
7.  **Minimize media transfer.** Upload only resized images, sampled
    frames, short proxies, or other representations actually required
    for a task.
8.  **No mandatory account.** MVP uses a local anonymous identity.
9.  **AWS is the deployment platform.** Cloud infrastructure is
    provisioned with AWS CDK written in TypeScript. Application/domain
    code must remain independent of CDK.
10. **Language boundaries follow responsibilities.** Consumer iOS
    remains Swift; backend and AI engines use Python; infrastructure
    uses TypeScript.

## 3. System Context

``` text
                         STORY iOS APP
              ┌────────────────────────────┐
              │ SwiftUI                    │
              │ Camera / Photos            │
              │ SwiftData                  │
              │ Original media             │
              │ Playback                   │
              │ On-device Media Engine     │
              └──────────────┬─────────────┘
                             │ HTTPS / JSON
                             ▼
                    ┌─────────────────┐
                    │    Story API    │
                    │ orchestration   │
                    │ validation      │
                    │ temp uploads    │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   Story Engine       Director Engine      Edit Engine
          │                  │                  │
          ├────────────┬─────┴──────┬──────────┘
          ▼            ▼            ▼
    Asset Engine   Music Engine  Model Gateway
                                     │
                                     ▼
                                  AI Models

              EditPlan returned to iPhone
                             │
                             ▼
                  On-device AVFoundation
                             │
                             ▼
                    GeneratedOutput
```

## 4. Repository Structure

``` text
story/
├── apps/
│   ├── ios/                         # Production native iPhone app — Swift
│   └── api/                         # Python API/orchestration application
├── packages/
│   ├── story_engine/                # Python
│   ├── director_engine/             # Python
│   ├── asset_engine/                # Python
│   ├── music_engine/                # Python
│   ├── edit_engine/                 # Python
│   ├── model_gateway/               # Python
│   └── observability/               # Python
├── infrastructure/
│   └── cdk/                         # AWS CDK — TypeScript
│       ├── bin/
│       ├── lib/
│       │   ├── stacks/
│       │   └── constructs/
│       └── test/
├── contracts/
│   ├── schemas/                     # Language-neutral JSON Schemas
│   └── openapi/
├── prototypes/
│   └── figma/                       # Frozen Figma HTML, reference only
├── specs/
│   ├── story-production.md
│   ├── mvp-build-plan.md
│   ├── 02-core-story-schema.md
│   ├── 03-system-architecture.md
│   └── 04-aws-infrastructure.md
├── evals/
│   ├── director/
│   ├── scene-understanding/
│   ├── asset-selection/
│   └── editing/
└── scripts/
```

`apps/ios` is the native consumer application. `apps/api` and the engine
packages are Python. `infrastructure/cdk` is TypeScript and contains
deployment definitions only. `contracts/` is language-neutral.

The Swift app never imports backend packages. Python application code
never imports CDK code. CDK deploys application artifacts but does not
define Story domain behavior.

## 5. Figma Prototype Boundary

Store Figma-generated HTML in `prototypes/figma/`.

It is a UX, interaction, and visual reference. It is **not production
frontend code** and production code must not depend on it.

Add `prototypes/figma/README.md` stating:

``` text
This directory contains the frozen Figma prototype and generated web code.
It is a UX and interaction reference for the production Story application.
Production code must not import from or depend on this directory.
The production iOS interface is implemented natively.
```

## 6. Technology Baseline

### iOS consumer app

-   Language: Swift
-   UI: SwiftUI
-   Camera: AVFoundation
-   Photo library: PhotoKit / PhotosPicker
-   Playback: AVKit
-   Rendering/export: AVFoundation
-   Concurrency: Swift Concurrency
-   Networking: URLSession
-   Structured persistence: SwiftData

Choose the concrete minimum supported iOS version during project setup
and record it in the repository.

### Backend and AI engines

-   Language: Python
-   API framework: FastAPI
-   Validation/domain DTOs: Pydantic
-   API description: OpenAPI
-   Testing: pytest
-   Packaging/dependency management: choose one Python project standard
    at repository bootstrap and use it consistently

Python owns API orchestration and the Story, Director, Asset, Music,
Edit, and Model Gateway implementations.

### Infrastructure

-   Cloud: AWS
-   Infrastructure as Code: AWS CDK
-   CDK language: TypeScript
-   Initial compute: AWS Lambda
-   API ingress: Amazon API Gateway
-   Temporary media: Amazon S3
-   Small operational/job state when needed: Amazon DynamoDB
-   Secrets: AWS Secrets Manager
-   Logs/metrics: Amazon CloudWatch
-   Permissions: AWS IAM
-   AWS-native model access where appropriate: Amazon Bedrock
-   Async expansion when required: Amazon SQS + Lambda
-   Heavy/long-running compute later when required: Amazon ECS/Fargate
    or AWS Batch

The backend must not depend directly on Lambda event shapes. AWS
adapters translate infrastructure events into application-level requests
so engines remain portable and testable.

## 7. Contracts

`02-core-story-schema.md` defines semantic meaning.

Machine-readable wire contracts live under:

``` text
contracts/
├── schemas/
│   ├── story.schema.json
│   ├── creative-intent.schema.json
│   ├── moment.schema.json
│   ├── scene-understanding.schema.json
│   ├── story-concept.schema.json
│   ├── story-plan.schema.json
│   ├── asset-understanding.schema.json
│   ├── music.schema.json
│   ├── edit-plan.schema.json
│   └── generated-output.schema.json
└── openapi/
    └── story-api.yaml
```

Generate or map these into Swift DTOs and Python/Pydantic DTOs.

Keep three concepts distinct:

``` text
Domain model       = what a concept means
API DTO            = what crosses the network
Persistence model  = how it is stored locally
```

Do not put transport-specific fields into the canonical domain model.

## 8. iOS Architecture

Use feature-oriented organization:

``` text
apps/ios/Story/
├── App/
├── Features/
│   ├── Home/
│   ├── CreateNow/
│   ├── StartStory/
│   ├── StoryHome/
│   ├── Moments/
│   ├── StoryGuide/
│   ├── StoryIdea/
│   ├── Capture/
│   ├── CreateStory/
│   ├── Music/
│   └── Output/
├── Domain/
│   ├── Models/
│   └── UseCases/
├── Data/
│   ├── Persistence/
│   ├── Repositories/
│   └── API/
├── Media/
│   ├── Camera/
│   ├── PhotoLibrary/
│   ├── Proxy/
│   ├── Playback/
│   └── Rendering/
├── DesignSystem/
└── Support/
```

Feature UI owns rendering, interaction, navigation, and loading/error
states.

Domain/use-case code owns operations such as:

``` text
startStory()
addMoment()
shootMoment()
createStoryOutput()
completeStory()
reopenStory()
```

Repositories abstract persistence and remote operations. Media modules
own device-specific capture, Photos, proxy, playback, and rendering
behavior.

UI must not call model providers, database primitives, or AVFoundation
rendering code directly.

## 9. Local Identity

On first launch, create an opaque `LocalIdentity` and persist it
locally.

No email, profile, or account is required.

Future account linking must preserve existing Story IDs.

## 10. Persistence and State Ownership

For MVP, the device is authoritative for the user's persistent Story
library.

Persist locally:

-   Story
-   status
-   CreativeIntent
-   MusicDirection
-   StoryBlueprint cache
-   StoryState cache
-   Moments
-   local Asset references
-   CaptureSession metadata
-   retained StoryIdeas
-   GeneratedOutput metadata
-   output file references

Use SwiftData for structured state.

Do not store original media blobs in SwiftData.

``` text
SwiftData
├── Story metadata
├── Moments
├── CaptureSession metadata
├── AI-derived cached metadata
└── GeneratedOutput metadata

PhotoKit / filesystem
├── original media
├── app-captured media
├── proxies
├── thumbnails where needed
└── generated videos
```

Cloud Story synchronization is deferred.

## 11. Media Ownership

Original media remains on-device by default.

An Asset may resolve to:

-   PhotoKit local identifier
-   app-owned local file
-   temporary cloud proxy
-   generated local file

Never design `Asset` as synonymous with a permanent cloud URL.

## 12. Media Sent to AI

Send the minimum representation required.

### Photo

``` text
local original
→ resize/compress locally
→ temporary AI input
```

### Scene scan

``` text
3–5 second scan
→ sample representative frames locally
→ resize/compress
→ Vision request
→ SceneUnderstanding
```

### Existing video

Prefer task-appropriate sampled frames, short low-resolution proxies,
metadata, or selected ranges rather than the full original.

## 13. Temporary Uploads

When a provider requires cloud-accessible media:

``` text
iOS
→ request temporary upload
→ Story API returns signed target
→ private temporary object storage
→ AI processing
→ structured derived result
→ object expires/deletes
```

Requirements:

-   private objects
-   signed access
-   opaque keys
-   short retention
-   automatic expiration
-   no permanent original-media storage by default

The domain is vendor-neutral.

## 14. Story API

The API is an orchestration boundary.

It owns:

-   validation
-   anonymous request identity
-   engine invocation
-   provider secrets
-   temporary upload coordination
-   async job coordination when needed
-   consistent errors
-   observability

It must expose Story-domain operations, not raw provider operations.

Illustrative endpoint families:

``` text
POST /v1/creative-intent

POST /v1/direct/scene-understanding
POST /v1/direct/concepts
POST /v1/direct/plan
POST /v1/direct/validate

POST /v1/stories/blueprint
POST /v1/stories/guide
POST /v1/stories/ideas
POST /v1/stories/reconcile

POST /v1/assets/analyze
POST /v1/music/recommend
POST /v1/edits/plan
POST /v1/uploads
```

Exact endpoints may be refined with OpenAPI.

Never expose a generic endpoint such as `/openai/chat`.

All app/backend endpoints start under `/v1/`.

## 15. Model Gateway

All external AI access passes through Model Gateway.

Conceptual interface:

``` ts
interface ModelGateway {
  generateStructured<T>(request): Promise<T>
  analyzeImages<T>(request): Promise<T>
  analyzeVideoProxy<T>(request): Promise<T>
  embed?(request): Promise<EmbeddingResult>
}
```

Model Gateway owns:

-   provider authentication
-   SDK adaptation
-   model routing
-   structured-output enforcement
-   timeout/retry behavior
-   request IDs
-   usage/cost/latency logging

It does not own Story product reasoning.

Model names are configuration, not domain constants.

No provider API key is shipped in the iOS app.

## 16. Story Engine

Story Engine owns long-horizon Story reasoning.

Inputs may include:

``` text
CreativeIntent
StoryBlueprint
StoryState
Moment summaries
AssetUnderstanding
```

Outputs may include:

``` text
StoryBlueprint
Story Guide
StoryIdea
updated StoryState
reconciliation decisions
```

It answers:

> What would improve this Story overall?

It does not direct the exact current camera setup.

## 17. Director Engine

Director Engine owns immediate scene-specific directing.

Inputs:

``` text
CreativeIntent
optional Story context
optional StoryIdea
SceneUnderstanding
capture constraints
```

Outputs:

``` text
StoryConcept
StoryPlan
ShotPlan[]
```

It answers:

> Given what the user wants and what is physically here, what should
> they shoot now?

Optimize for usefulness, scene specificity, feasibility, simplicity, and
low capture burden.

## 18. Asset Engine

Asset Engine answers:

> What is in this media and what parts are useful?

It may produce:

-   semantic description
-   scene tags
-   people/actions
-   basic technical quality
-   usable video ranges
-   potential narrative roles
-   future embeddings

Implement only fields needed by MVP consumers.

This boundary intentionally supports future large-library indexing
without building that system now.

## 19. Music Engine

Music Engine owns:

-   MusicDirection interpretation
-   candidate-track recommendation
-   track metadata
-   BPM
-   beats
-   sections
-   energy curve

MVP uses a small curated licensing-safe catalog.

Do not build Spotify, Apple Music, TikTok, or Instagram integrations.

## 20. Edit Engine

Edit Engine produces `EditPlan`.

Inputs:

``` text
CreativeIntent
StoryState
Moments
AssetUnderstanding
MusicAsset
MusicAnalysis
output constraints
```

Output specifies:

-   selected assets
-   source ranges
-   ordering
-   duration
-   crop/reframe intent
-   speed
-   simple transitions
-   music
-   cut timing
-   narrative roles

Edit Engine makes creative editing decisions but does not render media.

## 21. Media Engine

MVP Media Engine runs on-device using AVFoundation.

Input:

``` text
EditPlan
+ local assets
+ music asset
```

Responsibilities:

-   resolve local assets
-   trim
-   concatenate
-   crop/reframe
-   scale
-   speed changes
-   simple transitions
-   music mixing
-   basic audio handling
-   export
-   progress
-   cancellation

Output:

``` text
local MP4
→ GeneratedOutput
```

The renderer is deterministic and contains no hidden AI creative
reasoning.

## 22. Why Rendering Is On-Device

MVP renders on-device because:

-   originals already live on the phone
-   full-resolution upload is expensive and slow
-   privacy is better
-   AVFoundation supports required MVP operations
-   final outputs can remain local
-   it preserves local-first architecture

Revisit server rendering only if required by advanced effects,
generative media, cross-device workflows, or unsupported device
capabilities.

## 23. Mock Engine Strategy

Milestone A uses real product infrastructure with mock intelligence.

Define replaceable interfaces:

``` text
StoryEngine
├── MockStoryEngine
└── AIStoryEngine

DirectorEngine
├── MockDirectorEngine
└── AIDirectorEngine

AssetEngine
├── MockAssetEngine
└── AIAssetEngine

MusicEngine
├── MockMusicEngine
└── RealMusicEngine

EditEngine
├── MockEditEngine
└── AIEditEngine
```

The UI must not know which implementation produced a result.

## 24. Create Now Flow

``` text
Create Now
→ template/reference/description
→ Story API
→ CreativeIntent
→ optional local scene scan
→ sampled frames
→ SceneUnderstanding
→ Director Engine
→ StoryConcept + StoryPlan
→ iOS guided capture
→ local Asset/Capture
→ optional validation
→ Music + Edit planning
→ EditPlan
→ on-device Media Engine
→ GeneratedOutput
```

## 25. Start a Story Flow

``` text
Start a Story
→ Creative Direction
→ CreativeIntent
→ Story Engine
→ StoryBlueprint
→ persist Story locally
→ Story Home
```

A Story exists before it has Moments or generated outputs.

## 26. Add Existing Media Flow

``` text
Story Home
→ Add photos/videos
→ PhotosPicker
→ local Asset references
→ Moment[]
→ persist locally
→ optional/progressive AssetUnderstanding
→ update StoryState
```

Adding media does not automatically generate an output.

## 27. Shoot a Moment Flow

``` text
Story
→ Shoot a Moment
→ load CreativeIntent + StoryState
→ optionally scan current scene
→ SceneUnderstanding
→ Director Engine
→ StoryConcept + StoryPlan
→ guided local capture
→ Asset
→ Moment
→ persist locally
→ update StoryState
```

## 28. Story Idea → Show Me

``` text
Story Engine
→ StoryIdea
→ user taps Show Me
→ current SceneUnderstanding
→ Director Engine receives:
     StoryIdea
     CreativeIntent
     StoryState
     SceneUnderstanding
→ scene-specific StoryConcept
→ StoryPlan
→ capture
→ Moment
```

Story Idea is long-horizon reasoning; Show Me converts it into
scene-specific direction.

## 29. Create My Story Flow

``` text
Story
├── CreativeIntent
├── StoryState
├── Moments
└── MusicDirection
       ↓
ensure required AssetUnderstanding
       ↓
Story reconciliation
       ↓
Music Engine
       ↓
MusicAsset + MusicAnalysis
       ↓
Edit Engine
       ↓
EditPlan
       ↓
return to iOS
       ↓
resolve local originals
       ↓
on-device Media Engine
       ↓
local MP4
       ↓
GeneratedOutput
       ↓
persist locally
```

### AssetUnderstanding: on-device job queue (MVP, FROZEN 2026-10-05)

Authoritative design: `06-asset-understanding.md`. Asset Understanding runs as a **persistent
on-device job queue**, not a server-side fan-out:

``` text
Moment added
→ local persistent AU job queued   (Moment creation NEVER blocks on AU)
→ opportunistic analysis: local 24-frame extraction → small (~1–3 MB) request
  → existing App Runner /v1/asset-understanding → Sonnet 4.6 → MomentUnderstanding
→ MomentUnderstanding cached locally
```

`Create My Story` **consumes whatever `MomentUnderstanding` is already available locally**; it
does not itself trigger a server-side AU fan-out. The individual model call is synchronous
(p50 ~26s, well inside the 120s App Runner budget), while the product workflow is asynchronous
via the queue. There is **no** eager per-Moment cloud dispatch, **no** concurrent N-Moment
Bedrock fan-out at Create time, **no** SQS/worker/temp-S3 for AU.

> Exact gap-fill behaviour for any Moment still `PENDING` at Create time belongs to the future
> Create/Edit pipeline design and must NOT silently resurrect server-side N-Moment fan-out.

`Create My Story` never changes `Story.status`.

## 30. Complete / Reopen Story

These are local-first lifecycle operations:

``` text
completeStory()
active → completed

reopenStory()
completed → active
```

They do not render or generate anything.

## 31. Async Work

Use synchronous requests for operations expected to finish
interactively:

-   CreativeIntent
-   small scene analysis
-   StoryConcept
-   StoryPlan
-   StoryIdea

Use async jobs only when a workload cannot reliably complete
interactively, such as future long video analysis, batch processing,
server rendering, or generative media.

Reserved job states:

``` text
queued
running
succeeded
failed
cancelled
```

Do not introduce a queue until measured workload requires one.

## 32. Offline Behavior

Available offline:

-   Home
-   local Stories
-   Story Home
-   Moments browsing
-   output playback
-   camera capture
-   add local media
-   Complete/Reopen
-   cached Story Guide
-   local rendering when an EditPlan already exists

Requires network in MVP:

-   new model-backed CreativeIntent processing
-   scene understanding
-   new Story Ideas
-   AI Director
-   cloud AssetUnderstanding
-   new AI EditPlan
-   model-backed music recommendation when applicable

Network failure must never lose captured media.

## 33. Failure Handling

-   Scene analysis failure: retry or use a simpler fallback where the UX
    supports it.
-   Validation service failure: keep the captured clip.
-   Edit planning failure: keep all Moments and allow retry.
-   Rendering failure: keep EditPlan and source assets and allow retry.
-   Temporary upload failure: original local media remains untouched.

Never force a retake because the backend failed.

## 34. IDs and Idempotency

Use opaque UUIDs for domain IDs.

Prefer client-generated IDs for local-first objects where practical.

Retryable create operations should support idempotency.

Do not encode user data or semantics into IDs.

## 35. Privacy and Security

MVP baseline:

-   HTTPS only
-   provider secrets backend-only
-   no AI provider keys in the iOS bundle
-   private signed temporary media access
-   automatic temporary-media expiration
-   original media local by default
-   no raw media in logs
-   avoid unnecessary raw user text in logs
-   validate media type and request size
-   opaque IDs

Before external beta, perform a provider-by-provider privacy review for
any service receiving user media.

## 36. Data Minimization

For each model request, ask:

> What is the minimum data required for this task?

Examples:

``` text
Scene direction:
3–8 representative frames
not the entire 4K source video

Story Idea:
Moment summaries + StoryState
not all originals

Edit planning:
AssetUnderstanding + usable ranges + thumbnails
not full-resolution originals
```

## 37. Observability

Backend requests receive correlation IDs.

For AI operations record:

-   operation
-   provider/model
-   latency
-   success/failure
-   retries
-   structured-output validation failures
-   usage/cost when available

Useful non-sensitive product events include:

``` text
story_started
moment_added
shoot_moment_started
story_idea_shown
story_idea_used
shot_accepted
shot_retaken
create_story_started
create_story_succeeded
story_completed
story_reopened
```

Analytics is not a Milestone A blocker.

## 37a. OPS and Metrics

This section defines the operational signals, alarms, and runbook
triggers required to detect and respond to production issues.

### Request health

| Metric | Alarm threshold | Action |
|---|---|---|
| App Runner 5xx rate | > 1% over 5 min | Page on-call; check CloudWatch logs for stack traces |
| App Runner 4xx rate | > 5% over 5 min | Investigate; often client/schema mismatch |
| App Runner request latency p95 | > 30s | Investigate AI call bottleneck; check Bedrock latency |
| App Runner request latency p99 | > 90s | Critical — approaching 120s timeout; parallelize or async |
| App Runner timeout errors (502/504) | Any | Immediate — requests hitting 120s wall; move operation to async |

The 120-second App Runner request timeout is a hard ceiling. When p99
latency approaches 90 seconds, the operation must be moved to the async
worker path before it begins returning 502s to iOS clients.

### AI / Model Gateway

| Metric | Alarm threshold | Action |
|---|---|---|
| Bedrock throttling errors | > 3 in 1 min | Back off; check quota; consider request queue |
| Bedrock latency p95 | > 15s per call | Slow model; check model choice; reduce prompt size |
| Structured output validation failures | > 2% | Model drift or prompt regression; review recent changes |
| Model Gateway retries | > 10% of calls | Provider degraded; check Bedrock status page |
| AI cost per operation | Spike > 3× baseline | Unexpected prompt growth or wrong model routed |

### Asset Understanding (on-device queue) / Create My Story

| Metric | Alarm | Action |
|---|---|---|
| `/v1/asset-understanding` latency p95 | > 60s | Slow model/prompt; check Sonnet latency + frame payload size |
| AU structured-output validity after retry | < ~95% | Prompt/schema regression; run the frozen ground-truth gate |
| AU retry rate (one-retry policy) | > 15% of calls | Provider degraded or output-token cap too low |
| Create My Story end-to-end latency p95 | > 45s | Create consumes locally-cached MomentUnderstanding only; investigate the client, not a server AU fan-out |

AU is an **on-device, opportunistic, resumable** job queue (see §AssetUnderstanding). The server
sees one small 24-frame request per job; there is no eager server-side caching layer and no
concurrent N-Moment fan-out to monitor. Create My Story consumes whatever MomentUnderstanding is
already cached locally.

### S3 and media

| Metric | Alarm | Action |
|---|---|---|
| S3 presigned upload failures | > 1% | Check IAM; check bucket policy; check expiry |
| Temporary objects older than retention TTL | Any | S3 lifecycle may be misconfigured; verify lifecycle rule |
| S3 upload size rejected | Spike | Client-side proxy generation may be broken |

### Async worker (when enabled)

| Metric | Alarm | Action |
|---|---|---|
| SQS dead-letter queue depth | > 0 | Job failing repeatedly; check Lambda/Fargate logs |
| SQS queue age (oldest message) | > 5 min | Worker not consuming; check Lambda concurrency or Fargate task health |
| Worker Lambda errors | > 1% | Check CloudWatch logs |
| Worker job duration p95 | > 10 min (Lambda) | Consider migrating to Fargate task |

### Structured log fields (all backend requests)

Every log entry should include:

```json
{
  "correlation_id": "<uuid>",
  "operation": "<e.g. director.generate_shot_plan>",
  "duration_ms": 1240,
  "status": "success|failure",
  "provider": "bedrock|openai|anthropic",
  "model": "<model-id>",
  "retries": 0,
  "usage": { "input_tokens": 420, "output_tokens": 180 },
  "validation_passed": true
}
```

Never log raw media bytes, original filenames, user prompt text
verbatim, or anything that would constitute user PII.

### CloudWatch dashboards

Maintain at minimum:

- **API health:** request rate, latency (p50/p95/p99), error rate, timeout count
- **AI operations:** latency per engine, cost per operation type, validation failure rate
- **Create My Story:** end-to-end latency, cached vs uncached Moment ratio
- **Async worker:** queue depth, job duration, DLQ depth (when SQS enabled)

### Operational runbooks (write before staging)

1. **App Runner request timeout storm** — requests returning 502: identify the slow operation from p99 metrics, move it to async path or parallelize Bedrock calls
2. **Bedrock quota exceeded** — throttling errors: implement exponential backoff in Model Gateway; request quota increase if sustained
3. **AssetUnderstanding cache miss** — Create My Story consistently slow: verify eager analysis fires on `addMoment`; check for analysis failures being silently swallowed
4. **SQS DLQ messages accumulating** — worker jobs failing: inspect DLQ message body for error, check Lambda logs, fix and replay from DLQ

## 38. AI Evaluation

Evaluation artifacts live under `evals/`.

AI quality evaluation is separate from production telemetry.

Use human evaluation for Director, Story Guide, asset selection, and
editing quality.

Do not rely solely on models grading themselves.

## 39. Configuration and Feature Flags

Environment-specific values belong in configuration:

-   API URL
-   model names
-   model routing
-   timeouts
-   upload limits
-   mock/real engine selection
-   catalog configuration

Suggested environments:

``` text
local
development
staging
production
```

Use lightweight feature flags for:

``` text
real_scene_understanding
real_director
real_asset_analysis
real_edit_engine
music_engine
```

Do not build a complex feature-management service for MVP.

## 40. Dependency Rules

Allowed backend dependencies:

``` text
apps/api
  → story-engine
  → director-engine
  → asset-engine
  → music-engine
  → edit-engine
  → model-gateway
  → observability

story-engine
  → contracts
  → model-gateway

director-engine
  → contracts
  → model-gateway

asset-engine
  → contracts
  → model-gateway

music-engine
  → contracts
  → model-gateway when needed

edit-engine
  → contracts
  → model-gateway when needed

model-gateway
  → provider SDKs
```

Disallowed:

``` text
engines → apps/api
model-gateway → product engines
iOS → AI provider SDK/API
iOS → backend implementation packages
edit-engine → iOS Media Engine
production code → prototypes/figma
Python application/domain code → infrastructure/cdk
Swift application code → infrastructure/cdk
```

Prefer orchestration in the API/application layer:

``` text
API Orchestrator
├── Story Engine
├── Asset Engine
├── Music Engine
└── Edit Engine
```

Avoid chains of product engines calling one another and creating hidden
coupling.

## 41. Concurrency and Stale Responses

Local state is authoritative.

AI/network responses may arrive late.

Before applying a response, verify its Story/Asset/Moment still exists
and that the response is relevant to the current state.

Examples:

-   Moment removed while analysis runs
-   Story completed while StoryIdea loads
-   newer scene scan started before old result returns

Use cancellation where practical.

Never overwrite newer local user actions with stale AI output.

## 42. Generated Output Versioning

Do not build complex version control.

A `GeneratedOutput` is immutable historical metadata.

Record which Moment IDs/EditPlan produced it.

Creating again after adding media creates another GeneratedOutput rather
than mutating the previous one.

## 43. Testing

### iOS unit tests

-   Story lifecycle
-   use cases
-   persistence mapping
-   Moment management
-   EditPlan interpretation
-   media-path resolution

### iOS integration tests

-   SwiftData
-   API client
-   rendering
-   Photos/camera behavior where practical

### Backend unit tests

-   each engine with fixed structured inputs

### Contract tests

``` text
backend JSON
→ schema validation
→ Swift decoding
```

### Real-device tests

Required for: - camera - Photos - app lifecycle - persistence -
playback - rendering - memory/performance

Simulator-only success does not satisfy Milestone A.

## 44. Deployment

All cloud resources are deployed to AWS using CDK written in TypeScript.

### API service: AWS App Runner

The Story API runs on **AWS App Runner** — a fully managed container
runtime that is always-on, scales on concurrency, and supports
Server-Sent Events natively. It has no cold starts and requires no VPC,
load balancer, or cluster configuration.

App Runner has a **120-second request timeout**. This is not a
constraint in practice because:

- Interactive operations (scene scan, shot plan, story ideas) complete
  in 5-25 seconds
- `AssetUnderstanding` is computed eagerly when each Moment is added,
  not at Create time; cached results are available instantly at Create
  My Story
- Concurrent Bedrock calls for multiple Moments run in parallel, so
  analysis time is bounded by the slowest single call (~8s), not
  N × 8s
- Any operation that legitimately exceeds 120s belongs in the async
  worker path, not the synchronous request path

### Async worker: AWS Lambda (SQS consumer)

A separate Lambda function consumes an SQS queue for jobs that must not
block the request path. Initially this queue is empty; introduce it only
when measured workload requires it.

Future worker jobs may include: large Edit Plan computation, generative
media, or batch AssetUnderstanding.

If a worker job exceeds Lambda's 15-minute limit or 10GB memory ceiling,
migrate that specific job to an ECS Fargate task. The engine interfaces
remain the same regardless of execution environment.

### Initial MVP topology

``` text
Native iOS App
      │
      ▼
AWS App Runner (Python FastAPI)
      │
      ├── Story / Director / Asset / Music / Edit engines (Python modules)
      ├── Model Gateway ──► Amazon Bedrock / approved AI providers
      ├── Amazon S3 ──────► private temporary media
      ├── DynamoDB ───────► operational/job state when needed
      ├── Secrets Manager
      └── CloudWatch

SQS queue ──► Lambda worker (async jobs when needed)
              └── Fargate task (heavy jobs when Lambda limits are reached)
```

CDK is responsible for provisioning and wiring AWS resources. It is not
responsible for Story product logic.

MVP does not require:

-   Kubernetes/EKS
-   service mesh
-   one service per Story engine
-   event-streaming platform
-   distributed cache
-   multi-region active-active

The default is one logical Python backend deployment boundary on App
Runner. Engine modules remain code boundaries, not infrastructure
boundaries.

See `04-aws-infrastructure.md` for AWS stacks, environments, IAM, S3
lifecycle, deployment flow, and future compute expansion.

## 45. Backend Database

A full cloud Story database is not required for Milestone A because
persistent Story ownership is local-first.

A small backend datastore may later hold:

-   async job state
-   temporary upload metadata
-   operational metadata
-   rate-limiting data
-   anonymous-session support

Do not duplicate the user's full Story library in the backend merely
because a database exists.

If accounts/cloud sync become required, design synchronization
explicitly.

## 46. Performance and Cost Principles

Interactive local UI should feel immediate.

AI work should show clear progress and should not block capture
unnecessarily.

Avoid unnecessary serial model calls.

Cache stable derived state such as AssetUnderstanding.

Measure model operation, latency, usage, and cost.

Avoid re-analyzing unchanged media.

Prefer:

``` text
analyze asset once
→ cache AssetUnderstanding
→ reason over structured result repeatedly
```

over repeatedly resending originals.

### Parallel Bedrock calls (required, not optional)

When multiple independent AI calls can be made concurrently, they
**must** be fanned out in parallel. This is a hard requirement, not an
optimization.

The primary case is AssetUnderstanding at Create My Story time:

``` text
# Wrong — serial, O(N × latency), will timeout at scale
for moment in moments:
    result = await bedrock.analyze(moment)

# Correct — concurrent, O(max single latency), bounded regardless of N
results = await asyncio.gather(*[bedrock.analyze(m) for m in moments])
```

Other cases where parallelism applies:

- Analyzing a batch of imported Existing Media assets
- Running Asset Engine and Music Engine independently before Edit
  planning (no data dependency between them)
- Any set of Bedrock calls where result B does not depend on result A

Do not introduce serial dependencies between independent AI calls.
When a dependency genuinely exists (Edit Engine needs AssetUnderstanding
results), the serial ordering is correct — but verify the dependency is
real before serializing.

## 47. Future Large-Library Path

MVP does not solve thousands-of-assets processing, but current
boundaries preserve the path:

``` text
local media library
→ Asset Engine
→ progressive/local indexing
→ AssetUnderstanding
→ embeddings / clusters / dedupe
→ Story Engine
→ story discovery / creation
```

Do not build this now.

## 48. Future Generative Media Path

Future generated supporting media should use a separate abstraction:

``` text
Story/Edit Engine
→ GenerativeMediaRequest
→ generation provider
→ Generated Asset
→ Asset
```

Generated media must remain distinguishable from captured real-world
media.

Do not couple a generation provider directly into iOS or Director
Engine.

## 49. Architecture Decision Table

  Area                         MVP Decision
  ---------------------------- ------------------------------------
  Client                       Native iOS
  UI                           SwiftUI
  Camera                       AVFoundation
  Photo library                PhotoKit / PhotosPicker
  Local persistence            SwiftData
  Original media               Device/local-first
  Final rendering              On-device
  Rendering                    AVFoundation
  Backend                      Single modular application
  Backend language             Python
  Runtime                      AWS App Runner (container)
  HTTP framework               FastAPI
  API                          HTTPS + JSON
  API version                  `/v1`
  Contract source              JSON Schema + OpenAPI
  AI access                    Backend only
  AI abstraction               Model Gateway
  Direct iOS AI calls          No
  Persistent Story authority   Device for MVP
  Cloud Story sync             Deferred
  Required account             No
  Identity                     Anonymous local identity
  Scene media                  Sampled/resized/proxy
  Permanent original upload    No
  Temporary media              Private + expiring
  Story Engine                 Backend module
  Director Engine              Backend module
  Asset Engine                 Backend module
  Music Engine                 Backend module
  Edit Engine                  Backend module
  Media Engine                 On-device
  Microservices                No
  Queue                        Only after measured need
  Figma HTML                   `prototypes/figma`, reference only
  Large-library indexing       Deferred
  Generative video             Deferred
  Full editor                  Deferred

## 50. Explicit Non-Goals

MVP architecture does not include:

-   production microservices
-   cloud photo-library replacement
-   permanent upload of all originals
-   sophisticated cross-device sync
-   web or Android client
-   full timeline editor
-   multi-user collaboration
-   social graph
-   public publishing backend
-   third-party streaming music integration
-   advanced distributed queues
-   proprietary model hosting
-   3D scene reconstruction
-   AR capture overlays
-   large-scale vector search
-   full camera-roll indexing
-   generative-video pipeline
-   mandatory authentication

## 51. Architecture Review Triggers

Revisit this architecture if:

1.  on-device rendering cannot support required output quality
2.  cross-device synchronization becomes core
3.  accounts become necessary for product value
4.  asset analysis requires persistent cloud indexing
5.  long-running jobs require a real queue/worker system
6.  backend modules require independent scaling
7.  generative video becomes core
8.  Android/web becomes an active target
9.  privacy requirements move more intelligence on-device
10. real usage proves device-authoritative Story state insufficient

Do not pre-build these solutions.

## 52. Milestone A Architecture

Milestone A uses the real architecture with mock intelligence.

### Real

-   SwiftUI screens
-   navigation
-   SwiftData
-   Story lifecycle
-   camera
-   Photos picker
-   local media
-   Moment persistence
-   playback
-   local identity
-   API boundary
-   engine interfaces
-   output plumbing

### Mock

-   CreativeIntent intelligence
-   StoryBlueprint intelligence
-   Story Guide
-   Story Idea
-   SceneUnderstanding
-   Director
-   validation
-   AssetUnderstanding
-   music recommendation
-   EditPlan

First vertical slice:

``` text
Launch
→ Home
→ Start a Story
→ Creative Direction
→ persist Story
→ Story Home
→ Shoot a Moment
→ Mock Director
→ real camera
→ real local clip
→ persist Moment
→ Create My Story
→ mock result
→ persist GeneratedOutput metadata
→ kill app
→ relaunch
→ Story and media still exist
```

## 53. Architecture Completion Check

Kiro should be able to answer these without inventing new boundaries:

``` text
Where does a Story live?
→ On-device for MVP.

Where does original media live?
→ On-device.

Who owns Story Guide?
→ Story Engine.

Who owns scene-specific direction?
→ Director Engine.

Who understands media?
→ Asset Engine.

Who recommends/analyzes music?
→ Music Engine.

Who creates the edit?
→ Edit Engine produces EditPlan.

Who renders it?
→ On-device Media Engine.

Can iOS call AI providers?
→ No.

Does Story require an account?
→ No.

Does creating a video complete a Story?
→ No.

Does backend permanently store every original?
→ No.

Can a Story have multiple outputs?
→ Yes.

Is Figma HTML production code?
→ No.

Are Story Engine and Director Engine microservices?
→ No; they are backend modules.
```

## 54. Final Architecture

``` text
                    STORY iOS
          ┌────────────────────────┐
          │ UX                     │
          │ Local Story state      │
          │ Camera / Photos        │
          │ Original media         │
          │ On-device rendering    │
          └───────────┬────────────┘
                      │ structured API / SSE
                      ▼
            AWS CLOUD / STORY BACKEND
          ┌────────────────────────┐
          │ AWS App Runner         │
          │ Python / FastAPI       │
          │ Story Engine           │
          │ Director Engine        │
          │ Asset Engine           │
          │ Music Engine           │
          │ Edit Engine            │
          │ Model Gateway          │
          └───────────┬────────────┘
                      │
                      ▼
                   AI MODELS
                (Bedrock / external)

          SQS ──► Lambda / Fargate worker
                  (async jobs when needed)
```

> **Cloud thinks. Device owns the media. AI produces structured
> decisions. Deterministic systems execute them.**

This architecture supports Story's product goal: **help users plan,
guide, manage, and create visual stories while requiring as little
filmmaking, media management, and editing work from the user as
possible.**

## 55. Language and Deployment Boundary Summary

The chosen language split is intentional:

``` text
Consumer experience        Swift / SwiftUI
Backend + AI intelligence  Python
Infrastructure             TypeScript / AWS CDK
Contracts                  JSON Schema + OpenAPI
```

This is consistent with the original architecture's separation of
concerns. The original design already kept the native iOS client
separate from the backend and treated infrastructure as an
implementation detail. The revision changes the backend implementation
language from TypeScript to Python and makes AWS/CDK explicit; it does
not change Story's domain boundaries, local-first media model, engine
responsibilities, structured contracts, or on-device rendering strategy.

The rule is:

> Use the language that best fits each responsibility; use contracts to
> connect them.
