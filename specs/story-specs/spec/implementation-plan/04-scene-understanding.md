# Scene Understanding — Technical Specification

Status: Draft for implementation review
Component: Scene Understanding
Milestone: DIRECT Intelligence
Primary owner: Asset Engine / Scene Understanding
Primary consumer: Story Director
Output contract: `SceneUnderstanding`

---

> **⚠️ SUPERSEDED FOR IMPLEMENTATION (2026-10-01).**
> Kept as **design rationale**. The authoritative, implementation-ready design is
> [`milestone-c-scene-understanding-design.md`](./milestone-c-scene-understanding-design.md);
> the canonical field contract is [`02-core-story-schema.md`](./02-core-story-schema.md)
> §15 → `contracts/schemas/scene-understanding.schema.json`.
>
> **Read order:** the Milestone C design + schema FIRST (what to build), then THIS
> doc for the *why*, scene-acquisition options, privacy reasoning, and the
> evaluation strategy (§41–45), which are NOT duplicated in the design doc.
>
> **The §24 contract shape is ILLUSTRATIVE, not the contract.** Reconciled field
> decisions (approved):
> - **No `scene_type`** → use `summary` + `environment_tags`.
> - **No generic `visual_opportunities`** → kept split as `motion_opportunities`
>   + `composition_opportunities` (observations, not directing).
> - **`prominence`** added to each subject (`high|medium|low`, visual prominence).
> - **`operator_space`** added (`very_limited|limited|moderate|open|unknown`;
>   visibility, NOT a safety guarantee).
> - **No `spatial_structure`** object yet (fg/mg/bg/depth) — experiment.
> - **`lighting` stays a scalar** string (not an array) — experiment.
> - **No separate `action_opportunities`** — folded into `motion_opportunities`.
>
> **Transport & lifecycle decisions now CLOSED** in the design doc: ephemeral
> **synchronous** multipart frames first (no S3/async until measured); scan frames
> are **ephemeral** and must NOT use `MediaStore.adoptCapturedFile`; the Model
> Gateway gains a **generic multimodal** structured-request capability.
> **Still-open experiments** (do not resolve silently): whether Director also gets
> raw frames; whether `spatial_structure` is needed; frame count; S3/async need.

---

# 1. Purpose

Scene Understanding converts a lightweight scan of the user's current
physical environment into a compact structured representation that the
Story Director can use to make creative decisions.

It answers:

> What is actually here, and what creative possibilities and constraints
> does this environment provide?

It does NOT answer:

> What kind of Story does the user want?

That belongs to `CreativeIntent`.

It does NOT answer:

> What should the user shoot?

That belongs to Story Director.

Conceptually:

CreativeIntent
"What does the user want?"
          │
          │
          ▼
       DIRECTOR
          ▲
          │
SceneUnderstanding
"What can be shot here?"

Scene Understanding is therefore not intended to be a generic computer
vision system.

Its purpose is specifically to provide the minimum useful representation
of reality needed by Story Director.

---

# 2. Core Product Hypothesis

A useful Story Director must reason about both:

1. creative intent; and
2. the physical environment.

Without scene understanding, Director recommendations tend to become
generic:

- take a wide shot
- capture a close-up
- walk toward the camera
- pan across the scenery

With useful scene understanding, Director should be able to exploit
specific properties of the environment.

Example:

CreativeIntent:

> Make the mountain feel huge and us feel tiny.
> Quiet and contemplative.

Scene:

- large mountain dominates the background
- trail extends toward the mountain
- open foreground
- person can walk along trail
- strong foreground/background depth
- camera operator has room to remain stationary

Director can then propose:

> Have your partner walk about 15 meters down the trail.
> Stay here and hold the phone low.
> Keep them small in the frame with the mountain filling the background.

The value of Scene Understanding is therefore not object recognition.

The value is:

> enabling scene-specific creative direction.

---

# 3. Design Principles

## 3.1 Director-oriented, not vision-oriented

Do not expose everything the vision model can recognize.

For example:

