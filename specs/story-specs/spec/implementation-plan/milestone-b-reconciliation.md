# Milestone B — Schema Reconciliation Report

**Status:** Analysis complete — written BEFORE any material schema change (per task §1).
**Date:** 2026-10-01
**Scope:** Reconcile `02-core-story-schema.md` against the actual Milestone A Swift + Python code.
**Rule applied:** Where code conflicts with the frozen product definition
(`story-production-latest.md`), the product definition wins unless a documented
technical reason says otherwise.

Sources cross-checked: `story-production-latest.md`, `03-system-architecture.md`,
`04-aws-infrastructure.md`, `02-core-story-schema.md`, and a full type inventory of
`contracts/`, `apps/api/`, `packages/`, and `apps/ios/Story/Story/`.

---

## 0. Headline

Milestone A built a **correct but deliberately narrow** slice. Nothing in the code
contradicts the product definition — the invariants that matter most (Story ≠ Output,
Create ≠ Complete, local-first media, status = active|completed) are implemented and
test-covered. The gaps are **omissions** (objects not yet modeled) and **MVP shortcuts**
(flattening, mocks, in-memory store), plus a short list of **naming divergences** that
must be frozen before real AI consumes these contracts.

No product-behavior conflict was found that requires changing the product spec.

---

## 1. What matches the spec and the product definition ✅

| Concept | Code | Verdict |
|---|---|---|
| `Story.status` = `active \| completed` | Python enum + Swift enum, raw `"active"/"completed"` | ✅ matches `02 §3`, product `§18`, arch `§30` |
| Create ≠ Complete | `add_generated_output` / `addGeneratedOutput` deliberately never touch status; asserted in API + tests on both platforms | ✅ matches product `§17/§18`, invariants `§35.3-4` |
| Story ≠ GeneratedOutput; many outputs per Story | distinct types; `generated_outputs: [...]`; tests `testMultipleOutputsAllowed` | ✅ matches invariants `§35.1-2` |
| Local-first media | `Asset.local_uri` / `AssetModel.relativePath`; "backend never receives bytes"; originals never in SwiftData; `MediaStore` is sole resolver | ✅ matches product `§19`, arch `§10/§11` |
| Opaque UUID IDs | `uuid4` domain + `@Attribute(.unique) UUID` persistence | ✅ matches arch `§34` |
| Anonymous local identity | `LocalIdentityModel` (iOS only), no account | ✅ matches product `§19`, arch `§9` |
| Moment belongs to one Story | `MomentModel.story` relationship; domain `story_id` | ✅ matches invariant `§35.7` |
| Engines don't import each other | Protocols + mocks; app layer orchestrates | ✅ matches arch `§40` |
| Wire format snake_case JSON over `/v1` | `POST /v1/stories`, Pydantic snake_case, `model_dump(mode="json")` | ✅ matches arch `§14/§49` |
| AI = replaceable Protocol seam | `deps.py` returns mocks typed as Protocols; `model_gateway` Protocol-only | ✅ matches arch `§2 principle 15` |

---

## 2. Objects specified but NOT yet modeled in code (omissions)

These exist in `02-core-story-schema.md` and/or the product spec but have **no code
representation** yet. Milestone B must define their canonical + machine-readable
contracts (code wiring stays mock/absent — no real AI).

**Needed for Milestone C (freeze now):**
- `CreativeIntent` — exists but **flattened** (see §3); the rich shape is unmodeled.
- `SceneUnderstanding` — absent entirely.
- `StoryConcept` — only a trimmed `ShotSuggestion` stand-in exists.
- `StoryPlan` + `Shot`/`ShotPlan` — absent (nested shot list unmodeled).
- `ValidationResult` — absent (no object; not even named in arch docs — see §6).
- `CaptureSession` — absent (arch only ever says "CaptureSession metadata").

