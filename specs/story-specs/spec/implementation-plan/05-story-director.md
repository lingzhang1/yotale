> **⚠️ SUPERSEDED FOR IMPLEMENTATION (2026-10-01).**
> Kept as **design rationale** (strongest of the DIRECT drafts). The
> authoritative, implementation-ready design is
> [`milestone-c-story-director-design.md`](./milestone-c-story-director-design.md);
> the canonical field contracts are [`02-core-story-schema.md`](./02-core-story-schema.md)
> §16-18a → `contracts/schemas/{story-plan,story-concept,director-decision,director-state,validation-result}.schema.json`.
>
> **Read order:** the Milestone C design + schema FIRST (what to build), then THIS
> doc for the *why* (the beats argument §3, the loop §19, scene-specificity §10).
>
> **The §18 output JSON is ILLUSTRATIVE, not the contract.** Reconciled decisions
> (approved) — the Concept→Beats→Shots architecture and decision loop are adopted:
> - **`StoryBeat {id, purpose}`** added (minimal; no beat_type/scores). `StoryPlan`
>   gains `beats[]` + keeps `shots[]`.
> - **`Shot`** gains `beat_id` + `purpose`; keeps canonical
>   `framing`/`camera_motion`/`subject_action`/`instruction` (NO
>   `camera_behavior`/`subject_behavior` duplicates). `purpose`=semantic,
>   `instruction`=user-facing.
> - **`StoryConcept.summary` IS the thesis** (no separate `thesis` field).
> - **`DirectorDecision {action, shot?, reason?}`** added;
>   `action ∈ capture_shot|create_now|rescan_scene|retry_shot`. One strongest action.
> - **`BeatProgress {beat_id, status(unfulfilled|partial|fulfilled), supporting_asset_ids?}`**
>   + **`DirectorState`** added. Beat fulfillment is DIRECTOR state, NOT ValidationResult.
> - **`ValidationResult` stays shot-level** (no beat score); gained optional
>   `shot_id`/`capture_asset_id`.
> - **`CaptureSession`** gains `director_state`. StoryPlan=intent; DirectorState=progress.
>
> **Still-open experiments** (do not resolve silently): raw-frame access, beat
> count, plan-all-shots-upfront vs incremental, `supporting_asset_ids` need,
> model/provider, one-vs-two prompts, persistent-Story context depth.

---

## 1. What exactly is Story Director?

I would define it as:

> **Story Director converts creative intent and real-world context into the smallest coherent capture plan that can produce the intended Story.**

The important words are **coherent** and **smallest**.

It isn't:

```text
shot recommender
camera coach
cinematography chatbot
```

It is trying to answer:

```text
What are we trying to say/show?
        ↓
What visual progression expresses that?
        ↓
What material do I actually need?
        ↓
How can this person capture it simply?
```

That gives us a hierarchy.

---

# 2. I recommend Concept → Beats → Shots

I raised this question in the previous turn. After thinking through the downstream architecture, **I think we should introduce the concept of a visual/story beat**.

But importantly, a beat should be an **internal planning abstraction**, not another thing users have to understand.

The architecture becomes:

```text
CreativeIntent
       +
SceneUnderstanding
       +
CaptureConstraints
       +
existing CaptureSession state
       │
       ▼
┌─────────────────────────────┐
│        STORY DIRECTOR       │
│                             │
│  1. Story Concept           │
│           ↓                 │
│  2. Visual Beats            │
│           ↓                 │
│  3. Executable Shots        │
└─────────────────────────────┘
       │
       ▼
StoryConcept + StoryPlan
```

Consider TMB.

### Concept

```text
A tiny human moving through an enormous landscape.
```

This is the creative thesis.

Not:

```text
Cinematic hiking video.
```

That's merely a category.

Not:

```text
Shoot a wide shot of the mountain.
```

That's already implementation.

A useful StoryConcept gives the resulting video a point of view.

