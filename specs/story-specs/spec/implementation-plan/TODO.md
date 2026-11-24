# YoTale — Post-Beta AI Development Roadmap

**Updated:** October 26, 2026  
**Status:** Planning / Deferred  
**Purpose:** Preserve the AI improvements we have discussed so they are not forgotten after the first TestFlight beta.

---

## 1. Current AI foundation

The following capabilities have already been implemented and tested in development.

| Capability | Status |
|---|---|
| Rich Editorial AU v2 — visual and narrative candidates | Completed |
| Visual peak and candidate interval identification | Implemented; approximate accuracy |
| AU timestamp provenance and temporal grounding | Completed |
| EditPlan v5.3 — Highlights and Full Story | Completed in dev |
| Mode-aware duration recommendations | Completed |
| AI-guided Original, Revise, and Explore | Completed in dev |
| Music-aware planning and existing sound preferences | Implemented |
| Complete visual contact-sheet evidence | Implemented |

**Still scheduled before beta (not counted as post-beta work):**

- AU and My Music synchronization durability.
- My Music preview playback.
- Reusable AU frame caching and editorially aligned planner images (P1-F).
- Elimination of unnecessary pre-planning source-video downloads where feasible.
- Gemini AU reliability/latency fixes.
- Final TestFlight compatibility and acceptance.

Do not duplicate these projects in the post-beta backlog unless a follow-up quality improvement is specifically identified.

---

# 2. Post-Beta AI Backlog

## AI-01 — Speech and Dialogue Understanding for Full Story

**Priority:** P0 — Highest post-beta AI priority  
**Status:** Not implemented  
**Primary benefit:** Narrative quality

### Problem

AU v2 currently analyzes sampled visual frames, but it cannot understand the actual contents of conversations.

For example, during a trip to Egypt, the user may:

- Talk with local residents.
- Negotiate in a market.
- Joke with friends.
- Explain an interesting experience.
- React verbally to something unexpected.

Full Story should be able to recognize which conversations are meaningful and preserve them in the final film.

### Planned improvements

- Speech-to-text transcription.
- Multilingual speech recognition.
- Speaker diarization or speaker-turn identification.
- Timestamped utterances.
- Identification of meaningful dialogue.
- Dialogue relevance to the overall Story.
- Important emotional reactions.
- Reusable audio-understanding evidence.
- Integration with narrative candidates.

### Acceptance criteria

Full Story can recognize meaningful spoken events and preserve relevant conversations without cutting sentences in the middle.

---

## AI-02 — Audio-Aware Editing and Clip Boundaries

**Priority:** P0  
**Status:** Not implemented  
**Depends on:** AI-01

### Problem

Current planning can preserve source audio, but it has limited understanding of where meaningful sounds, speech, and reactions begin and end.

### Planned improvements

- Detect important ambient sound events.
- Identify conversation boundaries.
- Preserve complete utterances.
- Recognize laughter, applause, reactions, and environmental sounds.
- Avoid cutting meaningful natural audio prematurely.
- Use natural audio as an editorial storytelling element.
- Improve music ducking and transitions around speech.
- Coordinate video cuts with audio-event boundaries.

### Acceptance criteria

The editor can preserve a meaningful verbal or environmental event without awkward audio truncation, while balancing original sound and background music.

---

## AI-03 — Advanced Narrative Assembly

**Priority:** P0  
**Status:** Basic narrative planning exists; advanced reasoning not implemented  
**Depends on:** AI-01 and richer story evidence

### Problem

Full Story can prioritize AU narrative candidates, but a compelling documentary needs more than selecting longer clips.

It needs to understand how individual events relate to the larger experience.

### Planned improvements

- Identify important events across multiple Moments.
- Recognize event relationships and progression.
- Distinguish setup, development, turning point, and resolution.
- Find meaningful human interactions.
- Recognize emotional changes.
- Identify narrative gaps.
- Avoid repetitive contextual footage.
- Combine visual and audio understanding.
- Support thematic rather than strictly chronological sequences when appropriate.
- Build a coherent story using incomplete or unordered source footage.

