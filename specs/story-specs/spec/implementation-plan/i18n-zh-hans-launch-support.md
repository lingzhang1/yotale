# YoTale — English + Simplified Chinese launch support

Status: **IMPLEMENTED offline on `feat/i18n-en-zh-hans`; NOT built in Xcode, NOT device-verified, NOT merged, NOT deployed.**
AI-side detail: [i18n-zh-hans-ai-language-policy](./i18n-zh-hans-ai-language-policy.md).

## 1. Three languages (never conflated)

| Concept | Meaning | Source of truth |
|---|---|---|
| **App language** | All fixed interface text | `AppLanguage` preference: `system | en | zh-Hans` (Settings → globe menu on Home). One `UserDefaults` key `story.appLanguage`. |
| **Input language** | What the user types/speaks to the AI | The user. Preserved verbatim; never translated; never changes the app language. |
| **Content language** | Language of Story-specific generated text (Guide, Shooting Ideas, coverage text) | Derived per request by `ContentLanguageResolver`; sent as optional `content_language`; **never persisted**. |

## 2. App-language architecture

* `App/AppLanguage.swift`: `AppLanguage`, `ResolvedLanguage`, `AppLanguageResolver` (pure), `AppLanguageStore` (`@Observable`, injected at the app root), `L10n` (non-SwiftUI strings), `L10nFormat` (clock/date/number in the app locale).
* `.system` follows `Bundle.main.preferredLocalizations`, so the iOS per-app language setting (Settings ▸ YoTale ▸ Language) keeps working. We never write `AppleLanguages`, so there is no relaunch and no competing source.
* Explicit choice sets `\.locale` at the root (SwiftUI `Text("…")` literals resolve through the String Catalog) and the root view carries `.id(effectiveLanguage)` so strings computed with `L10n.t` refresh. Switching language only resets navigation to Home; Stories, Moments and GeneratedOutputs (SwiftData) are untouched and nothing is regenerated.
* String Catalogs: `Resources/Localizable.xcstrings` (857 keys, en source + zh-Hans, plural variations where a count appears) and `Resources/InfoPlist.xcstrings` (permission prompts). Info.plist strings follow the iOS system/per-app language only (iOS limitation).
* `StoryComponents` (`String`-typed titles) now look text up with `LocalizedStringKey`; non-key text (user titles, AI content) renders verbatim.
* No runtime LLM translation of fixed UI; no remote localization service.

## 3. Localization inventory (before → after)

Before: 0 catalogs, 0 zh-Hans, ~375 SwiftUI literals + ~330 non-SwiftUI user-facing strings (errors, status lines, enums, chips) English-only.
After (static scan, `scripts/i18n/check_catalog.py`): 857 catalog keys; 764 matched to code sites; **0 localized-site literals missing a key**; remaining 93 keys are used through `String`-typed component parameters/ternaries the scanner cannot see.

| Area | Coverage |
|---|---|
| Onboarding / auth / errors | Home, SignIn (+ Cognito/identity errors), Settings (storage, auto backup) — done |
| Story creation / management | CreativeDirection, StoryHome, create preview, Moments manage, Add Moments, photos picker — done |
| Story Guide / coverage / Shooting Idea | chrome localized; AI-generated text follows content language |
| Camera / Scan | ContinuousCapture, SceneScan flow, camera labels, permission explainer, capture-integrity messages — done |
| Customize / storyboard / Create / Revise | CustomizeYourStory, Arrange, Duration, Moment references, prompt chips, ReviseStorySheet — done |
| Music | MusicPicker, ChangeMusic, My Music errors — done |
| Result / playback / restore | StoryResultView, restore/backup messages — done |
| Quotas & errors | EditPlanJobClient quota messages, coordinator errors, service errors — done (technical detail omitted in zh) |
| Permissions | InfoPlist.xcstrings (camera, mic, photos ×2, location) |
| Subscription / payment | none exists in the app |
| Account deletion / privacy disclosures | **no such screens exist yet** (gap to schedule before public launch) |
| Notifications | none in the app |
| Not translated (by design) | user Story titles/descriptions, AI-generated content, DEBUG panels, logs, HTTP/diagnostic strings, machine-facing planner phrases (`QuickShortcut.phrase`, mood soft-direction phrases) |