### Beats

For a ~10-second video:

```text
Beat 1 — SCALE

Establish that the landscape overwhelms the person.

Beat 2 — JOURNEY

Show the person progressing deeper into the landscape.

Beat 3 — ARRIVAL / RELEASE

Let the environment become the final emotional payoff.
```

Notice that these aren't shots.

The same `SCALE` beat could be realized differently depending on the scene.

### Shots

Now Scene Understanding turns those beats into executable instructions.

```text
BEAT
Establish scale.

SCENE KNOWLEDGE
trail creates depth
mountain dominates background
person available
operator space open

SHOT
Have your partner walk about 10–15 meters down the trail.
Stay where you are.
Keep them small in the lower part of the frame.
Hold still and record for 3 seconds.
```

That's something an ordinary user can actually do.

---

# 3. Why beats are worth having

The main reason isn't architectural elegance.

It's **adaptation**.

Imagine Director wants:

```text
Beat 1: establish scale
```

It proposes Shot A.

User captures it.

Validation says the clip is usable but the person occupies too much of the frame, so the scale contrast isn't very strong.

Without beats, our state is basically:

```text
shot A passed/failed
```

With beats:

```text
Beat:
  establish scale

Attempt:
  shot A

Result:
  usable
  partially fulfills beat
```

Director can decide:

```text
Good enough → continue
```

or:

```text
Scale is central to the concept.
Let's try one more simple shot.
```

More importantly, EDIT later understands **why footage exists**.

Instead of:

```text
clip_123
clip_456
clip_789
```

we have:

```text
clip_123 → establishes scale
clip_456 → expresses progression
clip_789 → provides emotional release
```

That could become extremely useful for automatic editing.

So I think `Beat` earns its place.

---

# 4. But don't make Beats a huge domain model yet

I would start very small:

```text
StoryBeat

id
purpose
status
```

Possibly:

```text
preferred_duration_seconds
```

but even that may belong later.

Example:

```json
{
  "id": "beat_scale",
  "purpose": "Establish the contrast between the small human subject and the enormous landscape.",
  "status": "planned"
}
```

That's enough.

We should resist:

```text
beat_type
emotion_curve
importance_score
narrative_function
cinematic_function
transition_strategy
energy_score
...
```

until Director/Edit demonstrates need.

---

# 5. Director should plan globally but direct incrementally

This is another major architecture decision.

I don't recommend:

```text
analyze scene
→ generate Shot 1
→ capture
→ generate Shot 2 from scratch
→ capture
→ generate Shot 3 from scratch
```

That can produce individually decent shots with no coherence.

I also don't recommend rigidly generating:

```text
Shot 1
Shot 2
Shot 3
```

and blindly forcing the user through all three.

Instead:

```text
                    DIRECTOR
                       │
            ┌──────────┴──────────┐
            │                     │
       GLOBAL PLAN           NEXT ACTION
            │                     │
       StoryConcept         ShotSuggestion
       StoryBeats                 │
            │                     │
            └──────────┬──────────┘
                       │
                    capture
                       │
                    validate
                       │
                       ▼
                 update state
                       │
                       ▼
                  DIRECTOR
                       │
                 next action
```

In other words:

> **Plan the Story globally. Execute it incrementally.**

That's a strong architectural principle for DIRECT.

---

# 6. Director is stateful at the session level

The LLM itself doesn't need to be stateful.

Our domain state does.

Director receives something like:

```text
DirectorContext

CreativeIntent
SceneUnderstanding
StoryConcept
StoryPlan
captured Moments
validation results
current beat
capture constraints
```

Then each invocation asks:

> Given the intended Story and what we have successfully captured so far, what should the user do next?

This allows Director to say:

```text
We already have enough.
→ CREATE
```

instead of mechanically requiring another shot.

That's important because our product philosophy is minimum effort.

---

# 7. Director should be allowed to stop early

This should be first-class.

