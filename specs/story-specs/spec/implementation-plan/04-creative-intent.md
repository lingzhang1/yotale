
# Creative Intent — Technical Specification

Status: Draft for implementation review  
Component: Creative Intent  
Milestone: DIRECT Intelligence  
Primary owner: Story Engine  
Output contract: `CreativeIntent`

---

> **⚠️ SUPERSEDED FOR IMPLEMENTATION (2026-10-01).**
> This document is kept as **design rationale**. The authoritative,
> implementation-ready design is
> [`milestone-c-creative-intent-design.md`](./milestone-c-creative-intent-design.md);
> the canonical field contract is
> [`02-core-story-schema.md`](./02-core-story-schema.md) §4 →
> `contracts/schemas/creative-intent.schema.json`
> (`contracts/schemas/ai_contracts.py :: CreativeIntentContract`).
>
> **Read order for implementation:** the Milestone C design + the schema FIRST
> (what to build), then THIS doc for the *why* and the evaluation cases (§24).
> The reasoning here (input sources §4, precedence §5, the "must NOT contain"
> list §8, deterministic-vs-model split §10, reference features §18, eval cases
> §24-25) is still current and NOT duplicated in the design doc.
>
> **The field names in §6/§7 below are ILLUSTRATIVE, not the contract.** Where
> they differ from the frozen schema, the schema wins. Mapping:
> - `tone` → split into `desired_feeling` + `style_tags`
> - `storyEmphasis` → `emphasis`
> - `creativeConstraints` / `avoid` → `creative_constraints` (positive + negative)
> - `desiredDurationSeconds` → `target_duration_seconds`
> - `sourceSummary` → `source_inputs[]` (full objects, not just booleans)
> - `pace` → `pace` (adopted as a real field: `slow | moderate | fast`)
>
> **Decisions the draft left open are now CLOSED** in the design doc: resolution
> is **server-side**; transport is **hybrid** (text/template synchronous,
> reference media asynchronous via presigned upload + job poll); the Model
> Gateway has a **typed structured-output contract** with bounded repair/retry.

---

# 1. Purpose

Creative Intent converts the user's potentially vague, multimodal creative
direction into a small structured representation of what Story should try
to create.

Users should not need to understand:

- cinematography
- shot terminology
- editing terminology
- pacing terminology
- camera movement terminology
- music-production terminology

They should be able to express intent naturally.

Examples:

> Make this feel cinematic and peaceful.

> I want a short energetic video of Times Square.

> Something like this video.

> A quiet memory of our last morning in Kyoto.

> Make my hike feel epic but not cheesy.

Creative Intent translates those inputs into a representation that
downstream Story intelligence can reason about consistently.

Conceptually:

User Creative Direction
        │
        ├── text
        ├── template / example
        ├── optional reference media
        └── lightweight context
        │
        ▼
Creative Intent Resolver
        │
        ▼
CreativeIntent
        │
        ├──────────────→ Story Director
        │
        ├──────────────→ Story Guide
        │
        ├──────────────→ Edit Planner
        │
        └──────────────→ Music Direction

CreativeIntent describes the desired creative outcome.

It does NOT describe the current physical scene.

That responsibility belongs to Scene Understanding.

---

# 2. Product Role

CreativeIntent answers:

> What does the user want this Story to feel like and communicate?

It does not answer:

> What can the user shoot in front of them right now?

That separation is fundamental.

For example:

User says:

> Make a cinematic, energetic video of my afternoon at work.

CreativeIntent may represent:

- workday subject/context
- energetic tone
- cinematic visual character
- short-form output
- fast/moderate pacing
- emphasis on activity and environment

CreativeIntent must NOT invent:

- a desk
- a laptop
- a window
- a hallway
- coworkers
- available camera movement
- lighting conditions

Those are observations about the physical environment and belong to
`SceneUnderstanding`.

The Story Director combines both:

CreativeIntent
        +
SceneUnderstanding
        +
CaptureConstraints
        ↓
Story Director

---

# 3. Design Principles

## 3.1 Capture intent, not filmmaking instructions

CreativeIntent should describe the desired result.

It should not prematurely specify exact shots.

Bad:

```json
{
  "shot1": "wide establishing shot",
  "shot2": "close-up of hands",
  "shot3": "tracking shot"
}
```

Those decisions belong to Story Director.

Better:

```json
{
  "subject": "a day at work",
  "tone": ["energetic", "cinematic"],
  "pace": "fast",
  "desiredDurationSeconds": 10,
  "storyEmphasis": ["activity", "environment"]
}
```

The Director can then determine which shots make sense given the real
environment.

