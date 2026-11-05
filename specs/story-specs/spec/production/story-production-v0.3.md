# Story — Product & MVP Specification

**Working name:** Story  
**Status:** Product definition / MVP planning  
**Core concept:** AI Story Director

---

# 1. Product Vision

Story is an AI creative director that helps users turn an idea, experience, location, or collection of media into a finished visual story.

The user should not need to understand:

- cinematography
- posing
- shot planning
- camera movement
- editing
- transitions
- storytelling structure

Instead, the user communicates **what they want the final result to feel like**.

Story determines the easiest way to get there.

The long-term product promise is:

> **Tell Story what you want to create. Capture naturally. Story figures out the rest.**

Story may:

- use content the user already captured
- suggest something worth capturing
- actively direct a specific shot
- determine that no additional footage is needed
- eventually generate or transform missing material
- assemble everything into the final story

The goal is NOT to maximize how much content users capture.

The goal is:

> **Acquire the minimum useful material necessary to create the desired story.**

---

# 2. Core Product Principle

The original product flow was:

```text
User describes desired result
        ↓
Scan scene
        ↓
Story proposes 3 concepts
        ↓
User selects concept
        ↓
Story creates shot list
        ↓
User follows instructions
        ↓
Story edits footage
        ↓
Finished video
```

This is too rigid.

It assumes:

1. the scene is known before capture
2. the user wants active direction
3. Story knows the final story before seeing reality
4. the user is willing to make multiple creative decisions before shooting
5. all useful footage will be intentionally directed

Real consumer behavior is much less structured.

The new product model is:

```text
                 CREATIVE INTENT
                       │
                       ▼
                STORY BLUEPRINT
                       │
                       ▼
                  STORY STATE
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       DIRECT        ASSIST        EDIT
          │            │            │
          ▼            ▼            ▼
       Guided       Natural       Existing
       capture       capture       media
          │            │            │
          └────────────┼────────────┘
                       │
                       ▼
                CAPTURED ASSETS
                       │
                       ▼
             STORY RECONCILIATION
                       │
                       ▼
                   EDIT PLAN
                       │
                       ▼
                 FINISHED STORY
```

Story maintains an **evolving model of the desired story** rather than enforcing a fixed storyboard.

---

# 3. Product Thesis

Traditional content creation generally works like:

```text
Idea
 ↓
Plan shots
 ↓
Capture everything
 ↓
Review footage
 ↓
Select footage
 ↓
Edit
 ↓
Finished content
```

This requires the user to act as:

- director
- cinematographer
- photographer
- content manager
- editor

Story changes this relationship.

```text
User Intent
     ↓
Story understands desired outcome
     ↓
User captures naturally
     ↕
Story helps only when useful
     ↓
Story understands what actually happened
     ↓
Story builds the best achievable story
     ↓
Finished content
```

The user owns the **intent and experience**.

Story owns the **creative production problem**.

---

# 4. Creative Intent

The first step is not "scan the scene."

The first step is:

> **What do you want to create?**

Users should be able to express this through any combination of four input types.

## 4.1 Templates

Story provides visual examples of common creative directions.

Examples:

- Cinematic
- Energetic
- Fashion
- Romantic
- Calm / aesthetic
- Adventure
- Funny / playful
- Main character
- Landscape-focused
- Social-native / trending

Templates should primarily be communicated visually rather than through filmmaking terminology.

---

## 4.2 Reference Content

The user can provide:

- Instagram Reel
- TikTok-like short video
- video file
- photo
- previous Story
- other visual reference

The user is effectively saying:

> "I want something that feels like this."

Story should NOT simply copy the content.

It should extract transferable creative characteristics such as:

```text
Story structure
Camera movement
Shot duration
Subject movement
Framing
Pacing
Transitions
Editing rhythm
Visual mood
Relationship between subject and environment
```

Example:

```text
REFERENCE

Tokyo at night
Woman walking
Neon signs
Fast cinematic Reel

          ↓

EXTRACT CREATIVE GRAMMAR

follow subject
      ↓
foreground transition
      ↓
environment reveal

          ↓

TRANSFER TO USER CONTEXT

Times Square
Different person
Different environment
Same storytelling grammar
```

---

## 4.3 Natural Language

Example:

> "I want a cinematic 10-second video here. Mostly the environment, but include me. I don't want it to look touristy."

Or:

> "We're hiking TMB for eight days. I want a ~60-second emotional film that shows the scale of the mountains and feeling of the journey. Include us occasionally but don't make it influencer-like."

The user should not need filmmaking vocabulary.

---

## 4.4 Context

Story can optionally receive context such as:

- Times Square at night
- birthday dinner
- hiking TMB
- coffee shop
- proposal
- beach sunset
- family event
- fashion shoot
- road trip

Context can also include:

- desired duration
- number of people
- who is filming
- tripod availability
- expected length of event
- location type

---

# 5. Creative Intent Model

All inputs should eventually normalize into an internal representation:

```text
CreativeIntent

goal
duration
mood
energy
visual_style
story_preferences
subject_importance
environment_importance
reference_assets
context
constraints
capture_preference
```

The rest of the system should operate on this representation rather than directly on raw prompts.

---

# 6. Story Blueprint

Story should NOT immediately create a rigid shot list.

Instead, it creates a lightweight **Story Blueprint**.

The blueprint represents what would make the desired story successful.

Example:

## TMB

```text
Desired output:
60-second cinematic hiking film

Story Blueprint

OPENING
- anticipation
- beginning journey

JOURNEY
- movement
- changing environments
- human presence

SCALE
- people vs mountains
- wide landscapes

EFFORT
- climbing
- weather
- fatigue

HUMAN MOMENTS
- candid interaction
- food / hut / rest

CLIMAX
- strongest landscape / achievement

ENDING
- reflection
- completion
```

These are **story needs**, not exact shots.

Story does not yet know how each requirement will be fulfilled.

---

# 7. Story State

Story maintains persistent state describing the evolving project.

Conceptually:

```text
StoryState

CreativeIntent

StoryBlueprint

StoryNeeds

CapturedAssets

AssetUnderstanding

Coverage

SuggestedCaptures

ChosenCreativeDirection

EditCandidates

EditPlan
```

Example during TMB:

```text
STORY COVERAGE

Opening             ✓
Journey             ✓✓
Landscape           ✓✓✓✓
Human presence      ✓
Effort              ✗
Candid interaction  ✗
Climax              ?
Ending               ✗
```

This state changes as Story sees more material.

---

# 8. Three Creation Modes

Story supports three user-facing situations built on the same underlying Story engine:

- **Create Now** — make something in the current context; invokes DIRECT.
- **Start a Story** — create a persistent Story that evolves over time and invokes DIRECT only when useful.
- **Use Existing Media** — make something primarily from assets already captured.

DIRECT and EDIT remain internal capabilities. The previous ASSIST concept is now modeled as a persistent **Story** / `StoryPlan`, not a separate user-facing mode.

---

# 8.1 DIRECT Mode

### User intent

> "Tell me what to shoot."

Best for:

- Times Square
- fashion
- landmark
- restaurant
- controlled environment
- intentional social content
- short 5–15 second videos

Example:

```text
Creative Intent
      ↓
Optional scene scan
      ↓
Story recommends ONE concept
      ↓
2 shots required
      ↓
Story directs capture
      ↓
Validate footage
      ↓
Assemble
      ↓
Finished Story
```

### Important UX principle

Story should recommend **one strong default concept**.

Do NOT require the user to evaluate three concepts unless they explicitly want alternatives.

Example:

> **I have an idea.**

**NYC Main Character**

8 seconds · 2 shots · ~15 seconds to capture

[Preview]

**Let's shoot**

Secondary options:

- Try another idea
- Change style

This reduces decision fatigue.

---

# 8.2 Start a Story (Persistent StoryPlan)

### User intent

> "I'm starting something that unfolds over time. Remember what I want to make, what I capture, and help only when useful."

Best for:

- travel
- hiking
- vacations
- events
- birthdays
- weddings
- long experiences
- unpredictable environments

Story does NOT constantly interrupt the user.

Instead:

```text
Story Blueprint
       ↓
User captures naturally
       ↓
Story understands new footage
       ↓
Coverage updates
       ↓
Is something important missing?
       │
     No│      Yes
       │       │
       ▼       ▼
   Do nothing  Suggest capture
```

Example during TMB:

> **Story suggestion**

> You already have plenty of landscape footage, but almost nothing showing both of you together.

> At the next viewpoint, I can show you a simple 6-second shot.

Options:

**Show me**

**Not now**

Another example:

> This scene could work beautifully as the climax of your Story.

> Want a shot suggestion?

The default behavior should often be:

> **Do nothing. Let the user enjoy the experience.**

---

# 8.3 EDIT Mode

### User intent

> "I already have footage. Make something."

Best for:

- existing camera roll
- camera imports
- random clips
- previous trips
- spontaneous capture
- users who do not want direction

Flow:

```text
Creative Intent
      ↓
Existing media
      ↓
Story understands assets
      ↓
Story identifies achievable narratives
      ↓
Story chooses/recommends strongest direction
      ↓
Edit Plan
      ↓
Finished Story
```

Story should discover the best story that can be made from **what actually exists**.

---

# 9. Modes Are Not Separate Products

DIRECT, ASSIST, and EDIT are different interactions with the same Story state.

A user can move between them.

Example:

```text
TMB Trip

Before trip
    ↓
START A STORY
Create persistent Story + Story Blueprint

During trip
    ↓
Natural capture

Special viewpoint
    ↓
DIRECT
"Show me a shot here"

Continue trip
    ↓
Persistent Story

After trip
    ↓
EDIT
Use everything captured

    ↓
Finished Story
```

This flexibility is a core product advantage.

