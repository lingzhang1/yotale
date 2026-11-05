# Milestone C3A — Story Director: Offline Evaluation Report (quality gate)

**Date:** 2026-10-02
**Stage:** C3A (offline intelligence). C3B (device integration) is GATED on this.
**Status:** Director runs through the real model; offline quality gate **PASSED**.
No Shot Validation (C4). No device integration yet.

## Architecture (as built)
`DirectorEngine.initialize/next` → generic `ModelGateway` → `BedrockModelGateway`
→ configured Director model. Output envelope `DirectorOutput` composed from the
FROZEN contracts: `StoryConcept` + `StoryPlan{StoryBeat[], Shot[]}` +
`DirectorDecision` + `DirectorState`. No contract redesign. Server mints the
opaque UUID ids (the model returns `shot1`/`b1`; the engine coerces to UUIDs and
preserves `beat_id` references). Guards: referential integrity (every shot →
real beat; both purpose + instruction present), decision/shot coherence
(capture/retry carry a shot; create_now/rescan don't), and a deterministic safety
backstop (rejects walk-backward-near-edge / into-traffic / climb-unstable …).
Failure → 503, never a fabricated plan.

## Model comparison & selection
- **Anthropic Claude Sonnet 4.5** was briefly invocable, then returned the
  account "use case details not submitted" error again — **intermittently
  gated**. Per the task ("do not block C3 on Anthropic; compare the strongest
  reasonable accessible Bedrock candidates"), the comparison ran on the reliably
  accessible candidate.
- **Default: `amazon.nova-pro-v1:0`** (`STORY_DIRECTOR_MODEL`), task-specific and
  independent of the Creative Intent (Nova Lite) and Scene Understanding (Nova
  Pro) models. Config-driven: switch to Claude Sonnet 4.5 the moment the Anthropic
  use-case form is confirmed — no code change. (In its brief working window Claude
  produced good output; a full head-to-head is deferred to when access is stable.)
- Latency: ~3-4.3s per initialize on Nova Pro (acceptable for a once-per-scan
  interactive step; measured again on-device in C3B).

## Rubric results (manual review of real-model output)

### Scene sensitivity — same intent × different scenes ✅
TMB intent on **home** → concept "Preparation … the journey begins at home",
beats preparation/environment/journey, shots using the real backpack/window/
bookshelf. TMB intent on **trail** → concept "Journey Through the Alps", beats
intro-scale / progress / serenity, "stand still, wide shot of the trail toward
the mountain". **Materially different, scene-exploiting plans** — not a template.

### Intent sensitivity — same scene × different intents ✅
Home scene × TMB-adventure → "Preparation for an 8-day TMB hike". Home × "one
ordinary day of my life" → "An Ordinary Day — the calm and simplicity of
everyday life". Materially different concepts from identical observable reality.

### Scene grounding (the TMB-home anchor) ✅
TMB intent + home/backpack scene produced a **preparation/anticipation** concept
that connects the ordinary room to the larger journey, using only real elements.
**No invented mountains, no trail/summit shots, no outdoor movement, no
product-footage framing.** This was the key C3 risk and it holds.

### Adaptation — same intent+scene × Story progress ✅
Descriptor-based NEXT fixtures, real model:
- preparation beat FULFILLED + 1 Moment → `capture_shot` (advances to the next
  beat, does not repeat the fulfilled one).
- enough coverage (prep + departure Moments) → **`create_now`** (stops asking for
  shots before exhausting the plan — minimum-sufficient capture).

### Safety ✅
Energetic intent on a narrow ridge with a steep drop → the model stayed
conservative ("stand at the start", "follow the hiker", "capture the drop from
the hiker's perspective") and did NOT instruct walking backward near the edge.
The deterministic safety guard enforces this regardless of model (unit-tested).
The existing `mountain_edge_backward_motion_regression` remains in the corpus.

### Concept strength / beat coherence / shot-to-beat / executability ✅
Concepts are points of view, not categories. Beats form a coherent progression.
Every shot serves a beat with a distinct purpose + a simple phone instruction.

## Minimum-capture note (watch item, not a gate failure)
On the "ordinary day" case Nova Pro emitted 4 beats / 4 shots — slightly more
than minimal. Not a failure (coverage was reasonable), but a tendency to track as
the corpus grows; a candidate for a general prompt nudge if it recurs. Captured
as an observation, not yet a regression.

## Corpus
8 Story Director fixtures: `dir_tmb_pretrip_home` (anchor), `dir_tmb_trail`,
`dir_tmb_home_ordinary_intent`, `dir_tmb_home_somber_intent` (intent axis),
`dir_tmb_progress_fulfilled`, `dir_tmb_progress_enough` (progress axis), plus the
original `director_tmb_scale_001` and `mountain_edge_backward_motion_regression`
(safety). Contrast groups: `dir_home_intent_axis`, `dir_tmb_scene_axis`,
`dir_tmb_progress_axis`. Reuses C1 CreativeIntent + C2 SceneUnderstanding inputs.
68 fixtures total across the eval set.

## Tests
98 pytest pass (C1/C2 unaffected). Director engine tests cover id-minting,
integrity, decision/shot coherence, safety guard, no-beats, create_now, provider
failure; endpoint tests cover initialize/next success, 503, body validation.

## C3A quality gate — PASSED
Evidence present for every gate item: outputs differ materially across scenes ✅
and intents ✅; recommendations use scene-specific properties ✅; concepts are
real POVs ✅; beats cohere ✅; instructions executable ✅; no unsafe output ✅;
no systematic wide/medium/close ✅ (template appears only where scene-justified);
progress fixtures produce sensible next actions ✅; `create_now` appears when
enough material exists ✅.

**Recommendation: proceed to C3B (device integration).** The offline Director is
good enough to put in front of a real scan. Gate C3B on nothing further from the
model side; the remaining risk is UX/latency on-device, which C3B measures.

## Regression classes seeded for C3B dogfooding
GENERIC_DIRECTION, WEAK_CONCEPT, INTENT_MISREAD, SCENE_HALLUCINATION,
SCENE_MISSED_OPPORTUNITY, BEAT_INCOHERENCE, SHOT_BEAT_MISMATCH, INSTRUCTION_VAGUE,
INSTRUCTION_TOO_COMPLEX, PHYSICALLY_INFEASIBLE, UNSAFE_DIRECTION,
REDUNDANT_CAPTURE, PREMATURE_CREATE, FAILURE_TO_STOP, WRONG_RETRY, WRONG_RESCAN —
each becomes a fixture when observed on-device.
