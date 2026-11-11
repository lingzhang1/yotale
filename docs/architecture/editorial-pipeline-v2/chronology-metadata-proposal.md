# Moment capture chronology — audit + minimal compatible proposal

**Status: PROPOSAL for owner review. Not implemented. No schema, request-contract or prompt change has been made.**
Owner decisions needed are listed at the end. Explicit storyboard order and directives always outrank chronology;
import order is never capture order; unknown chronology stays unknown.

Audited at master `71bc307`. iOS paths relative to `apps/ios/Story/Story/` ("iOS/"). Backend paths relative to repo root. Line numbers are as of that HEAD. Read-only audit; the Kendall-τ data point was measured on the dev Story's synced `moment_refs` during the v5.4 evaluation.

## (a) Findings table

| # | Source | Field | Meaning | Reliability | Persisted where | file:line |
|---|---|---|---|---|---|---|
| 1 | In-app camera (ContinuousCamera) | `recordingStart = Date()` at start of recording → event `.recordingFinished(url, duration, started, fix)` | TRUE capture instant (recording start, device clock) | High; device wall clock (user can change system clock; absolute instant, tz offset not stored) | `AssetModel.capturedAt` set after the Moment is created | iOS/Media/Camera/ContinuousCameraController.swift:372, 414, 444; iOS/Features/Capture/ContinuousCaptureModel.swift:630-634, 697, 734 |
| 2 | Same capture, add-only Photos copy | `PHAssetChangeRequest.creationDate = capturedAt` | Writes capture time out to user's Photos | n/a (output only) | Photos | iOS/Media/Photos/PhotosSaver.swift:30-45; ContinuousCaptureModel.swift:762 |
| 3 | Photos import (Story Home picker) | `ImportedMediaMetadata.recover` → AVAsset `commonMetadata` `.commonKeyCreationDate` (string parsed via ISO8601/QuickTime fallbacks, else `dateValue`) | Container-embedded creation date of the picked file. NOT `PHAsset.creationDate`: the picker copies bytes via `loadTransferable(Data)` to a temp `.mov`, add-only auth, no asset id | Medium. Frequently nil (messaging apps/WhatsApp/AirDrop-recompressed/edited exports strip it). Not the Photos "Adjust Date & Time" value (that is DB-only, not in file). Screen recordings carry recording time (a real instant but not "scene" time). Downloaded/exported videos may carry encode/export time. iCloud-optimized originals: picker downloads the file first, metadata same as file. Tz: parsed string with offset → absolute `Date`; offset DISCARDED. | `ImportedMedia.capturedAt` → `AssetModel.capturedAt`; nil when absent | iOS/Media/Photos/ImportedMediaMetadata.swift:14-35, 63-80; iOS/Features/StoryHome/StoryPhotosPicker.swift:60-64, 113-121; iOS/Domain/UseCases/StoryUseCases.swift:273-284 |
| 4 | Photos import (global Library) | same `ImportedMedia.capturedAt` | same as #3 | same as #3 | `asset.capturedAt = item.capturedAt` | iOS/Features/Library/MomentsLibraryView.swift:143-154 |
| 5 | Model comment claims "PHAsset creationDate for an import" | `AssetModel.capturedAt: Date?` | Doc comment is inaccurate vs #3 (no PHAsset read). nil = unknown | n/a | SwiftData, optional/additive | iOS/Data/Persistence/Models.swift:259-263, 298-308 |
| 6 | Import time | `MomentModel.createdAt` (default `.now`) | IMPORT/persist time (or, for a cloud-restored shell, RESTORE time, §gaps G3) | Reliable as what it is; NOT capture time | SwiftData | iOS/Data/Persistence/Models.swift:160, 224-234 (MomentModel), 307 (AssetModel.createdAt) |
| 7 | Link time | `StoryMomentLink.addedAt` (default `.now`) | Time Moment was attached to the Story | Not capture | SwiftData; synced as `added_at` | iOS/Data/Persistence/Models.swift:381-389; iOS/Media/Sync/StoryDocCodec.swift:68 |
| 8 | Story doc sync (write) | `moment_refs[].captured_at` = `asset.capturedAt?.timeIntervalSince1970` (epoch seconds, double; `as Any` of an optional) | Copies capturedAt as-is | Same as source | story_doc/2 cloud doc | iOS/Media/Sync/StoryDocCodec.swift:60-76 |
| 9 | Story doc sync (restore) | `captured_at` read only inside `makeCloudOnlyShell` (new shell Moment) | Restores capturedAt on a brand-new cloud-only shell; shell's `createdAt` = restore time (default `.now`) | Good if source had it. For a Moment that already exists locally, `captured_at` from the doc is NOT applied (existing branch only re-links) | SwiftData | iOS/Media/Sync/StorySyncCoordinator.swift:429-445 (existing path), 451-462 (shell, :459 captured_at) |
| 10 | Upload / backup queues | `MediaUploadQueue`, `GeneratedOutputBackupQueue` sort by `createdAt` for FIFO | Upload ORDER only; no upload timestamp is used as a Moment date | n/a | – | iOS/Media/Upload/MediaUploadQueue.swift:156; iOS/Media/Upload/GeneratedOutputBackupQueue.swift:129 |
| 11 | AU queue | sorts by `createdAt` ascending | Processing order | n/a | – | iOS/Media/AssetUnderstanding/AssetUnderstandingQueue.swift:560 |
| 12 | Scene Scan | no Moment date at all; `Date()` only for scan timing, ephemeral intent `createdAt`, debug feedback `captured_at` (a DEBUG JSON, unrelated to Moments) | – | – | not persisted on Moments | iOS/Features/SceneScan/SceneScanFlowView.swift:432-460; CaptureContext.swift:38; DirectorDebugPanel.swift:89 |
| 13 | Derived/edited outputs | `GeneratedOutputModel.createdAt` (render time); synced `created_at` | Render time; outputs are not Moments and never feed moments[] | n/a | SwiftData / doc | iOS/Data/Persistence/Models.swift (GeneratedOutputModel init `createdAt`); StoryDocCodec.swift:83-88 |
| 14 | Directed capture inside a Story (`shootMoment`) / standalone (`shootStandaloneMoment`) | AssetModel created WITHOUT capturedAt; stamped afterward in `persist` | Window between creation and stamp; if the later stamp is skipped (no `moment.asset`) capturedAt stays nil | – | – | iOS/Domain/UseCases/StoryUseCases.swift:145-165; ContinuousCaptureModel.swift:733-741 |
| 15 | Backend | Zero references to `captured_at` / `capturedAt` anywhere under `apps/api` or `packages` (*.py grep returns nothing). Story doc is stored as an opaque `dict` (`doc: dict`, "story_doc/1 body", main.py:226) | Backend never reads capture time | – | – | apps/api/app/main.py:226 |