---

# 10. Scene Scan

Scene scanning is a **capability**, not a mandatory onboarding step.

Story should request a scene scan only when seeing the current environment materially improves its recommendation.

Example:

## Times Square

```text
"I want an energetic 8-sec video like this Reel."

        ↓

Story:
"Show me where you are."

        ↓

3–5 second scan

        ↓

Scene understanding:
- giant displays
- moving crowd
- strong night lighting
- open pedestrian area
- one subject
- strong depth

        ↓

Story creates scene-specific direction
```

For TMB before the trip, scene scanning makes no sense.

Therefore:

> **Scene understanding is contextual and optional.**

---

# 11. Capture-First Workflow

Users should also be able to capture before choosing an exact concept.

Example:

Times Square.

User selects:

> Energetic · ~10 sec

Then simply records:

```text
crowd
wife walking
billboard
taxi
random pan
close-up
```

Story analyzes the actual footage.

It may then say:

> **I found two good ways to tell this Story.**

### Main Character

Uses:

- walking
- crowd
- billboard

### NYC Energy

Uses:

- taxi
- crowd
- billboard
- pan

Concept selection now happens **after Story knows what is achievable**.

This can be better than asking the user to commit to a hypothetical concept before capturing anything.

---

# 12. When Should Story Choose the Concept?

There is no single correct stage.

The decision depends on the creation context.

| Scenario | Concept timing |
|---|---|
| Controlled short-form shoot | Before capture |
| Strong reference video | Mostly before capture |
| User asks for active direction | Before capture |
| Casual spontaneous capture | After some capture |
| Existing footage | After capture |
| Long event/trip | Blueprint before, final concept evolves |
| Fashion / intentional production | Before capture |

Story should dynamically choose the appropriate workflow.

---

# 13. Capture Guidance

When active guidance is useful, it should be extremely simple.

Bad:

> Move 2.3 meters left, rotate the camera 12 degrees, place the subject at the right third, lower the camera 20 cm...

Good:

> Walk toward the signs.

Then:

> Follow her from behind.

Then:

> Hold steady.

Then:

> 3... 2... 1... go.

Guidance principles:

1. One instruction at a time.
2. Prefer qualitative guidance.
3. Avoid cinematography terminology.
4. Minimize repositioning.
5. Minimize retakes.
6. Ask for only footage that contributes to the story.

---

# 14. Existing / Random Footage Is First-Class

Story must never assume all assets were captured through Story.

Real usage will look like:

```text
Directed shot
Random phone clip
Camera photo
Spontaneous video
Existing asset
Directed shot
AI-enhanced asset
```

Story should treat all of them as potential Story assets.

For every Story need:

```text
Does existing material satisfy it?

        │
   ┌────┴────┐
   │         │
  YES        NO
   │         │
   ▼         ▼
Use it    Is capture worthwhile?
               │
          ┌────┴────┐
          │         │
         YES        NO
          │         │
          ▼         ▼
       Suggest    Skip / eventually
       capture       generate
```

---

# 15. Story Reconciliation

This is a key concept.

The initial Story Blueprint is provisional.

Reality may be more interesting than the original plan.

Example:

Initial TMB intent:

> peaceful cinematic mountain journey

Reality:

- rainstorm
- exhaustion
- missed transportation
- funny restaurant moment
- dramatic sunset
- unexpected interaction

Story should not force these assets into the original storyboard.

Instead:

```text
INITIAL INTENT
      │
      ▼
PROVISIONAL BLUEPRINT
      │
      ▼
REALITY / CAPTURED ASSETS
      │
      ▼
STORY RECONCILIATION
      │
      ├── preserve original intent
      ├── discover unexpected moments
      ├── identify stronger narrative
      └── update story structure
      │
      ▼
FINAL STORY
```

The story should evolve with reality.

---

# 16. Capture vs Reuse vs Generate

Long-term, Story should determine the cheapest/easiest way to satisfy each Story need.

```text
                    STORY NEED
                        │
            ┌───────────┼───────────┐
            │           │           │
            ▼           ▼           ▼
         EXISTING     CAPTURE     GENERATE /
          MEDIA         NEW       TRANSFORM
            │           │           │
            └───────────┼───────────┘
                        ▼
                  STORY ASSET
```

Priority should generally be:

1. Reuse good existing material.
2. Capture something simple when authenticity matters.
3. Generate/transform when appropriate.

Generative AI should reduce capture burden rather than exist merely as a novelty.

---

# 17. Authenticity Principle

For personal memories, Story should distinguish between:

### Enhancement

The event happened; AI improves presentation.

Examples:

- stabilization
- reframing
- lighting
- object removal
- extension
- speed changes

### Reconstruction

The event/location is real; AI creates cinematography around it.

Examples:

- animate a real photograph
- create subtle camera movement
- extend a short real clip
- generate an alternate framing

### Fabrication

AI creates an event that did not happen.

Example:

> generating the user swimming in a lake when they never entered the lake

For memory-oriented use cases, Story should strongly prefer:

> **Capture reality. Generate cinematography.**

---

# 18. Editing

The final edit should be decided after Story understands the actual available material.

Editing pipeline:

```text
Story Blueprint
      +
Captured Assets
      +
Asset Understanding
      +
Creative Intent
        ↓
Story Reconciliation
        ↓
Edit Plan
        ↓
Deterministic Media Operations
        ↓
Optional Generative Operations
        ↓
Finished Story
```

Initial editing capabilities:

- clip selection
- trimming
- crop/reframe
- speed changes
- stabilization
- transitions
- music selection
- beat synchronization
- basic color treatment
- export

The LLM should decide **what** should happen.

Traditional media tooling should perform most deterministic operations.

---

# 19. MVP Scope

The full architecture above is the product vision.

The MVP should NOT implement all of it.

We will initially validate three connected workflows: **Create Now (DIRECT)**, **Start a Story (persistent StoryPlan that reuses DIRECT)**, and **Use Existing Media (EDIT)**.

---

# 19.1 MVP Path A — DIRECT

Goal:

Test whether AI creative direction produces enough additional value to justify the capture friction.

Flow:

```text
REFERENCE / TEMPLATE / TEXT
           ↓
     Creative Intent
           ↓
    Show Story scene
           ↓
 Scene Understanding
           ↓
Story recommends ONE concept
           ↓
   1–3 required shots
           ↓
    Guided capture
           ↓
   Simple validation
           ↓
       Assembly
           ↓
  5–15 sec Story
```

Example:

> "Make me an energetic 8-second Times Square video like this."

Story:

> **I have an idea.**

> Main Character — 8 sec — 2 shots.

Then direct capture.

---

# 19.2 MVP Path B — START A STORY

Goal:

Test whether a persistent Story can remember a larger creative goal, accumulate assets over time, and invoke DIRECT only when a useful capture is missing.

MVP flow:

```text
Creative Intent
      ↓
Create persistent Story
      ↓
Lightweight Story Blueprint
      ↓
Story Home / accumulated assets
      ↓
Story identifies one useful gap/opportunity
      ↓
Optional “Show me”
      ↓
Reuse DIRECT capture flow
      ↓
Return to persistent Story
      ↓
Create Story when enough material exists
```

For MVP, persistence can be local/simple and the opportunity can be simulated or manually triggered. Do not build proactive background notifications.

---

# 19.3 MVP Path C — EDIT / USE WHAT I HAVE

Goal:

Test whether Story can create useful output from imperfect/spontaneous media.

Flow:

```text
REFERENCE / TEMPLATE / TEXT
           ↓
     Creative Intent
           ↓
 User provides 2–10 clips
           ↓
   Asset Understanding
           ↓
 Story determines achievable
      creative direction
           ↓
        Edit Plan
           ↓
        Assembly
           ↓
     5–15 sec Story
```

No scene scan is required.

No capture guidance is required.

---

# 20. Postponed From MVP

Do NOT build initially:

- proactive background ASSIST/notification system
- production-grade long-trip automation
- sophisticated multi-day coverage scoring UI
- 60–90 second production-quality films
- thousands-of-photo ingestion
- full camera-roll indexing
- automatic deduplication
- sophisticated photo management
- persistent travel Story coverage
- proactive capture notifications
- LiDAR / detailed 3D understanding
- sophisticated AR direction
- full timeline editor
- proprietary video generation
- mandatory generative-video previews
- social network
- publishing/distribution system
- viral prediction
- deep personalization
- professional editing controls

These are future capabilities, not MVP requirements.

---

# 21. MVP UX Principle

The MVP should minimize the number of decisions required from the user.

The ideal DIRECT experience is:

```text
"I want something like this."
           ↓
"Show me where you are."
           ↓
"I have an idea."
           ↓
"Let's shoot."
           ↓
"Walk."
           ↓
"Got it."
           ↓
Finished Story
```

Not:

```text
Choose category
↓
Choose subcategory
↓
Describe style
↓
Scan
↓
Choose 1 of 5 concepts
↓
Configure concept
↓
Choose shot style
↓
Configure camera
↓
Capture
```

Story exists partly to **remove creative decisions from the user**.

---

# 22. Major Product Risks

## Risk 1 — Story creates more work than it saves

This is the largest risk.

Normal behavior:

```text
See something
↓
Open Camera
↓
Record
```

Story introduces additional interaction.

The result must be sufficiently better to justify that friction.

---

## Risk 2 — Generic creativity

If Story repeatedly recommends:

> walk → turn → reveal

across every environment, novelty will disappear quickly.

Story concepts must be:

- scene-specific
- context-specific
- style-specific
- varied

---

## Risk 3 — Over-planning

Consumers are not professional film crews.

Story should not turn vacations, dinners, or social experiences into production work.

Especially in ASSIST mode:

> **No recommendation is often the correct recommendation.**

