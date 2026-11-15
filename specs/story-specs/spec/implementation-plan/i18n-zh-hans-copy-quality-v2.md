# YoTale — Simplified Chinese localization quality pass v2

Status: **IMPLEMENTED on `feat/zh-hans-copy-v2` (PR #116) with the owner's final wording decisions; static checks green; iOS test target could NOT run in the agent environment (see §6); physical-device review PENDING (owner). Not merged, not deployed.**
Previous docs: [launch support](./i18n-zh-hans-launch-support.md) · [AI language policy](./i18n-zh-hans-ai-language-policy.md). Follow-up (separate milestone, branch `docs/ai-zh-writing-quality-proposal`, not in this PR): `i18n-zh-hans-ai-writing-quality-proposal.md`.

Scope: Simplified Chinese copy only. English values, catalog keys of existing strings, Moment ids, schemas, endpoints, SwiftData, navigation and AI prompts are unchanged.

## 1. Canonical glossary (owner-approved, final)

| Product concept | 简体中文 | Usage rule |
|---|---|---|
| Moment / Moments (product entity) | **瞬间** | library, picker, ordering, selection, counts, chips, errors, accessibility. Counts: `%lld 个瞬间` |
| Moment number | **瞬间 8** in compact labels/chips · **第 8 个瞬间** in complete sentences | compact = `L10n.t("Moment \(n)")`; sentence = `L10n.momentInSentence(n)` (key `Moment %lld (in a sentence)`, English value `Moment %lld`). Both parse to the same stable Moment id |
| Story | 故事 | |
| Story Guide / "Your Shooting Script" | 拍摄指南 | |
| Shooting Idea | 拍摄灵感 | |
| Scene / Shot | 场景 / 镜头 | |
| Actual clip / excerpt | 片段 | only where the English says *clip* |
| Final made video | 影片 | creation, result, versions, quota. **视频** stays for files, imports, downloads, restore, examples |
| Highlights / Full Story | 精彩集锦 / 完整故事 | |
| Create (video) | 制作 (影片) | 创作 for "再创作一个版本"; 生成 only for generated guides |
| Revise | **调整影片** (canonical) | 调整 only where the object is unambiguous (inside the Revise sheet: "想怎么调整？", "正在调整 V2") |
| Arrange Moments | **调整顺序** inside the Moment-sequence UI (sheet title, the sequence row button) · **调整瞬间顺序** standalone (Customize shortcut chip), in messages that name that chip, and in accessibility | sheet title uses key `Arrange Moments (sheet title)` (English value `Arrange Moments`) |

## 2. Inventory and classification

| Class | Where | This pass |
|---|---|---|
| Static iOS localization | `Localizable.xcstrings` (875 keys), `InfoPlist.xcstrings` | 343 zh values changed or added vs master |
| Parameterized counts/status | plural / positional keys | re-checked; numbers separated from Han by a space; positional args where order differs; Moment-name placeholders (`%@` = "第 8 个瞬间") have no padding spaces |
| Backend-provided user-facing text | `/v1/interpret-revision` `blocking` (preflight + grounding) and server `unresolved` | presentation mapping (§5) |
| AI-generated content | Guide/Director/Coverage/Creative-Intent/duration rationale | untouched; see the separate proposal |
| User-created text | titles, descriptions, event context, typed instructions | untouched |

## 3. Key fixes

**"穿裙子的女孩 中共 20 个"** — `MomentsManageView` already used a typed format string (`%lld in %@`, Int + String); the translation `%2$@ 中共 %1$lld 个` produced the bug. Now `%2$@ · %1$lld 个瞬间`; library `共 %lld 个`. Outputs: 0 → "共 0 个" / "… · 0 个瞬间"; 1, 2, 20, 682 likewise (no plural variants needed in either language).

**Coverage status** (`NarrativeCoverageDTO`, computation unchanged):

| State | Contract meaning | Label |
|---|---|---|
| `strong` | "the dimension's purpose is already well served by the understood material" — may be satisfied by a *different composition* that serves the purpose (prompts/story_coverage/v2) | **素材充足** (owner decision; was 已拍摄) |
| `looking_good` | good material meaningfully serves it; more optional | **已有相关素材** |
| `could_use_more` | relevant; more would help | 可以多拍一些 |
| `unknown` / none yet | — | 尚未拍摄 |

**Semantic mismatch to report (no backend change made):** `strong` is purpose-based, not shot-based. The coverage model may mark a scene `strong` when other footage serves the scene's purpose even though that exact scene was never shot, so 「已拍摄」 can overclaim. The English "Covered" has the same nuance but reads as coverage, not capture. Options for the owner: keep 已拍摄 (user-friendly, slight overclaim), or use 「已拍够」/「这部分已够用」 (purpose-based). No code change pending a decision.

**Story home** — 去拍摄 (opens camera) · 制作影片 (opens create flow) · 「可以把这些瞬间剪成影片了。」 only in `.ready` · empty Story 「故事已建好，去拍下第一个瞬间吧。」 · Story completion stays separate from video creation.

## 4. Instruction parsing
`MomentReferenceResolver` accepts 瞬间N / 瞬间 N / 第N个瞬间 / 第 N 个瞬间 / 第三个瞬间 plus the existing 片段 forms. Bare 瞬间 + a Chinese numeral is not a reference ("那一瞬间十分感人" ≠ Moment 10). Chip text 「从瞬间 8 开始」 and sentence text 「从第 8 个瞬间开始」 resolve to the same stable id (test `testCompactAndSentenceFormsResolveToSameMoment`).

## 5. Backend messages — localization must not hide details
`ServerMessageLocalizer` (iOS-only, presentation). Chinese UI only; English UI byte-identical.
- Known `blocking` templates keep their actionable detail: the internal Moment UUID is replaced by the Moment's **display number** from the screen's numbering snapshot ("第 3 个瞬间既被要求保留，又被要求去掉。"), the remaining count is kept ("只剩 1 个可用"), and both Moments of a contradictory ordering are named.
- An id the snapshot cannot resolve becomes 「某个瞬间」 (a raw UUID is not actionable).
- An **unknown** English reason is shown as 「这个要求有冲突，请调整后再试。（<original server text>）」 — never dropped.
- `unresolved` clauses (the user's own words, any language) are never rewritten; only the server's "Moment N is not in this Story" becomes 「这个故事里没有第 N 个瞬间。」.
- Other user-facing error copy audited: zh omits only non-actionable technical detail (HTTP codes inside some network errors keep their code; e.g. 「收到意外的响应（503）」). The AU quota message drops the raw scope token (e.g. `user_daily`) in zh; the English shows it raw. Pre-existing English issue: some English preflight messages show internal Moment UUIDs.

## 6. Verification

| Check | Result |
|---|---|
| `xcodebuild test -scheme Story -only-testing:StoryTests/ChineseInstructionParsingTests -only-testing:StoryTests/AppLanguageTests` (iPhone 16e simulator, Xcode 27.2, private DerivedData) | **Could not run: build failed before tests** — every Swift macro (`@Model`, `@Query`, `@State`, `@Observable`) fails with "swift-plugin-server produced malformed response". This is the agent sandbox's known macro limitation, not a code error. The owner's Xcode run is the authoritative gate |
| Standalone parser harness (resolver + MomentSequence + JSONValue compiled with `swiftc`) | 26/26 pass: every new 瞬间/第 N 个瞬间 case, compact-vs-sentence same-id, ordering, prose false-positives, 片段 and English regressions |
| Standalone localizer harness (stubbed `L10n`) | 10/10 pass: id→display-number, unknown-id fallback, remaining count, contradictory pair, unknown reason keeps text, user clause untouched, English pass-through |
| `scripts/i18n/check_catalog.py` | 875 keys, 0 localized sites missing a key; zh never adds a format specifier |
| `contracts/tests` (incl. catalog guards: 瞬间 not 片段, no 中共, coverage labels, alias keys keep English, owner decisions) | 69 passed |
| English regression | key-by-key: no English value changed or removed; the 2 alias keys carry English identical to the originals |
| `swiftc -parse` | clean on every changed Swift file |

### Permission prompts (Info.plist) — privacy meaning

| Key | English (unchanged) | 简体中文 | Meaning preserved? |
|---|---|---|---|
| Camera | Story uses the camera to capture your moments. | YoTale 需要使用相机来记录你的瞬间。 | yes |
| Microphone | Story records audio with your video moments. | YoTale 会在你拍摄视频时录制声音。 | yes (audio only while recording video) |
| Photos (add) | Story saves a copy … so you own them outside Story. | YoTale 会把你拍下的瞬间另存一份到“照片”，即使不用 YoTale，它们也依然属于你。 | yes |
| Location | … optional and never added to the videos you share. | … 定位是可选的，也不会出现在你分享的影片里。 | yes (matches English; no extra claim) |
| Photos (read) | Story can import existing photos and videos. | YoTale 可以导入你已有的照片和视频。 | unchanged |

**Privacy finding (English too, not changed):** the in-app location explainer says location "stays on your device". Recorded originals embed ISO-6709 GPS metadata (`ContinuousCameraController.locationMetadata`), Auto Backup uploads the original file, and "Save to Photos" sets the asset location. So with backup or Photos save on, location does leave the app's local store. The Chinese mirrors the English ("只保存在你的设备上"). Recommend an owner decision on the English wording (e.g. "stays with your Moments and is never added to the videos you share"), then the zh follows.

## 7. Physical-device screenshot checklist (owner)
Build `feat/zh-hans-copy-v2` from the main checkout (Pull, Clean Build Folder, Cmd-R). App language 简体中文 unless noted; capture full screens.

| # | Screen / state | Expect |
|---|---|---|
| 1 | Homepage | 灵感拍摄 / 拍下眼前的精彩 / 打开镜头，让 AI 帮你找到更好的拍法。 · 故事创作 / 把瞬间，变成故事 / 从一个想法开始… · 瞬间 · 珍藏每一个瞬间 · 故事 · 你的故事，都在这里 |
| 2 | Moments library (682) | title 瞬间, subtitle 共 682 个; Select → 选择, 已选 N 个瞬间, 备份/删除 N 个瞬间 + confirm dialogs |
| 3 | Story gallery (穿裙子的女孩, 20) | 穿裙子的女孩 · 20 个瞬间; + 添加瞬间; remove dialog 移除这个瞬间？ |
| 4 | Empty states | library 还没有瞬间 + 拍下或导入一些照片、视频，故事就从这里开始。; empty Story home 故事已建好，去拍下第一个瞬间吧。 |
| 5 | Story Home (ready) | 你的故事，正慢慢成形。 · N 个瞬间 → · 去拍摄 · 制作影片 · 可以把这些瞬间剪成影片了。 · pending state 「N 个已就绪 · N 个仍在分析中」 |
| 6 | Story Guide | 拍摄指南 · 共 N 个场景 · 调整指南 / 说说你想调整什么 · 场景 01 · 开场 · 这样拍 · 为什么拍这一幕 · 去拍摄 → · 更多场景 · statuses 尚未拍摄 / 可以多拍一些 / 已有相关素材 / 素材充足 (confirm a scene with no footage never shows 已拍摄) |
| 7 | Customize | 制作你的影片 · 告诉 AI，你想怎么剪。 · 影片类型 精彩集锦 / 完整故事 + blurbs · chips 调整瞬间顺序, 从某个瞬间开始, 用某个瞬间结尾, 包含所有瞬间 · row 瞬间顺序 + 调整顺序 · 交给 AI 安排 · 影片氛围 · 不指定 · 音乐与原声平衡 · 开始制作 |
| 8 | Arrange sheet | title 调整顺序 · tiles 瞬间 3 · disclosure 「第 3 个瞬间作为开场，第 5 个瞬间作为结尾。第 3、5 个瞬间会按这个顺序…」 · VoiceOver on a tile: 移动第 3 个瞬间 |
| 9 | Typed instruction | type 「从第 3 个瞬间开始，去掉瞬间 7」 → saved lines 从第 3 个瞬间开始 / 去掉第 7 个瞬间; same result as chip 「从瞬间 3 开始」 |
| 10 | Conflict message | sequence starts with Moment 2, type 「从瞬间 5 开始」 → 「你的文字要求从第 5 个瞬间开始，但当前顺序的开头是第 2 个瞬间。请在“调整瞬间顺序”中…」 |
| 11 | Camera + Shooting Idea | 存入瞬间 / 存入 <Story> · 获取 AI 拍摄灵感 · 查看取景 · 视觉灵感 · 并非你的实际画面 · location dialog |
| 12 | Revise | result card 调整影片 / 说说想怎么改 · sheet title 调整影片 · 想怎么调整？ · when the server blocks a request, the Chinese reason names the Moment by number (第 N 个瞬间), never a raw id; an unrecognised reason still shows the original text in （） |
| 13 | Creating / result / versions | 正在制作你的影片… stages · 你的影片做好了 · 再创作一个版本 · 新版本做好了 |
| 14 | Errors / quota | airplane mode → 无法连接 YoTale… · quota → 今天的影片制作次数已用完，请明天再来。 |
| 15 | Permission prompts | fresh install: camera, microphone, photos add, location in Chinese |
| 16 | Small iPhone + Dynamic Type AX3 | no truncated CTA: 把瞬间，变成故事, 再创作一个版本, 调整瞬间顺序 chip, 音乐与原声平衡 |
| 17 | English pass | switch to English: Home, library "682 in your library", gallery "20 in <title>", Arrange title "Arrange Moments", sentence "Moment 3 will open the video" — all unchanged |
| 18 | Xcode build log | no new "stale"/"new" entries in `Localizable.xcstrings` (would indicate a placeholder-type mismatch) |

## 8. Owner decisions applied (final)
1. `looking_good` → 已有相关素材 (calculation unchanged; `strong` mismatch reported in §3).
2. 瞬间 8 compact / 第 8 个瞬间 in sentences; same id; prose protection kept.
3. 调整影片 canonical; 调整 only where unambiguous.
4. 调整顺序 inside the sequence UI; 调整瞬间顺序 standalone / messages / accessibility.
5. AI Chinese style → separate milestone; no prompt change in this PR.

Open: location-explainer English wording (§6).

## 9. Before / after (all zh-Hans values changed vs master 575e81e)

| English key | Before (master 575e81e) | After |
|---|---|---|
| %@ after %@ | %1$@ 在 %2$@ 之后 | %1$@在%2$@之后 |
| %@ are still being analyzed. Give them a moment, then create your Story — your instruction is saved. | %@ 仍在分析中。稍等片刻再生成故事吧——你的要求已保存。 | %@还在分析中。稍等一下再制作影片，你的要求已保存。 |
| %@ can't come right after several Moments. | (new key) | %@不能同时紧跟在多个瞬间之后。 |
| %@ couldn't be matched (this Story has %lld). Choose Moments with “Arrange Moments”, or rephrase. | 无法匹配 %1$@（这个故事共有 %2$lld 个片段）。请通过“排序片段”选择片段，或换种说法。 | 找不到%1$@（这个故事共有 %2$lld 个瞬间）。请用“调整瞬间顺序”选择瞬间，或换种说法。 |
| %@ couldn't be matched (this Story has %lld). Reposition it with “Arrange”, or rephrase. | 无法匹配 %1$@（这个故事共有 %2$lld 个片段）。请用“排序”调整位置，或换种说法。 | 找不到%1$@（这个故事共有 %2$lld 个瞬间）。请用“调整顺序”调整位置，或换种说法。 |
| %@ is asked to be both kept and removed. | (new key) | %@既被要求保留，又被要求去掉。 |
| %@ is both in your arranged order and asked to be dropped. Remove it from the order, or don’t drop it. | %@ 既在你排好的顺序中，又被要求去掉。请把它从顺序中移除，或不要去掉它。 | %@既在你排好的顺序里，又被要求去掉。请把它移出顺序，或者保留它。 |
| %@ is in your Moment sequence but your text asks to drop it. Remove it from the sequence, or edit the text. | %@ 在你的片段顺序中，但你的文字要求去掉它。请把它从顺序中移除，或修改文字。 | %@在你的瞬间顺序里，但文字要求去掉它。请把它移出顺序，或修改文字。 |
| %@ is removed but also used in your ordering. | (new key) | %@已被去掉，却仍出现在你的顺序要求里。 |
| %@ is still being analyzed. Give it a moment, then create your Story — your instruction is saved. | %@ 仍在分析中。稍等片刻再生成故事吧——你的要求已保存。 | %@还在分析中。稍等一下再制作影片，你的要求已保存。 |
| %@ is the ending but another Moment is placed after it. | (new key) | %@是结尾，后面却还排了别的瞬间。 |
| %@ is the opening but is also placed after another Moment. | (new key) | %@是开场，却又被排在另一个瞬间之后。 |
| %@ isn't in this Story. | (new key) | %@不在这个故事里。 |
| %@ isn’t in your selected Moments. Add it in Arrange, or remove the mention. | %@ 不在你选中的片段里。请在“排序”中添加，或删掉这处提及。 | %@不在你选中的瞬间里。请在“调整顺序”中添加它，或删掉这处提及。 |
| %@ isn’t in your sequence, which is set to “Use only the selected Moments”. Add it in Arrange Moments, change that setting, or edit the text. | %@ 不在你的顺序中，而顺序已设为“只使用选中的片段”。请在“排序片段”中添加它、更改该设置，或修改文字。 | %@不在你的顺序里，而你选择了“只用选中的瞬间”。请在“调整瞬间顺序”中添加它、更改这个设置，或修改文字。 |
| %@ right after %@ | %1$@ 紧接在 %2$@ 之后 | %1$@紧接在%2$@之后 |
| %@ will open the video | %@ 将作为开场 | %@作为开场 |
| %@ will open the video and %@ will end it | %1$@ 将作为开场，%2$@ 将作为结尾 | %1$@作为开场，%2$@作为结尾 |
| %@. Moments %@ are required in this intended order; the editor may include other Moments between them, and keeps your order when the footage allows. | %1$@。片段 %2$@ 需要按此顺序出现；剪辑可能会在它们之间穿插其他片段，并在素材允许时保持你的顺序。 | %1$@。第 %2$@ 个瞬间会按这个顺序出现；AI 可能在它们之间穿插其他瞬间，素材允许时会保持你的顺序。 |
| %@. Moments %@ will follow this intended order. The rest of your video stays as it is. If the footage can't fully allow it, the result says so rather than forcing it. | %1$@。片段 %2$@ 将按此顺序排列，视频的其余部分保持不变。如果素材无法完全满足，结果会如实告知，而不会强行处理。 | %1$@。第 %2$@ 个瞬间会按这个顺序排列，影片的其他部分保持不变。如果素材无法完全满足，结果会如实说明，不会硬凑。 |
| %@. Only Moments %@ will be used, in this intended order. The editor keeps your order when the footage allows; if it can't fully honor it, the result is shown honestly rather than forced. | %1$@。只会使用片段 %2$@，并按此顺序排列。素材允许时会保持你的顺序；如果无法完全做到，结果会如实呈现，而不会强行处理。 | %1$@。只使用第 %2$@ 个瞬间，并按这个顺序排列。素材允许时会保持你的顺序；如果无法完全做到，会如实呈现结果，不会硬凑。 |
| %lld in %@ | %2$@ 中共 %1$lld 个 | %2$@ · %1$lld 个瞬间 |
| %lld in your library | 片段库中共 %lld 个 | 共 %lld 个 |
| %lld moments | %lld 个片段 | %lld 个瞬间 |
| %lld Moments | %lld 个片段 | %lld 个瞬间 |
| %lld moments couldn't be analyzed | 有 %lld 个片段分析失败 | 有 %lld 个瞬间分析失败 |
| %lld Moments selected | 已选择 %lld 个片段 | 已选 %lld 个瞬间 |
| %lld moments → | %lld 个片段 → | %lld 个瞬间 → |
| %lld of %lld moments ready. | %lld/%lld 个片段已就绪。 | 已就绪 %lld/%lld 个瞬间。 |
| %lld scenes | %lld 个场景 | 共 %lld 个场景 |
| %lld–%llds fits your footage | %lld–%lld 秒适合你的素材 | %lld–%lld 秒最适合你的素材 |
| + Add Moments | + 添加片段 | + 添加瞬间 |
| A concise highlights length | 简短的精彩集锦时长 | 精简的集锦时长 |
| A guide, not a checklist — capture what feels right. | 这只是参考，不是清单——拍你觉得对的画面。 | 这只是参考，不是任务清单，拍你觉得对的画面就好。 |
| a Moment | 某个片段 | 某个瞬间 |
| A moment worth capturing | 值得拍下的瞬间 | 值得拍下的一幕 |
| A Moment your instruction refers to isn't available on this device. Edit your instruction, or wait for it to finish syncing. | 你的要求提到的某个片段在此设备上不可用。请修改要求，或等待同步完成。 | 你提到的某个瞬间在这台设备上不可用。请修改要求，或等同步完成。 |
| A new version is being created | 正在生成新版本 | 正在创作新版本 |
| A referenced Moment is no longer in this Story. | 你提到的某个片段已不在这个故事中。 | 你提到的某个瞬间已不在这个故事里。 |
| A video is already being created for this Story. | 这个故事已有视频正在生成中。 | 这个故事已有影片正在制作中。 |
| A video is already being created for this Story. Please wait a moment and try again. | 这个故事已有视频正在生成中，请稍候再试。 | 这个故事已有影片正在制作中，请稍后再试。 |
| Add %lld | 添加 %lld | 添加 %lld 个 |
| Add a little about your event and your shooting script will appear. | 简单写写这次的活动，你的拍摄脚本就会出现。 | 简单写写这次要拍什么，拍摄指南就会出现。 |
| Add instruction: %@ | 添加指令：%@ | 添加要求：%@ |
| Add Moment reference | 添加片段引用 | 引用瞬间 |
| Add Moments | 添加片段 | 添加瞬间 |
| Add Moments below to arrange them yourself. | 在下方添加片段，自己安排顺序。 | 在下方添加瞬间，自己安排顺序。 |
| Adds every Moment to the sequence in their current order | 按当前顺序把所有片段加入序列 | 按当前顺序加入所有瞬间；每个瞬间通常只截取其中一段，而不是完整素材 |
| Adds to %@ | 添加到 %@ | 存入 %@ |
| Adjust instructions | 调整指令 | 调整要求 |
| AI can include other Moments between these | AI 可在这些片段之间穿插其他片段 | AI 可以在这些瞬间之间穿插其他瞬间 |
| AI chooses order | 由 AI 决定顺序 | 交给 AI 安排 |
| Almost there — crafting your Story carefully. This can take a minute or two. | 快好了——正在精心制作你的故事，可能需要一两分钟。 | 快好了，正在精心打磨，可能还需要一两分钟。 |
| Analyzing moments… | 正在分析片段… | 正在分析瞬间… |
| Analyzing your Moments | 正在分析你的片段 | 正在分析你的瞬间 |
| Anything you want to include? | 有什么想加入的吗？ | 想让影片怎么呈现？ |
| Apply supported | 应用支持的部分 | 应用可行部分 |
| Apply supported parts? | 只应用支持的部分？ | 只应用能做到的部分？ |
| Applying your change; the rest of the edit is kept. | 正在应用你的修改，其余剪辑保持不变。 | 正在应用你的调整，其余部分保持不变。 |
| Arrange | 排序 | 调整顺序 |
| Arrange Moments | 排序片段 | 调整瞬间顺序 |
| Arrange Moments (sheet title) | (new key) | 调整顺序 |
| Auto Back Up My Moments | 自动备份我的片段 | 自动备份我的瞬间 |
| Back up %lld moments | 备份 %lld 个片段 | 备份 %lld 个瞬间 |
| Back up %lld moments to your account? | 要将 %lld 个片段备份到你的账号吗？ | 要把这 %lld 个瞬间备份到你的账号吗？ |
| Back up Moments not yet backed up? | 备份尚未备份的片段？ | 备份尚未备份的瞬间？ |
| Back Up Moments Not Yet Backed Up… | 备份尚未备份的片段… | 备份尚未备份的瞬间… |
| Backing up an existing Moment associates it with THIS account and removes it from other accounts' Moments libraries on this phone. | 备份现有片段后，它会与当前账号关联，并从这部手机上其他账号的片段库中移除。 | 备份已有的瞬间后，它会归属当前账号，并从这台手机上其他账号的瞬间中移除。 |
| Balanced sound | 均衡声音 | 音乐与原声平衡 |
| Beautiful views first | 先展示美景 | 美景先行 |
| Build a meaningful story from your moments, with a clear beginning, progression, and ending. | 用你的片段串起一个有意义的故事，起承转合清晰完整。 | 用你的瞬间讲一个完整的故事，开头、发展、结尾都清晰。 |
| Can't do that edit yet | 暂时无法完成这个修改 | 暂时做不到这种调整 |
| Cancel move of Moment %lld | 取消移动片段%lld | 取消移动第 %lld 个瞬间 |
| Capture | 拍摄 | 灵感拍摄 |
| Capture a Moment | 拍摄片段 | 拍下眼前的精彩 |
| Capture a moment to start your library. | 拍摄一个片段，开始建立你的片段库。 | 拍下或导入一些照片、视频，故事就从这里开始。 |
| Capture naturally as you go — your guide will appear shortly. | 顺其自然地拍摄就好——拍摄指南很快就会出现。 | 边走边拍就好，拍摄指南马上就来。 |
| Capture naturally as you go. A guide, not a checklist — capture what feels right. | 顺其自然地拍摄就好。这只是参考，不是清单——拍你觉得对的画面。 | 边走边拍就好。拍摄指南只是参考，拍你觉得对的画面。 |
| Capture something worth remembering. Get an AI shot idea whenever you want. | 记录值得珍藏的瞬间，随时获取 AI 拍摄灵感。 | 打开镜头，让 AI 帮你找到更好的拍法。 |
| Checking the plan… | 正在检查方案… | 正在检查剪辑方案… |
| Choose a length for your Story. | 为你的故事选择时长。 | 选择影片时长。 |
| Choose how you want your moments to come together. | 选择你想让片段如何组合在一起。 | 告诉 AI，你想怎么剪。 |
| Choose the Moments you want to reposition, then drag to arrange them. Everything else in your video stays as it is. | 选择想要调整位置的片段，然后拖动排序。视频的其余部分保持不变。 | 选出想调整位置的瞬间，再拖动排序。影片的其他部分保持不变。 |
| Choose the Moments you want to show, then drag to arrange them. | 选择想要展示的片段，然后拖动排序。 | 选出想放进影片的瞬间，再拖动排序。 |
| Clear — no preference | 清除——不限 | 清除，不指定 |
| Clears the sequence so the editor chooses the order | 清除顺序，由剪辑自动决定排序 | 清空顺序，交给 AI 安排 |
| Clears the sequence so your current order is kept | 清除顺序，保持当前排序 | 清空顺序，保持现有顺序 |
| Cloud-only Moments | 仅在云端的片段 | 仅存于云端的瞬间 |
| Collect moments, tell your story, and create a film. | 汇集片段，讲述你的故事，生成一部短片。 | 从一个想法开始，记录沿途的精彩，慢慢拼出你的故事。 |
| Completed · %lld moments | 已完成 · %lld 个片段 | 已完成 · %lld 个瞬间 |
| Could use more | 还可以多拍一些 | 可以多拍一些 |
| Couldn't assemble the creation request: %@ | 无法准备生成请求，请重试。 | 无法准备制作请求，请重试。 |
| Couldn't build the music request: %@ | 无法生成音乐请求，请重试。 | 无法准备音乐请求，请重试。 |
| Couldn't finish the new version | 未能完成新版本 | 新版本没能完成 |
| Couldn't interpret that right now. | 暂时无法理解这条指令。 | 暂时没能理解这条要求。 |
| Couldn't re-render with the new music (%@). | 无法用新音乐重新生成视频。 | 没能用新音乐重新制作影片。 |
| Couldn't reach Story for Moment analysis. | 无法连接 YoTale 分析片段。 | 无法连接 YoTale，暂时不能分析瞬间。 |
| Couldn't read the saved edit for this video. | 无法读取这个视频已保存的剪辑。 | 无法读取这部影片已保存的剪辑。 |
| Couldn't revise | 无法修改 | 没能调整影片 |
| Couldn't save that clip | 无法保存这段视频 | 这段视频没能保存 |
| Couldn't update just now — your current guide is unchanged. Try again. | 暂时无法更新——当前指南保持不变，请重试。 | 暂时没能调整，当前指南保持不变，请重试。 |
| Covered | 已拍到 | 已拍摄 |
| Create | 生成 | 故事创作 |
| Create a %lld-second Story | 生成 %lld 秒的故事 | 制作 %lld 秒的影片 |
| Create Another Version | 生成另一个版本 | 再创作一个版本 |
| Create my Story | 生成我的故事 | 制作影片 |
| Create my video | 生成我的视频 | 开始制作 |
| Create without music | 不加音乐生成 | 不加音乐直接制作 |
| Create Your Video | 生成你的视频 | 制作你的影片 |
| Create · %llds | 生成 · %lld 秒 | 制作 · %lld 秒 |
| Created without music | 未添加音乐 | 无配乐 |
| Creating a new version. %@ Your current video is still available. | 正在生成新版本。%@ 当前视频仍可使用。 | 正在创作新版本。%@ 当前影片仍可观看。 |
| Creating your Story… | 正在生成你的故事… | 正在制作你的影片… |
| Creation failed. | 生成失败。 | 制作失败。 |
| Delete %lld moments | 删除 %lld 个片段 | 删除 %lld 个瞬间 |
| Delete %lld moments from your library? | 要从片段库中删除 %lld 个片段吗？ | 要删除这 %lld 个瞬间吗？ |
| Describe changes | 描述修改内容 | 说说想怎么改 |
| Double-tap another Moment to place this before it | 双击另一个片段，即可把它放在该片段之前 | 双击另一个瞬间，把它放到那个瞬间前面 |
| Double-tap, then double-tap another Moment to place this before it | 双击，再双击另一个片段，即可把它放在该片段之前 | 双击选中，再双击另一个瞬间，把它放到那个瞬间前面 |
| Downloading the exact video from your account. It isn't being re-created. | 正在从你的账号下载原视频，不会重新生成。 | 正在从你的账号下载原来的影片，不会重新制作。 |
| Each track shapes a different edit — Story cuts the moments and pacing to fit. | 每首曲目都会带来不同的剪辑效果——YoTale 会根据音乐调整片段和节奏。 | 不同的曲子会剪出不同的影片，YoTale 会根据音乐调整画面和节奏。 |
| Edit Story details | 编辑故事详情 | 编辑故事信息 |
| Editing %@ | 正在修改 %@ | 正在调整 %@ |
| Editing capabilities | 可编辑内容 | 能做哪些调整 |
| End with %@ | 以 %@ 结尾 | 用%@结尾 |
| End with… | 以…结尾 | 用某个瞬间结尾 |
| Everything from your Story, in one place. | 你的故事，尽在这里。 | 这个故事的一切，都在这里。 |
| Exclude %@ | 排除 %@ | 去掉%@ |
| Finishing up… | 即将完成… | 马上就好… |
| Follow the music | 跟随音乐 | 跟着音乐走 |
| Freed %@ from %lld moments. | 已从 %2$lld 个片段中释放 %1$@。 | 已从 %2$lld 个瞬间中释放 %1$@。 |
| From Story Moments | 从已有片段选择 | 从已有瞬间选择 |
| Getting your moments ready… | 正在准备你的片段… | 正在准备你的瞬间… |
| Hang tight — this usually takes a moment. | 请稍候——通常很快就好。 | 请稍候，通常很快就好。 |
| How should your Story feel and sound? | 你希望故事听起来是什么感觉？ | 影片想要什么样的感觉和声音？ |
| How to capture it | 拍摄方法 | 这样拍 |
| How to shoot | 拍摄方法 | 这样拍 |
| I couldn't finish your Story. | 未能完成你的故事。 | 这次没能完成你的影片。 |
| I couldn't put together a valid edit this time — this is on my side, not your footage. Please try again. | 这次未能生成有效的剪辑——问题出在我这边，与你的素材无关。请重试。 | 这次没能剪出可用的版本，问题出在我这边，不是你的素材。请重试。 |
| I couldn’t apply: “%@”. Try rephrasing it, or use “Arrange Moments” to set the order. | 无法应用：“%@”。请换种说法，或用“排序片段”设置顺序。 | 没能应用“%@”。请换种说法，或用“调整瞬间顺序”来设置。 |
| I couldn’t apply: “%@”. Try rephrasing it, or use “Arrange” to set the order. | 无法应用：“%@”。请换种说法，或用“排序”设置顺序。 | 没能应用“%@”。请换种说法，或用“调整顺序”来设置。 |
| Immersive | 沉浸 | 现场感 |
| Immersive sound | 沉浸声音 | 突出现场声音 |
| Include %@ | 包含 %@ | 包含%@ |
| Let's adjust your instruction. | 我们来调整一下你的指令。 | 调整一下你的要求吧。 |
| Library options | 片段库选项 | 更多选项 |
| Looking strong | 看起来不错 | 已有相关素材 |
| Looks good | 没问题 | 就这样 |
| Make cuts follow the music | 让剪辑跟着音乐节奏 | 剪辑跟着音乐节奏走 |
| Make the cuts follow the music | 让剪辑跟着音乐节奏 | 剪辑跟着音乐节奏走 |
| Manage Storage | 管理存储 | 管理存储空间 |
| Missing prerequisites for creation. | 缺少生成视频所需的内容，请检查后重试。 | 缺少制作影片所需的内容，请检查后重试。 |
| Moment | 片段 | 瞬间 |
| Moment %lld | 片段 %lld | 瞬间 %lld |
| Moment %lld (in a sentence) | (new key) | 第 %lld 个瞬间 |
| Moment %lld doesn't exist in this Story. | 这个故事里没有第 %lld 个片段。 | 这个故事里没有第 %lld 个瞬间。 |
| Moment added | 片段已添加 | 已添加瞬间 |
| Moment analysis is busy; will retry. | 片段分析正忙，稍后将自动重试。 | 瞬间分析繁忙，稍后自动重试。 |
| Moment analysis is rate-limited; will retry shortly. | 片段分析暂时受限，稍后将自动重试。 | 瞬间分析请求过多，稍后自动重试。 |
| Moment analysis paused — usage limit reached (%@). | 片段分析已暂停：已达到使用上限。 | 瞬间分析已暂停：已达使用上限。 |
| Moment order | 片段顺序 | 瞬间顺序 |
| Moment order. %@ | 片段顺序。%@ | 瞬间顺序。%@ |
| Moment sequence | 片段顺序 | 瞬间顺序 |
| Moment sequence. %@ | 片段顺序。%@ | 瞬间顺序。%@ |
| Moments | 片段 | 瞬间 |
| Mood | 氛围 | 影片氛围 |
| Mood, optional. %@ | 氛围，可选。%@ | 影片氛围，可选。%@ |
| More of the journey, people, and atmosphere. | 更多旅程、人物与氛围。 | 留下更多旅程细节、人物与真实感受。 |
| Move Moment %lld | 移动片段%lld | 移动第 %lld 个瞬间 |
| Music preferences aren't applied as a directive yet — this part is passed as a general note only. | 音乐偏好暂时无法作为明确指令执行，这部分只会作为一般说明参考。 | 音乐偏好暂时不能作为明确要求执行，这部分只作为参考说明。 |
| Music wasn't available for this version | 此版本未能使用音乐 | 这个版本没能加上音乐 |
| Music-led | 音乐主导 | 音乐为主 |
| Music-led sound | 音乐主导声音 | 以音乐为主 |
| No change — your current order is kept. | 无改动——保持当前顺序。 | 未做改动，保持现有顺序。 |
| No frames could be extracted from the Moment. | 无法从这个片段中提取画面。 | 无法从这个瞬间中提取画面。 |
| No Moments with both a local video file and a completed analysis — nothing to plan. | 没有同时具备本地视频和已完成分析的片段，暂时无法生成。 | 没有同时具备本地视频和分析结果的瞬间，暂时无法制作。 |
| No moments yet | 还没有片段 | 还没有瞬间 |
| No moments yet. Shoot one, or add photos or videos below. | 还没有片段。去拍一个，或在下方添加照片或视频。 | 还没有瞬间。去拍一段，或在下方导入照片、视频。 |
| No preference | 不限 | 不指定 |
| No sequence yet — the editor chooses the order. | 尚未设置顺序——由剪辑自动决定。 | 还没有设置顺序，将交给 AI 安排。 |
| No Story duration chosen — pick a duration before creating. | 还没有选择故事时长，请先选择时长再生成。 | 还没选择时长，请先选好再制作。 |
| No suggestions right now — switch to My Music, or create without music. | 暂时没有推荐——可以切换到“我的音乐”，或不加音乐直接生成。 | 暂时没有推荐，可以切换到“我的音乐”，或不加音乐直接制作。 |
| Not available for this video | 此视频不可用 | 这部影片暂不支持 |
| Not captured | 未拍摄 | 尚未拍摄 |
| Ongoing event context (optional) | 持续的活动背景（可选） | 活动背景信息（可选） |
| only these Moments | 仅使用这些片段 | 只用这些瞬间 |
| Opens the storyboard to choose and arrange Moments | 打开故事板以选择和排序片段 | 打开故事板，选择并调整瞬间顺序 |
| Opens the storyboard to reposition Moments | 打开故事板以调整片段位置 | 打开故事板，调整瞬间位置 |
| Optional idea — opens capture guidance | 可选的灵感——将打开拍摄指引 | 可选的灵感，会打开拍摄指引 |
| Other scenes | 其他场景 | 更多场景 |
| others allowed between | 允许穿插其他片段 | 可穿插其他瞬间 |
| Persistent details about your event you don't want to retype — itinerary, venue, who's there. | 不想反复输入的活动信息——行程、地点、同行的人。 | 不想每次重复输入的信息，比如行程、地点、和谁一起。 |
| Pick from moments you've already captured | 从你已拍摄的片段中挑选 | 从已拍下的瞬间中挑选 |
| Pin scene | 固定场景 | 固定这个场景 |
| Planning your Story… | 正在规划你的故事… | 正在构思剪辑… |
| Please rephrase your instruction so I can apply it. | 请换一种说法描述你的指令，以便我应用。 | 请换种说法描述你的要求，我才能照做。 |
| Preparing your moments… | 正在准备你的片段… | 正在准备你的瞬间… |
| Preparing your Story… | 正在准备你的故事… | 正在准备… |
| Protected %lld moments (moved for testing — not counted as freed). | 已保护 %lld 个片段（为测试而移动，不计入已释放）。 | 已保护 %lld 个瞬间（测试用，已移动，不计入释放空间）。 |
| Putting your Story together… | 正在合成你的故事… | 正在剪辑你的影片… |
| Re-create | 重新生成 | 重新制作 |
| Ready to create your Story. | 可以生成你的故事了。 | 可以把这些瞬间剪成影片了。 |
| Recent moments | 最近的片段 | 最近的瞬间 |
| Recent Moments | 最近的片段 | 最近的瞬间 |
| Recommended is tuned to your video type, or set your own. | 推荐时长会根据视频类型调整，你也可以自己设定。 | 推荐时长会根据影片类型调整，你也可以自己设定。 |
| Record | 录制 | 拍摄 |
| Remove Moment %lld from the sequence | 从顺序中移除片段%lld | 把第 %lld 个瞬间移出顺序 |
| Remove this moment | 移除此片段 | 移除这个瞬间 |
| Remove this moment? | 移除这个片段？ | 移除这个瞬间？ |
| Removing those Moments leaves only %lld to build from. Keep at least 2. | (new key) | 去掉这些瞬间后，只剩 %lld 个可用，至少需要保留 2 个。 |
| Rendering failed: %@ | 视频渲染失败，请重试。 | 影片渲染失败，请重试。 |
| Rendering your video… | 正在渲染你的视频… | 正在渲染影片… |
| Reset to AI order | 恢复 AI 排序 | 恢复 AI 顺序 |
| Reshoot → | 重拍 → | 再拍一次 → |
| Restoring your video… | 正在恢复你的视频… | 正在恢复你的影片… |
| Reuse moments you've already captured, or bring in media from your Photos. | 可以复用已拍摄的片段，也可以从相册导入。 | 可以选用已拍下的瞬间，也可以从相册导入。 |
| Revise | 修改 | 调整影片 |
| Revising your Story… | 正在修改你的故事… | 正在调整你的影片… |
| Room for the fuller story | 为完整故事留出空间 | 为完整故事留足时长 |
| Saves to Moments | 保存到片段 | 存入瞬间 |
| Several Moments can't all come right after %@. | (new key) | 多个瞬间不能都紧跟在%@之后。 |
| Shoot | 拍摄 | 去拍摄 |
| Shoot a moment | 拍摄片段 | 去拍摄 |
| Shoot or add a moment first. | 请先拍摄或添加片段。 | 先拍摄或添加一些瞬间吧。 |
| Shoot → | 拍摄 → | 去拍摄 → |
| Sign in to use Story's AI | 登录后即可使用 YoTale 的 AI 功能 | 登录后即可使用 AI 功能 |
| Sign out of Story? | 要退出 YoTale 登录吗？ | 要退出登录吗？ |
| Sign-in expired; Moment analysis will continue after you reopen YoTale. | 登录已过期，重新打开 YoTale 后将继续分析片段。 | 登录已过期，重新打开 YoTale 后会继续分析瞬间。 |
| Sit back — we're shaping your moments into a Story. | 放松一下——我们正在把你的片段编织成故事。 | 歇一会儿，我们正在把你的瞬间剪成影片。 |
| Sizing your Story… | 正在评估故事时长… | 正在估算影片时长… |
| Some of the original footage for this video is no longer available. | 这个视频的部分原始素材已不可用。 | 这部影片的部分原始素材已不可用。 |
| Some referenced Moments aren't ready yet. Please try again in a moment. | 部分提到的片段还没准备好，请稍后重试。 | 你提到的部分瞬间还没准备好，请稍后再试。 |
| Something went wrong creating the new version. You can try again. | 生成新版本时出了点问题。你可以重试。 | 创作新版本时出了点问题，可以再试一次。 |
| Start a Story | 开始一个故事 | 把瞬间，变成故事 |
| Start a Story from Home to see your projects and films here. | 在首页开始一个故事，你的作品和短片就会显示在这里。 | 在首页开始一个故事，你的故事和影片都会出现在这里。 |
| Start a Story. | 开始一个故事。 | 开始一个新故事。 |
| Start with %@ | 从 %@ 开始 | 从%@开始 |
| Start with Moment %lld | 从片段%lld开始 | 从瞬间 %lld 开始 |
| Start with Moment 8, drop Moment 4, make it more cinematic… | 从片段8开始，去掉片段4，让它更有电影感… | 从瞬间 8 开始，去掉瞬间 4，更有电影感一点… |
| Start with the mountain reveal, show the best moments, and make the cuts follow the music… | 先从山景揭幕开始，展示最精彩的片段，让剪辑跟着音乐走… | 从山景出现的那一刻开始，挑最精彩的画面，剪辑跟着音乐走… |
| Start with… | 从…开始 | 从某个瞬间开始 |
| Still looking at %lld more moments — your guide will fill in as they're ready. | 还在分析另外 %lld 个片段——它们就绪后，拍摄指南会更完善。 | 还有 %lld 个瞬间在分析中，分析完后指南会更完整。 |
| Still working on your Story — it's taking longer than usual. | 仍在处理你的故事，比平时花的时间更长。 | 影片仍在制作中，比平时久一些。 |
| Still working. Good edits take a little longer. | 仍在处理中。好的剪辑需要多一点时间。 | 还在剪辑中，好的剪辑值得多等一会儿。 |
| Story can | YoTale 可以 | 可以做到 |
| Story can tag the Moments you record with where you captured them, so your travel memories remember the place. Location is optional, stays on your device, and is never added to the videos you share. | YoTale 可以为你录制的片段标注拍摄地点，让旅行回忆记住那个地方。定位为可选项，仅保存在你的设备上，不会添加到你分享的视频中。 | YoTale 可以为你拍下的瞬间标注拍摄地点，让旅行回忆留住那个地方。定位是可选的，只保存在你的设备上，也不会出现在你分享的影片里。 |
| Story can't do %@ yet — it re-cuts, re-times, reorders, sets transitions and changes the soundtrack. Your current version is kept. Try rephrasing with a supported change. | YoTale 暂时无法做到“%@”——它可以重新剪辑、调整时长、调整顺序、设置转场和更换配乐。你当前的版本已保留，请换一种支持的修改方式试试。 | YoTale 暂时做不到“%@”。它可以重新剪辑、调整时长和顺序、设置转场、更换配乐。当前版本已保留，换一种可以做到的调整试试。 |
| Story can't do %@ yet. Apply the supported parts of your request and skip that? | YoTale 暂时无法做到“%@”。要只应用你请求中支持的部分、跳过它吗？ | YoTale 暂时做不到“%@”。要跳过这部分，只应用其余的调整吗？ |
| Story can't start a new video right now. Please try again in a moment. | YoTale 暂时无法开始生成新视频，请稍后再试。 | 暂时无法开始制作新影片，请稍后再试。 |
| Story has enough to work with. You can create your Story now. | YoTale 已有足够的素材，你现在就可以生成故事了。 | 素材已经足够，现在就可以制作影片了。 |
| Story is at capacity for AI video creation right now. Please try again later. | YoTale 的 AI 视频生成目前已满负荷，请稍后再试。 | 现在制作影片的人太多了，请稍后再试。 |
| Story keeps the existing edit unless you ask to change it. | 除非你要求修改，YoTale 会保留现有剪辑。 | 除非你提出修改，YoTale 会保留现有剪辑。 |
| Story length | 故事时长 | 影片时长 |
| Story will choose a fitting feel | YoTale 会选择合适的感觉 | YoTale 会挑选合适的感觉 |
| Tag your Moments with location? | 为片段标注拍摄地点？ | 为瞬间标注拍摄地点？ |
| Tap a moment to preview · close to return to the camera. | 点按片段即可预览 · 关闭后返回相机。 | 点按瞬间即可预览 · 关闭后返回相机。 |
| Tap a moment to preview · tap Select to add moments to this Story. | 点按片段即可预览 · 点按“选择”可将片段添加到此故事。 | 点按瞬间即可预览 · 点“选择”把瞬间加入这个故事。 |
| Tap a moment to preview · tap Select to pick moments for a new Story. | 点按片段即可预览 · 点按“选择”可为新故事挑选片段。 | 点按瞬间即可预览 · 点“选择”为新故事挑选瞬间。 |
| Tap a moment to preview · tap ✕ to remove it from this Story. | 点按片段可预览 · 点按 ✕ 可将其从故事中移除。 | 点按瞬间即可预览 · 点 ✕ 可将它移出这个故事。 |
| Tap moments to select · add them to this Story. | 点按选择片段 · 将它们添加到此故事。 | 点按挑选瞬间 · 加入这个故事。 |
| Tap moments to select · create a Story from them, or delete them. | 点按选择片段 · 用它们创建故事，或将其删除。 | 点按挑选瞬间 · 用它们创建故事，或删除。 |
| Tell your director what changed | 告诉导演有什么变化 | 说说你想调整什么 |
| Tell your director what changed, and the shooting script will update — your filmed and pinned scenes stay. | 告诉导演有什么变化，拍摄脚本就会随之更新——已拍摄和已固定的场景会保留。 | 说说有什么变化，拍摄指南会随之调整；已经拍过和已固定的场景都会保留。 |
| Thanks for your patience — finishing up your Story. You can keep waiting or cancel. | 感谢你的耐心——正在完成你的故事。你可以继续等待，也可以取消。 | 感谢耐心等待，影片马上就好。你可以继续等待，也可以取消。 |
| The best visual moments, beautifully cut. | 最精彩的画面，精心剪辑。 | 精选高光画面，节奏更轻快。 |
| the bottom Moment | 最下面的片段 | 最下面的瞬间 |
| The editor will choose the order. Add Moments above to arrange them yourself. | 由剪辑自动决定顺序。在上方添加片段即可自己排序。 | 将交给 AI 安排顺序。在上方添加瞬间，就能自己排。 |
| The moment is removed from this Story. This does not delete the original from your library. | 该片段将从这个故事中移除，不会删除片段库中的原片。 | 这个瞬间会从故事中移除，但不会删除原片。 |
| The Moment video could not be read. | 无法读取这个片段的视频。 | 无法读取这个瞬间的视频。 |
| The Moment video has no usable duration. | 这个片段的视频没有可用时长。 | 这个瞬间的视频没有可用时长。 |
| The ordering of %@ and %@ contradicts itself. | (new key) | %1$@和%2$@的顺序要求互相矛盾。 |
| The original files for these moments are no longer on this device. Re-add them to create your Story. | 这些片段的原始文件已不在此设备上。请重新添加后再生成故事。 | 这些瞬间的原始文件已不在这台设备上，重新添加后才能制作影片。 |
| The original video is uploaded privately to your YoTale account so it's safe if you lose this phone. It stays on this device too — nothing is deleted. Only you can access it; it won't appear for another account on this phone. | 原视频会私密上传到你的 YoTale 账号，即使手机丢失也不会丢。设备上也会保留一份，不会删除任何内容。只有你能访问，不会出现在这台手机上的其他账号中。 | 原视频会私密上传到你的 YoTale 账号，即使手机丢失也能找回。手机上也会保留一份，不会删除任何内容。只有你能查看，这台手机上的其他账号看不到。 |
| The plan can't be rendered: %@ | 无法生成这个视频，请重试。 | 这部影片没能渲染出来，请重试。 |
| The top Moment | 最上面的片段 | 最上面的瞬间 |
| There isn't enough usable footage for that length — try a shorter video. | 可用素材不足以达到这个时长——试试更短的视频。 | 可用素材不够这么长，试试短一点的影片。 |
| There isn't enough usable footage yet to build a Story. Capture a few more Moments and try again. | 可用的素材还不够生成故事。再拍几个片段后重试吧。 | 可用素材还不够制作影片。再拍几个瞬间后重试吧。 |
| There's about %llds of usable footage — not enough for a %llds Story. You can create a shorter %llds Story, or keep shooting. | 可用素材约 %1$lld 秒，不足以生成 %2$lld 秒的故事。你可以生成更短的 %3$lld 秒故事，或继续拍摄。 | 可用素材约 %1$lld 秒，不够制作 %2$lld 秒的影片。可以先做一部 %3$lld 秒的短片，或继续拍摄。 |
| There's only about %llds of usable footage — not enough for a %llds Story yet. Shoot or add a little more and try again. | 可用素材只有约 %1$lld 秒，还不足以生成 %2$lld 秒的故事。再拍摄或添加一些素材后重试。 | 可用素材只有约 %1$lld 秒，还不够制作 %2$lld 秒的影片。再拍一些或添加素材后重试。 |
| This change would have altered clips you didn't ask to change, so your current version was kept. Try naming the Moments to keep or move, or use Create Another Version for a fresh edit. | 这次修改会改动你没有要求更改的片段，因此已保留当前版本。你可以指明要保留或移动的片段，或使用“生成另一个版本”重新剪辑。 | 这次调整会改动你没要求修改的片段，所以保留了当前版本。可以指明要保留或移动哪些瞬间，或用“再创作一个版本”重新剪一版。 |
| This permanently removes the original media and analysis, and removes these moments from any Story that used them. Already-created videos are unaffected. | 这会永久删除原始素材和分析结果，并将这些片段从用到它们的故事中移除。已生成的视频不受影响。 | 这会永久删除原始照片、视频及分析结果，并把这些瞬间从所有用到它们的故事中移除。已经做好的影片不受影响。 |
| This request has a conflict. Please adjust it and try again. (%@) | (new key) | 这个要求有冲突，请调整后再试。（%@） |
| This Story is already being created. | 这个故事正在生成中。 | 这个故事的影片正在制作中。 |
| This Story moves out of your active Stories. You can still view Moments, create videos, or reopen it anytime. | 这个故事将从进行中的故事里移出。你仍可查看片段、生成视频，或随时重新打开。 | 这个故事将移出“进行中”。你仍可查看瞬间、制作影片，或随时重新打开。 |
| This Story returns to your active Stories. | 这个故事将回到进行中的故事。 | 这个故事将回到“进行中”。 |
| This video is backed up to your account. | 此视频已备份到你的账号。 | 这部影片已备份到你的账号。 |
| This video is no longer available. | 此视频已不可用。 | 这部影片已不可用。 |
| This video was made before version history, so its exact edit can't be reused. Create it again to enable Change Music. | 这个视频生成于版本记录功能上线之前，无法沿用原有剪辑。请重新生成后再更换音乐。 | 这部影片做于版本记录上线之前，无法沿用原来的剪辑。重新制作后就能更换音乐。 |
| This video was made before version history; its exact edit can't be reused. Re-create it to enable Change Music. | 这个视频生成于版本记录功能上线之前，无法复用原来的剪辑。请重新生成后再更换音乐。 | 这部影片做于版本记录上线之前，无法沿用原来的剪辑。重新制作后就能更换音乐。 |
| Tries the Moments that couldn't be analyzed again | 重新处理未能分析的片段 | 重新分析失败的瞬间 |
| Trim, reorder and select clips | 裁剪、调整顺序和挑选片段 | 裁剪、排序和挑选片段 |
| Turning Auto Backup on already does this. Use it again if some Moments still aren't backed up. | 开启自动备份时已经执行过此操作。如果仍有片段未备份，可以再次使用。 | 开启自动备份时已经做过这一步。如果仍有瞬间没有备份，可以再执行一次。 |
| Unpin scene | 取消固定场景 | 取消固定 |
| Update | 更新 | 调整 |
| Update Guide | 更新指南 | 调整指南 |
| Updating your shooting script… | 正在更新拍摄脚本… | 正在调整拍摄指南… |
| Uploads happen on Wi-Fi only. Moments wait until you're on Wi-Fi. | 仅在 Wi-Fi 下上传。片段会等到连上 Wi-Fi 后再上传。 | 仅在 Wi-Fi 下上传，瞬间会等连上 Wi-Fi 后再上传。 |
| Use every Moment | 使用每个片段 | 包含所有瞬间 |
| Use only the selected Moments | 只使用选中的片段 | 只用选中的瞬间 |
| Use the most beautiful views first | 先用最美的风景画面 | 先放最美的风景 |
| Video type | 视频类型 | 影片类型 |
| Visual inspiration · Not a preview of your actual shot | 视觉灵感 · 并非你实际画面的预览 | 视觉灵感 · 并非你的实际画面 |
| What about the other Moments? | 其他片段怎么处理？ | 其他瞬间怎么处理？ |
| What can Story edit? | YoTale 可以编辑什么？ | YoTale 能帮你怎么剪？ |
| What would you like to change? | 想修改什么？ | 想怎么调整？ |
| What's new | 有什么新情况 | 有什么新变化 |
| What's the event? (optional) | 是什么场合？（可选） | 这次要拍什么？（可选） |
| When on, your Moments on this phone — the ones you already have and new ones you add while signed in — are backed up to your YoTale account. Your originals always stay on this iPhone — nothing is deleted. | 开启后，这部手机上的片段——包括已有的和登录期间新增的——都会备份到你的 YoTale 账号。原片始终保留在这台 iPhone 上，不会删除任何内容。 | 开启后，这台手机上的瞬间（包括已有的和登录期间新增的）都会备份到你的 YoTale 账号。原片始终保留在这台 iPhone 上，不会删除任何内容。 |
| Why this matters | 为什么重要 | 为什么拍这一幕 |
| Writing your shooting script… | 正在撰写拍摄脚本… | 正在撰写拍摄指南… |
| You already have videos being created. Let those finish, then try again. | 你已有视频正在生成中，请等待完成后再试。 | 你已有影片正在制作中，请等它们完成后再试。 |
| You're all set. | 一切就绪。 | 准备好了。 |
| You've got what you need | 素材已经足够 | 素材已经够了 |
| You've reached a usage limit for AI video creation. Please try again later. | 你已达到 AI 视频生成的使用上限，请稍后再试。 | AI 影片制作已达使用上限，请稍后再试。 |
| You've reached this month's usage limit for AI video creation. It resets next month. | 你已达到本月 AI 视频生成的使用上限，下个月会重置。 | 本月的 AI 影片制作额度已用完，下个月会重置。 |
| You've reached today's limit for creating videos. Please try again tomorrow. | 你已达到今天的视频生成上限，请明天再试。 | 今天的影片制作次数已用完，请明天再来。 |
| Your captured memories | 你拍下的回忆 | 珍藏每一个瞬间 |
| Your captured Moments and saved Stories stay on this device either way. | 无论是否登录，你拍摄的片段和保存的故事都会保留在这台设备上。 | 无论是否登录，你的瞬间和故事都会保留在这台设备上。 |
| Your current order is kept. Add Moments above to reposition them. | 保持当前顺序。在上方添加片段即可调整位置。 | 保持现有顺序。在上方添加瞬间即可调整位置。 |
| Your current video is still available. You can leave and come back. | 当前视频仍可使用。你可以先离开，稍后再回来。 | 当前影片仍可观看。你可以先离开，稍后再回来。 |
| Your instruction couldn't be fully applied to this footage — some parts may conflict (for example an ordering or an exclude that leaves too little to work with). Try adjusting it. | 你的要求无法完全应用到这些素材上，其中部分内容可能相互冲突（例如顺序要求，或排除后剩下的素材太少）。请调整后再试。 | 你的要求无法完全应用到这些素材上，部分内容可能相互冲突（比如顺序要求，或去掉太多后剩下的素材不够）。请调整后再试。 |
| Your Moments and Stories stay on this device. You'll sign in again to use Story's AI. | 你的片段和故事会保留在这台设备上。再次使用 YoTale 的 AI 功能时需要重新登录。 | 你的瞬间和故事会保留在这台设备上。之后使用 AI 功能时需要重新登录。 |
| Your moments are still being analyzed. | 你的片段仍在分析中。 | 你的瞬间还在分析中。 |
| Your moments changed since this was made. | 自生成以来，你的片段有所变化。 | 这部影片做好后，你的瞬间有了变化。 |
| Your Moments on this phone that aren't backed up yet, and new Moments you add while signed in, will be uploaded privately to your YoTale account so they're safe if you lose this phone. Backing up a Moment associates it with this account. Originals stay on this device — nothing is deleted. Wi-Fi only unless you enable cellular. Only you can access your backups. | 这部手机上尚未备份的片段，以及你登录期间新增的片段，会私密上传到你的 YoTale 账号，即使手机丢失也不会丢。备份后，片段会与此账号关联。原片会保留在这台设备上，不会删除任何内容。除非开启蜂窝数据，否则仅在 Wi-Fi 下上传。只有你能访问你的备份。 | 这台手机上尚未备份的瞬间，以及你登录期间新增的瞬间，都会私密上传到你的 YoTale 账号，即使手机丢失也能找回。备份后，瞬间会归属此账号。原片仍保留在这台设备上，不会删除任何内容。未开启蜂窝数据时，仅在 Wi-Fi 下上传。只有你能查看自己的备份。 |
| Your moments will appear here | 你的片段会显示在这里 | 你的瞬间会出现在这里 |
| Your new version is ready | 新版本已就绪 | 新版本做好了 |
| Your projects and films | 你的作品与短片 | 你的故事，都在这里 |
| Your request only says which Moments to use or how to order them, but the result would remove some. Say which Moments to remove, or rephrase. | (new key) | 你的要求只说了用哪些瞬间、怎么排序，但结果会去掉一些瞬间。请说明要去掉哪些，或换种说法。 |
| Your Shooting Script | 你的拍摄脚本 | 拍摄指南 |
| Your Story already tells its story. You can keep capturing, or create it now. | 你的故事已经很完整了。可以继续拍摄，也可以现在就生成。 | 这些瞬间已经足够讲好这个故事了。可以继续拍，也可以现在就制作影片。 |
| Your Story is ready to begin. | 你的故事已准备就绪。 | 故事已建好，去拍下第一个瞬间吧。 |
| Your Story is taking shape. | 你的故事正在成形。 | 你的故事，正慢慢成形。 |
| Your text says to end with %@, but your order ends with %@. Drag the one you want to the bottom in Arrange, or edit the text. | 你的文字要求以 %1$@ 结尾，但当前顺序以 %2$@ 结尾。请在“排序”中把想要的片段拖到最下面，或修改文字。 | 你的文字要求用%1$@结尾，但当前顺序的结尾是%2$@。请在“调整顺序”中把想要的瞬间拖到最下面，或修改文字。 |
| Your text says to end with %@, but your sequence ends with %@. Drag the one you want to the bottom in Arrange Moments, or edit the text. | 你的文字要求以 %1$@ 结尾，但你的顺序以 %2$@ 结尾。请在“排序片段”中把想要的片段拖到最下面，或修改文字。 | 你的文字要求用%1$@结尾，但当前顺序的结尾是%2$@。请在“调整瞬间顺序”中把想要的瞬间拖到最下面，或修改文字。 |
| Your text says to start with %@, but your order starts with %@. Drag the one you want to the top in Arrange, or edit the text. | 你的文字要求以 %1$@ 开头，但当前顺序以 %2$@ 开头。请在“排序”中把想要的片段拖到最上面，或修改文字。 | 你的文字要求从%1$@开始，但当前顺序的开头是%2$@。请在“调整顺序”中把想要的瞬间拖到最上面，或修改文字。 |
| Your text says to start with %@, but your sequence starts with %@. Drag the one you want to the top in Arrange Moments, or edit the text. | 你的文字要求以 %1$@ 开头，但你的顺序以 %2$@ 开头。请在“排序片段”中把想要的片段拖到最上面，或修改文字。 | 你的文字要求从%1$@开始，但当前顺序的开头是%2$@。请在“调整瞬间顺序”中把想要的瞬间拖到最上面，或修改文字。 |
| Your video is ready | 你的视频已就绪 | 你的影片做好了 |
| ✦ Let Story choose | ✦ 交给 YoTale 选择 | ✦ 交给 YoTale 挑选 |
| Info.plist: NSCameraUsageDescription | YoTale 使用相机来拍摄你的片段。 | YoTale 需要使用相机来记录你的瞬间。 |
| Info.plist: NSLocationWhenInUseUsageDescription | YoTale 可以为你拍摄的片段标注拍摄地点，让旅行回忆记住那个地方。位置信息为可选项，也不会添加到你分享的视频中。 | YoTale 可以为你拍下的瞬间标注拍摄地点，让旅行回忆留住那个地方。定位是可选的，也不会出现在你分享的影片里。 |
| Info.plist: NSMicrophoneUsageDescription | YoTale 会在你拍摄片段时录制声音。 | YoTale 会在你拍摄视频时录制声音。 |
| Info.plist: NSPhotoLibraryAddUsageDescription | YoTale 会把你拍摄的片段保存一份到“照片”，这样你在 YoTale 之外也能保留它们。 | YoTale 会把你拍下的瞬间另存一份到“照片”，即使不用 YoTale，它们也依然属于你。 |
