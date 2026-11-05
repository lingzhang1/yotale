# R7 (expanded) — Complete Story-State Synchronization: Phase 0 Audit + Architecture

Status: 🟡 PHASE 0 AUDIT + ARCHITECTURE — approval gate. Nothing provisioned, no cloud contract changed, no
code merged on this basis. STOP for owner approval before new infra. Principle: **restore first, reuse valid
results, regenerate only when genuinely necessary.** Target: **zero Bedrock calls** on Device B for a fully
synced, compatible account.

## 0. The core finding (verified, not assumed)
`story_doc/1` (StoryDocCodec) and `apply()` sync **Story METADATA only**. The Story Guide, Coverage, Moment
Understanding, Music Plan, Duration recs, and Music Direction are **NOT encoded** (guide + music are literally
`NSNull()` in the encoder) and **NOT decoded** on pull. So on Device B every AI stage finds no cache and
**regenerates** — the Guide text you saw on B was *regenerated*, not restored. This is the whole bug.

## 1. Persistence & regeneration audit

Legend per column: **Store** · **Trigger** · **in story_doc/1?** · **Fingerprint / schema+prompt ver** ·
**Cross-device reuse-safe?** · **Scope** · **Prereq ordering**.

| Result | Store (SwiftData) | Regen trigger | In doc? | Fingerprint / version | Reuse-safe? | Scope | Prereq |
|---|---|---|---|---|---|---|---|
| **Moment Understanding** (+ useful segments, semantic desc — these live INSIDE `understandingJSON`) | `MomentUnderstandingModel` (PK **momentId**) | AU queue enqueues when a Moment has no completed MU (now guarded post-R7-C) | **No** | `schemaVersion` + `framePolicy` + `promptVersion` + `modelId`; source = the Moment's media (content-addressed via its `cloud_media_id` sha) | **Yes** — same media bytes + compatible schema ⇒ identical understanding | **Shared across Stories** (per Moment) | Feeds Guide, Coverage, Edit Plan |
| **Story Guide** | `StoryGuideModel` (PK storyId) | `StoryGuideCoordinator.ensureGuide` on Story open / Creative Direction (regenerates if absent) | **No** | `schemaVersion` + `promptVersion` + `modelId`; input = intent + moments | **Yes** — same intent + moment set + schema | Per Story | Needs intent; feeds Coverage |
| **Story Coverage** | `StoryCoverageModel` (PK storyId) | `StoryCoverageEngine` (now gate-coalesced) when stale | **No** | `sourceUnderstandingIdsFingerprint` + `creativeIntentFingerprint` + `storyGuideFingerprint` + schema+prompt | **Yes** — all three fingerprints match | Per Story | Needs AU + Guide |
| **Creative Intent** | fields on `StoryModel` | user input | **Yes** (in story block) | — (source, not derived) | Yes | Per Story | Feeds Guide/Coverage/plan |
| **Creative Direction + resolved directives** | `StoryModel.creativeDirectionText` / `creativeDirectivesJSON` | user input | **Yes** | — | Yes (user decision) | Per Story | Feeds plan |
| **Duration recommendation** | `DurationRecCacheModel` (PK storyId) | DurationService when `inputFingerprint` changes | **No** | `inputFingerprint` (intent+moments+prompt) + `promptVersion` | **Yes** | Per Story | — |
| **Music Direction** | `StoryMusicDirectionModel` (PK storyId) | MusicDirectionCoordinator.ensure; `userAuthored` guards overwrite | **No** (NSNull placeholder) | `fingerprint` + `userAuthored` | **Yes** (esp. user-authored) | Per Story | Feeds Music Plan |
| **Music Plan** | `MusicPlanCacheModel` (PK storyId) | MusicService when `inputFingerprint` changes | **No** | `inputFingerprint` + `promptVersion` | **Yes** | Per Story | Needs Music Direction |
| **Selected soundtrack** | (in Music Plan / output provenance) | user pick | partial | — | Yes (user decision) | Per Story | — |
| **Edit Plans + revision lineage** | on `GeneratedOutputModel` (`editPlanProvenance`, `sourceMomentIds`, `sourceFingerprint`); full plan JSON currently NOT persisted post-render | Edit Planner (user Create/Revise) | metadata only | provenance string + `sourceFingerprint`; frozen `edit_plan/2` | **Yes** (preserve exactly — never re-plan for playback) | Per Story | Needs AU/coverage to PRODUCE; not to REPLAY |
| **GeneratedOutput metadata** | `GeneratedOutputModel` (PK id) | render persists | **Yes** (metadata) | `sourceFingerprint` | Yes | Per Story | — |
| **Generated MP4 reference** | none yet (`cloudMediaId` field added, unused) | R7-D | planned | full-file sha256 | Yes | Per Story | R7-D |

**Takeaways:** every AI cache already carries a JSON blob + an input fingerprint + schema/prompt version — so
safe reuse is a matter of *transporting* them and *comparing fingerprints* on arrival. AU is the only one
**shared across Stories** (keyed by momentId) → it belongs in an account-level store, not inside each Story doc.

## 2. Cloud representation (additive; reuse R7 infra)

