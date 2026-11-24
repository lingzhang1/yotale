# Story --- Product & MVP Specification

**Working name:** Story\
**Status:** Frozen MVP product definition\
**Product goal:** Help users **plan, guide, manage, and create visual
stories** from real experiences and media without requiring filmmaking
or editing expertise.

------------------------------------------------------------------------

# 1. Product Vision

Story is an AI Story Director.

A user should be able to tell Story what they want to make, collect
material naturally over seconds, hours, or days, receive direction when
it is useful, and create a finished visual story from what they actually
captured.

The long-term product promise is:

> **Tell Story what you want to make. Story helps you plan it, capture
> it, manage it, and create it.**

Story should reduce the creative and operational burden normally placed
on the user:

-   deciding what is worth capturing
-   translating a vague vibe into a visual plan
-   knowing how to shoot a useful moment
-   remembering what has already been captured
-   recognizing what may still improve the story
-   organizing photos and videos into meaningful Moments
-   selecting usable material
-   choosing music and pacing
-   assembling the final video

The user owns the experience and creative intent. Story owns as much of
the creative production problem as possible.

The objective is not to maximize capture. It is to obtain and use the
**minimum useful material needed to create a satisfying story**.

------------------------------------------------------------------------

# 2. Product Model

Story has three connected user entry points:

``` text
HOME
├── Create Now
├── Start a Story
└── Use Existing Photos / Videos
```

These are different ways to enter one Story system.

## Create Now

For a short, immediate creation.

Typical intent:

> "I'm here now. Help me make something good."

Story can understand the desired style, inspect the current scene when
useful, recommend a strong concept, direct a small number of shots, and
create a short video.

## Start a Story

For an experience that unfolds over time.

Typical intent:

> "I'm starting something. Remember what I want to make, help me collect
> useful moments, and create from them whenever I want."

A persistent Story can represent:

-   a trip
-   a hike
-   a birthday
-   a wedding
-   a city visit
-   a family event
-   a day out
-   any experience that may accumulate media over time

## Use Existing Photos / Videos

For material the user already has.

Typical intent:

> "I already captured things. Help me turn them into a story."

Existing media is first-class input, not a fallback.

------------------------------------------------------------------------

# 3. The Core Story Loop

The core product loop is:

``` text
CREATIVE INTENT
      ↓
STORY UNDERSTANDING / BLUEPRINT
      ↓
CAPTURE OR COLLECT MOMENTS
      ↓
STORY STATE EVOLVES
      ↓
GUIDE / DIRECT ONLY WHEN USEFUL
      ↓
CREATE AT ANY TIME
      ↓
EDIT PLAN + MUSIC
      ↓
GENERATED OUTPUT
```

For persistent Stories, this loop can repeat.

A Story may have zero, one, or many generated outputs.

Creating an output does not complete the Story.

------------------------------------------------------------------------

# 4. Creative Direction

Story begins by understanding what the user wants.

The user may communicate intent through any combination of:

-   a Story template or visual example
-   reference photo/video
-   natural-language description
-   lightweight context
-   desired duration
-   desired vibe
-   music feeling

The user should not need filmmaking vocabulary.

Examples:

> "I want a cinematic 10-second video here. Mostly the environment, but
> include me."

> "We're hiking TMB. I want an emotional film that shows the scale of
> the mountains and the feeling of the journey."

All inputs normalize into a structured `CreativeIntent`.

Story should reason from that structured intent rather than repeatedly
reasoning from raw user prompts.

------------------------------------------------------------------------

# 5. Story Blueprint and Story Guide

For a persistent Story, Story creates a lightweight `StoryBlueprint`.

The blueprint represents useful narrative ingredients, not mandatory
tasks.

For a hiking story, examples might include:

-   opening
-   movement / journey
-   scale
-   human moments
-   effort or challenge
-   climax
-   ending

The blueprint powers **Story Guide**.

Story Guide answers:

> **What kinds of material could help me tell this Story well?**

Story Guide is available before and during the experience, even when
Story does not know the exact future locations.

