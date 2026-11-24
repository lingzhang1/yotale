# Evaluation — DIRECT Intelligence

**Status:** Draft
**Milestone:** DIRECT Intelligence / Milestone C
**Scope:** Creative Intent + Scene Understanding + Story Director
**Primary purpose:** Determine whether DIRECT produces useful, creative,
scene-specific, feasible direction with minimum user effort.

> **⛔ Shot-Validation scope update (2026-10-05, C4-Lite decision).** Where this document
> lists `ValidationResults` as an evaluation input/output (Phase 3 Director-loop
> simulation, data captured per run), note that **inline semantic Shot Validation was
> rejected for the MVP** (`milestone-c4-go-no-go-audit.md`). The MVP capture loop emits
> only a local **capture-integrity** signal (no semantic shot/beat success). Semantic
> `ValidationResult`-style judgment — and its evaluation — moves to the future
> **asynchronous Asset Understanding**. The C4A corpus, harness, four-axis research, model
>> comparison, and GO/NO-GO audit are preserved as that work's evaluation inputs. Treat the
> `ValidationResults` mentions below as *historical/async*, not an inline MVP eval target.
>
> **Asset Understanding evaluation (2026-10-05) now exists and is FROZEN.** The async
> semantic layer referenced above has its own human-reviewed ground truth
> (`evals/asset_understanding/ground_truth.json`, `au.ground_truth/1-approved`, 18 clips),
> scorer (`evals/score_au_finalists.py`), and model-selection gate (Sonnet 4.6 @ 24 frames —
> see `06-asset-understanding.md` §12 and `milestone-d-asset-understanding-experiment.md`).
> That is the regression gate for any AU model/frame/prompt/schema change; it is independent
> of this Director-focused document.

---

> **📎 LIVING SPECIFICATION — never "closed."** Unlike the Creative Intent /
> Scene Understanding / Story Director designs, this document is not frozen. Every
> bad Director behavior found in development or field testing becomes a
> fixture/regression case here. It grows from real failures.
>
> **Operational harness:** the runnable implementation lives in `evals/harness/`;
> the repo-aware plan is
> [`milestone-c-eval-harness-plan.md`](./milestone-c-eval-harness-plan.md). The
> **Layer-0 deterministic** foundation (schema/referential/enum/safety checks,
> fixture loader, run record + regression comparison) is BUILT and runs in CI with
> zero model cost. Layers 1-3 (LLM-judge, contrastive quality, human/field) are
> planned against the same spine and fill in when real models are on. The harness
> must be in place BEFORE prompt/model iteration so every change is MEASURABLE,
> not judged by demo feel.

---

# Evaluation Dataset Lifecycle

The evaluation dataset is not a one-time benchmark assembled before
implementation.

It grows continuously with the product.

Story uses three primary sources of evaluation data.

## 1. Curated Design Fixtures

Before implementing or tuning each AI component, create a small,
deliberately diverse fixture set covering the behaviors that component is
expected to handle.

Initial targets are guidelines, not hard requirements:

- Creative Intent: ~30–50 representative intent cases
- Scene Understanding: ~20–30 representative real scene scans
- Story Director: controlled Intent × Scene combinations plus Director-loop
  cases

Diversity and failure coverage are more important than dataset size.

Fixtures should describe expected and forbidden semantic properties rather
than pinning exact model prose.

Do not design the fixture set around the first model's outputs.

The purpose of the initial fixture set is to establish expected product
behavior before prompt/model tuning begins.

---

## 2. Development and Dogfood Failures

Every meaningful failure discovered while developing or using Story should
be considered a candidate regression fixture.

Examples include:

- misunderstood creative intent;
- hallucinated scene properties;
- missed scene opportunities;
- generic direction;
- unsafe direction;
- physically infeasible direction;
- instruction that is difficult to execute;
- incorrect retry behavior;
- redundant capture requests;
- failure to stop when enough footage exists.

The workflow is:

real failure
→ classify failure
→ preserve the smallest reproducible case
→ add regression fixture
→ fix behavior
→ run full evaluation suite
→ keep fixture permanently

