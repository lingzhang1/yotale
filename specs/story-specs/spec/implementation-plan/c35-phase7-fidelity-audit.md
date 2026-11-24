# C3.5 Phase 7 — Screenshot-level Figma fidelity audit

**Frozen Figma:** `prototypes/story-figma/src/App.tsx` @ git `ba88526`
**Method:** real Figma renders (headless Chrome against the running prototype,
iPhone frame) laid against real native iPhone renders (product-presentation mode,
2026-10-02 device run). Values were read directly from `App.tsx`, not from memory.

- Figma reference renders: `c35-figma-refs/*.png`
- Native device renders (pre-correction, this review): `c35-native-refs/native_*.png`

Parity values: **MATCHED · PARTIAL · MISSING · REAL_SYSTEM_EXTENSION**.
A screen is only MATCHED when composition, hierarchy, type, spacing and the
disabled-feature treatment are visually and interactionally close — not merely
"an equivalent view exists".

---

## FIGMA | NATIVE (pre-fix) | DIFFERENCES | FIX

### 1. Home — `home.png` | `native_home.png`
- **Composition:** Figma (no active Story) = title + **two large full-bleed
  photographic cards** (Create now on top = city; Start a Story below = alpine),
  each 16:9, radius 20, eyebrow+title+sub overlaid on a bottom-up ink gradient,
  then a quiet centered "Use photos & videos I already have". **No "Your Stories"
  list in this state.**
- **Native pre-fix:** flat dark text cards; Start-a-Story on top; Create-now below;
  "Use photos" left-aligned muted; **"Your Stories" list shown (TMB entries)** —
  which Figma does *not* show when there is no active hero on this layout.
- **Differences:** no imagery; wrong card order; wrong card geometry (text box vs
  image hero); extra "Your Stories" list in the creation-first state; title 30→ Figma 28.
- **FIX (done):** `StoryImageCard` (16:9, radius 20, gradient, bundled placeholder
  photo `ph_city`/`ph_alpine`); Create-now moved on top (disabled); "Use photos"
  centered; **"Your Stories" removed from the no-active-story layout**; the active
  layout now matches Figma's Continue-hero + Create section + Your Stories list.
- **Parity:** PARTIAL → corrected toward MATCHED (verify on device).

### 2. Start-a-Story · Describe — `storyintent.png` | `native_describe.png`
- Figma: **italic Fraunces** headline, one tall bordered textarea (fills most of
  the screen, full placeholder prose), Continue cream pill bottom-pinned, **no
  title field**.
- Native pre-fix: system-serif italic headline (close), big field present but a
  second "Give it a title" field competes, Continue pinned.
- **Differences:** headline face (Fraunces italic vs system serif italic — font not
  bundled); native adds a required title field Figma doesn't have.
- **FIX (done):** headline via `displayItalic`; big field dominant at 220pt; title
  field kept but demoted below (native needs a title; documented deviation);
  Continue bottom-pinned with a `Spacer`.
- **Parity:** PARTIAL (REAL_SYSTEM_EXTENSION: the title field). Font = remaining diff.

### 3. Start-a-Story · Feel — `storydirection.png` | `native_feel.png`
- Figma: 2×2 preset cards, **unselected cards dim to 0.5 opacity when one is
  selected**, selected = `2px #d4a853` border + `rgba(212,168,83,0.08)` fill +
  18px gold ✓ circle inset 10/10; dashed "+ Add a reference"; "or describe it" field.
- Native pre-fix: selection used a plain gold border only, all cards full opacity,
  check present but not inset to Figma spec.
- **Differences:** no dim-siblings, no selected background tint, check placement/weight.
- **FIX (done):** dim unselected to 0.5; selected bg tint + 2px border; ✓ circle
  top-right inset 10; descriptor dot-line; exact radii/min-height (14 / 84).
- **Parity:** PARTIAL → corrected toward MATCHED.

### 4. "Here's what I understood" — (Figma `storycontext`) | `native_understood.png`
- Figma reflects the resolved intent + an inferred Music row (disabled) + "Looks
  good" / "Edit".
- Native: matches structure (title, resolved summary, Music disabled, Looks good /
  Edit). Headline is upright serif (Figma uses upright here too). Close.
- **Differences:** minor — Music block styling weight; title-case of resolved title
  ("tMB" is a real C1 output artifact, not a UI bug).
- **FIX:** none required this batch; Music block already a neutral disabled section.
- **Parity:** MATCHED + REAL (intent is real C1) · Music = MATCHED + DISABLED FUTURE.

### 5. "Here's what I'll look for" — (Figma `storyblueprint`) | `native_lookfor.png`
- Figma: Story Guide block (disabled future) + "You're all set." + Start Story pill.
- Native: matches — Story Guide neutral-unavailable, "You're all set.", Start Story.
- **FIX:** none required.
- **Parity:** MATCHED + DISABLED FUTURE (Story Guide) · Start = MATCHED + REAL.

### 6. Story Home — `tmb.png` | `native_storyhome_moments.png` / `_active.png` / `_empty.png`
- Figma: `← Title / Day N of 8` **inline header row**; qualitative state line;
  **true 2×3 SQUARE photo mosaic** (grid repeat(3,1fr), aspectRatio 1, gap 2, up to
  6, count overlaid bottom-right); cream "Shoot a moment" pill; quiet "Create my
  Story" text; divider; ✦ Story Idea (neutral here); divider; Story Guide (italic).