---

## Risk 4 — Poor physical understanding

A model may recommend impossible camera or subject movements.

MVP should use qualitative guidance and conservative movement suggestions.

---

## Risk 5 — Reference interpretation

The user may like a reference for reasons they cannot articulate.

Story needs to distinguish:

- subject/content
- story structure
- camera grammar
- editing
- mood
- pacing

---

## Risk 6 — AI latency

Creative reasoning can tolerate a few seconds.

Capture guidance cannot.

Expensive model calls should not sit inside real-time interaction loops.

---

## Risk 7 — Generative AI cost

Generative video can quickly destroy consumer economics.

It should not be required for the initial value proposition.

---

## Risk 8 — Story quality evaluation

There is no simple objective metric for:

> "Is this a good Story?"

Human evaluation and preference testing will be necessary.

---

# 23. Core Technical Architecture

Conceptually:

```text
                         ┌─────────────────┐
                         │ Creative Intent │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ Story Blueprint │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   Story State   │
                         └────────┬────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
                ▼                 ▼                 ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │   Director   │  │    Vision    │  │ Asset Engine │
        │              │  │              │  │              │
        │ Story ideas  │  │ Scene        │  │ Existing     │
        │ Story needs  │  │ understanding│  │ media        │
        │ Shot plans   │  │ Validation   │  │ indexing     │
        └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
               │                 │                 │
               └─────────────────┼─────────────────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │ Captured Assets  │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │      Story       │
                       │  Reconciliation  │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │    Edit Plan     │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Media Pipeline  │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ Finished Story   │
                       └──────────────────┘
```

---

# 24. Important Architecture Principle

The product should NOT be implemented as one giant AI agent.

Story should be an orchestration layer around structured persistent state.

Models are replaceable.

The important long-term assets are:

- CreativeIntent schema
- StoryBlueprint schema
- StoryState
- StoryNeed representation
- Asset representation
- StoryPlan
- evaluation datasets
- creative grammar
- user preference signals

AI models should consume and update these structures.

---

# 25. Proposed Core Data Model

Initial conceptual representation:

```text
StoryProject
├── CreativeIntent
├── StoryBlueprint
├── StoryState
│
├── Assets[]
│   ├── source
│   ├── type
│   ├── metadata
│   ├── semantic_description
│   ├── quality/usability
│   └── story_roles[]
│
├── StoryNeeds[]
│   ├── role
│   ├── importance
│   ├── coverage
│   └── candidate_assets[]
│
├── CaptureSuggestions[]
│
├── StoryConcepts[]
│
└── EditPlan
```

Exact schemas should be defined before implementation.

---

# 26. Creative Grammar

One potential long-term differentiator is a structured representation of filmmaking/storytelling patterns.

Examples:

```text
Reveal
Push-in
Pull-out
Follow
Orbit
Foreground wipe
Match movement
Whip transition
Static subject / moving environment
POV
Reflection
Silhouette
Entrance
Exit
Human-vs-landscape
Detail → wide reveal
Motion match
Perspective transition
Time compression
Environmental movement
```

Story should eventually reason about which grammar is appropriate given:

```text
Creative Intent
      ×
Scene
      ×
Available subjects
      ×
Available assets
      ×
Story need
      ×
Capture difficulty
```

This can reduce generic LLM creativity.

---

# 27. Product Success Question

The most important question is NOT:

> Can Story generate a video?

Existing tools already generate and edit videos.

The question is:

> **Can Story understand what the user wants, understand what material is available, and intelligently reduce the effort required to get from experience to a compelling finished story?**

---

# 28. MVP Validation

Test Create Now/DIRECT, Start a Story, and EDIT as separate hypotheses while sharing the same Story core.

## DIRECT experiment

User enters a visually interesting environment.

Control:

> Make a 10-second video however you normally would.

Experiment:

> Use Story to create a 10-second video.

Measure:

- output preference
- time required
- number of takes
- frustration
- instruction compliance
- perceived creativity
- willingness to post
- willingness to use Story again

---

## EDIT experiment

Give Story:

- 5–10 random clips
- desired style/reference

Compare:

- Story output
- user's manual attempt
- simple template-based editor output

Measure:

- output preference
- time saved
- perceived originality
- whether Story understood intent
- willingness to use again

---

# 29. Primary MVP Success Metric

The most important qualitative question:

> **Would you use Story the next time you wanted to create this kind of content?**

A beautiful demo is not enough.

Users must prefer the workflow.

---

# 30. Product Evolution

If the MVP workflows work:

```text
PHASE 1

MVP

Create Now / DIRECT
Start a Story / persistent StoryPlan
Use Existing Media / EDIT

        ↓

PHASE 2

Deeper persistent Story intelligence

Story automatically tracks evolving
coverage and opportunities during an event

        ↓

PHASE 3

Multi-scene Story

birthday
day trip
city visit

        ↓

PHASE 4

Long Story

vacation
TMB
wedding
multi-day event

        ↓

PHASE 5

Full Story Agent

existing media
+
real-time capture
+
generation
+
editing
+
persistent taste
```

