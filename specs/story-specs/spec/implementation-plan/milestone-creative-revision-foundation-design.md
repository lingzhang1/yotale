# Milestone — Creative Revision Foundation: Create Another Version + Natural-Language Editing (DESIGN)

Status: **ARCHITECTURE / FREEZE GATE — awaiting owner approval. No production implementation; nothing pushed/deployed.**
Owner: lingzhang · Date: 2026-10-14 · Method: code-grounded re-audit (direct read, file:line verified this session).
Scope: two milestones designed around ONE shared foundation, implemented + validated SEPARATELY. Supersedes the
Versions + NL-revision sections of `milestone-mvp-reconciliation-createnow-versions-nlrevision.md` (Create Now is
NOT in this milestone). No frozen contract (EditPlan/2) or prompt (edit_plan/5.2) is reinterpreted.

---

## 1. Current code-grounded implementation status

Verified in code this session (not inferred from old specs):

**Create Another Version**
- The button EXISTS and is always available — `StoryResultView.recreate()` → `StoryCreationCoordinator.create()`
  (`apps/ios/Story/Story/Features/Create/StoryResultView.swift`). It is ADDITIVE: `persist()` only ever appends a
  new `GeneratedOutputModel` after a successful render; prior versions are never overwritten.
- Version lineage is ALREADY MODELED — `GeneratedOutputModel` carries `versionId`, `parentVersionId`,
  `operationType` ("original" | "change_music"; "another_version" reserved), `sourceMomentIds`,
  `sourceFingerprint`, and `editPlanJSON` (the EXACT executable plan the renderer consumed), plus
  `soundPreferenceRaw` / `musicAssetRef` (`apps/ios/Story/Story/Data/Persistence/Models.swift`).
