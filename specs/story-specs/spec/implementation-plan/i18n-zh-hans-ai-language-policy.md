# i18n (en / zh-Hans) — Backend AI Language Policy (Stage B)

Status: IMPLEMENTED (backend), offline + fake-gateway tests green. No deploy, no live model call, no prompt-file edit,
no `prompt_version` bump, no model/provider/routing change, no AU / EditPlan prompt-or-schema / evidence change,
no new LLM call. iOS untouched.

## 1. Contract (additive)

Optional request field `content_language` (string) — canonical `en` | `zh-Hans`.
`normalize_content_language` accepts `zh`, `zh-CN`, `zh_CN`, `zh_Hans`, `zh-Hans-CN`, `ZH-hans`, `cmn`, `EN`, `en-US`,
`en_GB` …; anything else (missing, `""`, `fr`, `zh-Hant`/`zh-TW`/`zh-HK`, garbage) → `None` = today's behaviour.
It is a plain `str | None`, so **an unknown string can never cause a 4xx** (only a wrong JSON *type*, e.g. a number,
fails Pydantic as for any field).

Shared pure module: `packages/language_policy/__init__.py`
(`normalize_content_language`, `detect_instruction_language`, `content_language_instruction`,
`reply_language_instruction`, `apply_language_suffix`, `contains_han`, `contains_cjk_or_fullwidth`).

Mechanism: a **runtime-appended suffix** to the system prompt (`system + "\n\n" + suffix`), only when a supported
language is present. `None` ⇒ the system prompt is the unchanged on-disk text (byte-identical). `prompt_version`
strings are not bumped. The suffix keeps every JSON key / id / enum / directive name / schema field as specified, tells
the model not to translate the user's own words, and pins `visual_reference_query` (and any image/video/music SEARCH
QUERY field) to short English keywords.

Also: user-content JSON payloads now use `ensure_ascii=False` (identical for ASCII input) so Chinese reaches the model
as characters rather than `\uXXXX` escapes.

## 2. Endpoints accepting `content_language`

| Route | Request model | Engine / effect |
|---|---|---|
| `POST /v1/story-guide-v2` | `StoryGuideRequest` | `GuideInput.content_language` → suffix on `story_guide/v2` |
| `POST /v1/story-guide` | `StoryGuideRequest` | retired (410) — field accepted, unused |
| `POST /v1/story-guide-refine` | `StoryGuideRefineRequest` | `RefineInput.content_language` → suffix on `story_guide/refine-v1` |
| `POST /v1/story-coverage` | `StoryCoverageRequest` | `CoverageInput.content_language` → suffix |
| `POST /v1/story-coverage/v2` | `StoryCoverageV2Request` | `CoverageV2Input.content_language` → suffix on Mapper **and** Judge |
| `POST /v1/story-coverage/v2/jobs` (+ worker) | `StoryCoverageV2Request` (JSON in `body` form field) | normalized value stored in the job body; `worker.py` forwards it to `CoverageV2Input` |
| `POST /v1/director/initialize` | `DirectorInitializeRequest` | `engine.initialize(..., content_language=)` → suffix on `story_director/v2` |
| `POST /v1/director/next` | `DirectorNextRequest` | `engine.next(prior, content_language=)` |
| `POST /v1/duration-recommendation` | `DurationRecommendationRequest` | `rationale` text → suffix |
| `POST /v1/creative-intent` | `ResolveCreativeIntentRequest` | `summary`/free-text fields → suffix |

Engines receive the kwarg **only when a language was requested**, so existing engines/fakes are called exactly as before.

## 3. Audit — every AI endpoint / prompt

