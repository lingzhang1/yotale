# Milestone (READ-ONLY AUDIT — Phase A): Create-My-Story Customization + Story Idea UX

**Status:** READ-ONLY AUDIT + PROPOSAL (2026-10-24). No code/prompts/schemas changed, no AI invoked, no
deploy, no persisted-user-data touched. For owner review before any implementation.
**Scope floor honored:** no change to Guide generation/refinement, Coverage matching/recovery, scene
identity/reconciliation, R7 contracts, provider routing, ModelGateway, EditPlan v2, rendering, cloud media,
auth, or AWS. OpenAI/Gemini preserved; no Anthropic. Treated code as authoritative; specs as intent only.

---

## 1. Headline findings

1. **The customization sheet the owner describes as "too many decisions" is MORE built-out than the brief
   assumes.** `CustomizeYourStoryView` ALREADY leads with natural-language Creative Direction (free text +
   Moment references + example chips + capability info) at the TOP, then Editing Approach (shown only when
   Visual-first is deployable), Story Length, and Sound. The NL-first direction the owner wants is largely
   already the primary interaction — the gap is (a) no optional **style/feeling presets**, and (b) the four
   explicit sections read as co-equal rather than "NL first, everything else optional/advanced."

2. **The removed style/feeling fields still EXIST in the contract and are consumed downstream — they are
   just not WRITTEN by any UI today.** `CreativeIntentContract.desired_feeling`, `.style_tags`, `.pace`
   are live fields; MusicDirection (deterministic) and the Edit Planner both read them. So optional style
   presets can be reused with **no new model or contract** — a preset chip just needs to write these
   existing fields (and/or `MusicDirection.mood_tags`/`energy`, which already accept a user-authored
   pass-through). **AVAILABLE BUT UNUSED**, not missing.

3. **Story Idea is genuinely behind the Guide redesign.** Its contract
   (`CoverageStoryIdea{title, description, rationale?, target_story_guide_dimension_id?}`) has **no capture
   instructions and no visual reference**, and the UI (`StoryIdeaSection`) is the old eyebrow+title+
   paragraph+Show-me. Modernizing the *card* is UI-only; adding a "how to capture it" line or an image is
   the one place that would need either a new AI field or reuse of the Guide image service (flagged below).

4. **No duplicate/contradictory music system exists today** — MusicDirection (deterministic character) →
   MusicPlan (energy arc) → the existing Epidemic selection flow is one pipeline. A style preset must feed
   THAT pipeline (via `MusicDirection`), not spawn a second selector. (Confirmed: `CustomizeYourStoryView`
   already routes an explicit `ParsedMusicIntent` into the existing flow, not a parallel one.)

---

## 2. Creative-preference data flow (as built)

```
Story title/description (the ONLY creation input today)
   -> POST /v1/creative-intent (OpenAI gpt-5.1) -> CreativeIntentContract
        desired_feeling[], style_tags[], pace, emphasis[], creative_constraints[],
        target_duration_seconds?, subject            (ALL inferred from free text; no UI writes them)
   -> persisted on StoryModel (intentRawText + the intent fields)
   -> Create My Story (CustomizeYourStoryView) writes, PER OUTPUT ATTEMPT:
        creativeDirectionText  (soft NL direction; ORIGINAL create only)
        creativeDirectivesJSON (resolved hard directives: opening/ending/order/include/exclude)
        editorialMode + explicit target seconds (length), SoundPreference, EditingApproach,
        ParsedMusicIntent (routes to MusicPlan)
   -> composeRevisionContext(...) folds these into revision_context {mode, directives, soft_direction,
        duration_target_source} on the EditPlan request
   -> async EditPlan job (OpenAI gpt-5.1, edit_plan/5.2) — directives = strong objectives, technical
        validation deterministic
   -> deterministic render -> GeneratedOutput
Music: CreativeIntent -> DeterministicMusicDirectionEngine (keyword map: pace->energy, feeling/style->
   mood_tags) -> MusicPlan (music_plan/1) -> Epidemic selection -> soundtrack.
```

### Answers to the §5 audit questions
1. **Persisted at STORY level:** `intentRawText`, the CreativeIntent fields (`desired_feeling`/`style_tags`/
   `pace`/…), `eventContext` (Guide), and the DRAFT `creativeDirectionText` + `creativeDirectivesJSON` (kept
   so Customize repopulates). These survive navigation/retry.