Two new synced surfaces, both account-scoped, both additive:

**(A) `story-<env>-understanding` DynamoDB table** — account-level Moment Understanding (shared across Stories).
```
PK story_user_id   SK moment_id
  understanding_json (S)   schema_version (S)   prompt_version (S)   frame_policy (S)   model_id (S)
  content_sha256 (S)       -- the Moment's media sha: reuse only if it MATCHES (same bytes)
  revision (N)   updated_at (N)
```
Device B restores AU by `moment_id`, reusing iff `content_sha256` + `schema_version` compatible.

**(B) Extend `story_doc/1` → `story_doc/2`** (additive, versioned) to carry the per-Story derived caches as
**inline JSON when small, or an S3 reference when large** (Phase-C2 rule, DynamoDB 400 KB):
```jsonc
"derived": {
  "guide":    { "json"|"ref", "schema_version", "prompt_version", "fingerprint" } | null,
  "coverage": { "json"|"ref", "schema_version", "prompt_version",
                "source_understanding_fingerprint", "creative_intent_fingerprint", "guide_fingerprint" } | null,
  "music_direction": { "json", "user_authored", "fingerprint" } | null,
  "music_plan":      { "json"|"ref", "input_fingerprint", "prompt_version" } | null,
  "duration_rec":    { "json", "input_fingerprint", "prompt_version" } | null,
  "outputs": [ { ...metadata..., "edit_plan": {"json"|"ref"}, "cloud_media_id|null" } ]  // edit plan preserved exactly
}
```
`story_doc/1` stays readable (a v1 doc decodes with `derived` absent); `apply()` learns to hydrate `derived`.
Large blobs (big coverage, multi-version edit plans) externalize to the EXISTING media bucket as
`media_kind:"ai_artifact"` objects, checksum-verified, account-scoped — the doc carries a `{cloud_media_id,
sha256}` ref (same mechanism R7-D uses for MP4s, so no new storage system).

## 3. Restore-before-recompute (Phase 2) — the hydration gate
A new **`CloudHydrationGate`** (process-wide, like CoverageRecomputeGate): while a Story's hydration is
pending, the AU / Guide / Coverage / Music queues **must not start inference** for it. Order on Device B:
auth → pull Story index → pull doc(s) → restore Moment shells → restore AU (account table) → restore Guide /
Coverage / Music / Duration / Edit Plans from `derived` → validate fingerprints → **only then** release the
gate so genuinely-missing/invalid state may regenerate. View recreation / relaunch re-checks caches, never
re-infers when fingerprints match.

## 4. Reuse & invalidation policy (Phase 3)
Reuse a cache iff its stored fingerprint matches the device's recomputed input fingerprint AND its
schema/prompt version is COMPATIBLE (not merely equal — a newer model version alone does NOT invalidate; only
input change, schema incompatibility, or dependency mismatch does). User-approved decisions (directives,
user-authored music direction, selected soundtrack, existing validated Edit Plans) are **never** silently
replaced. Existing rendered output → restore MP4, never re-plan for playback.

## 5. Sync safety (Phase 4) — unchanged
All approved R7 safeguards carry over verbatim: server monotonic revision, conditional writes, mutation_id
payload binding, persistent dirty-local, conflict preservation + Keep Both / Use Cloud Version, account-scoped,
no cross-account callbacks, idempotent retry, no silent overwrite, and — now first-class — **no duplicate AI
inference caused by sync** (the hydration gate enforces it).

## 6. New infra + schema + endpoints (what needs approval)
- **New table**: `story-<env>-understanding` (PK story_user_id, SK moment_id, PAY_PER_REQUEST, RETAIN).
- **Schema bump**: `story_doc/1 → story_doc/2` (additive `derived` block; v1 still decodes).
- **New endpoints** (require_user, account-scoped): `GET/PUT /v1/understanding` (batch by moment_ids),
  reuse `GET/PUT /v1/stories/{id}` for the v2 doc, reuse `/v1/media/*` for `ai_artifact` large blobs.
- **CDK**: the understanding table + App Runner RW grant + env var (pure add, like the stories table).
- **No change** to frozen prompts or the `edit_plan/2` contract.

## 7. Engineering estimate (bounded increments, each its own gate)
- **R7-E** backend: understanding table + endpoints + `story_doc/2` derived block + ai_artifact externalize + tests + dev CDK (**STOP before provision**) — ~3–4 d.
- **R7-F** iOS hydration: encode/decode `derived` + AU account sync + CloudHydrationGate (block queues until hydrated) + reuse/invalidation policy + tests — ~5–7 d.
- **R7-C** (resume) two-device metadata + conflict acceptance; **R7-D** generated-MP4 backup (already designed).
- Device acceptance measuring **Bedrock calls on B = 0** for compatible data — ~1–2 d.
- Total for the AI-reuse expansion ≈ **9–13 eng-days** on top of the existing R7-C/R7-D.

## Explicit exclusions
No Edit Planner (`invalid_after_repair`) investigation, no R4-C, no billing, no production, no CI/CD, no
frozen prompt / EditPlan contract change. STOP for approval before provisioning or changing cloud contracts.