```json
{
  "objects": [
    "grass",
    "rock",
    "shoe",
    "cloud",
    "tree",
    "backpack",
    "sign"
  ]
}
```

may be visually accurate but largely useless.

Scene Understanding should prioritize information that can change a
creative decision.

Useful information might include:

- a trail creates a strong line into the distance
- the mountain dominates the background
- a doorway can create a reveal
- the room allows several meters of camera movement
- a reflective surface can be used compositionally
- the environment is crowded
- the subject can safely move through the scene
- the lighting strongly favors one direction

---

## 3.2 Describe reality, not the desired Story

Scene Understanding must remain independent of CreativeIntent.

Given the same scan, these intents:

> Make this peaceful.

and:

> Make this chaotic and energetic.

should normally receive the same SceneUnderstanding.

The Director is responsible for deciding how the same environment should
be used differently for each intent.

This separation makes SceneUnderstanding reusable and testable.

---

## 3.3 Do not direct the user

SceneUnderstanding may describe:

> a long hallway provides several meters of visible depth

but should not say:

> walk backward through the hallway while filming the subject.

That is a Director decision.

Similarly:

SceneUnderstanding:

> mountain occupies most of the distant background

Director:

> keep the person small against the mountain.

---

## 3.4 Prefer useful relationships over exhaustive labels

Relationships often matter more than object inventories.

For example:

```text
person standing beside window
```

is more useful than:

```text
person
window
```

Likewise:

```text
trail leads toward mountain
```

is more useful than:

```text
trail
mountain
```

Scene Understanding should preserve meaningful spatial and visual
relationships when they materially affect directing.

---

## 3.5 Preserve uncertainty

The vision model must not create false physical certainty.

For example, from an image it may be impossible to determine whether:

- the camera operator can safely walk backward;
- a distant path is accessible;
- a surface can support the phone;
- a stranger will remain stationary;
- an apparent doorway is usable.

SceneUnderstanding should avoid converting visual inference into physical
fact.

Director must not receive unsupported assumptions as ground truth.

---

## 3.6 Minimize capture effort

Scene scanning exists to reduce user effort later.

It must not itself become a filmmaking task.

The user should not need to:

- carefully compose scan frames;
- manually photograph every object;
- map the room;
- perform a 360-degree scan;
- understand AR scanning;
- label subjects;
- reconstruct geometry.

For MVP, scanning should take only a few seconds.

---

# 4. Scene Acquisition

The MVP should capture enough visual context for useful directing while
keeping:

- user effort low;
- upload size low;
- latency low;
- privacy exposure limited;
- implementation complexity reasonable.

Candidate approaches are evaluated below.

---

# 5. Option A — Single Image

Flow:

```text
point camera
    ↓
capture frame
    ↓
Scene Understanding
```

Advantages:

- simplest UX;
- smallest payload;
- lowest latency;
- easiest implementation.

Limitations:

- narrow field of view;
- poor understanding of surrounding space;
- may miss useful movement opportunities;
- framing chosen by the user strongly biases understanding;
- difficult to understand spatial relationships outside the frame.

A single frame may be sufficient for some scenes, but should not be the
default assumption for DIRECT.

---

# 6. Option B — Short Pan + Representative Frames

Flow:

```text
user points phone around the scene
           ↓
short ~3–5 second scan
           ↓
sample representative frames locally
           ↓
deduplicate / select useful frames
           ↓
resize / compress
           ↓
multimodal Scene Understanding
```

Initial target:

```text
3–5 seconds scan
3–6 representative frames
```

Exact values should be measured rather than treated as permanent
constants.

Advantages:

- broader scene coverage;
- still relatively lightweight;
- no need to upload full video;
- allows multimodal models to infer relationships across views;
- simple enough for an ordinary user;
- compatible with local preprocessing.

Limitations:

- frames do not provide true geometry;
- duplicate frames waste model context;
- rapid camera movement can create blur;
- multi-frame spatial interpretation is imperfect.

This is the preferred MVP hypothesis.

It must be validated experimentally.

---

# 7. Option C — Short Video

Flow:

```text
3–5 second scan video
       ↓
upload compressed video
       ↓
video-capable multimodal model
```

Potential advantages:

- preserves temporal continuity;
- may improve understanding of camera movement through the space.

Disadvantages:

- larger payload;
- potentially higher latency;
- higher cost;
- model/provider dependency;
- more privacy exposure;
- unnecessary if representative frames provide comparable Director quality.

Do not use full-video understanding merely because a model supports it.

Adopt only if evaluation demonstrates material improvement over sampled
frames.

---

# 8. Option D — Spatial / AR Reconstruction

Examples:

- depth maps;
- ARKit scene reconstruction;
- SLAM;
- LiDAR;
- 3D environment mapping.

This may eventually enable advanced directing.

It is explicitly out of scope for MVP.

The product hypothesis does not require geometric reconstruction.

---

# 9. Recommended MVP Acquisition Strategy

Start with:

```text
3–5 second lightweight scene scan
        ↓
local frame sampling
        ↓
3–6 representative frames
        ↓
resize/compress
        ↓
multimodal Scene Understanding
```

The user-facing interaction should remain simple.

For example:

```text
"Show me what's around you"

[ camera ]

"Slowly move your phone around the scene"
```

Do not expose:

- frame sampling;
- model terminology;
- upload architecture;
- scene reconstruction terminology.

---

# 10. Frame Selection

Do not blindly select frames at fixed intervals if inexpensive local
selection materially improves representation.

Potential MVP strategy:

1. sample candidate frames;
2. remove obviously blurred frames;
3. remove near-duplicates;
4. preserve visually different viewpoints;
5. cap total frames.

Do not implement sophisticated computer vision unless required.

A simple image-similarity / blur heuristic may be sufficient.

The goal is not perfect scene reconstruction.

The goal is to give the multimodal model several useful views.

---

# 11. SceneUnderstanding Semantic Requirements

The canonical contract remains owned by `02-core-story-schema.md`.

This document defines what the representation needs to communicate.

Potential semantic categories are described below.

These categories should NOT automatically become fields.

Only promote them to first-class schema fields if Director evaluation
demonstrates value.

---

# 12. Scene Context

Broad description of the environment.

Examples:

```text
open alpine trail
modern office workspace
crowded urban intersection at night
small cafe interior
birthday dinner around a table
hotel room
beach at sunset
```

This provides semantic context without attempting exhaustive classification.

Potential representation:

```json
{
  "scene_type": "open alpine trail",
  "summary": "Wide mountain trail with strong depth and unobstructed mountain views."
}
```

`summary` should describe observable scene characteristics, not creative
direction.

---

# 13. Candidate Subjects

Identify elements that could plausibly become meaningful visual subjects.

Examples:

- person;
- couple;
- birthday cake;
- laptop/workstation;
- mountain;
- vehicle;
- food preparation;
- architectural feature.

Avoid listing every detectable object.

A candidate subject should be included because it could matter to Director.

Potential properties:

```text
type
description
approximate position
visual prominence
mobility when directly observable
```

Do not infer identity.

Do not infer intent.

---

# 14. Spatial Structure

Director may benefit from understanding broad composition and depth.

Useful concepts may include:

```text
foreground
midground
background
depth
open space
enclosure
dominant direction
subject/background relationship
```

Example:

```text
foreground:
  rocky trail

midground:
  person / trail

background:
  large mountain range

depth:
  strong
```

This is not metric geometry.

Do not pretend to know exact distances unless they are reliably available.

Relative descriptions are sufficient for MVP.

---

# 15. Visual Relationships

Important relationships may include:

```text
trail leads toward mountain
person stands against bright window
doorway frames workspace
street lines converge toward intersection
reflection mirrors subject
table gathers people into one visual group
```

These can be particularly valuable to Director because they expose
composition opportunities.

Avoid generating relationships that do not materially affect directing.

---

# 16. Visual Opportunities

The scene analyzer may identify observable visual characteristics that
could support creative use.

Candidate categories:

### Depth

Examples:

- strong foreground/background separation;
- long visible corridor;
- layered mountain ridges.