---

## 3.2 Keep the representation small

CreativeIntent is not a creative-writing document.

Avoid large fields containing generated prose.

Every field should exist because a downstream component uses it.

Prefer:

```text
small structured representation
```

over:

```text
large LLM-generated creative brief
```

---

## 3.3 Preserve user language where valuable

Structured normalization should not erase useful nuance.

For example:

> epic but not cheesy

should not become simply:

```text
tone = epic
```

because the negative preference materially affects creative decisions.

The system should preserve important user-specific creative constraints.

---

## 3.4 Infer reasonable defaults

Users should not have to configure every creative dimension.

For:

> A quiet morning in Kyoto.

Story may reasonably infer:

- reflective / calm tone
- slower pacing
- observational treatment

These are defaults, not facts.

The system should distinguish:

- explicitly requested intent
- inferred creative defaults

when that distinction matters for downstream reasoning or debugging.

---

## 3.5 Avoid unnecessary clarification

CreativeIntent should normally be resolvable without asking the user
follow-up questions.

Story should prefer a reasonable creative interpretation.

Ask the user only when ambiguity would materially change the intended
Story.

For example:

> Make something good.

may still be usable when a template/reference provides sufficient direction.

Do not turn Creative Direction into a configuration wizard.

---

# 4. Supported Input Sources

CreativeIntent may be derived from multiple sources.

## 4.1 Natural-language description

Examples:

> Make a dreamy video of our last evening in Tokyo.

> One day working at Amazon.

> Make the mountain feel huge and us feel tiny.

> I want something fun and chaotic.

Natural language is first-class input.

---

## 4.2 Template / visual example

The user may choose a Story-provided template or visual example.

A template should provide structured creative priors rather than forcing
the user to reproduce exact shots.

Example conceptual template:

```text
Cinematic Journey

tone:
  cinematic
  reflective

pace:
  moderate

story emphasis:
  environment
  movement
  progression
```

Templates should eventually resolve into the same CreativeIntent
representation as text input.

The rest of the system should not need a separate execution path for
"template intent".

---

## 4.3 Reference media

The user may provide a video or other supported reference representing:

> I want something like this.

The purpose is to understand creative characteristics, not to reproduce
the reference shot-for-shot.

Initial reference analysis should focus on characteristics such as:

- energy
- pacing
- approximate shot duration
- camera movement character
- subject/environment balance
- visual rhythm
- broad narrative structure
- overall mood

Do NOT treat reference analysis as:

- shot copying
- location copying
- subject copying
- exact transition copying
- exact composition copying

The reference describes creative language.

The current physical scene determines what is actually possible.

---

## 4.4 Lightweight context

Context may include product-known information that materially affects
interpretation.

Examples:

- persistent Story title
- Story description
- desired output duration
- current Story type/context where explicitly supplied
- whether this is Create Now or part of a persistent Story

Avoid feeding unrelated application state into Creative Intent.

---

# 5. Input Precedence and Combination

Creative inputs may coexist.

For example:

```text
template
+
reference
+
text description
```

They should be combined rather than forcing the user to choose exactly one.

General precedence:

```text
explicit user text
        ↓
explicit user modifications
        ↓
reference-derived characteristics
        ↓
template defaults
        ↓
system defaults
```

Explicit user intent wins when sources conflict.

Example:

Template:

```text
cinematic / slow
```

User says:

> Keep the cinematic look but make it fast and energetic.

Result should preserve the cinematic direction while overriding pacing.

Reference-derived properties should behave similarly.

If the reference appears slow but the user explicitly requests:

> Same visual feeling, but much faster.

the user's explicit request wins.

---

# 6. Proposed CreativeIntent Contract

The exact canonical definition remains owned by
`02-core-story-schema.md`.

This document defines the semantic requirements.

A minimal conceptual representation is:

```json
{
  "subject": "one day working at Amazon",

  "tone": [
    "energetic",
    "cinematic"
  ],

  "pace": "fast",

  "desiredDurationSeconds": 10,

  "storyEmphasis": [
    "activity",
    "environment"
  ],

  "creativeConstraints": [
    "authentic rather than staged"
  ],

  "sourceSummary": {
    "hasText": true,
    "hasTemplate": false,
    "hasReference": false
  }
}
```

This is illustrative.

Do not independently create a competing schema here.

The final machine-readable contract must come from the canonical shared
schema.

---

# 7. Candidate Semantic Fields

The following fields should be evaluated during implementation.

They should only remain if downstream systems actually benefit from them.

## 7.1 Subject

What the Story is broadly about.

Examples:

```text
one day working at Amazon
our first morning in Kyoto
hiking through the Alps
a birthday dinner
Times Square at night
```

This is semantic context, not a detected visual object list.

---

## 7.2 Tone

The emotional / creative character.

Examples:

```text
energetic
calm
intimate
playful
epic
dreamy
nostalgic
cinematic
raw
```

Prefer a small vocabulary plus preservation of meaningful free-form nuance
when necessary.

Avoid hundreds of near-synonymous labels.

---

## 7.3 Pace

Broad temporal energy.

Potential values:

```text
slow
moderate
fast
```

Do not encode exact edit timing here.

Exact shot duration and rhythm belong downstream.

---

## 7.4 Desired Duration

Approximate final output duration.

Example:

```text
10 seconds
```

This strongly affects how much material Director should request.

Duration may be:

- explicitly selected
- inferred from product mode
- inherited from a template
- defaulted by Story

---

## 7.5 Story Emphasis

What should receive creative attention.

Examples:

```text
person
environment
activity
relationship
scale
detail
journey
atmosphere
```

Multiple values may coexist.

This can help Director avoid treating every Story identically.

For example:

> Make the mountain feel huge and us feel tiny.

may strongly emphasize:

```text
environment
scale
person-in-environment
```

---

## 7.6 Creative Constraints

Important positive or negative preferences that do not fit cleanly into
other fields.

Examples:

```text
authentic, not staged

epic but not cheesy

don't make this feel like an advertisement

focus more on the environment than me

keep faces mostly out of it
```

This field should remain concise.

It must not become a dumping ground for arbitrary model reasoning.

---

# 8. What CreativeIntent Must NOT Contain

Do not include current-scene observations such as:

```text
there is a desk
sunlight is coming from the left
three people are standing nearby
there is a mountain behind the user
the hallway is narrow
```

Those belong to SceneUnderstanding.

Do not include detailed shot instructions such as:

```text
walk toward the desk
pan from left to right
shoot a 2-second close-up
```

Those belong to StoryPlan / Shot.

Do not include edit instructions such as:

```text
cut on beat
use a cross dissolve
speed ramp this clip
```

Those belong to EditPlan.

Do not include implementation information such as:

```text
modelId
promptVersion
provider
requestId
```

Those belong to operational metadata.

---

# 9. Resolution Pipeline

Recommended logical flow:

```text
CreativeDirectionInput
        │
        ├── text
        ├── template
        ├── reference
        └── context
        │
        ▼
Input Normalization
        │
        ├── deterministic template expansion
        └── normalize explicit settings
        │
        ▼
Reference Analysis
        │
        └── only when reference exists
        │
        ▼
Intent Resolver
        │
        ▼
Structured CreativeIntent
        │
        ▼
Schema Validation
        │
        ▼
Canonical CreativeIntent
```

Reference Analysis and Intent Resolution are logically separate even if
the initial implementation uses the same underlying model.

Do not expose model topology to the iOS client.

---

# 10. Deterministic vs Model-Based Work

Not every operation requires AI.

## Deterministic

Examples:

- template lookup
- explicit duration
- explicit user-selected vibe
- source metadata
- default product duration
- enum normalization where unambiguous

## Model-based

Examples:

- interpreting free-form creative language
- resolving combinations of template + text
- extracting style characteristics from reference media
- preserving nuanced constraints
- resolving ambiguous creative descriptions

Prefer deterministic handling where the meaning is already explicit.

Do not call a model merely to transform:

```text
duration = 10
```

into:

```text
desiredDurationSeconds = 10
```

---

# 11. Model Requirements

The Intent Resolver requires:

- strong natural-language interpretation
- reliable structured output
- low latency
- low/moderate cost
- ability to follow the canonical schema
- good handling of short ambiguous creative phrases

Reference analysis additionally requires multimodal understanding.

CreativeIntent itself should not depend on any specific model provider.

All model access must go through Model Gateway.

Conceptually:

```text
Story Engine
      ↓
Creative Intent Resolver
      ↓
Model Gateway
      ↓
configured model
```

Do not call provider SDKs directly from Creative Intent domain code.

---

# 12. Structured Output

Model output must be structured.

Never use free-form prose as the component contract.

Expected processing:

```text
model
  ↓
structured response
  ↓
parse
  ↓
Pydantic validation
  ↓
semantic validation
  ↓
CreativeIntent
```

If validation fails:

1. perform a bounded structured-output repair/retry;
2. validate again;
3. if still invalid, return a controlled failure or safe fallback.

Do not silently invent required values after repeated invalid output.

---

# 13. Defaults