It must not become:

-   an itinerary
-   a day-by-day schedule
-   a production task manager
-   a required checklist
-   a completion percentage
-   a list the user must satisfy before creating

The user can ignore the guide and create at any time.

------------------------------------------------------------------------

# 6. Moments

`Moment` is the primary user-facing media unit inside a persistent
Story.

A Moment may come from:

-   Story-directed capture
-   spontaneous capture
-   existing phone media
-   camera-imported photos/videos

Adding existing media to a Story adds it to **Moments**.

It does not immediately start generation.

The user can:

-   add
-   browse
-   preview
-   remove

Moments are the material Story considers when reasoning about the Story
and creating outputs.

Not every Moment needs to appear in the final output.

------------------------------------------------------------------------

# 7. Story Idea and Show Me

Story can recommend a high-level `Story Idea` based on:

-   CreativeIntent
-   StoryBlueprint
-   existing Moments
-   current StoryState

A Story Idea does not require Story to know the current physical scene.

Example:

> "You already have strong landscape footage. A quiet moment with both
> of you could add warmth."

If the user selects **Show Me**, Story can then inspect the current
scene and translate the general idea into a concrete capture.

``` text
Story Idea
    ↓
Show Me
    ↓
Optional scene scan
    ↓
Scene Understanding
    ↓
Scene-specific concept
    ↓
1–3 shot plan
    ↓
Guided capture
    ↓
Moment saved to Story
```

This separates long-horizon story reasoning from immediate
scene-specific directing.

------------------------------------------------------------------------

# 8. Shoot a Moment

`Shoot a Moment` is the direct capture entry point inside a persistent
Story.

It reuses the same directing primitive as Create Now.

Story may:

1.  understand the user's Story context
2.  inspect the current scene if needed
3.  recommend one strong idea
4.  show an example or preview
5.  guide a very small number of shots
6.  validate whether the captured material is usable
7.  save successful captures as Moments

Story should not require active direction for every capture.

The normal phone camera and existing-media import remain valid ways to
contribute Moments.

------------------------------------------------------------------------

# 9. Create Now

Create Now is optimized for a short immediate result.

``` text
Create Now
→ template / reference / description
→ CreativeIntent
→ optional scene scan
→ one recommended concept
→ preview / example
→ 1–3 guided shots
→ simple usability validation
→ optional additional existing media
→ music
→ EditPlan
→ generated video
```

Principles:

-   scene scan is contextual, not mandatory
-   recommend one strong default concept
-   alternatives are secondary
-   guidance is one instruction at a time
-   minimize retakes
-   minimize capture effort
-   do not expose a timeline editor
-   use existing media when it helps

------------------------------------------------------------------------

# 10. Use Existing Photos / Videos

Existing-media creation uses the same creative system but skips directed
capture when it is unnecessary.

``` text
CreativeIntent
      +
Selected media
      ↓
Asset Understanding
      ↓
Story determines what is achievable
      ↓
EditPlan
      ↓
Music-aware assembly
      ↓
GeneratedOutput
```

For MVP, this path handles a small number of selected assets.

Large-library indexing and thousands-of-photo workflows are future work.

------------------------------------------------------------------------

# 11. Scene Understanding

Scene scanning is a capability, not a required step.

Story asks to see the scene only when visual context materially improves
its recommendation.

For example:

``` text
3–5 second scan
      ↓
sample representative frames
      ↓
Vision model
      ↓
SceneUnderstanding
```

SceneUnderstanding may include:

-   environment
-   subjects
-   lighting
-   movement opportunities
-   composition opportunities
-   physical constraints

The MVP does not require full 3D reconstruction or AR mapping.

------------------------------------------------------------------------

# 12. Capture Guidance

Capture guidance must be simple enough for a normal user to follow while
holding a phone.

Good guidance:

> Walk toward the signs.

> Follow her from behind.

> Hold steady.

> 3... 2... 1... go.

Principles:

1.  one instruction at a time
2.  qualitative language
3.  no filmmaking terminology unless requested
4.  minimal repositioning
5.  minimal retakes
6.  only request material that meaningfully improves the result
7.  physical feasibility over ambitious cinematography

Validation asks:

> **Did we get a usable version of what Story requested?**

It does not score artistic quality.

------------------------------------------------------------------------

# 13. Story State

A persistent Story maintains lightweight state describing what Story
currently understands.

Conceptually:

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

`StoryState` can track lightweight narrative coverage and accumulated
material.

It should help Story decide:

-   what is already represented
-   what could improve the Story
-   whether direction would be useful
-   what can be created from current material

MVP should not expose sophisticated coverage scoring or a complex Story
Graph.

------------------------------------------------------------------------

# 14. Story Reconciliation

The initial Story Blueprint is provisional.

Reality may produce better material than the original plan.

Story should reconcile:

``` text
CREATIVE INTENT
      +
PROVISIONAL BLUEPRINT
      +
WHAT ACTUALLY HAPPENED
      +
MOMENTS
      ↓
CURRENT BEST STORY
```

Unexpected weather, funny interactions, fatigue, a beautiful accidental
shot, or a change of plan may become more important than the original
concept.

Story should adapt to reality rather than force reality into a rigid
storyboard.

------------------------------------------------------------------------

# 15. Music

Music is part of storytelling, not an afterthought.

At Story setup, Story can infer a lightweight `MusicDirection` from
Creative Direction.

Examples:

-   cinematic
-   emotional
-   epic
-   dreamy
-   energetic
-   chill
-   playful

Exact song selection is not required during Story creation.

At **Create My Story**, Story recommends a specific track from a small
MVP catalog and allows the user to preview or choose among a few
alternatives.

Music must feed the edit:

``` text
CreativeIntent
+
Moments
+
MusicAsset / MusicAnalysis
      ↓
EditPlan
```

Changing music may change:

-   selected clips
-   clip duration
-   pacing
-   cut points
-   overall structure

For MVP, use a small licensing-safe catalog.

Do not build a general music-browser product or third-party streaming
catalog integrations.

------------------------------------------------------------------------

# 16. Editing and Generated Outputs

Story's AI should decide **what the edit should be**.

A deterministic media engine should execute it.

``` text
CreativeIntent
+
StoryState
+
Moments / AssetUnderstanding
+
Music
      ↓
Story reconciliation
      ↓
EditPlan
      ↓
Deterministic Media Engine
      ↓
GeneratedOutput
```

Initial deterministic operations:

-   clip selection
-   trimming
-   crop/reframe
-   speed changes
-   simple transitions
-   music
-   basic beat alignment
-   basic color treatment
-   export

Do not ask an LLM to directly "edit video."

The AI produces structured decisions. The media engine executes them.

A Story may produce multiple outputs over time.

------------------------------------------------------------------------

# 17. Create My Story

`Create My Story` is always available inside a persistent Story.

The user does not need to complete Story Guide suggestions first.

Before creation, show the Moments currently available so the user
understands what Story can consider.

Story may use only a subset.

Creating an output:

-   does not close the Story
-   does not mark it completed
-   does not prevent more Moments from being added
-   does not replace previous outputs

This enables:

``` text
TMB
├── early-trip output
├── mid-trip output
├── final-trip output
└── alternate-music output
```

------------------------------------------------------------------------

# 18. Active and Completed Stories

`Create My Story` and `Complete Story` are independent actions.

``` text
Create My Story
= generate an output

Complete Story
= stop treating this as an active experience
```

Story status:

``` text
active | completed
```

Home organization:

``` text
HOME

CONTINUE
- active Stories

YOUR STORIES
- completed Stories
```

Completing a Story primarily changes organization.

It does not:

-   generate an output
-   delete Moments
-   delete Story Guide
-   remove generated outputs
-   make the Story immutable

A completed Story can still create outputs.

`Reopen Story` restores it to active status.

While completed, proactive capture suggestions should be hidden.

------------------------------------------------------------------------