When a failure is machine-checkable, also add or extend a deterministic
check where appropriate.

The regression dataset should therefore become increasingly representative
of actual Story failure modes over time.

---

## 3. Real-User Evaluation Sessions

After DIRECT is stable enough for internal dogfooding and beta testing,
collect consented real-world evaluation sessions.

The useful evaluation unit is the complete interaction trajectory, not only
an isolated image or model response.

Where privacy and consent allow, an evaluation session may contain:

- user creative input;
- CreativeIntent;
- scene scan / SceneUnderstanding;
- StoryConcept;
- StoryBeats;
- Director decisions;
- shot instructions;
- captured assets or privacy-safe derived representations;
- ValidationResults;
- Director-loop decisions;
- final Story;
- explicit user feedback.

Useful user-feedback questions include:

- Did Story suggest something worth shooting that you probably would not
  have thought of yourself?
- Was the direction easy to follow?
- Did the direction match what you wanted?
- Which recommendation was poor or confusing?
- Do you prefer the resulting Story to what you would normally capture?

Real-user data must follow the project's privacy, consent, retention, and
media-handling policies.

Do not assume production user media is automatically available for model
evaluation or training.

---

# Dataset Collection by Milestone

Dataset collection is part of each AI milestone rather than a separate
future task.

## Creative Intent milestone

Before significant prompt tuning:

- create approximately 30–50 curated Creative Intent fixtures;
- cover simple, detailed, vague, ambiguous, constrained, and equivalent
  phrasings;
- include tone, pace, subject emphasis, negative constraints, and
  underspecified requests.

During implementation:

- convert meaningful failures into regression fixtures.

## Scene Understanding milestone

Before significant model/prompt tuning:

- collect approximately 20–30 representative real scene scans;
- include indoor/outdoor, open/constrained, crowded/empty,
  bright/low-light, landscape/social/urban environments;
- include difficult and ambiguous scenes, not only visually attractive
  examples.

During real-device testing:

- convert hallucinations, missed opportunities, and missed constraints into
  regression fixtures.

## Story Director milestone

Construct controlled combinations of:

- same intent × different scenes;
- same scene × different intents;
- selected Intent × Scene cross-matrix cases;
- Director-loop outcomes.

During dogfooding:

- every meaningful Director failure becomes a candidate regression case.

## Director Loop / End-to-End milestone

Add complete trajectories covering:

- successful capture;
- failed capture requiring retry;
- usable capture with partially fulfilled Beat;
- new Shot for the same Beat;
- scene rescan;
- early create_now;
- redundant-capture prevention.

## Beta

Begin collecting consented real-session cases and explicit user quality
feedback.

These cases should gradually become the most important source of new
regression fixtures.

---

# Evaluation Capture in Debug Builds

Once Story Director exists and internal dogfooding begins, add a lightweight
debug-only mechanism for recording poor Director behavior.

Conceptually:

Director recommendation

[Good direction]
[Bad direction]

For bad direction, allow classification such as:

- generic;
- does not use this scene;
- does not match my intent;
- difficult to shoot;
- physically infeasible;
- unsafe;
- confusing;
- other.

The debug mechanism should preserve enough structured context to reproduce
the behavior, subject to privacy constraints.

It should make it easy to convert the captured case into an evaluation
fixture.

This debug tooling is NOT required before Creative Intent implementation.

Implement it when Story Director becomes available for real-device
dogfooding.

---

# Evaluation Dataset Rule

No AI milestone is complete until meaningful new failures observed during
that milestone have been:

1. converted into regression fixtures; or
2. explicitly documented as intentionally unsupported / deferred behavior.

Evaluation data collection is therefore part of the Definition of Done for
every AI milestone.

The expected lifecycle is:

DESIGN
→ CURATED FIXTURES
→ IMPLEMENT
→ RUN EVALUATION
→ REAL-DEVICE TEST
→ DISCOVER FAILURES
→ ADD REGRESSION FIXTURES
→ FIX
→ RUN FULL EVALUATION
→ NEXT MILESTONE

The evaluation dataset is a living product asset.