- So the substrate (lineage + the parent's exact plan on-device) already exists; what is missing is only the
  version-aware planning INPUT and the lineage WIRING on the re-create path.

**Natural-Language Revision** — does not exist anywhere in shipping code. No endpoint, DTO field, UI control, or
planner input takes a free-text editing directive. The `CreativeDirectionView` free-text box feeds
CreativeIntent at Story START, never `/v1/edit-plan*`. `creative_brief` is plumbed end-to-end but its value is a
hardcoded constant (`StoryMultimodalPlanning.creativeBrief`, `shortform_mvp/1`), not user text. The only
breadth/pace lever today is the structured `editorial_mode` enum (highlights|full|custom).

**Shared foundations that already exist and will be reused as-is**
- Async Edit Planning: `/v1/edit-plan-jobs` (submit 202 → poll), `EditPlanJobClient`, idempotent on
  `operation_id`; the worker runs the SAME planning core as the sync endpoints.
- The deterministic executability gate `validate_plan` (`packages/edit_planner/__init__.py`) — the hard,
  authoritative validator; the model never self-certifies.
- The `creative_brief` USER-message injection seam (`_build_user`) and the `critique → revise → validate`
  backbone (`_build_critique` / `_build_revision`), already in the engine but today only reachable INSIDE one
  `generate()` call and gated to multimodal.
- `StoryCreationCoordinator` 8-state machine; `EditPlanRequestBuilder`; `DurationFeasibility` preflight;
  Media Engine; MusicPlan; AU evidence + `MultimodalVisualBudget` contact sheets; GeneratedOutput persistence.
- `EditPlanRequest` is `model_config = ConfigDict(extra="forbid")` — ANY new wire field is a versioned contract
  change, additive and defaulted so an older client is unchanged.

## 2. Root cause of low version diversity

The PRIMARY, established gap is the **absence of a version-aware planning input and an explicit
alternative-edit objective**: the planner is given identical inputs and no instruction to differ, so it has
no reason to produce a different edit. Two secondary contributors:

1. **`temperature=0.0`.** This strongly biases the model toward the same high-probability plan, but model
   output is NOT guaranteed byte-identical — temperature-zero is a strong determinism bias, not a hard
   guarantee. We do NOT rely on, or change, temperature in this increment; the version-aware input is the lever.
2. **Idempotency is correct and must be preserved — it is not a bug to work around.** The async job key
   (`operation_id` + a canonical request fingerprint) exists so that:
   - **Transport recovery** — the SAME `operation_id` with the SAME request snapshot resumes the SAME job
     (never a second inference);
   - **A deliberate new version** mints a NEW `operation_id` (a genuinely different execution);
   - **The same `operation_id` with a CHANGED payload is a CONFLICT**, not a new execution;
   - **Polling never starts another inference.**

   We do NOT alter the fingerprint to "bypass" idempotency. Instead, a deliberate alternative version is a
   first-class new execution (new `operation_id`), and the version-aware `revision_context` is part of the
   request snapshot that the canonical fingerprint already covers — so an identical re-submission still
   resumes, and a genuine new-version request is genuinely new. The old framing ("change the fingerprint so a
   re-plan happens") is WRONG and is removed.

Storytelling mode shows the effect most because it is text-only (no contact-sheet variation to perturb the
inputs), so without a version-aware objective it leans hardest on the same argmax plan.

## 3. Shared architecture recommendation

**One foundation, two operations, no new engine.** Add ONE optional structured input to the planning request —
a `revision_context` object — that both milestones populate differently, and inject it into the **USER message
only** (the proven `creative_brief` seam). The frozen `edit_plan/5.2` SYSTEM body is untouched; `validate_plan`
stays the authoritative gate and gains new deterministic predicates for HARD constraints. The
`critique → revise → validate` backbone is lifted out so a "revise THIS committed plan with THIS instruction"
entry point is reachable (today it only runs inside `generate()`).

Minimum additive request fields (all optional, default none ⇒ today's behavior byte-for-byte):
```
revision_context (optional object, USER-message only; part of the FROZEN request snapshot at submission):
  mode:             "explore" | "revise"
  base_version_id:  id                              # the version the user SELECTED to work from (required
                                                    #   when revision_context is present) — fixes lineage so
                                                    #   constraints follow the selected chain, never a sibling
  prior_edit_summaries: [compact digest]            # EXPLORE: bounded summaries of the selected parent + a
                                                    #   bounded set of relevant recent versions (NOT full plans)
  base_plan:        EditPlan/2 object | ref         # REVISE: the EXACT executable plan of base_version_id, or
                                                    #   an immutable reference the worker reliably resolves —
                                                    #   NEVER a digest substitute (digests are explore-only)
  directives:       { include_moment_ids: [...],    # HARD — validated deterministically (NL V1)
                      exclude_moment_ids: [...],
                      opening_moment_id: id|null,
                      ending_moment_id:  id|null,
                      order_pins: [ [id,id], ... ],
                      preserve_continuous: [moment_id,...] }
  soft_direction:   str|null                        # SOFT — "more cinematic", "faster" (NL V1)
```

Contract rules (amendment §2):
- **base_version_id is explicit.** When `revision_context` is present it names the user-selected version;
  Explore carries bounded `prior_edit_summaries` (selected parent + a bounded relevant-recent set), Revise
  carries the EXACT `base_plan` for `base_version_id` (or an immutable ref the worker resolves) — a digest is
  never a substitute for the exact base plan in Revise.
- **The request snapshot is FROZEN at submission** and `revision_context` is included in the CANONICAL async
  request fingerprint (`payload_fingerprint`). So an identical re-submission under the same `operation_id`
  still resumes the same job (transport recovery), and a changed `revision_context` under the same
  `operation_id` is a CONFLICT — we never mutate the fingerprint to force a re-plan.
- **The context is carried end to end:** DTO validation → job staging → worker loading → planning → critique →
  repair → final validation. Each stage that re-sends the request re-sends `revision_context`.
- The frozen `edit_plan/5.2` SYSTEM body and the EditPlan/2 OUTPUT contract are unchanged; `revision_context`
  is request-only and injected into the USER message. When absent, behavior is byte-for-byte today's.

Why not a separate revision engine: the engine already plans, critiques, revises and validates against the same
schema. A second engine would duplicate the validator and the Media-Engine contract. The required behavior is a
composition over existing components — the gate's bar ("do not introduce a separate revision engine unless
existing components cannot support it") is NOT met.

## 4. Version diversity design (Create Another Version)

- **Evidence, not randomness.** Derive a compact `prior_plans` digest CLIENT-side from the parent chain's
  `editPlanJSON` (already persisted): per prior version — selected `moment_ids`, source ranges, ordering,
  opening + ending moment, shot-duration distribution (count + min/median/max), and the prior creative emphasis
  (sound preference, editorial_mode). Inject it in the USER message with a bounded objective: *"produce a
  meaningfully DIFFERENT yet valid edit from the prior version(s) below — different opening, different ordering
  or source emphasis — WITHOUT dropping required material or padding."* No shuffle, no templates.
- **Determinism lever.** Keep `temperature=0.0` as the baseline (prior-plan context is the primary lever); allow
  an OPTIONAL small temperature bump (e.g. 0.4) for the `mode:"explore"` op ONLY, flag-gated, measured in eval
  before it is a default.
- **Preserve (never varied away):** user duration (CreativeIntent target), sound preferences, any HARD
  directives, continuous-performance spans, source feasibility (validator unchanged), and ALL prior
  GeneratedOutputs (append-only).
- **Lineage wiring:** the re-create path sets `operationType="another_version"`,
  `parentVersionId = source.versionId`, and passes the derived `prior_plans`. Mints a fresh `operation_id` (so
  the idempotency fingerprint differs and a real re-plan happens).
- **Deterministic diversity diagnostics** (computed in eval + optionally logged): Jaccard distance of the
  selected moment-id set vs parent; opening-moment-changed (bool); ordering edit distance (Kendall tau on the
  shared moments); source-range IoU per shared moment; shot-count delta; shot-duration-distribution delta. A
  version that scores ~0 on all of these is a "near-identical" failure.
- **Human quality eval:** side-by-side parent vs new version on the four fixtures — is the new one genuinely a
  different, still-good edit (not merely shuffled, not degraded)?

## 5. Natural-language revision design (V1)

Reuse the `critique → revise → validate` backbone, seeded with the EXISTING committed plan (`base_plan` from the
source version's `editPlanJSON`) plus the parsed directive. Two directive classes, separated explicitly:

- **Reference TARGETS are typed and distinct** (an id matching is not proof of correct semantic resolution):
  (a) a **Moment**; (b) an **event / source range inside a Moment**; (c) a **particular segment occurrence** in
  the base edit (the same Moment can appear in multiple segments). The resolver must say WHICH it resolved.
- **Source-reference resolution** maps a user phrase to one of those targets using EXISTING AU evidence (moment
  summaries, `useful_segments`, events) and, when visual-first is on, the multimodal contact sheets. Resolution
  is scoped to the CURRENT Story's eligible Moments — INCLUDING omitted/unused footage — and never auto-inserts
  unrelated global-library media. Deterministic candidate ranking; the model proposes, the resolver confirms
  against real ids.
- **Ambiguous references → thumbnail clarification UX** (existing `MomentThumbnailCache`), producing a TYPED
  clarification outcome BEFORE rendering. An unresolved reference must NOT silently become a guessed hard
  directive — it is either resolved by the user or reported as unresolvable.
- **Explicit include-all semantics:** "include everything / all of them" = all eligible Moments in a FIXED
  selected source set, as suitable EXCERPTS (not every source second). A duration conflict (more material than
  the target allows) is EXPLAINED, not silently resolved by dropping clips.
- **Infeasible / conflicting directives are surfaced**, never dropped (e.g. "exclude the only Moment that can
  open", or "include X and exclude X").
- MVP keeps the current continuous-performance + native-audio safeguards; automatic discovery of precise
  musical/action boundaries is DEFERRED.

> This NL section is **design completion only** during the Explore increment — it is not implemented until the
> Create Another Version device gate passes (owner direction §4/§5).

## 6. Preservation semantics (Explore vs Revise)

Two distinct operations, both append-only (each creates a NEW GeneratedOutput; previous versions preserved):

| | **Explore** (`mode:"explore"`) | **Revise** (`mode:"revise"`) |
|---|---|---|
| Intent | Seek meaningful editorial diversity | Apply requested changes |
| Prior plan | Used as an "avoid being identical" reference | Used as the BASE to preserve |
| Latitude | Substantial changes allowed | Change the smallest set needed; preserve unaffected edits where feasible |
| Temperature | baseline 0.0, optional bounded bump | 0.0 (determinism is desirable for a targeted edit) |
| Directives | none required | hard + soft directives applied + validated |

**User-owned invariants preserved by DEFAULT in BOTH operations** (never silently replaced): user intent +
CreativeIntent target duration; editing approach; sound preference; the selected soundtrack; active INHERITED
hard directives; user-authored Story title + description; existing protected continuous passages. The user MAY
explicitly change a preference or directive — a conflict between an explicit new instruction and an inherited
one is RESOLVED and surfaced, never silently dropped on either side.

**Constraints follow the SELECTED version's lineage.** Inherited directives/protected passages come from
`base_version_id`'s chain only — never accidentally from an unrelated sibling version. **Change Music stays the
existing soundtrack-only operation** (`operationType="change_music"`), distinct from Explore/Revise.

**Revise is a DIFF against the exact base plan.** Allowed changes = what the directive/soft_direction asks for.
After a Revise, compare the result to the exact `base_plan` and DETECT unrelated changes to source ranges,
ordering, speed, crop, transition, music, and native-audio on segments the directive did not target — these are
regressions to flag/reject, not silent edits. A NECESSARY timeline shift (e.g. re-numbered `order` after an
insert/removal) is NOT by itself a change to the underlying shots and is allowed. **A directed revision that
produced no effective change must NOT be returned as a successful edit** — it is an honest "couldn't apply that"
rather than a saved near-identical version.

## 7. Contract and prompt implications

- Additive request-only field `revision_context` on `EditPlanRequest` + `EditPlanInputs` + the
  `/v1/edit-plan-jobs` form. Default none ⇒ behavior unchanged ⇒ older clients unaffected. Bump the REQUEST/DTO
  minor; the EditPlan/2 OUTPUT contract and the `edit_plan/5.2` SYSTEM body stay FROZEN (all new text enters via
  the USER message, exactly like `creative_brief`).
- New deterministic predicates added to `validate_plan` for the HARD directive class (include/exclude/opening/
  ending/order/continuous). These are ADDITIVE checks that only run when a `directives` object is present.
- `GeneratedOutputModel.operationType` vocabulary extended with `another_version` and `edit_ai` (both already
  reserved); lineage model already migration-safe (additive).
- A versioned prompt proposal is required ONLY if evaluation shows the USER-message injection is insufficient
  and the SYSTEM body must change — explicitly deferred to a separate freeze gate, not assumed here.

## 8. Evaluation and acceptance criteria

Fixtures (reuse cached AU evidence; bounded model spend; NO new multimodal research program): **Girl with
Dress, Hiking, Guitar, Minimal footage.**

- **Create Another Version:** regenerating a version yields measurably different output vs parent on the §4
  diagnostics (not identical) AND passes human side-by-side quality (different, still good, not degraded, not
  shuffled). Prior version preserved; user duration + sound preference + hard directives honored. Minimal-footage
  fixture must NOT be forced to fabricate diversity it cannot support (honest "material too thin to vary").
- **NL Revision V1:** per directive — directive satisfaction (the intended change happened); source grounding
  (resolved to the right real Moment); preservation of unaffected edits (Revise mode); executability
  (`validate_plan` passes); audio continuity (native-audio + continuous performance preserved). HARD directives
  deterministically validated; infeasible/conflicting directives surfaced, never silently dropped.
- Spend: cap model calls, reuse cached evidence, no broad sweep.

## 9. Implementation sequence (after the gate)

1. **Shared foundation:** `revision_context` request field (additive) + lift `_build_revision` into a reachable
   "revise base_plan with context" entry point + new `validate_plan` hard predicates (behind presence of
   `directives`). No behavior change when the field is absent.
2. **Create Another Version (A):** client-derived `prior_plans` digest + `operationType`/`parentVersionId`
   wiring + fresh op_id; `mode:"explore"`. Diversity diagnostics in eval. Device-gate on girl + hiking.
3. **NL Revision V1 (B):** soft preferences first (wiring), then hard directives (structured parse + predicates),
   then source-reference resolution + thumbnail clarification UX. Device-gate per directive.

Each ships and is validated separately; (2) and (3) both depend only on (1).

## 10. MVP vs post-MVP boundaries

- **MVP:** shared `revision_context` foundation; Create Another Version with prior-plan diversity;
  NL Revision soft preferences + hard include/exclude/opening/ending/order.
- **Post-MVP:** `preserve_continuous` tied to AU action spans (depends on `CreativeRefinementV2b`
  device-acceptance); temperature-tuned variation as a default; multi-segment-per-Moment diversity;
  conversational multi-turn revision.
- **OUT OF SCOPE (owner):** new editing models, manual timeline editing, generative effects, large-library
  indexing, Create Now (separate milestone).

## Updated spec references

- Supersedes the Versions (§A) + NL-revision (§B) design of
  `milestone-mvp-reconciliation-createnow-versions-nlrevision.md`; Create Now (§C) remains in that doc, out of
  this milestone.
- Relates: `milestone-me-music-library-change-music-versioning.md` (lineage substrate),
  `milestone-async-edit-planning-and-prod-rollout.md` (async foundation), `12-edit-flow.md` /
  `milestone-v2a/v2b-creative-editing-*.md` (deterministic cut refinement, distinct from NL directives).
- **STOP at owner architecture/freeze gate.** No implementation, no contract/prompt change, nothing pushed.

---

## Implementation — Shared Foundation + Create Another Version (Explore) [committed, device-acceptance pending]

Approved amendments applied (commit 864e925 in specs). Implemented (app commit 576ab2b, NOT pushed):

**Backend** — additive `revision_context` on `EditPlanRequest` (`extra="forbid"`-safe) + `EditPlanInputs`;
injected into the USER message ONLY via `_revision_context_block` (frozen `edit_plan/5.2` system body + EditPlan/2
output unchanged); threaded through BOTH sync endpoints and the async worker's request reconstruction. Because it
lives inside the request `body`, it is part of the frozen request snapshot AND the canonical
`payload_fingerprint` (body-hashed) with NO fingerprint-logic change — so same-op/same-body resumes, same-op/
changed-context is a 409 conflict, new version = new op_id. `diversity_diagnostics` helper added. Temperature
left at 0.0 (unchanged). 70 backend tests green (+8 new).

**iOS** — `EditPlanRequestDTO.revisionContext` (encoded `revision_context`, omitted when nil = byte-identical
request); `EditPlanRequestBuilder.build(revisionContext:)` passthrough; new pure `RevisionContextBuilder`
(Explore context from the user-selected parent's persisted `editPlanJSON` + a bounded ≤4 recent set; diversity
diagnostics). `StoryCreationCoordinator.createAnotherVersion(for:from:)` mints a fresh op_id, sets
`operationType="another_version"` + `parentVersionId`, re-plans Explore, computes `lastDiversity`, and persists
append-only. Wired through `StoryResultView` ("Create a new version" now carries its output as the Explore
parent) → `CreateStoryPreviewView` → `StoryCreatingView(sourceVersion:)`. Works for Storytelling AND Visual-first
(approach is not switched to fake difference). `RevisionContextBuilderTests` added (parse-clean; device Xcode is
the authoritative compile gate).

**Automated checks (owner §6):** absent-context unchanged ✓; context injected + carried ✓; same-op retry resumes
/ changed payload 409 / new op new job ✓ (existing job-API tests + new fingerprint test); selected parent incl.
older version ✓; bounded history ✓; near-identical flagged (not silently saved) ✓.

**STOP — awaiting bounded device acceptance** on Girl with Dress / Hiking / Guitar / Minimal footage (purposeful
alternative vs no forced/fabricated variation; near-identical explained, never saved as a creative alternative).
Natural-Language Revision V1 follows after this device gate. Nothing pushed.