Not found anywhere: file `modificationDate`, `importedAt`, `uploadedAt`, `PHAsset` reads, `kCGImagePropertyExif` / EXIF, AVMetadata `quickTimeMetadataCreationDate` / QuickTime `com.apple.quicktime.creationdate` (only the common key is read), and no `tz_offset` persisted anywhere.

## What the planner receives today

- `EditPlanRequestBuilder.build` iterates `story.moments.sorted(by: { $0.createdAt < $1.createdAt })` (iOS/Media/Render/RenderSupport.swift:449) → moments[] order is IMPORT order (createdAt), not `orderIndex`, not capture order. Same sort in `momentsPayload` (:380), `eligibleIds`-style helper (:354), and `MomentResolver.resolve` (:19).
- Per-moment keys sent: `id`, `duration_seconds`, `useful_segments`, `summary`, plus `evidence` (via `evidenceField`) and, when `EditorialTypeFlag.enabled` (default ON, EditorialType.swift:104-110), the v5.3 editorial fields (`editorial`, `events`, `sampled_frame_ms`) (RenderSupport.swift:~476-500, :389-392 for momentsPayload). **No capture time, no day, no rank.** CONFIRMED.
- Ordering semantics in the prompt: the user message (`_build_user`) says nothing about moments[] order meaning; the model therefore sees import order, and may treat it as narrative order (that is the defect).
- Backend schema: `EditPlanRequest` has `extra="forbid"` at top level only (apps/api/app/main.py:375-381); `moments: list[dict]` (main.py:387) and `DurationRequest`-style siblings (:421, :432) are free-form dicts. An extra optional key INSIDE a moment dict is accepted by pydantic with no code change. `EditPlanInputs.moments: list[dict]` (packages/edit_planner/__init__.py:519) is likewise free-form.
- `_build_user` (packages/edit_planner/__init__.py:1350-1400): `_sanitize_moment` — when `not _v53_active()` it REBUILDS the moment dropping only `editorial`, `events`, `sampled_frame_ms` (:1360). A new key would therefore pass THROUGH to the v5.2 prompt unless added to that drop tuple → YES, the v5.2 rollback projection must be extended (add the new key to the tuple at :1360). Under v5.3+ the key rides through unchanged. `_v53_active()` is `float(version) >= 5.3` (:79-87); default `_EDIT_PLAN_DEFAULT = "5"` (:69) so unset env means NOT active until the deployed env selects 5.3+.
- Request is part of the async fingerprint (body-hashed; main.py:1969, :402/:409): adding a key changes the fingerprint ONLY for payloads that carry it, so control (no key) stays byte-identical.
- The repair-turn payload `moments: inputs.moments` (packages/edit_planner/__init__.py:1664) is NOT sanitized at all (pre-existing divergence: editorial/events leak there even under rollback). A new key would appear in repair turns even under v5.2 → must also be projected there (or sanitize centrally).