# 19. Local-First Media and Account Strategy

MVP does not require registration.

Use a local anonymous identity and local-first Story persistence.

Original user media should normally remain on-device.

``` text
Original media on device
      ├── local reference
      ├── thumbnail / proxy
      └── derived AI input when needed
```

When cloud AI needs visual information, upload only what is necessary
where practical:

-   resized image
-   representative frames
-   short proxy
-   metadata
-   embeddings

The backend should not become a duplicate photo library.

Future authenticated accounts should be able to adopt local Stories
without changing Story identity.

------------------------------------------------------------------------

# 20. Core Domain Model

The canonical domain objects are defined in `02-core-story-schema.md`.

The important relationships are:

``` text
Story
├── CreativeIntent
├── MusicDirection
├── StoryBlueprint
├── StoryState
├── Moments[]
│   └── Asset
│       └── AssetUnderstanding
├── CaptureSessions[]
│   ├── SceneUnderstanding
│   ├── StoryConcept
│   ├── StoryPlan
│   └── Captures[]
└── GeneratedOutputs[]
    └── EditPlan
```

Important invariants:

-   Story is not GeneratedOutput.
-   A Story can have zero or many outputs.
-   Creating an output does not complete a Story.
-   Completing a Story does not create an output.
-   A completed Story can be reopened.
-   Not every Moment appears in an output.
-   An Asset can exist without being a Moment.
-   scene-specific direction uses SceneUnderstanding.
-   Story-level guidance does not require knowing the current scene.
-   original media does not require permanent cloud upload.

------------------------------------------------------------------------

# 21. Product Architecture Principles

Story should not be one giant AI agent.

The system should be an orchestration layer around structured state and
replaceable engines.

Logical responsibilities:

``` text
iOS Client
├── UX
├── camera
├── Photos integration
├── local Story persistence
├── local media references
└── playback

Story API
├── orchestration
├── request validation
├── AI/model access
└── async job coordination

Story Engine
├── StoryBlueprint
├── StoryState
├── Story Guide
├── Story Ideas
└── long-horizon reasoning

Director Engine
├── scene-specific concepts
├── shot plans
└── capture guidance

Asset Engine
├── media understanding
├── usable segments
└── quality/semantic metadata

Music Engine
├── track recommendation
└── beat/section analysis

Edit Engine
└── structured EditPlan

Media Engine
└── deterministic rendering

Model Gateway
└── provider-independent AI access
```

These are logical package boundaries. MVP does not require separate
microservices.

------------------------------------------------------------------------

# 22. MVP Scope

The MVP validates three connected experiences:

## A. Create Now

-   template/reference/text intent
-   optional scene scan
-   one concept
-   1--3 guided shots
-   simple validation
-   music-aware short edit
-   generated result

## B. Start a Story

-   create persistent Story
-   Creative Direction
-   Story Home
-   Moments
-   Story Guide
-   Story Idea / Show Me
-   Shoot a Moment
-   add existing media to Moments
-   Create My Story at any time
-   multiple outputs
-   Complete Story / Reopen Story

## C. Use Existing Photos / Videos

-   select a small number of existing assets
-   describe or choose desired style
-   basic AssetUnderstanding
-   automatic EditPlan
-   music-aware output

------------------------------------------------------------------------

# 23. Explicitly Postponed

Do not build for the first MVP:

-   thousands-of-photo ingestion
-   full camera-roll indexing
-   automatic deduplication
-   sophisticated photo management
-   production-grade cloud sync
-   mandatory user accounts
-   social network
-   collaboration
-   publishing/distribution platform
-   full timeline editor
-   professional editing controls
-   proactive background notifications
-   itinerary/calendar integration
-   sophisticated multi-day coverage scoring
-   AR shot overlays
-   LiDAR/3D scene reconstruction
-   proprietary generative video
-   mandatory AI-generated previews
-   deep personalization
-   Spotify/Apple Music/TikTok/Instagram catalog integrations

------------------------------------------------------------------------

# 24. Product Risks