Defaults should come from explicit product policy rather than being
invented independently by the model.

Example:

If Create Now targets a short social video and the user does not specify
duration, the product may provide a default duration.

That default should be supplied to Intent Resolver as context.

The model should not randomly choose:

```text
7 seconds
13 seconds
22 seconds
```

for otherwise identical requests.

Model creativity should influence creative interpretation, not basic
product configuration.

---

# 14. Confidence and Ambiguity

Avoid exposing meaningless numeric model confidence such as:

```text
confidence = 0.83
```

unless it has demonstrated product value.

Instead, ambiguity handling should be behavioral.

If sufficient:

```text
resolve intent
```

If genuinely underspecified but a reasonable default exists:

```text
apply default
```

If critically ambiguous:

```text
request clarification
```

Clarification should be rare.

---

# 15. Relationship to MusicDirection

Music matters to Story, but CreativeIntent and MusicDirection are
different concepts.

Example:

```text
CreativeIntent:
  tone = energetic
  pace = fast
  subject = city night

MusicDirection:
  energy = high
  mood = energetic
```

CreativeIntent may provide evidence used to infer MusicDirection.

But CreativeIntent should not contain:

- actual song IDs
- licensed track URLs
- beat maps
- BPM analysis
- music synchronization instructions

Those belong to the music subsystem.

---

# 16. Relationship to Persistent Story

A persistent Story owns a CreativeIntent.

CreativeIntent represents the overall intended creative direction.

It should remain relatively stable.

The Story may evolve as Moments accumulate, but Story should not silently
rewrite the user's original creative goal merely because new assets appear.

Future systems may derive additional StoryState from accumulated material.

That is separate from CreativeIntent.

Conceptually:

```text
CreativeIntent
    =
what the user wants

StoryState
    =
what Story currently has / understands

StoryBlueprint
    =
what would help tell the Story

SceneUnderstanding
    =
what is currently in front of the camera
```

These concepts must not collapse into one generic AI context object.

---

# 17. Relationship to Create Now

Create Now has no persistent Story requirement.

Its CreativeIntent may exist only for the CaptureSession / creation flow.

Conceptually:

```text
Create Now
   ↓
Creative Direction
   ↓
CreativeIntent
   ↓
DIRECT
```

Persistent Story:

```text
Start a Story
   ↓
Creative Direction
   ↓
CreativeIntent
   ↓
Story
   ↓
DIRECT invoked when needed
```

The same CreativeIntent semantics should work in both paths.

Do not create separate:

```text
CreateNowIntent
StoryIntent
```

unless future requirements prove they materially differ.

---

# 18. Reference Understanding

Reference media is a particularly important input because users often know
what they like without knowing how to describe it.

The initial implementation should extract only characteristics that can
actually influence downstream Story behavior.

Candidate reference features:

```text
energy
pace
average perceived shot length
camera movement character
subject/environment balance
visual rhythm
broad story structure
overall tone
```

Example:

Reference:

- rapid city montage
- short moving shots
- person frequently enters/exits frame
- environment remains prominent

Possible normalized influence:

```json
{
  "tone": ["energetic", "urban"],
  "pace": "fast",
  "storyEmphasis": [
    "person",
    "environment",
    "movement"
  ]
}
```

Do not attempt full semantic reconstruction of every reference shot in MVP.

---

# 19. Failure Behavior

CreativeIntent failure must not corrupt Story state.

Possible failures:

- model unavailable
- malformed structured output
- unsupported reference
- reference analysis timeout
- network unavailable

Where reasonable, degrade gracefully.

Example:

```text
reference analysis fails
+
user supplied meaningful text
        ↓
continue using text
```

Do not fail the entire Story creation merely because an optional reference
could not be analyzed.

If all meaningful creative input is unavailable and intent cannot be
resolved, return a recoverable UI state.

---

# 20. Latency Target

Creative Intent is part of an interactive user flow.

It should feel fast.

Initial engineering target:

```text
text-only CreativeIntent:
preferably ~1–3 seconds

reference-assisted CreativeIntent:
may take longer depending on reference analysis
```

These are targets, not hard guarantees.

Actual latency must be instrumented before final thresholds are frozen.

Avoid multi-call pipelines unless they materially improve output quality.

---

# 21. Observability

Record operational metadata outside the CreativeIntent domain object.

At minimum:

```text
operation
model/provider
prompt version
latency
retry count
structured-output success/failure
token/usage information when available
estimated cost when available
request/correlation ID
input-source types
```

Do not unnecessarily log raw user media or sensitive user content.

---

# 22. Prompt Architecture

Prompts should be versioned and externalized from domain logic.