## Storyboard / explicit ordering interaction

- `MomentSequence` (iOS/Domain/Creation/MomentSequence.swift:1-60): user-arranged ordered UUIDs + policy `allowOthers` (A) / `onlySelected` (B). Persisted as `StoryModel.momentSequenceJSON`, synced as `moment_sequence_json` (StoryDocCodec.swift:~55). Order is expressed to the planner as `must_include` + an `order_after` chain, kept as an OBJECTIVE (never a hard error) (MomentSequence.swift header; backend objective set: packages/edit_planner/__init__.py:173, 193). Policy B restricts moments[] itself (`allowedSourceSetForBuild`, iOS/Domain/Creation/StoryCreationCoordinator.swift:311-322; applied RenderSupport.swift:~437-445 `allowedSourceSet`).
- Hard-ish directives opening/ending/order_after/order_adjacent travel in `revision_context.directives` (packages/edit_planner/__init__.py:395-491 reorder repair; :985 `_DIRECTIVE_KEYS`; :1054 case-insensitive ids).
- Today an inactive sequence = "AI chooses order" with no ordering constraint; chronology is therefore currently an accident of createdAt order. Explicit user order already outranks anything by construction (directives are validated/repaired deterministically); chronology is only advisory prompt context and must stay below directives.

## Data point (measured during the v5.4 evaluation)

Dev Story A028ECD8: 25 `moment_refs.captured_at` span 2026-09-07..09-12; Kendall tau(import order, capture order) = -0.13 → import order is essentially uncorrelated with capture order. The data exist and are already cloud-synced; they are just never sent to the planner.

## (b) Gaps

- G1 Planner never receives capture chronology; moments[] is sorted by import order (RenderSupport.swift:449).
- G2 Sort is by `createdAt`, ignoring `StoryMomentLink.orderIndex` the user/story already has (`story.moments` is link-ordered, Models.swift:173-181, but every payload builder re-sorts by createdAt).
- G3 Cloud-restored shells get `createdAt = .now` at restore (StorySyncCoordinator.swift:451-462 via MomentModel default), so restored Stories' "import order" = restore order, arbitrary and not even import order. `captured_at` is the only surviving chronology.
- G4 `captured_at` from the doc is ignored for Moments that already exist locally (StorySyncCoordinator.swift:436-445), so device B/A drift is possible if one side lacked it.
- G5 Source of capturedAt not recorded (camera vs file metadata vs Photos) → cannot express reliability. Model comment is also wrong about PHAsset (Models.swift:259-263).
- G6 No tz offset persisted; QuickTime string offset discarded at parse (ImportedMediaMetadata.swift:63-80). Day grouping across travel/timezones is therefore device-tz dependent.
- G7 Import reads only `.commonKeyCreationDate`, not `com.apple.quicktime.creationdate` (usually carries the local offset on iPhone files); no EXIF/Photos fallback; no sanity filter (future dates, 1904/1970 epoch zeros, creation after import time) before storing.
- G8 Screen recordings/downloaded/forwarded videos produce misleading but non-nil `capturedAt`; no flag.
- G9 `StoryDocCodec` writes `nil as Any` for unknown captured_at (:74); restored reader treats missing/NSNull as nil (fine) but this is unverified for JSON encoding of Optional-in-Any (not tested here).
- G10 Backend rollback projection (`_sanitize_moment`) and repair payload do not know about any such key (see above).