Imagine the Director originally thinks:

```text
Beat A
Beat B
Beat C
```

But the first two clips turn out excellent.

The system shouldn't insist on C merely because the original plan contained it.

So the Director's next action isn't necessarily `Shot`.

Conceptually:

```text
DirectorAction =
    CaptureShot
  | CreateNow
  | RescanScene
  | RetryShot
```

Maybe later:

```text
SkipBeat
```

is internal rather than user-facing.

This means DIRECT is really a **decision loop**, not a generated shot list.

---

# 8. Minimum capture budget

I'd introduce another important principle:

> Every requested shot has a cost to the user.

Therefore Director should optimize approximately:

```text
Story quality
─────────────
capture effort
```

not simply maximize theoretical video quality.

If a 10-second Story can be made well from two clips, don't request five.

If the user already has useful assets, don't shoot redundant material.

If a beat isn't important enough to justify another capture, skip it.

This is one of the things that could make Story feel intelligent rather than demanding.

We don't need a numeric `capture_cost = 0.73`.

It's a reasoning principle.

---

# 9. One strong recommendation

This aligns with our frozen DIRECT UX.

Internally, the Director may consider several possibilities:

```text
candidate A
candidate B
candidate C
```

It can reason/rank internally.

But the contract should normally return:

```text
ONE StoryConcept
ONE next ShotSuggestion
```

not:

> Which one do you want?

The product is the director.

The user can reject/change it, but we don't transfer the creative decision burden back to them.

So:

```text
model considers alternatives
          ↓
Director selects strongest feasible one
          ↓
user sees one recommendation
```

---

# 10. Scene-specificity is mandatory

This is probably the most important quality criterion.

Suppose CreativeIntent is:

> cinematic and energetic

These scenes must not produce the same plan:

```text
office
Times Square
TMB
birthday dinner
hotel room
beach
```

A failure mode would be:

```text
1. wide establishing shot
2. medium action shot
3. close-up detail
```

That is generic filmmaking advice.

Director must exploit properties unique to the current environment.

### Office

Maybe:

```text
Concept:
"Momentum through a workday."

Use:
doorway framing
screen/desk activity
hallway movement
```

### Times Square

Maybe:

```text
Concept:
"Still person inside moving chaos."

Use:
crowd motion
neon
subject/environment contrast
```

### TMB

Maybe:

```text
Concept:
"Small human, enormous journey."

Use:
scale
trail depth
landscape
```

Same intent.

Different Story.

That's a core evaluation criterion.

---

# 11. Physical feasibility outranks cleverness

Director should not propose a brilliant shot that the user can't reasonably execute with a phone.

We need something like:

```text
Candidate Shot
      │
      ▼
Feasibility Check
      │
      ├── environment supports it?
      ├── subject exists?
      ├── operator space supports it?
      ├── physically reasonable?
      ├── safe capture behavior?
      └── simple enough?
      │
      ▼
recommend
```

Some of this may happen inside one model call initially.

I'm describing the **logical responsibility**, not necessarily separate services.

---

# 12. Shot instructions need two layers

I think a Shot should contain an internal semantic layer and a user-facing instruction layer.

For example:

```text
Shot

purpose:
  Establish scale by keeping the human small against the mountain.

subject:
  person

composition:
  person small, mountain dominant

camera_behavior:
  static

subject_behavior:
  walk away along trail

desired_duration:
  ~3 seconds

user_instruction:
  "Have your partner walk down the trail.
   Stay here and keep them small against the mountain.
   Hold still for about 3 seconds."
```

Why preserve the internal semantics?

Because Validation needs to know what matters.

It can evaluate:

```text
Was subject visible?
Was person sufficiently small?
Was camera reasonably stable?
Did clip last long enough?
```

If all we preserve is:

> “Have your partner walk down the trail...”

then later systems have to reverse-engineer intent from prose.

---

# 13. Don't over-specify cinematography