- **Native pre-fix:** large STACKED title; **mosaic rendered as a horizontal
  filmstrip of 3 narrow non-square tiles** (live `VideoPlayer`s), not a 2×3 square
  grid; otherwise sections present.
- **Differences (the #1 gap):** mosaic geometry (filmstrip vs square grid); header
  stacked vs inline; menu was an SF ellipsis vs `•••` text.
- **FIX (done):** `MomentsMosaic` rebuilt as a 3-col **square** grid (`aspectRatio
  1`), real first-frame thumbnails via `MomentThumbnailCache` with placeholder-tone
  fallback, count overlay on the last tile; empty state = dashed 16:5 panel; header
  rebuilt to the inline `← Title / status · •••` row; state line 17pt.
- **Parity:** PARTIAL → corrected toward MATCHED. Story Idea/Guide = MATCHED + EMPTY
  STATE (neutral, not TMB demo copy — correct per review §Story-Guide).

### 7. Scene Scan — `scene.png` | `native_scene.png`
- Figma: "Show me what's around you" + "Start Scan" gold pill + Cancel; dim scene
  image behind. Native: matches copy + gold pill + Cancel (no bg image — camera
  viewfinder fills it live on device).
- **FIX:** none required (viewfinder is real on device).
- **Parity:** MATCHED + REAL.

### 8. Director thinking — `thinking.png` | (in recording)
- Figma: staged serif copy, no fake %. Native: `StoryThinkingState` cycles staged
  copy over the real ~12–16s. **Parity:** MATCHED + REAL_SYSTEM_EXTENSION (real latency).

### 9. Director Idea / Shot Guidance — `idea.png` | `native_idea.png`
- Figma: shot card(s) with image + "SHOT n" gold label + pill meta + "Let's shoot"
  gold pill. Native: Concept title + description + "1 shot · ~N sec" + You/Hold +
  "Let's shoot" gold pill + Rescan + Cancel. Content is **real Director output**.
- **Differences:** Figma puts a scene image behind the shot card; native is text-first.
- **FIX:** deferred (needs the captured scene frame as backing — tracked). Content
  parity is strong; visual image-backing is the remaining delta.
- **Parity:** MATCHED + REAL (text) · image-backing = PARTIAL (remaining diff).

### 10. Final Capture — (Figma `finalcapture`)
- Real camera capture flow (Milestone A), wired. **Parity:** MATCHED + REAL.

### 11. Create Story Preview — `tmbpreview.png` | `native_preview.png`
- Figma: 3-wide moment strip + "N moments" + "Story will choose…" + Music (disabled)
  + Create (disabled, "coming in a later update"). Native: matches — now 3-col fixed
  grid with real first-frame thumbnails, Music `StoryUnavailableSection`, Create
  `StoryUnavailableButton`.
- **FIX (done):** thumbnails switched to cached first-frame; grid fixed 3-col.
- **Parity:** MATCHED + REAL (material) · Music + generation = MATCHED + DISABLED FUTURE.

### 12. Moments — `moments.png`
- Figma: full-screen moment grid. Native: Story Home mosaic taps through to Moments;
  dedicated manage/remove screen deferred (tracked). **Parity:** PARTIAL (remaining).

### 13. Complete / Reopen — `native_complete_menu.png` / `native_completed.png`
- Figma: `•••` → sheet (Edit details / Creative direction / Complete Story) → confirm
  sheet; completed state header reads "Completed" + "Everything from your Story, in
  one place." + Create my Story primary.
- Native: `•••` → confirmation dialog (Complete / Cancel) with the move-out message;
  completed header + state line + Create my Story match.
- **Differences:** native uses a system `confirmationDialog` (two-tap) vs Figma's
  custom bottom sheet with Edit-details / Creative-direction rows + a styled confirm.
- **FIX:** functional parity met (Complete/Reopen wired, correct copy); the custom
  sheet styling + the two extra menu rows (Edit details, Creative direction — both
  future) are a remaining visual delta, tracked.
- **Parity:** MATCHED + REAL (lifecycle) · menu styling = PARTIAL (remaining).

---

## Remaining differences after batch 2 (documented, with reason)
1. **Typography** — Fraunces + DM Sans are loaded from Google Fonts in Figma (open
   OFL fonts, not bundled locally). Per review §7, not downloading/bundling without
   explicit approval → system serif/sans fallback kept. Closest native match; the
   single largest residual visual delta. One-step to close on approval.
2. **Director Idea image-backing** — Figma shows the scene photo behind the shot card;
   native is text-first. Needs the captured scene frame surfaced as a backing image.
3. **Moments manage screen** — dedicated full grid + remove-from-Story deferred.
4. **Complete/Reopen menu** — custom bottom sheet + Edit-details / Creative-direction
   rows (both future) vs native system dialog.
5. **Placeholder imagery is procedural** — neutral gradient tones, not photographs, by
   design (no licensed media). Conveys the image-forward composition without fake content.

## Device gate
This audit's "native" column is the pre-correction device run. Batch-2 corrections
need a fresh **product-mode** device run to confirm the corrected composition. The
completion gate is that visual comparison, not parse/inspection.