2. **Output-specific:** length (`editorialMode` + exact seconds), `SoundPreference`, `EditingApproach`,
   `ParsedMusicIntent`, and the per-attempt `revision_context` — chosen at Create-My-Story time, per output.
3. **Style/feeling after simplification:** the Start-a-Story setup that collected style/feeling/music was
   removed from CREATION; the underlying `desired_feeling`/`style_tags`/`pace` CONTRACT fields remain and are
   now populated only by the model's inference of the description. No UI writes them.
4. **Fields that can back optional style presets:** `CreativeIntent.desired_feeling` + `.style_tags` + `.pace`
   (visual/edit style), and `MusicDirection.mood_tags` + `.energy` (music character, user-authored pass-through
   already supported). No new field needed for the core presets.
5. **NL instructions into EditPlan:** resolved by the SHARED `InterpretationCoordinator` → hard
   `ResolvedDirectives` (opening/ending/order/include/exclude) + `soft_direction`, folded by
   `composeRevisionContext` into `revision_context` on the job body. Hard refs that don't resolve BLOCK submit
   (never silently dropped).
6. **Conflict resolution:** newest typed directive wins per slot; saved directives fold only where the new
   input didn't set that slot; technical validation stays deterministic; creative directives are objectives
   (EditPlan v2), not terminal.
7. **Story-level vs output override:** story-level = CreativeIntent + eventContext (durable);
   output-override = the per-attempt Customize choices + `revision_context`. `composeRevisionContext` folds the
   one-time creation-time directives for the ORIGINAL create ONLY (`operationType=="original"`), so a later
   Explore/Revise does not silently inherit them.
8. **Survives navigation/retry/subsequent output:** draft `creativeDirectionText` + chip ids + saved
   directives repopulate the sheet; length/sound/approach re-seed from the Story's prior explicit choice
   (issue-1 prefill). A retry of the original create re-applies them; a NEW version mints a fresh operation id.
9. **Revise reuse:** Revise supplies its OWN directives (does not inherit the one-time creation instruction);
   preservation-first reconciliation applies (recent fix). Appropriate.
10. **Create Another Version:** stays `mode=explore` (confirmed in `composeRevisionContext` — the explore→
    revise reroute was deliberately removed); directives ride along as objectives without Revise's
    base-plan-preservation framing. Explore semantics intact.
11. **Music representation:** MusicDirection (mood_tags/energy/summary, authoritative character) →
    MusicPlan (energy arc + audio_strategy) → selected Epidemic track + SoundPreference (native-vs-music mix).
    One pipeline; `ParsedMusicIntent` from the sheet routes into it.
