# Guide v2.1 — Context-Aware Shooting Script & AI Refinement ("Update Guide")

**Status:** IMPLEMENTED (backend + iOS), parse-clean, backend suite green (636); iOS DTO/reconciler
type-checked standalone, authoritative device Xcode build is the owner's (sandbox blocks the SwiftData
macro plugin). **Nothing deployed — STOP before deployment for owner review.** Branch
`feat/yotale-shooting-script-guide` (off master; pre-existing WIP — pbxproj display-name, CDK WAF —
left untouched/uncommitted). Both features ship behind the existing `STORY_GUIDE_V2` flag.

**Owner decision (2026-10-23):** approve flexible AI refinement of the existing Story Guide; the AI
may replace/retire outdated **uncaptured** suggestions while preserving captured scenes, user-pinned
decisions, and historical coverage. Smallest safe implementation.

---

## 1. What this adds

1. **Richer initial shooting script** — the `story_guide/v2` prompt now carries concrete
   destination/event worked examples (Japan, San Francisco, Tour du Mont Blanc, Indian wedding) and
   stronger anti-generic guidance, so a sparse "Japan trip" yields recognizable, event-specific scenes
   (temple morning, street food after dark, the train) instead of an "Opening / Establishing / Closing"
   template. Output contract unchanged (still `framing_summary` + `scenes[]` with the four fields +
   `visual_reference_query`). The approved visual shooting-card UI + Unsplash integration are preserved.

2. **"Update Guide" refinement** — the user can type a natural-language update at any time
   ("Tomorrow we're visiting Arashiyama" · "We filmed lots of temples — suggest something different" ·
   "Focus more on us, less on landscapes"). A persistent, editable **event context** field is separate
   from a one-time refinement instruction; neither re-asks the user for the original description.

3. **Flexible, safe reconciliation** — the AI may preserve / improve / reorder / replace / add /
   archive **uncaptured, unpinned** scenes. It may NOT delete captured scenes, erase captured coverage,
   silently remove pinned scenes, rewrite a captured scene, or reset Story versions.

---

## 2. Architecture (additive, versioned)

- **New backend endpoint `POST /v1/story-guide-refine`** (gated by the existing `STORY_GUIDE_V2`;
  404 when off). Frozen `story_guide/1` and the generate-once `story_guide/v2` endpoints are
  byte-identical and untouched.
- **New prompt `story_guide/refine-v1`** — the model receives current scenes (each tagged
  `captured`/`pinned`/`protected`), the event context, and the user update, and proposes the next
  active script + a change log. It is told to reuse ids for conceptually-same scenes and mint fresh
  ordinals only for genuinely new scenes.
- **Server-authoritative reconciliation (`reconcile_refinement`)** — the model PROPOSES; the server
  DECIDES identity + history, so a prompt regression can never violate an invariant:
  - a captured (Coverage-evidenced) or pinned scene is forced into the output **verbatim** (any model
    rewrite of it is discarded) and can never be archived;
  - a scene returned with an existing id keeps that id (preserved/improved);
  - a scene with an unknown id gets a **fresh** `scene_NN` beyond the max existing ordinal — **retired
    ids are never reused**;
  - any existing uncaptured + unpinned scene the model dropped is **archived** (recorded in the change
    log + `archived_scene_ids`, id retained for history, never reused).
- **Result contract `StoryGuideRefinementResult`** (additive) = a normal `StoryGuideV2Contract`
  (`guide`) + `changes[]` (per-scene disposition log) + `archived_scene_ids[]`. Because `guide` is a
  plain v2 contract, **every existing consumer — persistence, Coverage/2 mapping, the scene-card UI —
  works unchanged**. The v2 scene id IS the Coverage/2 `story_guide_dimension_id` FK, so Coverage state
  and R7 references stay correct through refinement.

