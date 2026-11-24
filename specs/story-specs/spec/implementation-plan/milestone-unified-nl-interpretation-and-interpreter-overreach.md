# Unified Natural-Language Instruction Interpretation + Interpreter-Overreach Fix

**Status:** IMPLEMENTED (backend + iOS), deployed to dev, headline device-acceptance PASSED; broader
device matrix + prompt-freeze sign-off owner-gated. STOP at owner device acceptance. Nothing pushed/public.

**Branch:** `fix/p0-recover-jobs-explore-latency` (shares the P0 recover-jobs branch). Backend (API + worker
Lambda) deployed to `story-development-api` (acct 989088054552, us-east-1); health 200.

## Goal

Make Story honor ordinary natural-language editing instructions on BOTH Stage 2 Customize (initial create)
and post-generation Revise, through ONE shared interpretation pipeline that reuses the existing server
interpreter, without users learning command phrasing — and stop the interpreter from inventing hard
constraints the user never asked for.

## Root causes (all verified from code + live logs, not assumed)

1. **Directive id case mismatch (silent).** iOS encoded directive ids UPPERCASE (`UUID.uuidString`) while
   moments[]/segment ids are lowercased; the backend compared case-sensitively, so opening/ending/order
   **never matched** — every "new version" came back as the same default edit, and the first-pass validator
   rejected every segment. Fixed: iOS lowercases directives; `validate_plan` / `_validate_directives` /
   `apply_deterministic_revision` compare case-insensitively (defense-in-depth). *(commit `5f6b5b8`)*

2. **Opening collapsed into include-only chips.** `CreateStoryPreviewView` seeded the Customize reference
   chips from `mustInclude + exclude + opening + ending`, but chips are an INCLUDE-only control, so a
   persisted opening was downgraded to `must_include` on every round-trip — the clip never moved to the
   front. Fixed: seed only `mustInclude`. Also `"start from Moment N"` did not parse as opening (connector
   list lacked `from`). *(commit `75c60ab`)*

3. **Stale submitted text.** `CustomizeYourStoryView` seeds its `creativeDirection` @State once and
   `.sheet(item:)` reused the view identity, so the editor kept a stale seed and submitted a prior operation's
   text. Persistence ordering + the `directedByCustomize` gate were already correct. Fixed: presentation-scoped
   `.id(rec.id)` re-seeds every open. *(commit `7f0b698`)*

4. **Interpreter OVERREACH (the headline bug).** `revision_interpret/1` (Nova Lite) mapped an
   inclusion/ordering-only instruction — *"Use Moment 13 first and Moment 2 immediately after. And use Moment 6
   as end."* — to a large **exclude** set (read "use X,Y,Z" as "use only X,Y,Z"). Confirmed interpreter-origin:
   `revision_interpreter._map_ids(exclude)` emits it; the planner never adds excludes. The planner then failed
   `invalid_after_repair` → the device showed "Edit Planner unavailable, retry". *(commits `cb08c8a`, `6d02084`)*

5. **Revise dropped the base soundtrack.** `resolveBaseMusic` carried a provider track by re-running a FULL
   recommendation, which could miss or fail transiently → the revised video rendered silent (beacon
   `music=none`, `soundtrackTrack=NO`). Fixed: resolve the exact base track directly by id. *(commit `b4e2d06`)*

## What shipped

### Shared interpretation pipeline (Phases 1–3 of the first spec)
- `InterpretService` — the SINGLE iOS client for `POST /v1/interpret-revision` (reuses the existing server
  interpreter + preflight; server maps display-number→stable UUID, model never mints ids).
- `InterpretationCoordinator` — ONE entry point for Customize + Revise. Deterministic parse first, adopted
  ONLY when it consumes the WHOLE actionable instruction; compound/partial/unrecognized route to the server.
  "≥1 regex matched" is explicitly NOT the completeness test (a dropped Moment ref, dropped ordering clause,
  or unrecognized position phrasing forces the server path). Server 503/transport → deterministic fallback
  ONLY when the whole instruction is safely understood, else a retryable serviceFailure.
- Both `CustomizeYourStoryView` and `ReviseStorySheet` wired through the coordinator with: immutable
  submission snapshot (text+chips+numbering); duplicate-tap guard; stale-response drop (token bumped on
  edit/cancel/disappear); typed error kinds (ok / clarify-with-thumbnails / serviceFailure+Retry); music asks
  surfaced honestly (typed-music deferred); preflight `can_submit=false` never launches planning.
  *(commits `4c72b8e`, `6eefc7a`, `891eedb`)*

### Honest failure + preflight feasibility
- iOS `invalid_after_repair` → `directivesUnsatisfiable` ("adjust your instruction / exclude fewer Moments"),
  not a misleading transient "retry".
- `preflight_directives` rejects an exclude set leaving < 2 eligible Moments (upfront clarify, not an
  expensive failed job). *(commit `cb08c8a`)*