### Acceptance criteria

A Full Story feels like a meaningful account of an experience, not a collection of clips arranged chronologically.

---

## AI-04 — Precise Visual Peak and Cut Boundary Refinement

**Priority:** P1 — High  
**Status:** Approximate peaks implemented; precise refinement not implemented  
**Depends on:** P1-F reusable visual evidence

### Problem

AU v2 can identify interesting actions but sometimes misplaces the actual payoff.

Our dress-turn evaluations showed that the model could receive the correct visual frame and still report an earlier peak timestamp.

### Planned improvements

- Distinguish action onset, progression, apex, and completion.
- Improve frame-level peak localization.
- Use before/apex/after image sequences.
- Associate candidate events with actual frame IDs.
- Refine source start/end boundaries.
- Avoid premature cuts.
- Identify multiple visual payoffs within the same Moment.
- Support bounded local refinement around uncertain candidates.

### Acceptance criteria

Highlights reliably preserves the important visual payoff, including complete face reveals, expressive movement, and scenic reveals.

**Important:** Model-generated timestamps remain advisory until validated against real source evidence.

---

## AI-05 — Duration-Aware and Content-Adaptive Frame Sampling

**Priority:** P1 — Conditional  
**Status:** Not implemented  
**Depends on:** P1-F and evidence of missed actions

### Problem

AU currently analyzes 24 uniformly spaced frames per Moment.

This is often adequate for short clips but may miss brief events in longer videos.

However, the earlier IMG_9091 failure was caused by model temporal reasoning, not missing frames.

### Planned improvements

- Duration-aware frame counts.
- Scene-change detection.
- Motion-aware sampling.
- Higher sampling density around complex actions.
- Preserve whole-video coverage.
- Bounded frame budgets.
- Optional selective temporal refinement.
- Versioned sampling policies.

### Acceptance criteria

Adaptive sampling detects important events that uniform sampling actually missed, with a measured improvement that justifies additional latency and model cost.

**Do not increase frame counts merely because videos are longer.**

---

## AI-06 — Native Video Understanding

**Priority:** P2 — Research  
**Status:** Not implemented  
**Depends on:** Provider capability and quality evaluation

### Problem

A collection of static frames may not fully capture motion, timing, gesture, or causality.

### Planned improvements

- Evaluate native video-input models.
- Compare temporal understanding against sampled-frame AU.
- Analyze movement continuity.
- Improve action recognition.
- Compare candidate peak accuracy.
- Evaluate combined video/audio understanding.
- Measure inference cost and latency.

### Acceptance criteria

Native-video inference demonstrates a meaningful quality improvement over the existing frame-based approach at an acceptable operational cost.

This is an experimental alternative, not an automatic replacement for AU v2.

---

## AI-07 — More Intelligent Highlights Editing

**Priority:** P1  
**Status:** Basic Highlights strategy implemented; advanced intelligence deferred  
**Depends on:** AI-04 and richer visual evidence

### Planned improvements

- Better visual-payoff ranking.
- Stronger opening-hook selection.
- Shot composition diversity.
- Expressive movement recognition.
- Avoidance of visually repetitive scenes.
- Better sequencing between contrasting shots.
- Recognize complementary angles and actions.
- Improve transition choices.
- More deliberate emotional and visual pacing.
- Select the best subrange from longer source clips.

### Acceptance criteria

Highlights selects the footage a skilled human editor would most likely choose, rather than simply choosing high-confidence AU candidates or scenic imagery.

---

## AI-08 — Advanced Music-Aware Editing

**Priority:** P1  
**Status:** Basic music-aware planning exists; advanced capabilities deferred

### Planned improvements