Suggested organization:

```text
prompts/
└── creative_intent/
    ├── v1/
    │   ├── system.md
    │   ├── examples.json
    │   └── schema.json
    └── current
```

Exact filesystem mechanics may be adjusted during implementation.

The important requirements are:

- prompt version is identifiable
- prompt can evolve independently of domain code
- evaluation results can be associated with a prompt version
- examples are maintainable
- structured output schema is explicit

---

# 23. Initial Prompt Responsibility

The Creative Intent prompt should essentially ask:

> Translate the user's creative direction into the canonical
> CreativeIntent representation while preserving explicit preferences,
> applying only reasonable defaults, and avoiding assumptions about the
> physical scene.

It should explicitly distinguish:

```text
creative intent
vs.
scene facts
vs.
shot planning
vs.
editing decisions
```

This reduces responsibility leakage between engines.

---

# 24. Evaluation

Creative Intent should be evaluated independently before full DIRECT
integration.

Create cases covering:

### Simple explicit intent

> Energetic 10-second Times Square video.

### Emotional intent

> Our quiet last morning in Kyoto.

### Relative language

> Epic but not cheesy.

### Subject emphasis

> Make the mountains feel huge and us feel tiny.

### Negative preference

> Cinematic, but don't make it look like an advertisement.

### Minimal input

> Make something cool here.

### Template + override

Template:
Cinematic Journey

User:
> Faster and more playful.

### Reference + override

Reference:
slow cinematic travel video

User:
> Same visual feeling but much faster.

### Conflicting inputs

Template:
calm

User:
> I want this chaotic and energetic.

Explicit user intent should win.

---

# 25. Evaluation Criteria

Evaluate whether CreativeIntent:

1. preserves explicit user intent;
2. does not hallucinate physical-scene facts;
3. captures meaningful creative nuance;
4. avoids unnecessary filmmaking detail;
5. is compact;
6. provides enough information for Story Director;
7. resolves source conflicts correctly;
8. behaves consistently across similar inputs;
9. produces schema-valid output;
10. avoids unnecessary clarification.

The most important downstream question is:

> Given this CreativeIntent and an independent SceneUnderstanding, does
> Story Director have enough information to propose a good StoryConcept?

If not, modify the contract based on demonstrated downstream need rather
than adding speculative fields.

---

# 26. Initial MVP Scope

Implement first:

- natural-language Creative Direction
- template-derived defaults
- explicit duration
- explicit vibe/tone
- structured CreativeIntent
- source precedence
- model-backed language interpretation
- deterministic handling of explicit values

Then add:

- reference video analysis

if it can be implemented without blocking the first DIRECT evaluation.

Do not let sophisticated reference understanding delay testing the core
Director loop.

---

# 27. Open Technical Questions

The following should be resolved through implementation experiments rather
than assumptions:

1. Does `tone` need a controlled vocabulary, free-form values, or both?

2. Is `storyEmphasis` useful enough to justify a first-class field?

3. Should pace be categorical or continuous?

4. How much reference structure materially improves Director output?

5. Should reference analysis be its own reusable structured object before
   normalization into CreativeIntent?

6. Can a small/fast model reliably resolve text-only intent, or does output
   quality justify using the same stronger model as Director?

7. Which fields are actually consumed by Director after evaluation?

Do not prematurely freeze answers that can be tested cheaply.

---

# 28. Definition of Done

Creative Intent is ready for DIRECT implementation when:

- canonical CreativeIntent contract is frozen for the initial experiment;
- text input resolves reliably;
- template + text precedence works;
- structured output validates reliably;
- physical-scene hallucinations are rare;
- meaningful user constraints survive normalization;
- output is sufficiently compact;
- Director can consume it without needing raw user prose for ordinary cases;
- prompt versioning exists;
- evaluation fixtures exist;
- latency and approximate cost have been measured;
- failure behavior is defined.

At that point CreativeIntent can become a real upstream dependency of
Story Director.
```

## One design choice I want to flag before moving on

I intentionally made this spec **less ambitious than the schema might eventually become**.

I don't want CreativeIntent to turn into:

```text
40 AI-generated fields
→ fed to another LLM
→ most ignored
```

The core intelligence architecture should instead look like:

```text
            WHAT USER WANTS
                   │
            CreativeIntent
                   │
                   │
WHAT EXISTS        │
RIGHT NOW          │
     │             │
     ▼             ▼
SceneUnderstanding
         \       /
          \     /
           ▼   ▼
        DIRECTOR
           │
           ▼
     StoryConcept
           │
           ▼
       StoryPlan
```