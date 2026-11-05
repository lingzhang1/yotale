# C3.5 — Figma UX Convergence — Completion Report (Phase 7)

**Status:** ✅ CLOSED — physical-iPhone acceptance PASSED (2026-10-02, owner-verified).
The Phase-7 Figma-converged build runs correctly on a real iPhone and the product
UX is accepted. No further C3.5 UI changes. C4 NOT started.
**Frozen Figma:** `prototypes/story-figma/src/App.tsx` @ git `ba88526`.
**Scope rule honored:** zero changes to C1 Creative Intent, C2 Scene Understanding,
C3 Director, Opus model, prompts, contracts, ModelGateway, eval corpus, backend, or
AWS. C4 NOT started. 98 backend pytest green; all changed Swift `swiftc -parse` clean.

## Method (device-based gate, not inspection)
Real frozen-Figma renders (headless Chrome against the running prototype, iPhone
frame) laid beside real native iPhone renders (product-presentation mode). Values
read directly from `App.tsx`. References: `c35-figma-refs/*.png`,
`c35-native-refs/native_*.png`. Side-by-side detail: `c35-phase7-fidelity-audit.md`.

## Commits
Story app (github.com/lingzhang1/story):
- `de4a531` Phase 7 b1 — product/debug toggle + Home/wizard/Story Home fidelity
- `87e615e` b2 — image-forward Home cards, square mosaic, bundled placeholder photos
- `22cf573` fix — image-card/mosaic overflow broke hit-testing (cards/back tappable)
- `03844e1` fixes 1–9 — bundle Fraunces+DM Sans (OFL), scene-backed SHOT card,
  custom Complete/Reopen sheet, Moments manage screen + remove, display-title tidy
- `2da8481` fix — bound overflowing SHOT card, explicit ✕ on Moments tiles, custom back on Preview
- `372364b` fix — Moments mosaic tiles overflowed at 3+ moments; bound to clean square
Specs (github.com/lingzhang1/story-specs):
- `c022979` + `39227c4` — Figma + native reference renders, fidelity audit
- (this) — final reconciliation, capability-matrix Phase-7 update, completion report

## Final screen-by-screen reconciliation
Classification per frozen Figma surface: **R** = MATCHED+REAL · **D** = MATCHED+DISABLED
FUTURE CAPABILITY · **E** = MATCHED+EMPTY STATE · **X** = REAL_SYSTEM_EXTENSION.

| # | Figma surface | Native screen | Class | Notes |
|---|---|---|---|---|
| 1 | Home (no active Story) | HomeView (creation-first) | R | 2 full-bleed image cards (Create-now top, Start-a-Story), "Use photos" link; no Your-Stories list (matches Figma) |
| 2 | Home (active Story) | HomeView (active layout) | R | Continue hero (mosaic+body) + Create section + Your Stories (active→completed sort) |
| 3 | Start-a-Story · Describe | CreativeDirectionView.describe | R | Fraunces italic headline, dominant field, bottom-pinned Continue (+ title field = X) |
| 4 | Start-a-Story · Feel | CreativeDirectionView.feel | R | 2×2 presets, sibling-dim 0.5, gold-border+✓ select, dashed reference (D), describe field |
| 5 | Here's what I understood | CreativeDirectionView.context | R | reflects real C1 resolved intent; Music row = D |
| 6 | Here's what I'll look for | CreativeDirectionView.blueprint | D | Story Guide neutral-unavailable; "You're all set" + Start Story = R |
| 7 | Story Home | StoryHomeView | R | inline header, square 2×3 mosaic, cream pill + quiet Create; Idea/Guide = E/D (neutral, not TMB demo) |
| 8 | Scene Scan intro | SceneScanFlowView.intro | R | "Show me what's around you" + Start Scan + Cancel; live viewfinder on device |
| 9 | Director thinking | SceneScanFlowView.planning | X | staged copy over real ~12–16s, no fake % |
| 10 | Director Idea / Shot Guidance | SceneScanFlowView.recommendation | R / X | scene-backed card + "SHOT 1" label + concept + instruction + You/Hold; real Director output |
| 11 | rescan_scene decline | SceneScanFlowView.recommendation | X | "This scene doesn't quite fit" + Scan again (real C3 state, no Figma equiv) |
| 12 | Final Capture | ShootMomentView (camera) | R | real capture (Milestone A) |
| 13 | Create Story Preview | CreateStoryPreviewView | R / D | 3-col thumbnails + "N moments" + "Story will choose…"; Music D; Create generation D |
| 14 | Moments | MomentsManageView | R | full square grid, ✕ remove-from-Story (local), custom back |
| 15 | Complete / Reopen | StoryOptionsSheet | R / D | custom bottom sheet; Edit-details + Creative-direction rows = D ("Soon"); Complete/Reopen = R + styled confirm |
| 16 | Completed Story home | StoryHomeView (completed) | R | "Completed" + "Everything from your Story…" + Create my Story primary |
| 17 | Shot Validation | — | D (no entry point) | documented: no trigger until C4 wires the post-capture loop; not shipped as a dead view |
| 18 | Music track picker | — | D | ScreenTMBMusic surface reached only via disabled Music entries |
| 19 | Create → Result (generation) | CreateStoryPreviewView generate | D / E | real generation disabled; mock output DEBUG_ONLY |
| 20 | Existing-media analyze | Home "Use photos" | D | disabled entry (AssetUnderstanding) |