## 4. Glossary

| English | 简体中文 | Note |
|---|---|---|
| YoTale | YoTale | brand; "Story" as the app's voice → "YoTale" |
| Story | 故事 | |
| Moment | 片段 | |
| Story Guide | 拍摄指南 | |
| Shooting Idea / Shot idea | 拍摄灵感 | |
| Shooting Script | 拍摄脚本 | |
| Highlights | 精彩集锦 | verify width on 4.7" |
| Full Story | 完整故事 | |
| Customize | 自定义 | |
| Create (video) | 生成（视频） | "Create Story" (the object) → 创建故事 |
| Revise | 修改 | **owner to confirm** |
| Explore | 探索 | **owner to confirm** |
| Version / Music / Soundtrack / Mood | 版本 / 音乐 / 配乐 / 氛围 | |
| Back up / Restore | 备份 / 恢复 | |
| Sign in / Sign out | 登录 / 退出登录 | |
| Arrange / Moment sequence | 排序 / 片段顺序 | |
| Internal terms (AU, EditPlan, Edit Planner, must_include, order_after, contact sheet) | never shown | enforced by `contracts/tests/test_ios_localization_catalog.py` |

## 5. Multilingual input handling

* iOS local parsing (`MomentReferenceResolver`) now understands 片段N / 第N个片段 / 第N段, full-width digits, Chinese numerals (一…九十九, 两) and verbs (从…开始, 以…结尾, 不要用/去掉/删除/跳过, 紧接在…之后, 最后用…). English behaviour unchanged (existing tests untouched, new `ChineseInstructionParsingTests`).
* Backend `revision_interpret` receives a runtime Chinese-guidance suffix only when the instruction contains Han/full-width characters; hard directives stay integer Moment numbers resolved against the real Story ids (`从片段3开始，不要使用片段7` → `opening=3, exclude=[7]`, proven with a fake gateway). The grounding guard accepts Chinese omission/restriction cues. Original text is preserved everywhere; nothing is translated before the model.
* Typing in either language never switches the UI.

## 6. Output-language policy (as implemented)

1. Interactive replies: follow the user's instruction language unless asked otherwise (`reply_language_instruction`, defined; no endpoint returns free-text replies today).
2. Story Guide / Shooting Idea / coverage / director / duration / creative-intent: `content_language` resolved by `ContentLanguageResolver`: explicit request ("in English", "用中文") → (reserved: stored Story preference) → dominant language of the substantive Story text (title, description, event context, instruction; ≥2 Han chars or ≥8 Latin letters; URLs ignored; Han characters compared with Latin *words*) → app language.
3. Sent as `zh-Hans`; for English it is sent as `en` **only** when some text contains Chinese, otherwise omitted so pure-English requests are byte-identical to before.
4. AU, EditPlan, music-plan, scene-understanding prompts/schemas/versions: untouched. Search keys (`visual_reference_query`, music/video search) are forced to short English keywords by the same suffix; a query that still contains Han is rejected (text-only card) rather than sent to a provider.
5. Existing Guides/GeneratedOutputs are never regenerated or translated on a language change. New generations pick the language as above. No persisted Story-language field is added (derivation is cheap and migration-free).

## 7. Backward compatibility

* New request field is optional; old clients/Stories work; unknown values are ignored (no 4xx).
* No SwiftData schema change. One new `UserDefaults` key.
* English request bodies, prompts, cache keys and idempotency keys unchanged for pure-English Stories.
* Coverage job idempotency key includes the field only when present. Same `operation_id` with a different language returns 409 by the existing rule; iOS derives `operation_id` from the body, which now contains the language.
* Prompt files and prompt version strings untouched (runtime-appended suffix).

## 8. Test results & bilingual matrix

Automated now (offline): backend `1121 passed` (full suite, with PyJWT installed out-of-tree; repo venv lacks PyJWT so 9 pre-existing modules do not collect there); `contracts/tests` + language tests `144 passed`; static catalog check `0 missing`; `swiftc -parse` clean on every changed Swift file. **Not run:** the Xcode build and the XCTest bundle (the sandbox cannot run the SwiftData macro) — the owner's device build is the authoritative gate.