**Preserve for later milestones (define contract, keep mock):**
- `MusicDirection` — absent (product `§15`, schema `§6`).
- `StoryBlueprint` + `NarrativeNeed` + `StoryGuideIdea` — absent (product `§5`, schema `§7-9`).
- `StoryState` — absent (product `§13`, schema `§10`).
- `StoryIdea` — absent (product `§7`, schema `§21`).
- `AssetUnderstanding` — only a 2-field stub (`asset_engine.AssetUnderstandingStub`).
- `MusicAsset` + `MusicAnalysis` — only a 3-field `MusicTrackStub`.
- `EditPlan` + `EditSegment` — absent; `MockEditEngine` jumps straight to `GeneratedOutput`.
- `ExistingMediaImport` — absent (two Home entry points are disabled stubs).

---

## 3. Fields implemented differently from spec (shortcuts) ⚠️

### 3.1 CreativeIntent is flattened
- **Spec (`02 §4`):** `sourceInputs[]`, `summary`, `subject?`, `desiredFeeling[]`,
  `styleTags[]`, `emphasis[]`, `avoid[]`, `targetDurationSeconds?`, `targetFormat?`,
  `rawUserDescription?`.
- **Code:** Python domain/DTO = `{id, raw_text, theme, tone, summary, created_at}`;
  Swift value type = `{rawText, theme, tone, summary}` (no id/createdAt); SwiftData =
  4 scalar columns on `StoryModel` (`intentRawText/Theme/Tone/Summary`).
- **Verdict:** MVP shortcut, not a conflict. `theme`/`tone` are a mock stand-in for the
  richer structured fields. **Decision:** freeze the full `CreativeIntent` contract per
  spec, but keep the Milestone-A persisted fields usable via a documented mapping
  (`theme`→a `styleTags`/`desiredFeeling` seed, `summary` 1:1, `raw_text`→`rawUserDescription`).
  No destructive migration (see §5).

### 3.2 CreativeIntent identity differs by layer
- Python domain `CreativeIntent` has `id` + `created_at`; Swift value type has neither;
  SwiftData denormalizes it into the Story row (no own id).
- **Verdict:** acceptable. CreativeIntent is a value object owned by exactly one Story;
  it does not need an independent persisted identity in MVP. **Freeze decision:** domain
  model keeps `id`/`created_at` (useful for AI provenance); persistence may keep it
  flattened; the DTO carries whatever the API returns. Document the mapping.

### 3.3 GeneratedOutput references moments by id snapshot
- `moment_ids: list[UUID]` / `GeneratedOutputModel.momentIds` is a denormalized snapshot,
  not a live relationship.