**No unexplained native UX omissions.** Every classified surface is present; each
non-R is an intentional disabled/empty state tracked in `ui-capability-matrix.md`.

## What Phase 7 corrected (vs the first, too-permissive pass)
- **Parity methodology** — judged by rendered comparison, not "a view exists".
- **Typography** — bundled Fraunces + DM Sans (SIL OFL); `StoryTheme` resolves them with a system fallback.
- **Home** — flat text cards → full-bleed image cards; removed the wrong Your-Stories list from the no-active state; correct card order.
- **Story Home** — filmstrip → true square 2×3 mosaic; inline header.
- **Wizard** — generic forms → per-step Figma composition (italic headlines, sibling-dim selection, gold ✓).
- **DIRECT Idea** — text-only → scene-photo-backed card + "SHOT 1" label.
- **Complete/Reopen** — system dialog → custom Figma bottom sheet + styled confirm.
- **Moments** — added the dedicated manage screen + remove-from-Story.
- **Diagnostics** — product/AI-debug toggle (`-STORY_MODE`), no App Store Release build needed.
- **Title artifact** — presentation-only `displayTitle` tidies "tMB"→"TMB" without touching C1.
- **Hit-testing + layout bugs** — bounded all `scaledToFill` images (cards, mosaic, shot card) so taps work and tiles don't overflow.

## Remaining differences (documented, with reason)
1. **Placeholder imagery is procedural gradients**, not photographs — by design, no licensed media. Real captured frames show wherever media exists (mosaic, shot card, preview).
2. **Describe has a title field** Figma lacks — native data model needs a title (REAL_SYSTEM_EXTENSION).
3. **No micron-level pixel match** — system vs Figma rendering of the same bundled fonts differs by sub-pixel; composition/hierarchy/spacing match.
4. **Future surfaces are disabled**, not absent — Validation (no trigger until C4), Music, real Create/Result, Story Guide/arc, reference, existing-media analyze.

## Physical-iPhone acceptance checklist (run in product mode: scheme arg `-STORY_MODE product`, or default)
1. Launch → Home. No "DEBUG" copy anywhere. Headlines render in Fraunces (serif, distinct from system).
2. No active Story: two image cards (Create now disabled on top, Start a Story), "Use photos" link, NO "Your Stories" list.
3. Tap **Start a Story** → Describe: italic headline, type a description, title; Continue enables and advances.
4. Feel: tap a preset → it gets gold border + ✓, siblings dim; "or describe it" works; Continue advances.
5. "Here's what I understood": shows the REAL resolved intent (title title-cased); Music row shows "Not available yet"; Looks good advances.
6. "Here's what I'll look for": Story Guide neutral-unavailable; Start Story → Story Home.
7. Story Home: inline header (← / title / •••), state line, mosaic (dashed empty state when 0 moments), cream "Shoot a moment", quiet "Create my Story", "+ Add photos or videos" (gold), neutral Story Idea + Story Guide.
8. Tap **Shoot a moment** → scan intro → Start Scan → thinking shows staged copy over the real wait (no %) → Idea card is scene-backed with "SHOT 1" and fits the screen → Let's shoot → camera → capture returns a Moment.
9. Shoot 3+ moments → mosaic is a clean square grid (no overflow/gaps), count overlay on last tile.
10. Tap the mosaic → Moments screen: grid of square tiles, each with a ✕; ← returns to Story Home; ✕ → "Remove from Story" confirm → removes (count drops), original library media untouched.
11. **+ Add photos or videos** → PHPicker → picked media appear as Moments.
12. **Create my Story** → Preview: custom ← back, 3-col thumbnails, "Story will choose…", Music disabled, Create generation disabled ("coming in a later update"). No real/mock output in product mode.
13. **•••** → custom bottom sheet: Edit details / Creative direction show "Soon" (disabled); Complete Story → styled confirm → completes (moves out of active; Home sorts it below active).
14. Reopen from the completed Story's ••• → returns to active.
15. Relaunch the app → Stories persist (SwiftData); active/completed state and Moments survive.
16. (AI-debug check) Relaunch with `-STORY_MODE aidebug` → the "What Story understood" chips + Director debug panel + Good/Bad feedback reappear; confirm they are ABSENT in product mode.

## Definition of Done
- [x] Every frozen Figma surface present natively (R / D / E / X), no unexplained omission
- [x] Capability matrix updated; zero unexplained MISSING (all carry dependency + milestone)
- [x] Fonts bundled; diagnostics behind product/debug toggle
- [x] Cheap capabilities wired (Complete/Reopen + sort, add-to-Moments, Moments remove)
- [x] 98 backend tests green; parse-clean; C1–C3/contracts/model/AWS untouched; C4 not started
- [x] **Physical-iPhone acceptance (owner-run) — PASSED 2026-10-02. C3.5 CLOSED.**