### Interpreter overreach fix (second spec)
- **`revision_interpret/2`** — active default; v1 preserved verbatim as `_SYSTEM_V1` and still selectable for
  A/B. Explicit anti-overreach semantics: use/include/opening/ending/ordering NEVER imply exclusion; emit
  `exclude` ONLY on explicit omission (remove/drop/skip/without/don't use) or explicit restriction
  (only/except/just). Never invent constraints; preserve compound clauses; unresolved when unreliable.
- **`ground_directives()` grounding guard** — deterministic. Flags an exclude set unsupported by the user's
  words. The endpoint then does ONE bounded reinterpretation; if still unsupported it becomes a blocking
  reason (`can_submit=false` → clarify). NEVER silently drops; preserves legitimate "use only A,B,C". *(commit
  `6d02084`)*
- **Music carry-over** — `MusicSelectionResolver.resolveKnownTrack(trackId:)` resolves the base track directly
  (download + analysis by id, no recommendation), using the base output's persisted role/priority/title +
  `music_plan` from its editPlanJSON. *(commit `b4e2d06`)*

## Results

### Live v1→v2 interpreter comparison (deployed endpoint, Nova Lite, 15-Moment snapshot)
| Instruction | v2 directive keys | excludes | latency |
|---|---|---|---|
| Use Moment 13 first … Moment 2 immediately after … Moment 6 as end | opening, order_adjacent, ending, must_include | **0** | 1.14s |
| Start with Moment 5 | opening | 0 | 0.70s |
| Include Moment 8 | must_include | 0 | 0.81s |
| Use only Moments 13, 2, 6 | must_include, exclude | 12 (restriction honored) | 1.00s |
| Don't show anything except 13, 2, 6 | must_include, exclude | 12 | 1.05s |
| Remove Moment 4 | exclude | 1 | 0.65s |
| Use Moment 5 but exclude Moment 8 | must_include, exclude | 1 | 0.84s |
| Start with Moment 5 and make the cuts faster | opening (+soft) | 0 | 0.71s |

v2 eliminates invented exclusions on the failed instruction while preserving every legitimate restriction;
interpretation latency ≈ 0.6–1.1s, same model, no cost increase. The grounding guard did not need to fire
(v2's prompt alone produces correct output); it remains the deterministic safety net.

### Device acceptance (headline, verified from `rev_diag` + render beacon)
Instruction *"Use Moment 13 first and Moment 2 immediately after. And use Moment 6 as end."* (job `8f3efc20`):
- `directive_keys = [ending, must_include, opening, order_adjacent]` — **no `exclude`**.
- `opening == seg0` = Moment 13 (`opening_honored: true`); `seg1` = Moment 2 (adjacent); last seg = Moment 6.
- 13 distinct Moments used → other Moments remained eligible.
- Render beacon `soundtrackTrack=YES, looped x1, trackDur=120.8s` → **soundtrack preserved**.
- **Latency 36s**, format `vertical`, 14 segments / 91.5s, `model_calls: 1` (no repair, no fallback). Fixing
  the overreach also fixed the earlier 172s latency: a clean directive set validates on the first pass instead
  of forcing a 4-call multimodal repair cycle.

### Earlier device-verified
- Scenario #1 "Start with Moment 5" (job `1545575c`): opening honored, 1 model call, multimodal/36 sheets,
  vertical 90.1s, soundtrack YES.

## Tests
- Backend: full `edit_planner` + api suite green (302+), incl. 14 interpreter-overreach/grounding tests
  (scripted gateway, NOT via the Edit Planner), preflight over-exclusion, case-insensitivity regressions.
- iOS: `InterpretationPipelineTests` (routing of all 18 instructions, 503 fallback, decode filtering, partial-
  adjacency escalation) + `MomentReferenceResolverTests` ("start from"/"start with" opening). Run in Xcode
  (the SwiftData macro plugin is sandbox-blocked; device Xcode is the authoritative compile gate).

## Latency / model-call impact
- Interpretation (Nova Lite, text-only): ~0.6–1.1s, one call, unchanged v1→v2.
- Edit Planning (Opus 4.6, multimodal 36 sheets): a clean directive set = 1 call (~36s); the earlier 172s was
  4 sequential calls (1 repair) forced by the invented-exclude conflict — removed by the overreach fix.

## Deferred (require versioned approval — NOT implemented)
- **Semantic references** ("the girl in the green dress", "the summit celebration"): the interpreter resolves
  only numeric "Moment N"; semantic asks surface as unresolved → clarify / visual pick, never a silent soft
  downgrade. A `revision_interpret/≥3` with Moment summaries + an image-aware match is the proposal.
- **Typed music directives**: music intent currently survives only as soft_direction; a typed music contract
  field is a schema change held for a separate versioned proposal.
- **Multimodal edit-plan latency**: ~36s best case is dominated by the 36-image Opus call; a text-only revise
  path would be faster but is a planning-behavior change.

## Remaining limitations / known gaps
- v2 is the active default on dev; the prompt-freeze decision (keep v2) is the owner's to confirm after the
  broader device matrix. Recommendation: KEEP (fixes overreach, no latency/cost change, preserves all
  legitimate cases).
- The grounding guard currently checks the one overreach we have evidence for (unsupported exclude). Other
  invented-constraint classes would extend `ground_directives` the same way.
- Implicit-follow attaches to the opening; free-text/semantic references use clarification, not resolution.

## Commit list (this effort)
`f39c361` banner-ready fetch · `957b2a5` per-model/first-pass diag · `5f6b5b8` directive case fix ·
`52eb0db` directive/opening-vs-seg0 diag · `75c60ab` opening-chip-collapse + 'start from' · `7f0b698`
stale-text .id · `4c72b8e` shared interpretation pipeline · `6eefc7a` wire both UI paths · `891eedb`
pipeline tests · `cb08c8a` honest invalid_after_repair + over-exclusion preflight · `b4e2d06` revise music
carry-over · `6d02084` revision_interpret/2 + grounding guard.