- **Verdict:** correct and intentional — matches product `§17` ("records the Moment IDs
  that produced it") and keeps outputs immutable. Keep.

---

## 4. Naming inconsistencies to freeze 🔧

| # | Divergence | Spec/arch | Code | Freeze decision |
|---|---|---|---|---|
| 1 | **MomentSource values** | `02 §11`: `directed_capture`, `spontaneous_capture`, `existing_media`, `camera_import` | `directed`, `spontaneous`, `existing_media`, `camera_import` (Python + Swift raw values aligned) | **Keep the code values** (`directed`/`spontaneous`), update `02 §11` to match. Reason: both platforms already agree, data is persisted on devices with these values, and a rename forces a device migration for a purely cosmetic suffix. Documented technical reason to deviate from the doc's `_capture` suffix. |
| 2 | **Shot vs ShotPlan** | arch `§17` uses `ShotPlan[]`; task checklist says `Shot`; no object literally named `Shot` | n/a (unmodeled) | **Freeze as `Shot`** (the array element) nested inside `StoryPlan.shots[]`, matching `02 §18`'s `ShotPlan` fields but under the shorter product name `Shot`. Record the alias. |
| 3 | **ShotSuggestion shape** | n/a (A-only helper) | Python: `concept_title/instruction/target_duration_seconds`+ids; Swift: `guidance/suggestedSeconds` | Transitional mock type; **superseded** by frozen `StoryConcept`+`StoryPlan`. Mark deprecated; do not freeze into contracts. |
| 4 | **GeneratedOutputPlan** (Swift) | n/a | Swift-only planning struct | Transitional; superseded by `EditPlan`. Not a contract. |
| 5 | **Asset.local_uri vs relativePath** | domain/DTO `local_uri`; persistence `relativePath` | — | **Intentional layer difference**, not a bug: DTO carries an opaque reference string; SwiftData stores a Documents-relative path. Keep both; document the mapping (persistence `relativePath` → domain `local_uri` is a device-local resolution via `MediaStore`). |

---

## 5. Cross-platform mock divergence (behavioral note) 📌

Swift and Python mock engines use **different vocabularies, hash functions, and
selection math**, so the same input produces different theme/tone/guidance on each
platform. This is harmless for Milestone A (each platform is internally deterministic
and the backend is not the source of truth), but it means **contract tests must assert
shape and enum validity, not specific mock values** across the boundary. Recorded so
Milestone C does not accidentally depend on matching mock output.

---

## 6. Gaps the architecture docs themselves leave open (must decide at freeze)

From the arch/infra extract — these are unspecified anywhere and Milestone B must define
them deliberately rather than transcribe:
1. **Error-envelope shape** — arch mandates "consistent errors" but gives no JSON shape or
   code enum. The `§37a` log fields are a LOG schema, not an API error body. → Define a
   minimal error envelope.
2. **Timestamp/serialization conventions** — no ISO-8601 statement, no case rule. → Freeze:
   ISO-8601 UTC timestamps, snake_case JSON (matches existing code), UUID string ids.
3. **`Story.status` as a formal enum** — referenced but never declared. → Freeze as enum.
4. **`ValidationResult`** — only a `/v1/direct/validate` operation is named; no object. →
   Define the object per `02 §20` (`usable`, `confidence?`, `issues[]`, `recommendation`).
5. **`CaptureSession` fields** — only "metadata" referenced. → Define per `02 §14`.

---

## 7. Milestone-A shortcuts to preserve (do NOT "fix" in B)

These are correct for MVP and explicitly must not be grown:
- In-memory `InMemoryStoryStore` — backend is stateless; iOS SwiftData is the source of
  truth. Keep.
- Mock engines behind Protocols — no real AI in B.
- `GeneratedOutput` = metadata only, no render.
- Two Home entry points disabled — UX widening is not part of B (B is schema freeze).
- `model_gateway` Protocol-only; `asset_engine`/`music_engine` stubs — fine.

---

## 8. Reconciliation decisions summary (what §2 freeze will do)

1. Freeze all 17 canonical domain objects (task §2) in `02-core-story-schema.md` as the
   current design — the richer `CreativeIntent`, plus the previously-unmodeled objects.
2. Correct `02 §11` MomentSource to the code values (`directed`/`spontaneous`), with a
   note recording the deviation from the original `_capture` suffix and why.
3. Name the shot element `Shot` (nested in `StoryPlan.shots[]`); deprecate the
   transitional `ShotSuggestion`/`GeneratedOutputPlan` helpers (leave code as-is for A).
4. Define the four model layers explicitly (domain / API DTO / SwiftData persistence /
   AI structured-output) and the mapping table, honoring arch `§7` + `§2 principle 4`.
5. Add machine-readable JSON Schema for the boundary + AI objects under `contracts/`;
   add Pydantic models for the C-critical AI contracts; add Swift Codable DTOs only where
   iOS must consume a contract (none consumed in A — add the AI-facing ones as the C seam).
6. Add contract tests (incl. malformed cases) for CreativeIntent, SceneUnderstanding,
   StoryConcept, StoryPlan, ValidationResult.
7. No destructive migration: existing persisted StoryModel rows remain valid; new
   fields are additive/optional.

**No real AI is implemented in Milestone B.**