---

# 31. North-Star TMB Experience

TMB remains the north-star example for the full experience. The MVP now includes a deliberately simplified **Start a Story** slice using a TMB-like multi-day scenario, but does NOT require production-grade multi-day automation or a polished 60-second film.

Before the trip:

> "We're hiking TMB for eight days. I want a ~60-second cinematic film like these references. Mostly landscape and the feeling of the journey. Include us, but don't make it influencer-like."

Story creates a lightweight blueprint.

Then:

> **Got it. Enjoy your trip.**

During the trip, the user mostly captures naturally.

Story may occasionally identify a meaningful gap:

> You have plenty of landscapes, but almost nothing showing the two of you together.

> At the next viewpoint, want a simple 6-second suggestion?

Or:

> This location could work beautifully as your climax.

> Want me to show you a shot?

After the trip:

```text
Initial Creative Intent
        +
Hundreds of real assets
        +
Unexpected moments
        ↓
Story understands everything
        ↓
Story reconciles plan with reality
        ↓
Story finds strongest narrative
        ↓
Story identifies any missing material
        ↓
Optional AI reconstruction/generation
        ↓
Final 60-second Story
```

The user should feel:

> **I experienced my trip. Story handled the production.**

---

# 32. Product Principles

### 1. Plan lightly.

Do not force consumers into professional pre-production.

### 2. Capture naturally.

Spontaneous footage is first-class material.

### 3. Direct only when useful.

Every capture suggestion has a cost in user attention.

### 4. Reuse before requesting more.

Do not ask users to capture something they already have.

### 5. Reality can change the story.

The initial blueprint is provisional.

### 6. Minimize user decisions.

Story should make good defaults rather than constantly asking users to choose.

### 7. Show rather than explain.

Visual examples are more useful than cinematography terminology.

### 8. Capture reality; generate cinematography.

Especially for memories, preserve authenticity.

### 9. Story owns the outcome.

Do not optimize isolated poses or shots at the expense of the finished story.

### 10. The best direction may be no direction.

Story should protect the user's experience, not constantly interrupt it.

---

# 33. Current MVP Decision

Build three connected vertical slices:

### DIRECT

```text
Intent
→ optional scene understanding
→ one recommended concept
→ 1–3 guided shots
→ validation
→ automatic edit
→ finished 5–15 sec Story
```

### START A STORY

```text
Intent
→ persistent Story + lightweight blueprint
→ Story Home with accumulated assets
→ one optional opportunity/suggestion
→ invoke the frozen DIRECT capture flow
→ return to Story
→ simple final creation
```

### EDIT

```text
Intent
→ 2–10 existing/random assets
→ asset understanding
→ achievable story
→ automatic edit
→ finished 5–15 sec Story
```

Do not build ASSIST as a separate mode. **Start a Story is the MVP form of the persistent experience.** Keep it intentionally thin: persistent state, accumulated assets, Story Home, and reuse of DIRECT. Defer proactive notifications, sophisticated coverage reasoning, and production-grade long-running automation.

---

# 34. Working Product Definition

> **Story is an AI creative director that maintains an evolving understanding of what the user wants to create, what material they already have, and what is still needed—then finds the easiest path from intent to finished content.**

Short version:

> **Plan lightly. Capture naturally. Story does the rest.**

---

# 35. Frozen MVP UX Contract

The product UX is now frozen for MVP implementation. The following decisions supersede earlier exploratory flows where they conflict.

The user-facing product has three entry points:

```text
HOME
├── Create Now
├── Start a Story
└── Use Existing Photos / Videos
```

These are not three separate products. They share the same creative-intent, asset, director, edit-planning, music, and media-engine foundations.

## 35.1 Create Now

`Create Now` is the immediate DIRECT experience:

```text
Creative input
(template / reference / description)
        ↓
Optional scene understanding
        ↓
One recommended idea
        ↓
Example / preview
        ↓
Minimal guided capture
        ↓
Validation
        ↓
Automatic creation
        ↓
Finished short Story
```

Scene scanning is requested only when seeing the environment materially improves the recommendation.

The user should make as few creative decisions as possible. Story recommends one strong default and makes alternatives secondary.

## 35.2 Start a Story

`Start a Story` is a persistent creative container for something that unfolds over time.

It is intentionally not restricted to travel. Examples include:

- trip or hike
- birthday
- wedding
- city visit
- day out
- family event
- performance
- personal project

A Story is organized around a creative goal, not necessarily dates, days, locations, or an itinerary.

Frozen persistent Story structure:

```text
Story
├── Creative Direction
├── Moments
├── Story Guide
├── Story Idea / Show Me
├── Shoot a Moment
├── Create My Story
├── Generated Outputs
└── active/completed lifecycle
```

## 35.3 Creative Direction

The user may communicate what they want through:

- visual templates/examples
- reference media
- natural-language description
- lightweight context

Story normalizes this into `CreativeIntent`.

For persistent Stories, Story also derives a lightweight `MusicDirection`.

The user should not be required to know cinematography or music terminology.

## 35.4 Moments

`Moment` is the primary user-facing unit of media inside a persistent Story.

A Moment can originate from:

```text
DIRECT capture
spontaneous capture
existing phone media
camera-imported media
```

All are first-class Story material.

Adding photos/videos from within a Story means:

> Add these assets to this Story's Moments.

It does **not** mean:

> Immediately create the final Story.

Users can inspect accumulated Moments before creating an output. MVP Moment management should remain lightweight: add, browse, preview, and remove.

## 35.5 Story Guide

Story Guide is persistent guidance for what kinds of material would help tell the intended Story well.

It is not a rigid shot list.

For a TMB-like Story, it might contain narrative needs such as:

```text
Opening
Journey
Scale
Human moments
Challenge
Climax
Ending
```

For a birthday, the structure may be completely different.

Story Guide can exist before Story knows the future physical scenes. It should therefore communicate **what to look for**, not pretend to know exact framing or camera position in an unseen location.

Do not make Story Guide:

- a day-by-day timeline
- an itinerary
- a mandatory checklist
- a percentage-completion dashboard
- a production task manager

## 35.6 Story Idea → Show Me

Story Idea operates at the Story level.

It may say, conceptually:

> A quiet moment together could make the ending more personal.

This recommendation does not require Story to know the exact current scene.

When the user wants concrete help, `Show Me` can use current-scene understanding:

```text
Story-level need
      ↓
Show Me
      ↓
See current environment when useful
      ↓
Scene-specific idea
      ↓
Example / guidance
      ↓
DIRECT capture
      ↓
Moment added to Story
```

This separates long-horizon storytelling from immediate cinematography.

## 35.7 Shoot a Moment

`Shoot a Moment` lets the user intentionally create material for the current persistent Story.

When creative direction is useful, it reuses the same DIRECT primitive as Create Now:

```text
optional scene understanding
→ idea
→ example
→ guidance
→ capture
→ validation
→ Moment
```

The persistent Story should not need a separate directing engine.

## 35.8 Create My Story

`Create My Story` means:

> Use the material I currently have and create an output.

It is available at any point in the Story lifecycle.

The user does **not** have to finish Story Guide recommendations before creating.

Before generation, the user should be able to inspect the Moments currently available to Story. Story may select only the subset that improves the final result.

A user can create:

- no outputs yet
- one output
- multiple outputs over time

Creating an output does not change the Story from active to completed.

---

# 36. Music Model

Music is a core creative input because it changes pacing and edit structure.

The product should distinguish:

```text
MusicDirection
≠
MusicAsset
```

`MusicDirection` describes the desired feeling and may be inferred from Creative Direction:

- cinematic
- emotional
- epic
- dreamy
- energetic
- chill
- user-described direction

It should be lightweight and optional to modify.

The exact `MusicAsset` is selected around `Create My Story`, when Story knows the available Moments and desired output.

MVP behavior:

```text
CreativeIntent
+ MusicDirection
+ Moments
        ↓
recommended music
        ↓
EditPlan
        ↓
Finished Story
```

The user can preview Story's recommended track and choose from a small number of alternatives.

Changing music may trigger a different edit:

- different asset selection
- different segment lengths
- different cut points
- different pacing
- different emotional structure

Therefore music must not be implemented as merely replacing an audio file under a fixed video timeline.

MVP should use a small curated/licensing-safe music catalog. Large catalog integrations and music discovery are postponed.

---

# 37. Active and Completed Stories

Persistent Stories have a lightweight lifecycle:

```text
ACTIVE ↔ COMPLETED
```

This state is primarily organizational.

## 37.1 Create is not Complete

These concepts are independent:

> **Create My Story** = generate an output.

> **Complete Story** = stop treating this as something I am actively working on.

A Story can be active after multiple generated videos.

A Story can also be completed without ever generating a video.

## 37.2 Complete Story

`Complete Story` lives in the Story overflow menu rather than as another primary action.

Completion requires only lightweight confirmation.

Do not perform:

- final coverage review
- missing-shot analysis
- required creation
- automatic final rendering

The main visible effect is Home organization:

```text
CONTINUE
active Stories

YOUR STORIES
completed Stories
```

Completing a Story moves it out of `Continue` and into the lower completed Story list.

## 37.3 Completed Story behavior

Completion does not remove the Story's existing functionality.

The user can still access:

- Moments
- Story Guide
- Creative Direction
- existing generated outputs
- Create My Story

Proactive capture suggestions should stop while completed because the user has indicated they are no longer actively collecting material.

## 37.4 Reopen Story

A completed Story can be reopened.

Reopening:

- changes status back to active
- returns it to the active/Continue section
- restores active capture/suggestion behavior
- preserves all Moments, directions, guides, and generated outputs