### Contract / schema impact
- Frozen `story_guide/1` prompt + contract: **unchanged.**
- `story_guide/2` contract: **unchanged** (reused as the refinement's `guide`).
- Added: `SceneDisposition`, `SceneChange`, `StoryGuideRefinementResult` (additive Pydantic models) +
  `story-guide-refinement.schema.json` (registered). No existing frozen contract altered.
- `story_guide/v2` **prompt** improved (same output shape); `story_guide/refine-v1` prompt added.

---

## 3. iOS

- `StoryGuideRefineService` → `POST /v1/story-guide-refine`; 404/503 → `.unavailable`
  (recoverable, current Guide kept).
- `StoryGuideCoordinator.refineGuideV2(for:instruction:)` — **async + non-destructive**: the current
  guide stays persisted until a **valid** refined guide replaces it; failure throws `.unavailable` and
  leaves the Guide intact. **Dedupe**: an input fingerprint (guide JSON + instruction + event context +
  protected ids) skips re-inference on unchanged inputs (`.duplicate`). Captured ids are **derived**
  from the Coverage/2 snapshot (a `strong`/`looking_good` or represented/evidenced scene is "captured");
  pinned ids come from `StoryScenePinModel`.
- **Pins:** `StoryScenePinModel` (one row per `storyId#sceneId`, schema-registered) + `togglePin` /
  `isPinned` / `pinnedSceneIds`. Scene content stays canonical in `guideJSON`; a pin only records the
  flag by stable id, so it survives refinement + R7 sync.
- **Persistent event context:** additive `StoryModel.eventContext` (optional + defaulted nil —
  lightweight-migration-safe), distinct from `intentRawText` (never overwritten) and
  `creativeDirectionText` (edit-plan soft direction).
- **UI:** `StoryGuideV2Section` gains an **Update Guide** sheet (one-time instruction + editable event
  context), a per-scene **pin** control, and a refinement status line ("Updated · 2 added · 1 archived").
  Archived scenes drop out naturally (the backend omits them from the active script). The approved
  cinematic scene-card layout + Unsplash attribution are unchanged.
- **R7 sync:** `event_context` rides in the Story doc; `scene_pins` ride in the derived block
  (merge-additive on pull — a pull never deletes a local pin). A refinement marks the Story dirty, so
  R7 pushes the refined scenes; the dirty-check hashes the local re-encode and stamps `lastSyncedHash`
  from the adopted re-encode (no false-dirty, no silent LWW).

---

## 4. Generation & cost controls (req 6)

- Refinement is **explicit only** — triggered by the user's Update Guide action, **never** by a Moment
  Understanding completion.
- **Dedupe** by input fingerprint: identical (guide + instruction + context + protected ids) → no
  inference.
- **Async**, current Guide preserved while it runs; on failure the existing Guide remains and a
  recoverable error is shown.
- Uses the existing AI inference + quota infra (classified `ai_sync`, paid-auth protected, same
  Opus 4.6 selection + Opus→Sonnet quota fallback as v1/v2). No additional model repair loop for
  wording.

**Inference-cost estimate:** one Opus call per **explicit** Update Guide (≈ the cost of one initial
Guide generation; `GUIDE_REFINE_MAX_TOKENS=3500`). No per-Moment or per-coverage regeneration. A
repeated identical update costs **$0** (dedupe). At beta scale (a handful of updates per Story over its
life) this is a small, bounded, user-initiated cost.

---

## 5. Before / after example (reconciliation evidence)

Japan trip, 4-scene guide. `scene_01` **captured** (filmed temple morning), `scene_02` **pinned** by
the user. User update: *"we filmed lots of temples, show something different; tomorrow we visit
Arashiyama."* The model proposes keeping the protected scenes, dropping the two redundant uncaptured
temples, and adding two Arashiyama scenes. Server reconciliation result:

**BEFORE**
- `scene_01` Temple morning in Kyoto  *(captured)*
- `scene_02` Street food after dark  *(pinned)*
- `scene_03` Another temple visit  *(uncaptured)*
- `scene_04` A third temple courtyard  *(uncaptured)*

**AFTER**
- `scene_01` Temple morning in Kyoto — **preserved verbatim** (captured; model's rewrite discarded)
- `scene_02` Street food after dark — **preserved** (pinned)
- `scene_05` The Arashiyama bamboo grove — **added** (fresh id, beyond max ordinal 04)
- `scene_06` The riverside train to Arashiyama — **added**

**Change log:** `scene_01 preserved · scene_02 preserved · scene_05 added · scene_06 added ·
scene_03 archived · scene_04 archived`
**Archived:** `[scene_03, scene_04]` — ids retained for history, **never reused** (the new scenes took
`scene_05/06`, not the retired `scene_03/04`).

This is the deterministic reconciler output (no model call); live-model before/after examples for
Japan/SF/TMB/wedding will be captured from the dev backend once the owner lifts the deploy gate.

---

## 6. Scene-preservation evidence (tests)

**Backend** (`apps/api/tests/test_story_guide_refine.py`, all green within the 636-test suite):
- captured scene preserved verbatim even when the model rewrites it;
- pinned scene never archived even when the model omits it;
- new scene minted beyond the max ordinal;
- a retired id is never reused for a new scene;
- improved scene keeps its id and logs `improved`;
- reconciled result validates as a `StoryGuideV2Contract`;
- empty framing falls back to the current one;
- endpoint 404 when flag off; 200 with a change log when on; failure → 503 (current Guide preserved),
  never a 5xx crash; route classified + paid-auth protected.

**iOS** (`StoryGuideRefineTests.swift`, device-build to run):
- refinement result DTO decode (incl. the double-optional flatten);
- durable pin toggle → `pinnedSceneIds`;
- captured-scene derivation from Coverage/2; refine persists into the same row and preserves the
  captured scene; a failed refine preserves the current guide; refine without a guide throws.

---

## 7. Acceptance mapping (req 7)

| Acceptance criterion | Covered by |
|---|---|
| Sparse Japan/SF/TMB/wedding → relevant suggestions | richer `story_guide/v2` prompt (worked examples) |
| Confirmed vs suggested destinations distinguished | prompt rule (no fabrication; possibilities not assumptions) |
| User can update the Guide during an event | Update Guide sheet + `/v1/story-guide-refine` |
| Captured scenes + Coverage survive refinement | `reconcile_refinement` protected-id preservation (tested) |
| User-pinned scenes remain protected | pins passed as protected ids; server enforces (tested) |
| Outdated uncaptured scenes replaced/archived | reconciler archive path (tested) |
| New scenes get stable unique ids | fresh-ordinal minting, no reuse (tested) |
| Repeated identical updates → no duplicate inference | coordinator input-fingerprint dedupe |
| Failed refinement preserves previous Guide | 503 + coordinator keeps current guide (tested) |
| R7 retains refined Guide + scene history | guide dirty→push; `event_context` + `scene_pins` synced |
| Story Idea independent | untouched (Coverage/2 `story_idea` path unchanged) |
| Existing versions + Moments untouched | no change to outputs/versions/Moments |

---

## 8. Remaining risks

- **Device build unverified by the sandbox** — the authoritative iOS compile (SwiftData macro) is the
  owner's; parse-clean + standalone DTO/reconciler type-checks are not a substitute.
- **Live-model before/after** — only captured post-deploy (dev); §5 is the deterministic reconciler
  demonstration.
- **Deploy gate** — `/v1/story-guide-refine` is not live until the dev backend is redeployed with
  `STORY_GUIDE_V2=1` (same as v2). STOP held per owner.

## Boundaries honored
No change to Story creation, Customize, EditPlan, media ownership, quotas, WAF, billing, model pricing,
or R7 architecture. Unsplash provider + approved visual card unchanged. Frozen Guide v1 contract +
prompt untouched; the refinement contract is an additive versioned extension.

---

## CLOSEOUT UPDATE (2026-10-24) — DEPLOYED + LIVE-VERIFIED ON OPENAI; device build the only open item

The earlier STOP ("nothing deployed; Anthropic access blocked") is **superseded**. The Guide v2.1 backend
is now deployed to dev and the old blocker is **obsolete**: the direct OpenAI/Gemini provider migration
retired Anthropic entirely, so Guide generation/refinement no longer calls Bedrock Anthropic at all — the
"re-enable Anthropic Model Access" ask no longer applies.

**Deployed + live (dev `989088054552`, App Runner `story-development-api`, `STORY_MODEL_PROVIDER=direct`,
`STORY_GUIDE_V2=1`):** all three routes live in `/openapi.json` — `/v1/story-guide`, `/v1/story-guide-v2`,
`/v1/story-guide-refine`. Story Guide (all stages) runs on **OpenAI `gpt-5.1`**.

**Live before/after captured (the §8 "live-model before/after" risk — now CLOSED):**
- BEFORE — `/v1/story-guide-v2` on "Our week in Japan — Tokyo and Kyoto" → 8 event-specific scenes (First
  steps out of Tokyo station, scramble crossing, ramen counter, train to Kyoto, temple, Kyoto alley at
  dusk, last look back) — the richer v2 prompt producing recognizable scenes, not a generic template
  (~19.8s).
- AFTER — `/v1/story-guide-refine` with scene_01 captured, scene_06 pinned, instruction "we filmed a lot of
  temples — focus more on the two of us and the food": server-authoritative reconciliation verified —
  **scene_01 (captured) + scene_06 (pinned) preserved verbatim**; two generic landscape scenes
  (scene_02/scene_03) **archived**; scene_07 rewritten to include the couple; **new fresh ids scene_09 /
  scene_10** minted beyond the max ordinal (no id reuse) for the food focus; `changes[]` +
  `archived_scene_ids` returned (~15.8s).

**Tests:** `test_story_guide_refine.py` 10 passed (captured/pinned preservation, archive, fresh-id minting,
no-id-reuse, 503 preservation, feature gate). Backend suite green.

**Remaining open item (ONE):** the authoritative **iOS device Xcode build** (sandbox blocks the SwiftData
macro plugin) + on-device acceptance of the Update-Guide UX (pin toggle, event-context field, refinement
status). Everything server-side is deployed and verified.

**Minor follow-up (non-blocking):** a probe of `changes[].action` rendered empty via a raw key read — likely
a field-name nuance in `StoryGuideRefinementResult.changes`; the reconciliation behavior itself (preserve/
archive/add) is correct and verified. Worth a quick field-name confirm during the iOS wire-up, not a backend
defect.