- Music beat and phrase analysis.
- Align meaningful visual payoffs with musical changes.
- Intelligent pacing across song sections.
- Use buildup, drops, and emotional transitions.
- Improve transitions between natural audio and music.
- Avoid monotonous beat-synchronized cutting.
- Adapt musical editing differently for Highlights and Full Story.
- Better music selection based on narrative and mood.

### Acceptance criteria

Cuts and visual payoffs feel intentionally coordinated with the soundtrack, while the system preserves creative freedom rather than cutting mechanically on every beat.

---

## AI-09 — Better AI Revision and Creative Exploration

**Priority:** P1  
**Status:** Original/Revise/Explore implemented; advanced interaction deferred

### Planned improvements

- More reliable natural-language instruction interpretation.
- Relative source references and event-based directives.
- "Make the beginning more exciting."
- "Use more conversations from the market."
- "Keep the same opening but change the ending."
- "Give me a completely different interpretation."
- Better preservation of unaffected sections.
- Explain unmet instructions clearly.
- More efficient partial replanning.
- Reuse existing AU, EditPlan, and music evidence.
- Compare alternate versions meaningfully.

### Acceptance criteria

Users can iteratively direct their videos without unintended wholesale changes, unnecessary AI recomputation, or losing previous versions.

---

## AI-10 — AI Story Director and Shooting Guide Improvements

**Priority:** P1 — Product differentiation  
**Status:** Initial Guide capabilities implemented; advanced direction deferred

### Product vision

YoTale should eventually act as an AI creative director **before and during filming**, not merely edit footage afterward.

### Planned improvements

- Scene-specific shot suggestions.
- Camera movement recommendations.
- Better guidance for capturing short-form sequences.
- Event-aware and location-aware shot planning.
- Suggested opening, progression, and ending shots.
- Detect missing coverage.
- Guide users toward complementary footage.
- Improve live capture guidance.
- Suggest visual storytelling sequences based on the user's intended result.
- Turn an idea into a practical shooting plan for a short, engaging social video.

### Acceptance criteria

Users can follow the Guide to capture footage that is easier to assemble into a compelling video, without needing professional cinematography knowledge.

---

## AI-11 — Editorial Quality Evaluation and Feedback

**Priority:** P1  
**Status:** Manual evaluation exists; systematic evaluation deferred

### Planned improvements

- Standardized evaluation video datasets.
- Ground-truth visual-event intervals.
- Human preference comparisons.
- Highlights selection-quality benchmarks.
- Full Story narrative-quality benchmarks.
- Source trim accuracy.
- Audio continuity checks.
- Model failure classification.
- Regressions across prompt and model versions.
- Per-stage latency and cost tracking.
- Evaluate rendered MP4s, not just plan JSON.
- Optional model-assisted critique with human validation.

### Acceptance criteria

We can determine whether a planner, AU, or provider change actually improves final video quality using repeatable evidence.

---

## AI-12 — AI Provider Quality and Cost Optimization

**Priority:** P2  
**Status:** Direct OpenAI/Gemini routing exists; systematic optimization deferred  
**Depends on:** AI-11

### Planned improvements

- Compare providers by capability.
- AU model quality/latency comparisons.
- EditPlan model quality comparisons.
- Prompt/context compression.
- Prompt caching.
- Reduce unnecessary critique/repair calls.
- Reuse source understanding across versions.
- Optimize frame budgets.
- Optimize image resolution.
- Reduce model input token consumption.
- Measure cost per completed video.
- Improve fallback latency while preserving provider access policies.

### Acceptance criteria

Lower cost and latency without materially degrading rendered-video quality.

Provider-access denials must never trigger an unauthorized fallback.

---

## AI-13 — AI Evidence Reuse and Incremental Planning

**Priority:** P2  
**Status:** Foundational reuse exists; advanced optimization deferred  
**Depends on:** P1-F

### Planned improvements