| Endpoint / prompt | English-only assumptions found | Change made | Left alone (why) |
|---|---|---|---|
| story_guide/v2 (`/v1/story-guide-v2`) | Output prose language; `visual_reference_query` must be English; payload JSON ASCII-escaped | Suffix; `ensure_ascii=False`; query exception in suffix | Prompt file, schema, id minting, `visual_reference_query` pass-through unchanged |
| story_guide/refine-v1 | Same; user `user_instruction`/`event_context` rode in ASCII-escaped JSON | Suffix; `ensure_ascii=False` (Chinese instruction/context survive verbatim) | Reconciliation (`reconcile_refinement`) is id-based, language-agnostic |
| story_guide/v1 | retired | none | 410 Gone |
| story_coverage/v1, mapper-v1, story_judgment/v2 | Notes/strengths/redundancies/sufficiency reason/story_idea text language | Suffix on mapper + judge; `ensure_ascii=False` | Info-firewall (`assert_no_guide_leakage`) untouched — it checks ids/keys, `content_language` is never put in Judge evidence; mapper empty-result guard unchanged |
| story_director/v2 (`initialize`/`next`) | Shot text language; **`sanitize_reference_query` regex `[^a-z\- ]+` silently stripped Han → half-query / garbage to the stock provider**; English-only `_UNSAFE_SUBSTRINGS` safety backstop | Suffix; a reference query containing any Han ⇒ unusable (`None` ⇒ text-only card, never raises); Chinese equivalents appended to the unsafe backstop (English entries/behaviour unchanged) | Frozen contracts, shot-id minting, composition matching |
| `/v1/scene-image` (Unsplash) | `normalize_query` dropped Han and searched the remainder | Han in query ⇒ `None` ⇒ existing `{"image":null,"status":"invalid_query"}` (200, provider not called) | Broadening, cache, attribution unchanged |
| `/v1/scene-video` (Pixabay) | Uses `scene_image.normalize_query`; technique classifier uses English cue words | Inherits Han ⇒ `invalid_query`; a Chinese `technique_text` simply classifies as "no requested technique" (fail-soft) | Movement/composition rules unchanged (no Chinese cue table — owner decision) |
| `/v1/music/search`, `/music/candidates` | User-typed free text / MusicPlan vocabulary sent to Epidemic | none | User-typed query is the user's explicit input; MusicPlan vocab protected below |
| music_plan/1 (`/v1/music-plan`) | `mood_tags`/`track_selection_criteria` are *search vocabulary*, matched to an English taxonomy; a Chinese CreativeIntent could make the model emit Chinese tags and silently break ranking; ASCII-escaped payload | When the Story input contains Han, append an "English music-catalog vocabulary only" clause (byte-identical otherwise); `ensure_ascii=False` | Not user-facing ⇒ **no `content_language` field** on `MusicPlanRequest` |
| music_direction (`/v1/music-direction`) | Deterministic, no model | none | No text generation |
| revision_interpret/1 & /2 (`/v1/interpret-revision`) | English-only instruction cues; **`exclude_is_supported` grounding guard keyed on English words ⇒ a legitimate `不要使用片段7` would be flagged `unsupported_exclude` and block submit** | Runtime `CHINESE_GUIDANCE` appended **only** when the instruction has Han/full-width chars (片段N / 第N个片段 / 镜头N / 第N段, Chinese numerals, full-width digits, opening/ending/exclude/must_include/adjacent/after equivalents, `soft_direction` verbatim, worked example); Chinese omission/restriction cues added beside the English tuples (substring match) | Prompt v1/v2 text frozen; ASCII-only instruction ⇒ prompt byte-identical; number→id mapping (server) unchanged; original instruction preserved in user content |
| edit_plan / `/v1/edit-plan`, `-mm`, `-jobs` | Output is a plan (ids/ranges); `rationale` not user-facing; `_classify_unsupported_ops` regexes and the "N seconds" duration regex are English | none (hard rule: no EditPlan prompt/schema change) | Chinese "加滤镜 / 每个片段5秒" are not recognised by those server regexes — iOS capability classifier / interpreter cover them; follow-up if wanted (owner decision) |
| scene_understanding, asset_understanding (AU) | Internal descriptions; semantic guard looks for English directing words | none (AU frozen by hard rule; SU is a Director input, not shown) | — |
| creative_intent/v1 | `summary` etc. language | Suffix when `content_language` present | Chinese `raw_text` already round-trips (no ASCII validators in contracts) |
| duration_recommendation/1 | `rationale` language | Suffix | Deterministic evidence untouched |
| Server-built strings (`Moment N is not in this Story`, grounding/preflight `blocking` reasons) | English | none | Client-side display strings; localising server messages is an owner decision |

"Chinese survives every hop" check: no ASCII-only validators, `isascii`, `encode('ascii')`, upper-casing of free text or
byte-truncation of titles/descriptions/instructions were found on these paths; all `.encode` uses are UTF-8 size limits.
Interpreter lower-casing is applied only to a copy used for cue matching. Covered by tests.

## 4. Caching / idempotency

- Coverage job body is re-serialised from the validated model. `content_language` is **popped and re-added only if it
  normalises to a supported value**, so with the field absent/unknown the stored body and `coverage_payload_fingerprint`
  are byte-identical to before. `zh_CN` and `zh-Hans` collapse to the same key; `en`/`zh-Hans`/absent are three distinct keys.
- No other server-side content cache/idempotency exists for these endpoints (scene-image cache keys on the normalized
  English query only; edit-plan fingerprints are untouched because EditPlan takes no language field).
- Caveat: the *client-chosen* `operation_id` is not changed. Resubmitting the same `operation_id` with a different
  language is a payload conflict (409), by the existing same-id/different-payload rule. The iOS op-id should fold the
  language in (owner/iOS decision).

## 5. OpenAPI / schema snapshots

`contracts/openapi/openapi.json` at HEAD is already **stale vs the live app** (regenerating with
`scripts/export_openapi.py` rewrites ~6,000 lines of unrelated drift), so it was *not* regenerated; committing it would
bury the additive field. `contracts/schemas/*.json` (output contracts) are unchanged — no output contract changed.
The additive optional field is asserted against the live `create_app().openapi()` by
`test_openapi_exposes_optional_content_language_on_expected_requests`. Regenerate the snapshot in its own commit.

## 6. Tests

- `packages/language_policy/tests/test_language_policy.py` — normalization table, detection (en / zh / mixed / Chinese+“Moment 3” / empty / ids), suffix text, byte-identical when `None`.
- `apps/api/tests/test_content_language.py` — suffix present/absent per engine (guide v2, refine, coverage v1/v2 mapper+judge, duration, creative intent, director), Chinese survives request building, Chinese revise → real moment ids with FAKE gateway (system prompt contains the guidance and `从片段3开始，不要使用片段7`), grounding guard (Chinese omission passes, ordering-only exclude still flagged), mixed/full-width instructions, Han queries → graceful `invalid_query`, Chinese unsafe backstop, endpoint kwarg plumbing, unknown language never 4xx, coverage-job key identity/difference, music-plan vocabulary clause, OpenAPI surface.