It should become more valuable as Story encounters more real environments,
creative intents, capture behaviors, and user failures.



# 1. Purpose

This document defines how Story evaluates the intelligence behind DIRECT.

The primary product question is:

> Does Story help an ordinary user capture a better Story than they would
> have captured without direction?

The system must not be judged primarily by:

- JSON validity;
- model benchmark scores;
- object-recognition accuracy;
- prompt aesthetics;
- number of generated shots;
- subjective impressions from isolated demos.

Those are useful diagnostics.

The primary evaluation target is the behavior of the complete creative
system.

DIRECT should:

1. understand what the user wants;
2. understand what is physically available;
3. form a coherent creative idea;
4. exploit scene-specific opportunities;
5. propose simple executable shots;
6. adapt to what the user actually captures;
7. stop asking for footage when enough material exists.

---

# 2. Evaluation Philosophy

Evaluation follows five principles.

## 2.1 Evaluate downstream utility

An intermediate representation is valuable only if it improves downstream
behavior.

For example:

SceneUnderstanding should not be considered good merely because it
correctly identifies:

- mountain;
- trail;
- person.

It is useful if those observations allow Director to produce better
direction.

Therefore evaluate both:

- component quality;
- downstream Director utility.

---

## 2.2 Evaluate behavior, not prose quality

A Director response can sound cinematic while being useless.

Example:

> Capture the majesty of the mountains and the spirit of adventure.

This sounds creative but does not tell the user what to do.

Evaluation should ask:

> Could an ordinary user execute the recommendation?

and:

> Would the resulting footage meaningfully support the intended Story?

---

## 2.3 Evaluate contrastively

Many important qualities cannot be measured from one output.

Instead compare controlled variations.

Examples:

Same intent + different scenes:

```text
Intent
"cinematic and energetic"

Office
Times Square
TMB
Birthday
Beach
```

Director output should change materially.

Same scene + different intents:

```text
TMB scene

"quiet and contemplative"
"fast energetic adventure"
"make the person feel tiny"
"focus on our relationship"
```

Director output should also change materially.

Contrastive evaluation is central to this system.

---

## 2.4 Prefer categorical judgments over fake precision

Avoid unsupported metrics such as:

```text
creativity = 8.73
cinematic quality = 91.2%
```

Prefer bounded rubrics with concrete anchors.

Example:

```text
0 = generic / fails requirement
1 = partially useful
2 = clearly satisfies requirement
```

Aggregate scores may be calculated for experiment comparison, but the
underlying judgments must remain interpretable.

---

## 2.5 Human review remains necessary

Automated LLM judges can accelerate iteration.

They must not become the sole authority for subjective creative quality.

Use:

```text
deterministic checks
+
LLM-assisted evaluation
+
human review
```

for different aspects of quality.

---

# 3. Evaluation Layers

Evaluation has four layers.

```text
Layer 0 — Contract / deterministic correctness
Layer 1 — Component quality
Layer 2 — Director behavior
Layer 3 — End-to-end user outcome
```

Each layer answers a different question.

---

# 4. Layer 0 — Contract Correctness

These checks should be automated.

Examples:

- output validates against canonical JSON Schema;
- unknown fields rejected where required;
- referenced Beat IDs exist;
- every Shot references a Beat;
- DirectorDecision contains a valid action;
- `capture_shot` includes a valid Shot;
- supporting asset references exist;
- no malformed enums;
- no impossible object references.

These tests detect software/model-contract failures.

They do NOT measure creative quality.

---

# 5. Creative Intent Evaluation

Creative Intent asks:

> What does the user want to create?

Evaluate:

## 5.1 Intent fidelity

Does the structured representation preserve the user's important request?

Example:

User:

> Make this feel peaceful and cinematic. I mostly care about the mountain,
> not us.

The result should preserve:

- peaceful tone;
- cinematic aspiration;
- landscape emphasis;
- reduced human emphasis.

---

## 5.2 No unsupported invention

CreativeIntent should not invent major preferences.

Failure example:

User:

> Make a short video of this hike.

Output invents:

> romantic couple Story

without evidence.

---

## 5.3 Reference-media usefulness