- Cache reusable editorial interpretation.
- Version and invalidate analysis independently from frame pixels.
- Reuse unchanged visual evidence across multiple Stories.
- Avoid reanalyzing unchanged Moments.
- Incrementally update planning when only a subset of source footage changes.
- Reuse previously computed musical structure.
- Efficient Explore generation.
- Minimize repeated multimodal context in targeted Revise.
- Evaluate reusable intermediate planning representations.

### Acceptance criteria

Repeated generation and revision reuse validated source evidence whenever possible, without returning stale or mismatched analysis.

---

# 3. Recommended post-beta development order

| Order | Work | Reason |
|---|---|---|
| 1 | AI-01 Speech/dialogue understanding | Biggest remaining Full Story limitation |
| 2 | AI-02 Audio-aware trimming | Makes conversation-driven stories usable |
| 3 | AI-03 Advanced narrative assembly | Improves emotional and event coherence |
| 4 | AI-04 Precise visual peak refinement | Improves Highlights source selection |
| 5 | AI-07 Advanced Highlights intelligence | Produces stronger short-form results |
| 6 | AI-08 Music-aware editing | Improves rhythm and emotional impact |
| 7 | AI-09 Revision/Explore intelligence | Improves iterative creative control |
| 8 | AI-10 AI Story Director | Differentiates capture-to-edit experience |
| 9 | AI-11 Quality evaluation framework | Supports repeatable quality decisions |
| 10 | AI-05 Adaptive sampling | Implement only with demonstrated coverage gaps |
| 11 | AI-13 Incremental inference/evidence reuse | Reduce repeated generation work |
| 12 | AI-12 Cost/provider optimization | Optimize once quality is established |
| 13 | AI-06 Native video understanding | Longer-term research |

These priorities are provisional. Beta feedback should determine which gaps are most damaging to actual user outcomes.

---

# 4. Explicitly deferred, not abandoned

- [ ] Speech transcription and dialogue understanding
- [ ] Speaker-turn and multilingual conversation support
- [ ] Audio-aware story selection and cutting
- [ ] Advanced narrative assembly
- [ ] Precise visual peaks and cut-point refinement
- [ ] Content-adaptive frame extraction
- [ ] Native-video model experiments
- [ ] Smarter Highlights sequencing
- [ ] Music beat/phrase understanding
- [ ] Advanced revision and exploration
- [ ] AI Story Director and capture guidance
- [ ] Repeatable video-quality evaluation
- [ ] AI provider comparisons
- [ ] Prompt/context caching and compression
- [ ] Critique-pass optimization
- [ ] Incremental analysis and planning

---

# 5. Guardrails for future implementation

1. Maintain separate editorial types: **Highlights** and **Full Story**.
2. Editorial type is independent of duration, music, sound, and operation type.
3. Preserve Original, preservation-first Revise, and open-ended Explore semantics.
4. Keep existing output versions and source provenance intact.
5. Use validated source media as technical authority.
6. Treat AU candidate intervals, peaks, and confidence as advisory until independently grounded.
7. Do not sacrifice rendered-video quality solely to reduce latency or model cost.
8. Never reject a technically playable result solely because of subjective creative criteria.
9. Reuse existing ModelGateway and rendering infrastructure where practical.
10. Require real rendered-video evaluation before claiming major improvements.
11. Preserve user privacy, media ownership, access controls, and deletion behavior.
12. Use one scoped branch and protected PR workflow per implementation task.

---

# 6. Beta feedback questions

Collect feedback that helps prioritize future AI work:

- Do users prefer their Highlights edits or Full Story edits?
- What important footage did AI omit?
- Were visually compelling moments cut too early or too late?
- Did Full Story preserve meaningful events and human interactions?
- Did users want the video to preserve specific spoken conversations?
- Was music appropriate, and did cuts feel natural?
- Were revisions faithful to instructions?
- Did alternate versions feel meaningfully different?
- How much manual intervention did users want?
- What footage did users wish they had captured differently?

**Core principle:** After beta, prioritize the improvements that most directly make YoTale produce videos users actually want to keep, share, and revisit—not just improvements that increase AI sophistication.