### Leading structure

Examples:

- trail;
- road;
- hallway;
- railing;
- architectural lines.

### Natural framing

Examples:

- doorway;
- arch;
- window;
- tree branches.

### Reflection

Examples:

- mirror;
- window;
- water;
- polished surface.

### Scale contrast

Example:

- small person against very large landscape.

### Reveal potential

Example:

- doorway opens into larger room;
- foreground obstruction partially hides a view.

### Light

Examples:

- strong side light;
- backlight;
- window light;
- neon illumination;
- sunset direction.

These are scene observations.

They are NOT shot recommendations.

---

# 17. Action Opportunities

Scene Understanding may describe observable possibilities for subject
action when reasonably supported by the scene.

Examples:

```text
person can visibly walk along open trail

workspace supports seated desk activity

people are gathered around a table

open pedestrian area provides visible walking space
```

Be conservative.

Do not claim:

```text
user can safely run backward while filming
```

from visual evidence alone.

Director must treat physical feasibility conservatively.

---

# 18. Camera / Operator Space

The Director benefits from knowing whether there appears to be room for
camera movement.

Potential coarse values:

```text
very_limited
limited
moderate
open
unknown
```

Examples:

Small cafe between tables:

```text
operator_space = limited
```

Mountain overlook:

```text
operator_space = open
```

This should represent visible spatial availability, not a safety guarantee.

---

# 19. Lighting

Lighting can materially affect useful direction.

Keep representation coarse.

Potential observations:

```text
bright daylight
soft overcast
strong backlight
window side-light
low light
neon night lighting
mixed indoor lighting
sunset / golden-hour appearance
```

Avoid attempting professional photometric analysis.

Director needs enough information to avoid obviously poor recommendations
and exploit strong light when available.

---

# 20. Constraints

Scene Understanding should identify visible constraints that materially
affect capture.

Examples:

```text
crowded
limited operator movement
low light
heavy visual clutter
moving strangers
narrow space
strong backlight
obstructed view
```

Constraints are not failures.

They help Director propose feasible ideas.

For example:

```text
crowded Times Square
```

should not cause:

> Clear the area and walk through the center alone.

---

# 21. Safety Boundaries

Scene Understanding is not a safety-assessment system.

It may observe:

```text
visible steep drop
traffic nearby
crowded moving environment
water edge
```

but must not certify:

```text
safe to walk backward
safe to stand near edge
safe to enter roadway
```

Story Director should operate under conservative capture rules independent
of visual model confidence.

No shot should require risky camera operation.

Examples of instructions Director should avoid:

- walking backward near a road;
- moving while looking only through the screen near an edge;
- entering traffic;
- climbing onto unstable structures;
- interfering with strangers;
- operating the camera where doing so would obviously create risk.

This is a Director constraint, not a SceneUnderstanding conclusion.

---

# 22. Uncertainty

Scene Understanding should represent meaningful uncertainty where needed.

Avoid arbitrary numeric confidence for every field.

Prefer explicit uncertainty such as:

```text
"possible doorway; accessibility unknown"

"appears to be a walkable trail; continuation not visible"

"open space visible, but obstacles outside scanned area unknown"
```

However, do not flood the contract with caveats.

Only preserve uncertainty that can prevent Director from making a bad
assumption.

---

# 23. What SceneUnderstanding Must NOT Contain

Do not include creative intent:

```text
make this peaceful
make the mountain feel epic
make the scene romantic
```

Do not include shot instructions:

```text
walk toward the mountain
pan across the skyline
shoot from the doorway
```

Do not include edit instructions:

```text
cut after 2 seconds
speed ramp here
transition to close-up
```

Do not include model metadata:

```text
provider
model_id
prompt_version
token_count
request_id
```

Do not include unsupported physical claims:

```text
safe_to_walk_backward = true
```

---

# 24. Proposed Minimal Contract Shape

Do not treat this as a competing canonical schema.

The final contract must be reconciled with
`02-core-story-schema.md`.

A useful experimental shape may resemble:

```json
{
  "id": "...",

  "summary": "Open alpine trail with a large mountain backdrop and strong visible depth.",

  "scene_type": "mountain trail",

  "subjects": [
    {
      "type": "person",
      "description": "one person on the trail",
      "prominence": "medium"
    },
    {
      "type": "landscape",
      "description": "large mountain range",
      "prominence": "high"
    }
  ],

  "spatial_structure": {
    "depth": "strong",
    "foreground": "rocky trail",
    "midground": "person and trail",
    "background": "large mountain range",
    "operator_space": "open"
  },

  "visual_opportunities": [
    "trail creates a strong line toward the mountain",
    "large scale contrast between person and landscape",
    "clear foreground-to-background depth"
  ],

  "action_opportunities": [
    "person can visibly move along the open trail"
  ],

  "lighting": [
    "bright natural daylight"
  ],

  "constraints": []
}
```

The experimental contract should remain compact.

If Director does not use a field, remove it.

---

# 25. Why `visual_opportunities` Exists

This field requires special scrutiny.

A vision model can potentially provide useful higher-level observations
such as:

> doorway naturally frames the desk

without actually deciding:

> film from the doorway.

That distinction may provide significant value.

However, `visual_opportunities` risks leaking Director reasoning into Scene
Understanding.

Therefore it should be experimentally compared against a more factual
representation.

Experiment:

### Representation A

Mostly factual:

```text
doorway at front
desk visible beyond doorway
window behind desk
```

### Representation B

Includes visual abstraction:

```text
doorway can visually frame the desk area
```

Feed both into Director.

Evaluate whether B materially improves recommendations.

Do not keep this abstraction merely because it sounds useful.

---

# 26. Scene Scan vs Existing Asset Understanding

Scene Understanding and Asset Understanding are related but distinct.

Scene Understanding asks:

> What is available to shoot right now?

Asset Understanding asks:

> What does this already-captured media contain, and how could it be used?

Scene Understanding:

```text
current physical environment
→ Director
```

Asset Understanding:

```text
existing photo/video
→ Edit Planner / Story intelligence
```

They may eventually share visual-analysis infrastructure.

Do not collapse their domain contracts for convenience.

---

# 27. Scene Scan vs Shot Validation

Scene Understanding occurs before Director recommendations.

Shot Validation occurs after a directed capture.

```text
Scene Scan
    ↓
SceneUnderstanding
    ↓
Director
    ↓
Shot
    ↓
Capture
    ↓
Validation
```

Validation asks:

> Did the captured clip satisfy the requested shot sufficiently to use?

Scene Understanding should not attempt to validate captured shots.

---

# 28. Scene Scan Lifecycle

SceneUnderstanding should normally be ephemeral to the capture context.

Conceptually:

```text
CaptureSession
    │
    ├── CreativeIntent
    ├── SceneUnderstanding
    ├── StoryConcept
    ├── StoryPlan
    └── captures
```

A persistent Story does not necessarily need to permanently retain every
SceneUnderstanding.

The original scan frames should not become permanent Story assets merely
because they were used for analysis.

Retention should be minimal.

---

# 29. When to Scan

Do not require Scene Scan in every possible DIRECT invocation.

Possible cases:

### Scan useful

- unfamiliar current location;
- environment strongly influences shot design;
- user asks Story to tell them what to shoot here;
- Director lacks sufficient visual context.

### Scan potentially unnecessary

- user is following an already-defined shot at a known scene;
- current visual context is already available and sufficiently recent;
- future product flows provide equivalent scene information.

For the first DIRECT implementation, prefer a simple predictable flow.

Do not prematurely build complex scan-reuse heuristics.

---

# 30. Freshness

SceneUnderstanding represents a moment in the physical environment.

It may become stale.

Examples:

- user walks to another room;
- lighting changes;
- crowd changes;
- user moves to another viewpoint.

MVP does not need sophisticated freshness detection.

CaptureSession should simply treat SceneUnderstanding as belonging to the
scene in which it was captured.

If the user clearly starts a new scene, perform another scan.

---

# 31. Processing Pipeline

Recommended logical pipeline:

```text
Scene Scan
    ↓
Local Candidate Frame Sampling
    ↓
Blur / Duplicate Filtering
    ↓
Representative Frame Selection
    ↓
Resize / Compression
    ↓
Temporary Transport
    ↓
Scene Analyzer
    ↓
Structured SceneUnderstanding
    ↓
Schema Validation
    ↓
Story Director
```

Local preprocessing should remain lightweight.

Do not introduce sophisticated CV infrastructure unless evaluation proves
it necessary.

---

# 32. Transport

The system should send only the representation required for the task.

Preferred initial experiment:

```text
sampled compressed frames
    ↓
backend
    ↓
Model Gateway
    ↓
multimodal model
```

Do not upload the original scan video if frames are sufficient.

Exact transport should follow existing backend/AWS architecture.

If payloads are small enough for synchronous request handling, prefer the
simpler synchronous architecture.

If measured payload/latency requires temporary object storage, use:

- private S3;
- opaque keys;
- encryption;
- short retention;
- automatic expiration.

Do not introduce asynchronous job infrastructure without measured need.

---

# 33. Privacy

Scene scans may contain:

- people;
- homes;
- offices;
- screens;
- documents;
- personal belongings;
- location clues.

Therefore:

1. minimize captured duration;
2. sample only required frames;
3. resize/compress for task requirements;
4. avoid permanent cloud storage;
5. automatically expire temporary objects;
6. do not add scan frames to Story assets;
7. do not log image contents;
8. do not train product-specific models on scans without a separate explicit
   product/privacy decision.

Privacy minimization should be part of architecture, not a future cleanup.

---

# 34. Model Requirements

Scene Analyzer requires:

- strong multi-image visual understanding;
- reliable structured output;
- spatial relationship reasoning;
- broad environment understanding;
- reasonable latency;
- ability to avoid unsupported assumptions.

All model calls go through Model Gateway.

Conceptually:

```text
Scene Understanding Engine
       ↓
Model Gateway
       ↓
configured multimodal model
```

No provider-specific SDK belongs in Scene Understanding domain code.

---

# 35. Structured Output

Scene Analyzer must return structured output.

Flow:

```text
multimodal model
      ↓
structured response
      ↓
parse
      ↓
Pydantic validation
      ↓
semantic validation
      ↓
SceneUnderstanding
```

Unknown fields should be rejected where the canonical schema requires a
closed shape.

Bounded structured-output repair may be used through Model Gateway.

Do not silently manufacture missing observations.

---

# 36. Prompt Responsibility

The Scene Understanding prompt should essentially ask:

> Describe the current physical environment only in ways that can help a
> downstream creative director propose feasible phone-camera shots.

The prompt should explicitly require:

- observable facts;
- important spatial relationships;
- visually meaningful scene structure;
- useful constraints;
- conservative uncertainty.

It should explicitly prohibit:

- shot recommendations;
- creative-story recommendations;
- edit instructions;
- invented physical capabilities;
- safety certification.

---

# 37. Prompt Architecture

Use versioned external prompts.

Suggested organization:

```text
prompts/
└── scene_understanding/
    ├── v1/
    │   ├── system.md
    │   ├── examples.json
    │   └── schema.json
    └── current
```

Prompt version should be associated with evaluation results.

---

# 38. Latency

Scene Understanding is directly inside an interactive capture flow.

Latency matters substantially.

Initial target:

```text
scene scan:
~3–5 seconds user action

frame preparation:
preferably sub-second / low seconds

model analysis:
target interactive latency

total post-scan waiting:
preferably only a few seconds
```

Do not freeze a strict SLA before measuring real devices/models.

Director may eventually be pipelined with Scene Understanding if that
materially improves perceived latency.

Do not complicate the first implementation prematurely.

---

# 39. Failure Behavior

Possible failures:

- camera permission unavailable;
- scan interrupted;
- frames unusable;
- network unavailable;
- multimodal model unavailable;
- malformed structured output;
- model cannot confidently interpret scene.

Do not fabricate a scene.

Preferred behavior:

```text
analysis failure
     ↓
preserve CaptureSession
     ↓
allow retry / rescan
```

If enough nonvisual context exists for Director to produce a degraded
generic recommendation, that may later become an explicit product fallback.

Do not silently substitute generic scene data in MVP.

---

# 40. Observability

Record outside the domain object:

```text
operation
model/provider
prompt_version
latency_ms
frame_count
compressed_payload_size
attempts
structured_output_success
usage/cost where available
correlation_id
```

Do not log raw scene images.

These metrics will be important when deciding:

- frame count;
- image resolution;
- model choice;
- sync vs async transport;
- whether scene analysis and Director should be combined.

---

# 41. Evaluation Strategy

Scene Understanding cannot be evaluated only by asking:

> Did it correctly identify the objects?

The important question is:

> Does this representation help Director make better scene-specific,
> feasible recommendations?

Evaluation therefore has two layers.

---

# 42. Layer 1 — Scene Representation Quality

For each scene evaluate:

### Accuracy

Are important observations visually supported?

### Relevance

Does the representation prioritize information that could affect directing?

### Spatial usefulness

Does it capture meaningful relationships and depth?

### Constraint awareness

Does it identify obvious limitations?

### Hallucination

Does it invent objects, access, movement possibilities, or spatial facts?

### Compactness

Is it concise enough for downstream reasoning?

---

# 43. Layer 2 — Director Utility

Compare Director output using:

### A

CreativeIntent only.

### B

CreativeIntent + basic object labels.

### C

CreativeIntent + full SceneUnderstanding.

If C does not materially improve:

- scene specificity;
- feasibility;
- creativity;
- instruction quality;

then SceneUnderstanding is over-designed or contains the wrong information.

This downstream evaluation is more important than raw vision accuracy.

---

# 44. Initial Evaluation Scenes

Build representative fixtures covering materially different environments.

At minimum:

## Office

Potential characteristics:

- desk;
- laptop;
- hallway;
- doorway;
- window;
- limited/moderate movement.

## Busy urban environment

Example characteristics:

- crowds;
- traffic;
- signs/lights;
- strong depth;
- moving background;
- limited control.

## TMB / mountain trail

Potential characteristics:

- huge landscape;
- trail;
- strong depth;
- person/environment scale contrast;
- open movement;
- terrain constraints.

## Cafe

Potential characteristics:

- table;
- food/drink;
- window;
- narrow movement;
- other customers;
- intimate scale.

## Birthday

Potential characteristics:

- people gathered around table;
- cake;
- social interaction;
- clutter;
- limited operator space.

## Landscape without person

Tests whether Director can work without assuming a human subject.

## Weak / boring environment

Example:

- plain wall;
- generic room;
- parking area.

This is particularly important.

Scene Understanding should accurately communicate limited opportunities
rather than inventing cinematic features.

---

# 45. Multi-Frame Evaluation

For selected scenes compare:

```text
1 frame
vs.
3 representative frames
vs.
5–6 representative frames
```

Measure:

- useful scene coverage;
- hallucination;
- Director quality;
- latency;
- payload;
- model cost.

The purpose is to find the smallest representation that produces good
Director output.

Do not assume more frames are always better.

---

# 46. Model Comparison

Evaluate candidate multimodal models through Model Gateway.

Compare:

- visual understanding;
- spatial relationship reasoning;
- structured-output reliability;
- hallucination;
- latency;
- cost.

Do not choose based solely on generic model benchmarks.

Use Story-specific scenes and Director utility.

---

# 47. Important Experimental Question — Facts vs Opportunities

One major architectural question remains intentionally open:

Should SceneUnderstanding contain only relatively factual observations:

```text
trail extends toward mountain
doorway in foreground
desk beyond doorway
```

or also higher-level visual opportunities:

```text
trail creates strong visual depth
doorway provides natural framing
person/landscape provides strong scale contrast
```

Experiment with both.

The second representation may significantly improve Director quality.

But if the Scene Analyzer begins effectively directing the shot, the
boundary has gone too far.

The desired division is:

```text
Scene Understanding:
"Here is what visually exists and why it may matter."

Director:
"Here is what you should do with it."
```

---

# 48. Relationship to Story Director

Story Director should receive:

```text
CreativeIntent
+
SceneUnderstanding
+
CaptureConstraints
+
relevant CaptureSession context
```

SceneUnderstanding should provide enough information that Director does not
normally need raw scan frames for the initial MVP architecture.

However, this is an experimental assumption.

A future experiment may compare:

### Pipeline A

```text
frames
→ SceneUnderstanding
→ Director
```

against:

### Pipeline B

```text
frames
+
CreativeIntent
→ multimodal Director
```

and:

### Pipeline C

```text
frames
→ SceneUnderstanding
+
frames
+
CreativeIntent
→ multimodal Director
```

Do not prematurely assume the structured intermediate representation is
always sufficient.

The canonical architecture should preserve SceneUnderstanding even if the
Director later also receives visual context.

---

# 49. Why Keep SceneUnderstanding If Director Can See Images?

Even if the Director eventually consumes images directly,
SceneUnderstanding remains valuable for:

- explainability/debugging;
- evaluation;
- stable domain contracts;
- reuse across Director attempts;
- avoiding repeated visual analysis;
- observability;
- potential Story Guide reuse;
- provider independence.

However, architecture purity should not be allowed to materially degrade
creative quality.

Evaluation decides whether Director also needs visual input.

---

# 50. MVP Non-Goals

Do not build:

- full 3D reconstruction;
- precise depth maps;
- centimeter-level distances;
- object tracking;
- person identification;
- facial recognition;
- emotion inference from faces;
- persistent environmental maps;
- continuous live vision;
- full-video semantic indexing;
- permanent scene-scan storage;
- sophisticated AR guidance;
- automatic safety certification.

These are not required to validate DIRECT.

---

# 51. Open Questions

Resolve experimentally:

1. Is a short pan meaningfully better than one well-chosen frame?

2. What is the minimum useful frame count?

3. What image resolution gives sufficient understanding?

4. Does local duplicate/blur filtering materially improve results?

5. Does `visual_opportunities` improve Director quality enough to justify
   the abstraction?

6. How much spatial structure should be explicitly represented?

7. Should SceneUnderstanding contain candidate action opportunities?

8. Can SceneUnderstanding remain intent-independent without sacrificing
   useful visual abstraction?

9. Does Director need raw frames in addition to SceneUnderstanding?

10. Which multimodal model provides the best Story-specific tradeoff among
    quality, latency, reliability, and cost?

11. Can scene analysis remain synchronous at acceptable latency?

12. How long can SceneUnderstanding reasonably be reused within a
    CaptureSession?

Do not freeze answers that are cheap to test.

---

# 52. Definition of Done — Design

Scene Understanding design is ready for implementation review when:

- its responsibility relative to CreativeIntent and Director is explicit;
- MVP scene acquisition strategy is defined;
- transport/privacy assumptions are defined;
- semantic requirements are defined;
- canonical schema implications are identified;
- model boundary is defined;
- structured-output behavior is defined;
- failure behavior is defined;
- evaluation strategy is defined;
- open experimental questions are recorded.

After repo-aware implementation review, update this document or create a
complementary implementation design without silently changing its product
semantics.

---

# 53. Definition of Done — Implementation

Scene Understanding is ready for DIRECT integration when:

- a real iPhone can perform the lightweight scene scan;
- representative frames are generated locally;
- only task-appropriate compressed visual data leaves the device;
- the backend invokes a real multimodal model through Model Gateway;
- output validates against the canonical SceneUnderstanding contract;
- failed analysis can be retried without losing CaptureSession state;
- scene scans are not permanently added to Story media;
- evaluation fixtures cover the major scene classes;
- hallucination and scene-grounding have been manually reviewed;
- latency, payload size, and cost are measured;
- Director evaluation demonstrates that SceneUnderstanding materially
  improves recommendations over intent-only/basic-object baselines.

At that point SceneUnderstanding can become a real upstream dependency of
Story Director.
