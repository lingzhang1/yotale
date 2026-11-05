# Milestone — Natural-Language Revision: Explicit Moment References + Directed Fast Path

Status: IMPLEMENTED (backend + iOS), deployed to DEV, awaiting owner device acceptance.
STOP at device gate. No frozen EditPlan/2 or prompt body changed. Nothing pushed to prod / public.

Owner-approved across several turns (2026-10-14/15). Code-grounded.

## Scope

Make natural-language Story revision reliable and fast:
1. Explicit Moment references (typed numbers + visual picker) in Creative Direction and post-generation Revision.
2. Ordering directives (relative / adjacency), not just include/exclude/opening/ending.
3. Hybrid interpretation: deterministic parse + a bounded structured-AI step for compound language.
4. Preflight validation before spending an expensive revision job.
5. A directed revision fast path: deterministic (zero model) where safe, one targeted AI call otherwise.

Explicitly OUT: manual timeline editor, new media storage, a second resolution engine, frozen-contract changes.

## Architecture (one shared foundation, two surfaces)

- **Resolution core** (`apps/ios/.../Domain/Creation/MomentReferenceResolver.swift`): pure value types.
  `StoryMomentNumbering` = a stable Story-scoped 1-based numbering snapshot built from `story.moments`
  (existing `StoryMomentLink` order; NO model change, NO new numbering system). `parseTyped` / `parseOrdering`
  / `parseImplicitFollow` recognize the deterministic forms; `resolve()` maps typed numbers + visual-chip ids +
  ordering to `ResolvedDirectives` keyed by STABLE Moment UUID, surfacing unresolved references for
  clarification (never silently dropped/substituted). ONE implementation, reused by both flows.
- **Directive contract** (request-only, additive, in `revision_context.directives`):
  `must_include[], exclude[], opening, ending, order_after[[A,B]], order_adjacent[[A,B]]` — all RESOLVED
  stable ids. order_after = A somewhere after B; order_adjacent = A immediately after B; FIRST occurrence of
  each id is constrained. Injected into the planner USER message only — frozen `edit_plan/5.2` body and
  EditPlan/2 output UNCHANGED.
- **Backend validation** (`packages/edit_planner/__init__.py`): `validate_plan` deterministically enforces every
  directive and detects conflicts (include↔exclude, excluded-but-ordered, contradictory ordering, impossible
  adjacency, opening/ending vs ordering). `preflight_directives` does the same conflict/missing-reference check
  PLAN-INDEPENDENTLY, before any job.
- **Hybrid interpreter** (`packages/edit_planner/revision_interpreter.py` + `POST /v1/interpret-revision`): ONE
  bounded structured model call (text-only, no media, no planning). The model refers to Moments by DISPLAY
  NUMBER; the server maps number→stable id, so a model can never fabricate an id (an out-of-range number →
  unresolved). Returns typed directives + `soft_direction` + `unresolved` + preflight `blocking` + `can_submit`.