## Friction

Story must create enough value to justify being slower than opening
Camera.

## Generic direction

Recommendations must be specific to the scene, intent, and existing
Story material.

## Over-planning

Story must not turn an experience into production work.

Often the correct recommendation is no recommendation.

## Physical feasibility

Scene-specific instructions must be safe, simple, and realistically
executable.

## AI latency

Creative reasoning can take a few seconds. Capture interaction cannot
feel blocked by repeated slow model calls.

## Story quality

There is no reliable automatic metric for "good Story." Human preference
evaluation is required.

## Editing quality

Even strong direction fails if automatic editing, music, and pacing feel
generic.

------------------------------------------------------------------------

# 25. MVP Validation

The MVP is not successful merely because it can generate a video.

We need to learn whether users feel that Story:

-   helped them think of something they would not have captured
    themselves
-   reduced creative decision-making
-   made capturing easier rather than more burdensome
-   helped them manage an experience across multiple Moments
-   produced an output they prefer to their normal process
-   made them want to use Story again

Key qualitative questions:

> "Would you have thought to shoot it this way?"

> "Did Story make this easier?"

> "Did Story interrupt the experience too much?"

> "Did Story understand what you were trying to make?"

> "Would you use this on your next trip/event/day out?"

------------------------------------------------------------------------

# 26. North-Star Example --- TMB

Before the trip:

``` text
Start a Story
→ "Tour du Mont Blanc"
→ choose / describe cinematic emotional travel style
→ Story creates CreativeIntent + lightweight Story Guide
```

The user can inspect the guide before leaving and understand useful
kinds of material to look for.

During the trip:

``` text
User takes normal photos/videos
→ adds selected material to Moments

Interesting viewpoint
→ Shoot a Moment
→ Story optionally sees current scene
→ one scene-specific idea
→ guided capture
→ saved as Moment
```

Story may also surface a high-level idea:

> "You have beautiful landscapes. A human moment could make the Story
> feel more personal."

The user can choose **Show Me** when they want help.

At any point:

``` text
Create My Story
→ inspect current Moments
→ choose/review music
→ Story creates best achievable edit
→ GeneratedOutput
```

The Story remains active.

After the trip:

``` text
Complete Story
→ moves from Continue to Your Stories
```

The user can still reopen it or create another output later.

------------------------------------------------------------------------

# 27. Product Principles

1.  **Plan lightly.** Give users useful creative direction without
    turning experiences into productions.
2.  **Capture naturally.** Existing and spontaneous media are
    first-class.
3.  **Direct only when useful.** Scene-specific guidance should earn its
    friction.
4.  **Reuse before requesting more.** Do not ask for footage Story
    already has.
5.  **Reality can change the Story.** The blueprint evolves with actual
    Moments.
6.  **Minimize user decisions.** Story should remove creative work, not
    create menus.
7.  **Show rather than explain.** Visual examples beat filmmaking
    terminology.
8.  **Capture reality; generate cinematography.** Personal stories
    should preserve authenticity.
9.  **Story owns the outcome.** The user should not need to become an
    editor.
10. **No direction can be the right direction.** Do not interrupt
    unnecessarily.
11. **Create whenever useful.** Generation is not a final-stage gate.
12. **Completion is organization, not creation.**
13. **Music shapes the edit.**
14. **Earn the account.** Registration is not required before MVP value
    is proven.
15. **Structured state over giant agents.** AI models are replaceable
    implementation components.
16. **Local-first media.** Story should not require uploading an entire
    personal library.

------------------------------------------------------------------------

# 28. Final Product Definition

> **Story is an AI Story Director that helps users plan, guide, manage,
> and create visual stories. It understands what the user wants, helps
> them recognize or capture useful Moments, remembers what has been
> collected across an experience, and turns the available real-world
> material into a finished story whenever the user is ready.**

For the MVP, the product must prove that this combination of **creative
planning + selective direction + persistent Story management + automatic
creation** provides meaningful value beyond a normal camera, photo
library, or automatic video editor.
