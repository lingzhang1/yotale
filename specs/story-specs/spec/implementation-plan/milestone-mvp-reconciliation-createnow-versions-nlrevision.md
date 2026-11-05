# Milestone — MVP Roadmap Reconciliation: Create Now · Versions · Natural-Language Revision

Status: **AUDIT + ARCHITECTURE PROPOSAL — awaiting owner approval. No implementation, nothing pushed/deployed.**
Owner: lingzhang · Date: 2026-10-13 · Method: code-grounded audit (3 parallel read-only subagents), file:line verified.

> Three product capabilities audited against the ACTUAL code (not old specs): (1) Create Another Version
> with editorial diversity, (2) Natural-Language Revision, (3) complete Create Now entry flow.
> Headline: all three are **composition/wiring problems over strong existing foundations**, not missing
> engines. Only Natural-Language hard-directives needs genuinely new contract + validator work.

---

## 1. Code-grounded current status

### A. Create Another Version
- iOS button exists & always available — `StoryResultView.swift` → `recreate()`. Re-create is ADDITIVE (never overwrites; prior outputs kept).
- **Version lineage already modeled** — `GeneratedOutputModel.versionId / parentVersionId / operationType / editPlanJSON` (`Models.swift:310-313`). `operationType` enumerates `"original" | "change_music"` with `"another_version"` reserved as a **comment only** (`Models.swift:301`) — not wired.
- **ROOT CAUSE of near-identical versions:** the plan is a pure deterministic function of unchanged inputs. Three sources: (1) **`temperature=0.0`** on every model call (`edit_planner/__init__.py:621,646`); (2) **no prior-output input** — `EditPlanInputs` has no prior/variation/avoid field; (3) **idempotency short-circuit** — same `operation_id` → `UUIDv5` → same DynamoDB job → byte-identical cached plan returned (`edit_plan_jobs/__init__.py`). Happy path mints a fresh op_id per version (cleared on completion), so (1)+(2) dominate; op_id reuse is a fragility on the poll-timeout recovery path.
- Change Music (Operation A) is fully implemented; Create-Another-Version (V2-b) is **design-only in spec, absent in code** beyond the lineage substrate.

### B. Natural-Language Revision
- **No user-text revision path exists anywhere in shipping code.** No endpoint/DTO field/UI control/planner input takes a free-text directive to re-cut a generated Story.
- The free-text box (`CreativeDirectionView.swift`) feeds **CreativeIntent at Story START**, not editing — never reaches `/v1/edit-plan*`.
- Customize UX is **structured only** (duration / sound / editing approach / editorial_mode) — the only "broader/faster" lever is the `editorial_mode` enum.
- `creative_brief` is plumbed end-to-end but its value is a **hardcoded constant** (`StoryMultimodalPlanning.creativeBrief`, version `shortform_mvp/1`), not user text.
- Design recovered from `12-edit-flow.md`: a "Try a different direction → variation hint" card — unimplemented. v2a/v2b are deterministic cut-refinement, NOT user directives.

### C. Create Now
- **No wired entry point.** Home "Create now" card is `enabled: false` in both layouts (`HomeView.swift:55,97`), commented "frozen future path (DIRECT-one-off) with no persistent-Story backing." Only "Start a Story" is wired.
- Terminology trap: `SceneScanFlowView.swift` `case .createNow` is a **Director decision outcome** ("you have enough, Done"), not the Home product.
- Current real route to a video: describe→feel→context→blueprint wizard → StoryHome → shoot/skip-scan → capture → **async AU wait** → Create → duration → music → render = **~10+ decisions across 5 screens + an AU wait**. The `11-direct-flow.md` target was **≤2 creative decisions**.

## 2. Missing capabilities
- **A:** version-aware planning input (prior-plan / avoid-set); intentional determinism break; `operationType="another_version"` wiring.
- **B:** directive DTO/field; include/exclude/order-pin/opening/ending inputs; a "revise this committed plan + instruction" entry point; validator predicates for HARD constraints; a revision UX surface.
- **C:** a Home entry point; an ephemeral/implicit-Story create path; a decision-collapsed flow that threads capture→AU→plan→render; a launch-time resume of an in-flight render.

## 3. Proposed architecture (for approval)