When reference media is provided:

> Does it extract useful creative characteristics without merely describing
> objects in the reference?

Relevant characteristics may include:

- pacing;
- visual energy;
- composition tendency;
- subject emphasis;
- atmosphere.

---

## 5.4 Stability

Equivalent user requests should produce semantically similar intents.

Exact wording need not match.

---

# 6. Scene Understanding Evaluation

Scene Understanding asks:

> What is actually available to shoot here?

Evaluate:

## 6.1 Grounding

Are observations supported by the provided scene frames?

---

## 6.2 Hallucination

Does it invent:

- objects;
- people;
- accessible paths;
- movement possibilities;
- spatial relationships;
- physical capabilities?

Unsupported physical assumptions are particularly serious.

---

## 6.3 Director relevance

Does the representation prioritize information useful for directing?

Bad:

```text
rock
shoe
cloud
grass
backpack
```

Better:

```text
trail creates strong visible depth toward mountain
person is small relative to landscape
operator space appears open
```

---

## 6.4 Constraint awareness

Does it recognize visible limitations such as:

- crowding;
- narrow operator space;
- low light;
- visual obstruction;
- nearby traffic;
- steep terrain?

---

## 6.5 Compactness

Does it communicate useful information without dumping irrelevant visual
details?

---

# 7. Scene Understanding Downstream Utility

This is more important than raw recognition quality.

For the same CreativeIntent compare Director output with:

```text
A — CreativeIntent only

B — CreativeIntent + basic object labels

C — CreativeIntent + full SceneUnderstanding
```

Evaluate whether C improves:

- scene specificity;
- feasibility;
- creative use of the environment;
- shot quality;
- instruction quality.

If C does not materially improve Director behavior, SceneUnderstanding is
either:

- unnecessary;
- incorrectly structured;
- too lossy;
- or not being used effectively by Director.

---

# 8. Story Director — Primary Evaluation Dimensions

Director is the primary product-quality target.

Evaluate each recommendation across the following dimensions.

---

## 8.1 Intent Alignment

Question:

> Does the concept and shot direction express the requested creative intent?

Examples:

A contemplative request should not routinely produce frantic movement.

An energetic request should not always produce static scenic shots.

---

## 8.2 Scene Specificity

Question:

> Does the recommendation exploit something meaningfully specific to this
> environment?

Failure:

> Take a wide shot.
> Take a medium shot.
> Take a close-up.

Pass:

> Use the long trail and large mountain backdrop to keep the hiker visually
> small against the landscape.

Scene specificity is a critical quality gate.

---

## 8.3 Concept Strength

Question:

> Does the StoryConcept provide a coherent creative point of view?

Weak:

> Cinematic mountain hiking video.

Stronger:

> A tiny human moving through an enormous landscape.

The concept should guide later decisions.

---

## 8.4 Beat Coherence

Question:

> Do the Beats collectively express the StoryConcept?

Each Beat should have a reason to exist.

Failure:

```text
Beat 1: mountain
Beat 2: walking
Beat 3: backpack
```

Better:

```text
Beat 1: establish human/environment scale
Beat 2: show progression through the landscape
Beat 3: let the destination/environment provide release
```

---

## 8.5 Shot-to-Beat Coherence

Question:

> Does the requested Shot actually serve its Beat?

Every Shot should have a clear semantic purpose.

---

## 8.6 Executability

Question:

> Could an ordinary phone user understand and execute this instruction?

The user should not need filmmaking vocabulary.

---

## 8.7 Physical Feasibility

Question:

> Does the visible scene plausibly support the recommendation?

Consider:

- subject availability;
- operator space;
- movement;
- environmental constraints;
- phone-camera limitations.

---

## 8.8 Safety

Recommendations must avoid obviously risky capture behavior.

Examples of failures:

- walking backward near a cliff;
- entering traffic;
- climbing unstable structures;
- focusing on the screen while moving through hazardous terrain.

Safety violations are hard failures, not creative-quality tradeoffs.

---

## 8.9 Specificity of Instruction

Weak:

> Capture the epic scenery.

Strong:

> Stay here while your partner walks down the trail. Keep them small in
> the frame and hold still for about three seconds.

The instruction should answer enough of:

- what should the subject do?
- what should the camera operator do?
- what should dominate the frame?
- how long should the capture approximately last?

without becoming overly technical.

---

## 8.10 Creative Non-Obviousness

Question:

> Does the recommendation provide meaningful creative value beyond what an
> ordinary user would likely do automatically?

This does NOT mean every recommendation must be unusual.

Novelty without usefulness is not a goal.

The desired property is:

> useful creative direction the user plausibly would not have considered.

---

## 8.11 Minimum Capture

Question:

> Is every additional requested capture worth the user's effort?

Director should not request footage merely because another Beat or Shot
exists in the initial plan.

If sufficient material exists, prefer:

```text
create_now
```

---

## 8.12 Adaptation

After capture + validation:

> Does Director make a sensible next decision based on what actually
> happened?

Examples:

- successful capture → advance;
- technically failed same shot → retry_shot;
- valid capture but Beat remains weak → new capture_shot for the same Beat;
- scene no longer usable → rescan_scene;
- sufficient material → create_now.

---

# 9. Director Rubric

For most subjective Director dimensions use:

```text
0 — fails
1 — partially satisfies
2 — clearly satisfies
```

Evaluate:

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Intent alignment | conflicts/ignores | partially reflects | clearly expresses |
| Scene specificity | generic | some scene use | strongly scene-grounded |
| Concept strength | label/category | usable but generic | clear creative thesis |
| Beat coherence | disconnected | partly coherent | coherent progression |
| Shot-to-beat fit | unrelated | partial | clearly serves Beat |
| Executability | confusing | executable with interpretation | immediately actionable |
| Feasibility | unsupported | uncertain | clearly plausible |
| Instruction specificity | vague | adequate | concrete/simple |
| Creative value | obvious boilerplate | somewhat useful | meaningfully adds an idea |
| Capture efficiency | redundant | acceptable | minimum sufficient |

Safety is evaluated separately as pass/fail.

Do not treat the summed score as absolute truth.

Use it primarily to compare:

- prompts;
- models;
- contract variants;
- context variants.

---

# 10. Contrastive Matrix — Scene Sensitivity

Use the SAME intent across different scenes.

Example intent:

> Make it cinematic and energetic.

Fixtures:

1. office;
2. busy urban intersection;
3. TMB alpine trail;
4. birthday dinner;
5. hotel room;
6. beach.

Evaluate:

- concept diversity;
- Beat diversity;
- scene-specific opportunity use;
- feasibility;
- repeated generic patterns.

Failure signal:

Most scenes receive some variation of:

```text
wide establishing shot
medium action
detail close-up
```

---

# 11. Contrastive Matrix — Intent Sensitivity

Use the SAME scene with different intents.

Example scene:

TMB alpine overlook.

Intents:

1. quiet and contemplative;
2. energetic adventure;
3. make the person feel tiny;
4. focus on our relationship;
5. landscape-first travel memory.

Evaluate whether:

- StoryConcept changes;
- Beats change;
- shot behavior changes;
- subject/environment emphasis changes;
- camera motion changes where appropriate.

Failure signal:

Different intents produce nearly identical plans with adjective changes.

---

# 12. Cross Matrix

After the individual contrastive tests work, construct a smaller matrix:

```text
              Intent A   Intent B   Intent C

Office           X          X          X

TMB              X          X          X

Birthday         X          X          X
```

This helps detect whether the model is over-dominated by:

- scene;
- intent;
- generic filmmaking priors.

Do not start with a huge combinatorial fixture set.

---

# 13. Director Loop Fixtures

Static initialize evaluation is insufficient.

Create multi-step fixtures.

Example:

```text
INITIAL
Beat: establish scale
Shot: person small against mountain
```

### Outcome A — successful

Validation:

```text
usable = true
recommendation = accept
```

Expected:

- Beat becomes fulfilled or Director otherwise accepts sufficient coverage;
- move to next highest-value Beat OR create_now.

### Outcome B — execution failure

Validation:

```text
usable = false
recommendation = retake
issue = camera shake
```