No archive/project-management lifecycle is needed for MVP.

---

# 38. Account and Local-First Strategy

MVP does not require user registration.

First-run product behavior should prioritize value:

```text
Open Story
→ Create Now / Start a Story
→ request media/camera permissions when needed
→ use the product
```

Use a local anonymous identity/installation identifier underneath so Story objects have stable ownership without forcing authentication.

The architecture should permit later account attachment/migration without losing local Stories.

A full User Center is not part of MVP. A lightweight Settings surface is enough if needed.

Authentication should be introduced when the user asks for a capability that actually requires identity, such as:

- cloud backup
- cross-device sync
- collaboration
- server-side subscriptions/credits
- cross-platform continuity

Story remains local-first for original media. Avoid requiring users to upload an entire camera roll merely to use the product.

---

# 39. Revised MVP Data Model

The persistent model should now explicitly support Moments, outputs, music direction, and lifecycle state.

```text
Story
├── id
├── title
├── status: active | completed
├── CreativeIntent
├── MusicDirection
├── StoryBlueprint
├── StoryState
├── Moments[]
├── CaptureSessions[]
├── GeneratedOutputs[]
└── persistence metadata

Moment
├── id
├── story_id
├── Asset
├── source
├── created_at
├── AssetUnderstanding?
└── story_roles[]

CaptureSession
├── id
├── story_id?
├── SceneUnderstanding
├── StoryConcept
├── StoryPlan
├── Captures[]
└── Validation[]

GeneratedOutput
├── id
├── story_id
├── source_moment_ids[]
├── music_asset_id
├── EditPlan
├── output_asset
└── created_at
```

`story_id` can remain optional for a standalone Create Now session, but persistent Story captures should always attach back to the parent Story.

A Story can own multiple generated outputs. Output creation must not implicitly complete the Story.

---

# 40. Frozen MVP Scope

The MVP now includes:

| Capability | MVP decision |
| --- | --- |
| Create Now / DIRECT | Yes |
| Start a Story | Yes |
| Use Existing Media / EDIT | Yes |
| Persistent Story Home | Yes |
| Moments | Yes |
| Add/remove/preview existing media | Yes |
| Story Guide | Yes, lightweight |
| Story Idea / Show Me | Yes |
| Shoot a Moment | Yes, reuse DIRECT |
| Create My Story at any time | Yes |
| Multiple outputs per Story | Yes |
| Music Direction | Yes |
| Small music selection experience | Yes |
| Complete/Reopen Story | Yes |
| Mandatory account | No |
| Local anonymous identity | Yes |
| Local-first media | Yes |
| Cloud backup/sync | No |
| User Center | No |
| Thousands-of-assets ingestion | No |
| Full camera-roll indexing/dedupe | No |
| Background proactive notifications | No |
| Rigid itinerary/day timeline | No |
| Mandatory Story Guide completion | No |
| Full timeline editor | No |
| Generative video | No |
| Social network/publishing | No |

---

# 41. Updated North-Star TMB Experience

Before TMB, the user starts a Story and communicates:

> "I want an emotional cinematic film about the journey and the scale of the mountains. Mostly scenery, but include us naturally."

Story derives:

- Creative Direction
- Music Direction
- a lightweight Story Guide

The guide can tell the user what kinds of material may help:

```text
Opening
Journey
Scale
Human moments
Challenge
Climax
Ending
```

It does not pretend to know exactly what the user will encounter.

During the trip, the user can:

- shoot normally and add media as Moments
- browse accumulated Moments
- use `Shoot a Moment`
- open Story Guide
- receive or request a Story Idea
- use `Show Me` at a real viewpoint for scene-specific direction
- tap `Create My Story` at any time to see what Story can make so far

Creating a video on Day 3 does not imply the trip is finished.

The user may continue adding Moments and create another version later.

At the end of the trip, the user may choose `Complete Story`. This simply moves TMB out of the active `Continue` section into `Your Stories`. It does not force final rendering.

The user can still create another output later or reopen TMB if more media is found.

The intended feeling is:

> **I lived the experience. Story helped me know what was worth capturing and turned what I had into something worth keeping.**

---

# 42. Updated Product Principles

The previous principles remain, with four explicit additions.

### 11. Create whenever useful.

Do not force the user to finish collecting before seeing an output.

### 12. Completion is organization, not creation.

Story lifecycle and generated outputs are independent.

### 13. Music shapes the edit.

Treat music as creative structure, not decoration added at the end.

### 14. Earn the account.

Let users experience Story before asking them to register. Require identity only when an identity-dependent feature provides clear value.

---

# 43. Frozen MVP Product Definition

> **Story is an AI creative director that understands what the user wants to make, helps them recognize and capture useful moments when needed, remembers those moments across an experience, and turns the available material into a finished story with minimal creative work from the user.**

Short version:

> **Plan lightly. Capture naturally. Create anytime. Story does the rest.**