12. **Visual-first vs Storytelling — REAL behavior difference, confirmed:** Visual-first builds per-Moment
    contact sheets and sends them (multimodal planning_mode) so the planner reasons over pixels; Storytelling
    is text-only. It changes input preparation (frame extraction + sheets), the request payload, model cost
    (image tokens), and the plan. It is NOT a cosmetic toggle. (Note: Visual-first is gated behind
    `StoryMultimodalPlanning.enabled`; the section is hidden when it can't run.)

### Duplicated / ignored / contradictory controls found
- **Ignored:** `CreativeIntent.desired_feeling`/`style_tags`/`pace` have no write surface post-simplification
  (dormant style fields) — the single biggest reuse opportunity.
- **Potentially over-exposed:** Editing Approach (Visual-first vs Storytelling) is real but uses filmmaking
  terminology an ordinary user won't parse — a candidate for Advanced/progressive disclosure, not removal.
- **No contradictions** between the sheet and the backend were found; the music routing is single-path.

---

## 3. Recommended customization design — **Option B+ (compact AI summary + optional Customize, with presets inside)**

Comparison (user effort / clarity / control / complexity / contract-fit / beta-readiness):

| Option | Effort | Clarity | Control | Complexity | Contract fit | Beta |
|---|---|---|---|---|---|---|
| A — simplified sheet + advanced | low | good | full | **low (UI-only)** | reuses all | ready |
| **B — compact AI summary + optional Customize (presets inside)** | **lowest** | **best** | full on demand | low-med (UI-only) | reuses all | ready |
| C — pure NL, no presets | lowest | medium | NL-only | low | reuses all | risky (no quick style) |

**Recommend B.** It matches the product promise (AI as creative director; zero required choices) while keeping
every existing control reachable. Concretely:

- **Create screen (default path):** a compact **"Story direction"** card showing the AI-inferred summary in
  plain language (e.g. *"A calm, personal travel story — ~30s, balanced sound"*) + a single primary
  **"Create my Story"** button. **No required choices.** (Scenario A/C satisfied with zero taps.)
- **One optional "Customize" affordance** opens the EXISTING `CustomizeYourStoryView`, reorganized as:
  - **Creative Direction** (NL + Moment refs) — primary, unchanged.
  - **NEW: optional Feeling/Style preset chips** — Cinematic / Energetic / Emotional / Playful / Calm
    (examples, not frozen). Multi-select, OFF by default. Selecting a chip writes
    `CreativeIntent.style_tags`/`desired_feeling` (+ maps to `pace` where unambiguous) AND seeds
    `MusicDirection.mood_tags`/`energy` as user-authored — so one tap steers BOTH edit style and music through
    the existing fields/pipeline. Presets are additive inspiration; NL always wins where both are present.
  - **Simple controls:** Story Length, Sound (unchanged).
  - **Advanced (progressive disclosure, collapsed):** Editing Approach (Visual-first/Storytelling) relabeled
    in plain language, plus any future technical prefs. Hidden by default.
- **Music:** unchanged workflow; presets feed `MusicDirection`, never a second selector.

Example copy:
- Card: *"Story direction"* · *"A warm, personal highlight — about 30 seconds, balanced sound. Tap Customize
  to steer it."* · **[Create my Story]** **[Customize]**
- Preset row (inside Customize): *"Give it a feel (optional)"* — `Cinematic` `Energetic` `Emotional`
  `Playful` `Calm`.

This is **UI-only** and rides existing contracts; the presets are the one genuinely new (small) surface.

---

## 4. Recommended Story Idea design

**Current contract:** `{title, description, rationale?, target_story_guide_dimension_id?}` — **no capture
instruction, no image.** "Show me" routes into Director via `targetStoryGuideDimensionId`. It updates when
Coverage recomputes (fingerprint) and is null when coverage finds no gap (correct — do not force filler).

**Recommend a contextual card visually consistent with the Guide, built from what EXISTS:**
- **Eyebrow:** "A moment worth capturing" · **Title:** `idea.title` · **Why:** `idea.rationale ?? description`.
- **"How to capture it":** use `idea.description` as the practical line (it reads as a concept today). A truly
  capture-specific instruction is NOT in the contract — see the flagged decision below.
- **Visual reference:** **reuse the existing Guide image service** keyed off `targetStoryGuideDimensionId`
  when the idea targets a known scene (no new inference, no decorative image); omit the image otherwise.
- **Show me →** unchanged (Director entry).
- **Dismissal / empty / stale / loading:** support dismiss (local, per-idea, re-surfaces on a materially new
  idea); empty state = no card (already the behavior); stale = show last idea dimmed until recompute lands;
  loading = the existing coverage spinner.

**Flagged owner decision (the only part that may need a new AI field):** if you want a distinct, idea-specific
"how to capture it" line (not just the concept `description`), that requires either (a) adding a
`capture_hint` string to the Story Idea contract + a prompt tweak (OUT of this read-only scope; a separate
tiny additive change), or (b) accepting `description` as the how-to line (no change). **Recommend (b) for
beta** — ship the modern card now with existing fields; defer `capture_hint` unless the concept text proves
insufficient on device.

---

## 5. Exact implementation scope (for the follow-up build milestone)

**UI-only, reuses existing contracts:**
- `CustomizeYourStoryView.swift` — reorganize into NL-first + optional preset chips + Advanced disclosure;
  add a preset model that writes `style_tags`/`desired_feeling`/`pace` + `MusicDirection` seed.
- `CreateStoryPreviewView.swift` / Story Home create entry — add the compact "Story direction" summary card
  + single Create button + optional Customize.
- `StoryCoverageViews.swift` (`StoryIdeaSection`) — redesign the card to Guide-visual language; optional
  reuse of the Guide image service by `targetStoryGuideDimensionId`.
- Reusable components already present: `PromptSuggestionChips`, `CapabilityInfoButton`, the Guide scene-card
  styling, the Guide image/Unsplash service, `StoryEyebrow`, the gold-ring selected-row style.

**Existing fields used (no schema change for the core):** `CreativeIntent.desired_feeling/style_tags/pace`,
`MusicDirection.mood_tags/energy`, `StoryModel.creativeDirectionText/creativeDirectivesJSON`, the Story Idea
DTO as-is.

**Possible NEW (flagged, deferrable):** a `capture_hint` field on the Story Idea contract (+ prompt) IF the
owner wants a distinct how-to line. Not required for beta.

**No backend/schema/infra change required for the recommended beta scope.**

---

## 6. Scenario check
- **A (minimal):** compact summary + Create → zero config, AI infers. ✓ (no change to immediate creation)
- **B (TMB cinematic):** NL "cinematic, mountain-focused" OR the Cinematic preset → `style_tags`; length+sound
  respected; no redundant questions. ✓
- **C (wedding energetic/joyful):** one preset or NL sentence; no Visual-first/Storytelling knowledge needed
  (it's in Advanced). ✓
- **D (Moment 5 then 2, keep audio):** existing Moment references + `InterpretationCoordinator` + Immersive
  sound → directives reach EditPlan. ✓ (already supported)
- **E (Story Idea):** modern card shows what/why/how + Show me → Director. ✓ (UI redesign)
- **F (no idea):** card hidden; Home coherent; no filler. ✓ (already the behavior)

---

## 7. Regression + device acceptance plan
- iOS: `CustomizeYourStoryViewTests` (preset→fields mapping, presets optional, NL-wins-over-preset),
  `StoryCreationCoordinatorTests` (presets fold into CreativeIntent/MusicDirection; original-only folding
  preserved), `StoryGuideCoverageV2DTOTests` / a new `StoryIdeaCardTests` (card renders what/why/how, image
  reuse, dismiss, null-idea hidden). Backend: unchanged (no contract change in beta scope) — existing
  coverage/music suites must stay green.
- Device acceptance: Scenarios A–F on a physical device; confirm presets steer both edit style and music;
  confirm Story Idea card matches the Guide and Show-me still enters Director; confirm zero-config create.

---

## 8. Milestones (prioritized for TestFlight)
1. **M1 (UI, highest value):** compact "Story direction" summary card + single Create + optional Customize
   entry. Delivers "zero required choices." UI-only.
2. **M2 (UI):** optional Feeling/Style preset chips inside Customize, wired to existing
   `style_tags`/`desired_feeling`/`pace` + `MusicDirection` seed; NL-wins precedence.
3. **M3 (UI):** Advanced progressive disclosure for Editing Approach (plain-language relabel).
4. **M4 (UI):** Story Idea card redesign (what/why/how + optional Guide-image reuse + dismiss).
5. **Deferred:** `capture_hint` Story-Idea field (+prompt) — only if `description` proves insufficient.

## 9. Risks / trade-offs / open owner decisions
- **Preset→pace mapping ambiguity:** "Cinematic" implies mood but not clearly a pace; map presets to
  `style_tags`/`desired_feeling` always, `pace` only for unambiguous ones (Energetic→fast, Calm→slow).
- **Preset vs NL precedence:** recommend NL (and explicit chips) win per slot; a preset only fills what NL
  left unset. Owner confirm.
- **Story Idea how-to line:** (b) reuse `description` for beta vs (a) add `capture_hint`. Owner decision.
- **Image reuse for Story Idea:** only when `targetStoryGuideDimensionId` resolves to a Guide scene with an
  image; never a decorative fetch. Owner confirm "no image when none relevant" is acceptable.

## 10. Classification
- **Already implemented:** NL-first Creative Direction, Moment refs, length, sound, music pipeline,
  Explore/Revise semantics, Visual-first (gated), Story Idea generation + Show-me→Director.
- **Available but unused:** `CreativeIntent.desired_feeling/style_tags/pace` (dormant style fields);
  `MusicDirection` user-authored pass-through.
- **Requires modification (UI):** Customize layout + presets, create-screen summary card, Story Idea card.
- **Requires new functionality:** only the optional preset chips (UI) and — deferred — a `capture_hint` field.
- **Deferred:** `capture_hint`; any advanced technical editing prefs beyond approach.