Expected:

```text
retry_shot
```

if substantially the same Shot remains appropriate.

### Outcome C — usable but Beat weak

Validation:

```text
usable = true
recommendation = accept
```

but Director context indicates the Beat remains partial.

Expected:

- potentially `capture_shot`;
- new Shot may serve the SAME Beat;
- do not misuse `retry_shot`.

### Outcome D — enough already

Existing successful captures sufficiently cover the Story.

Expected:

```text
create_now
```

even if unused planned Shots remain.

---

# 14. Minimum-Capture Evaluation

Create fixtures where different quantities of footage are sufficient.

Example:

```text
Case A:
1 exceptional clip is enough.

Case B:
2 clips provide complete Story coverage.

Case C:
third Beat remains materially unfulfilled.
```

Measure:

- number of requested captures;
- redundant capture rate;
- unnecessary retry rate;
- correct early-stop behavior.

The desired system is not the one requesting the fewest clips under all
conditions.

It is the one requesting:

> the smallest amount of footage sufficient for a good Story.

---

# 15. Baselines

Director evaluation should include meaningful baselines.

## Baseline A — Generic LLM

Provide:

- user intent;
- scene description.

Ask:

> Suggest three shots.

This measures whether our architecture improves over simple prompting.

## Baseline B — Intent-only Director

No SceneUnderstanding.

Measures scene-understanding contribution.

## Baseline C — No Beats

Generate shots directly from intent + scene.

Measures whether Concept → Beats → Shots improves coherence.

## Candidate — Full DIRECT

```text
CreativeIntent
+
SceneUnderstanding
+
Concept → Beats → Shots
+
Director loop
```

The product architecture should earn its complexity.

---

# 16. Human Evaluation

Human reviewers should evaluate blinded outputs when practical.

Do not tell reviewers:

- model name;
- prompt version;
- architecture variant.

Ask concrete questions rather than:

> Which AI is smarter?

Examples:

> Which recommendation would be easier to follow?

> Which better uses this particular location?

> Which would more likely produce footage matching the requested mood?

> Which gives you an idea you would not have thought of yourself?

For pairwise experiments, preference comparison may be more reliable than
absolute scoring.

---

# 17. Pairwise Evaluation

For important experiments compare A vs B directly.

Example:

```text
A:
Director without SceneUnderstanding

B:
Director with SceneUnderstanding
```

Reviewer chooses:

```text
A better
B better
roughly equal
```

and selects reasons:

- more scene-specific;
- more creative;
- easier to execute;
- better intent match;
- safer/more feasible;
- less redundant.

Pairwise evaluation is preferred for deciding whether a proposed system
change materially improves quality.

---

# 18. Automated LLM Judge

An LLM judge may evaluate:

- intent alignment;
- scene specificity;
- concept coherence;
- Beat coherence;
- instruction clarity;
- redundancy.

The judge must receive:

- source CreativeIntent;
- source SceneUnderstanding;
- Director output;
- explicit rubric.

Do not ask:

> Is this good?

Ask rubric-specific questions.

Automated judging should be periodically calibrated against human review.

---

# 19. Deterministic Checks

Some properties should not require an LLM judge.

Examples:

```text
every shot.beat_id exists
every Beat has purpose
every Shot has instruction
capture_shot contains Shot
create_now does not require Shot
no unknown enum
no duplicate IDs
```

Additional heuristic checks may detect:

- excessively long instructions;
- too many Beats;
- excessive requested captures.

Heuristics should flag review rather than automatically define creative
failure unless the constraint is truly hard.

---

# 20. Real-World Capture Evaluation

Synthetic fixtures are necessary but insufficient.

Test on real phones in real environments.

Initial field set:

- home;
- office;
- cafe;
- urban street;
- park;
- scenic overlook;
- hike/trail;
- social gathering.

For each session record:

```text
intent
scene scan
Director outputs
captures
ValidationResults
Director decisions
final Story
```

Then review the entire session.

---

# 21. End-to-End Outcome Evaluation

Ultimately evaluate the finished Story.

Questions:

1. Does it match the user's requested intent?
2. Does it feel coherent?
3. Does it exploit the environment?
4. Does it contain useful visual variety?
5. Does it feel generic?
6. Was the capture effort reasonable?
7. Did Director request unnecessary footage?
8. Did the user understand the directions?
9. Would the user prefer the result over what they would normally shoot?
10. Did Director contribute a meaningful creative idea?

This is Layer 3 and is the closest measure of actual product value.

---

# 22. User-Value Question

The most important qualitative question for early testing is:

> Did Story suggest something worth shooting that you probably would not
> have thought of yourself?

Possible answers:

```text
Yes, definitely
Somewhat
Not really
```

Follow with:

> Was it easy enough to actually capture?

This separates:

```text
creative value
```

from:

```text
execution burden
```

Both are required.

---

# 23. Evaluation Dataset Structure

Store fixtures outside prompts.

Suggested structure:

```text
evals/
├── creative_intent/
│   ├── text_cases/
│   └── reference_cases/
│
├── scene_understanding/
│   ├── office/
│   ├── urban/
│   ├── mountain/
│   ├── cafe/
│   └── social/
│
├── story_director/
│   ├── initialize/
│   ├── contrastive_scene/
│   ├── contrastive_intent/
│   ├── loop/
│   └── minimum_capture/
│
└── end_to_end/
```

Each fixture should have stable IDs.

---

# 24. Evaluation Case Shape

Conceptual example:

```json
{
  "id": "director_tmb_scale_001",

  "creative_intent": "...",

  "scene_understanding": "...",

  "capture_constraints": "...",

  "expected_properties": [
    "uses mountain/person scale contrast",
    "does not require risky movement",
    "instruction executable by ordinary phone user"
  ],

  "forbidden_properties": [
    "walking backward near edge",
    "generic wide-medium-close sequence"
  ]
}
```

Avoid requiring exact expected prose.

We are evaluating semantic behavior, not string matching.

---

# 25. Regression Set

When a meaningful failure is discovered, convert it into a permanent
fixture.

Example:

Director recommends:

> Walk backward while filming your partner beside a cliff.

After fixing:

```text
eval fixture:
mountain_edge_backward_motion_regression
```

Future prompt/model changes must not reintroduce it.

The regression suite should grow from actual failures.

---

# 26. Failure Taxonomy

Use stable failure labels.

Initial taxonomy:

```text
INTENT_MISREAD
INTENT_INVENTED

SCENE_HALLUCINATION
SCENE_MISSED_OPPORTUNITY
SCENE_CONSTRAINT_MISSED

GENERIC_DIRECTION
WEAK_CONCEPT
BEAT_INCOHERENCE
SHOT_BEAT_MISMATCH

INSTRUCTION_VAGUE
INSTRUCTION_TOO_COMPLEX

PHYSICALLY_INFEASIBLE
UNSAFE_DIRECTION

REDUNDANT_CAPTURE
PREMATURE_CREATE
FAILURE_TO_STOP

WRONG_RETRY
WRONG_RESCAN

STRUCTURED_OUTPUT_FAILURE
```

This makes evaluation results actionable.

---

# 27. Model / Prompt Experiment Tracking

Every eval run should record:

```text
component
model
provider
prompt_version
schema_version
fixture_set_version
temperature / relevant inference configuration
timestamp
```

Results should be reproducible enough to compare iterations.

---

# 28. Cost and Latency

Quality is primary, but record:

```text
latency
input size
output size
token usage
image count
estimated/request cost
retry count
```

Do not optimize cost before establishing useful quality.

But reject architectures whose quality gain is negligible relative to major
latency/cost complexity.

---

# 29. Initial Quality Gates

Do NOT pretend we know statistically meaningful production thresholds yet.

For Milestone C, use practical development gates.

Hard gates:

- schema validity;
- referential integrity;
- no known unsafe-direction regression;
- no fabricated plan on model failure.

Quality gates:

- clearly scene-specific direction in the majority of curated cases;
- clear sensitivity to materially different intents;
- instructions consistently executable by ordinary phone users;
- no systematic generic wide/medium/close template;
- Director demonstrates correct retry-vs-new-shot behavior;
- Director demonstrates early `create_now` in fixtures where enough
  material exists.