### A. Version-aware planning (no random shuffle, no fixed templates)
Add ONE optional additive input to `EditPlanInputs` / the request + multipart form: `prior_plans` (or a compact `avoid: {moment_ids, source_ranges, opening_moment_id}` derived client-side from the parent chain's `editPlanJSON`). Inject it into the **USER message only** (same seam as `creative_brief`), frozen `edit_plan/5.2` system body untouched. Diversity is EVIDENCE-DRIVEN: the model is told what the prior version did and asked for a meaningfully different valid edit — not randomized. Keep `temperature=0.0` (prior-plan context is the lever); optionally allow a bounded temp bump for the variation op only. iOS sets `operationType="another_version"`, `parentVersionId=source.versionId`, decodes parent `editPlanJSON`. No new endpoint.

### B. Natural-Language Revision (bounded V1)
Reuse the proven **critique→revise→validate** backbone. Two directive classes:
- **Soft preferences** (change opening/ending vibe, broader/faster, creative tone): carry as text into a `_build_revision`-style call seeded with the EXISTING committed plan; gate on `validate_plan`. Nearly free — mostly wiring.
- **Hard constraints** (include/exclude a Moment, pin first/last, pin relative order, preserve a continuous action): a STRUCTURED `directives` object parsed from the user's NL, enforced by **new deterministic `validate_plan` predicates** (required-moment present, forbidden-moment absent, first/last asset_id pinned, order respected). A revision failing a hard predicate is rejected (retry/repair), never silently ignored. Expose a "revise this base_plan with these directives" entry point (today `_build_revision` is only reachable inside one `generate()` call).

### C. Create Now (smallest complete)
Pure composition — reuse Asset Understanding, music planning, async Edit Planning, rendering AS-IS:
1. Flip the Home card to a real entry point.
2. Create an **ephemeral/implicit `StoryModel`** behind the scenes (everything downstream already takes a `StoryModel`).
3. Collapse decisions to ≤2: default intent, recommended duration, recommended-or-no music.
4. One continuous "Creating…" that threads capture → AU wait → plan → render, instead of returning to a gated Home.
5. Already satisfied: skip-scan, Concept Card, retry, Result save/share.

## 4. Shared foundations (all three reuse)
Async Edit Planning (`EditPlanJobClient`, idempotent on `operation_id`); the frozen `validate_plan` deterministic gate; the `creative_brief` USER-message injection seam; the version-lineage data model; the `StoryCreationCoordinator` 8-state machine; local-first SwiftData persistence (`StoryModel` + `GeneratedOutputModel.editPlanJSON`). **No frozen contract (EditPlan/2, edit_plan/5.2 system body) is reinterpreted — all additions enter via optional request fields / the USER message.**

## 5. Required contracts & versioning
- **A:** `EditPlanInputs` + `EditPlanRequest` + `/v1/edit-plan-jobs` form gain optional `prior_plans`/`avoid` (default none ⇒ unchanged). Additive.
- **B:** optional `revision_directive: str` + optional `base_plan: dict` + structured `directives` object; new `validate_plan` predicates. Additive; bump the request/DTO minor, keep EditPlan/2 output contract frozen.
- **C:** NONE — runs on existing contracts.
- Versioning: `GeneratedOutputModel` lineage already migration-safe; extend `operationType` vocabulary (`another_version`, `edit_ai`) — already reserved.

## 6. UX implications
- **A:** Result screen's existing version list carries derived versions; no new screen.
- **B:** NEW revision surface (recover the `12-edit-flow` "different direction" card into a bounded directive input); must distinguish hard vs soft and SHOW when a hard directive is infeasible (never silent).
- **C:** new Home entry + a decision-collapsed Creating flow; honest states already built.

## 7. Recommended implementation order
1. **Create Now (C)** — highest value / lowest risk, zero contract change, pure reuse. Unblocks the headline MVP entry.
2. **Create Another Version (A)** — one additive field + prior-plan injection; fixes the visible "identical version" complaint.
3. **Natural-Language Revision (B)** — largest surface (contract + validator + UX); do soft-preferences first, hard-directives second.

## 8. MVP vs post-MVP
- **MVP:** C (full), A (prior-plan diversity), B-soft (creative preferences) + B-hard include/exclude/opening/ending/order.
- **Post-MVP:** B preserve-continuous-action tied to AU action spans (depends on `CreativeRefinementV2b` device-acceptance); temperature-tuned variation; multi-segment-per-Moment planning.
- **OUT OF SCOPE (owner):** advanced timeline editing, generative effects, large-library indexing.

## 9. Acceptance criteria
- **A:** regenerate a version → measurably different Moment set / order / source ranges vs parent (not identical); prior version preserved; explicit user constraints honored; device-verified on girl + hiking.
- **B:** each V1 directive produces the intended change; HARD directives deterministically validated (include present / exclude absent / opening/ending/order pinned); infeasible/conflicting directives surfaced, never silently dropped; device-verified.
- **C:** launch → generated Story in ≤2 creative decisions; scan skippable; reuses AU/music/async-plan/render (no duplication); in-flight Story persisted + recovered on relaunch.

## 10. Updated roadmap / spec references
- Supersedes/relates: `milestone-me-music-library-change-music-versioning.md` (versioning substrate), `12-edit-flow.md` + `milestone-v2a/v2b-creative-editing-*.md` (revision design), `11-direct-flow.md` + `milestone-c3-direct-flow-audit.md` (Create Now definition).
- Register in `00-milestones-and-experiments-index.md` (done).

## Phase 5 — Roadmap amendment (separation)
- **Completed capabilities:** async Edit Planning (dev-accepted); Change Music versioning; structured Customize UX; CreativeIntent/Director/AU/coverage/guide/music pipeline; the version-lineage data model; the critique→revise→validate backbone.
- **MVP implementation gaps:** Create Now entry flow (C); version-aware planning input (A); NL revision soft+hard (B).
- **Release blockers:** C (no wired entry = no MVP "create now"); A root-cause (identical versions is a visible quality bug); prod Opus quota headroom (separate rollout doc).
- **Post-MVP enhancements:** continuous-action preservation; temperature-tuned variation; multi-segment planning.