We need to remember the user isn't a filmmaker.

Bad:

> Use a 24mm-equivalent low-angle dolly-out while maintaining the subject on the lower-right rule-of-thirds intersection.

Better:

> Stay here. Hold the phone low and still. Keep your partner small against the mountain.

Internally we can represent:

```text
camera:
  static

framing:
  wide

subject_scale:
  small

camera_height:
  low
```

But the UI instruction should remain natural.

---

# 14. Director should understand Story duration

A 7-second Story and a 30-second Story require different capture strategies.

Roughly:

```text
7 sec
→ perhaps 1–2 excellent visual ideas

10–15 sec
→ perhaps 2–4 beats

30 sec
→ more progression / variety
```

But **don't turn this into fixed formulas**.

We should evaluate what works.

Desired duration should constrain:

```text
number of beats
capture quantity
shot duration
story complexity
```

---

# 15. Music should influence Director—but indirectly at first

We established earlier that music is important.

I don't think Director should choose actual tracks.

But CreativeIntent/MusicDirection can influence:

```text
energy
pace
rhythm
```

That may affect capture.

For example, fast energetic music can benefit from:

```text
shorter visual beats
more motion
more variation
```

while contemplative music may support:

```text
fewer shots
longer holds
less camera movement
```

Architecture:

```text
CreativeIntent
      │
      ├────────→ MusicDirection
      │
      ▼
Director
```

Eventually:

```text
CreativeIntent
MusicDirection
SceneUnderstanding
       ↓
Director
```

For first DIRECT experiment, CreativeIntent's `pace/tone` may be enough.

Don't make music selection block Director.

---

# 16. How persistent Story fits

This is important because DIRECT exists in both Create Now and Start a Story.

### Create Now

```text
CreativeIntent
      +
SceneUnderstanding
      ↓
Director
      ↓
Concept + Beats + Shots
      ↓
Capture
      ↓
Create
```

### Persistent Story

Suppose:

```text
"TMB Trip"
```

already has:

```text
StoryBlueprint
Story Moments
existing assets
```

Then DIRECT isn't creating an entirely unrelated mini-video.

It may be fulfilling part of the larger Story.

Eventually:

```text
StoryBlueprint
      │
      ▼
desired Moment / missing beat
      │
      +
CreativeIntent
SceneUnderstanding
      ↓
DIRECT
```

But I would **not fully solve persistent Story orchestration inside Director v1**.

Director's responsibility remains:

> Create a coherent capture plan for the current DIRECT task.

Story Guide/Blueprint determines **why that task is currently useful**.

That's a clean separation.

---

# 17. Proposed domain architecture

At this point, I think our conceptual model should be:

```text
┌────────────────────────────────────────────┐
│                STORY SYSTEM                │
│                                            │
│ Story Blueprint / Guide                    │
│ "What would help the overall Story?"       │
│                   │                        │
│                   ▼                        │
│             DIRECT task                    │
│                                            │
│ CreativeIntent       SceneUnderstanding    │
│       │                       │             │
│       └───────────┬───────────┘             │
│                   ▼                        │
│             STORY DIRECTOR                 │
│                                            │
│             StoryConcept                   │
│                   ↓                        │
│               StoryBeats                   │
│                   ↓                        │
│            Next ShotSuggestion             │
│                   ↓                        │
│                Capture                     │
│                   ↓                        │
│               Validation                   │
│                   ↓                        │
│             Director Loop                  │
│                   ↓                        │
│            enough material?                │
│               /       \                    │
│             no         yes                 │
│             │           │                  │
│          next shot    CREATE               │
└────────────────────────────────────────────┘
```

This is the architecture I would take forward.

---

# 18. Proposed Director output contract

I **wouldn't modify the canonical schema yet**, but this is what I want us to evaluate against it.

Something conceptually like:

```json
{
  "concept": {
    "title": "Small Human, Enormous Journey",
    "thesis": "Show the hiker as a small moving presence inside an overwhelming alpine landscape."
  },

  "beats": [
    {
      "id": "beat_1",
      "purpose": "Establish the scale contrast between the hiker and landscape."
    },
    {
      "id": "beat_2",
      "purpose": "Show progression deeper into the landscape."
    },
    {
      "id": "beat_3",
      "purpose": "End on the environment as the emotional payoff."
    }
  ],

  "next_action": {
    "type": "capture_shot",

    "shot": {
      "beat_id": "beat_1",

      "purpose": "Establish scale.",

      "subject": "hiker",

      "composition": "Keep the hiker small while the mountain dominates the frame.",

      "camera_behavior": "static",

      "subject_behavior": "walk slowly away along the trail",

      "desired_duration_seconds": 3,

      "instruction": "Have your partner walk down the trail. Stay here and keep them small against the mountain. Hold still for about 3 seconds."
    }
  }
}
```

Don't freeze this yet.

Kiro needs to compare it against the schemas we already have after we've finished the semantic design.

---

# 19. Director's decision loop

I think this is the heart of `05-story-director.md`:

```text
INITIALIZE

CreativeIntent
+
SceneUnderstanding
+
CaptureConstraints
        ↓
Generate coherent StoryConcept
        ↓
Generate minimum sufficient StoryBeats
        ↓
Choose highest-value unfulfilled beat
        ↓
Generate simplest feasible shot
        ↓
CAPTURE


LOOP

CapturedAsset
+
ValidationResult
+
StoryPlan state
        ↓
How well is the current beat fulfilled?
        ↓
   ┌────┼─────────────┐
   │    │             │
 poor partial       good
   │    │             │
 retry maybe      mark fulfilled
   │    │             │
   └────┴──────┬──────┘
               ↓
      Is Story sufficiently covered?
             /   \
           no     yes
           │       │
     next beat    CREATE
```

That makes DIRECT adaptive rather than scripted.

> **⛔ Supersession note (2026-10-05, C4-Lite decision).** The LOOP above shows the Director
> consuming an inline `ValidationResult` ("CapturedAsset + ValidationResult + StoryPlan
> state → how well is the beat fulfilled?"). **That inline semantic validation path is NOT
> being built for the MVP** — the GO/NO-GO audit (`milestone-c4-go-no-go-audit.md`) rejected
> inline semantic Shot Validation (latency/cost/trust). In the C4-Lite MVP there is **no
> inline semantic `ValidationResult`**; the capture loop runs only a local **capture
> integrity** check (`milestone-c4-lite-capture-integrity-design.md`) that can neutrally
> save a Moment or flag an obvious integrity failure, but makes **no beat/shot-fulfillment
> judgment**. Beat-progress / semantic shot-success therefore does **not** update inline.
> The future Director loop will consume **settled asynchronous Asset/Moment Understanding
> and Story coverage**, not an inline validation guess; that integration is designed
> together with Asset Understanding. Principle 10 below ("Validation feeds back into
> Director") still holds in spirit, but via async understanding, not an inline validator.

---

# 20. What I would freeze now

I think these are strong enough to become Director design principles:

1. **Concept → Beats → Shots.**
2. **Plan globally, direct incrementally.**
3. **One strong recommendation at a time.**
4. **Optimize for minimum sufficient capture.**
5. **Every shot must serve a beat.**
6. **Every beat must serve the StoryConcept.**
7. **Scene specificity is mandatory.**
8. **Physical feasibility beats creative cleverness.**
9. **Shot semantics and user-facing instructions are separate.**
10. **Validation feeds back into Director.**
11. **Director can decide that enough material already exists.**
12. **Director does not own persistent Story orchestration.**
13. **Director doesn't select actual music in v1.**
14. **Raw-frame access remains an experiment.**
15. **Don't add fields until downstream evaluation demonstrates need.**