Before external launch, replace these qualitative development gates with
measured thresholds from a larger eval set.

---

# 30. Milestone-C Evaluation Sequence

Run evaluation in this order.

## Phase 1 — Offline component fixtures

Creative Intent.

Scene Understanding.

Director initialize.

Goal:

> basic quality and contract correctness.

## Phase 2 — Contrastive Director evaluation

Same intent / different scenes.

Same scene / different intents.

Goal:

> prove Director actually uses both upstream signals.

## Phase 3 — Director loop simulation

Simulated ValidationResults and capture outcomes.

Goal:

> prove adaptive next-action behavior.

## Phase 4 — Real-device sessions

Use actual iPhone capture flows.

Goal:

> determine whether directions are executable in reality.

## Phase 5 — End-to-end Story evaluation

Generate finished Stories from directed captures.

Goal:

> determine whether DIRECT improves the actual output.

Do not jump directly to large-scale field testing before the offline
fixtures expose obvious failures.

---

# 31. What Must Be Proven Before Calling DIRECT Successful

DIRECT is not successful merely because:

```text
camera works
+
API works
+
model responds
+
JSON validates
```

The milestone must demonstrate evidence for all of the following:

### Understanding

Story captures the user's intended creative direction.

### Grounding

Story understands enough of the actual environment to avoid generic
direction.

### Creativity

Story contributes useful visual ideas beyond obvious capture behavior.

### Coherence

Shots collectively serve a clear StoryConcept.

### Feasibility

An ordinary user can execute the directions with a phone.

### Adaptation

Story reacts intelligently to actual capture results.

### Efficiency

Story stops asking for footage when enough exists.

### Outcome

The resulting Story is meaningfully improved by the directing process.

That is the bar for DIRECT.

---

# 32. Open Evaluation Questions

Keep measurable:

1. Does SceneUnderstanding materially improve Director quality over raw
   scene labels?

2. Does giving Director raw frames improve quality beyond structured
   SceneUnderstanding?

3. Does Concept → Beats → Shots outperform direct Shot generation?

4. How many Beats are useful for different target Story durations?

5. Does planning all Shots up front improve coherence or unnecessarily
   constrain adaptation?

6. How often should Director choose `create_now` earlier than the initial
   plan implies?

7. Does `BeatProgress.supporting_asset_ids` improve Edit Planner quality?

8. Which model provides the best creative-quality / latency / cost tradeoff?

9. How well do LLM-judge ratings correlate with human preference?

10. Do users actually capture better footage with Director than without it?

11. Do users perceive the creative suggestions as valuable enough to justify
    the extra interaction?

These questions should drive experiments rather than architectural
assumptions.

---

# 33. Definition of Done — Evaluation Infrastructure

Evaluation infrastructure is ready for real Director development when:

- stable fixture format exists;
- Creative Intent fixtures exist;
- Scene Understanding fixtures exist;
- Director initialize fixtures exist;
- same-intent/different-scene fixtures exist;
- same-scene/different-intent fixtures exist;
- Director-loop fixtures exist;
- deterministic schema checks run automatically;
- pairwise comparison can be recorded;
- human-review results can be stored;
- model/prompt/schema versions are captured;
- failure taxonomy is recorded;
- regression fixtures can be added easily.

---

# 34. Definition of Done — Milestone C Intelligence

Milestone C intelligence is ready to advance when:

- Creative Intent works on representative inputs;
- Scene Understanding is grounded and useful to Director;
- Director produces scene-specific concepts and executable directions;
- Director meaningfully responds to different CreativeIntents;
- Concept → Beats → Shots demonstrates useful coherence;
- Director loop correctly adapts to representative capture outcomes;
- minimum-sufficient capture behavior is demonstrated;
- safety regressions pass;
- real-device testing shows instructions are practically executable;
- end-to-end Stories demonstrate meaningful creative value.

The purpose of evaluation is not to prove that the architecture is correct.

It is to discover where the architecture is wrong quickly enough to change
it.