## (c) Minimal proposal

### Field (per moment, optional, additive)

Recommend relative chronology, not absolute time, in the planner payload:

```json
"chronology": { "rank": 3, "day": 1, "source": "camera_capture" }
```

- `rank`: 1-based position among moments in THIS payload that have a known capture time, sorted by capture instant, ties broken by id. Computed after `allowedSourceSet` filtering so it is dense within what the planner sees.
- `day`: 0-based calendar-day index relative to the earliest known capture in this payload, in the capture's own local calendar when a tz offset is known, else the device's current tz. Lets the planner group "day 1 / day 2" without learning dates.
- `source`: `camera_capture` | `file_metadata` (embedded container creation date) | (`photos_creation_date` reserved; not producible today because no Photos read auth).
- Omit the whole `chronology` key when capturedAt is nil/invalid. Never fill from `createdAt`, `addedAt`, upload time, file mtime, or doc restore time.
- Optional later extension (not v1): `gap_class` (`same_session` <30 min | `same_day` | `later_day`) relative to the previous known moment.

Alternative (simpler, absolute): `captured_at` ISO-8601 UTC + `capture_time_source`. NOT recommended for the planner (privacy below). Persisted/synced `captured_at` stays as is (it is already in the user's own story doc).

### Which to send and why (privacy)

Exact timestamps = personal data (when the user was where/doing what; with lat/long adjacent in the same model they locate a person in time). The planner needs only ORDER and day grouping to reason about "beginning/development/end" and "same outing". Relative rank + day index carries exactly that and no calendar date, no time of day, no timezone, and nothing that can be correlated outside the request. Cost: cannot reason about "sunset/night/New Year's" from timestamp, but the video content (AU) already provides that visually. Decision: send relative only; keep absolute on device/doc.

### iOS fill (never invent)

1. In a single shared helper (e.g. `ChronologyPayload.make(moments:)`), read `moment.asset?.capturedAt`; reject nil, epoch-zero/<2000-ish, > now+1 day.
2. Add optional persisted `AssetModel.captureTimeSourceRaw: String?` (additive migration, nil = legacy/unknown) set at camera persist (`camera_capture`) and import (`file_metadata`); legacy rows with capturedAt but no source: treat as source `unknown_source` and still usable only if user-visible policy allows (recommend: include with `source:"file_metadata"` only if Moment `sourceRaw == existingMedia`, `camera_capture` only if `.directed`; this derives source from the existing `MomentSource` without a migration).
3. (Optional phase 2) persist `captureTzOffsetMin` from the QuickTime `creationdate` string / `TimeZone.current.secondsFromGMT` at recording start for correct day buckets across travel.
4. Attach in `EditPlanRequestBuilder.build` only when a new flag is ON; flag OFF = payload byte-identical to today. Do the same in `momentsPayload` only if the Duration planner is meant to use it (not needed for v1).
5. Do NOT change the existing sort in this step (still createdAt) so moments[] order and image_moment_order stay stable; chronology is carried by `rank`, not by array position. A later step may switch array order to rank (separate, gated).

### Backend acceptance + version gating

- Accepted today with no code change (free-form `list[dict]`, extra=forbid is top-level only).
- In `_build_user` add a version-scoped gate for the NEXT EditPlan version (same pattern as `_v53_active`; v5.4 was not adopted, so the number is the owner's call). In `_sanitize_moment`: when the new version is NOT active, drop `chronology` (extend the v5.2 projection tuple and also strip in the >=5.3 path), so v5.3 and v5.2 behaviours stay byte-identical regardless of what an updated client sends. Also sanitize the repair payload (packages/edit_planner/__init__.py:1664) the same way.
- When the new version is active and any moment has `chronology`: add a short USER-message block (not the frozen system body), emitted only if ≥2 moments carry it, e.g. "Moments carry optional chronology {rank, day}. For FULL STORY, prefer capture order for the narrative unless a user directive says otherwise. moments[] array order is NOT chronological."
- Fingerprint: client-side only changes for payloads carrying the key (body-hashed) → control unaffected. Validator unchanged (chronology is advisory, never a hard error).

### Ordering rules

1. Explicit user order wins: active `MomentSequence`, and directives opening/ending/order_after/order_adjacent/order_pins always override chronology (validator/repair already enforce).
2. Full Story (`editorial_type == "full_story"`): chronology is the DEFAULT narrative order for the moments that have it, unless overridden by (1) or by clear content logic (e.g. a deliberate cold-open). Advisory, not a hard validator rule (consistent with "ordering is an objective").
3. Highlights: not bound by chronology; it may be used only as a tiebreak/variety hint (don't cluster same-day shots). No new instruction beyond "optional".
4. Unknown stays unknown: moments without `chronology` get no inferred position. Mixed known/unknown: order known ones by rank; unknown ones are placed by the model on content logic (suggest: don't force them to the start or end); the prompt must say "absent chronology = unknown, not earliest/latest".
5. If fewer than 2 moments have chronology, omit the block entirely.

### Backward compatibility

- Existing Stories: no migration; chronology is computed at request time from existing `capturedAt`; Stories with all nil get no key (identical request).
- Synced docs: story_doc/2 `captured_at` unchanged; no doc version bump. If `captureTimeSourceRaw`/tz offset are added, write them as additive optional doc keys (readers already ignore unknown keys; older clients ignore them), and fix G4 by letting `captured_at` fill a nil local capturedAt on existing Moments (never overwrite a non-nil).
- Old clients against new backend: never send key → unchanged. New client against old/rolled-back backend: extra key passes pydantic; on v5.2 backend before the projection fix it would leak into the prompt → ship the backend projection BEFORE enabling the client flag.

### Tests needed

iOS (StoryTests):
- chronology payload: nil capturedAt omitted; epoch-zero/future omitted; never falls back to createdAt/addedAt; rank/day correct with ties, cross-midnight, Policy-B restricted set; flag OFF → moments[] JSON byte-identical to a recorded fixture.
- Import: ImportedMediaMetadata parse variants (offset/no offset/garbage), source tagging (camera vs import); restore: `captured_at` applied to shell and fills nil on existing without overwriting; cloud-restored shell with createdAt=now still yields correct rank.
- Doc round-trip: StoryDocCodec with/without captured_at (nil as Any encoding, G9).
Backend (`apps/api/tests`, pattern of `test_edit_plan_v53.py`):
- EditPlanRequest accepts moments with `chronology`; extra top-level key still rejected.
- `_build_user` under version 5.2/5.3: payload with `chronology` produces output byte-identical to the same payload without it (golden); under the new version: key present + directive block present only when ≥2 moments carry it; repair payload also projected.
- Fingerprint: request without the key identical to prior fingerprint.
- Prompt-level eval (offline fixture like dev Story A028ECD8, 25 moments, tau −0.13): Full Story output order tau vs capture order improves; with an active MomentSequence/opening directive the explicit order still wins; Highlights unchanged; mixed known/unknown does not pin unknowns to an end.

## Open decisions for the owner

1. Relative (recommended) vs absolute time to the planner.
2. Whether the array order of moments[] should also change to capture order (separate gated step; affects contact-sheet `image_moment_order` and caching).
3. Day-bucket tz: device-current (v1) vs persisted per-capture offset (phase 2).