| # | Case | Automated | Device gate |
|---|---|---|---|
| 1 | EN UI + EN input | existing suites | ☐ |
| 2 | EN UI + ZH input | `ChineseInstructionParsingTests`, backend revise/guide tests | ☐ |
| 3 | ZH UI + ZH input | same + catalog check | ☐ |
| 4 | ZH UI + EN input | content-language tests (`AppLanguageTests`) | ☐ |
| 5–6 | Mixed input (EN/ZH UI) | resolver + interpreter tests | ☐ |
| 7 | Language switch with existing Story | by construction (no data touched) | ☐ switch mid-Story, confirm Guide/outputs intact |
| 8 | Restart / reinstall | `AppLanguageTests` persistence | ☐ (reinstall resets to Follow iPhone) |
| 9 | Saved Guide / GeneratedOutputs | no migration | ☐ open pre-existing Stories |
| 10 | Chinese Moment refs / include / exclude / order | iOS parser tests + backend fake-gateway | ☐ real `/v1` Revise with "从片段3开始，不要使用片段7" |
| 11 | Chinese title/description | guide request tests, `ContentLanguageResolver` tests | ☐ |
| 12 | AI response language consistency | prompt suffix tests | ☐ one live Guide in each language (needs an authorized backend deploy) |
| 13 | Error/quota messages | catalog check | ☐ force quota denial in zh |
| 14 | Camera / shooting instructions | catalog check | ☐ |
| 15 | Small iPhone + Dynamic Type; Xcode pseudolocalization; VoiceOver; clipping | — | ☐ (SE-size sim, AX5, "Double-Length Pseudolanguage", zh VoiceOver) |

### Device checklist for the owner
1. Pull `feat/i18n-en-zh-hans` into the **main** worktree, Clean Build Folder, Cmd-R (SwiftData macro compiles only in Xcode).
2. Home → globe → 简体中文: whole app switches; → English; → Follow iPhone.
3. Settings ▸ YoTale ▸ Language (iOS per-app) set to 简体中文 with "Follow iPhone": app follows.
4. Create a Story with a Chinese description while the app is English: Guide is Chinese, photos still load (English search keys).
5. Revise: "从片段3开始，不要使用片段7" and "Start with Moment 3, drop Moment 7" yield the same plan.
6. Build log: any Xcode "stale/new" entries in `Localizable.xcstrings` indicate an interpolation-type key mismatch (compiler extraction is enabled for the app target) — report them.

## 9. Example outputs

* Chinese UI, quota: "你已达到今天的视频生成上限，请明天再试。" (EN: "You've reached today's limit for creating videos. Please try again tomorrow.")
* Chip insert (zh): `从片段8开始。` / (en) `Start with Moment 8`.
* Guide request (Chinese Story): `{"…","content_language":"zh-Hans"}`; (English Story): field omitted.
* Interpreter (zh) — see AI language-policy doc for the suffix text.

## 10. Remaining ambiguities requiring product approval

1. Glossary: Revise → 修改, Explore → 探索, Highlights → 精彩集锦 (width), Create (video) → 生成 vs 创建.
2. `en` sent explicitly when an English Story contains Chinese text appends the English output suffix to prompts (pure-English unaffected). Acceptable?
3. Chinese error messages intentionally omit technical detail present in English; keep?
4. Language switch resets navigation to Home (`.id`); acceptable for launch?
5. Chinese Story title without spaces fails `hasSufficientGuideContext` (needs 2+ space-separated words) — left unchanged; recommend a script-aware rule as a follow-up.
6. Account-deletion and privacy-disclosure screens do not exist; they need both languages before public launch.
7. Voice: only native keyboard dictation exists (no `SFSpeechRecognizer`/custom STT); Chinese dictation works through the system keyboard. No new voice stack was added.
8. Repo hygiene: `contracts/openapi/openapi.json` was already stale at HEAD (~6k lines drift); regenerate in a separate commit. `apps/api/.venv` lacks PyJWT.