- **Directed fast path** (`packages/edit_planner/deterministic_revision.py`): `apply_deterministic_revision`
  applies exclude/opening/ending/order_* to the exact `base_plan` by pure reorder+prune (preserving every
  unaffected segment's source range/speed/transition/native-audio + the music; renumbering `order`). The
  planner `generate()` short-circuits BEFORE any model call when `mode=revise` + `base_plan` + hard directives +
  no soft text, adopting the result only if `validate_plan` passes (`revision_path=deterministic`,
  `model_calls=0`). A `must_include` of a Moment not already present, or a soft/creative request, falls through
  to a SINGLE generate call (critique stays off by default — so even the fallback is ~1 call, not 3).

## Latency

| Edit kind | Before | After |
|---|---|---|
| Structural (opening/exclude/reorder/adjacency on base plan) | 3 Opus multimodal calls, 35 images, ~235s | **0 model calls** (deterministic), ~sub-second planning |
| Creative/targeted | 3 calls | **1 call** (no critique round) |
| Full re-edit | 3 calls | unchanged (broad reinterpretation only) |

Root cause of the old cost (measured from live jobs): `generate→critique→revise` with 35 contact-sheet images
re-sent per call; `critique_applied=False` on observed runs, so 2 of 3 calls were waste.

## The owner's canonical instruction

"Use Moment 5 to start and Moment 2 follow." resolves to `opening=5` + `order_adjacent[2,5]`:
- `parseTyped` → opening=5; `parseImplicitFollow` → [2]; `resolve` attaches Moment 2 immediately after the
  opening. Verified in the resolver tests AND live on the interpreter endpoint
  (`/v1/interpret-revision` returned opening + order_adjacent + can_submit=true).

## Contract & prompt implications

- Additive request-only directive fields; EditPlan/2 output + `edit_plan/5.2` body unchanged.
- New endpoint `/v1/interpret-revision` (interpret + preflight). 503 on model/provider failure → client falls
  back to its deterministic parse.
- Prior speed-capability work (reject speed outside 0.5x–2.0x, bounded repair) and the renderer coverage-gap
  fix (`MediaEngineV1` "Operation Stopped") are prerequisites that shipped alongside.

## Implementation commits (local, unpushed)

- `7e7965b` parser robustness (natural phrasings, no phantom include)
- `51ceb33` ordering directives + conflict detection (backend)
- `4688e02` iOS resolver: ordering parse + encode (+ implicit-follow→opening)
- `001b5ea` hybrid interpreter `/v1/interpret-revision`
- `e5c55ce` deterministic fast path (0 model calls)
- `3878f17` preflight validation
- `51d9473` 16-case instruction matrix
- (earlier: `2a98c47` hard-directive validation; `b868d1d`/`54cbc36`/`e585fe4`/`136c73e`/`d30d295`/`6082337`
  the reference foundation + Revise sheet; `177f201` Revise music carry; `b82f854` speed cap; `78e5d53`
  renderer coverage-gap)

## Tests

Backend suite 227+ green: directive satisfaction (include/exclude/opening/ending), ordering (after/adjacent),
conflict detection, interpreter number→id mapping + no-fabrication, deterministic fast path (gateway that
raises if called → proves 0 model calls), preflight. iOS: resolver core (numbering, parser, reordering safety,
clarification) + the 16-case instruction matrix. Device acceptance (Phase 7) pending.

## Deployment (DEV)

Two artifacts, both carry this code:
- App Runner `story-development-api` (CodeBuild → ECR `:latest` → start-deployment).
- Worker Lambda `story-development-edit-plan-worker` (zip `.worker-asset` → update-function-code) — the async
  planning path; MUST be updated separately from App Runner.
Live-verified: `/v1/interpret-revision` returns correct directives for the owner's instruction.

## Known limitations

- Implicit "Moment N follow" attaches to the OPENING; a different antecedent needs explicit phrasing or the AI
  path.
- Free-text references ("the blue-dress clip") resolve only via the AI interpreter, not the deterministic parser.
- `must_include` of a Moment not already in the base plan falls back to the AI path (deterministic cannot invent
  a segment) — correct, but not sub-second.
- Relative ordering is representable (order_after/order_adjacent); arbitrary multi-constraint permutations are
  satisfied best-effort by reorder, else routed to AI.
- The visual Moment-reference picker's long-term UX (vs. always-visible Moment-number badges) is an open design
  question deferred by the owner.

## Device acceptance (Phase 7 — pending)

Clean-rebuild iOS (delete both `Story-*` DerivedData dirs — the stale-binary cause), then on iPhone:
select a generated version → Revise → "Use Moment 5 to start and Moment 2 follow" → verify opens with Moment 5,
Moment 2 immediately follows, unaffected edits preserved, planning fast, music/native-audio/render/share intact,
prior versions retained.
