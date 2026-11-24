# Story Specs

## Sources of Truth

| What | Where |
|---|---|
| Product behavior and principles | [`production/story-production.md`](./production/story-production.md) |
| MVP scope and build sequence | [`implementation-plan/mvp-build-plan.md`](./implementation-plan/mvp-build-plan.md) |
| Shared data contracts (authoritative) | [`implementation-plan/02-core-story-schema.md`](./implementation-plan/02-core-story-schema.md) |
| All milestones & experiments (index) | [`implementation-plan/00-milestones-and-experiments-index.md`](./implementation-plan/00-milestones-and-experiments-index.md) |

## Current Milestone

**Alpha 0.1** — DIRECT + EDIT walking skeleton with mocked AI, running end-to-end on a physical iPhone.

See `mvp-build-plan.md` for the acceptance criteria and build sequence.

## Rule

Do not implement capabilities from `production/story-production.md` unless they are explicitly included in `mvp-build-plan.md`. The production spec is the long-term vision. The build plan is what gets built now.

## Component Specs

| # | Spec | One line |
|---|---|---|
| [01](./implementation-plan/01-project-foundation.md) | Project Foundation | iOS shell, navigation, persistence, backend skeleton |
| [02](./implementation-plan/02-core-story-schema.md) | Core Story Schema | **Authoritative data contracts — read this first** |
| [03](./implementation-plan/03-creative-intent.md) | Creative Intent | Template + text + reference → `CreativeIntent` |
| [04](./implementation-plan/04-scene-understanding.md) | Scene Understanding | Scan video → `SceneUnderstanding` |
| [05](./implementation-plan/05-story-director.md) | Story Director | Core AI: intent + scene → concept + shot plan |
| [06](./implementation-plan/06-asset-understanding.md) | Asset Understanding | Clip analysis → usable range, roles, quality |
| [07](./implementation-plan/07-camera-capture.md) | Camera Capture | Real-time guided capture driven by `StoryPlan` |
| [08](./implementation-plan/08-shot-validation.md) | Shot Validation | PASS/RETRY per shot, PASS-biased, < 3s |
| [09](./implementation-plan/09-edit-planner.md) | Edit Planner | Story Reconciliation → `EditPlan` |
| [10](./implementation-plan/10-media-engine.md) | Media Engine | Deterministic AVFoundation pipeline → MP4 |
| [11](./implementation-plan/11-direct-flow.md) | DIRECT Flow | End-to-end "help me shoot something" UX |
| [12](./implementation-plan/12-edit-flow.md) | EDIT Flow | End-to-end "I already have footage" UX |
| [13](./implementation-plan/13-evaluation.md) | Evaluation | Dataset, rubric, user test protocol |
